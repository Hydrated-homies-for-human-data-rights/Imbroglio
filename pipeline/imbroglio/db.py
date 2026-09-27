"""Postgres storage layer.

Connection string from IMBROGLIO_DB env var, defaulting to the local
docker-compose instance. Production (Neon) is the same code with a different
DSN — that's the whole point of keeping this layer thin.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

DEFAULT_DSN = "postgresql://imbroglio:imbroglio@localhost:5432/imbroglio"
SCHEMA = Path(__file__).parent / "schema.sql"


def connect(dsn: str | None = None) -> psycopg.Connection:
    return psycopg.connect(dsn or os.environ.get("IMBROGLIO_DB", DEFAULT_DSN))


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()


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
