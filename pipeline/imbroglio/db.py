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


def insert_change_event(conn: psycopg.Connection, document_id: int,
                        old_version_id: int, new_version_id: int) -> None:
    conn.execute(
        """INSERT INTO change_events (document_id, old_version_id, new_version_id, summary)
           VALUES (%s, %s, %s, %s)""",
        (document_id, old_version_id, new_version_id, "content hash changed"),
    )
