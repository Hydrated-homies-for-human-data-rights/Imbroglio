"""Demo console: a web UI over the vertical-slice pipeline.

    cd pipeline/demo
    ../.venv/Scripts/python app.py        # -> http://localhost:8765

Type a domain: cached sites are served straight from the database; others
are queued, and a worker runs discovery -> fetch -> extract -> hash -> store
while the page polls for progress.

Deployment settings (environment variables):
    IMBROGLIO_PASSWORD   required unless HOST is 127.0.0.1; HTTP basic auth
    IMBROGLIO_USER       basic-auth username (default "imbroglio")
    HOST / PORT          bind address (default 127.0.0.1:8765; Railway sets PORT)
    IMBROGLIO_DB / DATABASE_URL   Postgres connection string
    EMBEDDED_WORKER      1 = run queue worker threads in this process (default;
                         set 0 in production, where a worker service runs)
    WORKER_CONCURRENCY   embedded worker threads (default 2)
    MAX_OPEN_REQUESTS    queue size cap (default 200)

Security model for the hosted prototype: one shared password gates every
route except /healthz; outbound fetches refuse non-public addresses (see
imbroglio/netguard.py); analyses run in queue workers with a capped queue,
never inside a web request. Batch runs stay CLI-only.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from typing import Literal

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from imbroglio import db, jobs
from imbroglio.api import router as v1_router

@asynccontextmanager
async def lifespan(_app):
    # Local dev convenience: process the queue inside this process.
    if EMBEDDED_WORKER and db_reachable():
        from imbroglio.worker import start_threads
        start_threads(EMBEDDED_WORKER_THREADS)
        logging.getLogger("imbroglio.demo").info(
            "embedded worker started (%d threads)", EMBEDDED_WORKER_THREADS)
    yield


# API docs (F8) are generated from the /v1 models and sit behind the same
# password as everything else until launch.
app = FastAPI(title="Imbroglio API", version="0.1",
              description="Read API for Imbroglio privacy-policy analysis. "
                          "Every endpoint reads precomputed data only.",
              docs_url="/v1/docs", redoc_url=None, openapi_url="/v1/openapi.json",
              lifespan=lifespan)
app.include_router(v1_router)
STATIC = Path(__file__).parent / "static"

AUTH_USER = os.environ.get("IMBROGLIO_USER", "imbroglio")
AUTH_PASSWORD = os.environ.get("IMBROGLIO_PASSWORD", "")
# Analyses run in queue workers, never in the web request. EMBEDDED_WORKER=1
# starts worker threads inside this process (local dev); production runs a
# separate worker service so Chromium never shares memory with the web server.
EMBEDDED_WORKER = os.environ.get("EMBEDDED_WORKER", "1") == "1"
EMBEDDED_WORKER_THREADS = int(os.environ.get("WORKER_CONCURRENCY", "2"))
MAX_OPEN_REQUESTS = int(os.environ.get("MAX_OPEN_REQUESTS", "200"))  # abuse cap
OPEN_PATHS = {"/healthz"}  # platform health checks; reveals nothing


def _authorized(header: str | None) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        user, _, password = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False
    # compare_digest on both so timing doesn't reveal which one was wrong
    ok_user = secrets.compare_digest(user.encode(), AUTH_USER.encode())
    ok_pass = secrets.compare_digest(password.encode(), AUTH_PASSWORD.encode())
    return ok_user and ok_pass


@app.middleware("http")
async def security(request: Request, call_next):
    if AUTH_PASSWORD and request.url.path not in OPEN_PATHS:
        if not _authorized(request.headers.get("authorization")):
            return Response("Authentication required", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Imbroglio prototype"'})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}

DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


class AnalyzeRequest(BaseModel):
    domain: str = Field(max_length=253)
    playwright: bool = True


def clean_domain(raw: str) -> str | None:
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0].split("?")[0].removeprefix("www.")
    if re.fullmatch(r"[0-9.]+", d):
        return None  # IPv4 literal: we analyze websites by name, never raw addresses
    return d if DOMAIN_RE.match(d) else None


def db_reachable() -> bool:
    try:
        conn = db.connect()
        conn.close()
        return True
    except Exception:
        return False


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "db": db_reachable()}


@app.get("/api/services")
def services() -> dict:
    """Everything cached in the database, grouped by domain."""
    if not db_reachable():
        return {"db": False, "services": []}
    conn = db.connect()
    try:
        db.init_schema(conn)
        rows = db.list_services(conn)
    finally:
        conn.close()

    grouped: dict[str, dict] = {}
    for domain, doc_type, url, versions, changes, last_fetched in rows:
        svc = grouped.setdefault(domain, {"domain": domain, "docs": []})
        if doc_type:
            svc["docs"].append({
                "doc_type": doc_type,
                "url": url,
                "versions": versions,
                "changes": changes,
                "last_fetched": last_fetched.isoformat() if last_fetched else None,
            })
    return {"db": True, "services": list(grouped.values())}


@app.get("/api/service/{domain}")
def service_detail(domain: str):
    """Latest cached version of each document for one domain, extracted text
    included, plus full version history."""
    domain = clean_domain(domain) or ""
    if not domain:
        return JSONResponse({"error": "bad domain"}, status_code=400)
    if not db_reachable():
        return JSONResponse({"error": "database offline"}, status_code=503)

    conn = db.connect()
    try:
        rows = db.service_detail(conn, domain)
        history = db.version_history(conn, domain)
    finally:
        conn.close()
    if not rows:
        return JSONResponse({"error": f"{domain} is not cached"}, status_code=404)

    hist_by_doc: dict[str, list] = {}
    for doc_type, vid, vhash, fetched_at in history:
        hist_by_doc.setdefault(doc_type, []).append({
            "version_id": vid,
            "content_hash": vhash,
            "fetched_at": fetched_at.isoformat(),
        })

    return {
        "domain": domain,
        "docs": [
            {
                "doc_type": doc_type,
                "url": url,
                "discovered_via": via,
                "version_id": vid,
                "content_hash": vhash,
                "fetch_method": method,
                "fetched_at": fetched_at.isoformat(),
                "chars": len(text),
                "text": text,
                "history": hist_by_doc.get(doc_type, []),
            }
            for doc_type, url, via, vid, vhash, method, fetched_at, text in rows
        ],
    }


# --- audit --------------------------------------------------------------------

AUDIT_PREVIEW_CHARS = 4000


class AuditVerdict(BaseModel):
    attempt_id: int
    verdict: Literal["correct", "wrong", "missed", "none", "unsure"]
    correct_url: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=1000)
    reviewer: str | None = Field(default=None, max_length=60)


@app.get("/audit")
def audit_page() -> FileResponse:
    return FileResponse(STATIC / "audit.html")


@app.get("/api/audit/next")
def audit_next(kind: Literal["found", "missed", "all"] = "all", skip: str = ""):
    if not db_reachable():
        return JSONResponse({"error": "database offline"}, status_code=503)
    skip_ids = [int(x) for x in skip.split(",") if x.strip().isdigit()][:500]
    conn = db.connect()
    try:
        db.init_schema(conn)
        row = db.audit_next(conn, kind, skip_ids)
        if row is None:
            return {"item": None}
        aid, domain, doc_type, ok, status, url, via, method, chars, notes = row
        text = db.latest_text(conn, domain, doc_type) if ok else None
    finally:
        conn.close()
    return {"item": {
        "attempt_id": aid, "domain": domain, "doc_type": doc_type, "found": ok,
        "status": status, "url": url, "discovered_via": via, "fetch_method": method,
        "chars": chars, "notes": notes,
        "preview": text[:AUDIT_PREVIEW_CHARS] if text else None,
        "preview_truncated": bool(text and len(text) > AUDIT_PREVIEW_CHARS),
    }}


@app.post("/api/audit")
def audit_save(v: AuditVerdict):
    if v.correct_url and not re.match(r"^https?://", v.correct_url, re.I):
        return JSONResponse({"error": "correct_url must start with http:// or https://"},
                            status_code=400)
    conn = db.connect()
    try:
        saved = db.audit_save(conn, v.attempt_id, v.verdict, v.correct_url or None,
                              (v.note or "").strip() or None, (v.reviewer or "").strip() or None)
        conn.commit()
    finally:
        conn.close()
    if not saved:
        return JSONResponse({"error": "attempt not found"}, status_code=404)
    return {"ok": True}


def audit_metrics(counts: dict) -> dict:
    """Turn raw counts into the two numbers that matter.

    precision: of documents we said we found, the share that were the right
      document (reviewed sample).
    recall: of sites that actually publish the document, the share we found.
      Found and missed attempts are reviewed at different rates, so each
      reviewed rate is scaled up to its population before combining:
        TP ~ total_found  * precision
        FN ~ total_missed * (missed / (missed + none))
    """
    t, v = counts["totals"], counts["verdicts"]
    total_found, total_missed = t.get("found", 0), t.get("missed", 0)
    correct, wrong = v.get("found:correct", 0), v.get("found:wrong", 0)
    missed, none = v.get("missed:missed", 0), v.get("missed:none", 0)
    precision = correct / (correct + wrong) if correct + wrong else None
    miss_has_policy = missed / (missed + none) if missed + none else None
    recall = None
    if precision is not None and miss_has_policy is not None:
        tp = total_found * precision
        fn = total_missed * miss_has_policy
        recall = tp / (tp + fn) if tp + fn else None
    return {
        "totals": {"found": total_found, "missed": total_missed},
        "reviewed": {"found": sum(n for k, n in v.items() if k.startswith("found:")),
                     "missed": sum(n for k, n in v.items() if k.startswith("missed:"))},
        "verdicts": v,
        "precision": precision,
        "missed_with_policy_rate": miss_has_policy,
        "recall_estimate": recall,
    }


@app.get("/api/audit/summary")
def audit_summary():
    if not db_reachable():
        return JSONResponse({"error": "database offline"}, status_code=503)
    conn = db.connect()
    try:
        db.init_schema(conn)
        counts = db.audit_counts(conn)
    finally:
        conn.close()
    return audit_metrics(counts)


# --- analysis requests (queue) ----------------------------------------------

@app.post("/api/requests")
def create_request(req: AnalyzeRequest):
    """Queue a domain for analysis. Returns immediately; poll
    /api/requests/{id}. An open request for the same domain is reused."""
    domain = clean_domain(req.domain)
    if not domain:
        return JSONResponse({"error": "That doesn't look like a domain. Try something like notion.so."},
                            status_code=400)
    if not db_reachable():
        return JSONResponse({"error": "database offline"}, status_code=503)
    conn = db.connect()
    try:
        db.init_schema(conn)
        open_now = sum(n for st, n in jobs.stats(conn).items() if st in ("queued", "running"))
        if open_now >= MAX_OPEN_REQUESTS:
            return JSONResponse({"error": "The analysis queue is full. Try again in a few minutes."},
                                status_code=429)
        request_id, status, created = jobs.enqueue(conn, domain, source="web",
                                                   use_playwright=req.playwright)
    finally:
        conn.close()
    return {"request_id": request_id, "domain": domain, "status": status, "created": created}


@app.get("/api/requests/{request_id}")
def get_request(request_id: int):
    conn = db.connect()
    try:
        job = jobs.get(conn, request_id)
    finally:
        conn.close()
    if job is None:
        return JSONResponse({"error": "request not found"}, status_code=404)
    return job


@app.get("/api/queue")
def queue_overview():
    """Live queue view: counts, open jobs, recently finished jobs."""
    if not db_reachable():
        return JSONResponse({"error": "database offline"}, status_code=503)
    conn = db.connect()
    try:
        db.init_schema(conn)
        return jobs.overview(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    if host not in ("127.0.0.1", "localhost") and not AUTH_PASSWORD:
        sys.exit("Refusing to listen on a public interface without IMBROGLIO_PASSWORD set.")
    if AUTH_PASSWORD and len(AUTH_PASSWORD) < 12:
        sys.exit("IMBROGLIO_PASSWORD must be at least 12 characters.")
    uvicorn.run(app, host=host, port=port, proxy_headers=True, forwarded_allow_ips="*")
