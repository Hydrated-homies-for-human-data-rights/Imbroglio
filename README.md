# Imbroglio (working codename — final name TBD: Clause vs Receipts)

Automated privacy policy and terms of service analysis. Reads policy documents,
extracts specific data practices with verbatim supporting quotes, scores them
against a published versioned rubric, and monitors them for changes.

See `docs/` for the project proposal and rubric specification.

## Repo layout

| Path | What | Owner |
| --- | --- | --- |
| `pipeline/` | Python: discovery, fetch, extraction, classifier, scoring, monitoring | Jaiden / Gage / Alex |
| `pipeline/spike_a/` | Week-1 extraction feasibility spike (go/no-go gate) | — |
| `web/` | Next.js website + public read API | Sam |
| `extension/` | Manifest V3 browser extension (thin API client) | Alex |
| `docs/` | Rubric spec, evaluation reports, competitive review | Sam |

## Quick start

```bash
# Local Postgres for development
docker compose up -d

# Pipeline setup
cd pipeline
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Run Spike A (extraction feasibility test on 20 sites)
cd spike_a
python spike_a.py

# Analyze one domain end to end (discover -> extract -> hash -> store)
python -m imbroglio.cli analyze notion.so           # needs Postgres up
python -m imbroglio.cli analyze notion.so --no-db   # dry run
```

## Milestone gates

- **Week 2:** extraction spike — ≥16/20 sites must yield clean policy text
- **Week 4:** classifier baseline — per-category P/R/F1 on held-out OPP-115 split
- **Week 6:** vertical slice — one service scored end to end with evidence
- **Week 10:** macro F1 ≥ 0.70 in live pipeline, 500 services underway
