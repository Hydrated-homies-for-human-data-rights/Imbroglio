"""Migrations: a failed migration must release the migration lock.

Regression test: a failing migration once left its advisory lock held, and
every later migration attempt (both services on startup) hung forever."""

import threading
import uuid

import psycopg
import pytest

from imbroglio import db
from tests.conftest import ADMIN_DSN


@pytest.fixture
def broken_db(monkeypatch):
    name = f"imb_test_{uuid.uuid4().hex[:8]}"
    try:
        admin = psycopg.connect(ADMIN_DSN, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local Postgres not running (docker compose up -d)")
    admin.execute(f"CREATE DATABASE {name}")
    dsn = ADMIN_DSN.rsplit("/", 1)[0] + "/" + name
    # A pre-existing object that migration 0002 (CREATE TABLE, no IF NOT
    # EXISTS) collides with, so the upgrade fails partway through.
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("CREATE TABLE analysis_requests (id int)")
    monkeypatch.setenv("IMBROGLIO_DB", dsn)
    yield dsn
    admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _migrate_fresh():
    db._migrated = False
    db.migrate()


def test_failed_migration_releases_lock(broken_db):
    with pytest.raises(Exception):
        _migrate_fresh()

    # The second attempt must fail fast too, not block on a leaked lock.
    outcome = {}

    def second():
        try:
            _migrate_fresh()
            outcome["result"] = "succeeded"
        except Exception as exc:
            outcome["result"] = type(exc).__name__

    t = threading.Thread(target=second, daemon=True)
    t.start()
    t.join(timeout=30)
    assert not t.is_alive(), "second migration attempt hung: advisory lock was leaked"
    assert outcome["result"] != "succeeded"  # still broken, but reported, not stuck
    db._migrated = False
