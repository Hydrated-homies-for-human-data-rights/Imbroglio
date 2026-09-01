"""Command-line entrypoint.

    python -m imbroglio.cli analyze notion.so
    python -m imbroglio.cli analyze notion.so --no-db      # dry run, no Postgres
    python -m imbroglio.cli analyze notion.so --no-playwright
"""

from __future__ import annotations

import argparse
import sys

from .analyze import analyze


def main() -> int:
    ap = argparse.ArgumentParser(prog="imbroglio")
    sub = ap.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="discover, extract, and store a domain's policy documents")
    a.add_argument("domain")
    a.add_argument("--no-db", action="store_true", help="run without Postgres (print only)")
    a.add_argument("--no-playwright", action="store_true", help="disable headless-browser fallback")
    a.add_argument("--dsn", help="Postgres DSN (default: IMBROGLIO_DB env or local docker)")

    args = ap.parse_args()
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
