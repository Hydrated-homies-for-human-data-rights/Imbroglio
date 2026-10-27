"""GET /v1/rubric: the published rubric and scoring rules (F5). No database."""

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
    assert body["scorer_version"] == scorer.SCORER_VERSION
    assert [c["key"] for c in body["categories"]] == list(rubric.categories)
    published = {k["check_id"]: k for c in body["categories"] for k in c["checks"]}
    assert set(published) == {c.id for c in rubric.checks}
    sells = {s["status"]: s["tier"] for s in published["sells_personal_data"]["statuses"]}
    assert sells == {"yes": "SEVERE", "no": "LIMITED"}   # exposure 3 and 0


def test_rubric_publishes_rules_and_every_tier():
    body = client.get("/v1/rubric").json()
    assert body["rules"] == scorer.RULES
    assert [t["tier"] for t in body["tiers"]] == ["SEVERE", "EXTENSIVE", "MODERATE", "LIMITED", "NOT_DISCLOSED"]
