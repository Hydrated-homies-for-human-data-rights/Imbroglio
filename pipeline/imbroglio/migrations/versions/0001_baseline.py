"""Baseline: the schema as deployed before migrations existed.

Frozen copy of the former schema.sql. Every statement uses IF NOT EXISTS, so
this adopts an existing database (Supabase production, older local Docker
volumes) without touching data, and builds a fresh one from scratch.

Revision ID: 0001
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = r"""
-- Imbroglio core schema.
-- Design rules:
--   * document_versions is append-only: every published claim must be
--     traceable to the exact text that produced it (proposal risk #8).
--   * findings/scores hang off a VERSION, not a document — re-analysis of a
--     new version never overwrites history.
--   * rubric_version + scorer_version columns make results reproducible and
--     let the rubric evolve without corrupting old rows.

CREATE TABLE IF NOT EXISTS services (
    id          SERIAL PRIMARY KEY,
    domain      TEXT UNIQUE NOT NULL,
    name        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id             SERIAL PRIMARY KEY,
    service_id     INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    doc_type       TEXT NOT NULL CHECK (doc_type IN ('privacy', 'terms')),
    url            TEXT NOT NULL,
    discovered_via TEXT,            -- link-text | href | common-path | iframe | manual
    UNIQUE (service_id, doc_type)
);

CREATE TABLE IF NOT EXISTS document_versions (
    id              SERIAL PRIMARY KEY,
    document_id     INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content_hash    TEXT NOT NULL,  -- sha256 of normalized_text
    normalized_text TEXT NOT NULL,
    fetch_method    TEXT,           -- static | playwright
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, content_hash)
);

-- One row per rubric question answered about one document version.
CREATE TABLE IF NOT EXISTS findings (
    id             SERIAL PRIMARY KEY,
    version_id     INT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    rubric_version TEXT NOT NULL,
    category       TEXT NOT NULL,   -- rubric category, e.g. 'ai_training'
    question_id    TEXT NOT NULL,   -- rubric question key
    answer         TEXT NOT NULL CHECK (answer IN ('yes', 'no', 'unclear', 'not_disclosed')),
    quote          TEXT,            -- verbatim supporting quote (NULL iff not_disclosed)
    quote_verified BOOLEAN NOT NULL DEFAULT false,
    provenance     TEXT NOT NULL DEFAULT 'machine'
                   CHECK (provenance IN ('machine', 'human', 'agreed')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, rubric_version, question_id)
);

CREATE TABLE IF NOT EXISTS scores (
    id             SERIAL PRIMARY KEY,
    version_id     INT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    rubric_version TEXT NOT NULL,
    scorer_version TEXT NOT NULL,
    category       TEXT NOT NULL,
    score          TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, rubric_version, category)
);

CREATE TABLE IF NOT EXISTS change_events (
    id             SERIAL PRIMARY KEY,
    document_id    INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    old_version_id INT REFERENCES document_versions(id),
    new_version_id INT NOT NULL REFERENCES document_versions(id),
    detected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary        TEXT
);

CREATE INDEX IF NOT EXISTS idx_versions_document ON document_versions(document_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_version ON findings(version_id);
CREATE INDEX IF NOT EXISTS idx_changes_document ON change_events(document_id, detected_at DESC);

-- Batch runs: every bulk import, with its source and timing.
CREATE TABLE IF NOT EXISTS batches (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,          -- input file name or seed source
    total       INT NOT NULL,
    workers     INT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

-- One row per (domain, doc_type) attempt, success OR failure. Successful
-- documents also land in documents/document_versions; this table is the
-- audit trail that lets us report extraction success rates (F1) and group
-- failures by cause.
CREATE TABLE IF NOT EXISTS crawl_attempts (
    id             SERIAL PRIMARY KEY,
    batch_id       INT REFERENCES batches(id) ON DELETE CASCADE,
    domain         TEXT NOT NULL,
    doc_type       TEXT NOT NULL CHECK (doc_type IN ('privacy', 'terms')),
    ok             BOOLEAN NOT NULL,
    status         TEXT NOT NULL,      -- stored-new | unchanged | changed | failed | error
    url            TEXT,
    discovered_via TEXT,
    fetch_method   TEXT,
    chars          INT NOT NULL DEFAULT 0,
    notes          TEXT,
    seconds        REAL,               -- wall time for the whole domain
    attempted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_attempts_batch ON crawl_attempts(batch_id);
CREATE INDEX IF NOT EXISTS idx_attempts_domain ON crawl_attempts(domain, attempted_at DESC);

-- Human review of discovery results: was the found document the right one,
-- and did a "not found" site actually have a policy? These labels turn the
-- automatic success rate into a verified accuracy figure (F1, F5).
CREATE TABLE IF NOT EXISTS audit_labels (
    id          SERIAL PRIMARY KEY,
    attempt_id  INT REFERENCES crawl_attempts(id) ON DELETE SET NULL,
    domain      TEXT NOT NULL,
    doc_type    TEXT NOT NULL CHECK (doc_type IN ('privacy', 'terms')),
    outcome     TEXT NOT NULL CHECK (outcome IN ('found', 'missed')),
    verdict     TEXT NOT NULL CHECK (verdict IN ('correct', 'wrong', 'missed', 'none', 'unsure')),
    correct_url TEXT,               -- reviewer-supplied URL of the real document, if known
    note        TEXT,
    reviewer    TEXT,               -- free-text name; there are no accounts
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_domain ON audit_labels(domain, doc_type);
"""


def upgrade() -> None:
    # Raw driver call: op.execute would parse ":word" in comments as bind params.
    op.get_bind().exec_driver_sql(SCHEMA)


def downgrade() -> None:
    raise NotImplementedError("baseline migration is not reversible")
