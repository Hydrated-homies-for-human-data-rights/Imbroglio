"""Rubric: the published list of questions every document is checked against.

The rubric is data (YAML), versioned, and stored alongside every finding so
"the company changed" and "our ruler changed" stay distinguishable (design
goal 8). load() validates the structure so a malformed edit fails loudly
instead of silently producing wrong scores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

RUBRIC_DIR = Path(__file__).parent
NOT_DISCLOSED = "not_disclosed"
TIERS = ["LIMITED", "MODERATE", "EXTENSIVE", "SEVERE"]  # index = exposure level
# Concern levels (rubric v0.2 on, scorer s2): how much a user would worry about
# an answer. `info` marks a practice that is present but not rated as a concern
# (the site collects sensitive data); an answer with no concern is protective
# (the site doesn't sell data). In a rubric that uses concerns, each answer's
# exposure must be the one its concern implies, so the rating shown next to an
# answer and the rating it produces are the same.
CONCERN_EXPOSURE = {"severe": 3, "high": 2, "medium": 1, "info": 0, None: 0}
RATED_CONCERNS = ("severe", "high", "medium")


@dataclass(frozen=True)
class Status:
    name: str
    exposure: int
    meaning: str
    concern: str | None = None
    # Another check whose concern already covers this answer's practice, so the
    # two count once toward the overall rating (selling in the state-law sense
    # is sharing with ad partners, which shares_for_advertising also asks).
    same_concern_as: str | None = None


@dataclass(frozen=True)
class Check:
    id: str
    category: str
    question: str
    guidance: str
    statuses: dict[str, Status]
    # Words a supporting quote must contain (case-insensitive). Deterministic
    # relevance check: a real quote that isn't about the question (seen: a
    # Terms of Use clause about rule violations cited as "government
    # disclosure") doesn't count. Empty = no relevance requirement.
    evidence: tuple[str, ...] = ()
    _evidence_re: re.Pattern | None = field(default=None, compare=False, repr=False)

    def allowed(self) -> list[str]:
        return [*self.statuses, NOT_DISCLOSED]

    def relevant(self, quote: str) -> bool:
        return self._evidence_re is None or bool(self._evidence_re.search(quote))


@dataclass(frozen=True)
class Rubric:
    version: str
    categories: dict[str, str]     # key -> display name
    checks: list[Check]

    def check(self, check_id: str) -> Check:
        for c in self.checks:
            if c.id == check_id:
                return c
        raise KeyError(check_id)

    @property
    def uses_concerns(self) -> bool:
        return any(s.concern for c in self.checks for s in c.statuses.values())

    @property
    def high_concern_checks(self) -> frozenset[str]:
        """Checks with at least one severe or high concern answer: the
        questions the s2 coverage gate counts."""
        return frozenset(c.id for c in self.checks
                         if any(s.concern in ("severe", "high") for s in c.statuses.values()))


class RubricError(ValueError):
    pass


@lru_cache(maxsize=None)
def load(version: str = "v0") -> Rubric:
    raw = yaml.safe_load((RUBRIC_DIR / f"{version}.yaml").read_text(encoding="utf-8"))
    if raw.get("version") != version:
        raise RubricError(f"file {version}.yaml declares version {raw.get('version')!r}")
    categories = raw["categories"]
    checks, seen = [], set()
    for c in raw["checks"]:
        cid = c["id"]
        if cid in seen:
            raise RubricError(f"duplicate check id {cid}")
        seen.add(cid)
        if c["category"] not in categories:
            raise RubricError(f"{cid}: unknown category {c['category']}")
        statuses = {}
        for name, s in c["statuses"].items():
            name = str(name)
            if name == NOT_DISCLOSED:
                raise RubricError(f"{cid}: {NOT_DISCLOSED} is implicit, don't list it")
            if not isinstance(s, dict) or not {"exposure", "meaning"} <= set(s) <= {
                    "exposure", "meaning", "concern", "same_concern_as"}:
                # e.g. an unquoted comma inside {meaning: a, b} splits the text into a stray key
                raise RubricError(f"{cid}.{name}: expected exposure + meaning (+ concern, same_concern_as), "
                                  f"got {sorted(s or {})} (quote meanings that contain commas)")
            if s["exposure"] not in range(len(TIERS)):
                raise RubricError(f"{cid}.{name}: exposure must be 0-{len(TIERS) - 1}")
            if s.get("concern") not in CONCERN_EXPOSURE:
                raise RubricError(f"{cid}.{name}: concern must be severe, high, medium or info")
            statuses[name] = Status(name, int(s["exposure"]), s["meaning"], s.get("concern"),
                                    s.get("same_concern_as"))
        if not statuses:
            raise RubricError(f"{cid}: no statuses")
        evidence = tuple(str(e).strip().lower() for e in (c.get("evidence") or []) if str(e).strip())
        evidence_re = (re.compile("|".join(re.escape(e) for e in evidence), re.I)
                       if evidence else None)
        checks.append(Check(cid, c["category"], c["question"].strip(),
                            (c.get("guidance") or "").strip(), statuses, evidence, evidence_re))
    missing = set(categories) - {c.category for c in checks}
    if missing:
        raise RubricError(f"categories with no checks: {sorted(missing)}")
    rubric = Rubric(version, dict(categories), checks)
    for c in checks:
        for s in c.statuses.values():
            if s.same_concern_as is not None and (s.same_concern_as not in seen or s.same_concern_as == c.id):
                raise RubricError(f"{c.id}.{s.name}: same_concern_as must name another check, "
                                  f"got {s.same_concern_as!r}")
    if rubric.uses_concerns:
        for c in checks:
            for s in c.statuses.values():
                if s.exposure != CONCERN_EXPOSURE[s.concern]:
                    raise RubricError(f"{c.id}.{s.name}: concern {s.concern or 'none'} means "
                                      f"exposure {CONCERN_EXPOSURE[s.concern]}, not {s.exposure}")
    return rubric
