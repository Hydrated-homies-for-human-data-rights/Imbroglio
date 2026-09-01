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
