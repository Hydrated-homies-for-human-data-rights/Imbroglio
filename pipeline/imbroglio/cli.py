"""Command-line entrypoint.

    python -m imbroglio.cli analyze notion.so
    python -m imbroglio.cli analyze notion.so --no-db      # dry run, no Postgres
    python -m imbroglio.cli analyze notion.so --no-playwright

    python -m imbroglio.cli seed-tosdr seeds/tosdr_rated.csv --rated-only
    python -m imbroglio.cli batch seeds/tosdr_rated.csv --limit 100 --workers 6
    python -m imbroglio.cli report                # latest batch
    python -m imbroglio.cli report 3 --out runs/batch-3.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .analyze import analyze


def main() -> int:
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

    r = sub.add_parser("report", help="summarize a batch (default: latest)")
    r.add_argument("batch_id", nargs="?", type=int)
    r.add_argument("--out", type=Path, help="also write the report to this markdown file")

    args = ap.parse_args()

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
