"""Withdrawing one finding (cli withdraw / unwithdraw / withdrawn).

The site promises that a finding whose quote doesn't support it is withdrawn
and the rating worked out again from what remains. A withdrawn finding keeps
its row but is left out of scoring and out of every public answer, and only
unwithdraw brings it back: reading the same document again does not."""

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import analysis, cli, db, search
from imbroglio.api import router
from imbroglio.llm_extract import Extraction, Finding
from imbroglio.normalize import content_hash

app = FastAPI()
app.include_router(router)
client = TestClient(app)

RUBRIC = "v0.1"   # scorer s1: the headline is the worst category
TEXT = "We sell personal data to partners. We share data only with service providers. " * 30
SELLS = ("sells_personal_data", "selling_sharing", "yes", "We sell personal data to partners.")
SHARES = ("shares_for_advertising", "selling_sharing", "service_providers_only",
          "We share data only with service providers.")
# with both findings: SEVERE 23/100; without the selling one: MODERATE 79/100


@pytest.fixture(autouse=True)
def pinned_rubric(monkeypatch):
    monkeypatch.setattr("imbroglio.analysis.RUBRIC_VERSION", RUBRIC)
    search.clear_cache()
    yield
    search.clear_cache()


def _store(conn, domain, text=TEXT, doc_type="privacy"):
    sid = db.upsert_service(conn, domain)
    did = db.upsert_document(conn, sid, doc_type, f"https://{domain}/{doc_type}", "link-text")
    vid = db.insert_version(conn, did, content_hash(text), text, "static")
    conn.commit()
    return vid


def _rate(conn, version_id, findings=(SELLS, SHARES)):
    for check_id, category, status, quote in findings:
        conn.execute("""INSERT INTO findings (version_id, rubric_version, check_id, category, status,
                                              quotes, quotes_verified, verified, explanation, model)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, true, 'because', 'test')""",
                     (version_id, RUBRIC, check_id, category, status, [quote], [True]))
    analysis.rescore(conn, version_id, RUBRIC)
    conn.commit()


def _site(domain="sells.example"):
    return client.get(f"/v1/sites/{domain}").json()


def _shown_checks(body):
    return {f["check_id"] for c in body["scorecard"]["categories"] for f in c["findings"]}


def _lookup(domain):
    full = hashlib.sha256(domain.encode()).hexdigest()
    body = client.get(f"/v1/lookup/{full[:6]}").json()
    return next(s for s in body["sites"] if s["hash"] == full)


def _stored_tier(conn, version_id, category="selling_sharing"):
    return conn.execute("SELECT tier FROM scores WHERE version_id = %s AND rubric_version = %s "
                        "AND category = %s", (version_id, RUBRIC, category)).fetchone()[0]


def _withdraw(conn, vid, check_id="sells_personal_data", reason="the quote is about cookies"):
    return db.withdraw_finding(conn, vid, RUBRIC, check_id, reason, "tester")


def test_a_withdrawn_finding_is_left_out_of_scoring(conn):
    vid = _store(conn, "sells.example")
    _rate(conn, vid)
    assert db.headlines(conn, RUBRIC) == {"sells.example": "SEVERE"}
    assert _stored_tier(conn, vid) == "SEVERE"

    assert _withdraw(conn, vid) == "yes"
    assert db.headlines(conn, RUBRIC) == {"sells.example": "MODERATE"}
    assert _stored_tier(conn, vid) == "MODERATE"          # the scores table is written again too
    assert [c for _, c, *_ in db.site_findings(conn, RUBRIC)["sells.example"]] == ["shares_for_advertising"]
    # the row is kept, with who and why
    assert db.withdrawn_findings(conn)[0][:4] == ("sells.example", "privacy", "sells_personal_data", "yes")
    assert db.withdrawn_findings(conn)[0][7:9] == ("the quote is about cookies", "tester")
    assert _withdraw(conn, vid) is None                   # already withdrawn


def test_a_withdrawn_finding_is_left_out_of_every_api_answer(conn):
    vid = _store(conn, "sells.example")
    _rate(conn, vid)
    before = _site()
    assert before["scorecard"]["headline"] == "SEVERE" and before["scorecard"]["score"]["value"] == 23
    assert "sells_personal_data" in _shown_checks(before)

    _withdraw(conn, vid)
    search.clear_cache()
    card = _site()["scorecard"]
    assert card["headline"] == "MODERATE" and card["score"]["value"] == 79
    assert _shown_checks(_site()) == {"shares_for_advertising"}
    assert [d["check_id"] for d in card["score"]["deductions"]] == ["shares_for_advertising"]

    found = _lookup("sells.example")["scores"]
    assert found["headline"] == "MODERATE" and found["score"] == 79
    assert {c["key"]: c["findings"] for c in found["categories"]}["selling_sharing"] == 1
    for path in ("/v1/sites", "/v1/recent"):
        site = client.get(path).json()["sites"][0]
        assert site["headline"] == "MODERATE" and site["score"] == 79
    hit = client.get("/v1/search", params={"q": "sells.example"}).json()["results"][0]
    assert hit["headline"] == "MODERATE" and hit["score"] == 79


def test_unwithdraw_restores_the_finding_and_the_rating(conn):
    vid = _store(conn, "sells.example")
    _rate(conn, vid)
    _withdraw(conn, vid)
    assert db.unwithdraw_finding(conn, vid, RUBRIC, "sells_personal_data") == \
        ("yes", "the quote is about cookies")
    assert _stored_tier(conn, vid) == "SEVERE"
    card = _site()["scorecard"]
    assert card["headline"] == "SEVERE" and card["score"]["value"] == 23
    assert "sells_personal_data" in _shown_checks(_site())
    assert db.withdrawn_findings(conn) == []
    assert db.unwithdraw_finding(conn, vid, RUBRIC, "sells_personal_data") is None


def test_withdrawing_every_finding_never_sends_the_document_back_to_the_model(conn, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    vid = _store(conn, "sells.example")
    _rate(conn, vid)
    _withdraw(conn, vid)
    _withdraw(conn, vid, "shares_for_advertising")
    assert analysis.pending_versions(conn) == []
    assert db.rated_version(conn, "sells.example", "privacy", RUBRIC) == vid
    assert _site()["scorecard"] is None                   # nothing left to rate on


def test_reading_the_same_version_again_keeps_the_withdrawal(conn, monkeypatch):
    def same_answers(text, rubric, model):
        return Extraction(model, "ok", findings=[
            Finding(c, cat, st, [q], [True], True, "again") for c, cat, st, q in (SELLS, SHARES)])
    monkeypatch.setattr(analysis, "extract", same_answers)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    vid = _store(conn, "sells.example")
    assert analysis.ensure_analyzed(conn, vid) == "analyzed"
    _withdraw(conn, vid)

    assert analysis.ensure_analyzed(conn, vid, force=True) == "analyzed"
    assert db.finding_state(conn, vid, RUBRIC, "sells_personal_data") == ("yes", True)
    assert _site()["scorecard"]["headline"] == "MODERATE"
    assert _stored_tier(conn, vid) == "MODERATE"


def test_a_copy_of_identical_text_carries_the_withdrawal(conn):
    vid = _store(conn, "sells.example")
    _rate(conn, vid)
    _withdraw(conn, vid)
    copy = _store(conn, "sister.example")
    assert analysis.ensure_analyzed(conn, copy) == "reused"
    assert db.finding_state(conn, copy, RUBRIC, "sells_personal_data") == ("yes", True)
    assert _site("sister.example")["scorecard"]["headline"] == "MODERATE"


def test_identical_copies_rated_before_the_withdrawal_are_named(conn):
    vid = _store(conn, "sells.example")
    _rate(conn, vid)
    _rate(conn, _store(conn, "sister.example"))
    _withdraw(conn, vid)
    assert db.identical_copies(conn, vid, RUBRIC, "sells_personal_data") == ["sister.example"]
    assert _site("sister.example")["scorecard"]["headline"] == "SEVERE"   # per site: untouched


def _cli(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["imbroglio", *argv])
    return cli.main()


def test_cli_withdraw_withdrawn_unwithdraw_round_trip(conn, monkeypatch, capsys):
    vid = _store(conn, "sells.example")
    _rate(conn, vid)
    rid = conn.execute("""INSERT INTO reports (domain, kind, message) VALUES
                          ('sells.example', 'quote', 'that quote is about cookies') RETURNING id""").fetchone()[0]
    conn.commit()

    assert _cli(monkeypatch, "withdraw", "sells.example", "not_a_check", "--doc", "privacy",
                "--reason", "x") == 2
    assert _cli(monkeypatch, "withdraw", "nothing.example", "sells_personal_data", "--doc", "privacy",
                "--reason", "x") == 1
    assert _cli(monkeypatch, "withdraw", "sells.example", "retention_period", "--doc", "privacy",
                "--reason", "x") == 1                                       # no such finding
    assert _cli(monkeypatch, "withdraw", "sells.example", "sells_personal_data", "--doc", "privacy",
                "--reason", "x", "--report", "9999") == 1                   # no such report
    assert db.withdrawn_findings(conn) == []
    capsys.readouterr()

    assert _cli(monkeypatch, "withdraw", "www.Sells.example", "sells_personal_data", "--doc", "privacy",
                "--reason", "the quote is about cookies", "--report", str(rid), "--by", "sam") == 0
    out = capsys.readouterr().out
    assert "withdrew sells.example privacy sells_personal_data (yes)" in out
    assert "rating: SEVERE 23/100 -> MODERATE 79/100" in out
    status, note = conn.execute("SELECT status, note FROM reports WHERE id = %s", (rid,)).fetchone()
    assert status == "withdrawn" and "sells_personal_data" in note and "cookies" in note
    assert conn.execute("SELECT withdrawn_report, withdrawn_by FROM findings WHERE check_id = "
                        "'sells_personal_data'").fetchone() == (rid, "sam")

    assert _cli(monkeypatch, "withdraw", "sells.example", "sells_personal_data", "--doc", "privacy",
                "--reason", "again") == 1
    assert "already withdrawn" in capsys.readouterr().out
    assert _cli(monkeypatch, "withdrawn") == 0
    out = capsys.readouterr().out
    assert "sells_personal_data" in out and "the quote is about cookies" in out and "1 withdrawn findings" in out

    assert _cli(monkeypatch, "unwithdraw", "sells.example", "sells_personal_data", "--doc", "privacy") == 0
    out = capsys.readouterr().out
    assert "restored sells.example privacy sells_personal_data" in out
    assert "rating: MODERATE 79/100 -> SEVERE 23/100" in out
    assert _cli(monkeypatch, "unwithdraw", "sells.example", "sells_personal_data", "--doc", "privacy") == 1
    assert "is not withdrawn" in capsys.readouterr().out
