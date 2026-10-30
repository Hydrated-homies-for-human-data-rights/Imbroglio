"""Postgres storage layer.

Connection string from IMBROGLIO_DB (or DATABASE_URL, the name hosting
platforms use), defaulting to the local docker-compose instance. Production
(Supabase) is the same code with a different DSN — that's the whole point of
keeping this layer thin.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import psycopg

DEFAULT_DSN = "postgresql://imbroglio:imbroglio@localhost:5432/imbroglio"
MIGRATIONS = Path(__file__).parent / "migrations"


def database_url() -> str:
    return os.environ.get("IMBROGLIO_DB") or os.environ.get("DATABASE_URL") or DEFAULT_DSN


def connect(dsn: str | None = None) -> psycopg.Connection:
    # prepare_threshold=None: Supabase's connection pooler (PgBouncer-style)
    # can hand consecutive statements to different backends, which breaks
    # server-side prepared statements. connect_timeout keeps a dead database
    # from hanging requests for half a minute.
    return psycopg.connect(dsn or database_url(), prepare_threshold=None, connect_timeout=5)


_migrated = False
_migrate_lock = threading.Lock()


def migrate() -> None:
    """Apply pending Alembic migrations (once per process). Safe to call from
    several processes at once: env.py serializes them with an advisory lock."""
    global _migrated
    with _migrate_lock:
        if _migrated:
            return
        from alembic import command
        from alembic.config import Config

        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS))
        command.upgrade(cfg, "head")
        _migrated = True


def init_schema(conn: psycopg.Connection | None = None) -> None:
    """Kept for existing callers: ensures the schema is current. The schema
    itself now lives in migrations/ (Alembic), not in a SQL file."""
    migrate()


def upsert_service(conn: psycopg.Connection, domain: str) -> int:
    row = conn.execute(
        """INSERT INTO services (domain) VALUES (%s)
           ON CONFLICT (domain) DO UPDATE SET domain = EXCLUDED.domain
           RETURNING id""",
        (domain,),
    ).fetchone()
    return row[0]


def upsert_document(conn: psycopg.Connection, service_id: int, doc_type: str,
                    url: str, discovered_via: str | None) -> int:
    row = conn.execute(
        """INSERT INTO documents (service_id, doc_type, url, discovered_via)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (service_id, doc_type)
           DO UPDATE SET url = EXCLUDED.url, discovered_via = EXCLUDED.discovered_via
           RETURNING id""",
        (service_id, doc_type, url, discovered_via),
    ).fetchone()
    return row[0]


def latest_version(conn: psycopg.Connection, document_id: int) -> tuple[int, str] | None:
    """Returns (version_id, content_hash) of the newest stored version."""
    return conn.execute(
        """SELECT id, content_hash FROM document_versions
           WHERE document_id = %s ORDER BY fetched_at DESC LIMIT 1""",
        (document_id,),
    ).fetchone()


def insert_version(conn: psycopg.Connection, document_id: int, content_hash: str,
                   normalized_text: str, fetch_method: str | None) -> int:
    """Insert a new version; returns existing id if this exact content is
    already stored (same document, same hash)."""
    row = conn.execute(
        """INSERT INTO document_versions
               (document_id, content_hash, normalized_text, fetch_method)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (document_id, content_hash) DO NOTHING
           RETURNING id""",
        (document_id, content_hash, normalized_text, fetch_method),
    ).fetchone()
    if row:
        return row[0]
    return conn.execute(
        "SELECT id FROM document_versions WHERE document_id = %s AND content_hash = %s",
        (document_id, content_hash),
    ).fetchone()[0]


def list_services(conn: psycopg.Connection) -> list[tuple]:
    """One row per (service, document): domain, doc_type, url, version count,
    change count, newest fetch time. Services with no documents yet appear
    with doc_type NULL."""
    return conn.execute(
        """SELECT s.domain, d.doc_type, d.url,
                  count(DISTINCT v.id)  AS versions,
                  count(DISTINCT c.id)  AS changes,
                  max(v.fetched_at)     AS last_fetched
           FROM services s
           LEFT JOIN documents d         ON d.service_id = s.id
           LEFT JOIN document_versions v ON v.document_id = d.id
           LEFT JOIN change_events c     ON c.document_id = d.id
           GROUP BY s.domain, d.doc_type, d.url
           ORDER BY s.domain, d.doc_type""",
    ).fetchall()


def service_detail(conn: psycopg.Connection, domain: str) -> list[tuple]:
    """Latest stored version of each document for one domain, full text
    included, plus a version-history count via list_services. One row per
    document: doc_type, url, discovered_via, version_id, content_hash,
    fetch_method, fetched_at, normalized_text."""
    return conn.execute(
        """SELECT d.doc_type, d.url, d.discovered_via,
                  v.id, v.content_hash, v.fetch_method, v.fetched_at, v.normalized_text
           FROM services s
           JOIN documents d ON d.service_id = s.id
           JOIN document_versions v ON v.document_id = d.id
           WHERE s.domain = %s
             AND v.fetched_at = (SELECT max(v2.fetched_at)
                                 FROM document_versions v2
                                 WHERE v2.document_id = d.id)
           ORDER BY d.doc_type""",
        (domain,),
    ).fetchall()


def version_history(conn: psycopg.Connection, domain: str) -> list[tuple]:
    """All stored versions for a domain: doc_type, version_id, content_hash,
    fetched_at — newest first."""
    return conn.execute(
        """SELECT d.doc_type, v.id, v.content_hash, v.fetched_at
           FROM services s
           JOIN documents d ON d.service_id = s.id
           JOIN document_versions v ON v.document_id = d.id
           WHERE s.domain = %s
           ORDER BY d.doc_type, v.fetched_at DESC""",
        (domain,),
    ).fetchall()


def insert_change_event(conn: psycopg.Connection, document_id: int,
                        old_version_id: int, new_version_id: int) -> None:
    conn.execute(
        """INSERT INTO change_events (document_id, old_version_id, new_version_id, summary)
           VALUES (%s, %s, %s, %s)""",
        (document_id, old_version_id, new_version_id, "content hash changed"),
    )


# --- batch runs ---------------------------------------------------------------

def create_batch(conn: psycopg.Connection, source: str, total: int, workers: int) -> int:
    return conn.execute(
        "INSERT INTO batches (source, total, workers) VALUES (%s, %s, %s) RETURNING id",
        (source, total, workers),
    ).fetchone()[0]


def finish_batch(conn: psycopg.Connection, batch_id: int) -> None:
    conn.execute("UPDATE batches SET finished_at = now() WHERE id = %s", (batch_id,))


def insert_attempt(conn: psycopg.Connection, batch_id: int | None, domain: str,
                   doc_type: str, ok: bool, status: str, url: str | None,
                   discovered_via: str | None, fetch_method: str | None,
                   chars: int, notes: str | None, seconds: float) -> None:
    conn.execute(
        """INSERT INTO crawl_attempts
               (batch_id, domain, doc_type, ok, status, url, discovered_via,
                fetch_method, chars, notes, seconds)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (batch_id, domain, doc_type, ok, status, url, discovered_via,
         fetch_method, chars, notes, seconds),
    )


def domains_with_privacy(conn: psycopg.Connection) -> set[str]:
    """Domains that already have a stored privacy policy version."""
    rows = conn.execute(
        """SELECT DISTINCT s.domain FROM services s
           JOIN documents d ON d.service_id = s.id AND d.doc_type = 'privacy'
           JOIN document_versions v ON v.document_id = d.id""",
    ).fetchall()
    return {r[0] for r in rows}


def latest_batch_id(conn: psycopg.Connection) -> int | None:
    row = conn.execute("SELECT max(id) FROM batches").fetchone()
    return row[0] if row else None


def get_batch(conn: psycopg.Connection, batch_id: int) -> tuple:
    """(source, total, workers, started_at, finished_at)"""
    return conn.execute(
        "SELECT source, total, workers, started_at, finished_at FROM batches WHERE id = %s",
        (batch_id,),
    ).fetchone()


def batch_attempts(conn: psycopg.Connection, batch_id: int) -> list[tuple]:
    """(domain, doc_type, ok, status, url, discovered_via, fetch_method,
    chars, notes, seconds) for every attempt in a batch."""
    return conn.execute(
        """SELECT domain, doc_type, ok, status, url, discovered_via, fetch_method,
                  chars, notes, seconds
           FROM crawl_attempts WHERE batch_id = %s ORDER BY domain, doc_type""",
        (batch_id,),
    ).fetchall()


# --- audit (human review of discovery results) --------------------------------

# Latest attempt per (domain, doc_type). Excluded: pipeline errors and hosts we
# couldn't connect to at all — neither says anything about discovery quality,
# and a reviewer can't verify an unreachable site (batch reports count those
# separately).
_LATEST_ATTEMPTS = """
    SELECT * FROM (
        SELECT DISTINCT ON (domain, doc_type)
               id, domain, doc_type, ok, status, url, discovered_via, fetch_method, chars, notes
        FROM crawl_attempts
        WHERE status <> 'error'
        ORDER BY domain, doc_type, attempted_at DESC
    ) latest_per_doc
    WHERE coalesce(notes, '') NOT LIKE '%%host unreachable%%'
"""


def audit_next(conn: psycopg.Connection, kind: str, skip: list[int]) -> tuple | None:
    """One unreviewed attempt. kind: 'found' | 'missed' | 'all'. Order is a
    stable pseudo-random shuffle so reviewers see a representative mix rather
    than alphabetical order. Returns (id, domain, doc_type, ok, status, url,
    discovered_via, fetch_method, chars, notes) or None."""
    return conn.execute(
        f"""WITH latest AS ({_LATEST_ATTEMPTS})
            SELECT l.* FROM latest l
            WHERE NOT EXISTS (SELECT 1 FROM audit_labels a
                              WHERE a.domain = l.domain AND a.doc_type = l.doc_type)
              AND (%(kind)s = 'all' OR (%(kind)s = 'found' AND l.ok)
                   OR (%(kind)s = 'missed' AND NOT l.ok))
              AND NOT (l.id = ANY(%(skip)s))
            ORDER BY md5(l.domain || l.doc_type)
            LIMIT 1""",
        {"kind": kind, "skip": skip},
    ).fetchone()


def latest_text(conn: psycopg.Connection, domain: str, doc_type: str) -> str | None:
    row = conn.execute(
        """SELECT v.normalized_text FROM services s
           JOIN documents d ON d.service_id = s.id AND d.doc_type = %s
           JOIN document_versions v ON v.document_id = d.id
           WHERE s.domain = %s ORDER BY v.fetched_at DESC LIMIT 1""",
        (doc_type, domain),
    ).fetchone()
    return row[0] if row else None


def audit_save(conn: psycopg.Connection, attempt_id: int, verdict: str,
               correct_url: str | None, note: str | None, reviewer: str | None) -> bool:
    """Record a verdict against an attempt. Domain/doc_type/outcome are taken
    from the attempt row, not the client. Returns False if the attempt is gone."""
    row = conn.execute(
        """INSERT INTO audit_labels (attempt_id, domain, doc_type, outcome, verdict,
                                     correct_url, note, reviewer)
           SELECT id, domain, doc_type, CASE WHEN ok THEN 'found' ELSE 'missed' END,
                  %s, %s, %s, %s
           FROM crawl_attempts WHERE id = %s
           RETURNING id""",
        (verdict, correct_url, note, reviewer, attempt_id),
    ).fetchone()
    return row is not None


def audit_counts(conn: psycopg.Connection) -> dict:
    """Totals of latest attempts by outcome, plus reviewed verdict counts."""
    totals = dict(conn.execute(
        f"""SELECT CASE WHEN ok THEN 'found' ELSE 'missed' END, count(*)
            FROM ({_LATEST_ATTEMPTS}) l GROUP BY 1""").fetchall())
    verdicts = conn.execute(
        """SELECT DISTINCT ON (domain, doc_type) outcome, verdict
           FROM audit_labels ORDER BY domain, doc_type, created_at DESC""").fetchall()
    counts: dict[str, int] = {}
    for outcome, verdict in verdicts:
        counts[f"{outcome}:{verdict}"] = counts.get(f"{outcome}:{verdict}", 0) + 1
    return {"totals": totals, "verdicts": counts}


def site_findings(conn: psycopg.Connection, rubric_version: str,
                  hash_like: str | None = None) -> dict[str, list[tuple]]:
    """domain -> (domain_hash, check_id, status, verified, created_at) for
    every finding on the latest version of each of the site's documents. Only
    analyzed sites appear. `hash_like` narrows it to a domain_hash pattern."""
    rows = conn.execute(
        f"""WITH latest AS (
                SELECT DISTINCT ON (d.id) s.domain, s.domain_hash, v.id AS version_id
                FROM documents d JOIN services s ON s.id = d.service_id
                JOIN document_versions v ON v.document_id = d.id
                {"WHERE s.domain_hash LIKE %(hash)s" if hash_like else ""}
                ORDER BY d.id, v.fetched_at DESC)
            SELECT l.domain, l.domain_hash, f.check_id, f.status, f.verified, f.created_at
            FROM latest l JOIN findings f ON f.version_id = l.version_id
            WHERE f.rubric_version = %(rubric)s""",
        {"rubric": rubric_version, "hash": hash_like},
    ).fetchall()
    out: dict[str, list[tuple]] = {}
    for domain, *rest in rows:
        out.setdefault(domain, []).append(tuple(rest))
    return out


def headlines(conn: psycopg.Connection, rubric_version: str) -> dict[str, str]:
    """domain -> headline rating across the site's latest analyzed documents,
    for list views. The same scorer.rate the scorecard uses."""
    from . import scorer
    from .rubric import load

    rubric = load(rubric_version)
    return {domain: scorer.rate(rubric, [scorer.ScoredFinding(c, s, v) for _, c, s, v, _ in rows])[1]
            for domain, rows in site_findings(conn, rubric_version).items()}


def offsite_documents(conn: psycopg.Connection) -> list[tuple]:
    """(document_id, domain, doc_type, url, analyzed) for every stored document
    hosted on another site whose latest text never names this one: the rule
    discovery applies to other sites' documents (locate.names_site), checked
    against documents stored before it covered links found on those sites'
    own pages (keepassxc.org stored GitHub's terms, liberapay.com PayPal's)."""
    from urllib.parse import urlparse

    from .locate import names_site, site_of

    rows = conn.execute(
        """SELECT DISTINCT ON (d.id) d.id, s.domain, d.doc_type, d.url, v.normalized_text,
                  EXISTS (SELECT 1 FROM findings f JOIN document_versions v2 ON v2.id = f.version_id
                          WHERE v2.document_id = d.id)
           FROM documents d JOIN services s ON s.id = d.service_id
           JOIN document_versions v ON v.document_id = d.id
           ORDER BY d.id, v.fetched_at DESC""").fetchall()
    return [(doc_id, domain, doc_type, url, analyzed)
            for doc_id, domain, doc_type, url, text, analyzed in rows
            if site_of(urlparse(url).hostname or "") != site_of(domain) and not names_site(domain, text)]
