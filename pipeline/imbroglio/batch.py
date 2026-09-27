"""Bulk import: run discovery + extraction over many domains in parallel.

    python -m imbroglio.cli seed-tosdr seeds/tosdr.csv --rated-only
    python -m imbroglio.cli batch seeds/tosdr.csv --limit 100 --workers 6
    python -m imbroglio.cli report            # latest batch

Every (domain, doc_type) attempt is written to crawl_attempts, failures
included, so a batch produces a measured extraction success rate (F1) and a
breakdown of why the failures failed. Successful documents land in the normal
documents / document_versions tables exactly as a single `analyze` would.

Workers are threads: the work is network-bound, and each Playwright fallback
runs its own browser, so peak memory is roughly one Chromium per worker.
"""

from __future__ import annotations

import csv
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests

from . import db
from .analyze import analyze

log = logging.getLogger("imbroglio")

DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
TOSDR_API = "https://api.tosdr.org/service/v3/"


def clean_domain(raw: str) -> str | None:
    """'https://www.Notion.so/product?x=1' -> 'notion.so'; None if not a domain."""
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0].split("?")[0].split("#")[0].removeprefix("www.")
    if d.endswith(".onion"):
        return None
    return d if DOMAIN_RE.match(d) else None


def load_domains(path: Path) -> list[str]:
    """Read domains from a .txt (one per line, # comments) or .csv (a 'domain'
    column, else the first column). Cleans, de-duplicates, keeps file order."""
    raw: list[str] = []
    if path.suffix.lower() == ".csv":
        with open(path, encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, [])
            col = header.index("domain") if "domain" in header else 0
            if col == 0 and header and clean_domain(header[0]):
                raw.append(header[0])  # no header row, first line is data
            raw.extend(row[col] for row in reader if len(row) > col)
    else:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line:
                raw.append(line)

    seen: set[str] = set()
    out: list[str] = []
    for r in raw:
        d = clean_domain(r)
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def seed_tosdr(out_path: Path, rated_only: bool = False, max_pages: int | None = None) -> int:
    """Write ToS;DR's service catalogue to a CSV (domain, name, rating,
    tosdr_id, comprehensively_reviewed). Public API, no key. Data is
    CC BY-SA 3.0 — attribute if redistributed."""
    rows: list[list] = []
    seen: set[str] = set()
    page = 1
    while True:
        for attempt in range(6):
            resp = requests.get(TOSDR_API, params={"page": page}, timeout=30)
            if resp.status_code != 429:
                break
            # Rate limited: honor Retry-After when given, else back off 10/20/40s...
            wait = float(resp.headers.get("Retry-After") or 10 * 2**attempt)
            log.info("tosdr rate limit on page %d, waiting %.0fs", page, wait)
            time.sleep(wait)
        resp.raise_for_status()
        data = resp.json()
        for svc in data.get("services", []):
            if rated_only and svc.get("rating") in (None, "N/A"):
                continue
            domain = next((d for d in map(clean_domain, svc.get("urls") or []) if d), None)
            if not domain or domain in seen:
                continue
            seen.add(domain)
            rows.append([domain, svc.get("name", ""), svc.get("rating", ""),
                         svc.get("id", ""), svc.get("is_comprehensively_reviewed", False)])
        end = data.get("page", {}).get("end", page)
        log.info("tosdr page %d/%d, %d services kept so far", page, end, len(rows))
        if page >= end or (max_pages and page >= max_pages):
            break
        page += 1
        time.sleep(3)  # polite to a volunteer-run API (0.5s tripped its rate limit)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["domain", "name", "rating", "tosdr_id", "comprehensively_reviewed"])
        w.writerows(rows)
    return len(rows)


@dataclass
class DomainResult:
    domain: str
    seconds: float
    privacy_ok: bool
    terms_ok: bool
    error: str | None = None


def _run_one(domain: str, batch_id: int, use_playwright: bool,
             time_budget: float) -> DomainResult:
    t0 = time.monotonic()
    try:
        outcomes = analyze(domain, use_playwright=use_playwright,
                           init_schema=False, time_budget=time_budget)
        error = None
    except Exception as exc:  # one bad site must not kill the batch
        outcomes, error = [], f"{type(exc).__name__}: {exc}"[:500]
    seconds = time.monotonic() - t0

    conn = db.connect()
    try:
        if error:
            for doc_type in ("privacy", "terms"):
                db.insert_attempt(conn, batch_id, domain, doc_type, False, "error",
                                  None, None, None, 0, error, seconds)
        for o in outcomes:
            db.insert_attempt(conn, batch_id, domain, o.doc_type, o.status != "failed",
                              o.status, o.url, o.discovered_via, o.fetch_method,
                              o.chars, o.notes or None, seconds)
        conn.commit()
    finally:
        conn.close()

    ok = {o.doc_type: o.status != "failed" for o in outcomes}
    return DomainResult(domain, seconds, ok.get("privacy", False), ok.get("terms", False), error)


def run_batch(domains: list[str], source: str, workers: int = 6,
              use_playwright: bool = True, time_budget: float = 120.0,
              skip_done: bool = False) -> int:
    """Run the pipeline over `domains`. Returns the batch id."""
    conn = db.connect()
    try:
        db.init_schema(conn)
        if skip_done:
            done = db.domains_with_privacy(conn)
            before = len(domains)
            domains = [d for d in domains if d not in done]
            print(f"skipping {before - len(domains)} domains that already have a privacy policy")
        batch_id = db.create_batch(conn, source, len(domains), workers)
        conn.commit()
    finally:
        conn.close()

    print(f"batch {batch_id}: {len(domains)} domains, {workers} workers, "
          f"{time_budget:.0f}s budget per site, browser fallback {'on' if use_playwright else 'off'}")
    t0 = time.monotonic()
    done_n = priv_n = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one, d, batch_id, use_playwright, time_budget): d
                   for d in domains}
        for fut in as_completed(futures):
            r = fut.result()
            done_n += 1
            priv_n += r.privacy_ok
            mark = lambda ok: "ok " if ok else "-- "
            extra = f"  ERROR {r.error}" if r.error else ""
            print(f"[{done_n:>4}/{len(domains)}] privacy {mark(r.privacy_ok)} terms {mark(r.terms_ok)}"
                  f"{r.seconds:6.1f}s  {r.domain}{extra}", flush=True)

    conn = db.connect()
    try:
        db.finish_batch(conn, batch_id)
        conn.commit()
    finally:
        conn.close()
    elapsed = time.monotonic() - t0
    print(f"\nbatch {batch_id} done in {elapsed / 60:.1f} min - "
          f"privacy found for {priv_n}/{len(domains)} ({100 * priv_n / max(len(domains), 1):.0f}%)")
    return batch_id


# --- reporting ----------------------------------------------------------------

def failure_cause(status: str, notes: str | None) -> str:
    """Bucket a failed attempt by its most informative symptom. Order matters:
    earlier buckets explain later ones (a blocked site also looks 'thin')."""
    n = (notes or "").lower()
    if status == "error":
        return "pipeline error"
    if "time budget" in n:
        return "time budget exceeded"
    if re.search(r"-> (401|403|429|503)\b", n):
        return "blocked (401/403/429/503)"
    if re.search(r"connectionerror|sslerror|timeout|nameresolution", n):
        return "network / DNS / TLS"
    if "thin" in n:
        return "page found but too little text (JS-rendered, wall, non-English)"
    if re.search(r"-> 404|-> 410", n):
        return "only 404s (no link found, guessed paths missing)"
    if not n:
        return "no candidate link found"
    return "other"


def batch_report(batch_id: int | None = None) -> str:
    conn = db.connect()
    try:
        if batch_id is None:
            batch_id = db.latest_batch_id(conn)
            if batch_id is None:
                return "no batches yet"
        meta = db.get_batch(conn, batch_id)
        rows = db.batch_attempts(conn, batch_id)
    finally:
        conn.close()

    source, total, workers, started, finished = meta
    by_domain: dict[str, dict[str, tuple]] = {}
    for r in rows:
        by_domain.setdefault(r[0], {})[r[1]] = r
    n = len(by_domain)
    if n == 0:
        return f"batch {batch_id}: no attempts recorded"

    def rate(k: int) -> str:
        return f"{k}/{n} ({100 * k / n:.0f}%)"

    priv = sum(1 for d in by_domain.values() if d.get("privacy", (None,) * 3)[2])
    terms = sum(1 for d in by_domain.values() if d.get("terms", (None,) * 3)[2])
    either = sum(1 for d in by_domain.values() if any(x[2] for x in d.values()))
    same_url = sum(1 for d in by_domain.values()
                   if d.get("privacy") and d.get("terms") and d["privacy"][2] and d["terms"][2]
                   and d["privacy"][4] == d["terms"][4])
    secs = sorted(next(iter(d.values()))[9] or 0 for d in by_domain.values())
    median = secs[len(secs) // 2]
    wall = (finished - started).total_seconds() / 60 if finished else None

    lines = [
        f"# Batch {batch_id} — {source}",
        "",
        f"{n} domains attempted (of {total} queued), {workers} workers"
        + (f", {wall:.1f} min wall time" if wall else ", still running or interrupted"),
        f"median {median:.1f}s per domain, slowest {secs[-1]:.1f}s",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Privacy policy found | **{rate(priv)}** |",
        f"| Terms of service found | {rate(terms)} |",
        f"| At least one document | {rate(either)} |",
        f"| Privacy and terms resolved to the same URL | {same_url} (likely a combined legal page, or a wrong pick) |",
        "",
    ]

    for doc_type in ("privacy", "terms"):
        ok_rows = [d[doc_type] for d in by_domain.values() if doc_type in d and d[doc_type][2]]
        via: dict[str, int] = {}
        method: dict[str, int] = {}
        for r in ok_rows:
            via[r[5] or "?"] = via.get(r[5] or "?", 0) + 1
            method[r[6] or "?"] = method.get(r[6] or "?", 0) + 1
        lines += [f"## {doc_type}: how successes were found", "",
                  "| Discovered via | Count | | Fetch method | Count |", "| --- | --- | --- | --- | --- |"]
        vi, mi = sorted(via.items(), key=lambda x: -x[1]), sorted(method.items(), key=lambda x: -x[1])
        for i in range(max(len(vi), len(mi))):
            a = vi[i] if i < len(vi) else ("", "")
            b = mi[i] if i < len(mi) else ("", "")
            lines.append(f"| {a[0]} | {a[1]} | | {b[0]} | {b[1]} |")
        lines.append("")

    causes: dict[str, list[str]] = {}
    for dom, d in by_domain.items():
        r = d.get("privacy")
        if r is None or r[2]:
            continue
        causes.setdefault(failure_cause(r[3], r[8]), []).append(dom)
    lines += ["## Why privacy policies were not found", "",
              "| Cause | Count | Examples |", "| --- | --- | --- |"]
    for cause, doms in sorted(causes.items(), key=lambda x: -len(x[1])):
        lines.append(f"| {cause} | {len(doms)} | {', '.join(sorted(doms)[:6])} |")
    lines.append("")
    return "\n".join(lines)
