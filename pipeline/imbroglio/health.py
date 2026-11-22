"""How the request queue, the worker and the analysis budget are doing, for
the health watch (.github/workflows/health.yml, through GET /v1/health).

Counts and times only: never which sites anyone asked about. `snapshot`
reads the numbers; `problems` turns them into plain sentences, one per thing
a person should look at. The thresholds are generous on purpose: a post to
Discord should mean something is really wrong, not that the queue is busy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import psycopg

from . import analysis

VISITOR_WAIT_MINUTES = 20      # a visitor's request still waiting this long
STALL_MINUTES = 30             # work waiting, nothing finished this long
STALE_RUNNING_MINUTES = 15     # a running job with no heartbeat this long
FAILED_PER_DAY = 5             # jobs that failed outright in 24 hours
RECHECK_STALE_HOURS = 26       # the hourly recheck pass hasn't recorded anything
# ...while documents have been due this long. A quiet day with nothing due
# is normal (every document checked within RECHECK_DAYS), not a stop. Two
# hours is two hourly passes, so a document that just came due doesn't count.
RECHECK_OVERDUE_HOURS = 2


@dataclass
class Snapshot:
    checked_at: str
    queued: int
    running: int
    visitor_queued: int
    oldest_visitor_wait_minutes: float | None
    oldest_wait_minutes: float | None
    finished_last_hour: int
    minutes_since_last_finish: float | None
    stale_running: int
    failed_24h: int
    spent_24h_usd: float
    budget_usd: float
    hours_since_last_recheck: float | None
    overdue_rechecks: int = 0      # documents due for RECHECK_OVERDUE_HOURS+ hours


def _minutes(td) -> float | None:
    return None if td is None else round(td.total_seconds() / 60, 1)


def snapshot(conn: psycopg.Connection, public_sources: tuple[str, ...]) -> Snapshot:
    """`public_sources`: the request sources that are visitors (api.PUBLIC_SOURCES)."""
    q = conn.execute(
        """SELECT
             count(*) FILTER (WHERE status = 'queued'),
             count(*) FILTER (WHERE status = 'running'),
             count(*) FILTER (WHERE status = 'queued' AND source = ANY(%(public)s)),
             now() - min(requested_at) FILTER (WHERE status = 'queued' AND source = ANY(%(public)s)),
             now() - min(requested_at) FILTER (WHERE status = 'queued'),
             count(*) FILTER (WHERE status IN ('done', 'failed')
                              AND finished_at > now() - interval '1 hour'),
             now() - max(finished_at),
             count(*) FILTER (WHERE status = 'running'
                              AND heartbeat_at < now() - make_interval(mins => %(stale)s)),
             count(*) FILTER (WHERE status = 'failed' AND finished_at > now() - interval '24 hours')
           FROM analysis_requests""",
        {"public": list(public_sources), "stale": STALE_RUNNING_MINUTES}).fetchone()
    last_check = conn.execute("SELECT now() - max(checked_at) FROM document_checks").fetchone()[0]
    overdue = 0
    from .recheck import RECHECK_DAYS, due
    if RECHECK_DAYS > 0:  # 0 turns rechecks off, so nothing is ever overdue
        overdue = len(due(conn, RECHECK_DAYS, grace_hours=RECHECK_OVERDUE_HOURS))
    return Snapshot(
        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        queued=q[0], running=q[1], visitor_queued=q[2],
        oldest_visitor_wait_minutes=_minutes(q[3]), oldest_wait_minutes=_minutes(q[4]),
        finished_last_hour=q[5], minutes_since_last_finish=_minutes(q[6]),
        stale_running=q[7], failed_24h=q[8],
        spent_24h_usd=round(analysis.spent_last_24h(conn), 2), budget_usd=analysis.DAILY_BUDGET_USD,
        hours_since_last_recheck=None if last_check is None else round(last_check.total_seconds() / 3600, 1),
        overdue_rechecks=overdue,
    )


def problems(s: Snapshot) -> list[str]:
    out = []
    if s.oldest_visitor_wait_minutes is not None and s.oldest_visitor_wait_minutes > VISITOR_WAIT_MINUTES:
        out.append(f"A visitor's request has waited {s.oldest_visitor_wait_minutes:.0f} minutes "
                   f"({s.visitor_queued} visitor requests queued).")
    work_waiting = s.queued > 0
    idle = s.minutes_since_last_finish is None or s.minutes_since_last_finish > STALL_MINUTES
    if work_waiting and idle and s.running == 0:
        out.append(f"The worker looks stopped: {s.queued} jobs queued, none running, and nothing has "
                   f"finished in {STALL_MINUTES}+ minutes.")
    if s.stale_running:
        out.append(f"{s.stale_running} running job(s) stopped sending heartbeats "
                   f"{STALE_RUNNING_MINUTES}+ minutes ago (worker crashed or redeploying?).")
    if s.failed_24h >= FAILED_PER_DAY:
        out.append(f"{s.failed_24h} jobs failed outright in the last 24 hours.")
    if s.budget_usd and s.spent_24h_usd >= s.budget_usd:
        out.append(f"The analysis budget is used up: ${s.spent_24h_usd:.2f} of ${s.budget_usd:.2f} in "
                   "24 hours. New sites are crawled but wait for analysis.")
    quiet = s.hours_since_last_recheck is None or s.hours_since_last_recheck > RECHECK_STALE_HOURS
    if quiet and s.overdue_rechecks:
        since = ("ever" if s.hours_since_last_recheck is None
                 else f"in {s.hours_since_last_recheck:.0f} hours")
        out.append(f"Rechecks look stopped: {s.overdue_rechecks} document(s) are overdue and no "
                   f"policy recheck was recorded {since}.")
    return out


def report(conn: psycopg.Connection, public_sources: tuple[str, ...]) -> dict:
    s = snapshot(conn, public_sources)
    found = problems(s)
    return {"ok": not found, "problems": found, **asdict(s)}
