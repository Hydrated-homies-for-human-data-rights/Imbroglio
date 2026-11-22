"""Withdrawing a single finding (cli withdraw / unwithdraw / withdrawn).

The site tells readers that if a quote doesn't support a finding, we withdraw
it and work the rating out again from what remains. Until now the only way to
do that was editing the row by hand. withdrawn_at marks a finding a person
reread against the stored document and found unsupported: the row stays, but
a withdrawn finding is never scored and never shown. NULL is a normal finding.
withdrawn_reason says why, withdrawn_by who, and withdrawn_report the reader
report that led to it, when there was one.

The mark belongs to the finding row, that is to one check on one document
version under one rubric. Reading the same version again (extract --force,
reanalyze) updates the answer but keeps the mark, so a withdrawal never comes
back on its own; only `cli unwithdraw` lifts it. Findings copied from an
identical document carry the mark with them. A new version of the document
(the text changed) is a new reading and starts unmarked.

Revision ID: 0014
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

UP = r"""
ALTER TABLE findings ADD COLUMN withdrawn_at TIMESTAMPTZ;
ALTER TABLE findings ADD COLUMN withdrawn_reason TEXT;
ALTER TABLE findings ADD COLUMN withdrawn_by TEXT;
ALTER TABLE findings ADD COLUMN withdrawn_report INT REFERENCES reports(id) ON DELETE SET NULL;
ALTER TABLE findings ADD CONSTRAINT findings_withdrawn_has_reason
    CHECK (withdrawn_at IS NULL OR withdrawn_reason IS NOT NULL);
CREATE INDEX idx_findings_withdrawn ON findings (withdrawn_at) WHERE withdrawn_at IS NOT NULL;
"""

DOWN = r"""
DROP INDEX IF EXISTS idx_findings_withdrawn;
ALTER TABLE findings DROP CONSTRAINT IF EXISTS findings_withdrawn_has_reason;
ALTER TABLE findings DROP COLUMN IF EXISTS withdrawn_report;
ALTER TABLE findings DROP COLUMN IF EXISTS withdrawn_by;
ALTER TABLE findings DROP COLUMN IF EXISTS withdrawn_reason;
ALTER TABLE findings DROP COLUMN IF EXISTS withdrawn_at;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
