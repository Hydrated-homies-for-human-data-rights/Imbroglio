"""Shared fixtures. `conn` gives a migrated, empty throwaway Postgres
database on the local docker-compose server (tests skip if it isn't running)."""

import uuid

import psycopg
import pytest

from imbroglio import db

ADMIN_DSN = "postgresql://imbroglio:imbroglio@localhost:5432/imbroglio"


@pytest.fixture(scope="module")
def test_dsn():
    name = f"imb_test_{uuid.uuid4().hex[:8]}"
    try:
        admin = psycopg.connect(ADMIN_DSN, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local Postgres not running (docker compose up -d)")
    admin.execute(f"CREATE DATABASE {name}")
    dsn = ADMIN_DSN.rsplit("/", 1)[0] + "/" + name
    yield dsn
    admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


@pytest.fixture
def conn(test_dsn, monkeypatch):
    monkeypatch.setenv("IMBROGLIO_DB", test_dsn)
    monkeypatch.setattr(db, "_migrated", False)
    db.migrate()
    c = db.connect()
    c.execute("""TRUNCATE analysis_requests, crawl_attempts, change_events, document_versions,
                 documents, services RESTART IDENTITY CASCADE""")
    c.commit()
    yield c
    c.close()


