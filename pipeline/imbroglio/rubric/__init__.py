"""Rubric: the published list of questions every document is checked against.

The rubric is data (YAML), versioned, and stored alongside every finding so
"the company changed" and "our ruler changed" stay distinguishable (design
goal 8). load() validates the structure so a malformed edit fails loudly
instead of silently producing wrong scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

RUBRIC_DIR = Path(__file__).parent
NOT_DISCLOSED = "not_disclosed"
TIERS = ["LIMITED", "MODERATE", "EXTENSIVE", "SEVERE"]  # index = exposure level


@dataclass(frozen=True)
class Status:
    name: str
    exposure: int
    meaning: str


@dataclass(frozen=True)
class Check:
    id: str
    category: str
    question: str
    guidance: str
    statuses: dict[str, Status]

    def allowed(self) -> list[str]:
        return [*self.statuses, NOT_DISCLOSED]


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
            if s["exposure"] not in range(len(TIERS)):
                raise RubricError(f"{cid}.{name}: exposure must be 0-{len(TIERS) - 1}")
            statuses[name] = Status(name, int(s["exposure"]), s["meaning"])
        if not statuses:
            raise RubricError(f"{cid}: no statuses")
        checks.append(Check(cid, c["category"], c["question"].strip(),
                            (c.get("guidance") or "").strip(), statuses))
    missing = set(categories) - {c.category for c in checks}
    if missing:
        raise RubricError(f"categories with no checks: {sorted(missing)}")
    return Rubric(version, dict(categories), checks)
