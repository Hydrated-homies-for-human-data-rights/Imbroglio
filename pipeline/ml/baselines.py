"""Classical paragraph classifiers, one binary model per check.

    python -m ml.baselines data/imbroglio/v0.2-split1 --out data/imbroglio/runs

Models, each scored with ml.metrics on dev and saved as runs for both dev and
test:

  * floors: random scores, paragraph length, and the rubric's evidence words
    (the rule the live pipeline uses to accept a quote)
  * TF-IDF (word 1- and 2-grams) with logistic regression
  * TF-IDF with a linear SVM

Training labels: a paragraph is positive for a check when it holds a verified
quote for it and negative otherwise. That treats unquoted paragraphs as
negatives even though some answer the question; how much that costs is the
question Gage's transformer experiments take up. Paragraphs whose quote was
rejected only for lacking an evidence word are left out of training for that
check, since nobody knows which side they belong on.

Both classifiers weight classes by inverse frequency (positives are under 1%
of paragraphs for every check) and choose C per check on dev MRR. Dev figures
for the tuned models are therefore slightly optimistic; test is scored once,
at the end, against the gold set.

The evidence-word floor is flattered on these labels: a quote only counts as
verified if it contains an evidence word, so every positive matches the rule.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC

from imbroglio.rubric import load
from ml.dataset import read_jsonl
from ml.metrics import Scorer, load_split, report, save_run

C_GRID = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0)
TOP_FEATURES = 15


def texts_by_split(dataset: Path) -> dict[str, dict[tuple[int, int], dict]]:
    out = {"train": {}, "dev": {}, "test": {}}
    for p in read_jsonl(dataset / "paragraphs.jsonl"):
        out[p["split"]][(p["version_id"], p["idx"])] = p
    return out


def floors(split, rows: list[dict], rubric, seed: int = 0) -> dict[str, np.ndarray]:
    length = np.array([len(p["text"]) for p in rows], float)
    evidence = np.array([[float(rubric.check(c).relevant(p["text"])) for c in split.checks] for p in rows])
    return {"random": np.random.default_rng(seed).random((len(rows), len(split.checks))),
            "length": np.repeat(length[:, None], len(split.checks), 1),
            # ties among matching paragraphs are broken by length, so the rule ranks
            "evidence_words": evidence + 1e-6 * length[:, None]}


def make_model(kind: str, c: float):
    if kind == "logreg":
        return LogisticRegression(C=c, class_weight="balanced", solver="liblinear", max_iter=2000)
    return LinearSVC(C=c, class_weight="balanced", max_iter=5000)


def scores_of(model, x) -> np.ndarray:
    return model.decision_function(x)


def train_check(kind, x_train, y, keep, x_dev, dev_scorer_fn):
    """Fit every C in the grid; return the best model by dev MRR and the
    whole tuning curve."""
    best, curve = None, {}
    for c in C_GRID:
        model = make_model(kind, c).fit(x_train[keep], y[keep])
        mrr = dev_scorer_fn(scores_of(model, x_dev))
        curve[c] = mrr
        if best is None or mrr > best[1]:
            best = (model, mrr, c)
    return best, curve


def run(dataset: Path, out: Path, n_boot: int = 1000) -> str:
    rubric = load("v0.2")
    paras = texts_by_split(dataset)
    dev, test = load_split(dataset, "dev"), load_split(dataset, "test")
    checks = dev.checks
    train_keys = list(paras["train"])
    train_rows = [paras["train"][k] for k in train_keys]
    dev_rows = [paras["dev"][k] for k in dev.keys]
    test_rows = [paras["test"][k] for k in test.keys]

    t = time.time()
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_df=0.5, sublinear_tf=True, strip_accents="unicode")
    x_train = vec.fit_transform(p["text"] for p in train_rows)
    x_dev = vec.transform(p["text"] for p in dev_rows)
    x_test = vec.transform(p["text"] for p in test_rows)
    vocab = np.array(vec.get_feature_names_out())
    log = [f"TF-IDF: {x_train.shape[1]} features from {x_train.shape[0]} training paragraphs "
           f"({time.time() - t:.0f} s)."]

    scorer = Scorer(dev, n_boot)
    quick = Scorer(dev, 1)    # point figures only, for tuning

    def dev_mrr(j):
        def fn(s):
            full = np.zeros((len(dev.keys), len(checks)))
            full[:, j] = s
            return quick.figures(quick.prepare(full))[f"{checks[j]}/mrr"]
        return fn

    sections, summary, tuning, features = [], [], [], {}
    runs = {name: (s_dev, floors(test, test_rows, rubric)[name])
            for name, s_dev in floors(dev, dev_rows, rubric).items()}
    for kind in ("logreg", "svm"):
        t = time.time()
        s_dev = np.zeros((len(dev.keys), len(checks)))
        s_test = np.zeros((len(test.keys), len(checks)))
        for j, c in enumerate(checks):
            y = np.array([c in p["pos"] for p in train_rows])
            keep = np.array([c not in p["kw_failed"] for p in train_rows])
            (model, mrr, best_c), curve = train_check(kind, x_train, y, keep, x_dev, dev_mrr(j))
            s_dev[:, j] = scores_of(model, x_dev)
            s_test[:, j] = scores_of(model, x_test)
            tuning.append(f"| {kind} | {c} | " + " | ".join(f"{curve[g]:.3f}" for g in C_GRID) + f" | {best_c} |")
            if kind == "logreg":
                w = model.coef_.ravel()
                features[c] = {"positive": vocab[np.argsort(-w)[:TOP_FEATURES]].tolist(),
                               "negative": vocab[np.argsort(w)[:TOP_FEATURES]].tolist()}
        runs[kind] = (s_dev, s_test)
        log.append(f"{kind}: 14 checks x {len(C_GRID)} values of C in {time.time() - t:.0f} s.")

    for name, (s_dev, s_test) in runs.items():
        save_run(out / f"{name}-dev.npz", dev.keys, s_dev, checks)
        save_run(out / f"{name}-test.npz", test.keys, s_test, checks)
        scored = scorer.score(s_dev)
        sections.append(report(scored, checks, f"{name} on dev"))
        summary.append(f"| {name} | " + " | ".join(
            f"{scored[f'macro/{m}'][0]:.3f} ({scored[f'macro/{m}'][1]:.3f} to {scored[f'macro/{m}'][2]:.3f})"
            for m in ("recall@1", "recall@5", "mrr", "auroc")) + " |")

    lines = ["# Classical baselines on dev", "", *log, "",
             "Macro averages over the 14 checks, with 95% intervals from a bootstrap over site groups.", "",
             "| Model | recall@1 | recall@5 | MRR | detection AUROC |", "| --- | --- | --- | --- | --- |",
             *summary, "", "## Tuning (dev MRR per C)", "",
             "| Model | Check | " + " | ".join(map(str, C_GRID)) + " | chosen |",
             "| --- | --- |" + " --- |" * (len(C_GRID) + 1), *tuning, "", *sections]
    text = "\n".join(lines) + "\n"
    (out / "baselines.md").write_text(text, encoding="utf-8")
    (out / "logreg-features.json").write_text(json.dumps(features, indent=1), encoding="utf-8")
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dataset", type=Path, help="directory written by ml.dataset")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--boot", type=int, default=1000)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    print(run(args.dataset, args.out, args.boot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
