"""BM25 ranking of each document's paragraphs for each check.

    python -m ml.bm25 data/imbroglio/v0.2-split1 --out data/imbroglio/runs

The search-engine baseline the trained models have to beat. Every paragraph
is scored against a query built from the check; nothing is learned except
two constants, chosen on dev.

BM25 for a query q and paragraph p:

    sum over terms t in q:  idf(t) * tf(t, p) * (k1 + 1) / (tf(t, p) + k1 * (1 - b + b * |p| / avg|p|))

with idf(t) = log(1 + (N - df(t) + 0.5) / (df(t) + 0.5)), counted over the
training paragraphs. k1 controls how fast repeated words stop adding score;
b how much long paragraphs are penalized.

Three queries per check, to see where the signal is:
  * question: the rubric question's words, without stop words
  * evidence: the check's evidence words. Several are word stems
    ("advertis", "third part"), so each is expanded to every vocabulary word
    starting with it. A phrase becomes separate words, so "third part" also
    matches "partners" on its own: bag-of-words ranking can't keep phrases
  * both: question and evidence together

Like the evidence-word floor, the evidence and both queries are flattered on
these labels, since every verified quote contains an evidence word.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

from imbroglio.rubric import load
from ml.dataset import read_jsonl
from ml.metrics import Scorer, load_split, report, save_run

K1_GRID = (0.6, 0.9, 1.2, 1.5, 2.0)
B_GRID = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
TOKEN = r"[a-z]+"


class BM25:
    def __init__(self, train_texts: list[str]):
        self.vec = CountVectorizer(token_pattern=TOKEN, lowercase=True, strip_accents="unicode")
        x = self.vec.fit_transform(train_texts)
        n = x.shape[0]
        df = np.bincount(x.indices, minlength=x.shape[1])
        self.idf = np.log1p((n - df + 0.5) / (df + 0.5))
        self.avg_len = x.sum() / n
        self.vocab = self.vec.vocabulary_
        self.words = np.array(self.vec.get_feature_names_out())

    def query(self, question: str = "", evidence: tuple[str, ...] = ()) -> np.ndarray:
        """Query term counts over the vocabulary."""
        q = np.zeros(len(self.vocab))
        for w in re.findall(TOKEN, question.lower()):
            if w not in ENGLISH_STOP_WORDS and w in self.vocab:
                q[self.vocab[w]] += 1
        for e in evidence:
            *whole, stem = re.findall(TOKEN, e.lower())
            for w in whole:
                if w in self.vocab:
                    q[self.vocab[w]] += 1
            # the last word of an evidence phrase may be a stem: expand it
            lo = np.searchsorted(self.words, stem)
            hi = np.searchsorted(self.words, stem + "{")      # "{" sorts right after "z"
            q[lo:hi] += 1
        return q

    def term_weights(self, texts: list[str], k1: float, b: float) -> sparse.csr_matrix:
        """The BM25 weight of every term in every paragraph (idf times the
        saturated term frequency); scoring a query is then one product."""
        x = self.vec.transform(texts).astype(float).tocsr()
        length = np.asarray(x.sum(axis=1)).ravel()
        norm = k1 * (1 - b + b * length / self.avg_len)
        rows = np.repeat(np.arange(x.shape[0]), np.diff(x.indptr))
        tf = x.data
        x.data = self.idf[x.indices] * tf * (k1 + 1) / (tf + norm[rows])
        return x


def run(dataset: Path, out: Path, n_boot: int = 1000) -> str:
    rubric = load("v0.2")
    texts = {}
    train = []
    for p in read_jsonl(dataset / "paragraphs.jsonl"):
        if p["split"] == "train":
            train.append(p["text"])
        else:
            texts[(p["version_id"], p["idx"])] = p["text"]
    dev, test = load_split(dataset, "dev"), load_split(dataset, "test")
    checks = dev.checks
    t = time.time()
    bm = BM25(train)
    queries = {
        "question": [bm.query(rubric.check(c).question) for c in checks],
        "evidence": [bm.query("", rubric.check(c).evidence) for c in checks],
        "both": [bm.query(rubric.check(c).question, rubric.check(c).evidence) for c in checks],
    }
    dev_texts = [texts[k] for k in dev.keys]
    test_texts = [texts[k] for k in test.keys]
    quick, scorer = Scorer(dev, 1), Scorer(dev, n_boot)
    lines = ["# BM25 on dev", "", f"Vocabulary {len(bm.vocab)} words from {len(train)} training paragraphs.", "",
             "Query terms per check (evidence stems expanded):", ""]
    for j, c in enumerate(checks):
        lines.append(f"- {c}: {np.count_nonzero(queries['question'][j])} question words, "
                     f"{np.count_nonzero(queries['evidence'][j])} evidence words")
    lines += ["", "## Tuning (dev macro MRR)", "", "| Query | k1 | b | MRR |", "| --- | --- | --- | --- |"]
    sections, summary = [], []
    for name, qs in queries.items():
        q = np.stack(qs, axis=1)                          # vocabulary x checks
        best = None
        for k1 in K1_GRID:
            for b in B_GRID:
                s = bm.term_weights(dev_texts, k1, b) @ q
                mrr = quick.figures(quick.prepare(s))["macro/mrr"]
                if best is None or mrr > best[0]:
                    best = (mrr, k1, b, s)
        mrr, k1, b, s_dev = best
        lines.append(f"| {name} | {k1} | {b} | {mrr:.3f} |")
        s_test = bm.term_weights(test_texts, k1, b) @ q
        save_run(out / f"bm25-{name}-dev.npz", dev.keys, s_dev, checks)
        save_run(out / f"bm25-{name}-test.npz", test.keys, s_test, checks)
        scored = scorer.score(s_dev)
        sections.append(report(scored, checks, f"bm25-{name} on dev (k1={k1}, b={b})"))
        summary.append(f"| bm25-{name} | " + " | ".join(
            f"{scored[f'macro/{m}'][0]:.3f} ({scored[f'macro/{m}'][1]:.3f} to {scored[f'macro/{m}'][2]:.3f})"
            for m in ("recall@1", "recall@5", "mrr", "auroc")) + " |")
    lines += ["", f"Built and tuned in {time.time() - t:.0f} s.", "", "## Summary (macro, 95% intervals over site groups)", "",
              "| Query | recall@1 | recall@5 | MRR | detection AUROC |", "| --- | --- | --- | --- | --- |",
              *summary, "", *sections]
    text = "\n".join(lines) + "\n"
    (out / "bm25.md").write_text(text, encoding="utf-8")
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
