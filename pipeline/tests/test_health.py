"""The health watch's numbers (health.py) and GET /v1/health."""

from dataclasses import replace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import analysis, health, jobs
from imbroglio.api import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)

QUIET = health.Snapshot(
    checked_at="2026-11-20T00:00:00+00:00", queued=0, running=0, visitor_queued=0,
    oldest_visitor_wait_minutes=None, oldest_wait_minutes=None, finished_last_hour=3,
    minutes_since_last_finish=4.0, stale_running=0, failed_24h=0, spent_24h_usd=1.0,
    budget_usd=5.0, hours_since_last_recheck=1.0)


def test_a_quiet_system_has_no_problems():
    assert health.problems(QUIET) == []


def test_a_busy_queue_that_is_moving_is_not_a_problem():
    busy = replace(QUIET, queued=80, running=2, oldest_wait_minutes=90.0, minutes_since_last_finish=2.0)
    assert health.problems(busy) == []


def test_each_problem_reads_plainly():
    bad = replace(QUIET, queued=5, running=0, visitor_queued=1, oldest_visitor_wait_minutes=41.0,
                  minutes_since_last_finish=55.0, stale_running=1, failed_24h=6,
                  spent_24h_usd=5.2, hours_since_last_recheck=30.0, overdue_rechecks=4)
    found = health.problems(bad)
    assert len(found) == 6
    assert found[0].startswith("A visitor's request has waited 41 minutes")
    assert any(p.startswith("The worker looks stopped") for p in found)
    assert any("budget is used up" in p for p in found)


def test_a_quiet_day_with_nothing_due_is_not_a_stopped_recheck():
    # Every document was checked within RECHECK_DAYS, so the hourly pass had
    # nothing to record. That used to post "rechecks stopped" every day.
    nothing_due = replace(QUIET, hours_since_last_recheck=40.0, overdue_rechecks=0)
    assert health.problems(nothing_due) == []
    stopped = replace(nothing_due, overdue_rechecks=12)
    assert health.problems(stopped) == [
        "Rechecks look stopped: 12 document(s) are overdue and no policy recheck was recorded in 40 hours."]
    # overdue documents while checks are still being recorded: a backlog, not a stop
    assert health.problems(replace(QUIET, overdue_rechecks=12)) == []


def test_overdue_counts_only_documents_past_due(conn, monkeypatch):
    from imbroglio import db, recheck
    from imbroglio.normalize import content_hash
    monkeypatch.setattr(recheck, "RECHECK_DAYS", 30)
    sid = db.upsert_service(conn, "old.example")
    for doc_type, age in (("privacy", "31 days"), ("terms", "29 days")):
        did = db.upsert_document(conn, sid, doc_type, f"https://old.example/{doc_type}", "link-text")
        vid = db.insert_version(conn, did, content_hash(doc_type), doc_type, "static")
        conn.execute("UPDATE document_versions SET fetched_at = now() - %s::interval WHERE id = %s",
                     (age, vid))
    conn.commit()
    s = health.snapshot(conn, ("web",))
    assert s.overdue_rechecks == 1 and s.hours_since_last_recheck is None
    assert health.problems(s)[-1].startswith("Rechecks look stopped: 1 document(s) are overdue")


def test_the_worker_isnt_stopped_while_a_job_is_running():
    slow = replace(QUIET, queued=3, running=1, minutes_since_last_finish=45.0)
    assert not any(p.startswith("The worker looks stopped") for p in health.problems(slow))


def test_endpoint_reports_counts_not_sites(conn, monkeypatch):
    monkeypatch.setattr(analysis, "DAILY_BUDGET_USD", 5.0)
    jobs.enqueue(conn, "visitor.example", source="web")
    conn.execute("UPDATE analysis_requests SET requested_at = now() - interval '45 minutes'")
    conn.commit()
    body = client.get("/v1/health").json()
    assert body["visitor_queued"] == 1 and body["queued"] == 1
    assert not body["ok"] and body["problems"][0].startswith("A visitor's request has waited 45 minutes")
    assert "visitor.example" not in str(body)
