"""Take the app's tables away from Supabase's API roles.

Supabase gives its `anon` and `authenticated` roles full rights on everything
in the public schema, for its auto-generated REST API (PostgREST) and
supabase-js. Imbroglio uses neither: the website and the extension only talk
to our own API, and the API and worker connect straight to Postgres. Those
grants were only a way in (the project's anon key is meant to be public), so
this revokes every right those two roles have on the public schema's tables,
sequences and functions, and changes the default privileges so tables made
by later migrations don't get them either.

Each role is handled only if it exists, so on plain Postgres (CI, local
docker) this does nothing. Supabase also sets default privileges for its own
admin role, which we can't change and don't need to: our migrations create
the tables, as the role the app connects with.

Revision ID: 0015
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

# No percent signs in here (quote_ident, not format's %I): the driver would
# read them as query parameters.
UP = r"""
DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ' || quote_ident(r);
            EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM ' || quote_ident(r);
            EXECUTE 'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM ' || quote_ident(r);
            EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM ' || quote_ident(r);
            EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM ' || quote_ident(r);
            EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM ' || quote_ident(r);
        END IF;
    END LOOP;
END
$$;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    # Nothing to undo on purpose: giving the public API roles our tables back
    # would reopen the hole. If PostgREST is ever wanted, grant exactly what it
    # needs in a new migration.
    pass
