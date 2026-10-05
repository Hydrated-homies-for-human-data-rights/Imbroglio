"""Queue behavior against a real Postgres (SKIP LOCKED, partial unique index
and interval math don't exist in a mock). Uses a throwaway database on the
local docker-compose server; skipped when that server isn't running."""

import uuid

import psycopg
import pytest

from imbroglio import db, jobs

ADMIN_DSN = "postgresql://imbroglio:imbroglio@localhost:5432/imbroglio"


@pytest.fixture(scope="module")
def test_dsn():
    name = f"imb_test_{uuid.uuid4().hex[:8]}"
    try:
        admin = psycopg.connect(ADMIN_DSN, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local Postgres not running (docker compose up -d)")
    admin.execute(f"CREATE DATABASE {name}")
    dsn = ADMIN_DSN.rsplit("/", 1)[0] + "/" + name
    yield dsn
    admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


@pytest.fixture
def conn(test_dsn, monkeypatch):
    monkeypatch.setenv("IMBROGLIO_DB", test_dsn)
    monkeypatch.setattr(db, "_migrated", False)
    db.migrate()
    c = db.connect()
    c.execute("TRUNCATE analysis_requests RESTART IDENTITY")
    c.commit()
    yield c
    c.close()


def test_duplicate_requests_merge(conn):
    a, status, created = jobs.enqueue(conn, "notion.so")
    b, _, created2 = jobs.enqueue(conn, "notion.so")
    assert (status, created, created2) == ("queued", True, False)
    assert a == b
    assert conn.execute("SELECT request_count FROM analysis_requests WHERE id = %s",
                        (a,)).fetchone()[0] == 2


def test_two_workers_never_get_the_same_job(conn, test_dsn):
    jobs.enqueue(conn, "a.com")
    jobs.enqueue(conn, "b.com")
    w1, w2 = psycopg.connect(test_dsn), psycopg.connect(test_dsn)
    try:
        j1, j2 = jobs.claim(w1, "w1"), jobs.claim(w2, "w2")
        assert j1 and j2 and j1[0] != j2[0]
        assert jobs.claim(w1, "w1") is None  # queue drained
    finally:
        w1.close(), w2.close()


def test_priority_by_request_count(conn):
    jobs.enqueue(conn, "old.com")
    jobs.enqueue(conn, "popular.com")
    jobs.enqueue(conn, "popular.com")
    assert jobs.claim(conn, "w")[1] == "popular.com"


def test_finished_domain_can_be_requested_again(conn):
    rid, *_ = jobs.enqueue(conn, "x.com")
    jobs.claim(conn, "w")
    jobs.finish(conn, rid, True, {"documents": []})
    rid2, _, created = jobs.enqueue(conn, "x.com")
    assert created and rid2 != rid


def test_dead_worker_job_is_reclaimed_then_abandoned(conn):
    rid, *_ = jobs.enqueue(conn, "crashy.com")
    for attempt in range(1, jobs.MAX_ATTEMPTS + 1):
        job = jobs.claim(conn, f"w{attempt}")
        assert job and job[0] == rid
        # Simulate the worker dying: heartbeat goes stale.
        conn.execute("UPDATE analysis_requests SET heartbeat_at = now() - interval '1 hour' WHERE id = %s",
                     (rid,))
        conn.commit()
    assert jobs.claim(conn, "w-last") is None
    row = jobs.get(conn, rid)
    assert row["status"] == "failed" and "abandoned" in row["error"]


def test_progress_and_result_roundtrip(conn):
    rid, *_ = jobs.enqueue(conn, "p.com")
    jobs.claim(conn, "w")
    jobs.progress(conn, rid, "fetching homepage")
    jobs.progress(conn, rid, "got 1,234 chars")
    jobs.finish(conn, rid, True, {"documents": [{"doc_type": "privacy", "found": True}]})
    row = jobs.get(conn, rid)
    assert row["progress"] == ["fetching homepage", "got 1,234 chars"]
    assert row["status"] == "done" and row["result"]["documents"][0]["found"]
