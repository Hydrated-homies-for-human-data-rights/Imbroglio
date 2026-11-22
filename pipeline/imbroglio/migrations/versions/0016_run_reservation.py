"""Let an extraction run be written before its model call, as 'running'.

The daily LLM budget used to be checked and spent in two separate steps: read
the last 24 hours' spend, make the call (a minute or two), then record what it
cost. Two workers checking at the same moment both passed. Now the check and
a reservation row ('running', with the average cost of a call) are written
under one advisory lock (analysis._reserve), and the row is filled in with the
real numbers when the call returns. Schema only.

Revision ID: 0016
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

UP = r"""
ALTER TABLE extraction_runs DROP CONSTRAINT extraction_runs_status_check;
ALTER TABLE extraction_runs ADD CONSTRAINT extraction_runs_status_check
    CHECK (status IN ('ok', 'refused', 'error', 'running'));
"""

DOWN = r"""
UPDATE extraction_runs SET status = 'error', error = coalesce(error, 'interrupted') WHERE status = 'running';
ALTER TABLE extraction_runs DROP CONSTRAINT extraction_runs_status_check;
ALTER TABLE extraction_runs ADD CONSTRAINT extraction_runs_status_check
    CHECK (status IN ('ok', 'refused', 'error'));
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
