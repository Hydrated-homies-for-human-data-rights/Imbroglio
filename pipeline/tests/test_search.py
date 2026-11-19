"""Site search: ranking rules (pure) and the endpoint (real Postgres)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import db, search
from imbroglio.api import router
from imbroglio.normalize import content_hash
from imbroglio.search import Entry

app = FastAPI()
app.include_router(router)
client = TestClient(app)

CATALOGUE = [
    Entry("facebook.com", "Facebook", ("privacy", "terms"), "SEVERE"),
    Entry("fb.com", None, ("privacy",), None),
    Entry("facebookcorewwwi.example", None, (), None),
    Entry("notion.so", "Notion", ("privacy", "terms"), "EXTENSIVE"),
    Entry("bbc.co.uk", "BBC", ("privacy",), None),
    Entry("books.example", "Face Books", ("privacy",), None),
]


def domains(q):
    return [e.domain for e in search.search(q, CATALOGUE)]


@pytest.mark.parametrize("raw, normalized", [
    ("https://www.Facebook.com/privacy?x=1", "facebook.com"),
    ("  Notion  ", "notion"),
    ("face book", "face book"),
])
def test_normalize(raw, normalized):
    assert search.normalize(raw) == normalized


def test_exact_domain_first():
    assert domains("facebook.com")[0] == "facebook.com"
    assert domains("https://www.facebook.com/settings")[0] == "facebook.com"


def test_brand_and_name_match():
    assert domains("notion")[0] == "notion.so"
    assert domains("BBC")[0] == "bbc.co.uk"


def test_prefix_ranks_analyzed_sites_first():
    hits = domains("face")
    assert hits[0] == "facebook.com"                 # analyzed, wins the tie
    assert set(hits) >= {"facebookcorewwwi.example", "books.example"}   # brand prefix, name word prefix


def test_typos():
    assert domains("facebok")[0] == "facebook.com"
    assert domains("notoin")[0] == "notion.so"
    assert domains("facebok.com")[0] == "facebook.com"


def test_too_short_or_no_match():
    assert domains("f") == []
    assert domains("zzzzzz") == []


# --- endpoint ---

@pytest.fixture(autouse=True)
def fresh_cache():
    search.clear_cache()
    yield
    search.clear_cache()


def _site(conn, domain):
    sid = db.upsert_service(conn, domain)
    did = db.upsert_document(conn, sid, "privacy", f"https://{domain}/privacy", "link-text")
    db.insert_version(conn, did, content_hash(domain), "policy text " + domain, "static")
    conn.commit()


def test_search_endpoint(conn):
    _site(conn, "notion.so")
    _site(conn, "notability.example")
    body = client.get("/v1/search", params={"q": "notion"}).json()
    assert body["results"][0]["domain"] == "notion.so"
    assert body["results"][0]["documents"] == ["privacy"]
    assert body["results"][0]["headline"] is None          # not analyzed yet
    assert body["can_request"] is None


def test_unknown_domain_can_be_requested(conn):
    _site(conn, "notion.so")
    body = client.get("/v1/search", params={"q": "https://www.brand-new.example/x"}).json()
    assert body["results"] == []
    assert body["can_request"] == "brand-new.example"
    assert client.get("/v1/search", params={"q": "notion.so"}).json()["can_request"] is None


def _rated(conn, domain, answers, rubric_version="v0.3"):
    from imbroglio import analysis
    from imbroglio.rubric import load
    rubric = load(rubric_version)
    text = f"{domain} policy. " * 100
    sid = db.upsert_service(conn, domain)
    did = db.upsert_document(conn, sid, "privacy", f"https://{domain}/privacy", "link-text")
    vid = db.insert_version(conn, did, content_hash(text), text, "static")
    for check_id, status in answers:
        conn.execute(
            """INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                     quotes_verified, verified, model)
               VALUES (%s, %s, %s, %s, %s, %s, %s, true, 'test')""",
            (vid, rubric_version, check_id, rubric.check(check_id).category, status, [f"{domain} policy."], [True]))
    analysis._write_scores(conn, vid, rubric_version)
    conn.commit()


CLEAN = [("sells_personal_data", "no"), ("retention_period", "specific"),
         ("deletion_on_request", "all_users"), ("access_and_export", "all_users")]


def test_search_and_recent_carry_the_score_and_biggest_reason(conn, monkeypatch):
    from imbroglio import analysis
    monkeypatch.setattr(analysis, "RUBRIC_VERSION", "v0.3")
    search.clear_cache()
    _rated(conn, "older.example", CLEAN)
    _rated(conn, "aitrain.example", CLEAN + [("trains_ai_on_user_data", "private_content"),
                                             ("shares_for_advertising", "yes")])
    _rated(conn, "thin.example", CLEAN[:1])

    hit = client.get("/v1/search", params={"q": "aitrain.example"}).json()["results"][0]
    assert (hit["headline"], hit["score"]) == ("EXTENSIVE", 46)
    assert hit["reason"] == "They can use your private content, like messages, files or AI chats, to train AI."

    sites = client.get("/v1/recent", params={"limit": 5}).json()["sites"]
    assert [s["domain"] for s in sites] == ["thin.example", "aitrain.example", "older.example"]
    assert [(s["score"], s["reason"]) for s in sites] == [
        (None, None), (46, hit["reason"]), (100, None)]
    assert client.get("/v1/recent", params={"limit": 1}).json()["sites"][0]["domain"] == "thin.example"
    search.clear_cache()


def test_sites_lists_every_rated_site_and_leaves_out_unrated_ones(conn, monkeypatch):
    from imbroglio import analysis
    monkeypatch.setattr(analysis, "RUBRIC_VERSION", "v0.3")
    search.clear_cache()
    _site(conn, "stored-only.example")
    _rated(conn, "older.example", CLEAN)
    _rated(conn, "aitrain.example", CLEAN + [("trains_ai_on_user_data", "private_content"),
                                             ("shares_for_advertising", "yes")])

    body = client.get("/v1/sites").json()
    assert body["count"] == 2
    assert [(s["domain"], s["headline"], s["score"]) for s in body["sites"]] == [
        ("aitrain.example", "EXTENSIVE", 46), ("older.example", "LIMITED", 100)]
    search.clear_cache()
