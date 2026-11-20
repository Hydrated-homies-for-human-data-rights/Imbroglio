"""A random public id for each analysis request.

The serial id counts up, so anyone could walk GET /v1/requests/{id} and list
every domain other people asked about. The API now names requests only by
public_id, a random UUID nobody can guess; the serial id stays internal (the
worker and the queue still use it).

The default is volatile, so adding the column gives every existing row its
own value, and every insert path (visitor requests, batch imports) gets one
without passing it.

Revision ID: 0011
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

UP = r"""
ALTER TABLE analysis_requests
    ADD COLUMN public_id UUID NOT NULL DEFAULT gen_random_uuid();

CREATE UNIQUE INDEX uq_requests_public_id ON analysis_requests (public_id);
"""

DOWN = """
DROP INDEX IF EXISTS uq_requests_public_id;
ALTER TABLE analysis_requests DROP COLUMN IF EXISTS public_id;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
