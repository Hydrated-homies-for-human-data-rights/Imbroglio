"""Site search (use case UC1): type a name or domain, get matching sites.

Ranking is done in Python over the whole catalogue (domain, name), which is
cached briefly. That's fast well past 10,000 sites; if the catalogue grows
far beyond that, move it into Postgres with the pg_trgm extension.

Order: exact domain, exact brand or name, prefix, substring, then close
spellings ("facebok" -> facebook.com). Analyzed sites win ties.
"""

from __future__ import annotations

import difflib
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from .locate import brand_of

MIN_QUERY = 2
TYPO_RATIO = 0.75       # SequenceMatcher ratio for a "close spelling"
CACHE_SECONDS = 60


@dataclass(frozen=True)
class Entry:
    domain: str
    name: str | None
    documents: tuple[str, ...]
    headline: str | None     # None until analyzed
    concerns: tuple[str, ...] = ()           # category names rated EXTENSIVE or SEVERE
    analyzed_at: datetime | None = None
    last_changed: datetime | None = None      # newest detected policy change


def normalize(query: str) -> str:
    """'https://www.Facebook.com/privacy' -> 'facebook.com'; 'Face Book' -> 'face book'."""
    q = query.strip().lower()
    q = re.sub(r"^[a-z]+://", "", q)
    q = q.split("/")[0].split("?")[0] if "." in q.split("/")[0] else q
    return q.removeprefix("www.").strip()


def score(q: str, e: Entry) -> float:
    brand = brand_of(e.domain)
    name = (e.name or "").lower()
    if q == e.domain:
        return 100
    if q in (brand, name):
        return 90
    words = name.split()
    if e.domain.startswith(q) or brand.startswith(q) or any(w.startswith(q) for w in words):
        return 80
    if q in e.domain or (name and q in name):
        return 60
    if len(q) >= 3:
        bare = q.split(".")[0]          # "facebok.com" -> compare "facebok" with the brand
        ratio = max(difflib.SequenceMatcher(None, bare, brand).ratio(),
                    difflib.SequenceMatcher(None, q, name).ratio() if name else 0)
        if ratio >= TYPO_RATIO:
            return 40 * ratio
    return 0


def search(query: str, entries: list[Entry], limit: int = 10) -> list[Entry]:
    q = normalize(query)
    if len(q) < MIN_QUERY:
        return []
    scored = [(score(q, e), e) for e in entries]
    scored = [(s, e) for s, e in scored if s > 0]
    scored.sort(key=lambda se: (-se[0], se[1].headline is None, not se[1].documents,
                                len(se[1].domain), se[1].domain))
    return [e for _, e in scored[:limit]]


# --- catalogue cache -----------------------------------------------------------

_cache: tuple[float, list[Entry]] | None = None
_lock = threading.Lock()


def catalogue(conn, rubric_version: str) -> list[Entry]:
    global _cache
    with _lock:
        if _cache and time.monotonic() - _cache[0] < CACHE_SECONDS:
            return _cache[1]
    from . import db, scorer
    from .rubric import load

    rubric = load(rubric_version)
    # per analyzed site: its headline, the categories rated EXTENSIVE or SEVERE
    # across its latest documents, and when it was last analyzed
    heads: dict[str, str] = {}
    concerns: dict[str, set[str]] = {}
    analyzed: dict[str, datetime] = {}
    for domain, found in db.site_findings(conn, rubric_version).items():
        tiers, heads[domain] = scorer.rate(rubric, [scorer.ScoredFinding(c, s, v) for _, c, s, v, _ in found])
        concerns[domain] = {rubric.categories[c] for c, t in tiers.items() if t in ("EXTENSIVE", "SEVERE")}
        analyzed[domain] = max(created for *_, created in found)
    rows = conn.execute(
        """SELECT s.domain, s.name,
                  coalesce(array_agg(DISTINCT d.doc_type ORDER BY d.doc_type)
                           FILTER (WHERE d.doc_type IS NOT NULL), '{}'),
                  (SELECT max(c.detected_at) FROM change_events c
                   JOIN documents d2 ON d2.id = c.document_id WHERE d2.service_id = s.id)
           FROM services s LEFT JOIN documents d ON d.service_id = s.id
           GROUP BY s.id, s.domain, s.name""").fetchall()
    entries = [Entry(domain, name, tuple(docs), heads.get(domain),
                     tuple(sorted(concerns.get(domain, ()))), analyzed.get(domain), changed)
               for domain, name, docs, changed in rows]
    with _lock:
        _cache = (time.monotonic(), entries)
    return entries


def clear_cache() -> None:
    global _cache
    with _lock:
        _cache = None
