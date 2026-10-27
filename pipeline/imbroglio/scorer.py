"""Deterministic scorer (S2, design goal 3: "the model extracts, the code scores").

Pure functions, no model calls. Same findings in, same scores out.

  * a finding counts only if verified (it has at least one confirmed quote)
  * a category's tier is the highest exposure among its counted findings
  * a category whose checks are all not_disclosed (or unverified) is NOT_DISCLOSED
  * the headline is the worst category, never an average (design goal 5)

Site scores combine documents: for each category the worst tier across the
site's privacy policy and terms of service wins.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rubric import NOT_DISCLOSED, TIERS, Rubric

SCORER_VERSION = "s1"
NOT_DISCLOSED_TIER = "NOT_DISCLOSED"

# Published on the website's "How we score" page (GET /v1/rubric). Keep these
# in step with the code below: they are the rules this version applies.
RULES = [
    "Only verified findings count: each needs at least one quote found word for word in the "
    "document and about the question asked.",
    "Each answer in the rubric has an exposure level, from LIMITED to SEVERE. A category's "
    "rating is the highest exposure among its verified findings.",
    "A category the documents don't address is NOT DISCLOSED. Silence is reported, never "
    "filled in by guessing.",
    "When a site has both a privacy policy and terms of service, each category takes the "
    "worse of the two ratings.",
    "The overall rating is the worst category, never an average, so one serious practice "
    "can't be hidden behind good ones.",
    "No AI model ever assigns a rating. The model only answers the questions and quotes the "
    "document; this code does the scoring.",
]
TIER_MEANINGS = {
    "SEVERE": "The practice is present at its broadest, with no meaningful limit or choice disclosed.",
    "EXTENSIVE": "The practice is present and broad, with some limit or choice disclosed.",
    "MODERATE": "The practice is present with clear limits, or a choice the user can exercise.",
    "LIMITED": "The practice is narrow, absent, or the user is protected by a specific commitment.",
    NOT_DISCLOSED_TIER: "The documents say nothing about the practice.",
}
# Ordering for "worst": a disclosed SEVERE beats everything; NOT_DISCLOSED sits
# below every disclosed tier so silence never outranks a stated practice.
_RANK = {NOT_DISCLOSED_TIER: -1, **{t: i for i, t in enumerate(TIERS)}}


@dataclass(frozen=True)
class ScoredFinding:
    check_id: str
    status: str
    verified: bool


def category_tiers(rubric: Rubric, findings: list[ScoredFinding]) -> dict[str, str]:
    worst: dict[str, int] = {}
    for f in findings:
        if not f.verified or f.status == NOT_DISCLOSED:
            continue
        check = rubric.check(f.check_id)
        status = check.statuses.get(f.status)
        if status is None:
            continue  # unknown status was already rejected upstream; never guess
        worst[check.category] = max(worst.get(check.category, -1), status.exposure)
    return {cat: TIERS[worst[cat]] if cat in worst else NOT_DISCLOSED_TIER
            for cat in rubric.categories}


def combine(*per_document: dict[str, str]) -> dict[str, str]:
    """Worst tier per category across a site's documents."""
    out: dict[str, str] = {}
    for tiers in per_document:
        for cat, tier in tiers.items():
            if cat not in out or _RANK[tier] > _RANK[out[cat]]:
                out[cat] = tier
    return out


def headline(tiers: dict[str, str]) -> str:
    return max(tiers.values(), key=lambda t: _RANK[t]) if tiers else NOT_DISCLOSED_TIER
