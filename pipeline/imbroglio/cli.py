"""Command-line entrypoint.

    python -m imbroglio.cli analyze notion.so
    python -m imbroglio.cli analyze notion.so --no-db      # dry run, no Postgres
    python -m imbroglio.cli analyze notion.so --no-playwright

    python -m imbroglio.cli seed-tosdr seeds/tosdr_rated.csv --rated-only
    python -m imbroglio.cli batch seeds/tosdr_rated.csv --limit 100 --workers 6
    python -m imbroglio.cli enqueue seeds/tosdr_rated.csv --limit 100 --dry-run
    python -m imbroglio.cli consistency --sample 50 --runs 3
    python -m imbroglio.cli offsite-documents     # --remove keepassxc.org ... deletes those
    python -m imbroglio.cli report                # latest batch
    python -m imbroglio.cli report 3 --out runs/batch-3.md
    python -m imbroglio.cli reports               # new problem reports from readers
    python -m imbroglio.cli reports --mark 12 withdrawn --note "quote not in document"
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


def _reanalyze_cmd(args) -> int:
    from concurrent.futures import ThreadPoolExecutor

    from . import db
    from .analysis import (average_cost, extraction_enabled, reanalysis_targets, reanalyze_checks,
                           reread_versions, spent_last_24h)
    from .rubric import load

    where: dict[str, list[str]] = {}
    for item in args.where:
        check_id, _, statuses = item.partition("=")
        if not statuses:
            print(f"--where {item!r}: expected CHECK=STATUS[,STATUS]")
            return 2
        where.setdefault(check_id.strip(), []).extend(s.strip() for s in statuses.split(",") if s.strip())
    new, old = load(args.rubric), load(args.from_version)
    for check_id, statuses in where.items():
        if check_id not in {c.id for c in new.checks} or check_id not in {c.id for c in old.checks}:
            print(f"{check_id}: not a question in both {args.from_version} and {args.rubric}")
            return 2
        unknown = [s for s in statuses if s not in old.check(check_id).allowed()]
        if unknown:
            print(f"{check_id}: {unknown} aren't answers in {args.from_version}")
            return 2

    logging.basicConfig(level=logging.WARNING)
    conn = db.connect()
    groups = reanalysis_targets(conn, args.from_version, where)
    if args.skip_done:
        # Already read under the new rubric: a run that stopped on the budget
        # picks up where it left off instead of paying for every document again.
        done = reread_versions(conn, args.rubric)
        before = len(groups)
        groups = [g for g in groups if done.isdisjoint(g)]
        print(f"{before - len(groups)} already read under {args.rubric}, skipped")
    groups = groups[: args.limit]
    docs = sum(len(g) for g in groups)
    print(f"{len(groups)} distinct documents to read ({docs} stored copies), for "
          + "; ".join(f"{c} in {s}" for c, s in where.items()))
    print(f"estimated cost: ${len(groups) * average_cost(conn):.2f}; spent in last 24h: ${spent_last_24h(conn):.2f}")
    conn.close()
    if args.dry_run:
        return 0
    if not extraction_enabled():
        print("ANTHROPIC_API_KEY not set (put it in pipeline/.env)")
        return 1

    def one(group):
        c = db.connect()
        try:
            return group, reanalyze_checks(c, group, args.rubric, list(where), model=args.model)
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (group, outcome) in enumerate(pool.map(one, groups), 1):
            print(f"[{i:>3}/{len(groups)}] {outcome:<40} version {group[0]}"
                  + (f" (+{len(group) - 1} copies)" if len(group) > 1 else ""), flush=True)
    conn = db.connect()
    print(f"spent in last 24h: ${spent_last_24h(conn):.2f}")
    conn.close()
    return 0


REPORT_STATUSES = ("new", "reviewed", "withdrawn", "dismissed")


def list_reports(conn, status: str = "new", limit: int = 50) -> list[tuple]:
    """Latest problem reports first; `status` 'all' lists every status."""
    where, params = "", []
    if status != "all":
        where, params = "WHERE status = %s", [status]
    return conn.execute(
        f"""SELECT id, created_at, status, kind, domain, message, contact, note
            FROM reports {where} ORDER BY created_at DESC, id DESC LIMIT %s""",
        params + [limit]).fetchall()


def mark_report(conn, report_id: int, status: str, note: str | None = None) -> bool:
    """Set a report's status (and note, when given). False if no such report."""
    if status not in REPORT_STATUSES:
        raise ValueError(f"status must be one of {', '.join(REPORT_STATUSES)}")
    row = conn.execute(
        "UPDATE reports SET status = %s, note = COALESCE(%s, note) WHERE id = %s RETURNING id",
        (status, note, report_id)).fetchone()
    conn.commit()
    return row is not None


def _report_line(row) -> str:
    rid, created, status, kind, domain, message, contact, _ = row
    text = " ".join(message.split())[:80]
    line = f"{rid:>5}  {created:%Y-%m-%d}  {status:<9} {kind:<14} {domain or '-':<28} {text}"
    return line + (f"  <{contact}>" if contact else "")


def _harvest_links_cmd(args) -> int:
    """Backfill the site's own opt-out links for sites stored before the
    harvest existed: the homepage and each stored document URL are fetched
    again (static, no model calls), read for links, and the result replaces
    the site's stored links. A site whose pages all fail is left as it was."""
    import requests

    from . import db
    from .fetch import fetch_rendered, fetch_static
    from .links import best, dedupe, harvest
    from .locate import is_challenge

    conn = db.connect()
    db.init_schema(conn)
    if args.domains:
        wanted = [d.strip().lower() for d in args.domains.split(",") if d.strip()]
        rows = conn.execute(
            """SELECT s.id, s.domain, array_agg(d.doc_type), array_agg(d.url)
               FROM services s LEFT JOIN documents d ON d.service_id = s.id
               WHERE s.domain = ANY(%s) GROUP BY s.id ORDER BY s.id""", (wanted,)).fetchall()
    else:
        rows = conn.execute(
            """SELECT s.id, s.domain, array_agg(d.doc_type), array_agg(d.url)
               FROM services s JOIN documents d ON d.service_id = s.id
               GROUP BY s.id ORDER BY s.id""").fetchall()
    if args.limit:
        rows = rows[:args.limit]

    session = requests.Session()
    found = skipped = 0
    for service_id, domain, doc_types, urls in rows:
        pages = 0
        links = []
        homepage = f"https://{domain}"
        html, status = fetch_static(homepage, session)
        if html and is_challenge(html):
            html, status = None, "bot challenge"
        if not html and args.render:
            html, status = fetch_rendered(homepage)
            if html and is_challenge(html):
                html, status = None, "bot challenge"
        if html:
            pages += 1
            links += harvest(html, homepage, domain, "homepage")
        for doc_type, url in zip(doc_types or [], urls or []):
            if not url:
                continue
            page, _ = fetch_static(url, session)
            if page and not is_challenge(page):
                pages += 1
                links += harvest(page, url, domain, doc_type)
        links = dedupe(links)
        chosen = best(links)
        if not pages:
            skipped += 1
            print(f"{domain:<32} no page could be read ({status}); kept as is")
            continue
        found += 1 if chosen else 0
        summary = ", ".join(f"{l.category}: {l.url}" for l in chosen) or "no links"
        print(f"{domain:<32} {len(links):>2} link(s) on {pages} page(s)  {summary}")
        if links and not args.dry_run:
            db.replace_links(conn, service_id, links)
    conn.close()
    print(f"\n{len(rows)} site(s): {found} with links, {skipped} unreadable"
          + (" (dry run, nothing stored)" if args.dry_run else ""))
    return 0


def _reports_cmd(args) -> int:
    from . import db

    conn = db.connect()
    db.init_schema(conn)
    try:
        if args.mark:
            report_id, status = args.mark
            if not mark_report(conn, int(report_id), status, args.note):
                print(f"no report {report_id}")
                return 1
            print(f"report {report_id}: {status}")
            return 0
        rows = list_reports(conn, args.status, args.limit)
        for row in rows:
            print(_report_line(row))
        print(f"{len(rows)} reports ({args.status})")
        return 0
    finally:
        conn.close()


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

    ra = sub.add_parser("reanalyze",
                        help="ask the model again only where a new rubric changes an answer, and keep the "
                             "new answers for those questions only (run rebase-rubric first)")
    ra.add_argument("--rubric", required=True, help="the new rubric version, e.g. v0.3")
    ra.add_argument("--from", dest="from_version", required=True, help="the version the answers come from, e.g. v0.2")
    ra.add_argument("--where", action="append", required=True, metavar="CHECK=STATUS[,STATUS]",
                    help="documents whose --from answer to CHECK is one of these; that question's answer "
                         "is replaced. Repeat for more questions")
    ra.add_argument("--limit", type=int, help="at most this many distinct documents")
    ra.add_argument("--model", help="override EXTRACTION_MODEL")
    ra.add_argument("--workers", type=int, default=3)
    ra.add_argument("--dry-run", action="store_true", help="count the documents and estimate the cost only")
    ra.add_argument("--skip-done", action="store_true",
                    help="leave out documents the model has already read under --rubric, so a run that "
                         "stopped on the daily budget can finish without paying twice")

    cs = sub.add_parser("consistency", help="run-to-run consistency study (N2), read-only")
    cs.add_argument("--sample", type=int, default=50)
    cs.add_argument("--runs", type=int, default=3)
    cs.add_argument("--seed", type=int, default=1)
    cs.add_argument("--model", help="override EXTRACTION_MODEL")
    cs.add_argument("--rubric", help="override RUBRIC_VERSION")
    cs.add_argument("--out", type=Path, default=Path("runs/consistency.md"))

    rb = sub.add_parser("rebase-rubric", help="move findings to a new rubric version without new LLM calls")
    rb.add_argument("--from", dest="from_version", required=True)
    rb.add_argument("--to", dest="to_version", required=True)

    cal = sub.add_parser("calibrate", help="compare scoring schemes on stored findings (no LLM calls)")
    cal.add_argument("--rubric", default="v0.1")
    cal.add_argument("--tosdr", type=Path, default=Path("seeds/tosdr_rated.csv"))
    cal.add_argument("--out", type=Path, help="also write the report to this markdown file")

    ss = sub.add_parser("score-spread",
                        help="how the score out of 100 spreads across analyzed sites (read-only, no LLM calls)")
    ss.add_argument("--rubric", default=None, help="rubric version (default: RUBRIC_VERSION, as the API uses)")
    ss.add_argument("--out", type=Path, help="also write the report to this markdown file")
    ss.add_argument("--csv", type=Path, help="also write every site's score to this CSV file")

    rq = sub.add_parser("rejected-quotes",
                        help="real quotes the evidence-word check turned away, and words that would let them in "
                             "(read-only, no LLM calls)")
    rq.add_argument("--rubric", default=None, help="rubric version (default: RUBRIC_VERSION)")
    rq.add_argument("--check", help="only show this question's suggestions and samples")
    rq.add_argument("--samples", type=int, default=12, help="turned-away quotes shown per question")
    rq.add_argument("--top", type=int, default=15, help="suggested words per question")
    rq.add_argument("--out", type=Path, help="also write the report to this markdown file")
    rq.add_argument("--csv", type=Path, help="write every turned-away quote, with an on_topic column to fill in")

    od = sub.add_parser("offsite-documents",
                        help="list stored documents that are another site's (they never name this one)")
    # A parent company's own policy (riotgames.com for leagueoflegends.com) can
    # be the right one without naming the site, so removal is per site.
    od.add_argument("--remove", nargs="+", metavar="DOMAIN", default=[],
                    help="delete these sites' listed documents with their findings and scores, "
                         "so a new crawl can look for the right ones")

    sd = sub.add_parser("store-document",
                        help="store a policy you fetched by hand, for sites that block the crawler")
    sd.add_argument("domain")
    sd.add_argument("doc_type", choices=["privacy", "terms"])
    sd.add_argument("url", help="where the document lives, shown on the scorecard")
    sd.add_argument("file", type=Path,
                    help="the document, as UTF-8 text or the page saved as HTML (- for stdin)")
    sd.add_argument("--analyze", action="store_true", help="run the LLM analysis right away")

    el = sub.add_parser("export-labels", help="export findings + document texts as classifier training data")
    el.add_argument("--rubric", default="v0.1")
    el.add_argument("--out", type=Path, default=Path("exports/labels-v0.1"))
    el.add_argument("--stdout", action="store_true", help="print JSON lines instead of writing files")

    rp = sub.add_parser("reports", help="list problem reports from readers, or mark one reviewed")
    rp.add_argument("--status", choices=REPORT_STATUSES + ("all",), default="new")
    rp.add_argument("--limit", type=int, default=50)
    rp.add_argument("--mark", nargs=2, metavar=("ID", "STATUS"),
                    help="set a report's status: " + "|".join(REPORT_STATUSES))
    rp.add_argument("--note", help="reviewer's note, stored with --mark")

    hl = sub.add_parser("harvest-links",
                        help="read stored sites' homepages and policy pages for their own opt-out links")
    hl.add_argument("--domains", help="comma-separated domains (default: every site with a document)")
    hl.add_argument("--limit", type=int, default=None, help="stop after this many sites")
    hl.add_argument("--render", action="store_true",
                    help="also render a homepage in the headless browser when the static page has no links")
    hl.add_argument("--dry-run", action="store_true", help="print what would be stored, store nothing")

    args = ap.parse_args()

    if args.command == "reports":
        return _reports_cmd(args)
    if args.command == "harvest-links":
        return _harvest_links_cmd(args)

    if args.command == "store-document":
        import sys

        from .analyze import store_manual
        raw = sys.stdin.read() if str(args.file) == "-" else args.file.read_text(encoding="utf-8")
        o = store_manual(args.domain, args.doc_type, args.url, raw)
        print(f"{args.domain} {o.doc_type:8s} {o.status:11s} {o.chars:>7,} chars"
              + (f"  version {o.version_id}" if o.version_id else "")
              + (f"  {o.notes}" if o.notes else ""))
        if o.status == "failed":
            return 1
        if args.analyze:
            from . import db
            from .analysis import ensure_analyzed
            conn = db.connect()
            try:
                print(f"analysis: {ensure_analyzed(conn, o.version_id)}")
            finally:
                conn.close()
        else:
            print(f"next: python -m imbroglio.cli extract {args.domain}")
        return 0

    if args.command == "offsite-documents":
        from . import db
        conn = db.connect()
        db.init_schema(conn)
        found = db.offsite_documents(conn)
        for _, domain, doc_type, url, analyzed in found:
            print(f"{domain:<28} {doc_type:<8} {'analyzed' if analyzed else '':<9} {url}")
        print(f"{len(found)} documents belong to another site "
              f"({sum(1 for *_, a in found if a)} analyzed)")
        unknown = set(args.remove) - {f[1] for f in found}
        if unknown:
            print(f"not in the list, nothing removed: {' '.join(sorted(unknown))}")
            return 1
        doomed = [f for f in found if f[1] in args.remove]
        if doomed:
            conn.execute("DELETE FROM documents WHERE id = ANY(%s)", ([f[0] for f in doomed],))
            conn.commit()
            print(f"removed {len(doomed)} documents; crawl these sites again to look for their own: "
                  f"{' '.join(sorted(args.remove))}")
        return 0

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

    if args.command == "rejected-quotes":
        from . import db
        from .analysis import RUBRIC_VERSION
        from .rejected_quotes import check_quotes, load_rows, report, write_csv
        from .rubric import load
        rubric = load(args.rubric or RUBRIC_VERSION)
        if args.check and args.check not in {c.id for c in rubric.checks}:
            print(f"no check {args.check!r} in rubric {rubric.version}")
            return 2
        conn = db.connect()
        try:
            quotes = check_quotes(rubric, load_rows(conn, rubric.version))
        finally:
            conn.close()
        text = report(rubric, quotes, only=args.check, samples=args.samples, top=args.top)
        print(text)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        if args.csv:
            write_csv(args.csv, quotes)
        return 0

    if args.command == "score-spread":
        from . import db
        from .analysis import RUBRIC_VERSION
        from .rubric import load
        from .score_spread import report, score_sites, write_csv
        rubric = load(args.rubric or RUBRIC_VERSION)
        conn = db.connect()
        try:
            scored = score_sites(rubric, db.site_findings(conn, rubric.version))
        finally:
            conn.close()
        text = report(rubric, scored)
        print(text)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        if args.csv:
            write_csv(args.csv, scored)
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

    if args.command == "reanalyze":
        return _reanalyze_cmd(args)

    if args.command == "consistency":
        from .analysis import EXTRACTION_MODEL, RUBRIC_VERSION, extraction_enabled
        from .consistency import run as consistency_run
        if not extraction_enabled():
            print("ANTHROPIC_API_KEY not set (put it in pipeline/.env)")
            return 1
        print(consistency_run(args.sample, args.runs, args.model or EXTRACTION_MODEL,
                              args.rubric or RUBRIC_VERSION, seed=args.seed, out=args.out))
        print()
        print(f"report: {args.out}  details: {args.out.with_suffix('.json')}")
        return 0

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
