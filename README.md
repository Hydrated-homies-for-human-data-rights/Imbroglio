# Imbroglio

Automated privacy policy and terms of service analysis. Reads policy documents,
extracts specific data practices with verbatim supporting quotes, scores them
against a published versioned rubric, and monitors them for changes.

CS 4360 Senior Experience, Fall 2026 — Hydrated Homies for Human Data Rights
(Gage Gunn, Sam Holton, Alex Kimoni, Jaiden Searle). The proposal, requirements
and design specification live in the team Notes repo.

## Status

Prototype, hosted on Railway + Supabase behind a shared password.

Working:

- **Discovery and extraction:** finds a site's privacy policy and terms of
  service (link text, href patterns, common paths, headless-browser fallback,
  iframe follow), extracts clean text, hashes it, and stores every version.
  On a random sample of ToS;DR services it finds a privacy policy for about 80%
  of the sites it can reach.
- **Job queue + worker:** new sites are queued and analyzed by a separate
  worker service; cached sites are served straight from the database.
- **Read API v1** (docs generated at `/v1/docs`):
  - `GET /v1/sites/{domain}`: documents, analysis in progress, state
  - `POST /v1/requests` + `GET /v1/requests/{id}`: ask for an analysis and
    follow it (per-client rate limit and a daily cap)
  - `GET /v1/lookup/{prefix}`: look a site up by a prefix of `sha256(domain)`,
    so clients like the extension never reveal which site a user is on
- **Bulk import:** seed from the ToS;DR catalogue and run batches from the CLI.
- **Audit page:** reviewers mark found documents right or wrong, and misses as
  real misses or "no policy exists", producing a verified accuracy figure.
- **Spikes:** discovery feasibility (19/20, [report](pipeline/spike_a/results/report.md))
  and a TF-IDF classifier baseline on OPP-115 (macro F1 0.765,
  [metrics](pipeline/spike_b/results/metrics.md)).

Not built yet: rubric, LLM extraction and quote verification, scorer, classifier
in the live pipeline, daily change monitor, website, browser extension,
evaluation report.

## How it fits together

```text
 website / extension / researchers
              │  GET /v1/sites, /v1/lookup · POST /v1/requests
              ▼
   web service (pipeline/demo/app.py) ──── reads ────►  Postgres (Supabase)
              │ enqueue                                     ▲
              ▼                                             │ writes
   analysis_requests table ◄── claims jobs ── worker service (python -m imbroglio.worker)
                                               discover → fetch → extract → hash → store
```

The web service never fetches a website or runs a browser; only workers do.

## Repo layout

| Path | What |
| --- | --- |
| `pipeline/imbroglio/` | Python package: discovery, fetch, extraction, storage, queue, worker, API |
| `pipeline/imbroglio/migrations/` | Alembic database migrations (the schema lives here) |
| `pipeline/demo/` | Web service: prototype console, audit page, mounts the `/v1` API |
| `pipeline/tests/` | pytest suite |
| `pipeline/spike_a/`, `spike_b/` | Early feasibility spikes |
| `web/` | Next.js website (not started) |
| `extension/` | Browser extension (not started) |
| `docs/` | Rubric, evaluation reports |

## Setup

Requires Python 3.12+ and Docker.

```bash
docker compose up -d                 # local Postgres

cd pipeline
python -m venv .venv
.venv\Scripts\activate               # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
playwright install chromium
```

The database schema is created and upgraded automatically on first use. To run
migrations by hand: `alembic upgrade head` (from `pipeline/`).

## Run

From `pipeline/`:

```bash
# Web console + embedded worker -> http://localhost:8765
cd demo && python app.py

# One site from the command line
python -m imbroglio.cli analyze notion.so

# Bulk import
python -m imbroglio.cli seed-tosdr seeds/tosdr_rated.csv --rated-only
python -m imbroglio.cli batch seeds/tosdr_rated.csv --sample 100 --workers 4
python -m imbroglio.cli report

# Standalone worker (what production runs)
python -m imbroglio.worker
```

## Tests

```bash
cd pipeline && pytest
```

Queue and API tests need the local Postgres from `docker compose up -d`; they
create and drop a throwaway database and skip themselves if Postgres isn't
running. CI runs the full suite on every push and pull request.

## Database changes

Never edit an old migration. Add a new one:

```bash
cd pipeline
alembic revision -m "add segments table"   # then write the SQL into UP / DOWN
alembic upgrade head
```

## Deploy

Two Railway services build from `pipeline/Dockerfile` and redeploy on every
push to `main`:

| Service | Start command | Notes |
| --- | --- | --- |
| `pipeline` (web) | default (`python demo/app.py`) | public URL, health check `/healthz`, `EMBEDDED_WORKER=0` |
| `worker` | `python -m imbroglio.worker` | no public URL; runs Chromium |

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Supabase **session pooler** connection string (both services) |
| `IMBROGLIO_PASSWORD` | Shared site password, 12+ characters (web) |
| `IMBROGLIO_USER` | Basic-auth username, default `imbroglio` (web) |
| `EMBEDDED_WORKER` | `1` runs worker threads inside the web process (local default); `0` in production |
| `WORKER_CONCURRENCY` | Worker threads per process (default 2) |
| `MAX_BROWSERS` | Headless browsers at once per process (default 2; production worker uses 1) |
| `REQUESTS_PER_HOUR` | Analysis requests allowed per client per hour (default 30) |
| `DAILY_REQUEST_CAP` | Analysis requests accepted per 24 hours, all clients (default 300) |

Security: every route except `/healthz` requires the password; outbound fetches
refuse private, loopback and cloud-metadata addresses, including via redirects
and in-browser requests (`pipeline/imbroglio/netguard.py`); Chromium runs as a
non-root user in the worker only.

## Known issues

- **Windows Smart App Control** can block lxml's DLLs, which breaks
  trafilatura. The pipeline falls back to a pure-Python extractor
  automatically, but its output differs slightly from the Linux containers, so
  don't load locally extracted documents into the production database.
- **Windows MAX_PATH:** the OPP-115 zip contains very long file names;
  `spike_b/prepare.py` extracts only the folders it needs to avoid this.
- **1 GB per Railway service:** headless Chromium needs headroom; keep
  `MAX_BROWSERS=1` on the worker unless its memory limit is raised.

## License

Code is licensed under the [Apache License 2.0](LICENSE).

Data derived from the ToS;DR API is licensed separately under CC BY-SA 3.0,
per its source, and is attributed where it is displayed or redistributed.
OPP-115 is used for research and teaching with citation (Wilson et al.,
ACL 2016) and is not redistributed in this repository.
