# Design changes since the design spec

The design specification (Sep 27, 2026) is in the team Notes repo. This page records where the built
system differs from it and why, so every difference is a decision on record and not drift. Update it
whenever a planned piece changes.

## Decided and built differently

| Spec said | What we did | Why |
| --- | --- | --- |
| LLM vendor undecided (open question 5) | Anthropic, Claude Sonnet 5 | Measured side by side with Haiku 4.5 on the same policies: cheaper per document and more careful about "not disclosed" (see [evaluation.md](evaluation.md)) |
| Extraction at temperature 0 for reproducibility (N2) | No temperature setting | Sonnet 5 doesn't accept sampling settings, so run-to-run consistency is measured instead of configured |
| Rubric v1 with 25 checks | Rubric v0.3 live with 14 checks (2 per category), after v0.1 and v0.2; v1.0 drafted with 28 | A smaller rubric let us build and measure the whole pipeline first; calibration showed which questions need changing before v1 |
| One scoring rule set | Scorer s3 live (since Nov 17), after s1 and s2 ("red flags + coverage") | s1 rated every site SEVERE or EXTENSIVE. The comparison is in [rubric-calibration.md](rubric-calibration.md); s3 is in [rubric.md](rubric.md) |
| Four rating tiers plus NOT DISCLOSED | s2 adds UNCLEAR | A site shouldn't be called clean when too few questions were answered |
| SQLAlchemy ORM and httpx | Plain SQL with psycopg, and requests | The queries are short and the provenance joins read clearly in SQL; Alembic still runs the migrations |
| Raw HTML archived in Supabase Storage | Only the normalized text is stored, with its hash | Quote checking and change detection both use the normalized text; the raw page wasn't needed yet |
| Extension asks the API about the current domain | Extension sends only a short prefix of the domain's hash (`/v1/lookup`) | Our server never learns which site a user is on. This is a privacy improvement over the spec |
| Correction path as a dispute form | A "Report a problem" form on the website (`POST /v1/reports`, optional email), with the GitHub issue template kept for people who prefer it | The issue template shipped first, once the repo went public; it needs a GitHub account, so the form followed |
| A public read API | The API service sits behind one shared password (basic auth) on every route but `/healthz`; the website calls it from its server and passes only lookup and request status through to browsers | Keeps the prototype's API, and its analysis budget, out of reach of anyone but the website and the extension until launch |
| Front end: Tailwind with a token layer, TanStack Query | Tailwind with classes copied from the UX team's Figma Make file; pages fetch on the server | Server rendering already caches and keeps the API password off the browser, so TanStack Query wasn't needed. Tiers still always show shape, word and color |

## Planned, not built yet

| Spec item | Status |
| --- | --- |
| Segment classifier in the live pipeline (S3) | Baseline measured (macro F1 0.765); the neural network classifier is in progress; not wired in yet |
| Clause retrieval with sentence-transformers and pgvector | Not started. Its answer key (verified quotes from the label export) is ready |
| Confidence calibration | Not started |
| Daily change monitor on Railway cron (F7) | Rechecks run inside the worker service instead of a cron: every hour it fetches the documents not checked in `RECHECK_DAYS` and stores any change as a new version with a change event. Detect-only; re-rating a changed policy is still done by hand, and there is no public change feed yet |
| ToS;DR staleness flags and grade comparison | Letter grades proved unusable for comparison; switching to their per-finding verdicts |
| Open Terms Archive for historical versions | Not used yet |
| Request voting (F6) | Requests and the queue work; voting isn't built |
| Weights & Biases model registry | Not used yet; the baseline's metrics are in the repo |
| Front end tests (Vitest, React Testing Library) | Not set up. CI now lints and builds the website on every push |
| Ruff and Black | Not set up |
