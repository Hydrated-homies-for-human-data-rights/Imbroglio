"""Progress log on analysis requests.

The worker appends one line per pipeline step ("trying https://x/privacy",
"got 13,533 chars"...) so clients polling a request can show the same live
log the console used to stream directly from the web process.

Revision ID: 0003
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UP = r"""
ALTER TABLE analysis_requests ADD COLUMN progress JSONB NOT NULL DEFAULT '[]'::jsonb;
"""

DOWN = r"""
ALTER TABLE analysis_requests DROP COLUMN progress;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
