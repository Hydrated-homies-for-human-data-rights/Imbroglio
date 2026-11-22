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


API_ROLES = ("anon", "authenticated")


def test_0015_takes_the_tables_away_from_supabase_api_roles(fresh_db):
    """Supabase's anon and authenticated roles, made here the way Supabase
    sets them up (full rights, and default privileges for new tables). Roles
    belong to the whole server, so only ones this test made are dropped."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(db.MIGRATIONS))
    command.upgrade(cfg, "0014")
    admin = psycopg.connect(ADMIN_DSN, autocommit=True)
    made = []
    try:
        for role in API_ROLES:
            if admin.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone() is None:
                admin.execute(f"CREATE ROLE {role} NOLOGIN")
                made.append(role)
        with psycopg.connect(fresh_db, autocommit=True) as c:
            for role in API_ROLES:
                c.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {role}")
                c.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {role}")
                c.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {role}")
            assert c.execute("SELECT has_table_privilege('anon', 'reports', 'SELECT')").fetchone()[0]

        command.upgrade(cfg, "head")
        with psycopg.connect(fresh_db, autocommit=True) as c:
            for role in API_ROLES:
                for table in ("reports", "findings", "services"):
                    for right in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                        assert not c.execute("SELECT has_table_privilege(%s, %s, %s)",
                                             (role, table, right)).fetchone()[0], (role, table, right)
                assert not c.execute("SELECT has_sequence_privilege(%s, 'reports_id_seq', 'USAGE')",
                                     (role,)).fetchone()[0]
            c.execute("CREATE TABLE made_later (id int)")    # default privileges no longer grant it
            assert not c.execute("SELECT has_table_privilege('anon', 'made_later', 'SELECT')").fetchone()[0]
            # the app's own role keeps everything
            assert c.execute("SELECT has_table_privilege(current_user, 'reports', 'INSERT')").fetchone()[0]
    finally:
        if made:
            with psycopg.connect(fresh_db, autocommit=True) as c:
                for role in made:
                    c.execute(f"DROP OWNED BY {role}")   # its grants here, so the role can go
            for role in made:
                admin.execute(f"DROP ROLE IF EXISTS {role}")
        admin.close()


def test_0015_does_nothing_without_the_supabase_roles(fresh_db):
    """Plain Postgres (CI, local docker) has no anon or authenticated role."""
    from alembic import command
    from alembic.config import Config

    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        if admin.execute("SELECT 1 FROM pg_roles WHERE rolname = ANY(%s)", (list(API_ROLES),)).fetchone():
            pytest.skip("this server has a Supabase API role")
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(db.MIGRATIONS))
    command.upgrade(cfg, "head")
    with psycopg.connect(fresh_db) as c:
        current = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert current == ScriptDirectory.from_config(cfg).get_current_head()
