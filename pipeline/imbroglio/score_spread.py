"""How the score out of 100 spreads across every analyzed site.

    python -m imbroglio.cli score-spread --rubric v0.2
    python -m imbroglio.cli score-spread --rubric v0.2 --out runs/score-spread.md --csv runs/scores.csv

Read-only and free: it runs the same scorer.rate() and scorer.score() the
website uses over the findings already stored, with no model calls and no
writes. Run it before the score goes live, and again after any change to the
points, to check that sites spread out instead of piling up on a few values
and that the "kept in range" adjustment stays rare.
"""

from __future__ import annotations

import csv
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import scorer
from .rubric import Rubric

BUCKET = 10
BAR_WIDTH = 40


@dataclass(frozen=True)
class SiteScore:
    domain: str
    headline: str
    score: scorer.Score | None


def score_sites(rubric: Rubric, sites: dict[str, list[tuple]]) -> list[SiteScore]:
    """Every site's headline and score, from db.site_findings() rows
    (domain_hash, check_id, status, verified, created_at), as the API does."""
    out = []
    for domain, rows in sorted(sites.items()):
        findings = [scorer.ScoredFinding(c, s, v) for _, c, s, v, _ in rows]
        _, head = scorer.rate(rubric, findings)
        out.append(SiteScore(domain, head, scorer.score(rubric, findings, head)))
    return out


def _bar(n: int, most: int) -> str:
    return "█" * max(1, round(n / most * BAR_WIDTH)) if n else ""


def report(rubric: Rubric, scored: list[SiteScore]) -> str:
    with_score = [s for s in scored if s.score is not None]
    values = [s.score.value for s in with_score]
    lines = [
        f"# Score spread, rubric {rubric.version} (scorer {scorer.version_for(rubric)})",
        "",
        f"{len(scored)} analyzed sites, {len(with_score)} with a score. "
        f"Points: {', '.join(f'-{p}' for p in sorted(scorer.POINTS.values(), reverse=True))} "
        "for a severe, high and medium concern.",
        "",
    ]
    without = Counter(s.headline for s in scored if s.score is None)
    if without:
        lines += ["No score (by rating): " + ", ".join(f"{t} {n}" for t, n in without.most_common()), ""]
    if not values:
        return "\n".join(lines + ["Nothing to score yet."]) + "\n"

    # Histogram, high scores first, so it reads like the ratings: best at the top.
    buckets = Counter(min(v // BUCKET, (100 // BUCKET) - 1) for v in values)
    most = max(buckets.values())
    lines += ["## Histogram", "", "```"]
    for b in range(100 // BUCKET - 1, -1, -1):
        lo, hi = b * BUCKET, (b + 1) * BUCKET - 1 if b < 100 // BUCKET - 1 else 100
        lines.append(f"{lo:>3}-{hi:<3} {buckets.get(b, 0):>5}  {_bar(buckets.get(b, 0), most)}")
    lines += ["```", ""]

    # Per rating: does each range get used, or does everything sit on one value?
    lines += ["## By rating", "",
              "| Rating | Range | Sites | Min | Median | Max | Distinct values | Most common (share) | Kept in range |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for tier, (lo, hi) in scorer.BANDS.items():
        group = [s for s in with_score if s.headline == tier]
        if not group:
            lines.append(f"| {tier} | {lo} to {hi} | 0 | | | | | | |")
            continue
        vals = [s.score.value for s in group]
        top, top_n = Counter(vals).most_common(1)[0]
        adjusted = sum(s.score.adjusted for s in group)
        lines.append(
            f"| {tier} | {lo} to {hi} | {len(group)} | {min(vals)} | {statistics.median(vals):g} | {max(vals)} "
            f"| {len(set(vals))} | {top} ({top_n / len(group):.0%}) | {adjusted} |")
    lines.append("")

    lines += ["## Most common scores", "", "| Score | Sites | Share |", "| --- | --- | --- |"]
    for value, n in Counter(values).most_common(10):
        lines.append(f"| {value} | {n} | {n / len(values):.0%} |")
    lines.append("")

    deductions = Counter((d.check_id, d.status, d.points) for s in with_score for d in s.score.deductions)
    lines += ["## What takes points off", "", "| Answer | Points | Sites |", "| --- | --- | --- |"]
    for (check_id, status, points), n in deductions.most_common():
        lines.append(f"| `{check_id}` = `{status}` | -{points} | {n} |")
    lines.append("")

    adjusted = [s for s in with_score if s.score.adjusted]
    lines += ["## Kept in range", "",
              f"{len(adjusted)} of {len(with_score)} scores were moved to stay inside their rating's range."]
    for s in adjusted[:15]:
        lines.append(f"- {s.domain}: {s.headline}, {s.score.unadjusted} kept at {s.score.value}")
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, scored: list[SiteScore]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["domain", "rating", "score", "unadjusted", "deductions"])
        for s in scored:
            sc = s.score
            w.writerow([s.domain, s.headline, sc.value if sc else "", sc.unadjusted if sc else "",
                        "; ".join(f"{d.check_id}={d.status} -{d.points}" for d in sc.deductions) if sc else ""])
