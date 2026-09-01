"""Spike B step 2: TF-IDF + logistic regression baseline on OPP-115.

Multilabel one-vs-rest classification of policy segments into the 10 OPP-115
practice categories. This is deliberately the dumbest credible model — it sets
the floor any transformer fine-tune must beat, and its numbers go in the
week-4 report next to published Polisis figures.

Trains on the train split, tunes nothing (spike!), reports per-category
precision/recall/F1 on dev AND test, plus macro/micro averages.

Outputs: results/metrics.md, results/metrics.json

Usage: python baseline.py   (run prepare.py first)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support
from sklearn.multiclass import OneVsRestClassifier

HERE = Path(__file__).parent
PROCESSED = HERE.parent / "data" / "opp115" / "processed"
RESULTS = HERE / "results"

csv.field_size_limit(10_000_000)


def load(split: str) -> tuple[list[str], np.ndarray, list[str]]:
    texts, labels = [], []
    with open(PROCESSED / "segments.csv", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        categories = header[4:]
        for row in reader:
            if row[1] != split:
                continue
            texts.append(row[3])
            labels.append([int(v) for v in row[4:]])
    return texts, np.array(labels), categories


def evaluate(name: str, y_true: np.ndarray, y_pred: np.ndarray, categories: list[str]) -> dict:
    p, r, f1, support = precision_recall_fscore_support(
        y_true, y_pred, average=None, zero_division=0
    )
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    micro_p, micro_r, micro_f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="micro", zero_division=0
    )
    return {
        "split": name,
        "per_category": {
            cat: {"precision": round(float(pi), 3), "recall": round(float(ri), 3),
                  "f1": round(float(fi), 3), "support": int(si)}
            for cat, pi, ri, fi, si in zip(categories, p, r, f1, support)
        },
        "macro": {"precision": round(float(macro_p), 3), "recall": round(float(macro_r), 3),
                  "f1": round(float(macro_f1), 3)},
        "micro": {"precision": round(float(micro_p), 3), "recall": round(float(micro_r), 3),
                  "f1": round(float(micro_f1), 3)},
    }


def to_markdown(results: list[dict], n_train: int) -> str:
    lines = [
        "# Spike B — TF-IDF + Logistic Regression Baseline (OPP-115)",
        "",
        f"Trained on {n_train} segments (train split, majority-vote labels,",
        "split by policy, seed 42). One-vs-rest logistic regression over",
        "TF-IDF 1-2 grams. No tuning — this is the floor, not the model.",
        "",
        "Week-10 target (proposal objective 2): macro F1 >= 0.70 in the live",
        "pipeline. Polisis (USENIX 2018) reported ~0.78 micro-average F1 on",
        "segment classification with CNNs — numbers here frame that gap.",
        "",
    ]
    for res in results:
        lines += [
            f"## {res['split']} split",
            "",
            f"**Macro F1: {res['macro']['f1']}** · micro F1: {res['micro']['f1']}",
            "",
            "| Category | P | R | F1 | support |",
            "| --- | --- | --- | --- | --- |",
        ]
        for cat, m in res["per_category"].items():
            lines.append(
                f"| {cat} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not (PROCESSED / "segments.csv").exists():
        sys.exit("segments.csv missing — run prepare.py first")

    X_train, y_train, categories = load("train")
    X_dev, y_dev, _ = load("dev")
    X_test, y_test, _ = load("test")
    print(f"train {len(X_train)} / dev {len(X_dev)} / test {len(X_test)} segments")

    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True,
                          strip_accents="unicode")
    Xtr = vec.fit_transform(X_train)
    print(f"vocab: {len(vec.vocabulary_):,}")

    clf = OneVsRestClassifier(
        LogisticRegression(max_iter=2000, class_weight="balanced"),
        n_jobs=-1,
    )
    clf.fit(Xtr, y_train)

    results = [
        evaluate("dev", y_dev, clf.predict(vec.transform(X_dev)), categories),
        evaluate("test", y_test, clf.predict(vec.transform(X_test)), categories),
    ]

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "metrics.json").write_text(json.dumps(results, indent=2))
    (RESULTS / "metrics.md").write_text(to_markdown(results, len(X_train)), encoding="utf-8")

    for res in results:
        print(f"{res['split']}: macro F1 {res['macro']['f1']}, micro F1 {res['micro']['f1']}")
    print(f"\nreport -> {RESULTS / 'metrics.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
