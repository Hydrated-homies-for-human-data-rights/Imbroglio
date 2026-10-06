"""Model comparison for extraction.

    python -m imbroglio.cli compare-models --sample 10 --models opus,sonnet,haiku

Runs each model on the same random sample of stored privacy policies and
reports, per model: quote verification rate (the F4 trust number), how many
findings survive verification, refusals/errors, cost and speed, and how often
the models agree with each other. Read-only: nothing is written to the
database. The per-document details go to a JSON file for human spot checks.
"""

from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

from . import db
from .llm_extract import ALIASES, MODELS, extract
from .rubric import NOT_DISCLOSED, load


def sample_documents(conn, n: int, seed: int, min_chars=3000, max_chars=60000) -> list[tuple]:
    rows = conn.execute(
        """SELECT DISTINCT ON (d.id) s.domain, v.id, v.normalized_text
           FROM documents d JOIN services s ON s.id = d.service_id
           JOIN document_versions v ON v.document_id = d.id
           WHERE d.doc_type = 'privacy'
             AND length(v.normalized_text) BETWEEN %s AND %s
           ORDER BY d.id, v.fetched_at DESC""",
        (min_chars, max_chars),
    ).fetchall()
    rows.sort(key=lambda r: r[0])
    return random.Random(seed).sample(rows, min(n, len(rows)))


def run(n: int, models: list[str], seed: int = 1, out: Path | None = None,
        rubric_version: str = "v0", parallel: int = 4) -> str:
    models = [ALIASES.get(m, m) for m in models]
    rubric = load(rubric_version)
    conn = db.connect()
    try:
        docs = sample_documents(conn, n, seed)
        total_docs = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
    finally:
        conn.close()

    jobs = [(d, m) for d in docs for m in models]
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        results = list(pool.map(lambda j: (j[0], j[1], extract(j[0][2], rubric, j[1])), jobs))

    per = {m: [] for m in models}
    for doc, m, r in results:
        per[m].append((doc, r))

    lines = [f"# Extraction model comparison — rubric {rubric.version}",
             "", f"{len(docs)} privacy policies (random, seed {seed}), "
                 f"{len(rubric.checks)} checks each. Projected cost covers all "
                 f"{total_docs} stored documents, analyzed once.", "",
             "| Model | OK / refused / error | Quote verification | Findings shown | "
             "Not disclosed | Unanswered or invalid | Avg time | Cost (sample) | Projected cost |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    summary = {}
    for m in models:
        rs = [r for _, r in per[m]]
        ok = [r for r in rs if r.status == "ok"]
        quotes = [v for r in ok for f in r.findings for v in f.quotes_verified]
        shown = sum(1 for r in ok for f in r.findings if f.verified and f.status != NOT_DISCLOSED)
        nd = sum(1 for r in ok for f in r.findings if f.status == NOT_DISCLOSED)
        bad = sum(1 for r in ok for f in r.findings if not f.verified and f.status != NOT_DISCLOSED)
        spent = sum(r.cost_usd for r in rs)
        per_doc = spent / len(rs) if rs else 0
        avg_s = sum(r.seconds for r in rs) / len(rs) if rs else 0
        rate = sum(quotes) / len(quotes) if quotes else None
        summary[m] = dict(ok=len(ok), refused=sum(r.status == "refused" for r in rs),
                          error=sum(r.status == "error" for r in rs), quote_rate=rate,
                          shown=shown, not_disclosed=nd, invalid=bad, avg_seconds=avg_s,
                          cost=spent, projected=per_doc * total_docs)
        s = summary[m]
        lines.append(f"| {MODELS.get(m, {}).get('label', m)} | {s['ok']} / {s['refused']} / {s['error']} | "
                     f"{'n/a' if rate is None else f'{100 * rate:.1f}%'} ({len(quotes)} quotes) | "
                     f"{shown} | {nd} | {bad} | {avg_s:.1f}s | ${spent:.3f} | ${s['projected']:.2f} |")

    # Agreement: same status on the same check of the same document.
    status = {(doc[1], m, f.check_id): f.status
              for doc, m, r in results if r.status == "ok" for f in r.findings}
    lines += ["", "## Agreement between models", "",
              "Share of (document, check) pairs where both models chose the same status.", "",
              "| Pair | Agreement |", "| --- | --- |"]
    for a, b in combinations(models, 2):
        keys = [(d[1], c.id) for d in docs for c in rubric.checks
                if (d[1], a, c.id) in status and (d[1], b, c.id) in status]
        same = sum(status[(v, a, c)] == status[(v, b, c)] for v, c in keys)
        lines.append(f"| {MODELS[a]['label']} vs {MODELS[b]['label']} | "
                     f"{100 * same / len(keys):.0f}% of {len(keys)} |" if keys else
                     f"| {a} vs {b} | n/a |")

    errors = [(doc[0], m, r.error) for doc, m, r in results if r.status != "ok"]
    if errors:
        lines += ["", "## Failures", ""] + [f"- {d} / {m}: {e}" for d, m, e in errors]
    lines += ["", "Documents: " + ", ".join(d[0] for d in docs)]
    report = "\n".join(lines)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        details = [{"domain": doc[0], "version_id": doc[1], "model": m, "status": r.status,
                    "error": r.error, "cost_usd": r.cost_usd, "seconds": r.seconds,
                    "findings": [f.__dict__ for f in r.findings]} for doc, m, r in results]
        out.with_suffix(".json").write_text(json.dumps(details, indent=2), encoding="utf-8")
    return report
