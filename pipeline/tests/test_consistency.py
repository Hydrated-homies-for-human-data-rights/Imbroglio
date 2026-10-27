"""Consistency study statistics, and the study itself with the model and
database replaced (no API calls, nothing written)."""

import pytest

from imbroglio import consistency
from imbroglio.llm_extract import Extraction, Finding
from imbroglio.rubric import NOT_DISCLOSED, load


def test_fleiss_kappa_hand_worked_example():
    # P-bar = (1 + 1 + 1/3) / 3 = 7/9; P-e = (5/9)^2 + (4/9)^2 = 41/81 -> 22/40
    assert consistency.fleiss_kappa([["a"] * 3, ["b"] * 3, ["a", "a", "b"]]) == pytest.approx(0.55)


def test_fleiss_kappa_perfect_and_undefined():
    assert consistency.fleiss_kappa([["a"] * 3, ["b"] * 3]) == pytest.approx(1.0)
    assert consistency.fleiss_kappa([["a"] * 3, ["a"] * 3]) is None  # no variation at all


def test_agreement_counts_pairs_where_every_run_matches():
    docs = {1: [{"x": "a", "y": "a"}, {"x": "a", "y": "b"}, {"x": "a", "y": "a"}],
            2: [{"x": "c", "y": "c"}] * 3}
    assert consistency.agreement(docs) == 0.75
    assert consistency.pairwise_agreement(["a", "b", "a"]) == pytest.approx(1 / 3)


def test_bootstrap_is_reproducible_and_brackets_the_estimate():
    docs = {i: [{"x": "a"}, {"x": "a" if i % 4 else "b"}] for i in range(40)}
    low, high = consistency.bootstrap(docs, consistency.agreement, seed=3)
    assert (low, high) == consistency.bootstrap(docs, consistency.agreement, seed=3)
    assert low <= consistency.agreement(docs) <= high


def test_study_reports_disagreements_and_drops_failed_documents(monkeypatch, tmp_path):
    rubric = load("v0.1")
    first, second = rubric.checks[0], rubric.checks[1]
    status_a, status_b = list(first.statuses)[:2]

    def findings(changed: bool):
        return [Finding(first.id, first.category, status_b if changed else status_a,
                        ["q"], [True], True, ""),
                Finding(second.id, second.category, NOT_DISCLOSED, [], [], False, "")]

    calls = {"stable.com": 0, "wobbly.com": 0, "broken.com": 0}

    def fake_extract(text, rubric_, model):
        calls[text] += 1
        if text == "broken.com" and calls[text] == 2:
            return Extraction(model, "error", error="overloaded")
        return Extraction(model, "ok", findings(text == "wobbly.com" and calls[text] == 3), cost_usd=0.01)

    class FakeConn:
        def close(self):
            pass

    monkeypatch.setattr(consistency.db, "connect", lambda: FakeConn())
    monkeypatch.setattr(consistency, "sample_documents",
                        lambda conn, n, seed: [(d, i, d) for i, d in enumerate(calls)])
    monkeypatch.setattr(consistency, "extract", fake_extract)

    report = consistency.run(3, 3, "sonnet", "v0.1", out=tmp_path / "c.md", parallel=1)
    assert "2 documents had every run succeed" in report
    assert "| 75.0%" in report  # 3 of the 4 (document, check) pairs agree
    assert f"wobbly.com / {first.id}: {status_a}, {status_a}, {status_b}" in report
    assert "broken.com run 2: error overloaded" in report
    assert "Cost $0.08" in report
    assert (tmp_path / "c.json").exists()
