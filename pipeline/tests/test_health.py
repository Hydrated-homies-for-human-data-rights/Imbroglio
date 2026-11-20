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
                  spent_24h_usd=5.2, hours_since_last_recheck=30.0)
    found = health.problems(bad)
    assert len(found) == 6
    assert found[0].startswith("A visitor's request has waited 41 minutes")
    assert any(p.startswith("The worker looks stopped") for p in found)
    assert any("budget is used up" in p for p in found)


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
