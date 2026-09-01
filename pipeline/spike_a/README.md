# Spike A — extraction feasibility (week-1 go/no-go gate)

Tests whether policy documents can be discovered and extracted programmatically
across 20 sites (5 large / 10 medium / 5 small). Gate: >= 16/20 privacy
policies extracted and validated.

## Run

```bash
cd pipeline
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cd spike_a
python spike_a.py
```

JS-rendered sites (fallback):

```bash
pip install playwright && playwright install chromium
python spike_a.py --playwright
```

Single site while iterating: `python spike_a.py --domain notion.so`

## Output

- `results/report.md` — pass/fail table for the week-2 instructor demo
- `results/report.json` — machine-readable results
- `results/<domain>/privacy.txt`, `terms.txt` — extracted text; manually
  spot-check against the live page (the proposal requires manual verification)

## How it works

1. Fetch homepage, collect `<a>` candidates: visible link text matching
   privacy/terms patterns (strongest), then href matches, then common paths
   (`/privacy`, `/legal/terms`, ...) as last resort.
2. Fetch best candidate, extract main text with trafilatura (favor_recall on —
   over-grab beats truncation for legal text).
3. Validate: >= 1,500 chars AND doc-type keywords present (rejects nav shells,
   cookie walls, error pages).
4. If static extraction is thin and `--playwright` is set, re-render in
   headless Chromium.

## Interpreting failures

- `403` / `ConnectTimeout` — bot-blocked; note it, this is real spike data
  informing the fallback plan (user-submitted policy URLs)
- `no candidate found` — discovery gap; check homepage manually, may need a
  site-specific pattern
- `too short` — extraction gap; likely JS-rendered, retry with `--playwright`
