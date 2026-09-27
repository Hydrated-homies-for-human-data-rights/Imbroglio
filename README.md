# Imbroglio

Automated privacy policy and terms of service analysis. Reads policy documents,
extracts specific data practices with verbatim supporting quotes, scores them
against a published versioned rubric, and monitors them for changes.

CS 4360 Senior Experience, Fall 2026 — Hydrated Homies for Human Data Rights
(Gage Gunn, Sam Holton, Alex Kimoni, Jaiden Searle). The proposal, requirements
and design specification live in the team Notes repo.

## Status

Prototype phase. Built so far:

- **Spike A — discovery feasibility:** 19/20 privacy policies located and
  extracted, gate (>= 16/20) passed. Report: [pipeline/spike_a/results/report.md](pipeline/spike_a/results/report.md)
- **Spike B — classifier baseline:** TF-IDF + logistic regression on OPP-115,
  macro F1 0.765 on the held-out test split. Report: [pipeline/spike_b/results/metrics.md](pipeline/spike_b/results/metrics.md)
- **Pipeline spine:** domain -> discover -> fetch (static, headless fallback,
  iframe follow) -> extract -> normalize -> hash -> store, with change detection
  on re-fetch. `pipeline/imbroglio/`
- **Demo console:** throwaway local web UI over the pipeline. `pipeline/demo/`

Not yet built: rubric, LLM extraction and quote verification, scorer, read
API, web app, monitoring cron, ToS;DR ingest, evaluation harness.

## Repo layout

| Path | What |
| --- | --- |
| `pipeline/imbroglio/` | Python analysis pipeline package |
| `pipeline/demo/` | Local demo console (FastAPI + one HTML page) |
| `pipeline/spike_a/` | Week-1 discovery feasibility spike |
| `pipeline/spike_b/` | OPP-115 corpus prep + classical baseline spike |
| `web/` | Next.js web app (not started) |
| `extension/` | Browser extension, stretch (not started) |
| `docs/` | Rubric, evaluation reports |

## Setup

Requires Python 3.12+ and Docker.

```bash
# Local Postgres
docker compose up -d

# Pipeline
cd pipeline
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
playwright install chromium
```

## Run

```bash
# Analyze one domain from the command line (from pipeline/)
python -m imbroglio.cli analyze notion.so
python -m imbroglio.cli analyze notion.so --no-db    # without Postgres

# Demo console -> http://localhost:8765  (from pipeline/demo/)
python app.py

# Spikes
cd spike_a && python spike_a.py --playwright
cd spike_b && python prepare.py && python baseline.py
```

## Known issues

- **Windows Smart App Control** can block lxml's DLLs, which breaks
  trafilatura. The pipeline falls back to a pure-Python extractor
  automatically; output is somewhat noisier.
- **Windows MAX_PATH:** the OPP-115 zip contains very long file names;
  `spike_b/prepare.py` extracts only the folders it needs to avoid this.

## License

Code is licensed under the [Apache License 2.0](LICENSE).

Data derived from the ToS;DR API is licensed separately under CC BY-SA 3.0,
per its source, and is attributed where it is displayed or redistributed.
OPP-115 is used for research and teaching with citation (Wilson et al.,
ACL 2016) and is not redistributed in this repository.
