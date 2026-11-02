"""Problem reports: the published correction path (proposal risk 8).

A reader who thinks a rating or quote is wrong tells us from the site page
or the extension. Reports land here untouched. A team member rereads the
finding against the stored document; if the quote does not support it, the
finding is withdrawn and the report marked accordingly. `client` is the
rate-limit client id, kept so abuse can be reviewed, not shown anywhere.

Revision ID: 0008
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

UP = r"""
CREATE TABLE reports (
    id          SERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    domain      TEXT,                              -- cleaned; null for site-wide feedback
    kind        TEXT NOT NULL
                CHECK (kind IN ('rating', 'quote', 'wrong_document', 'missing', 'other')),
    message     TEXT NOT NULL,
    contact     TEXT,                              -- optional, for follow-up
    page        TEXT,                              -- where the reader was on imbroglio.io
    client      TEXT,                              -- rate-limit client id, for abuse review
    status      TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'reviewed', 'withdrawn', 'dismissed')),
    note        TEXT                               -- reviewer's note
);

CREATE INDEX idx_reports_status_recent ON reports (status, created_at DESC);
"""

DOWN = "DROP TABLE IF EXISTS reports;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
