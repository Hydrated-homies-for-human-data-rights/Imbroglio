"""What-you-can-do advice: the file must stay in step with the rubric."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import advice
from imbroglio.analysis import RUBRIC_VERSION
from imbroglio.api import router
from imbroglio.rubric import load

RUBRIC = load(RUBRIC_VERSION)
app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_advice_file_matches_the_current_rubric():
    book = advice.load(RUBRIC_VERSION)   # raises on unknown checks, statuses or bad links
    assert set(book.checks) == {c.id for c in RUBRIC.checks}, "every check needs advice"
    assert {g.id for g in book.general} >= {"vpn", "passwords", "trackers", "rights"}


def test_advice_only_for_the_statuses_it_applies_to():
    book = advice.load(RUBRIC_VERSION)
    assert book.for_finding("sells_personal_data", "yes").title
    assert book.for_finding("sells_personal_data", "no") is None   # nothing to do about a good practice
    assert book.for_finding("no_such_check", "yes") is None


@pytest.mark.parametrize("raw, message", [
    ({"checks": {"made_up": {"title": "t", "why": "w", "applies_to": ["yes"], "steps": [{"text": "s"}]}}},
     "not a check"),
    ({"checks": {"sells_personal_data": {"title": "t", "why": "w", "applies_to": ["maybe"],
                                         "steps": [{"text": "s"}]}}}, "not a status"),
    ({"checks": {"sells_personal_data": {"title": "t", "why": "w", "applies_to": ["yes"],
                                         "steps": [{"text": "s", "link": "http://x.com"}]}}}, "https"),
    ({"checks": {"sells_personal_data": {"title": "t", "why": "w", "applies_to": ["yes"], "steps": []}}},
     "at least one step"),
])
def test_bad_advice_fails_loudly(raw, message):
    with pytest.raises(advice.AdviceError, match=message):
        advice.parse(raw, RUBRIC)


def test_learn_endpoint():
    r = client.get("/v1/learn")
    assert r.status_code == 200
    body = r.json()
    topic = next(t for t in body["topics"] if t["check_id"] == "trains_ai_on_user_data")
    assert topic["category"] == "AI and model training"
    assert topic["applies_to"] == ["yes"] and topic["steps"]
    assert any(g["id"] == "vpn" for g in body["guides"])
