"""Rechecks (recheck.py): fetch stored documents again, record what changed,
and never take a site's rating down while the new text waits to be rated."""

import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import analysis, db, recheck
from imbroglio.api import router
from imbroglio.normalize import content_hash, normalize
from imbroglio.rubric import load

POLICY = ("This privacy policy explains the personal information we collect, the cookies we use, "
          "and when we share data with third parties. ") * 20
CHANGED = POLICY + "New: we now share your personal information with advertising partners. " * 3

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)


def _doc(conn, domain="site.example", text=POLICY, fetch_method="static"):
    sid = db.upsert_service(conn, domain)
    did = db.upsert_document(conn, sid, "privacy", f"https://{domain}/privacy", "link-text")
    text = normalize(text)
    vid = db.insert_version(conn, did, content_hash(text), text, fetch_method)
    conn.commit()
    return did, vid


def _age(conn, did, days):
    conn.execute("UPDATE document_versions SET fetched_at = now() - make_interval(days => %s) "
                 "WHERE document_id = %s", (days, did))
    conn.commit()


def _serve(monkeypatch, text):
    """Make the next fetch return `text` (None: the fetch fails)."""
    def fake(url, doc_type, session, use_playwright):
        if text is None:
            return None, "", "404", "static"
        return f"<html><body>{text}</body></html>", text, "200", "static"
    monkeypatch.setattr(recheck, "_try_url", fake)


def _row(conn, did):
    return conn.execute("""SELECT d.id, s.domain, d.doc_type, d.url FROM documents d
                           JOIN services s ON s.id = d.service_id WHERE d.id = %s""", (did,)).fetchone()


def _counts(conn):
    return tuple(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                 for t in ("document_versions", "change_events", "document_checks"))


def test_due_skips_fresh_checked_and_hand_stored_documents(conn):
    old, _ = _doc(conn, "old.example")
    fresh, _ = _doc(conn, "fresh.example")
    checked, _ = _doc(conn, "checked.example")
    manual, _ = _doc(conn, "manual.example", fetch_method="manual")
    for did in (old, checked, manual):
        _age(conn, did, 10)
    conn.execute("INSERT INTO document_checks (document_id, outcome) VALUES (%s, 'unchanged')", (checked,))
    conn.commit()
    assert [r[1] for r in recheck.due(conn, 7)] == ["old.example"]
    assert {r[1] for r in recheck.due(conn, 0)} == {"old.example", "fresh.example", "checked.example"}
    assert recheck.due(conn, 0, domains=["fresh.example"])[0][1] == "fresh.example"


def test_same_text_is_logged_as_unchanged_and_stores_no_version(conn, monkeypatch):
    did, vid = _doc(conn)
    _serve(monkeypatch, POLICY)
    check = recheck.check_one(conn, _row(conn, did), requests.Session())
    assert (check.outcome, check.version_id) == ("unchanged", vid)
    assert _counts(conn) == (1, 0, 1)


def test_new_text_stores_a_version_and_a_change_event(conn, monkeypatch):
    did, vid = _doc(conn)
    _serve(monkeypatch, CHANGED)
    check = recheck.check_one(conn, _row(conn, did), requests.Session())
    assert check.outcome == "changed" and check.version_id != vid
    assert "lines" in check.note
    assert _counts(conn) == (2, 1, 1)
    assert conn.execute("SELECT old_version_id, new_version_id FROM change_events").fetchone() == (
        vid, check.version_id)


def test_going_back_to_an_older_text_is_reverted_not_a_change(conn, monkeypatch):
    did, first = _doc(conn)
    _serve(monkeypatch, CHANGED)
    recheck.check_one(conn, _row(conn, did), requests.Session())
    _serve(monkeypatch, POLICY)
    check = recheck.check_one(conn, _row(conn, did), requests.Session())
    assert (check.outcome, check.version_id) == ("reverted", first)
    assert _counts(conn) == (2, 1, 2)   # no second change event


def test_a_bot_check_on_the_plain_fetch_is_retried_in_the_browser(monkeypatch):
    wall = "<html><head><title>Just a moment...</title></head><body>cf-chl- wait</body></html>"
    monkeypatch.setattr(recheck, "_try_url", lambda *a: (wall, "wait", "200", "static"))
    monkeypatch.setattr(recheck, "fetch_rendered", lambda url: (f"<html><body><p>{POLICY}</p></body></html>", "200"))
    text, how = recheck._fetch("https://site.example/privacy", "privacy", requests.Session(), True)
    assert how == "playwright" and "third parties" in text
    # without the browser, the wall is a failed check
    assert recheck._fetch("https://site.example/privacy", "privacy", requests.Session(), False) == (
        None, "blocked: bot challenge")


def test_a_failed_fetch_or_a_page_that_isnt_a_policy_is_logged_as_failed(conn, monkeypatch):
    did, _ = _doc(conn)
    _serve(monkeypatch, None)
    assert recheck.check_one(conn, _row(conn, did), requests.Session()).outcome == "failed"
    _serve(monkeypatch, "Page not found. " * 100)
    check = recheck.check_one(conn, _row(conn, did), requests.Session())
    assert check.outcome == "failed" and "signals" in check.note
    assert _counts(conn) == (1, 0, 2)


def test_dry_run_changes_nothing(conn, monkeypatch):
    did, _ = _doc(conn)
    _serve(monkeypatch, CHANGED)
    assert recheck.check_one(conn, _row(conn, did), requests.Session(), dry_run=True).outcome == "changed"
    assert _counts(conn) == (1, 0, 0)


def test_run_checks_every_row_and_summarizes(conn, monkeypatch):
    a, _ = _doc(conn, "a.example")
    b, _ = _doc(conn, "b.example")
    _serve(monkeypatch, POLICY)
    checks = recheck.run([_row(conn, a), _row(conn, b)], workers=2)
    assert recheck.summary(checks) == {"checked": 2, "unchanged": 2, "changed": 0, "reverted": 0, "failed": 0}


def test_a_detected_change_keeps_the_site_rated_until_the_new_text_is_rated(conn, monkeypatch):
    monkeypatch.setattr(analysis, "RUBRIC_VERSION", "v0.3")
    rubric = load("v0.3")
    did, vid = _doc(conn, "rated.example")
    conn.execute(
        """INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                 quotes_verified, verified, model)
           VALUES (%s, 'v0.3', 'sells_personal_data', %s, 'no', %s, %s, true, 'test')""",
        (vid, rubric.check("sells_personal_data").category, ["third parties"], [True]))
    analysis._write_scores(conn, vid, "v0.3")
    conn.commit()

    _serve(monkeypatch, CHANGED)
    new = recheck.check_one(conn, _row(conn, did), requests.Session()).version_id

    assert "rated.example" in db.site_findings(conn, "v0.3")
    card = _client.get("/v1/sites/rated.example").json()
    assert card["scorecard"] is not None
    assert card["documents"][0]["version_id"] == vid            # the version we rated
    assert card["documents"][0]["changes_detected"] == 1

    # once the new text is rated, it is the one shown
    conn.execute("""INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                          quotes_verified, verified, model)
                    SELECT %s, rubric_version, check_id, category, status, quotes, quotes_verified,
                           verified, model FROM findings WHERE version_id = %s""", (new, vid))
    conn.commit()
    assert _client.get("/v1/sites/rated.example").json()["documents"][0]["version_id"] == new
