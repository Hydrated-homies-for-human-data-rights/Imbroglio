"""Findings and scores for real use, plus per-call extraction accounting.

The placeholder findings/scores tables from the baseline were never written
to (0 rows), so they are recreated rather than altered:
  * findings hold every quote the model returned and whether each was found
    word-for-word in the stored text (F4: unverified findings are never shown)
  * the model that produced a finding is recorded (ModelVersion, S2)
  * reused_from_version_id marks findings copied from an identical document
  * extraction_runs records tokens, cost and time for every LLM call, for the
    model comparison and to keep spend visible

Revision ID: 0005
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UP = r"""
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS scores;

CREATE TABLE extraction_runs (
    id             SERIAL PRIMARY KEY,
    version_id     INT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    rubric_version TEXT NOT NULL,
    model          TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('ok', 'refused', 'error')),
    stop_reason    TEXT,
    input_tokens   INT,
    output_tokens  INT,
    cache_read_tokens INT,
    cost_usd       NUMERIC(10, 5),
    seconds        REAL,
    error          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE findings (
    id             SERIAL PRIMARY KEY,
    version_id     INT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    run_id         INT REFERENCES extraction_runs(id) ON DELETE SET NULL,
    rubric_version TEXT NOT NULL,
    check_id       TEXT NOT NULL,
    category       TEXT NOT NULL,
    status         TEXT NOT NULL,          -- a rubric status, or not_disclosed / unverified
    quotes         TEXT[] NOT NULL DEFAULT '{}',
    quotes_verified BOOLEAN[] NOT NULL DEFAULT '{}',
    verified       BOOLEAN NOT NULL,       -- false = never shown, never scored
    explanation    TEXT,
    model          TEXT NOT NULL,
    provenance     TEXT NOT NULL DEFAULT 'machine'
                   CHECK (provenance IN ('machine', 'human', 'agreed')),
    reused_from_version_id INT REFERENCES document_versions(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, rubric_version, check_id)
);

CREATE TABLE scores (
    id             SERIAL PRIMARY KEY,
    version_id     INT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    rubric_version TEXT NOT NULL,
    scorer_version TEXT NOT NULL,
    category       TEXT NOT NULL,
    tier           TEXT NOT NULL CHECK (tier IN ('LIMITED', 'MODERATE', 'EXTENSIVE', 'SEVERE', 'NOT_DISCLOSED')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, rubric_version, scorer_version, category)
);

CREATE INDEX idx_findings_version ON findings (version_id, rubric_version);
CREATE INDEX idx_runs_version ON extraction_runs (version_id);
CREATE INDEX idx_scores_version ON scores (version_id, rubric_version);
"""

DOWN = r"""
DROP TABLE IF EXISTS scores;
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS extraction_runs;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
