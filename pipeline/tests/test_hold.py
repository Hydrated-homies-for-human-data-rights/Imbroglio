"""Holding a stored document that is the wrong page (cli hold / unhold / held).

A held document keeps its text but is treated as if we didn't have it:
gone from the site report, lookups, search and lists, never rated, never
rechecked, and not stored again when discovery finds the same page."""

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import analysis, cli, db, recheck, search
from imbroglio.analyze import DocOutcome, same_url, store_manual, store_text
from imbroglio.api import router
from imbroglio.normalize import content_hash

app = FastAPI()
app.include_router(router)
client = TestClient(app)

PRIVACY = "We collect personal data and share it with our service providers. " * 40
TERMS = "By using the service you agree to these terms and to arbitration. " * 40
PROMO = "Get $10 in bitcoin when you sign up this week. Terms apply to the promotion. " * 40


def _store(conn, domain, doc_type="privacy", text=PRIVACY, url=None):
    sid = db.upsert_service(conn, domain)
    did = db.upsert_document(conn, sid, doc_type, url or f"https://{domain}/{doc_type}", "link-text")
    vid = db.insert_version(conn, did, content_hash(text), text, "static")
    conn.commit()
    return vid


def _rate(conn, version_id):
    conn.execute("""INSERT INTO findings (version_id, rubric_version, check_id, category, status,
                                          quotes, quotes_verified, verified, explanation, model)
                    VALUES (%s, %s, 'sells_personal_data', 'selling_sharing', 'no', '{}', '{}',
                            false, '', 'test')""", (version_id, analysis.RUBRIC_VERSION))
    conn.commit()


def _lookup(domain):
    full = hashlib.sha256(domain.encode()).hexdigest()
    body = client.get(f"/v1/lookup/{full[:6]}").json()
    return next((s for s in body["sites"] if s["hash"] == full), None)


@pytest.fixture(autouse=True)
def fresh_cache():
    search.clear_cache()
    yield
    search.clear_cache()


def test_same_url_ignores_scheme_www_trailing_slash_and_fragment():
    assert same_url("https://www.coinbase.com/legal/promo/", "http://coinbase.com/legal/promo#top")
    assert same_url("https://x.com/terms?utm_source=footer", "https://x.com/terms")
    assert not same_url("https://x.com/help?article=1", "https://x.com/help?article=2")
    assert not same_url("https://x.com/legal/promo", "https://x.com/legal/user-agreement")


def test_a_held_outcome_is_not_found():
    assert not DocOutcome("terms", "held").found and not DocOutcome("terms", "failed").found
    assert DocOutcome("terms", "unchanged").found


def test_held_document_leaves_the_report_and_the_scorecard(conn):
    _rate(conn, _store(conn, "coinbase.com"))
    _rate(conn, _store(conn, "coinbase.com", "terms", PROMO))
    before = client.get("/v1/sites/coinbase.com").json()
    assert before["scorecard"]["documents"] == ["privacy", "terms"]

    assert db.hold_document(conn, "coinbase.com", "terms", "promo help article") == "https://coinbase.com/terms"
    body = client.get("/v1/sites/coinbase.com").json()
    assert body["state"] == "ready"
    assert [d["type"] for d in body["documents"]] == ["privacy"]
    assert body["missing"] == ["terms"] and body["not_rated"] == []   # reads as never found
    assert body["scorecard"]["documents"] == ["privacy"]
    assert _lookup("coinbase.com")["documents"] == ["privacy"]
    # the text is still there
    assert db.latest_text(conn, "coinbase.com", "terms") == PROMO


def test_a_site_whose_only_document_is_held_reads_as_nothing_stored(conn):
    _rate(conn, _store(conn, "usu.edu", "terms", PROMO))
    db.insert_attempt(conn, None, "usu.edu", "terms", True, "stored-new", "https://usu.edu/terms",
                      "link-text", "static", len(PROMO), None, 3.0)
    conn.commit()
    assert client.get("/v1/sites/usu.edu").json()["state"] == "ready"
    assert [s["domain"] for s in client.get("/v1/sites").json()["sites"]] == ["usu.edu"]

    db.hold_document(conn, "usu.edu", "terms", "copyright page")
    search.clear_cache()
    body = client.get("/v1/sites/usu.edu").json()
    assert body["state"] == "no_policy_found" and body["documents"] == []
    assert body["missing"] == ["privacy", "terms"] and body["scorecard"] is None
    assert _lookup("usu.edu") is None
    assert client.get("/v1/search", params={"q": "usu.edu"}).json()["results"] == []
    assert client.get("/v1/sites").json()["sites"] == []
    assert client.get("/v1/recent").json()["sites"] == []
    assert db.headlines(conn, analysis.RUBRIC_VERSION) == {}


def test_held_documents_are_never_pending_and_never_rated(conn, monkeypatch):
    def no_llm(*a, **k):
        raise AssertionError("a held document must not reach the model")
    monkeypatch.setattr(analysis, "extract", no_llm)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    vid = _store(conn, "giftcards.example", "terms", PROMO)
    assert analysis.pending_versions(conn) == [vid]
    db.hold_document(conn, "giftcards.example", "terms", "gift card terms")
    assert analysis.pending_versions(conn) == []
    assert analysis.pending_versions(conn, domain="giftcards.example") == []
    assert analysis.ensure_analyzed(conn, vid) == "held"
    assert analysis.ensure_analyzed(conn, vid, force=True) == "held"
    assert conn.execute("SELECT count(*) FROM extraction_runs").fetchone()[0] == 0


def test_recheck_skips_held_documents(conn):
    _store(conn, "blog.example", "privacy", PRIVACY)
    _store(conn, "fine.example", "privacy", PRIVACY + " fine")
    assert {r[1] for r in recheck.due(conn, 0)} == {"blog.example", "fine.example"}
    db.hold_document(conn, "blog.example", "privacy", "a blog post")
    assert [r[1] for r in recheck.due(conn, 0)] == ["fine.example"]


def test_rediscovering_the_held_page_stores_nothing(conn):
    _store(conn, "coinbase.com", "terms", PROMO, url="https://www.coinbase.com/legal/promo")
    db.hold_document(conn, "coinbase.com", "terms", "promo help article")
    sid = db.upsert_service(conn, "coinbase.com")
    o = store_text(conn, sid, "terms", "https://coinbase.com/legal/promo/#x", "link-text", "static",
                   PROMO + " a newer promo")
    assert o.status == "held" and o.version_id is None and not o.found
    assert o.notes == "held: promo help article"
    assert conn.execute("SELECT count(*) FROM document_versions").fetchone()[0] == 1
    assert db.held_documents(conn) == [("coinbase.com", "terms", "promo help article",
                                        "https://www.coinbase.com/legal/promo")]


def test_discovering_a_different_page_stores_it_and_lifts_the_hold(conn):
    _store(conn, "coinbase.com", "terms", PROMO, url="https://www.coinbase.com/legal/promo")
    db.hold_document(conn, "coinbase.com", "terms", "promo help article")
    sid = db.upsert_service(conn, "coinbase.com")
    o = store_text(conn, sid, "terms", "https://www.coinbase.com/legal/user_agreement", "link-text",
                   "static", TERMS)
    assert o.status == "changed" and o.version_id and "hold lifted" in o.notes
    assert db.held_documents(conn) == []
    assert [d["url"] for d in client.get("/v1/sites/coinbase.com").json()["documents"]] == \
        ["https://www.coinbase.com/legal/user_agreement"]


def test_storing_by_hand_lifts_the_hold_even_at_the_same_address(conn):
    _store(conn, "walled.example", "privacy", PROMO, url="https://walled.example/privacy")
    db.hold_document(conn, "walled.example", "privacy", "login wall")
    o = store_manual("walled.example", "privacy", "https://walled.example/privacy", PRIVACY)
    assert o.status == "changed" and db.held_documents(conn) == []


def _cli(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["imbroglio", *argv])
    return cli.main()


def test_cli_hold_held_unhold_round_trip(conn, monkeypatch, capsys):
    _store(conn, "coinbase.com", "terms", PROMO, url="https://www.coinbase.com/legal/promo")
    assert _cli(monkeypatch, "hold", "nothing.example", "terms", "--reason", "x") == 1
    assert "nothing held" in capsys.readouterr().out
    assert _cli(monkeypatch, "hold", "www.Coinbase.com", "terms", "--reason", "promo help article") == 0
    assert "held coinbase.com terms: https://www.coinbase.com/legal/promo" in capsys.readouterr().out

    assert _cli(monkeypatch, "held") == 0
    out = capsys.readouterr().out
    assert "coinbase.com" in out and "promo help article" in out and "1 held documents" in out

    assert _cli(monkeypatch, "unhold", "coinbase.com", "terms") == 0
    assert "was held: promo help article" in capsys.readouterr().out
    assert db.held_documents(conn) == []
    assert _cli(monkeypatch, "unhold", "coinbase.com", "terms") == 1     # not held any more
    assert "is not held" in capsys.readouterr().out
