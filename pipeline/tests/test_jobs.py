"""Queue behavior against a real Postgres (SKIP LOCKED, partial unique index
and interval math don't exist in a mock). Uses a throwaway database on the
local docker-compose server; skipped when that server isn't running."""

import psycopg

from imbroglio import db, jobs


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


def test_overview_lists_open_and_recent(conn):
    done_id, *_ = jobs.enqueue(conn, "done.com")
    jobs.claim(conn, "w")
    jobs.finish(conn, done_id, True, {"documents": [{"doc_type": "privacy", "found": True},
                                                     {"doc_type": "terms", "found": False}]})
    jobs.enqueue(conn, "waiting.com")
    jobs.enqueue(conn, "busy.com")
    jobs.enqueue(conn, "busy.com")  # higher priority -> claimed next
    running = jobs.claim(conn, "w")
    assert running[1] == "busy.com"
    ov = jobs.overview(conn)
    assert [j["domain"] for j in ov["open"]] == ["busy.com", "waiting.com"]  # running first
    assert ov["recent"][0]["domain"] == "done.com" and ov["recent"][0]["found"] == ["privacy"]
    assert ov["counts"] == {"done": 1, "running": 1, "queued": 1}


def test_batch_jobs_wait_behind_visitors(conn):
    jobs.enqueue_batch(conn, ["a.com", "b.com"])
    rid, *_ = jobs.enqueue(conn, "visitor.com")
    assert jobs.get(conn, rid)["queue_ahead"] == 0
    assert jobs.claim(conn, "w")[1] == "visitor.com"
    assert jobs.claim(conn, "w")[1] == "a.com"  # then batch jobs, in file order


def test_visitor_request_bumps_a_queued_batch_job(conn):
    jobs.enqueue_batch(conn, ["a.com", "b.com"])
    jobs.enqueue(conn, "b.com")
    assert jobs.claim(conn, "w")[1] == "b.com"
    assert jobs.stats(conn) == {"queued": 1, "running": 1}


def test_enqueue_batch_skips_known_domains_and_respects_limit(conn):
    service = db.upsert_service(conn, "stored.com")
    db.upsert_document(conn, service, "privacy", "https://stored.com/privacy", "link")
    conn.commit()
    done, *_ = jobs.enqueue(conn, "tried.com")
    jobs.claim(conn, "w")
    jobs.finish(conn, done, True, {"documents": []})
    jobs.enqueue(conn, "waiting.com")

    out = jobs.enqueue_batch(conn, ["stored.com", "tried.com", "waiting.com",
                                    "new1.com", "new2.com", "new3.com"], limit=2)
    assert out == {"queued": ["new1.com", "new2.com"],
                   "already_stored": ["stored.com"],
                   "already_requested": ["tried.com", "waiting.com"]}
    assert jobs.enqueue_batch(conn, ["new1.com", "new3.com"], dry_run=True)["queued"] == ["new3.com"]
    assert jobs.stats(conn) == {"queued": 3, "done": 1}  # dry run added nothing
    assert jobs.enqueue_batch(conn, ["new1.com", "new3.com"])["queued"] == ["new3.com"]
