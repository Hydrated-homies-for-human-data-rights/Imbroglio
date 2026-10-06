"""Queue worker: claims analysis requests and runs the pipeline.

    python -m imbroglio.worker                 # WORKER_CONCURRENCY threads (default 2)
    python -m imbroglio.worker --once          # process at most one job, then exit

Runs as its own Railway service, so headless Chromium never shares memory
with the web server. The web app can also start these threads in-process
(EMBEDDED_WORKER=1) for local development without a second terminal.

Each pipeline log line becomes a progress line on the request (heartbeat +
live log for clients). SIGTERM (redeploy) stops claiming new jobs; a job cut
off mid-run stops heart-beating and is reclaimed by the next worker.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import threading
import time

from . import db, jobs
from .analysis import ensure_analyzed
from .analyze import analyze

log = logging.getLogger("imbroglio.worker")

POLL_SECONDS = 2.0
TIME_BUDGET = 120.0
PROGRESS_MIN_INTERVAL = 0.3  # seconds; throttle DB writes from chatty runs

_stop = threading.Event()


class _ProgressHandler(logging.Handler):
    """Forwards one worker thread's pipeline log lines to its request row."""

    def __init__(self, request_id: int, thread_id: int) -> None:
        super().__init__()
        self.request_id = request_id
        self.thread_id = thread_id
        self.conn = db.connect()
        self.last = 0.0
        self.pending: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread != self.thread_id:
            return
        msg = record.getMessage()
        now = time.monotonic()
        if now - self.last < PROGRESS_MIN_INTERVAL:
            self.pending = msg  # keep the latest; flushed on the next write or close
            return
        self._write(msg)

    def _write(self, msg: str) -> None:
        try:
            jobs.progress(self.conn, self.request_id, msg)
            self.last = time.monotonic()
            self.pending = None
        except Exception:
            pass  # progress is best effort; the job result is what matters

    def close(self) -> None:
        if self.pending:
            self._write(self.pending)
        try:
            self.conn.close()
        finally:
            super().close()


def _summary(outcomes) -> dict:
    return {
        "documents": [
            {"doc_type": o.doc_type, "found": o.status != "failed", "status": o.status,
             "url": o.url, "chars": o.chars, "version_id": o.version_id,
             "discovered_via": o.discovered_via, "fetch_method": o.fetch_method,
             "notes": o.notes, "analysis": getattr(o, "analysis", None)}
            for o in outcomes
        ],
    }


def process_one(worker_id: str) -> bool:
    """Claim and run one job. Returns False if the queue was empty."""
    conn = db.connect()
    try:
        job = jobs.claim(conn, worker_id)
    finally:
        conn.close()
    if job is None:
        return False

    request_id, domain, use_playwright = job
    log.info("job %s: %s (browser %s)", request_id, domain, "on" if use_playwright else "off")
    pipeline_log = logging.getLogger("imbroglio")
    pipeline_log.setLevel(logging.INFO)
    handler = _ProgressHandler(request_id, threading.get_ident())
    pipeline_log.addHandler(handler)
    t0 = time.time()
    try:
        outcomes = analyze(domain, use_playwright=use_playwright, time_budget=TIME_BUDGET)
        seconds = time.time() - t0
        conn = db.connect()
        try:
            for o in outcomes:  # same audit trail as batch and console runs
                db.insert_attempt(conn, None, domain, o.doc_type, o.status != "failed",
                                  o.status, o.url, o.discovered_via, o.fetch_method,
                                  o.chars, o.notes or None, seconds)
            conn.commit()
            # Analysis (findings + scores) for every stored document. Reuses
            # identical text and respects the daily LLM budget; a failure here
            # never fails the crawl that already succeeded.
            for o in outcomes:
                if o.version_id:
                    try:
                        o.analysis = ensure_analyzed(conn, o.version_id)
                    except Exception:
                        conn.rollback()
                        log.exception("analysis failed for version %s", o.version_id)
                        o.analysis = "failed:error"
            pipeline_log.removeHandler(handler)
            handler.close()
            jobs.finish(conn, request_id, True, _summary(outcomes))
        finally:
            conn.close()
        log.info("job %s done in %.1fs", request_id, seconds)
    except Exception as exc:
        log.exception("job %s failed", request_id)
        pipeline_log.removeHandler(handler)
        handler.close()
        conn = db.connect()
        try:
            jobs.finish(conn, request_id, False, error=f"{type(exc).__name__}")
        finally:
            conn.close()
    return True


def _loop(worker_id: str) -> None:
    while not _stop.is_set():
        try:
            busy = process_one(worker_id)
        except Exception:
            log.exception("worker loop error (database unreachable?)")
            busy = False
        if not busy:
            _stop.wait(POLL_SECONDS)


def start_threads(n: int) -> list[threading.Thread]:
    """Start n worker threads (daemon). Used by the CLI and by the web app's
    embedded mode."""
    db.migrate()
    host = socket.gethostname()
    threads = []
    for i in range(n):
        t = threading.Thread(target=_loop, args=(f"{host}-{os.getpid()}-{i}",),
                             daemon=True, name=f"worker-{i}")
        t.start()
        threads.append(t)
    return threads


def main() -> int:
    ap = argparse.ArgumentParser(prog="imbroglio.worker")
    ap.add_argument("--once", action="store_true", help="process at most one job, then exit")
    ap.add_argument("--concurrency", type=int,
                    default=int(os.environ.get("WORKER_CONCURRENCY", "2")))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    if args.once:
        db.migrate()
        process_one(f"{socket.gethostname()}-once")
        return 0

    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    threads = start_threads(args.concurrency)
    log.info("worker started: %d threads", args.concurrency)
    while not _stop.is_set():
        _stop.wait(1.0)
    log.info("stopping: finishing in-flight jobs (up to %ss)", int(TIME_BUDGET))
    for t in threads:
        t.join(timeout=TIME_BUDGET + 30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
