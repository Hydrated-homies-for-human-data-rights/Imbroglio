"""Public read API, version 1 (design spec: Public Read API, F2/F3/F8).

The same endpoints serve the website, the browser extension, and outside
researchers. Responses only ever read precomputed data: no request here
fetches a website or runs a model.

    GET /v1/sites/{domain}    everything we know about one site
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import db
from .batch import clean_domain

router = APIRouter(prefix="/v1", tags=["v1"])

SiteState = Literal["unknown", "queued", "analyzing", "ready", "no_policy_found"]
CACHE_SECONDS = 30  # short: a site can go from queued to ready within a minute


class Document(BaseModel):
    type: Literal["privacy", "terms"]
    url: str
    discovered_via: str | None
    fetch_method: str | None
    version_id: int
    content_hash: str
    chars: int
    fetched_at: datetime
    versions_stored: int
    changes_detected: int


class PendingRequest(BaseModel):
    id: int
    status: Literal["queued", "running"]
    stage: str | None
    queue_ahead: int
    requested_at: datetime


class Site(BaseModel):
    domain: str
    state: SiteState
    checked_at: datetime | None
    documents: list[Document]
    missing: list[Literal["privacy", "terms"]]
    pending_request: PendingRequest | None
    scores: None = None  # filled in once the rubric scorer exists (M4)


class ApiError(BaseModel):
    error: str


def _documents(conn, domain: str) -> list[Document]:
    rows = conn.execute(
        """SELECT d.doc_type, d.url, d.discovered_via, v.fetch_method, v.id, v.content_hash,
                  length(v.normalized_text), v.fetched_at,
                  (SELECT count(*) FROM document_versions v2 WHERE v2.document_id = d.id),
                  (SELECT count(*) FROM change_events c WHERE c.document_id = d.id)
           FROM services s
           JOIN documents d ON d.service_id = s.id
           JOIN LATERAL (SELECT * FROM document_versions v
                         WHERE v.document_id = d.id
                         ORDER BY v.fetched_at DESC LIMIT 1) v ON true
           WHERE s.domain = %s
           ORDER BY d.doc_type""",
        (domain,),
    ).fetchall()
    return [Document(type=r[0], url=r[1], discovered_via=r[2], fetch_method=r[3],
                     version_id=r[4], content_hash=r[5], chars=r[6], fetched_at=r[7],
                     versions_stored=r[8], changes_detected=r[9]) for r in rows]


def _pending(conn, domain: str) -> PendingRequest | None:
    row = conn.execute(
        """SELECT id, status, stage, requested_at,
                  (SELECT count(*) FROM analysis_requests q
                   WHERE q.status = 'queued' AND q.requested_at < r.requested_at)
           FROM analysis_requests r
           WHERE domain = %s AND status IN ('queued', 'running')""",
        (domain,),
    ).fetchone()
    if row is None:
        return None
    return PendingRequest(id=row[0], status=row[1], stage=row[2], requested_at=row[3],
                          queue_ahead=row[4] if row[1] == "queued" else 0)


def _last_attempt(conn, domain: str) -> datetime | None:
    row = conn.execute(
        "SELECT max(attempted_at) FROM crawl_attempts WHERE domain = %s", (domain,)
    ).fetchone()
    return row[0] if row else None


def build_site(conn, domain: str) -> Site:
    docs = _documents(conn, domain)
    pending = _pending(conn, domain)
    if docs:
        state: SiteState = "ready"
        checked_at = max(d.fetched_at for d in docs)
    else:
        checked_at = _last_attempt(conn, domain)
        if pending is not None:
            state = "analyzing" if pending.status == "running" else "queued"
        elif checked_at is not None:
            state = "no_policy_found"
        else:
            state = "unknown"
    have = {d.type for d in docs}
    return Site(domain=domain, state=state, checked_at=checked_at, documents=docs,
                missing=[t for t in ("privacy", "terms") if t not in have],
                pending_request=pending)


@router.get("/sites/{domain}", response_model=Site,
            responses={400: {"model": ApiError}, 503: {"model": ApiError}},
            summary="Everything known about one site")
def get_site(domain: str, request: Request, response: Response):
    """Current documents, any analysis in progress, and (later) scores.

    `state` is `ready` once at least one document is stored. A site we have
    never seen is `unknown` (HTTP 200, not 404): an unknown site is a normal
    answer, and the client can offer to request an analysis.

    Supports `If-None-Match`: pollers get `304 Not Modified` until something
    changes."""
    clean = clean_domain(domain)
    if not clean:
        return JSONResponse({"error": "not a valid domain"}, status_code=400)
    try:
        conn = db.connect()
    except Exception:
        return JSONResponse({"error": "database unavailable"}, status_code=503)
    try:
        site = build_site(conn, clean)
    finally:
        conn.close()

    body = site.model_dump(mode="json")
    etag = '"' + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": f"private, max-age={CACHE_SECONDS}"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(body, headers=headers)
