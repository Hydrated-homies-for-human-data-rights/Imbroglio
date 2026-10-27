"""Analysis step + scorecard API, with a fake extractor (no LLM calls)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import analysis, db
from imbroglio.api import router
from imbroglio.llm_extract import Extraction, check_findings
from imbroglio.normalize import content_hash
from imbroglio.rubric import load

RUBRIC = load("v0")
POLICY = ("We do not sell your personal information. "
          "We use your content to train our machine learning models. "
          "We retain your data for as long as necessary. ") * 20

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _store(conn, domain, text=POLICY, doc_type="privacy"):
    sid = db.upsert_service(conn, domain)
    did = db.upsert_document(conn, sid, doc_type, f"https://{domain}/{doc_type}", "link-text")
    vid = db.insert_version(conn, did, content_hash(text), text, "static")
    conn.commit()
    return vid


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def fake_extract(text, rubric, model):
        calls.append(text)
        raw = [
            {"check_id": "sells_personal_data", "status": "no",
             "quotes": ["We do not sell your personal information."], "explanation": "Says no sale."},
            {"check_id": "trains_ai_on_user_data", "status": "yes",
             "quotes": ["We use your content to train our machine learning models."], "explanation": "Trains."},
            {"check_id": "retention_period", "status": "vague",
             "quotes": ["We keep data forever and ever."], "explanation": "fabricated quote"},
        ]
        return Extraction(model, "ok", findings=check_findings(rubric, raw, text), cost_usd=0.04,
                          input_tokens=1000, output_tokens=100)

    monkeypatch.setattr(analysis, "extract", fake_extract)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return calls


def test_analyze_then_reuse_identical_text(conn, fake_llm):
    v1 = _store(conn, "first.example")
    assert analysis.ensure_analyzed(conn, v1) == "analyzed"
    assert analysis.ensure_analyzed(conn, v1) == "done-already"
    v2 = _store(conn, "copycat.example")                  # same text, different site
    assert analysis.ensure_analyzed(conn, v2) == "reused"
    assert len(fake_llm) == 1                              # one paid call for two sites
    assert conn.execute("SELECT count(*) FROM extraction_runs").fetchone()[0] == 1


def test_daily_budget_stops_llm_calls(conn, fake_llm, monkeypatch):
    monkeypatch.setattr(analysis, "DAILY_BUDGET_USD", 0.05)
    assert analysis.ensure_analyzed(conn, _store(conn, "a.example", POLICY + "a")) == "analyzed"   # $0.04
    assert analysis.ensure_analyzed(conn, _store(conn, "b.example", POLICY + "b")) == "analyzed"   # under $0.05 before
    assert analysis.ensure_analyzed(conn, _store(conn, "c.example", POLICY + "c")).startswith("skipped:daily budget")
    assert len(fake_llm) == 2


def test_no_api_key_skips_cleanly(conn, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert analysis.ensure_analyzed(conn, _store(conn, "nokey.example")).startswith("skipped")


def test_scorecard_shows_only_verified_evidence(conn, fake_llm):
    analysis.ensure_analyzed(conn, _store(conn, "card.example"))
    card = client.get("/v1/sites/card.example").json()["scorecard"]
    cats = {c["key"]: c for c in card["categories"]}
    assert card["headline"] == "SEVERE" and card["headline_categories"] == ["AI and model training"]
    assert cats["ai_training"]["tier"] == "SEVERE"
    assert cats["selling_sharing"]["tier"] == "LIMITED"
    assert cats["retention"]["tier"] == "NOT_DISCLOSED"          # its only finding was unverified
    assert cats["retention"]["findings"] == []                   # and it is never shown
    ev = cats["ai_training"]["findings"][0]
    assert ev["quotes"] == ["We use your content to train our machine learning models."]
    assert ev["document"] == "privacy" and ev["reused"] is False
    assert card["documents"] == ["privacy"]
    # what the user can do: offered for the AI-training finding, not for "does not sell"
    assert ev["exposure"] == 3 and cats["selling_sharing"]["findings"][0]["exposure"] == 0
    assert ev["what_you_can_do"]["learn_anchor"] == "trains_ai_on_user_data"
    assert ev["what_you_can_do"]["steps"]
    assert cats["selling_sharing"]["findings"][0]["what_you_can_do"] is None


def test_headlines_for_list_view(conn, fake_llm):
    analysis.ensure_analyzed(conn, _store(conn, "rated.example"))
    _store(conn, "unrated.example", POLICY + " different")
    from imbroglio.scorer import SCORER_VERSION
    h = db.headlines(conn, analysis.RUBRIC_VERSION, SCORER_VERSION)
    assert h == {"rated.example": "SEVERE"}       # unrated sites are simply absent


def test_search_results_carry_concerns_and_analysis_date(conn, fake_llm):
    from imbroglio import search
    search.clear_cache()
    analysis.ensure_analyzed(conn, _store(conn, "rated.example"))
    _store(conn, "unrated.example", POLICY + " different")
    hits = {r["domain"]: r for r in client.get("/v1/search", params={"q": "example"}).json()["results"]}
    assert hits["rated.example"]["concerns"] == ["AI and model training"]
    assert hits["rated.example"]["analyzed_at"] is not None
    assert hits["unrated.example"]["concerns"] == [] and hits["unrated.example"]["analyzed_at"] is None
    assert hits["rated.example"]["last_changed"] is None
    search.clear_cache()


def _lookup(domain):
    import hashlib
    full = hashlib.sha256(domain.encode()).hexdigest()
    body = client.get(f"/v1/lookup/{full[:6]}").json()
    assert domain not in str(body)                 # still only hashes, never the domain
    return next(s for s in body["sites"] if s["hash"] == full)


def test_lookup_carries_the_same_ratings_as_the_scorecard(conn, fake_llm):
    analysis.ensure_analyzed(conn, _store(conn, "lookup.example"))
    entry = _lookup("lookup.example")
    card = client.get("/v1/sites/lookup.example").json()["scorecard"]
    scores = entry["scores"]
    assert scores["headline"] == card["headline"] == "SEVERE"
    assert scores["rubric_version"] == card["rubric_version"]
    assert [(c["key"], c["tier"]) for c in scores["categories"]] == \
           [(c["key"], c["tier"]) for c in card["categories"]]
    counts = {c["key"]: c["findings"] for c in scores["categories"]}
    assert counts == {c["key"]: len(c["findings"]) for c in card["categories"]}
    assert counts["ai_training"] == 1 and counts["retention"] == 0   # unverified isn't counted
    assert "quotes" not in str(scores)                                # ratings only, no evidence


def test_lookup_scores_combine_documents_and_wait_for_analysis(conn, fake_llm):
    _store(conn, "pending.example", POLICY + " pending")
    assert _lookup("pending.example")["scores"] is None               # stored, not analyzed yet
    analysis.ensure_analyzed(conn, _store(conn, "both.example"))
    analysis.ensure_analyzed(conn, _store(conn, "both.example", POLICY + " terms", doc_type="terms"))
    entry = _lookup("both.example")
    assert entry["documents"] == ["privacy", "terms"]
    counts = {c["key"]: c["findings"] for c in entry["scores"]["categories"]}
    assert counts["ai_training"] == 2                                 # one finding per document


GOV_POLICY = ("We may investigate your use of the services to determine whether a violation of "
              "these Terms has occurred. We may disclose information to law enforcement in response "
              "to a valid subpoena or court order. ") * 15


def _seed_v0(conn, vid, check_id, status, quote):
    conn.execute(
        """INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                 quotes_verified, verified, explanation, model)
           VALUES (%s, 'v0', %s, 'government', %s, %s, %s, true, 'e', 'claude-sonnet-5')""",
        (vid, check_id, status, [quote], [True]))
    conn.commit()


def test_rebase_rejects_off_topic_quote_without_llm(conn, monkeypatch):
    monkeypatch.setattr(analysis, "extract", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    vid = _store(conn, "wiki.example", GOV_POLICY)
    _seed_v0(conn, vid, "discloses_to_government", "broad",
             "We may investigate your use of the services to determine whether a violation of these Terms has occurred.")
    assert analysis.rebase(conn, vid, "v0", "v0.1") == "rebased"
    row = conn.execute("""SELECT verified FROM findings WHERE version_id = %s AND rubric_version = 'v0.1'
                          AND check_id = 'discloses_to_government'""", (vid,)).fetchone()
    assert row == (False,)     # real quote, but not about governments -> doesn't count
    tier = conn.execute("""SELECT tier FROM scores WHERE version_id = %s AND rubric_version = 'v0.1'
                           AND category = 'government'""", (vid,)).fetchone()[0]
    assert tier == "NOT_DISCLOSED"


def test_rebase_recalibrates_broad_government_disclosure(conn):
    vid = _store(conn, "gov.example", GOV_POLICY)
    _seed_v0(conn, vid, "discloses_to_government", "broad",
             "We may disclose information to law enforcement in response to a valid subpoena or court order.")
    analysis.rebase(conn, vid, "v0", "v0.1")
    tier = conn.execute("""SELECT tier FROM scores WHERE version_id = %s AND rubric_version = 'v0.1'
                           AND category = 'government'""", (vid,)).fetchone()[0]
    assert tier == "EXTENSIVE"   # was SEVERE under v0
