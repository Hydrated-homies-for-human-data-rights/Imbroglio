"""Command-line entrypoint.

    python -m imbroglio.cli analyze notion.so
    python -m imbroglio.cli analyze notion.so --no-db      # dry run, no Postgres
    python -m imbroglio.cli analyze notion.so --no-playwright

    python -m imbroglio.cli seed-tosdr seeds/tosdr_rated.csv --rated-only
    python -m imbroglio.cli batch seeds/tosdr_rated.csv --limit 100 --workers 6
    python -m imbroglio.cli enqueue seeds/tosdr_rated.csv --limit 100 --dry-run
    python -m imbroglio.cli report                # latest batch
    python -m imbroglio.cli report 3 --out runs/batch-3.md
"""

from __future__ import annotations

import argparse
import os
import logging
import sys
from pathlib import Path

from .analyze import analyze


def _load_dotenv(path: Path = Path(__file__).resolve().parent.parent / ".env") -> None:
    """Read KEY=VALUE lines from pipeline/.env (gitignored) into the
    environment, without overriding variables that are already set. Keeps
    secrets like ANTHROPIC_API_KEY out of the shell history and the code."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _extract_cmd(args) -> int:
    from concurrent.futures import ThreadPoolExecutor

    from . import db
    from .analysis import RUBRIC_VERSION, ensure_analyzed, extraction_enabled, spent_last_24h

    logging.basicConfig(level=logging.WARNING)
    if not extraction_enabled():
        print("ANTHROPIC_API_KEY not set (put it in pipeline/.env)")
        return 1
    conn = db.connect()
    db.init_schema(conn)
    where, params = "", []
    if args.domains:
        where, params = "WHERE s.domain = ANY(%s)", [list(args.domains)]
    elif not args.all:
        print("give domains, or --all")
        return 1
    rows = conn.execute(
        f"""SELECT DISTINCT ON (d.id) s.domain, d.doc_type, v.id
            FROM documents d JOIN services s ON s.id = d.service_id
            JOIN document_versions v ON v.document_id = d.id {where}
            ORDER BY d.id, v.fetched_at DESC""", params).fetchall()
    if not args.force:
        rows = [r for r in rows if not conn.execute(
            "SELECT 1 FROM findings WHERE version_id = %s AND rubric_version = %s LIMIT 1",
            (r[2], RUBRIC_VERSION)).fetchone()]
    rows = rows[: args.limit]
    print(f"{len(rows)} documents to analyze; spent in last 24h: ${spent_last_24h(conn):.2f}")
    conn.close()

    def one(row):
        domain, doc_type, version_id = row
        c = db.connect()
        try:
            return domain, doc_type, ensure_analyzed(c, version_id, force=args.force, model=args.model)
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (domain, doc_type, outcome) in enumerate(pool.map(one, rows), 1):
            print(f"[{i:>3}/{len(rows)}] {outcome:<28} {domain} {doc_type}", flush=True)
    conn = db.connect()
    print(f"spent in last 24h: ${spent_last_24h(conn):.2f}")
    conn.close()
    return 0


def main() -> int:
    _load_dotenv()
    ap = argparse.ArgumentParser(prog="imbroglio")
    sub = ap.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="discover, extract, and store a domain's policy documents")
    a.add_argument("domain")
    a.add_argument("--no-db", action="store_true", help="run without Postgres (print only)")
    a.add_argument("--no-playwright", action="store_true", help="disable headless-browser fallback")
    a.add_argument("--dsn", help="Postgres DSN (default: IMBROGLIO_DB env or local docker)")

    s = sub.add_parser("seed-tosdr", help="download the ToS;DR service catalogue to a CSV")
    s.add_argument("out", type=Path)
    s.add_argument("--rated-only", action="store_true", help="only services with an A-E grade")
    s.add_argument("--max-pages", type=int, help="stop after N pages of 500 (for quick tests)")

    b = sub.add_parser("batch", help="run discovery + extraction over a file of domains")
    b.add_argument("file", type=Path, help=".txt (one domain per line) or .csv (domain column)")
    b.add_argument("--limit", type=int, help="only the first N domains")
    b.add_argument("--sample", type=int, help="random sample of N domains (reproducible with --seed)")
    b.add_argument("--seed", type=int, default=42)
    b.add_argument("--workers", type=int, default=6)
    b.add_argument("--time-budget", type=float, default=120.0, help="seconds per domain")
    b.add_argument("--no-playwright", action="store_true")
    b.add_argument("--skip-done", action="store_true", help="skip domains that already have a privacy policy")

    q = sub.add_parser("enqueue", help="queue new domains from a file for the worker (no local crawling)")
    q.add_argument("file", type=Path, help=".txt (one domain per line) or .csv (domain column)")
    q.add_argument("--limit", type=int, required=True, help="queue at most N new domains")
    q.add_argument("--dry-run", action="store_true", help="show what would be queued, change nothing")

    r = sub.add_parser("report", help="summarize a batch (default: latest)")
    r.add_argument("batch_id", nargs="?", type=int)
    r.add_argument("--out", type=Path, help="also write the report to this markdown file")

    cm = sub.add_parser("compare-models", help="run extraction models side by side on sample documents")
    cm.add_argument("--sample", type=int, default=10)
    cm.add_argument("--models", default="opus,sonnet,haiku")
    cm.add_argument("--seed", type=int, default=1)
    cm.add_argument("--out", type=Path, default=Path("runs/compare-models.md"))

    ex = sub.add_parser("extract", help="run LLM analysis (findings + scores) for stored documents")
    ex.add_argument("domains", nargs="*", help="domains to analyze (default: none; see --all)")
    ex.add_argument("--all", action="store_true", help="every stored document without findings")
    ex.add_argument("--limit", type=int, default=50)
    ex.add_argument("--model", help="override EXTRACTION_MODEL")
    ex.add_argument("--force", action="store_true", help="re-analyze even if findings exist")
    ex.add_argument("--workers", type=int, default=3)

    rb = sub.add_parser("rebase-rubric", help="move findings to a new rubric version without new LLM calls")
    rb.add_argument("--from", dest="from_version", required=True)
    rb.add_argument("--to", dest="to_version", required=True)

    cal = sub.add_parser("calibrate", help="compare scoring schemes on stored findings (no LLM calls)")
    cal.add_argument("--rubric", default="v0.1")
    cal.add_argument("--tosdr", type=Path, default=Path("seeds/tosdr_rated.csv"))
    cal.add_argument("--out", type=Path, help="also write the report to this markdown file")

    el = sub.add_parser("export-labels", help="export findings + document texts as classifier training data")
    el.add_argument("--rubric", default="v0.1")
    el.add_argument("--out", type=Path, default=Path("exports/labels-v0.1"))
    el.add_argument("--stdout", action="store_true", help="print JSON lines instead of writing files")

    args = ap.parse_args()

    if args.command == "export-labels":
        from .export import run as export_run
        return export_run(args.out, args.rubric, args.stdout)

    if args.command == "calibrate":
        from .calibrate import run as calibrate_run
        text = calibrate_run(args.rubric, args.tosdr)
        print(text)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        return 0

    if args.command == "rebase-rubric":
        from . import db
        from .analysis import rebase
        conn = db.connect()
        db.init_schema(conn)
        ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT version_id FROM findings WHERE rubric_version = %s", (args.from_version,))]
        from collections import Counter
        outcomes = Counter(rebase(conn, v, args.from_version, args.to_version) for v in ids)
        print(f"{len(ids)} document versions: {dict(outcomes)}")
        return 0

    if args.command == "extract":
        return _extract_cmd(args)

    if args.command == "compare-models":
        from .compare import run as compare_run
        print(compare_run(args.sample, args.models.split(","), seed=args.seed, out=args.out))
        print()
        print(f"report: {args.out}  details: {args.out.with_suffix('.json')}")
        return 0

    if args.command == "seed-tosdr":
        from .batch import seed_tosdr
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        n = seed_tosdr(args.out, rated_only=args.rated_only, max_pages=args.max_pages)
        print(f"wrote {n} services -> {args.out}")
        return 0

    if args.command == "batch":
        from .batch import load_domains, run_batch
        domains = load_domains(args.file)
        source = args.file.name
        if args.sample:
            import random
            domains = random.Random(args.seed).sample(domains, min(args.sample, len(domains)))
            source += f" (sample {len(domains)}, seed {args.seed})"
        if args.limit:
            domains = domains[: args.limit]
        batch_id = run_batch(domains, source=source, workers=args.workers,
                             use_playwright=not args.no_playwright,
                             time_budget=args.time_budget, skip_done=args.skip_done)
        print()
        print(f"report: python -m imbroglio.cli report {batch_id}")
        return 0

    if args.command == "enqueue":
        from psycopg.conninfo import conninfo_to_dict

        from . import db, jobs
        from .batch import load_domains
        domains = load_domains(args.file)
        target = conninfo_to_dict(db.database_url())
        print(f"database: {target.get('host', 'localhost')}/{target.get('dbname', '')}")
        conn = db.connect()
        db.init_schema(conn)
        out = jobs.enqueue_batch(conn, domains, limit=args.limit, dry_run=args.dry_run)
        print(f"{len(domains)} domains in {args.file.name}: {len(out['already_stored'])} already stored, "
              f"{len(out['already_requested'])} already requested")
        print(f"{'would queue' if args.dry_run else 'queued'} {len(out['queued'])}: "
              + ", ".join(out["queued"][:10]) + (" ..." if len(out["queued"]) > 10 else ""))
        print(f"queue now: {jobs.stats(conn)}")
        conn.close()
        return 0

    if args.command == "report":
        from .batch import batch_report
        text = batch_report(args.batch_id)
        print(text)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        return 0

    outcomes = analyze(
        args.domain,
        use_playwright=not args.no_playwright,
        dsn=args.dsn,
        store=not args.no_db,
    )
    failed = 0
    for o in outcomes:
        line = f"{o.doc_type:8s} {o.status:11s}"
        if o.url:
            line += f" {o.chars:>7,} chars  {o.url}"
        if o.version_id:
            line += f"  (version {o.version_id})"
        if o.notes:
            line += f"  [{o.notes}]"
        print(line)
        failed += o.status == "failed"
    return 1 if failed == len(outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
