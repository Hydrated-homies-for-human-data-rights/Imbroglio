"""Orchestrator: domain -> located, normalized, stored document versions.

This is the vertical-slice spine. Today it runs discovery -> extraction ->
normalization -> storage -> change detection. Later stages plug in where
marked, each behind its module owner's interface:

    classify(text)          -> [(segment, categories)]        (Gage)
    llm_extract(segments)   -> findings with quotes           (Gage/Alex)
    verify_quotes(findings, text) -> quote_verified flags     (Gage/Alex)
    score(findings)         -> category scores                (Sam)

Re-fetching an unchanged document is a no-op by design: identical content
hash means no new version row, no change event, and (later) no LLM spend —
the analyze-once-and-cache economics the proposal is built on.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from . import SERVER_ONLY, db

log = logging.getLogger("imbroglio")
from .extract import extract_text
from .locate import MAX_TEXT_CHARS, Located, locate_all
from .normalize import content_hash, normalize


@dataclass
class DocOutcome:
    doc_type: str
    status: str            # stored-new | unchanged | changed | held | failed
    url: str | None = None
    version_id: int | None = None
    chars: int = 0
    notes: str = ""
    content_hash: str | None = None
    discovered_via: str | None = None
    fetch_method: str | None = None

    @property
    def found(self) -> bool:
        # "held": discovery found the page a person marked as wrong again,
        # which for every reader is the same as not finding the document.
        return self.status not in ("failed", "held")


def analyze(domain: str, use_playwright: bool = True,
            dsn: str | None = None, store: bool = True,
            init_schema: bool = True,
            time_budget: float | None = None,
            policy_url: str | None = None) -> list[DocOutcome]:
    located = locate_all(domain, use_playwright=use_playwright, time_budget=time_budget,
                         policy_url=policy_url)
    outcomes: list[DocOutcome] = []

    conn = db.connect(dsn) if store else None
    try:
        if conn is not None:
            if init_schema:  # batch runs init once up front; concurrent DDL races
                db.init_schema(conn)
            service_id = db.upsert_service(conn, domain)

        for doc_type, loc in located.items():
            if not loc.ok:
                outcomes.append(DocOutcome(doc_type, "failed",
                                           notes="; ".join(loc.notes)[:2000]))
                continue

            text = normalize(loc.text)
            log.info("[%s] normalized to %s chars, sha256 %s…",
                     doc_type, f"{len(text):,}", content_hash(text)[:12])

            if conn is None:
                outcomes.append(DocOutcome(doc_type, "stored-new", loc.url,
                                           None, len(text), "dry run (no db)",
                                           content_hash(text), loc.discovered_via, loc.fetch_method))
                continue

            # TODO(classifier): route segments of `text` to practice categories
            # TODO(llm_extract): answer rubric questions on relevant segments
            # TODO(scorer): fold verified findings into category scores

            outcomes.append(store_text(conn, service_id, doc_type, loc.url, loc.discovered_via,
                                       loc.fetch_method, text))

        # The site's own opt-out pages, read off the same fetches (links.py).
        # Stored whenever at least one page was read, even if no document was
        # found: a homepage with a "Your Privacy Choices" link is still worth
        # knowing. An empty harvest keeps the last one.
        first = next(iter(located.values()), None)
        if conn is not None and first is not None and first.pages_seen and first.links:
            db.replace_links(conn, service_id, first.links)
            log.info("site links: %d stored", len(first.links))
    finally:
        if conn is not None:
            conn.close()
    return outcomes


def same_url(a: str, b: str) -> bool:
    """Two addresses for one page: scheme, host case, a leading www., a
    trailing slash and the fragment don't matter. The query does (help
    centers tell articles apart by it), less any tracking parameters."""
    from .locate import _strip_tracking

    def key(url: str) -> tuple:
        p = urlparse(_strip_tracking(url.strip()))
        return (p.hostname or "").lower().removeprefix("www."), p.path.rstrip("/"), p.query

    return key(a) == key(b)


def store_text(conn, service_id: int, doc_type: str, url: str, discovered_via: str | None,
               fetch_method: str | None, text: str, *, by_hand: bool = False) -> DocOutcome:
    """Store normalized `text` as the document's newest version and say whether
    it is new, unchanged, or a change from the stored one. Commits.

    The one place every stored page passes through, so it also keeps holds:
    if a person held this document and discovery comes back with the same
    page, nothing is stored ("held"). A different page is a new candidate
    and is stored, which lifts the hold (db.upsert_document), as does a
    page a person stores by hand (`by_hand`)."""
    digest = content_hash(text)
    hold = db.held(conn, service_id, doc_type)
    if hold is not None and not by_hand and same_url(hold[0], url):
        # Progress lines are public; the reason is a note for the team.
        log.info("[%s] this page was marked as the wrong one, not stored", doc_type)
        log.info("[%s] held: %s", doc_type, hold[1], extra=SERVER_ONLY)
        conn.commit()
        return DocOutcome(doc_type, "held", url, None, len(text), f"held: {hold[1]}", digest,
                          discovered_via, fetch_method)
    document_id = db.upsert_document(conn, service_id, doc_type, url, discovered_via)
    previous = db.latest_version(conn, document_id)
    version_id = db.insert_version(conn, document_id, digest, text, fetch_method)

    if previous is None:
        status = "stored-new"
        log.info("[%s] first version stored (id %d)", doc_type, version_id)
    elif previous[1] == digest:
        status = "unchanged"
        log.info("[%s] hash matches stored version %d — no change", doc_type, previous[0])
    else:
        status = "changed"
        db.insert_change_event(conn, document_id, previous[0], version_id)
        log.info("[%s] hash differs from version %d — change event recorded",
                 doc_type, previous[0])

    conn.commit()
    note = f"hold lifted (was held: {hold[1]})" if hold is not None else ""
    return DocOutcome(doc_type, status, url, version_id, len(text), note, digest,
                      discovered_via, fetch_method)


# Shorter than this is a block page or a fragment, not a policy. The shortest
# real policy stored so far is about 3,500 characters.
MIN_MANUAL_CHARS = 1_000

_HTML_START = re.compile(r"\s*(<!doctype\s+html|<html[\s>]|<head[\s>]|<body[\s>])", re.IGNORECASE)


def looks_like_html(raw: str) -> bool:
    """A page saved from the browser (Ctrl+S) rather than copied-out text."""
    return bool(_HTML_START.match(raw[:2000])) or "</html>" in raw[-2000:].lower()


def store_manual(domain: str, doc_type: str, url: str, raw: str,
                 dsn: str | None = None) -> DocOutcome:
    """Store a document someone fetched by hand, for sites whose bot
    protection blocks the crawler. `raw` is either the page's text or the
    page saved as HTML, which goes through the same extractor as a crawled
    page. Same normalization, hashing and change detection as a crawled
    document; recorded as fetched and discovered "manual" so the provenance
    shows on the scorecard."""
    if looks_like_html(raw):
        raw = extract_text(raw)
    text = normalize(raw)
    if len(text) < MIN_MANUAL_CHARS:
        return DocOutcome(doc_type, "failed", url, None, len(text),
                          f"only {len(text)} characters after normalization; a policy has at "
                          f"least {MIN_MANUAL_CHARS}. Is this the block page?")
    if len(text) > MAX_TEXT_CHARS:
        return DocOutcome(doc_type, "failed", url, None, len(text),
                          f"{len(text):,} characters after normalization; more than any one "
                          f"policy ({MAX_TEXT_CHARS:,} at most). Is this the whole site?")
    conn = db.connect(dsn)
    try:
        db.init_schema(conn)
        service_id = db.upsert_service(conn, domain)
        return store_text(conn, service_id, doc_type, url, "manual", "manual", text, by_hand=True)
    finally:
        conn.close()
