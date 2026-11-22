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

from . import SERVER_ONLY, db, jobs
from .analysis import analyze_backlog, ensure_analyzed, pending_versions
from .analyze import analyze

log = logging.getLogger("imbroglio.worker")

POLL_SECONDS = 2.0
TIME_BUDGET = 120.0
PROGRESS_MIN_INTERVAL = 0.3  # seconds; throttle DB writes from chatty runs
# Hard limit on one job, crawl and analysis together. TIME_BUDGET is the
# crawl's own soft budget and each model call takes a minute or two, so a
# real job ends well inside this.
JOB_TIME_LIMIT = float(os.environ.get("JOB_TIME_LIMIT", "600"))
# The supervising thread heart-beats on this schedule, so a long model call
# (which logs nothing) isn't mistaken for a dead worker and reclaimed after
# jobs.STALE_AFTER. Only a worker process that died goes quiet.
HEARTBEAT_SECONDS = 30.0
# What a failed request says in public. The details stay in the server log.
TOOK_TOO_LONG = "This site took too long to analyze, so we stopped. Please try again later."
CRASHED = "Something went wrong on our side while analyzing this site. Please try again later."

_stop = threading.Event()


class _ProgressHandler(logging.Handler):
    """Forwards one worker thread's pipeline log lines to its request row."""

    def __init__(self, request_id: int, thread_id: int, cancel: threading.Event | None = None) -> None:
        super().__init__()
        self.request_id = request_id
        self.thread_id = thread_id
        self.cancel = cancel
        self.conn = db.connect()
        self.last = 0.0
        self.pending: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread != self.thread_id or getattr(record, "server_only", False):
            return
        if self.cancel is not None and self.cancel.is_set():
            return  # the request was already marked failed; its log is closed
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
            {"doc_type": o.doc_type, "found": o.found, "status": o.status,
             "url": o.url, "chars": o.chars, "version_id": o.version_id,
             "discovered_via": o.discovered_via, "fetch_method": o.fetch_method,
             "notes": o.notes, "analysis": getattr(o, "analysis", None)}
            for o in outcomes
        ],
    }


def process_one(worker_id: str, conn=None) -> bool:
    """Claim and run one job. Returns False if the queue was empty. `conn`
    is the polling loop's own connection, kept across polls; without one a
    connection is opened for the claim.

    The job runs on its own thread while this one keeps its heartbeat going
    and watches the clock. A job past JOB_TIME_LIMIT is marked failed and left
    behind, so one site that stalls every fetch can't hold a worker thread
    (and, through reclaims, the next one) forever. Python can't kill a
    thread, so the job is told to stop instead (`cancel`): it starts no new
    model call, stores nothing more, and writes no more progress to the
    request. A fetch already in flight still runs to its own deadline in
    fetch.py, and a model call already in flight finishes and is recorded,
    since it has been paid for."""
    own = conn is None
    if own:
        conn = db.connect()
    try:
        job = jobs.claim(conn, worker_id)
    finally:
        if own:
            conn.close()
    if job is None:
        return False

    request_id, domain, use_playwright, policy_url = job
    log.info("job %s: %s (browser %s)", request_id, domain, "on" if use_playwright else "off")
    outcome: dict = {}
    cancel = threading.Event()
    t = threading.Thread(target=_run_job,
                         args=(request_id, domain, use_playwright, policy_url, outcome, cancel),
                         daemon=True, name=f"job-{request_id}")
    t0 = time.monotonic()
    t.start()
    while True:
        t.join(HEARTBEAT_SECONDS)
        if not t.is_alive():
            break
        if time.monotonic() - t0 > JOB_TIME_LIMIT:
            log.error("job %s (%s) still running after %ss; marked failed and told to stop",
                      request_id, domain, int(JOB_TIME_LIMIT))
            cancel.set()
            outcome = {"ok": False, "error": TOOK_TOO_LONG}
            break
        try:
            conn = db.connect()
            try:
                jobs.heartbeat(conn, request_id)
            finally:
                conn.close()
        except Exception:
            log.exception("job %s: heartbeat failed", request_id)

    conn = db.connect()
    try:
        if outcome.get("ok"):
            jobs.finish(conn, request_id, True, outcome["result"])
        else:
            jobs.finish(conn, request_id, False, error=outcome.get("error", CRASHED))
    finally:
        conn.close()
    return True


def _run_job(request_id: int, domain: str, use_playwright: bool, policy_url: str | None,
             outcome: dict, cancel: threading.Event | None = None) -> None:
    """Crawl and analyze one site; the result goes into `outcome` for
    process_one to record. Once `cancel` is set (process_one gave up on the
    job) it stops at the next step instead of carrying on unseen."""
    cancel = cancel or threading.Event()
    pipeline_log = logging.getLogger("imbroglio")
    pipeline_log.setLevel(logging.INFO)
    handler = _ProgressHandler(request_id, threading.get_ident(), cancel)
    pipeline_log.addHandler(handler)
    t0 = time.time()
    try:
        outcomes = analyze(domain, use_playwright=use_playwright, time_budget=TIME_BUDGET,
                           policy_url=policy_url)
        seconds = time.time() - t0
        if cancel.is_set():
            log.warning("job %s (%s) finished its crawl after it was given up on; stopping there",
                        request_id, domain, extra=SERVER_ONLY)
            return
        conn = db.connect()
        try:
            for o in outcomes:  # same audit trail as batch and console runs
                db.insert_attempt(conn, None, domain, o.doc_type, o.found,
                                  o.status, o.url, o.discovered_via, o.fetch_method,
                                  o.chars, o.notes or None, seconds)
            conn.commit()
            # Analysis (findings + scores) for every stored document. Reuses
            # identical text and respects the daily LLM budget; a failure here
            # never fails the crawl that already succeeded.
            for o in outcomes:
                if o.version_id:
                    o.analysis = _analyze_safely(conn, o.version_id, cancel)
            # Documents stored earlier that are still waiting (the budget ran
            # out, or this crawl couldn't reach them today).
            seen = {o.version_id for o in outcomes}
            for version_id in pending_versions(conn, domain=domain):
                if version_id not in seen and not cancel.is_set():
                    _analyze_safely(conn, version_id, cancel)
        finally:
            conn.close()
        outcome.update(ok=True, result=_summary(outcomes))
        log.info("job %s done in %.1fs", request_id, time.time() - t0, extra=SERVER_ONLY)
    except Exception:
        log.exception("job %s failed", request_id, extra=SERVER_ONLY)
        outcome.update(ok=False, error=CRASHED)
    finally:
        pipeline_log.removeHandler(handler)
        handler.close()


def _analyze_safely(conn, version_id: int, cancel: threading.Event | None = None) -> str:
    try:
        return ensure_analyzed(conn, version_id, cancel=cancel)
    except Exception:
        conn.rollback()
        log.exception("analysis failed for version %s", version_id, extra=SERVER_ONLY)
        return "failed:error"


def _loop(worker_id: str) -> None:
    # One connection for polling, kept between polls: an idle worker asks for
    # a job every POLL_SECONDS, and a new connection each time was one TLS
    # handshake and backend start per thread every two seconds. Dropped and
    # opened again after any error, since it may be the connection that broke.
    conn = None
    try:
        while not _stop.is_set():
            try:
                if conn is None or conn.closed:
                    conn = db.connect()
                busy = process_one(worker_id, conn)
            except Exception:
                log.exception("worker loop error (database unreachable?)")
                busy = False
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
            if not busy:
                _stop.wait(POLL_SECONDS)
    finally:
        if conn is not None:
            conn.close()


RECHECK_TICK_SECONDS = 3600.0
RECHECK_FIRST_DELAY = 300.0  # let a fresh deploy settle before the first pass


def _recheck_loop() -> None:
    """Once an hour, recheck the stored documents that are due (recheck.py).
    Detect-only: no model calls. Only the worker service runs this, never the
    web app's embedded workers, so there is one schedule."""
    from . import recheck

    _stop.wait(RECHECK_FIRST_DELAY)
    while not _stop.is_set():
        try:
            recheck.scheduled_tick(_stop)
        except Exception:
            log.exception("recheck pass failed (database unreachable?)")
        _stop.wait(RECHECK_TICK_SECONDS)


BACKLOG_TICK_SECONDS = 3600.0


def _backlog_loop() -> None:
    """Once an hour, analyze stored documents still waiting for it, oldest
    first, within the daily LLM budget (analysis.analyze_backlog). Without
    this a site whose analysis was skipped for the budget stayed unrated.
    Worker service only, like the recheck schedule."""
    _stop.wait(RECHECK_FIRST_DELAY)
    while not _stop.is_set():
        try:
            analyze_backlog(_stop)
        except Exception:
            log.exception("backlog pass failed (database unreachable?)")
        _stop.wait(BACKLOG_TICK_SECONDS)


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
    threading.Thread(target=_backlog_loop, daemon=True, name="backlog").start()
    from .recheck import RECHECK_DAYS
    if RECHECK_DAYS > 0:
        threading.Thread(target=_recheck_loop, daemon=True, name="recheck").start()
    log.info("worker started: %d threads; documents rechecked every %s", args.concurrency,
             f"{RECHECK_DAYS} days" if RECHECK_DAYS > 0 else "never (RECHECK_DAYS=0)")
    while not _stop.is_set():
        _stop.wait(1.0)
    log.info("stopping: finishing in-flight jobs (up to %ss)", int(TIME_BUDGET))
    for t in threads:
        t.join(timeout=TIME_BUDGET + 30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
