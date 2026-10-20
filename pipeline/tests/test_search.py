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
