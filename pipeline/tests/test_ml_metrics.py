"""Shared scoring (ml/metrics.py)."""

import json

import numpy as np
import pytest

from ml.metrics import (Scorer, load_run, load_split, prf, ranking_units, ranks_of_positives,
                        recall_at, save_run)

CHECKS = ["a", "b"]


def test_ties_rank_positives_below_negatives():
    positive = np.array([False, True, False, True])
    assert list(ranks_of_positives(np.zeros(4), positive)) == [3, 4]
    assert list(ranks_of_positives(np.array([0.1, 0.9, 0.5, 0.2]), positive)) == [1, 3]


def test_recall_at_k():
    ranks = np.array([1, 4, 9])
    assert recall_at(ranks, 1) == pytest.approx(1 / 3)
    assert recall_at(ranks, 5) == pytest.approx(2 / 3)


def test_prf():
    y = np.array([1, 1, 0, 0, 1], bool)
    pred = np.array([1, 0, 1, 0, 1], bool)
    assert prf(y, pred) == pytest.approx((2 / 3, 2 / 3, 2 / 3))
    assert prf(y, np.zeros(5, bool)) == (0.0, 0.0, 0.0)


@pytest.fixture
def dataset(tmp_path):
    """Six dev documents in three groups. In each, paragraph 0 answers check
    a; documents 0 to 2 are silent on b, 3 to 5 answer it in paragraph 1."""
    paras, docs = [], []
    for d in range(6):
        answers = {"a": {"status": "yes"}, "b": {"status": "not_disclosed" if d < 3 else "yes"}}
        docs.append({"version_id": d, "domain": f"s{d}.com", "split": "dev", "group": f"g{d // 2}", "answers": answers})
        for i in range(4):
            pos = {}
            if i == 0:
                pos["a"] = "yes"
            if i == 1 and d >= 3:
                pos["b"] = "yes"
            paras.append({"version_id": d, "idx": i, "split": "dev", "pos": pos, "in_train": i == 3, "text": "t"})
    paras.append({"version_id": 99, "idx": 0, "split": "train", "pos": {}, "in_train": False, "text": "t"})
    docs.append({"version_id": 99, "split": "train", "group": "x", "answers": {}})
    (tmp_path / "paragraphs.jsonl").write_text("\n".join(map(json.dumps, paras)), encoding="utf-8")
    (tmp_path / "documents.jsonl").write_text("\n".join(map(json.dumps, docs)), encoding="utf-8")
    return tmp_path


def oracle(split):
    return split.pos.astype(float) + 0.01 * np.arange(len(split.keys))[:, None] / len(split.keys)


def test_split_and_units(dataset):
    split = load_split(dataset, "dev", CHECKS)
    assert len(split.keys) == 24 and split.silent[:, 1].tolist() == [True] * 3 + [False] * 3
    units = ranking_units(split, oracle(split))
    assert len(units) == 6 + 3 and all(list(u[2]) == [1] for u in units)


def test_oracle_scores_perfectly_and_constant_scores_worst(dataset):
    split = load_split(dataset, "dev", CHECKS)
    scorer = Scorer(split, n_boot=50)
    good = scorer.score(oracle(split))
    assert good["macro/recall@1"][0] == 1.0 and good["macro/mrr"][0] == 1.0
    assert good["b/auroc"][0] == 1.0 and np.isnan(good["a/auroc"][0])     # no document is silent on a
    flat = scorer.score(np.zeros((24, 2)))
    assert flat["a/recall@1"][0] == 0.0 and flat["a/mrr"][0] == pytest.approx(0.25)
    lo, hi = good["macro/mrr"][1:]
    assert lo <= 1.0 <= hi


def test_paired_comparison(dataset):
    split = load_split(dataset, "dev", CHECKS)
    scorer = Scorer(split, n_boot=50)
    same = scorer.compare(oracle(split), oracle(split))
    assert same["macro/mrr"][0] == 0.0 and same["macro/mrr"][3] == 1.0
    better = scorer.compare(oracle(split), np.zeros((24, 2)))
    assert better["a/recall@1"][0] == 1.0 and better["a/recall@1"][1] > 0


def test_run_file_aligns_and_fills_missing(dataset, tmp_path):
    split = load_split(dataset, "dev", CHECKS)
    keys = list(reversed(split.keys[1:]))                     # shuffled order, one paragraph left out
    scores = np.array([[k[0] + k[1] / 10, -1.0] for k in keys])
    save_run(tmp_path / "run.npz", keys, scores[:, ::-1], ["b", "a"])  # columns in another order too
    out = load_run(tmp_path / "run.npz", split)
    assert np.isneginf(out[0]).all()
    assert out[1, 0] == pytest.approx(0.1) and out[1, 1] == -1.0
    with pytest.raises(ValueError):
        save_run(tmp_path / "bad.npz", keys, scores[:, :1], ["a"])
        load_run(tmp_path / "bad.npz", split)


def test_dropping_in_train_paragraphs_shrinks_the_ranking(dataset):
    split = load_split(dataset, "dev", CHECKS)
    flat = np.zeros((24, 2))
    full = Scorer(split, n_boot=10).score(flat)["a/mrr"][0]
    dropped = Scorer(split, n_boot=10, drop_in_train=True).score(flat)["a/mrr"][0]
    assert full == pytest.approx(1 / 4) and dropped == pytest.approx(1 / 3)


def test_error_analysis_lists_false_alarms_in_silent_documents_and_misses(dataset, tmp_path):
    from ml.errors import analyze
    split = load_split(dataset, "dev", CHECKS)
    scores = oracle(split)
    scores[split.keys.index((3, 2)), 1] = 5.0          # s3.com: paragraph 2 beats the quoted paragraph 1 for b
    save_run(tmp_path / "run.npz", split.keys, scores, CHECKS)
    text = analyze(dataset, tmp_path / "run.npz")
    b = text.split("## b")[1]
    alarms = b.split("### Misses")[0]
    assert "s2.com line 3" in alarms and "s3.com" not in alarms     # only documents 0 to 2 are silent on b
    assert "Misses (1 documents" in b and "s3.com: quoted line 1 ranked 2 of 4" in b
