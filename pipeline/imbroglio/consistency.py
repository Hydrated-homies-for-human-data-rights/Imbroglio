"""Run-to-run consistency study (N2).

    python -m imbroglio.cli consistency --sample 50 --runs 3 --out runs/consistency.md

Reads the same random sample of stored privacy policies several times with
the production model and rubric, and reports how often the answers stay the
same. N2's target: at least 90% agreement across three runs on 50 documents.

Measured, not configured: Sonnet 5 and Opus 5 don't accept a temperature,
so there is no setting that forces identical output.

Reported:
  * answer agreement: share of (document, check) pairs where every run chose
    the same status (the N2 number), plus pairwise agreement
  * per check: agreement and Fleiss' kappa, so a check that is nearly always
    not_disclosed can't look stable just because of that
  * what users would see: same category tier and same headline across runs
    (scored with the current scorer)
  * 95% bootstrap intervals, resampling documents

Read-only: nothing is written to the database. Every run's raw answers go to
a JSON file next to the report, along with the sampled documents, so the
numbers can be recomputed without new model calls.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

from . import db, scorer
from .compare import sample_documents
from .llm_extract import ALIASES, MODELS, extract
from .rubric import load

BOOTSTRAP_RESAMPLES = 2000


# --- statistics (pure functions; runs are lists of {key: answer} dicts) -------

def all_agree(answers: list) -> bool:
    return len(set(answers)) == 1


def pairwise_agreement(answers: list) -> float:
    pairs = list(combinations(answers, 2))
    return sum(a == b for a, b in pairs) / len(pairs)


def fleiss_kappa(items: list[list]) -> float | None:
    """Fleiss' kappa for items each rated by the same number of raters (here,
    runs). None when every rating is the same category: agreement is then
    perfect but chance agreement is too, and kappa is undefined."""
    if not items:
        return None
    n = len(items[0])
    counts = [Counter(item) for item in items]
    total = Counter()
    for c in counts:
        total.update(c)
    p_e = sum((v / (len(items) * n)) ** 2 for v in total.values())
    if p_e == 1:
        return None
    p_bar = sum((sum(v * v for v in c.values()) - n) / (n * (n - 1)) for c in counts) / len(items)
    return (p_bar - p_e) / (1 - p_e)


def agreement(docs: dict[int, list[dict]]) -> float | None:
    """Share of (document, key) pairs where every run gave the same value."""
    pairs = [[run.get(k) for run in runs] for runs in docs.values() for k in runs[0]]
    return sum(map(all_agree, pairs)) / len(pairs) if pairs else None


def bootstrap(docs: dict[int, list[dict]], stat, seed: int = 0,
              resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[float, float] | None:
    """95% percentile interval for stat(docs), resampling whole documents
    (answers within a document aren't independent)."""
    ids = list(docs)
    if not ids:
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        picked = rng.choices(ids, k=len(ids))
        v = stat({i: docs[d] for i, d in enumerate(picked)})  # a doc drawn twice counts twice
        if v is not None:
            values.append(v)
    values.sort()
    return values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1]


# --- the study ------------------------------------------------------------------

def run(n: int, runs: int, model: str, rubric_version: str, seed: int = 1,
        out: Path | None = None, parallel: int = 4) -> str:
    model = ALIASES.get(model, model)
    rubric = load(rubric_version)
    conn = db.connect()
    try:
        docs = sample_documents(conn, n, seed)
    finally:
        conn.close()

    jobs = [(d, r) for d in docs for r in range(runs)]
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        results = list(pool.map(lambda j: (j[0], j[1], extract(j[0][2], rubric, model)), jobs))

    by_doc: dict[int, list] = {}
    for doc, _, ex in results:
        by_doc.setdefault(doc[1], []).append(ex)
    complete = {v: exs for v, exs in by_doc.items() if all(e.status == "ok" for e in exs)}
    answers = {v: [{f.check_id: f.status for f in e.findings} for e in exs] for v, exs in complete.items()}
    rated = {v: [scorer.rate(rubric, [scorer.ScoredFinding(f.check_id, f.status, f.verified)
                                      for f in e.findings]) for e in exs]
             for v, exs in complete.items()}
    tiers = {v: [t for t, _ in rs] for v, rs in rated.items()}
    headlines = {v: [{"headline": h} for _, h in rs] for v, rs in rated.items()}

    def pct(x):
        return "n/a" if x is None else f"{100 * x:.1f}%"

    def ci(stat_docs, stat=agreement):
        b = bootstrap(stat_docs, stat, seed)
        return "" if b is None else f" (95% CI {pct(b[0])} to {pct(b[1])})"

    spent = sum(ex.cost_usd for _, _, ex in results)
    model_label = MODELS.get(model, {}).get("label", model)
    status_pairs = [[run.get(k) for run in rs] for rs in answers.values() for k in rs[0]]
    overall = agreement(answers)
    lines = [f"# Run-to-run consistency (N2): rubric {rubric.version}, {model_label}",
             "",
             f"{len(docs)} privacy policies (random, seed {seed}), {runs} runs each, "
             f"{len(rubric.checks)} checks per run. {len(complete)} documents had every run "
             f"succeed and are counted. Cost ${spent:.2f}.",
             "",
             "The model doesn't accept a temperature setting, so this measures how much its "
             "answers vary rather than assuming they don't.",
             "",
             "## Headline numbers",
             "",
             "| Measure | Result | Target |",
             "| --- | --- | --- |",
             f"| Same answer in every run, per (document, check) | {pct(overall)}{ci(answers)} | at least 90% |",
             f"| Same answer, average over pairs of runs | "
             f"{pct(sum(map(pairwise_agreement, status_pairs)) / len(status_pairs) if status_pairs else None)} | |",
             f"| Same rating in every run, per (document, category), scorer {scorer.version_for(rubric)} | "
             f"{pct(agreement(tiers))}{ci(tiers)} | |",
             f"| Same headline rating in every run, per document | {pct(agreement(headlines))}{ci(headlines)} | |",
             "",
             "## Per check",
             "",
             "Fleiss' kappa treats each run as a rater. n/a means every run on every document "
             "gave the same answer, so there is no variation to measure.",
             "",
             "| Check | Same answer in every run | Fleiss' kappa | Most common answer |",
             "| --- | --- | --- | --- |"]
    for c in rubric.checks:
        items = [[run.get(c.id) for run in rs] for rs in answers.values()]
        if not items:
            continue
        kappa = fleiss_kappa(items)
        common, count = Counter(a for item in items for a in item).most_common(1)[0]
        lines.append(f"| {c.id} | {pct(sum(map(all_agree, items)) / len(items))} | "
                     f"{'n/a' if kappa is None else f'{kappa:.2f}'} | "
                     f"{common} ({100 * count / (len(items) * runs):.0f}%) |")

    unstable = [f"- {domain} / {c}: " + ", ".join(str(r.get(c)) for r in answers[v])
                for domain, v, _ in docs if v in answers
                for c in answers[v][0] if not all_agree([r.get(c) for r in answers[v]])]
    if unstable:
        lines += ["", "## Answers that changed between runs", ""] + unstable
    failures = [(doc[0], i, ex.status, ex.error) for doc, i, ex in results if ex.status != "ok"]
    if failures:
        lines += ["", "## Failed runs (their documents are left out)", ""]
        lines += [f"- {d} run {i + 1}: {s} {e or ''}" for d, i, s, e in failures]
    lines += ["", "Documents: " + ", ".join(d[0] for d in docs)]
    report = "\n".join(lines)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        details = [{"domain": doc[0], "version_id": doc[1], "run": i + 1, "model": ex.model,
                    "status": ex.status, "error": ex.error, "cost_usd": ex.cost_usd,
                    "seconds": ex.seconds, "findings": [f.__dict__ for f in ex.findings]}
                   for doc, i, ex in results]
        out.with_suffix(".json").write_text(json.dumps(details, indent=2), encoding="utf-8")
    return report
