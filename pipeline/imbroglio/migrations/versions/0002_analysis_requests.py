"""Analysis request queue (design spec: AnalysisRequest entity, F6).

Web requests and batch imports enqueue a domain; worker processes claim jobs
with FOR UPDATE SKIP LOCKED so any number of workers can run without
double-processing. A worker refreshes heartbeat_at while it runs, so a job
whose worker died (redeploy, out-of-memory kill) can be reclaimed.

Revision ID: 0002
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UP = r"""
CREATE TABLE analysis_requests (
    id             SERIAL PRIMARY KEY,
    domain         TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued', 'running', 'done', 'failed')),
    stage          TEXT,                 -- human-readable progress, e.g. "fetching privacy"
    use_playwright BOOLEAN NOT NULL DEFAULT true,
    source         TEXT NOT NULL DEFAULT 'web',   -- web | batch | extension | monitor
    request_count  INT NOT NULL DEFAULT 1,        -- duplicate requests bump priority
    attempts       INT NOT NULL DEFAULT 0,
    worker_id      TEXT,
    result         JSONB,                -- per-document outcome summary when done
    error          TEXT,
    requested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at     TIMESTAMPTZ,
    heartbeat_at   TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ
);

-- At most one open request per domain: enqueueing an already-queued or
-- running domain bumps request_count instead of adding a duplicate job.
CREATE UNIQUE INDEX uq_requests_open_domain
    ON analysis_requests (domain) WHERE status IN ('queued', 'running');

CREATE INDEX idx_requests_claim
    ON analysis_requests (status, request_count DESC, requested_at);

CREATE INDEX idx_requests_domain_recent
    ON analysis_requests (domain, requested_at DESC);
"""

DOWN = "DROP TABLE IF EXISTS analysis_requests;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
