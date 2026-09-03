"""Demo console: a local web UI over the vertical-slice pipeline.

    cd pipeline/demo
    ../.venv/Scripts/python app.py        # -> http://localhost:8765

Type a domain, watch discovery -> fetch -> extract -> hash -> store run live.
If Postgres is down (classroom wifi, docker not running), the console
automatically falls back to a dry run so the demo never dies on stage.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from imbroglio import db
from imbroglio.analyze import analyze

app = FastAPI(title="Imbroglio demo console")
STATIC = Path(__file__).parent / "static"

DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


class AnalyzeRequest(BaseModel):
    domain: str
    playwright: bool = True
    store: bool = True


def clean_domain(raw: str) -> str | None:
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0].split("?")[0].removeprefix("www.")
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


@app.post("/api/analyze")
def run(req: AnalyzeRequest):
    domain = clean_domain(req.domain)
    if not domain:
        return JSONResponse({"error": "That doesn't look like a domain. Try something like notion.so."},
                            status_code=400)

    # Check the database up front so a dead DB costs a fallback flag, not a
    # 30-second re-fetch after a failed analyze.
    store = req.store and db_reachable()
    t0 = time.time()
    try:
        outcomes = analyze(domain, use_playwright=req.playwright, store=store)
    except Exception as exc:
        return JSONResponse({"error": f"Pipeline error: {type(exc).__name__}: {exc}"},
                            status_code=500)

    return {
        "domain": domain,
        "db": store,
        "seconds": round(time.time() - t0, 1),
        "outcomes": [
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
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
