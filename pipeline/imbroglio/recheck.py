"""Rechecks: fetch each stored document again at its stored address and
record whether its text changed. Detect-only: nothing is rated here, so a
recheck costs no model calls. A changed document gets a new version and a
change event; ratings keep coming from the newest version that has been
rated (db.site_findings, api._documents) until someone rates the new one
(`cli extract --all`).

    python -m imbroglio.cli recheck                    # everything not checked in RECHECK_DAYS
    python -m imbroglio.cli recheck --every-days 0 --domain steampowered.com
    python -m imbroglio.cli recheck --dry-run --limit 20

The worker service also runs it on its own (worker.py): once an hour it
checks up to RECHECK_BATCH documents that are due. RECHECK_DAYS sets how
often each document comes due: 7 is weekly, 30 monthly, 0 turns it off.

Every check is logged in document_checks, which gives the false-change
rate the proposal sets a bar for (no more than one per 100 checks): audit
the "changed" rows by hand against their diffs.
"""

from __future__ import annotations

import difflib
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests

from . import db
from .extract import extract_text
from .fetch import fetch_rendered
from .locate import _try_url, _validate, is_challenge
from .normalize import content_hash, normalize

log = logging.getLogger(__name__)

RECHECK_DAYS = int(os.environ.get("RECHECK_DAYS", "7"))
RECHECK_BATCH = int(os.environ.get("RECHECK_BATCH", "100"))


@dataclass
class Check:
    document_id: int
    domain: str
    doc_type: str
    url: str
    outcome: str = "failed"        # unchanged | changed | reverted | failed
    version_id: int | None = None
    note: str = ""


def due(conn, every_days: int, limit: int | None = None,
        domains: list[str] | None = None) -> list[tuple[int, str, str, str]]:
    """(document_id, domain, doc_type, url) for documents neither fetched nor
    checked in the last `every_days` days, longest-waiting first. Documents
    stored by hand (fetch_method 'manual') are left out: they were stored
    that way because the crawler can't fetch them."""
    return conn.execute(
        f"""SELECT d.id, s.domain, d.doc_type, d.url
            FROM documents d
            JOIN services s ON s.id = d.service_id
            JOIN LATERAL (SELECT fetched_at, fetch_method FROM document_versions v
                          WHERE v.document_id = d.id
                          ORDER BY v.fetched_at DESC LIMIT 1) v ON true
            LEFT JOIN LATERAL (SELECT max(checked_at) AS at FROM document_checks c
                               WHERE c.document_id = d.id) c ON true
            WHERE coalesce(v.fetch_method, '') <> 'manual'
              AND greatest(v.fetched_at, c.at) <= now() - make_interval(days => %(days)s)
              {"AND s.domain = ANY(%(domains)s)" if domains else ""}
            ORDER BY greatest(v.fetched_at, c.at), d.id
            {"LIMIT %(limit)s" if limit else ""}""",
        {"days": every_days, "domains": domains, "limit": limit},
    ).fetchall()


def _fetch(url: str, doc_type: str, session: requests.Session,
           use_playwright: bool) -> tuple[str | None, str]:
    """(normalized text, fetch method), or (None, why it failed). The same
    fetch, extraction and checks discovery uses, so an unchanged page gives
    the same text it gave when it was stored."""
    html, text, status, method = _try_url(url, doc_type, session, use_playwright)
    if html is not None and is_challenge(html) and method == "static" and use_playwright:
        # A bot check served to the plain request (16 of 200 in the Nov 17
        # trial) often lets a real browser through, as it did at discovery.
        rendered, _ = fetch_rendered(url)
        if rendered is not None and not is_challenge(rendered):
            html, text, method = rendered, extract_text(rendered), "playwright"
    if html is None:
        return None, f"fetch failed ({status})"
    if is_challenge(html):
        return None, "blocked: bot challenge"
    ok, reason = _validate(doc_type, text)
    if not ok:
        return None, reason
    return normalize(text), method


def _diff_note(old: str, new: str) -> str:
    added = removed = 0
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return f"{len(old):,} -> {len(new):,} chars, +{added} -{removed} lines"


def check_one(conn, row: tuple[int, str, str, str], session: requests.Session,
              use_playwright: bool = True, dry_run: bool = False) -> Check:
    """Fetch one document again and record what came back. Commits unless
    dry_run, which changes nothing in the database."""
    doc_id, domain, doc_type, url = row
    check = Check(doc_id, domain, doc_type, url)
    text, how = _fetch(url, doc_type, session, use_playwright)
    if text is None:
        check.note = how
    else:
        digest = content_hash(text)
        latest_id, latest_hash, latest_text = conn.execute(
            """SELECT id, content_hash, normalized_text FROM document_versions
               WHERE document_id = %s ORDER BY fetched_at DESC LIMIT 1""", (doc_id,)).fetchone()
        older = conn.execute(
            "SELECT id FROM document_versions WHERE document_id = %s AND content_hash = %s",
            (doc_id, digest)).fetchone()
        if digest == latest_hash:
            check.outcome, check.version_id = "unchanged", latest_id
        elif older is not None:
            # The text went back to an earlier version. An A/B test or a
            # rotating block flips like this; a real policy rarely does.
            # No change event: the audit counts these separately.
            check.outcome, check.version_id = "reverted", older[0]
            check.note = f"same as stored version {older[0]}; {_diff_note(latest_text, text)}"
        else:
            check.outcome = "changed"
            check.note = _diff_note(latest_text, text)
            if not dry_run:
                check.version_id = db.insert_version(conn, doc_id, digest, text, how)
                db.insert_change_event(conn, doc_id, latest_id, check.version_id)
    if not dry_run:
        conn.execute(
            """INSERT INTO document_checks (document_id, outcome, version_id, note)
               VALUES (%s, %s, %s, %s)""",
            (doc_id, check.outcome, check.version_id, check.note[:2000]))
        conn.commit()
    log.info("recheck %s %s: %s %s", domain, doc_type, check.outcome, check.note)
    return check


def run(rows: list[tuple[int, str, str, str]], workers: int = 2, use_playwright: bool = True,
        dry_run: bool = False, stop: threading.Event | None = None) -> list[Check]:
    """Check each row, `workers` at a time. `stop` (the worker's shutdown
    signal) ends the run between documents."""
    local = threading.local()
    opened, opened_lock = [], threading.Lock()

    def one(row) -> Check | None:
        if stop is not None and stop.is_set():
            return None
        if not hasattr(local, "conn"):  # one connection and session per thread
            local.conn, local.session = db.connect(), requests.Session()
            with opened_lock:
                opened.append(local.conn)
        try:
            return check_one(local.conn, row, local.session, use_playwright, dry_run)
        except Exception as exc:  # one bad page never ends the run
            local.conn.rollback()
            log.exception("recheck %s %s failed", row[1], row[2])
            failed = Check(row[0], row[1], row[2], row[3], note=f"error: {type(exc).__name__}")
            if not dry_run:  # logged, so the document isn't retried every hour
                local.conn.execute(
                    "INSERT INTO document_checks (document_id, outcome, note) VALUES (%s, 'failed', %s)",
                    (failed.document_id, failed.note))
                local.conn.commit()
            return failed

    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            return [c for c in pool.map(one, rows) if c is not None]
    finally:
        for conn in opened:
            conn.close()


def summary(checks: list[Check]) -> dict[str, int]:
    out = {"checked": len(checks), "unchanged": 0, "changed": 0, "reverted": 0, "failed": 0}
    for c in checks:
        out[c.outcome] += 1
    return out


# Any number works as long as nothing else uses it; it keeps two worker
# replicas (or a redeploy overlapping the old container) from checking the
# same documents at once.
_LOCK_KEY = 0x1B0C_0010


def scheduled_tick(stop: threading.Event | None = None) -> dict[str, int] | None:
    """One pass of the worker's schedule: check up to RECHECK_BATCH due
    documents. Returns the summary, or None when turned off or when another
    process holds the lock."""
    if RECHECK_DAYS <= 0:
        return None
    conn = db.connect()
    try:
        if not conn.execute("SELECT pg_try_advisory_lock(%s)", (_LOCK_KEY,)).fetchone()[0]:
            return None
        try:
            rows = due(conn, RECHECK_DAYS, RECHECK_BATCH)
            conn.commit()
            if not rows:
                return summary([])
            # one at a time: the worker's browser slot is shared with
            # visitors' requests, which come first
            result = summary(run(rows, workers=1, stop=stop))
            log.info("recheck: %s", result)
            return result
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
            conn.commit()
    finally:
        conn.close()
