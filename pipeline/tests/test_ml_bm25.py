"""BM25 ranking (ml/bm25.py)."""

import math

import numpy as np
import pytest

from ml.bm25 import BM25

TRAIN = ["we sell your data", "we never sell data to advertisers",
         "advertising partners use cookies", "contact us by email", "contact us"]


def test_idf_counts_training_paragraphs():
    bm = BM25(TRAIN)
    n, df = 5, 2                                             # "sell" is in two paragraphs
    assert bm.idf[bm.vocab["sell"]] == pytest.approx(math.log1p((n - df + 0.5) / (df + 0.5)))
    assert bm.idf[bm.vocab["cookies"]] > bm.idf[bm.vocab["sell"]]


def test_query_drops_stop_words_and_expands_stems():
    bm = BM25(TRAIN)
    q = bm.query("Do they sell data?", ("advertis", "third part"))
    words = {bm.words[i] for i in np.flatnonzero(q)}
    # "third part" loses its phrase: "third" is not in the vocabulary, and the stem "part" matches "partners"
    assert words == {"sell", "data", "advertisers", "advertising", "partners"}


def test_score_matches_the_formula_and_saturates():
    bm = BM25(TRAIN)
    k1, b = 1.2, 0.75
    q = bm.query("sell")
    texts = ["we sell data", "sell sell sell sell data", "nothing here"]
    s = bm.term_weights(texts, k1, b) @ q
    idf, avg = bm.idf[bm.vocab["sell"]], bm.avg_len
    expected = idf * 1 * (k1 + 1) / (1 + k1 * (1 - b + b * 3 / avg))
    assert s[0] == pytest.approx(expected) and s[2] == 0
    assert s[1] > s[0] and s[1] < 4 * s[0]                  # repeats help, with diminishing returns
