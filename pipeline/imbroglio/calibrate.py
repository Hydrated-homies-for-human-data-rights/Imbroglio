"""Rubric calibration lab: try scoring schemes on stored findings, at no cost.

    python -m imbroglio.cli calibrate
    python -m imbroglio.cli calibrate --out runs/calibration.md

Read-only. Scoring is plain code over findings already in the database, so a
new weighting can be compared on every analyzed site in seconds without a
single LLM call. Only changes to the questions themselves need a new
extraction.

A scheme maps a site's answers (one status per check, the worst across its
privacy policy and terms) to a headline tier plus the reasons behind it. The
report shows how well each scheme tells sites apart and how its ranking lines
up with ToS;DR's human grades where we overlap. ToS;DR grades cover more than
privacy (arbitration, account termination, ...), so agreement is a sanity
check, not a target.
"""

from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import scorer
from .rubric import NOT_DISCLOSED, TIERS, Rubric, load

ND = scorer.NOT_DISCLOSED_TIER
UNCLEAR = "UNCLEAR"     # too little was answered to call a site clean
GRADES = "ABCDE"


@dataclass
class Result:
    headline: str
    reasons: list[str] = field(default_factory=list)
    points: float | None = None     # finer-grained score, when the scheme has one


@dataclass(frozen=True)
class Scheme:
    key: str
    name: str
    description: str
    score: Callable[[Rubric, dict[str, str]], Result]


def site_answers(rubric: Rubric, findings: list[tuple[str, str, bool]]) -> dict[str, str]:
    """(check_id, status, verified) across a site's documents -> one status per
    check: the most exposed verified answer. Unverified and not_disclosed
    findings are dropped, the same as the production scorer."""
    out: dict[str, str] = {}
    for check_id, status, verified in findings:
        if not verified or status == NOT_DISCLOSED:
            continue
        statuses = rubric.check(check_id).statuses
        if status not in statuses:
            continue
        if check_id not in out or statuses[status].exposure > statuses[out[check_id]].exposure:
            out[check_id] = status
    return out


def _meaning(rubric: Rubric, check_id: str, status: str) -> str:
    return rubric.check(check_id).statuses[status].meaning


# --- schemes -----------------------------------------------------------------

def _current(rubric, answers):
    """Production scorer s1: category = worst exposure, headline = worst category."""
    tiers = scorer.category_tiers(rubric, [scorer.ScoredFinding(c, s, True) for c, s in answers.items()])
    h = scorer.headline(tiers)
    reasons = [_meaning(rubric, c, s) for c, s in answers.items()
               if TIERS[rubric.check(c).statuses[s].exposure] == h] if h != ND else []
    return Result(h, reasons)


# Boilerplate that nearly every policy contains: still shown, but it can no
# longer set the headline on its own.
CAPPED_EXPOSURE = {
    ("collects_from_third_parties", "yes"): 1,
    ("collects_sensitive_data", "yes"): 1,     # can't yet tell payment cards from health data
    ("content_license", "broad"): 1,           # needed just to host user content
    ("security_measures", "generic"): 1,
    ("retention_period", "vague"): 1,
    ("discloses_to_government", "broad"): 1,
    ("trains_ai_on_user_data", "yes"): 2,
}
CATEGORY_CAP = {"government": 1, "security": 1}   # at most MODERATE


def _capped(rubric, answers):
    worst, reasons = -1, {}
    for c, s in answers.items():
        check = rubric.check(c)
        e = CAPPED_EXPOSURE.get((c, s), check.statuses[s].exposure)
        e = min(e, CATEGORY_CAP.get(check.category, len(TIERS) - 1))
        reasons.setdefault(e, []).append(check.statuses[s].meaning)
        worst = max(worst, e)
    if worst < 0:
        return Result(ND)
    return Result(TIERS[worst], reasons[worst])


# What a user would actually worry about. High: the site does something with
# your data you can't undo or avoid. Medium: worth knowing. Everything else
# (government requests under legal process, generic security wording, the
# license needed to host content) is informational.
HIGH_CONCERN = {
    ("sells_personal_data", "yes"),
    ("retention_period", "indefinite"),
    ("deletion_on_request", "no"),
    ("access_and_export", "no"),
    ("opt_out_of_tracking", "no"),
    ("trains_ai_on_user_data", "yes"),
}
MEDIUM_CONCERN = {
    ("shares_for_advertising", "yes"),
    ("deletion_on_request", "some_jurisdictions"),
    ("access_and_export", "some_jurisdictions"),
    ("opt_out_of_tracking", "limited"),
    ("retention_period", "vague"),
    ("breach_notification", "no"),
}


def _red_flags(rubric, answers):
    if not answers:
        return Result(ND)
    high = [_meaning(rubric, c, s) for c, s in answers.items() if (c, s) in HIGH_CONCERN]
    medium = [_meaning(rubric, c, s) for c, s in answers.items() if (c, s) in MEDIUM_CONCERN]
    if len(high) >= 2:
        h = "SEVERE"
    elif high:
        h = "EXTENSIVE"
    elif len(medium) >= 2:
        h = "MODERATE"
    else:
        h = "LIMITED"
    return Result(h, high + medium, points=3 * len(high) + len(medium))


HIGH_CONCERN_CHECKS = {c for c, _ in HIGH_CONCERN}
MIN_HIGH_ANSWERED = 4   # of the 6 high-concern checks


def _red_flags_coverage(rubric, answers):
    """Red flags, but a site with no red flag is only called clean if most of
    the high-concern questions were actually answered. Otherwise UNCLEAR:
    silence is reported, never read as good (design goal 4)."""
    r = _red_flags(rubric, answers)
    if r.headline in ("LIMITED", "MODERATE"):
        answered = len(HIGH_CONCERN_CHECKS & set(answers))
        if answered < MIN_HIGH_ANSWERED:
            return Result(UNCLEAR, [f"only {answered} of {len(HIGH_CONCERN_CHECKS)} "
                                    "high-concern questions answered"] + r.reasons, r.points)
    return r


# Points: bad practices add, good practices subtract, scaled by user concern.
POINTS = {
    "sells_personal_data": {"yes": 6, "no": -2},
    "shares_for_advertising": {"yes": 3, "service_providers_only": 1, "no": -2},
    "collects_sensitive_data": {"yes": 1, "no": -1},
    "collects_from_third_parties": {"yes": 1, "no": -1},
    "retention_period": {"indefinite": 4, "vague": 1, "specific": -2},
    "deletion_on_request": {"no": 5, "some_jurisdictions": 2, "all_users": -2},
    "access_and_export": {"no": 3, "some_jurisdictions": 1, "all_users": -1},
    "opt_out_of_tracking": {"no": 4, "limited": 1, "yes": -1},
    "security_measures": {"generic": 0, "specific": -1},
    "breach_notification": {"no": 1, "yes": -1},
    "trains_ai_on_user_data": {"yes": 4, "opt_in": 0, "no": -3},
    "content_license": {"broad": 1, "limited": -1},
    "discloses_to_government": {"broad": 1, "legal_process_required": 0},
    "notifies_users_of_requests": {"no": 0, "yes": -1},
}
POINT_TIERS = [(12, "SEVERE"), (7, "EXTENSIVE"), (3, "MODERATE")]   # below 3: LIMITED


def _points(rubric, answers):
    if not answers:
        return Result(ND)
    scored = [(POINTS.get(c, {}).get(s, 0), _meaning(rubric, c, s)) for c, s in answers.items()]
    total = sum(p for p, _ in scored)
    h = next((t for floor, t in POINT_TIERS if total >= floor), "LIMITED")
    reasons = [f"{p:+d} {m}" for p, m in sorted(scored, key=lambda x: -abs(x[0])) if p]
    return Result(h, reasons, points=total)


SCHEMES = [
    Scheme("current", "Current (s1)", "Worst category sets the headline; v0.1 exposure levels.", _current),
    Scheme("capped", "Capped boilerplate",
           "Same worst-category rule, but near-universal boilerplate is capped at MODERATE, "
           "government and security can't exceed MODERATE, and AI training tops out at EXTENSIVE.",
           _capped),
    Scheme("flags", "Red flags",
           "Count high-concern practices: 2+ is SEVERE, 1 is EXTENSIVE; otherwise 2+ medium "
           "concerns is MODERATE, else LIMITED.", _red_flags),
    Scheme("flags+coverage", "Red flags + coverage",
           f"Red flags, but a site without a red flag is UNCLEAR unless at least "
           f"{MIN_HIGH_ANSWERED} of the 6 high-concern questions were answered.", _red_flags_coverage),
    Scheme("points", "Concern points",
           "Bad practices add points and good ones subtract, weighted by user concern; "
           "12+ SEVERE, 7+ EXTENSIVE, 3+ MODERATE.", _points),
]


# --- metrics -----------------------------------------------------------------

def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1     # ties share the average rank
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return cov / (vx * vy) if vx and vy else None


def spread(headlines: list[str]) -> float:
    """Normalized entropy over the four tiers: 0 = every site the same, 1 = even."""
    counts = Counter(h for h in headlines if h in TIERS)
    n = sum(counts.values())
    if not n:
        return 0.0
    return -sum(c / n * math.log(c / n) for c in counts.values()) / math.log(len(TIERS))


def load_tosdr(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {r["domain"].lower().removeprefix("www."): r["rating"]
                for r in csv.DictReader(f) if r.get("rating") in set(GRADES)}


def load_sites(conn, rubric: Rubric) -> dict[str, dict[str, str]]:
    rows = conn.execute(
        """WITH latest AS (
             SELECT DISTINCT ON (v.document_id) v.id, v.document_id
             FROM document_versions v
             WHERE EXISTS (SELECT 1 FROM findings f WHERE f.version_id = v.id AND f.rubric_version = %s)
             ORDER BY v.document_id, v.fetched_at DESC)
           SELECT s.domain, f.check_id, f.status, f.verified
           FROM latest l JOIN documents d ON d.id = l.document_id
           JOIN services s ON s.id = d.service_id
           JOIN findings f ON f.version_id = l.id AND f.rubric_version = %s""",
        (rubric.version, rubric.version)).fetchall()
    per_site = defaultdict(list)
    for domain, check_id, status, verified in rows:
        per_site[domain].append((check_id, status, verified))
    return {d: site_answers(rubric, fs) for d, fs in sorted(per_site.items())}


# --- report ------------------------------------------------------------------

def evaluate(rubric: Rubric, sites: dict[str, dict[str, str]], tosdr: dict[str, str],
             schemes: list[Scheme] = SCHEMES) -> str:
    results = {s.key: {d: s.score(rubric, a) for d, a in sites.items()} for s in schemes}
    graded = [d for d in sites if d in tosdr]
    grade_mix = Counter(tosdr[d] for d in graded)

    lines = [f"# Rubric calibration — rubric {rubric.version}", "",
             f"{len(sites)} analyzed sites, {len(graded)} also graded by ToS;DR "
             f"({', '.join(f'{g} {grade_mix[g]}' for g in GRADES if grade_mix[g])}). "
             "Spread: 0 = every site gets the same tier, 1 = evenly spread. "
             "ToS;DR agreement: Spearman rank correlation with their A–E grade "
             "(1 = same order, 0 = unrelated).", "",
             "| Scheme | SEVERE | EXTENSIVE | MODERATE | LIMITED | Unclear | Not disclosed | Spread | ToS;DR agreement |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for s in schemes:
        heads = [r.headline for r in results[s.key].values()]
        c = Counter(heads)
        pairs = [(results[s.key][d], GRADES.index(tosdr[d])) for d in graded
                 if results[s.key][d].headline in TIERS]
        rho = spearman([r.points if r.points is not None else TIERS.index(r.headline) for r, _ in pairs],
                       [g for _, g in pairs])
        lines.append(f"| {s.name} | {c['SEVERE']} | {c['EXTENSIVE']} | {c['MODERATE']} | {c['LIMITED']} | "
                     f"{c[UNCLEAR]} | {c[ND]} | {spread(heads):.2f} | "
                     f"{'n/a' if rho is None else f'{rho:.2f}'} (n={len(pairs)}) |")

    lines += ["", "## Schemes", ""] + [f"- **{s.name}**: {s.description}" for s in schemes]

    lines += ["", "## How often each answer appears", "",
              "Share of sites giving each answer (sites that don't address a check are left out). "
              "An answer nearly every site gives can't tell sites apart.", "",
              "| Check | Answers (sites) | Not addressed |", "| --- | --- | --- |"]
    for c in rubric.checks:
        counts = Counter(a[c.id] for a in sites.values() if c.id in a)
        silent = sum(c.id not in a for a in sites.values())
        lines.append(f"| {c.id} | " + ", ".join(f"{k} {v}" for k, v in counts.most_common())
                     + f" | {silent} of {len(sites)} |")

    lines += ["", "## Per site", "",
              f"Answered: how many of the {len(rubric.checks)} checks the site's documents address.", "",
              "| Site | Answered | ToS;DR | " + " | ".join(s.name for s in schemes) + " |",
              "| --- | --- | --- | " + " | ".join("---" for _ in schemes) + " |"]
    for d in sites:
        cells = []
        for s in schemes:
            r = results[s.key][d]
            cells.append(r.headline + (f" ({r.points:g})" if r.points is not None else ""))
        lines.append(f"| {d} | {len(sites[d])} | {tosdr.get(d, '')} | " + " | ".join(cells) + " |")

    lines += ["", "## Why: reasons under each new scheme", ""]
    for d in sites:
        lines.append(f"**{d}**")
        for s in schemes[1:]:
            r = results[s.key][d]
            lines.append(f"- {s.name}: {r.headline}" + (f" — {'; '.join(r.reasons)}" if r.reasons else ""))
        lines.append("")
    return "\n".join(lines)


def run(rubric_version: str = "v0.1", tosdr_csv: Path = Path("seeds/tosdr_rated.csv")) -> str:
    from . import db

    rubric = load(rubric_version)
    conn = db.connect()
    try:
        sites = load_sites(conn, rubric)
    finally:
        conn.close()
    return evaluate(rubric, sites, load_tosdr(tosdr_csv))
