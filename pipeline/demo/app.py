"""Demo console: a web UI over the vertical-slice pipeline.

    cd pipeline/demo
    ../.venv/Scripts/python app.py        # -> http://localhost:8765

Type a domain, watch discovery -> fetch -> extract -> hash -> store run live.
If Postgres is down (classroom wifi, docker not running), the console
automatically falls back to a dry run so the demo never dies on stage.

Deployment settings (environment variables):
    IMBROGLIO_PASSWORD   required unless HOST is 127.0.0.1; HTTP basic auth
    IMBROGLIO_USER       basic-auth username (default "imbroglio")
    HOST / PORT          bind address (default 127.0.0.1:8765; Railway sets PORT)
    IMBROGLIO_DB / DATABASE_URL   Postgres connection string
    MAX_CONCURRENT       simultaneous analyses (default 2)

Security model for the hosted prototype: one shared password gates every
route except /healthz; outbound fetches refuse non-public addresses (see
imbroglio/netguard.py); analyses are capped in number and duration because
each can launch a Chromium process. Batch runs stay CLI-only.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import queue
import re
import secrets
import sys
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from typing import Literal

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from imbroglio import db
from imbroglio.analyze import analyze

# Public deployments don't need the interactive API docs pages.
app = FastAPI(title="Imbroglio demo console", docs_url=None, redoc_url=None, openapi_url=None)
STATIC = Path(__file__).parent / "static"

AUTH_USER = os.environ.get("IMBROGLIO_USER", "imbroglio")
AUTH_PASSWORD = os.environ.get("IMBROGLIO_PASSWORD", "")
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "2"))
ANALYZE_TIME_BUDGET = 90.0  # seconds of probing per site, same idea as batch runs
_slots = threading.BoundedSemaphore(MAX_CONCURRENT)
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
    store: bool = True


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


def _log_attempts(domain: str, outcomes, seconds: float) -> None:
    """Record console analyses in crawl_attempts (no batch) so the audit page
    can review them alongside batch runs. Best effort: never fails a run."""
    try:
        conn = db.connect()
        try:
            for o in outcomes:
                db.insert_attempt(conn, None, domain, o.doc_type, o.status != "failed",
                                  o.status, o.url, o.discovered_via, o.fetch_method,
                                  o.chars, o.notes or None, seconds)
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logging.getLogger("imbroglio.demo").exception("could not log attempts for %s", domain)


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


class _QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__()
        self.q = q

        self.thread_id: int | None = None

    def emit(self, record: logging.LogRecord) -> None:
        # The "imbroglio" logger is process-wide; with concurrent analyses
        # each stream must only carry its own worker thread's lines.
        if record.thread == self.thread_id:
            self.q.put(record.getMessage())


@app.post("/api/analyze")
def run(req: AnalyzeRequest):
    """Streams NDJSON: {"type":"log",...} lines while the pipeline runs,
    then one final {"type":"result",...} line.

    The worker starts before the response is returned and owns all cleanup
    (log handler, concurrency slot), so a client that disconnects early, or
    before streaming even begins, can't leak a slot."""
    domain = clean_domain(req.domain)
    if not domain:
        return JSONResponse({"error": "That doesn't look like a domain. Try something like notion.so."},
                            status_code=400)

    if not _slots.acquire(blocking=False):
        return JSONResponse({"error": f"Busy: {MAX_CONCURRENT} analyses already running. "
                                      "Try again in a minute."}, status_code=429)

    # Check the database up front so a dead DB costs a fallback flag, not a
    # 30-second re-fetch after a failed analyze.
    try:
        store = req.store and db_reachable()
    except Exception:
        _slots.release()
        raise

    q: queue.Queue = queue.Queue()
    handler = _QueueHandler(q)
    logger = logging.getLogger("imbroglio")
    logger.setLevel(logging.INFO)
    result: dict = {}

    def work() -> None:
        handler.thread_id = threading.get_ident()
        logger.addHandler(handler)
        t0 = time.time()
        try:
            outcomes = analyze(domain, use_playwright=req.playwright, store=store,
                               time_budget=ANALYZE_TIME_BUDGET)
            if store:
                _log_attempts(domain, outcomes, time.time() - t0)
            result.update(
                domain=domain, db=store, seconds=round(time.time() - t0, 1),
                outcomes=[
                    {
                        "doc_type": o.doc_type,
                        "found": o.status != "failed",
                        "status": o.status,
                        "url": o.url,
                        "version_id": o.version_id,
                        "chars": o.chars,
                        "content_hash": o.content_hash,
                        "discovered_via": o.discovered_via,
                        "fetch_method": o.fetch_method,
                        "notes": o.notes,
                    }
                    for o in outcomes
                ],
            )
        except Exception as exc:
            logging.getLogger("imbroglio.demo").exception("analyze failed for %s", domain)
            result["error"] = f"Pipeline error: {type(exc).__name__}"  # details stay in server logs
        finally:
            logger.removeHandler(handler)
            _slots.release()
            q.put(None)  # sentinel: work finished

    threading.Thread(target=work, daemon=True).start()

    def stream():
        if not store:
            yield json.dumps({"type": "log", "msg": "database off — dry run, nothing will be stored"}) + "\n"
        while True:
            msg = q.get()
            if msg is None:
                break
            yield json.dumps({"type": "log", "msg": msg}) + "\n"
        yield json.dumps({"type": "result", **result}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    if host not in ("127.0.0.1", "localhost") and not AUTH_PASSWORD:
        sys.exit("Refusing to listen on a public interface without IMBROGLIO_PASSWORD set.")
    if AUTH_PASSWORD and len(AUTH_PASSWORD) < 12:
        sys.exit("IMBROGLIO_PASSWORD must be at least 12 characters.")
    uvicorn.run(app, host=host, port=port, proxy_headers=True, forwarded_allow_ips="*")
