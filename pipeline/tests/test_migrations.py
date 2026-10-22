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


@pytest.fixture
def fresh_db(monkeypatch):
    name = f"imb_test_{uuid.uuid4().hex[:8]}"
    try:
        admin = psycopg.connect(ADMIN_DSN, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local Postgres not running (docker compose up -d)")
    admin.execute(f"CREATE DATABASE {name}")
    dsn = ADMIN_DSN.rsplit("/", 1)[0] + "/" + name
    monkeypatch.setenv("IMBROGLIO_DB", dsn)
    yield dsn
    db._migrated = False
    admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def test_0006_replaces_near_miss_quotes_with_document_text(fresh_db):
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(db.MIGRATIONS))
    command.upgrade(cfg, "0005")
    text = ("You grant us a non-exclusive, transferable, sub-licensable, royalty-free, and worldwide license "
            "to host, use, distribute, modify, run, copy, publicly perform or display, translate.")
    typo = ("you grant us a non-exclusive, transferable, sub-licensable, royalty-free, and worldwide license "
            "to host, use, distribute, modify, run, copy, publly perform or display")
    with psycopg.connect(fresh_db) as c:
        sid = c.execute("INSERT INTO services (domain) VALUES ('fb.example') RETURNING id").fetchone()[0]
        did = c.execute("INSERT INTO documents (service_id, doc_type, url) VALUES (%s, 'terms', 'https://fb.example/t') "
                        "RETURNING id", (sid,)).fetchone()[0]
        vid = c.execute("INSERT INTO document_versions (document_id, content_hash, normalized_text, fetch_method) "
                        "VALUES (%s, 'h', %s, 'static') RETURNING id", (did, text)).fetchone()[0]
        for check, quotes, flags in [("content_license", [typo, "made up words that are nowhere"], [True, False])]:
            c.execute("""INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                               quotes_verified, verified, model)
                         VALUES (%s, 'v0.1', %s, 'ai_training', 'broad', %s, %s, true, 'm')""", (vid, check, quotes, flags))
    command.upgrade(cfg, "head")
    with psycopg.connect(fresh_db) as c:
        quotes = c.execute("SELECT quotes FROM findings").fetchone()[0]
    assert quotes[0].startswith("You grant us") and "publicly perform" in quotes[0]
    assert quotes[1] == "made up words that are nowhere"      # unverified quotes are left alone
