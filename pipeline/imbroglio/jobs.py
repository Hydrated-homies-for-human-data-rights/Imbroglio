"""Analysis request queue (Postgres-backed jobs).

    enqueue()  — add a domain, or bump priority if it's already open
    claim()    — a worker takes the highest-priority job, safely
    progress() — worker heartbeat + one line of live log
    finish()   — mark done / failed with a result summary
    get()      — clients poll a request by id

Claiming uses FOR UPDATE SKIP LOCKED, so any number of worker threads or
processes can pull from the same table without taking the same job. A job
whose worker died (redeploy, OOM kill) stops heart-beating and is reclaimed
after STALE_AFTER; after MAX_ATTEMPTS it is marked failed instead.
"""

from __future__ import annotations

import json

import psycopg

STALE_AFTER = "5 minutes"
MAX_ATTEMPTS = 3
PROGRESS_KEEP = 200  # cap log lines per request


def enqueue(conn: psycopg.Connection, domain: str, source: str = "web",
            use_playwright: bool = True) -> tuple[int, str, bool]:
    """Returns (request_id, status, created). An open request for the same
    domain is reused (request_count += 1) instead of queueing a duplicate."""
    row = conn.execute(
        """INSERT INTO analysis_requests (domain, source, use_playwright)
           VALUES (%s, %s, %s)
           ON CONFLICT (domain) WHERE status IN ('queued', 'running')
           DO UPDATE SET request_count = analysis_requests.request_count + 1
           RETURNING id, status, (xmax = 0) AS created""",
        (domain, source, use_playwright),
    ).fetchone()
    conn.commit()
    return row[0], row[1], row[2]


def claim(conn: psycopg.Connection, worker_id: str) -> tuple[int, str, bool] | None:
    """Take the next job: open requests by priority (request_count, then age),
    including running jobs whose worker went silent. Returns
    (request_id, domain, use_playwright) or None."""
    # Give up on jobs that keep killing their worker.
    conn.execute(
        f"""UPDATE analysis_requests
            SET status = 'failed', finished_at = now(),
                error = 'abandoned: worker stopped responding {MAX_ATTEMPTS} times'
            WHERE status = 'running' AND heartbeat_at < now() - interval '{STALE_AFTER}'
              AND attempts >= %s""",
        (MAX_ATTEMPTS,),
    )
    row = conn.execute(
        f"""UPDATE analysis_requests r
            SET status = 'running', attempts = r.attempts + 1, worker_id = %s,
                started_at = now(), heartbeat_at = now(), stage = 'starting',
                progress = '[]'::jsonb
            WHERE r.id = (
                SELECT id FROM analysis_requests
                WHERE status = 'queued'
                   OR (status = 'running' AND heartbeat_at < now() - interval '{STALE_AFTER}')
                ORDER BY request_count DESC, requested_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1)
            RETURNING r.id, r.domain, r.use_playwright""",
        (worker_id,),
    ).fetchone()
    conn.commit()
    return row


def progress(conn: psycopg.Connection, request_id: int, line: str) -> None:
    """Heartbeat + append one log line (also becomes the current stage)."""
    conn.execute(
        """UPDATE analysis_requests
           SET heartbeat_at = now(), stage = left(%s, 300),
               progress = CASE WHEN jsonb_array_length(progress) >= %s THEN progress
                               ELSE progress || to_jsonb(left(%s, 500)) END
           WHERE id = %s AND status = 'running'""",
        (line, PROGRESS_KEEP, line, request_id),
    )
    conn.commit()


def finish(conn: psycopg.Connection, request_id: int, ok: bool,
           result: dict | None = None, error: str | None = None) -> None:
    conn.execute(
        """UPDATE analysis_requests
           SET status = %s, finished_at = now(), heartbeat_at = now(),
               stage = %s, result = %s, error = %s
           WHERE id = %s""",
        ("done" if ok else "failed", "done" if ok else "failed",
         json.dumps(result) if result is not None else None, error, request_id),
    )
    conn.commit()


def get(conn: psycopg.Connection, request_id: int) -> dict | None:
    row = conn.execute(
        """SELECT id, domain, status, stage, progress, result, error, request_count,
                  requested_at, started_at, finished_at,
                  (SELECT count(*) FROM analysis_requests q
                   WHERE q.status = 'queued' AND q.requested_at < r.requested_at) AS ahead
           FROM analysis_requests r WHERE id = %s""",
        (request_id,),
    ).fetchone()
    if row is None:
        return None
    keys = ["id", "domain", "status", "stage", "progress", "result", "error",
            "request_count", "requested_at", "started_at", "finished_at", "queue_ahead"]
    d = dict(zip(keys, row))
    for k in ("requested_at", "started_at", "finished_at"):
        d[k] = d[k].isoformat() if d[k] else None
    if d["status"] != "queued":
        d["queue_ahead"] = 0
    return d


def stats(conn: psycopg.Connection) -> dict:
    return dict(conn.execute(
        "SELECT status, count(*) FROM analysis_requests GROUP BY status").fetchall())


def overview(conn: psycopg.Connection, open_limit: int = 50, recent_limit: int = 10) -> dict:
    """Open jobs (running first, then in claim order) and the latest finished
    ones, for a live queue view."""
    cols = ["id", "domain", "status", "stage", "source", "request_count", "attempts",
            "requested_at", "started_at", "finished_at", "error", "found"]

    def rows(sql: str, limit: int) -> list[dict]:
        out = []
        for r in conn.execute(sql, (limit,)).fetchall():
            d = dict(zip(cols, r))
            for k in ("requested_at", "started_at", "finished_at"):
                d[k] = d[k].isoformat() if d[k] else None
            out.append(d)
        return out

    select = """SELECT id, domain, status, stage, source, request_count, attempts,
                       requested_at, started_at, finished_at, error,
                       (SELECT array_agg(x->>'doc_type') FROM jsonb_array_elements(result->'documents') x
                        WHERE (x->>'found')::boolean) AS found
                FROM analysis_requests"""
    return {
        "counts": stats(conn),
        "open": rows(select + """ WHERE status IN ('queued', 'running')
                     ORDER BY status = 'running' DESC, request_count DESC, requested_at
                     LIMIT %s""", open_limit),
        "recent": rows(select + """ WHERE status IN ('done', 'failed')
                       ORDER BY finished_at DESC LIMIT %s""", recent_limit),
    }
