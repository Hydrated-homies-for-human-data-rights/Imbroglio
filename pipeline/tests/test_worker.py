"""The worker's own guards, with the database and the crawl faked: a job that
never ends is given up on, and what a failed job says in public is a plain
sentence, never an exception name or a dollar amount."""

import logging
import threading
import time

import pytest

from imbroglio import SERVER_ONLY, worker


class _Conn:
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass


@pytest.fixture
def fake(monkeypatch):
    calls = {"finish": [], "heartbeat": 0, "progress": []}
    monkeypatch.setattr(worker.db, "connect", lambda *a, **k: _Conn())
    monkeypatch.setattr(worker.db, "insert_attempt", lambda *a, **k: None)
    monkeypatch.setattr(worker.jobs, "claim", lambda conn, wid: (7, "slow.example", False, None))
    monkeypatch.setattr(worker.jobs, "finish",
                        lambda conn, rid, ok, result=None, error=None: calls["finish"].append((ok, result, error)))
    monkeypatch.setattr(worker.jobs, "progress", lambda conn, rid, line: calls["progress"].append(line))

    def beat(conn, rid):
        calls["heartbeat"] += 1
    monkeypatch.setattr(worker.jobs, "heartbeat", beat)
    monkeypatch.setattr(worker, "pending_versions", lambda conn, domain=None: [])
    monkeypatch.setattr(worker, "PROGRESS_MIN_INTERVAL", 0)
    return calls


def test_a_job_past_the_time_limit_is_failed_and_left_behind(fake, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(worker, "analyze", lambda *a, **k: release.wait(30) and [])
    monkeypatch.setattr(worker, "JOB_TIME_LIMIT", 0.5)
    monkeypatch.setattr(worker, "HEARTBEAT_SECONDS", 0.1)
    started = time.monotonic()
    try:
        assert worker.process_one("w") is True
        assert time.monotonic() - started < 5
        assert fake["finish"] == [(False, None, worker.TOOK_TOO_LONG)]
        assert fake["heartbeat"] >= 2          # kept alive while it waited, so never reclaimed
    finally:
        release.set()


def test_a_job_given_up_on_stops_instead_of_carrying_on(fake, monkeypatch):
    # Python can't kill the thread, so it is told to stop: once the slow
    # crawl returns, it records nothing, starts no paid analysis, and writes
    # no more lines to a request already marked failed.
    from imbroglio.analyze import DocOutcome

    release = threading.Event()
    analyzed, attempts = [], []
    log = logging.getLogger("imbroglio")

    def slow_crawl(*a, **k):
        release.wait(30)
        log.info("late line")
        return [DocOutcome("privacy", "stored-new", "https://slow.example/privacy", 5)]
    monkeypatch.setattr(worker, "analyze", slow_crawl)
    monkeypatch.setattr(worker, "ensure_analyzed", lambda conn, vid, **k: analyzed.append(vid) or "analyzed")
    monkeypatch.setattr(worker.db, "insert_attempt", lambda *a, **k: attempts.append(a))
    monkeypatch.setattr(worker, "JOB_TIME_LIMIT", 0.3)
    monkeypatch.setattr(worker, "HEARTBEAT_SECONDS", 0.1)
    try:
        assert worker.process_one("w") is True
        assert fake["finish"] == [(False, None, worker.TOOK_TOO_LONG)]
        job = next(t for t in threading.enumerate() if t.name == "job-7")
    finally:
        release.set()
    job.join(5)
    assert not job.is_alive()
    assert analyzed == [] and attempts == []
    assert "late line" not in fake["progress"]


def test_the_polling_connection_is_reused(fake, monkeypatch):
    opened = []
    monkeypatch.setattr(worker.db, "connect", lambda *a, **k: opened.append(1) or _Conn())
    monkeypatch.setattr(worker.jobs, "claim", lambda conn, wid: None)
    shared = _Conn()
    assert worker.process_one("w", shared) is False
    assert worker.process_one("w", shared) is False
    assert opened == []


def test_a_crash_reads_as_a_plain_sentence(fake, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("OperationalError: connection to 10.0.0.3 refused")
    monkeypatch.setattr(worker, "analyze", boom)
    worker.process_one("w")
    (ok, _, error), = fake["finish"]
    assert not ok and error == worker.CRASHED
    assert "Error" not in error and "10.0.0.3" not in error


def test_server_only_lines_stay_out_of_the_public_progress(fake, monkeypatch):
    log = logging.getLogger("imbroglio")

    def chatty(*a, **k):
        log.info("analysis paused: daily limit reached, it will finish later")
        log.info("analysis: daily LLM budget reached ($5.01 of $5.00)", extra=SERVER_ONLY)
        return []
    monkeypatch.setattr(worker, "analyze", chatty)
    worker.process_one("w")
    assert fake["progress"] == ["analysis paused: daily limit reached, it will finish later"]
    assert fake["finish"][0][0] is True


def test_a_pasted_policy_link_reaches_the_crawl(fake, monkeypatch):
    monkeypatch.setattr(worker.jobs, "claim",
                        lambda conn, wid: (7, "slow.example", False, "https://slow.example/privacy"))
    seen = {}

    def crawl(domain, **k):
        seen.update(k)
        return []
    monkeypatch.setattr(worker, "analyze", crawl)
    worker.process_one("w")
    assert seen["policy_url"] == "https://slow.example/privacy"
    assert fake["finish"][0][0] is True
