"""Deterministic scorer (S2, design goal 3: "the model extracts, the code scores").

Pure functions, no model calls. Same findings in, same scores out.

  * a finding counts only if verified (it has at least one confirmed quote)
  * a category's tier is the highest exposure among its counted findings
  * a category whose checks are all not_disclosed (or unverified) is NOT_DISCLOSED
  * the headline is never below the worst category (design goal 5)

Site scores combine documents: for each category the worst tier across the
site's privacy policy and terms of service wins.

Two versions, chosen by the rubric:
  s1 (rubric v0.1): the headline is the worst category.
  s2 (rubric v0.2 on, whose answers carry concern levels): "red flags +
     coverage". The headline counts concerns across the whole site, is never
     below an EXTENSIVE or SEVERE category, and is UNCLEAR when too few of the
     high-concern questions were answered to call a site's practices limited.
     A category whose answers are only informational is INFO, not LIMITED.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .rubric import NOT_DISCLOSED, RATED_CONCERNS, TIERS, Rubric

NOT_DISCLOSED_TIER = "NOT_DISCLOSED"
UNCLEAR_TIER = "UNCLEAR"         # s2 headline only, never a category
INFO_TIER = "INFO"               # s2 category only: the practice is reported, not rated
SERIOUS = ("EXTENSIVE", "SEVERE")  # s2: categories the headline can never sit below
MIN_HIGH_ANSWERED = 4            # s2 coverage gate: of the rubric's high-concern questions

# The score out of 100 (both scorers). It starts at 100 and loses points for
# each answer that raises a concern, so a reader can add it up from the
# answers on the report, then stays inside its rating's range so the number
# and the word never disagree. The points are set so that the arithmetic
# alone almost always lands in the right range under s2: one high concern
# (100 - 42 = 58) is EXTENSIVE, two medium ones (76) are MODERATE, one severe
# concern or two high ones (35, 16) are SEVERE.
START = 100
POINTS = {3: 65, 2: 42, 1: 12}   # by the answer's exposure: severe, high, medium concern
BANDS = {"LIMITED": (80, 100), "MODERATE": (60, 79), "EXTENSIVE": (40, 59), "SEVERE": (0, 39)}
_SCORE_COMMON = (
    "The score always stays in its rating's range: LIMITED 80 to 100, MODERATE 60 to 79, "
    "EXTENSIVE 40 to 59, SEVERE 0 to 39. An UNCLEAR or NOT DISCLOSED site gets no score, so "
    "silence never earns points."
)
SCORE_RULE_S1 = ("Every rated site also gets a score out of 100, higher is better. It starts at 100 and "
                 "loses 65 points for each SEVERE answer, 42 for each EXTENSIVE one and 12 for each "
                 "MODERATE one. " + _SCORE_COMMON)
SCORE_RULE_S2 = ("Every rated site also gets a score out of 100, higher is better. It starts at 100 and "
                 "loses 65 points for each severe concern, 42 for each high one and 12 for each medium "
                 "one, counted the same way as the overall rating. " + _SCORE_COMMON)
# Published on the website's "How we score" page (GET /v1/rubric). Keep these
# in step with the code below: they are the rules each version applies.
_COMMON_FIRST = [
    "Only verified findings count: each needs at least one quote found word for word in the "
    "document and about the question asked.",
]
_COMMON_LAST = [
    "A category the documents don't address is NOT DISCLOSED. Silence is reported, never "
    "filled in by guessing.",
    "When a site has both a privacy policy and terms of service, each category takes the "
    "worse of the two ratings.",
]
_NO_MODEL = ("No AI model ever assigns a rating. The model only answers the questions and quotes the "
             "document; this code does the scoring.")
RULES_S1 = [
    *_COMMON_FIRST,
    "Each answer in the rubric has an exposure level, from LIMITED to SEVERE. A category's "
    "rating is the highest exposure among its verified findings.",
    *_COMMON_LAST,
    "The overall rating is the worst category, never an average, so one serious practice "
    "can't be hidden behind good ones.",
    SCORE_RULE_S1,
    _NO_MODEL,
]
RULES_S2 = [
    *_COMMON_FIRST,
    "Each answer is a severe, high or medium concern, informational (the practice is present "
    "but not rated), or protective. A category's rating is its most concerning answer: SEVERE "
    "for a severe concern, EXTENSIVE for a high one, MODERATE for a medium one, INFO when "
    "its answers are informational, LIMITED when every answer is protective.",
    *_COMMON_LAST,
    "The overall rating counts concerns across the whole site: SEVERE for any severe concern "
    "(selling data for money, or no way to delete it) or two or more high ones, EXTENSIVE for "
    "one high concern, MODERATE for two or more medium ones, LIMITED otherwise. Two answers "
    "about the same practice count once. It is never below an EXTENSIVE or SEVERE category, "
    "so one serious practice can't be hidden, and never an average.",
    f"A site is only rated LIMITED if at least {MIN_HIGH_ANSWERED} of the high-concern "
    "questions were answered. Otherwise it is UNCLEAR: we couldn't confirm enough to say its "
    "practices are limited, so silence is never read as good.",
    SCORE_RULE_S2,
    _NO_MODEL,
]
TIER_MEANINGS = {
    "SEVERE": "The practice is present at its broadest, with no meaningful limit or choice disclosed.",
    "EXTENSIVE": "The practice is present and broad, with some limit or choice disclosed.",
    "MODERATE": "The practice is present with clear limits, or a choice the user can exercise.",
    "LIMITED": "The practice is narrow, absent, or the user is protected by a specific commitment.",
    NOT_DISCLOSED_TIER: "The documents say nothing about the practice.",
}
UNCLEAR_MEANING = ("Too few of the key questions were answered to say this site's practices are "
                   "limited. Overall rating only.")
INFO_MEANING = ("The documents describe the practice, and we report what they say without rating "
                "it as a concern. Categories only.")
# Ordering for "worst": a disclosed SEVERE beats everything; NOT_DISCLOSED sits
# below every disclosed tier so silence never outranks a stated practice. INFO
# sits above LIMITED: a category is LIMITED only if every answer is protective.
_RANK = {NOT_DISCLOSED_TIER: -1, **{t: i for i, t in enumerate(TIERS)}, INFO_TIER: 0.5}


def version_for(rubric: Rubric) -> str:
    return "s2" if rubric.uses_concerns else "s1"


def rules_for(rubric: Rubric) -> list[str]:
    return RULES_S2 if rubric.uses_concerns else RULES_S1


def tier_meanings(rubric: Rubric) -> dict[str, str]:
    if not rubric.uses_concerns:
        return TIER_MEANINGS
    return {**TIER_MEANINGS, INFO_TIER: INFO_MEANING, UNCLEAR_TIER: UNCLEAR_MEANING}


def answer_tier(status) -> str:
    """The rating an answer leads to, as shown next to it."""
    return INFO_TIER if status.concern == "info" else TIERS[status.exposure]


@dataclass(frozen=True)
class ScoredFinding:
    check_id: str
    status: str
    verified: bool


def _counted(rubric: Rubric, findings: list[ScoredFinding]):
    """(check, status) for every finding that counts: verified, disclosed, and
    an answer the rubric allows (unknown ones were rejected upstream; never guess)."""
    for f in findings:
        if not f.verified or f.status == NOT_DISCLOSED:
            continue
        check = rubric.check(f.check_id)
        status = check.statuses.get(f.status)
        if status is not None:
            yield check, status


def category_tiers(rubric: Rubric, findings: list[ScoredFinding]) -> dict[str, str]:
    worst: dict[str, str] = {}
    for check, status in _counted(rubric, findings):
        tier = answer_tier(status)
        if check.category not in worst or _RANK[tier] > _RANK[worst[check.category]]:
            worst[check.category] = tier
    return {cat: worst.get(cat, NOT_DISCLOSED_TIER) for cat in rubric.categories}


def combine(*per_document: dict[str, str]) -> dict[str, str]:
    """Worst tier per category across a site's documents."""
    out: dict[str, str] = {}
    for tiers in per_document:
        for cat, tier in tiers.items():
            if cat not in out or _RANK[tier] > _RANK[out[cat]]:
                out[cat] = tier
    return out


def headline(tiers: dict[str, str]) -> str:
    """The worst category (s1's headline, and s2's floor)."""
    return max(tiers.values(), key=lambda t: _RANK[t]) if tiers else NOT_DISCLOSED_TIER


def site_answers(rubric: Rubric, findings: list[ScoredFinding]) -> dict[str, str]:
    """One answer per check across a site's documents: the most exposed one
    that counts."""
    out: dict[str, str] = {}
    for check, status in _counted(rubric, findings):
        if check.id not in out or status.exposure > check.statuses[out[check.id]].exposure:
            out[check.id] = status.name
    return out


def _concerns(rubric: Rubric, answers: dict[str, str]) -> list[tuple[str, str]]:
    """(check_id, status) of every answer that counts as a concern toward the
    overall rating. s2: a rated concern, with two answers about the same
    practice counted once. s1: every answer with an exposure above LIMITED."""
    status = {c: rubric.check(c).statuses[s] for c, s in answers.items()}
    if not rubric.uses_concerns:
        return [(c, s.name) for c, s in status.items() if s.exposure > 0]
    return [(c, s.name) for c, s in status.items()
            if s.concern in RATED_CONCERNS
            # counted once with the other check's concern about the same practice
            and not (s.same_concern_as in status and status[s.same_concern_as].concern in RATED_CONCERNS)]


def rate(rubric: Rubric, findings: list[ScoredFinding]) -> tuple[dict[str, str], str]:
    """Category tiers and headline for a site, from the findings of all its
    latest documents together (or for one document, from its own)."""
    tiers = category_tiers(rubric, findings)
    worst = headline(tiers)
    if not rubric.uses_concerns or worst == NOT_DISCLOSED_TIER:
        return tiers, worst
    answers = site_answers(rubric, findings)
    concerns = [rubric.check(c).statuses[s].concern for c, s in _concerns(rubric, answers)]
    high = concerns.count("high")
    if "severe" in concerns or high >= 2:
        flags = "SEVERE"
    elif high:
        flags = "EXTENSIVE"
    elif concerns.count("medium") >= 2:
        flags = "MODERATE"
    else:
        flags = "LIMITED"
    # Never below a serious category (design goal 5). One medium concern alone
    # leaves its category MODERATE but the site can still be LIMITED overall.
    head = max(flags, worst if worst in SERIOUS else "LIMITED", key=lambda t: _RANK[t])
    if head == "LIMITED" and len(rubric.high_concern_checks & answers.keys()) < MIN_HIGH_ANSWERED:
        head = UNCLEAR_TIER
    return tiers, head


@dataclass(frozen=True)
class Deduction:
    check_id: str
    status: str
    points: int


@dataclass(frozen=True)
class Score:
    value: int                       # what is shown: START minus the deductions, kept in the band
    deductions: list[Deduction] = field(default_factory=list)
    band: tuple[int, int] = (0, 100)
    unadjusted: int = START          # START minus the deductions, before keeping it in the band

    @property
    def adjusted(self) -> bool:
        return self.value != self.unadjusted


def score(rubric: Rubric, findings: list[ScoredFinding], head: str | None = None) -> Score | None:
    """The site's score out of 100 (see SCORE_RULE_S1/S2), or None when its
    overall rating is UNCLEAR or NOT_DISCLOSED. Pass the headline from rate()
    if you already have it."""
    head = head if head is not None else rate(rubric, findings)[1]
    if head not in BANDS:
        return None
    answers = site_answers(rubric, findings)
    deductions = sorted(
        (Deduction(c, s, POINTS[rubric.check(c).statuses[s].exposure]) for c, s in _concerns(rubric, answers)),
        key=lambda d: (-d.points, [c.id for c in rubric.checks].index(d.check_id)))
    raw = START - sum(d.points for d in deductions)
    lo, hi = BANDS[head]
    return Score(min(max(raw, lo), hi), deductions, (lo, hi), raw)
