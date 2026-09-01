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

from dataclasses import dataclass

from . import db
from .locate import Located, locate_all
from .normalize import content_hash, normalize


@dataclass
class DocOutcome:
    doc_type: str
    status: str            # stored-new | unchanged | changed | failed
    url: str | None = None
    version_id: int | None = None
    chars: int = 0
    notes: str = ""


def analyze(domain: str, use_playwright: bool = True,
            dsn: str | None = None, store: bool = True) -> list[DocOutcome]:
    located = locate_all(domain, use_playwright=use_playwright)
    outcomes: list[DocOutcome] = []

    conn = db.connect(dsn) if store else None
    try:
        if conn is not None:
            db.init_schema(conn)
            service_id = db.upsert_service(conn, domain)

        for doc_type, loc in located.items():
            if not loc.ok:
                outcomes.append(DocOutcome(doc_type, "failed",
                                           notes="; ".join(loc.notes[-3:])))
                continue

            text = normalize(loc.text)
            digest = content_hash(text)

            if conn is None:
                outcomes.append(DocOutcome(doc_type, "stored-new", loc.url,
                                           None, len(text), f"hash {digest[:12]} (dry run)"))
                continue

            document_id = db.upsert_document(conn, service_id, doc_type,
                                             loc.url, loc.discovered_via)
            previous = db.latest_version(conn, document_id)
            version_id = db.insert_version(conn, document_id, digest, text,
                                           loc.fetch_method)

            if previous is None:
                status = "stored-new"
            elif previous[1] == digest:
                status = "unchanged"
            else:
                status = "changed"
                db.insert_change_event(conn, document_id, previous[0], version_id)

            # TODO(classifier): route segments of `text` to practice categories
            # TODO(llm_extract): answer rubric questions on relevant segments
            # TODO(scorer): fold verified findings into category scores

            conn.commit()
            outcomes.append(DocOutcome(doc_type, status, loc.url, version_id, len(text)))
    finally:
        if conn is not None:
            conn.close()
    return outcomes
