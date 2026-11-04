"""Fine-tune a transformer as a 14-check paragraph classifier.

    ml/.venv/Scripts/python -m ml.finetune data/imbroglio/v0.2-split1 --name roberta-u1 \
        --unlabeled-weight 1.0

Runs in the training environment (ml/requirements-train.txt), not the
pipeline's. One model reads a paragraph and gives 14 independent scores, one
per check (multi-label: sigmoid outputs with binary cross-entropy).

Labels come from Claude (distillation from silver labels): positive where a
verified quote for the check lies in the paragraph. The open question is what
to do with every other paragraph, and `--unlabeled-weight` covers the range:

  * clean negatives, paragraphs of documents that don't address the check at
    all, always count as negatives with weight 1
  * unlabeled paragraphs, in documents that do address the check but that
    Claude didn't quote, count as negatives with weight w:
      w = 1    treat them as negatives (noisy: some answer the question)
      w = 0    ignore them, train on positives and clean negatives only
               (easy negatives: the model may learn the document's topic
               rather than what a paragraph says)
      0 < w < 1  in between, a simple positive-unlabeled weighting
  * paragraphs whose quote failed only the evidence-word check are ignored

Positives are rare (under 1% of paragraphs for every check), so each check's
positives are weighted by sqrt(negatives / positives) (`--pos-weight`).

Each epoch is scored on dev with ml.metrics (macro MRR decides the best
epoch). The best epoch's scores are saved as runs for dev and test, next to
a JSON log of the settings and every epoch's figures.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from ml.dataset import read_jsonl
from ml.metrics import Scorer, load_split, save_run


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def targets(p: dict, checks: list[str], unlabeled_weight: float) -> tuple[list[float], list[float]]:
    """Per check, the target (1 or 0) and the loss weight (0 drops it)."""
    y, w = [], []
    for c in checks:
        if c in p["pos"]:
            y.append(1.0); w.append(1.0)
        elif c in p["kw_failed"]:
            y.append(0.0); w.append(0.0)
        elif c in p["neg"]:
            y.append(0.0); w.append(1.0)
        else:
            y.append(0.0); w.append(unlabeled_weight)
    return y, w


def training_rows(dataset: Path, checks: list[str], unlabeled_weight: float, fraction: float, seed: int):
    """Training paragraphs, optionally from a random share of the training
    site groups (whole groups, so the learning curve keeps the split's
    independence)."""
    docs = [d for d in read_jsonl(dataset / "documents.jsonl") if d["split"] == "train"]
    groups = sorted({d["group"] for d in docs})
    keep = set(random.Random(seed).sample(groups, max(1, round(fraction * len(groups)))))
    keep_docs = {d["version_id"] for d in docs if d["group"] in keep}
    rows = []
    for p in read_jsonl(dataset / "paragraphs.jsonl"):
        if p["split"] == "train" and p["version_id"] in keep_docs:
            y, w = targets(p, checks, unlabeled_weight)
            rows.append((p["text"], y, w))
    return rows, len(keep_docs)


def positive_weights(rows, n_checks: int, mode: str) -> torch.Tensor:
    y = np.array([r[1] for r in rows])
    w = np.array([r[2] for r in rows])
    pos = (y * (w > 0)).sum(0)
    neg = ((1 - y) * w).sum(0)
    ratio = neg / np.maximum(pos, 1)
    return torch.tensor({"none": np.ones(n_checks), "sqrt": np.sqrt(ratio), "full": ratio}[mode], dtype=torch.float32)


def collate(tokenizer, max_len: int):
    def fn(batch):
        enc = tokenizer([b[0] for b in batch], truncation=True, max_length=max_len, padding=True, return_tensors="pt")
        enc["labels"] = torch.tensor([b[1] for b in batch])
        enc["weights"] = torch.tensor([b[2] for b in batch])
        return enc
    return fn


@torch.no_grad()
def predict(model, tokenizer, texts: list[str], max_len: int, batch: int, device) -> np.ndarray:
    """Logits for every text, batched by length so padding stays small."""
    model.eval()
    order = np.argsort([len(t) for t in texts])
    out = np.zeros((len(texts), model.config.num_labels), np.float32)
    for i in range(0, len(texts), batch):
        idx = order[i:i + batch]
        enc = tokenizer([texts[j] for j in idx], truncation=True, max_length=max_len, padding=True,
                        return_tensors="pt").to(device)
        with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            out[idx] = model(**enc).logits.float().cpu().numpy()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dataset", type=Path, help="directory written by ml.dataset")
    ap.add_argument("--name", required=True, help="run name, used for the output files")
    ap.add_argument("--model", default="roberta-base")
    ap.add_argument("--unlabeled-weight", type=float, default=1.0)
    ap.add_argument("--pos-weight", choices=["none", "sqrt", "full"], default="sqrt")
    ap.add_argument("--train-fraction", type=float, default=1.0, help="share of training site groups")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("data/imbroglio/runs"))
    ap.add_argument("--save-model", type=Path, help="directory for the best checkpoint")
    ap.add_argument("--limit", type=int, help="train on the first N paragraphs only (smoke test)")
    args = ap.parse_args()

    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dev, test = load_split(args.dataset, "dev"), load_split(args.dataset, "test")
    checks = dev.checks
    texts = {(p["version_id"], p["idx"]): p["text"] for p in read_jsonl(args.dataset / "paragraphs.jsonl")
             if p["split"] != "train"}
    rows, n_docs = training_rows(args.dataset, checks, args.unlabeled_weight, args.train_fraction, args.seed)
    if args.limit:
        rows = rows[:args.limit]
    pos_w = positive_weights(rows, len(checks), args.pos_weight).to(device)

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=len(checks), problem_type="multi_label_classification").to(device)
    loader = DataLoader(rows, batch_size=args.batch, shuffle=True, collate_fn=collate(tokenizer, args.max_len),
                        generator=torch.Generator().manual_seed(args.seed))
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = args.epochs * len(loader)
    sched = get_linear_schedule_with_warmup(opt, int(0.06 * steps), steps)
    scorer = Scorer(dev, 1)

    log = {"settings": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
           "training_paragraphs": len(rows), "training_documents": n_docs,
           "pos_weight": dict(zip(checks, map(float, pos_w.cpu()))), "epochs": []}
    dev_texts = [texts[k] for k in dev.keys]
    best = None
    for epoch in range(1, args.epochs + 1):
        model.train()
        t, total, seen = time.time(), 0.0, 0
        for step, batch in enumerate(loader, 1):
            labels, weights = batch.pop("labels").to(device), batch.pop("weights").to(device)
            batch = batch.to(device)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits = model(**batch).logits.float()
            loss_each = torch.nn.functional.binary_cross_entropy_with_logits(
                logits, labels, weight=weights, pos_weight=pos_w, reduction="sum")
            loss = loss_each / weights.sum().clamp(min=1)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
            total += loss.item() * len(labels); seen += len(labels)
            if step % 200 == 0:
                print(f"epoch {epoch} step {step}/{len(loader)} loss {total / seen:.4f} "
                      f"({seen / (time.time() - t):.0f} paragraphs/s)", flush=True)
        s_dev = predict(model, tokenizer, dev_texts, args.max_len, 128, device)
        figs = scorer.figures(scorer.prepare(s_dev))
        entry = {"epoch": epoch, "train_loss": total / seen, "minutes": (time.time() - t) / 60,
                 **{k: figs[f"macro/{k}"] for k in ("recall@1", "recall@5", "mrr", "auroc")},
                 "per_check_mrr": {c: figs[f"{c}/mrr"] for c in checks}}
        log["epochs"].append(entry)
        print(f"epoch {epoch}: dev macro MRR {entry['mrr']:.3f}, recall@5 {entry['recall@5']:.3f}, "
              f"AUROC {entry['auroc']:.3f}", flush=True)
        if best is None or entry["mrr"] > best[0]:
            best = (entry["mrr"], epoch, s_dev)
            if args.save_model:
                model.save_pretrained(args.save_model)
                tokenizer.save_pretrained(args.save_model)
            s_test = predict(model, tokenizer, [texts[k] for k in test.keys], args.max_len, 128, device)
            save_run(args.out / f"{args.name}-dev.npz", dev.keys, s_dev, checks)
            save_run(args.out / f"{args.name}-test.npz", test.keys, s_test, checks)
    log["best_epoch"] = best[1]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{args.name}.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(f"best epoch {best[1]} (dev macro MRR {best[0]:.3f}); runs and log in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
