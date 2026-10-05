"""Alembic environment.

Connection string comes from the same variables the app uses (IMBROGLIO_DB,
DATABASE_URL, local docker default). Migrations run under a Postgres
advisory lock so the web and worker services can both migrate on startup
without racing each other.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, text

from imbroglio.db import database_url

MIGRATION_LOCK = 727_001  # arbitrary, fixed advisory-lock key


def _sqlalchemy_url(dsn: str) -> str:
    # psycopg 3 driver; plain postgres:// URLs default to psycopg2 in SQLAlchemy.
    for prefix in ("postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return "postgresql+psycopg://" + dsn[len(prefix):]
    return dsn


def run_migrations_online() -> None:
    engine = create_engine(
        _sqlalchemy_url(database_url()),
        # Supabase's pooler can't hold server-side prepared statements.
        connect_args={"prepare_threshold": None, "connect_timeout": 10},
    )
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK})
        try:
            context.configure(connection=connection, target_metadata=None,
                              transaction_per_migration=True)
            with context.begin_transaction():
                context.run_migrations()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK})
            connection.commit()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline (SQL script) mode is not supported; run against a database")
run_migrations_online()
