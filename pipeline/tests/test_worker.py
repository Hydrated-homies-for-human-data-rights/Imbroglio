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
    monkeypatch.setattr(worker.jobs, "claim", lambda conn, wid: (7, "slow.example", False))
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
