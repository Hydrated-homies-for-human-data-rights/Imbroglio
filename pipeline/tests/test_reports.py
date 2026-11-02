"""POST /v1/reports: the correction path. Reports are stored cleaned, bots
get a fake success, and the reviewer's CLI helpers change status."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import api, cli
from imbroglio.api import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    monkeypatch.setattr(api, "_report_limiter", api._RateLimiter(api.REPORTS_PER_HOUR))


def _report(**overrides):
    body = {"domain": "notion.so", "kind": "quote",
            "message": "The quoted sentence is not in the privacy policy."}
    body.update(overrides)
    return client.post("/v1/reports", json=body)


def _rows(conn):
    return conn.execute(
        "SELECT domain, kind, message, contact, page, client, status FROM reports ORDER BY id"
    ).fetchall()


def test_report_is_stored_with_cleaned_fields(conn):
    r = _report(domain="https://www.Notion.so/privacy", contact="  reader@example.com ",
                page="/site/notion.so")
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0 and body["received_at"]
    assert _rows(conn) == [("notion.so", "quote", "The quoted sentence is not in the privacy policy.",
                            "reader@example.com", "/site/notion.so", "testclient", "new")]


def test_domain_is_optional(conn):
    assert _report(domain=None, kind="other").status_code == 201
    assert _report(domain="   ", kind="other").status_code == 201
    assert [row[0] for row in _rows(conn)] == [None, None]


def test_honeypot_returns_success_and_stores_nothing(conn):
    r = _report(website="http://spam.example")
    assert r.status_code == 201 and r.json()["id"] == 0
    assert _rows(conn) == []


def test_message_too_short(conn):
    assert _report(message="short").status_code == 422  # pydantic, before the handler
    # long enough for pydantic, too short once padding and control characters go
    r = _report(message="   hi\x00\x00\x00\x00\x00\x00\x00\x00   ")
    assert r.status_code == 400 and r.json()["error"] == "message is too short"
    assert _rows(conn) == []


def test_invalid_domain_is_400(conn):
    r = _report(domain="127.0.0.1")
    assert r.status_code == 400 and r.json()["error"] == "not a valid domain"
    assert _rows(conn) == []


def test_invalid_kind_is_422(conn):
    assert _report(kind="rant").status_code == 422


def test_control_characters_are_stripped(conn):
    _report(message="line one\x00\x1b[31m\nline two\tindented\x7f", contact="me\x07@example.com")
    (row,) = _rows(conn)
    assert row[2] == "line one[31m\nline two\tindented"  # newline and tab survive
    assert row[3] == "me@example.com"


def test_page_outside_the_site_is_dropped(conn):
    _report(page="https://evil.example/phish")
    _report(page="https://imbroglio.io/site/notion.so")
    _report(page="/learn#retention")
    assert [row[4] for row in _rows(conn)] == [None, "https://imbroglio.io/site/notion.so",
                                               "/learn#retention"]


def test_per_client_hourly_limit(conn, monkeypatch):
    monkeypatch.setattr(api, "_report_limiter", api._RateLimiter(2))
    assert _report().status_code == 201
    assert _report().status_code == 201
    r = _report()
    assert r.status_code == 429 and "Retry-After" in r.headers
    assert len(_rows(conn)) == 2


def test_daily_cap(conn, monkeypatch):
    monkeypatch.setattr(api, "REPORTS_PER_DAY", 1)
    assert _report().status_code == 201
    assert _report().status_code == 429
    assert len(_rows(conn)) == 1


def test_cli_list_and_mark(conn):
    rid = _report(message="First line of the report\nsecond line " + "x" * 100,
                  contact="reader@example.com").json()["id"]
    _report(domain=None, kind="other", message="Site-wide feedback here.")

    rows = cli.list_reports(conn)
    assert [r[0] for r in rows] == [rid + 1, rid]  # newest first
    line = cli._report_line(rows[1])
    assert "  new  " in line and "quote" in line and "notion.so" in line
    assert "First line of the report second line" in line and "\n" not in line
    assert line.endswith("<reader@example.com>")
    assert " other " in cli._report_line(rows[0]) and "-" + " " * 27 in cli._report_line(rows[0])

    assert cli.mark_report(conn, rid, "withdrawn", "quote not in document")
    assert cli.list_reports(conn) == [r for r in rows if r[0] != rid]
    (done,) = cli.list_reports(conn, status="withdrawn")
    assert done[2] == "withdrawn" and done[7] == "quote not in document"
    # marking again without a note keeps the old note
    assert cli.mark_report(conn, rid, "reviewed")
    assert cli.list_reports(conn, status="reviewed")[0][7] == "quote not in document"
    assert len(cli.list_reports(conn, status="all")) == 2
    assert not cli.mark_report(conn, 999999, "dismissed")
    with pytest.raises(ValueError):
        cli.mark_report(conn, rid, "bogus")
