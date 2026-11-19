"""One row per scheduled recheck of a stored document (recheck.py): when it
was fetched again and what came back. It says when each document was last
looked at (document_versions only grows when the text changes), and it is
the denominator for the false-change rate the proposal sets (no more than
one false change per 100 document checks).

Revision ID: 0010
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

UP = r"""
CREATE TABLE document_checks (
    id           SERIAL PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    outcome      TEXT NOT NULL CHECK (outcome IN ('unchanged', 'changed', 'reverted', 'failed')),
    version_id   INTEGER REFERENCES document_versions(id) ON DELETE SET NULL,
    note         TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_document_checks_doc ON document_checks (document_id, checked_at DESC);
"""

DOWN = "DROP TABLE IF EXISTS document_checks;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
