"""GET /v1/rubric: the published rubric and scoring rules (F5). No database."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import scorer
from imbroglio.analysis import RUBRIC_VERSION
from imbroglio.api import router
from imbroglio.rubric import load

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_rubric_lists_every_check_and_answer():
    body = client.get("/v1/rubric").json()
    rubric = load(RUBRIC_VERSION)
    assert body["rubric_version"] == rubric.version
    assert body["scorer_version"] == scorer.version_for(rubric)
    assert [c["key"] for c in body["categories"]] == list(rubric.categories)
    published = {k["check_id"]: k for c in body["categories"] for k in c["checks"]}
    assert set(published) == {c.id for c in rubric.checks}
    sells = {s["status"]: s["tier"] for s in published["sells_personal_data"]["statuses"]}
    assert sells == {"yes": "SEVERE", "no": "LIMITED"}   # exposure 3 and 0


def test_rubric_publishes_rules_and_every_tier():
    body = client.get("/v1/rubric").json()
    assert body["rules"] == scorer.rules_for(load(RUBRIC_VERSION))
    assert [t["tier"] for t in body["tiers"]] == ["SEVERE", "EXTENSIVE", "MODERATE", "LIMITED", "NOT_DISCLOSED"]


def _rate_from_published(body, answers):
    """The website's "Try the rules" scorer, written from the published JSON
    alone (web/src/lib/tryRules.ts does the same): the rating and score for
    one answer per question."""
    rank = {"NOT_DISCLOSED": -1, "LIMITED": 0, "INFO": 0.5, "MODERATE": 1, "EXTENSIVE": 2, "SEVERE": 3}
    sc = body["scoring"]
    statuses = {k["check_id"]: {s["status"]: s for s in k["statuses"]}
                for c in body["categories"] for k in c["checks"]}
    category = {k["check_id"]: c["key"] for c in body["categories"] for k in c["checks"]}
    chosen = {cid: statuses[cid][st] for cid, st in answers.items()}
    if not chosen:
        return "NOT_DISCLOSED", None
    worst = max((s["tier"] for s in chosen.values()), key=rank.get)
    rated = ("severe", "high", "medium")
    counted = [s for cid, s in chosen.items() if s["concern"] in rated
               and not (s["same_concern_as"] in chosen and chosen[s["same_concern_as"]]["concern"] in rated)]
    concerns = [s["concern"] for s in counted]
    if "severe" in concerns or concerns.count("high") >= 2:
        head = "SEVERE"
    elif "high" in concerns:
        head = "EXTENSIVE"
    elif concerns.count("medium") >= sc["moderate_needs"]:
        head = "MODERATE"
    else:
        head = "LIMITED"
    if worst in ("EXTENSIVE", "SEVERE") and rank[worst] > rank[head]:
        head = worst
    high_checks = {cid for cid, ss in statuses.items() if any(s["concern"] in ("severe", "high") for s in ss.values())}
    if head == "LIMITED" and len(high_checks & chosen.keys()) < sc["min_high_answered"]:
        head = "UNCLEAR"
    if head == "LIMITED" and not set(sc["limited_requires"]) <= {category[c] for c in chosen}:
        head = "MODERATE"
    if head not in sc["bands"]:
        return head, None
    lo, hi = sc["bands"][head]
    return head, min(max(sc["start"] - sum(s["points"] for s in counted), lo), hi)


@pytest.mark.parametrize("version", ["v0.2", "v0.3", "v1.0"])
def test_published_scoring_reproduces_the_scorer(version, monkeypatch):
    import random

    monkeypatch.setattr("imbroglio.analysis.RUBRIC_VERSION", version)
    body = client.get("/v1/rubric").json()
    rubric = load(version)
    assert body["rubric_version"] == version and body["scoring"] is not None
    rng = random.Random(7)
    for _ in range(3000):
        answers = {c.id: rng.choice(list(c.statuses)) for c in rubric.checks if rng.random() < 0.7}
        findings = [scorer.ScoredFinding(c, s, True) for c, s in answers.items()]
        _, head = scorer.rate(rubric, findings)
        result = scorer.score(rubric, findings, head)
        assert _rate_from_published(body, answers) == (head, result.value if result else None), answers


def test_scorer_s1_publishes_no_scoring(monkeypatch):
    monkeypatch.setattr("imbroglio.analysis.RUBRIC_VERSION", "v0.1")
    assert client.get("/v1/rubric").json()["scoring"] is None
