"""Shared scoring for every paragraph model (baselines, BM25, transformers).

    python -m ml.metrics data/imbroglio/v0.2-split1 runs/tfidf-lr.npz --split dev
    python -m ml.metrics data/imbroglio/v0.2-split1 runs/roberta.npz --compare runs/bm25.npz

A model is scored from a run file: an .npz with `version_id` and `idx` (which
paragraph), `scores` (one row per paragraph, one column per check, higher
means more relevant) and `checks` (the column names). Paragraphs the run
leaves out count as scoring lowest.

What Claude's labels can and can't measure. A paragraph Claude didn't quote
may still answer the question (it cites at most 3 quotes), so on these labels
a "false positive" may be right and precision can't be measured honestly.
Two things can be:

  * ranking, per document and check where Claude placed a verified quote:
    rank the document's paragraphs by score and see where the quoted ones
    land (recall@k, MRR)
  * detection, per document and check: does the document's best paragraph
    score separate documents that address the check (a verified quote) from
    documents that don't (`not_disclosed`)? Measured as ROC AUC. Longer
    documents address more checks and also have more chances at a high best
    score, so even random scores land above 0.5 here; compare against the
    random baseline, not against 0.5

Precision, recall and F1 at a threshold need people's labels; `prf` and
`average_precision` are here for the gold set.

Uncertainty: paragraphs and documents from one site group aren't
independent, so confidence intervals resample whole groups (a cluster
bootstrap), and two models are compared on the same resamples (a paired
bootstrap).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from ml.dataset import read_jsonl

KS = (1, 3, 5, 10)
N_BOOT = 1000
SEED = 0


# --- data --------------------------------------------------------------------

@dataclass
class Split:
    """One split of the paragraph dataset, in a fixed order."""
    keys: list[tuple[int, int]]          # (version_id, idx) per paragraph
    doc: np.ndarray                      # document number per paragraph
    docs: list[dict]                     # documents.jsonl rows, by document number
    pos: np.ndarray                      # paragraphs x checks, a verified quote lies in it
    silent: np.ndarray                   # documents x checks, the answer is not_disclosed
    in_train: np.ndarray                 # paragraph text also appears in training
    checks: list[str]


def load_split(dataset: Path, split: str, checks: list[str] | None = None) -> Split:
    docs = [d for d in read_jsonl(dataset / "documents.jsonl") if d["split"] == split]
    if checks is None:
        checks = sorted(docs[0]["answers"])
    number = {d["version_id"]: i for i, d in enumerate(docs)}
    col = {c: j for j, c in enumerate(checks)}
    keys, doc, pos, in_train = [], [], [], []
    for p in read_jsonl(dataset / "paragraphs.jsonl"):
        if p["split"] != split:
            continue
        keys.append((p["version_id"], p["idx"]))
        doc.append(number[p["version_id"]])
        row = np.zeros(len(checks), bool)
        for c in p["pos"]:
            row[col[c]] = True
        pos.append(row)
        in_train.append(p["in_train"])
    silent = np.array([[d["answers"].get(c, {}).get("status") == "not_disclosed" for c in checks] for d in docs])
    return Split(keys, np.array(doc), docs, np.array(pos), silent, np.array(in_train), checks)


def save_run(path: Path, keys: list[tuple[int, int]], scores: np.ndarray, checks: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, version_id=np.array([k[0] for k in keys]), idx=np.array([k[1] for k in keys]),
                        scores=scores.astype(np.float32), checks=np.array(checks))


def load_run(path: Path, split: Split) -> np.ndarray:
    """The run's scores aligned to the split's paragraphs and checks."""
    run = np.load(path)
    col = {str(c): j for j, c in enumerate(run["checks"])}
    missing = [c for c in split.checks if c not in col]
    if missing:
        raise ValueError(f"{path} has no scores for {missing}")
    row = {(int(v), int(i)): r for r, (v, i) in enumerate(zip(run["version_id"], run["idx"]))}
    out = np.full((len(split.keys), len(split.checks)), -np.inf)
    for r, key in enumerate(split.keys):
        if key in row:
            out[r] = run["scores"][row[key], [col[c] for c in split.checks]]
    return out


# --- per-unit measurements ---------------------------------------------------

def ranks_of_positives(scores: np.ndarray, positive: np.ndarray) -> np.ndarray:
    """1-based rank of each positive among all paragraphs. Ties are broken
    pessimistically (a positive tied with a negative ranks below it), so a
    model can't gain from constant scores."""
    order = np.lexsort((positive, -scores))      # by score, then negatives first
    rank = np.empty(len(scores), int)
    rank[order] = np.arange(1, len(scores) + 1)
    return np.sort(rank[positive])


def ranking_units(split: Split, scores: np.ndarray, keep: np.ndarray | None = None):
    """Per document and check with at least one positive paragraph: the ranks
    of the positives within that document. `keep` drops paragraphs (for the
    report without `in_train` paragraphs)."""
    keep = np.ones(len(split.keys), bool) if keep is None else keep
    by_doc = defaultdict(list)
    for r in np.flatnonzero(keep):
        by_doc[split.doc[r]].append(r)
    units = []        # (document, check column, ranks, number of paragraphs)
    for d, rows in by_doc.items():
        rows = np.array(rows)
        for j in range(len(split.checks)):
            positive = split.pos[rows, j]
            if positive.any():
                units.append((d, j, ranks_of_positives(scores[rows, j], positive), len(rows)))
    return units


def recall_at(ranks: np.ndarray, k: int) -> float:
    return float((ranks <= k).mean())


def detection(split: Split, scores: np.ndarray):
    """Per check: each document's best paragraph score, and whether the
    document addresses the check (1), is silent on it (0) or neither (-1:
    Claude answered but no verified quote could be placed)."""
    n_docs = len(split.docs)
    best = np.full((n_docs, len(split.checks)), -np.inf)
    np.maximum.at(best, split.doc, scores)
    addresses = np.zeros((n_docs, len(split.checks)), bool)
    np.logical_or.at(addresses, split.doc, split.pos)
    label = np.where(addresses, 1, np.where(split.silent, 0, -1))
    return best, label


def auroc(y: np.ndarray, s: np.ndarray, weights: np.ndarray | None = None) -> float:
    if not len(y) or y.min() == y.max():
        return float("nan")
    s = np.where(np.isneginf(s), np.finfo(np.float32).min, s)
    return float(roc_auc_score(y, s, sample_weight=weights))


# --- gold-set measurements ---------------------------------------------------

def prf(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float, float]:
    tp = float(np.sum(y_true & y_pred))
    p = tp / y_pred.sum() if y_pred.sum() else 0.0
    r = tp / y_true.sum() if y_true.sum() else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def average_precision(y_true: np.ndarray, scores: np.ndarray) -> float:
    return float(average_precision_score(y_true, scores)) if y_true.any() else float("nan")


# --- bootstrap ---------------------------------------------------------------

def group_resamples(groups: list[str], n_boot: int = N_BOOT, seed: int = SEED) -> list[np.ndarray]:
    """Each resample draws site groups with replacement and returns, per
    group drawn, how many times it was drawn (a weight per group)."""
    names = sorted(set(groups))
    rng = np.random.default_rng(seed)
    return [np.bincount(rng.integers(0, len(names), len(names)), minlength=len(names)) for _ in range(n_boot)]


def interval(values: list[float], level: float = 0.95) -> tuple[float, float]:
    v = np.array([x for x in values if not np.isnan(x)])
    if not len(v):
        return float("nan"), float("nan")
    a = (1 - level) / 2
    return float(np.quantile(v, a)), float(np.quantile(v, 1 - a))


class Scorer:
    """Ranking and detection figures for one run, with cluster-bootstrap
    intervals. The same resamples are used for every run on a split, which
    is what makes a paired comparison possible."""

    def __init__(self, split: Split, n_boot: int = N_BOOT, seed: int = SEED, drop_in_train: bool = False):
        self.split = split
        self.keep = ~split.in_train if drop_in_train else None
        names = sorted({d["group"] for d in split.docs})
        self.group_of_doc = np.array([names.index(d["group"]) for d in split.docs])
        self.resamples = group_resamples([d["group"] for d in split.docs], n_boot, seed)

    def prepare(self, scores: np.ndarray) -> dict:
        """Everything the figures need from one run, computed once: per check,
        the document of each ranking unit and its per-unit values, and each
        document's best score with its detection label."""
        units = ranking_units(self.split, scores, self.keep)
        per_check = {}
        for j in range(len(self.split.checks)):
            sel = [u for u in units if u[1] == j]
            values = {f"recall@{k}": np.array([recall_at(u[2], k) for u in sel]) for k in KS}
            values["mrr"] = np.array([1.0 / u[2][0] for u in sel])
            per_check[j] = (np.array([u[0] for u in sel], int), values)
        best, label = detection(self.split, scores)
        return {"units": per_check, "best": best, "label": label}

    def figures(self, prep: dict, weights: np.ndarray | None = None) -> dict[str, float]:
        """Point figures; `weights` (times each group was drawn) gives a bootstrap replicate."""
        checks = self.split.checks
        doc_w = np.ones(len(self.split.docs)) if weights is None else weights[self.group_of_doc].astype(float)
        out = {}
        for j, check in enumerate(checks):
            docs, values = prep["units"][j]
            w = doc_w[docs]
            for name, v in values.items():
                out[f"{check}/{name}"] = float(w @ v / w.sum()) if w.sum() else float("nan")
            label = prep["label"][:, j]
            known = (label >= 0) & (doc_w > 0)
            out[f"{check}/auroc"] = auroc(label[known], prep["best"][known, j], doc_w[known])
        for name in [*(f"recall@{k}" for k in KS), "mrr", "auroc"]:
            vals = [out[f"{c}/{name}"] for c in checks if not np.isnan(out[f"{c}/{name}"])]
            out[f"macro/{name}"] = float(np.mean(vals)) if vals else float("nan")
        return out

    def score(self, scores: np.ndarray) -> dict[str, tuple[float, float, float]]:
        """name -> (point, low, high)."""
        prep = self.prepare(scores)
        point = self.figures(prep)
        reps = [self.figures(prep, w) for w in self.resamples]
        return {k: (v, *interval([r[k] for r in reps])) for k, v in point.items()}

    def compare(self, a: np.ndarray, b: np.ndarray) -> dict[str, tuple[float, float, float, float]]:
        """name -> (a minus b, low, high, two-sided bootstrap p-value)."""
        prep_a, prep_b = self.prepare(a), self.prepare(b)
        pa, pb = self.figures(prep_a), self.figures(prep_b)
        out = {k: [] for k in pa}
        for w in self.resamples:
            ra, rb = self.figures(prep_a, w), self.figures(prep_b, w)
            for k in out:
                out[k].append(ra[k] - rb[k])
        result = {}
        for k, diffs in out.items():
            d = np.array(diffs)
            d = d[~np.isnan(d)]
            p = min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean())) if len(d) else float("nan")
            result[k] = (pa[k] - pb[k], *interval(list(d)), float(p))
        return result


# --- report ------------------------------------------------------------------

COLUMNS = ("recall@1", "recall@5", "mrr", "auroc")


def report(scored: dict, checks: list[str], title: str) -> str:
    def cell(v):
        return "n/a" if np.isnan(v[0]) else f"{v[0]:.3f} ({v[1]:.3f} to {v[2]:.3f})"
    lines = [f"## {title}", "", "| Check | " + " | ".join(COLUMNS) + " |", "| --- |" + " --- |" * len(COLUMNS)]
    for c in [*checks, "macro"]:
        lines.append(f"| {c} | " + " | ".join(cell(scored[f"{c}/{m}"]) for m in COLUMNS) + " |")
    return "\n".join(lines) + "\n"


def comparison(diff: dict, checks: list[str], title: str) -> str:
    def cell(v):
        return "n/a" if np.isnan(v[0]) else f"{v[0]:+.3f} ({v[1]:+.3f} to {v[2]:+.3f}), p={v[3]:.3f}"
    lines = [f"## {title}", "", "| Check | " + " | ".join(COLUMNS) + " |", "| --- |" + " --- |" * len(COLUMNS)]
    for c in [*checks, "macro"]:
        lines.append(f"| {c} | " + " | ".join(cell(diff[f"{c}/{m}"]) for m in COLUMNS) + " |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dataset", type=Path, help="directory written by ml.dataset")
    ap.add_argument("run", type=Path)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--compare", type=Path, help="a second run: report the first minus this one")
    ap.add_argument("--boot", type=int, default=N_BOOT)
    ap.add_argument("--drop-in-train", action="store_true", help="leave out paragraphs also seen in training")
    args = ap.parse_args()

    split = load_split(args.dataset, args.split)
    scorer = Scorer(split, args.boot, drop_in_train=args.drop_in_train)
    a = load_run(args.run, split)
    print(report(scorer.score(a), split.checks, f"{args.run.stem} on {args.split}"))
    if args.compare:
        b = load_run(args.compare, split)
        print(report(scorer.score(b), split.checks, f"{args.compare.stem} on {args.split}"))
        print(comparison(scorer.compare(a, b), split.checks, f"{args.run.stem} minus {args.compare.stem}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
