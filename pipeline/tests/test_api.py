"""GET /v1/sites/{domain}: one test per state the endpoint can report."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import db, jobs
from imbroglio.api import router
from imbroglio.normalize import content_hash

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _store(conn, domain, doc_type="privacy", text="We collect personal data. " * 80):
    service_id = db.upsert_service(conn, domain)
    doc_id = db.upsert_document(conn, service_id, doc_type, f"https://{domain}/{doc_type}", "link-text")
    db.insert_version(conn, doc_id, content_hash(text), text, "static")
    conn.commit()


def test_unknown_site_is_200_not_404(conn):
    r = client.get("/v1/sites/never-seen.example")
    assert r.status_code == 200
    assert r.json()["state"] == "unknown"
    assert r.json()["missing"] == ["privacy", "terms"]


def test_ready_site_with_documents(conn):
    _store(conn, "notion.so")
    body = client.get("/v1/sites/www.Notion.so").json()  # case and www. are normalized
    assert body["domain"] == "notion.so" and body["state"] == "ready"
    assert [d["type"] for d in body["documents"]] == ["privacy"]
    assert body["missing"] == ["terms"]
    assert body["documents"][0]["versions_stored"] == 1
    assert body["scores"] is None


def test_queued_then_analyzing(conn):
    rid, *_ = jobs.enqueue(conn, "new.example")
    body = client.get("/v1/sites/new.example").json()
    assert body["state"] == "queued" and body["pending_request"]["id"] == rid
    jobs.claim(conn, "w")
    jobs.progress(conn, rid, "fetching homepage")
    body = client.get("/v1/sites/new.example").json()
    assert body["state"] == "analyzing"
    assert body["pending_request"]["stage"] == "fetching homepage"


def test_no_policy_found_after_failed_attempt(conn):
    db.insert_attempt(conn, None, "bare.example", "privacy", False, "failed",
                      None, None, None, 0, "only 404s", 3.0)
    conn.commit()
    body = client.get("/v1/sites/bare.example").json()
    assert body["state"] == "no_policy_found" and body["checked_at"]


def test_etag_gives_304_until_something_changes(conn):
    _store(conn, "etag.example")
    first = client.get("/v1/sites/etag.example")
    etag = first.headers["etag"]
    assert "max-age" in first.headers["cache-control"]
    again = client.get("/v1/sites/etag.example", headers={"If-None-Match": etag})
    assert again.status_code == 304
    _store(conn, "etag.example", text="A different policy text entirely. " * 80)  # new version
    changed = client.get("/v1/sites/etag.example", headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.headers["etag"] != etag


def test_rejects_non_domain():
    assert client.get("/v1/sites/127.0.0.1").status_code == 400


# --- POST /v1/requests, GET /v1/requests/{id} ---

import hashlib

import pytest

from imbroglio import api


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    monkeypatch.setattr(api, "_limiter", api._RateLimiter(api.REQUESTS_PER_HOUR))


def test_request_lifecycle(conn):
    r = client.post("/v1/requests", json={"domain": "Brand-New.example"})
    assert r.status_code == 202
    body = r.json()
    assert body["domain"] == "brand-new.example" and body["status"] == "queued" and body["created"]
    job = client.get(body["status_url"]).json()
    assert job["status"] == "queued" and job["progress"] == []
    # a second request joins the same job instead of queueing a duplicate
    again = client.post("/v1/requests", json={"domain": "brand-new.example"}).json()
    assert again["request_id"] == body["request_id"] and not again["created"]


def test_cached_site_is_not_requeued_unless_refresh(conn):
    _store(conn, "cached.example")
    r = client.post("/v1/requests", json={"domain": "cached.example"})
    assert r.status_code == 200 and r.json()["status"] == "already_available"
    r = client.post("/v1/requests", json={"domain": "cached.example", "refresh": True})
    assert r.status_code == 202 and r.json()["status"] == "queued"


def test_per_client_rate_limit(conn, monkeypatch):
    monkeypatch.setattr(api, "_limiter", api._RateLimiter(2))
    for i in range(2):
        assert client.post("/v1/requests", json={"domain": f"site{i}.example"}).status_code == 202
    r = client.post("/v1/requests", json={"domain": "site9.example"})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_daily_cap(conn, monkeypatch):
    monkeypatch.setattr(api, "DAILY_REQUEST_CAP", 1)
    assert client.post("/v1/requests", json={"domain": "one.example"}).status_code == 202
    assert client.post("/v1/requests", json={"domain": "two.example"}).status_code == 429


def test_unknown_request_404(conn):
    assert client.get("/v1/requests/999999").status_code == 404


# --- GET /v1/lookup/{prefix} ---

def test_lookup_by_hash_prefix_never_returns_domain(conn):
    _store(conn, "private.example")
    _store(conn, "private.example", doc_type="terms", text="By using you agree to these terms. " * 60)
    full = hashlib.sha256(b"private.example").hexdigest()
    body = client.get(f"/v1/lookup/{full[:5]}").json()
    match = [s for s in body["sites"] if s["hash"] == full]
    assert match and match[0]["documents"] == ["privacy", "terms"]
    assert "private.example" not in str(body)  # the server only deals in hashes


def test_lookup_validates_prefix(conn):
    for bad in ("abc", "ZZZZ", "abcd1234ef", "not-hex!"):
        assert client.get(f"/v1/lookup/{bad}").status_code == 400
    assert client.get("/v1/lookup/0000").json()["sites"] == []


# --- M3: negative caching and identical-text detection ---

def _failed_attempt(conn, domain, days_ago=0):
    db.insert_attempt(conn, None, domain, "privacy", False, "failed", None, None, None,
                      0, "only 404s", 3.0)
    conn.execute("UPDATE crawl_attempts SET attempted_at = now() - make_interval(days => %s) "
                 "WHERE domain = %s", (days_ago, domain))
    conn.commit()


def test_recent_no_policy_answered_from_cache(conn):
    _failed_attempt(conn, "nopolicy.example", days_ago=1)
    r = client.post("/v1/requests", json={"domain": "nopolicy.example"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_policy_found" and body["recheck_after"] and not body["created"]
    site = client.get("/v1/sites/nopolicy.example").json()
    assert site["state"] == "no_policy_found" and site["recheck_after"]
    # refresh still forces a crawl
    assert client.post("/v1/requests", json={"domain": "nopolicy.example", "refresh": True}).status_code == 202


def test_old_no_policy_result_is_rechecked(conn):
    _failed_attempt(conn, "stale.example", days_ago=30)
    assert client.post("/v1/requests", json={"domain": "stale.example"}).status_code == 202


def test_shared_with_counts_identical_documents(conn):
    text = "Generated privacy policy. We collect personal data and use cookies. " * 40
    for d in ("a-shop.example", "b-shop.example", "c-shop.example"):
        _store(conn, d, text=text)
    _store(conn, "unique.example", text="Our own custom policy about personal data. " * 40)
    docs = client.get("/v1/sites/a-shop.example").json()["documents"]
    assert docs[0]["shared_with"] == 2
    assert client.get("/v1/sites/unique.example").json()["documents"][0]["shared_with"] == 0
