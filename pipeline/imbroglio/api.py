"""Public read API, version 1 (design spec: Public Read API, F2/F3/F8).

The same endpoints serve the website, the browser extension, and outside
researchers. Responses only ever read precomputed data: no request here
fetches a website or runs a model.

    GET  /v1/sites/{domain}     everything we know about one site
    POST /v1/requests           ask for a site to be analyzed (rate limited)
    GET  /v1/requests/{id}      follow an analysis while it runs
    GET  /v1/lookup/{prefix}    privacy-preserving lookup by hash prefix
    GET  /v1/learn              what users can do about each kind of finding
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import db, jobs, scorer
from .advice import Advice, load as load_advice
from .rubric import NOT_DISCLOSED, load as load_rubric
from .batch import clean_domain

# Abuse limits for the only write path. Every accepted request can cost a
# crawl (and, once extraction exists, LLM tokens), so both a per-client rate
# and a global daily ceiling apply.
REQUESTS_PER_HOUR = int(os.environ.get("REQUESTS_PER_HOUR", "30"))
DAILY_REQUEST_CAP = int(os.environ.get("DAILY_REQUEST_CAP", "300"))
PUBLIC_SOURCES = ("web", "api", "extension")

# "No policy found" is itself a result (design goal 4) and is remembered:
# re-requesting such a site within this window answers from the database
# instead of crawling it again. `refresh` overrides.
NEGATIVE_TTL_DAYS = int(os.environ.get("NEGATIVE_TTL_DAYS", "7"))

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
    shared_with: int = Field(
        description="Other sites whose current document is word-for-word identical. "
                    "Common for policy generators and for one company running several "
                    "domains; analysis of identical text is reused.")


class PendingRequest(BaseModel):
    id: int
    status: Literal["queued", "running"]
    stage: str | None
    queue_ahead: int
    requested_at: datetime


class AdviceStep(BaseModel):
    text: str
    link: str | None


class WhatYouCanDo(BaseModel):
    title: str
    why: str
    steps: list[AdviceStep]
    learn_anchor: str = Field(description="Anchor for the website's learn page: /learn#<anchor>")


class Evidence(BaseModel):
    check_id: str
    question: str
    status: str
    meaning: str
    quotes: list[str] = Field(description="Only quotes confirmed word-for-word in the stored document")
    explanation: str | None
    document: Literal["privacy", "terms"]
    provenance: Literal["machine", "human", "agreed"]
    model: str
    reused: bool = Field(description="Copied from an identical document instead of a new analysis")
    what_you_can_do: WhatYouCanDo | None = Field(
        None, description="Practical steps for this finding; null when the practice needs no action")


class CategoryScore(BaseModel):
    key: str
    name: str
    tier: Literal["LIMITED", "MODERATE", "EXTENSIVE", "SEVERE", "NOT_DISCLOSED"]
    findings: list[Evidence]


class Scorecard(BaseModel):
    rubric_version: str
    scorer_version: str
    headline: Literal["LIMITED", "MODERATE", "EXTENSIVE", "SEVERE", "NOT_DISCLOSED"]
    headline_categories: list[str] = Field(description="Categories at the headline tier")
    categories: list[CategoryScore]
    analyzed_at: datetime
    documents: list[Literal["privacy", "terms"]]


class Site(BaseModel):
    domain: str
    state: SiteState
    checked_at: datetime | None
    documents: list[Document]
    missing: list[Literal["privacy", "terms"]]
    pending_request: PendingRequest | None
    recheck_after: datetime | None = Field(
        None, description="For no_policy_found: when a new request will crawl the site again")
    scorecard: Scorecard | None = Field(
        None, description="Ratings and evidence; null until the documents have been analyzed")


class ApiError(BaseModel):
    error: str


def _documents(conn, domain: str) -> list[Document]:
    rows = conn.execute(
        """SELECT d.doc_type, d.url, d.discovered_via, v.fetch_method, v.id, v.content_hash,
                  length(v.normalized_text), v.fetched_at,
                  (SELECT count(*) FROM document_versions v2 WHERE v2.document_id = d.id),
                  (SELECT count(*) FROM change_events c WHERE c.document_id = d.id),
                  (SELECT count(DISTINCT d2.service_id) FROM document_versions v2
                   JOIN documents d2 ON d2.id = v2.document_id
                   WHERE v2.content_hash = v.content_hash AND d2.service_id <> s.id)
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
                     versions_stored=r[8], changes_detected=r[9], shared_with=r[10])
            for r in rows]


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


def _what_you_can_do(a: Advice | None) -> WhatYouCanDo | None:
    if a is None:
        return None
    return WhatYouCanDo(title=a.title, why=a.why, learn_anchor=a.check_id,
                        steps=[AdviceStep(text=s.text, link=s.link) for s in a.steps])


def _scorecard(conn, docs: list[Document]) -> Scorecard | None:
    """Combine the latest analyzed version of each document into one card.
    Only verified findings appear, and only their verified quotes."""
    from .analysis import RUBRIC_VERSION

    rubric = load_rubric(RUBRIC_VERSION)
    book = load_advice(RUBRIC_VERSION)
    per_doc_tiers, evidence, analyzed, covered = [], {c: [] for c in rubric.categories}, [], []
    for d in docs:
        rows = conn.execute(
            """SELECT check_id, status, quotes, quotes_verified, verified, explanation, model,
                      provenance, reused_from_version_id IS NOT NULL, created_at
               FROM findings WHERE version_id = %s AND rubric_version = %s""",
            (d.version_id, rubric.version)).fetchall()
        if not rows:
            continue
        covered.append(d.type)
        per_doc_tiers.append(scorer.category_tiers(
            rubric, [scorer.ScoredFinding(r[0], r[1], r[4]) for r in rows]))
        for (check_id, status, quotes, flags, verified, expl, model, prov, reused, created) in rows:
            analyzed.append(created)
            if not verified or status == NOT_DISCLOSED:
                continue
            check = rubric.check(check_id)
            if status not in check.statuses:
                continue
            evidence[check.category].append(Evidence(
                check_id=check_id, question=check.question, status=status,
                meaning=check.statuses[status].meaning,
                quotes=[q for q, ok in zip(quotes, flags) if ok], explanation=expl,
                document=d.type, provenance=prov, model=model, reused=reused,
                what_you_can_do=_what_you_can_do(book.for_finding(check_id, status))))
    if not per_doc_tiers:
        return None
    tiers = scorer.combine(*per_doc_tiers)
    head = scorer.headline(tiers)
    return Scorecard(
        rubric_version=rubric.version, scorer_version=scorer.SCORER_VERSION, headline=head,
        headline_categories=[rubric.categories[c] for c, t in tiers.items() if t == head],
        categories=[CategoryScore(key=c, name=rubric.categories[c], tier=tiers[c],
                                  findings=evidence[c]) for c in rubric.categories],
        analyzed_at=max(analyzed), documents=covered)


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
    recheck = (checked_at + timedelta(days=NEGATIVE_TTL_DAYS)
               if state == "no_policy_found" and checked_at else None)
    return Site(domain=domain, state=state, checked_at=checked_at, documents=docs,
                missing=[t for t in ("privacy", "terms") if t not in have],
                pending_request=pending, recheck_after=recheck,
                scorecard=_scorecard(conn, docs) if docs else None)


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


# --- analysis requests ----------------------------------------------------------

class _RateLimiter:
    """Sliding one-hour window per client. In memory: fine for one web
    instance; move to the database if the web service is ever scaled out."""

    def __init__(self, per_hour: int) -> None:
        self.per_hour = per_hour
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[client]
            while q and now - q[0] > 3600:
                q.popleft()
            if len(q) >= self.per_hour:
                return False
            q.append(now)
            return True


_limiter = _RateLimiter(REQUESTS_PER_HOUR)


class NewRequest(BaseModel):
    domain: str = Field(max_length=253, examples=["notion.so"])
    browser: bool = Field(True, description="Allow the headless-browser fallback for JavaScript-rendered pages")
    refresh: bool = Field(False, description="Re-analyze even if the site is already available")


class RequestAccepted(BaseModel):
    request_id: int | None
    domain: str
    status: Literal["queued", "running", "already_available", "no_policy_found"]
    recheck_after: datetime | None = None
    created: bool
    status_url: str | None


class AnalysisRequest(BaseModel):
    id: int
    domain: str
    status: Literal["queued", "running", "done", "failed"]
    stage: str | None
    progress: list[str]
    result: dict | None
    error: str | None
    request_count: int
    queue_ahead: int
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@router.post("/requests", status_code=202, response_model=RequestAccepted,
             responses={200: {"model": RequestAccepted}, 400: {"model": ApiError},
                        429: {"model": ApiError}, 503: {"model": ApiError}},
             summary="Ask for a site to be analyzed")
def create_request(body: NewRequest, request: Request):
    """Queues the site and returns immediately (202); follow it at
    `status_url`. Answered from the database instead (200, nothing queued)
    when the site already has documents (`already_available`) or was checked
    recently and had none (`no_policy_found`, with `recheck_after`), unless
    `refresh` is true.
    Duplicate requests for a site already in the queue join that job."""
    domain = clean_domain(body.domain)
    if not domain:
        return JSONResponse({"error": "not a valid domain"}, status_code=400)
    client = request.client.host if request.client else "unknown"
    try:
        conn = db.connect()
    except Exception:
        return JSONResponse({"error": "database unavailable"}, status_code=503)
    try:
        db.init_schema(conn)
        if not body.refresh:
            if _documents(conn, domain):
                return JSONResponse(RequestAccepted(request_id=None, domain=domain,
                                                    status="already_available", created=False,
                                                    status_url=None).model_dump(), status_code=200)
            last = _last_attempt(conn, domain)
            if last and datetime.now(timezone.utc) - last < timedelta(days=NEGATIVE_TTL_DAYS):
                return JSONResponse(RequestAccepted(
                    request_id=None, domain=domain, status="no_policy_found", created=False,
                    status_url=None, recheck_after=last + timedelta(days=NEGATIVE_TTL_DAYS),
                ).model_dump(mode="json"), status_code=200)
        if not _limiter.allow(client):
            return JSONResponse({"error": f"Rate limit: at most {REQUESTS_PER_HOUR} requests per hour."},
                                status_code=429, headers={"Retry-After": "600"})
        today = conn.execute(
            """SELECT count(*) FROM analysis_requests
               WHERE requested_at > now() - interval '24 hours' AND source = ANY(%s)""",
            (list(PUBLIC_SOURCES),)).fetchone()[0]
        if today >= DAILY_REQUEST_CAP:
            return JSONResponse({"error": "Daily analysis limit reached. Try again tomorrow."},
                                status_code=429, headers={"Retry-After": "3600"})
        request_id, status, created = jobs.enqueue(conn, domain, source="api",
                                                   use_playwright=body.browser)
    finally:
        conn.close()
    return RequestAccepted(request_id=request_id, domain=domain, status=status, created=created,
                           status_url=f"/v1/requests/{request_id}")


@router.get("/requests/{request_id}", response_model=AnalysisRequest,
            responses={404: {"model": ApiError}}, summary="Follow an analysis")
def get_request(request_id: int):
    """Status, current step, and the live progress log. Poll every second or
    two while `status` is `queued` or `running`."""
    conn = db.connect()
    try:
        job = jobs.get(conn, request_id)
    finally:
        conn.close()
    if job is None:
        return JSONResponse({"error": "request not found"}, status_code=404)
    return job


# --- privacy-preserving lookup ---------------------------------------------------

HASH_PREFIX = re.compile(r"^[0-9a-f]{4,8}$")


class LookupEntry(BaseModel):
    hash: str
    documents: list[Literal["privacy", "terms"]]
    checked_at: datetime | None
    scores: None = None


class LookupResult(BaseModel):
    prefix: str
    sites: list[LookupEntry]


@router.get("/lookup/{prefix}", response_model=LookupResult,
            responses={400: {"model": ApiError}},
            summary="Look up sites by hash prefix, without revealing the domain")
def lookup(prefix: str, response: Response):
    """For clients that shouldn't reveal which site a user is on (the
    browser extension). Compute `sha256(domain)` locally (lowercase, no
    `www.`), send the first 4-8 hex characters, and find your site in the
    returned list by its full hash. The server only learns the prefix, which
    is shared by an enormous number of possible domains.

    Sites appear here once they have at least one stored document."""
    p = prefix.lower()
    if not HASH_PREFIX.match(p):
        return JSONResponse({"error": "prefix must be 4-8 lowercase hex characters"}, status_code=400)
    conn = db.connect()
    try:
        rows = conn.execute(
            """SELECT s.domain_hash, array_agg(DISTINCT d.doc_type ORDER BY d.doc_type),
                      max(v.fetched_at)
               FROM services s
               JOIN documents d ON d.service_id = s.id
               JOIN document_versions v ON v.document_id = d.id
               WHERE s.domain_hash LIKE %s
               GROUP BY s.domain_hash
               LIMIT 500""",
            (p + "%",),
        ).fetchall()
    finally:
        conn.close()
    response.headers["Cache-Control"] = "private, max-age=300"
    return LookupResult(prefix=p, sites=[LookupEntry(hash=h, documents=docs, checked_at=t)
                                         for h, docs, t in rows])


# --- learn: what users can do --------------------------------------------------

class LearnTopic(BaseModel):
    check_id: str
    category: str
    question: str
    title: str
    why: str
    applies_to: list[str] = Field(description="Finding statuses this advice is shown for")
    steps: list[AdviceStep]


class Guide(BaseModel):
    id: str
    title: str
    body: str


class Learn(BaseModel):
    topics: list[LearnTopic]
    guides: list[Guide]


@router.get("/learn", response_model=Learn, summary="What users can do about each kind of finding")
def learn(response: Response):
    """Everything behind the website's learn pages and the extension's "What
    can you do?" link: one topic per rubric check (anchor = `check_id`) plus
    general guides. Static content; never touches the database."""
    from .analysis import RUBRIC_VERSION

    rubric = load_rubric(RUBRIC_VERSION)
    book = load_advice(RUBRIC_VERSION)
    response.headers["Cache-Control"] = "public, max-age=3600"
    topics = [LearnTopic(check_id=a.check_id, category=rubric.categories[rubric.check(a.check_id).category],
                         question=rubric.check(a.check_id).question, title=a.title, why=a.why,
                         applies_to=list(a.applies_to),
                         steps=[AdviceStep(text=s.text, link=s.link) for s in a.steps])
              for a in book.checks.values()]
    return Learn(topics=topics, guides=[Guide(id=g.id, title=g.title, body=g.body) for g in book.general])
