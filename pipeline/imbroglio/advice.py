"""What a user can do about each finding (advice.yaml).

Advice is shown next to findings and on the website's learn pages. It never
affects a rating, so it lives outside the versioned rubric; load() checks it
against a rubric so a renamed check or status fails loudly instead of
silently dropping advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .rubric import Rubric

ADVICE_FILE = Path(__file__).parent / "advice.yaml"


@dataclass(frozen=True)
class Step:
    text: str
    link: str | None = None


@dataclass(frozen=True)
class Advice:
    check_id: str
    title: str
    why: str
    applies_to: tuple[str, ...]
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class Guide:
    id: str
    title: str
    body: str


@dataclass(frozen=True)
class AdviceBook:
    checks: dict[str, Advice]
    general: tuple[Guide, ...]

    def for_finding(self, check_id: str, status: str) -> Advice | None:
        a = self.checks.get(check_id)
        return a if a is not None and status in a.applies_to else None


class AdviceError(ValueError):
    pass


def _link(where: str, link) -> str | None:
    if link is None:
        return None
    if not isinstance(link, str) or not link.startswith("https://"):
        raise AdviceError(f"{where}: links must be https:// URLs, got {link!r}")
    return link


def parse(raw: dict, rubric: Rubric) -> AdviceBook:
    checks = {}
    for check_id, a in (raw.get("checks") or {}).items():
        try:
            check = rubric.check(check_id)
        except KeyError:
            raise AdviceError(f"{check_id}: not a check in rubric {rubric.version}") from None
        listed = tuple(str(s) for s in a.get("applies_to") or [])
        if not listed:
            raise AdviceError(f"{check_id}: applies_to is empty")
        # One advice file serves every rubric version, so it may name answers
        # another version has (v0.1's "yes" to selling, v0.2's sold_for_money).
        # Each version keeps its own; tests check every name exists somewhere.
        applies = tuple(s for s in listed if s in check.statuses)
        if not applies:
            raise AdviceError(f"{check_id}: applies_to {list(listed)} is not a status of this check "
                              f"in rubric {rubric.version}")
        steps = tuple(Step(str(s["text"]).strip(), _link(check_id, s.get("link")))
                      for s in a.get("steps") or [])
        if not steps or any(not s.text for s in steps):
            raise AdviceError(f"{check_id}: needs at least one step, each with text")
        checks[check_id] = Advice(check_id, str(a["title"]).strip(), str(a["why"]).strip(),
                                  applies, steps)
    general = tuple(Guide(str(g["id"]), str(g["title"]).strip(), " ".join(str(g["body"]).split()))
                    for g in raw.get("general") or [])
    return AdviceBook(checks, general)


@lru_cache(maxsize=None)
def load(rubric_version: str) -> AdviceBook:
    from .rubric import load as load_rubric
    raw = yaml.safe_load(ADVICE_FILE.read_text(encoding="utf-8"))
    return parse(raw, load_rubric(rubric_version))
