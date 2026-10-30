"""Allow the INFO category rating (scorer s2, rubric v0.2).

A category whose answers are only informational (the site collects sensitive
data, grants a broad content license) is reported as INFO instead of LIMITED,
since LIMITED means the practice is narrow or absent. Schema only.

Revision ID: 0007
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UP = r"""
ALTER TABLE scores DROP CONSTRAINT scores_tier_check;
ALTER TABLE scores ADD CONSTRAINT scores_tier_check
    CHECK (tier IN ('LIMITED', 'MODERATE', 'EXTENSIVE', 'SEVERE', 'NOT_DISCLOSED', 'INFO'));
"""

DOWN = r"""
DELETE FROM scores WHERE tier = 'INFO';
ALTER TABLE scores DROP CONSTRAINT scores_tier_check;
ALTER TABLE scores ADD CONSTRAINT scores_tier_check
    CHECK (tier IN ('LIMITED', 'MODERATE', 'EXTENSIVE', 'SEVERE', 'NOT_DISCLOSED'));
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
