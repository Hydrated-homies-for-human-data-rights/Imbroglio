"""Gold set: the human labels every ML result is tested against (see ml/GOLD.md).

    python -m ml.gold sample data/imbroglio/v0.2-split1 --out ml/gold/sample.csv
    python -m ml.gold pool data/imbroglio/v0.2-split1 --sample ml/gold/sample.csv \
        --out data/imbroglio/gold
    python -m ml.gold serve data/imbroglio/gold --labels ml/gold/labels
    python -m ml.gold disagree data/imbroglio/gold --labels ml/gold/labels

  sample    draws the gold and pilot documents and says who labels each
  pool      writes each document's lines, its candidate paragraphs per check
            and its pool-check sample. These hold policy text, so they go
            under data/ and stay out of git
  serve     the labeling page, on localhost only. Labels save as you go
  disagree  where the two annotators differ on the double-labeled documents,
            as a CSV to settle together

Label files name documents by version_id and paragraphs by line number, never
by text, so ml/gold/ can be committed. Agreement statistics (kappa) and the
comparisons against Claude are analysis, not tooling, and live elsewhere.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from imbroglio.rubric import NOT_DISCLOSED, load
from ml.dataset import read_jsonl
from ml.neardup import MIN_PARAGRAPH

ANNOTATORS = ("gage", "sam")
SEED = 0
RUBRIC = "v0.2"            # the rubric the dataset's labels were made under
N_PRIVACY, N_TERMS, N_DOUBLE = 13, 11, 12
MAX_PARAGRAPHS = 250       # substantive paragraphs; longer documents are left out (a reported bias)
PILOT_MAX = 120            # pilot documents are kept short
POOL_CHECK = 10            # random unpooled paragraphs per document
PAGE = Path(__file__).with_name("gold_page.html")
SAMPLE_FIELDS = ["order", "set", "annotators", "version_id", "domain", "doc_type", "split", "paragraphs"]


def substantive_counts(paragraphs: list[dict]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for p in paragraphs:
        if len(p["text"]) >= MIN_PARAGRAPH:
            counts[p["version_id"]] += 1
    return counts


# --- sample ------------------------------------------------------------------

def draw_sample(docs: list[dict], sizes: dict[int, int], n_privacy: int = N_PRIVACY,
                n_terms: int = N_TERMS, n_double: int = N_DOUBLE, seed: int = SEED) -> list[dict]:
    """Gold documents from test, in proportion by type, plus one privacy and one
    terms pilot document from dev. The double-labeled set takes its share of
    each type, and single documents alternate between the annotators."""
    rng = random.Random(seed)

    def pick(split, doc_type, n, limit):
        ok = sorted((d for d in docs if d["split"] == split and d["doc_type"] == doc_type
                     and 0 < sizes.get(d["version_id"], 0) <= limit), key=lambda d: d["version_id"])
        if len(ok) < n:
            raise ValueError(f"only {len(ok)} {split} {doc_type} documents fit, need {n}")
        return rng.sample(ok, n)

    pilot = pick("dev", "privacy", 1, PILOT_MAX) + pick("dev", "terms", 1, PILOT_MAX)
    privacy = pick("test", "privacy", n_privacy, MAX_PARAGRAPHS)
    terms = pick("test", "terms", n_terms, MAX_PARAGRAPHS)
    k = n_double * n_privacy // (n_privacy + n_terms)
    double = privacy[:k] + terms[:n_double - k]
    rng.shuffle(double)
    single = privacy[k:] + terms[n_double - k:]

    rows = [("pilot", ANNOTATORS, d) for d in pilot]
    rows += [("double", ANNOTATORS, d) for d in double]
    rows += [("single", (ANNOTATORS[i % 2],), d) for i, d in enumerate(single)]
    return [{"order": i + 1, "set": s, "annotators": " ".join(who), "version_id": d["version_id"],
             "domain": d["domain"], "doc_type": d["doc_type"], "split": d["split"],
             "paragraphs": sizes[d["version_id"]]} for i, (s, who, d) in enumerate(rows)]


def read_sample(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["order"], r["version_id"], r["paragraphs"] = int(r["order"]), int(r["version_id"]), int(r["paragraphs"])
    return rows


# --- pool --------------------------------------------------------------------

def pool_document(paragraphs: list[dict], rubric, seed: int = SEED, n_check: int = POOL_CHECK):
    """Candidate paragraphs per check, where each came from, and the pool-check
    sample. A paragraph holding one of Claude's quotes is a candidate however
    short it is; evidence words only count in substantive paragraphs, since a
    heading like "Advertising" would match every time."""
    sources: dict[str, dict[int, list[str]]] = {c.id: {} for c in rubric.checks}
    for p in paragraphs:
        long_enough = len(p["text"]) >= MIN_PARAGRAPH
        for c in rubric.checks:
            src = []
            if c.id in p["pos"]:
                src.append("quote")
            if c.id in p["kw_failed"]:
                src.append("quote_kw_failed")
            if long_enough and c.evidence and c.relevant(p["text"]):
                src.append("evidence_word")
            if src:
                sources[c.id][p["idx"]] = src
    pooled = {i for per_check in sources.values() for i in per_check}
    rest = [p["idx"] for p in paragraphs if len(p["text"]) >= MIN_PARAGRAPH and p["idx"] not in pooled]
    vid = paragraphs[0]["version_id"] if paragraphs else 0
    check_sample = sorted(random.Random(f"{seed}:{vid}").sample(rest, min(n_check, len(rest))))
    pools = {c: sorted(s) for c, s in sources.items()}
    return pools, sources, check_sample


def write_pool(dataset: Path, sample: list[dict], out: Path, rubric_version: str = RUBRIC,
               seed: int = SEED) -> str:
    wanted = {r["version_id"] for r in sample}
    by_doc: dict[int, list[dict]] = defaultdict(list)
    for p in read_jsonl(dataset / "paragraphs.jsonl"):
        if p["version_id"] in wanted:
            by_doc[p["version_id"]].append(p)
    meta = {d["version_id"]: d for d in read_jsonl(dataset / "documents.jsonl") if d["version_id"] in wanted}
    rubric = load(rubric_version)

    (out / "docs").mkdir(parents=True, exist_ok=True)
    lines = ["# Gold pools", "", "| Order | Set | Document | Candidates | Pool check |", "| --- | --- | --- | --- | --- |"]
    with (out / "sources.jsonl").open("w", encoding="utf-8") as src_fh:
        for r in sample:
            vid = r["version_id"]
            paras = sorted(by_doc[vid], key=lambda p: p["idx"])
            pools, sources, check_sample = pool_document(paras, rubric, seed)
            doc = {"version_id": vid, "domain": r["domain"], "doc_type": r["doc_type"],
                   "split": meta[vid]["split"], "rubric_version": rubric_version,
                   "lines": [{"idx": p["idx"], "text": p["text"]} for p in paras],
                   "pools": pools, "pool_check": check_sample}
            (out / "docs" / f"{vid}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            for c, per_check in sources.items():
                for idx, s in sorted(per_check.items()):
                    src_fh.write(json.dumps({"version_id": vid, "check": c, "idx": idx, "sources": s}) + "\n")
            lines.append(f"| {r['order']} | {r['set']} | {r['domain']} ({r['doc_type']}) | "
                         f"{sum(map(len, pools.values()))} | {len(check_sample)} |")
    (out / "tasks.json").write_text(json.dumps({"rubric_version": rubric_version, "tasks": sample}, indent=1),
                                    encoding="utf-8")
    report = "\n".join(lines) + "\n"
    (out / "pools.md").write_text(report, encoding="utf-8")
    return report


def rubric_for_page(version: str) -> dict:
    r = load(version)
    return {"version": version, "checks": [
        {"id": c.id, "category": r.categories[c.category], "question": c.question, "guidance": c.guidance,
         "statuses": [{"name": s.name, "meaning": s.meaning} for s in c.statuses.values()]
                     + [{"name": NOT_DISCLOSED, "meaning": "The document doesn't address this question"}]}
        for c in r.checks]}


# --- serve -------------------------------------------------------------------

_LABEL_PATH = re.compile(r"^/api/labels/([a-z]+)/(\d+)$")
_DOC_PATH = re.compile(r"^/api/doc/(\d+)$")


class Store:
    """The work folder (tasks and documents) and the labels folder."""

    def __init__(self, work: Path, labels: Path):
        self.work, self.labels = work, labels
        meta = json.loads((work / "tasks.json").read_text(encoding="utf-8"))
        self.rubric = rubric_for_page(meta["rubric_version"])
        self.tasks = meta["tasks"]

    def assigned(self, annotator: str, vid: int) -> bool:
        return any(t["version_id"] == vid and annotator in t["annotators"].split() for t in self.tasks)

    def label_path(self, annotator: str, vid: int) -> Path:
        return self.labels / annotator / f"{vid}.json"

    def state(self, annotator: str) -> dict:
        tasks = []
        for t in self.tasks:
            if annotator in t["annotators"].split():
                path = self.label_path(annotator, t["version_id"])
                finished = json.loads(path.read_text(encoding="utf-8")).get("finished", {}) if path.exists() else {}
                tasks.append({**t, "finished": finished})
        return {"annotators": list(ANNOTATORS), "rubric": self.rubric, "tasks": tasks}

    def save(self, annotator: str, vid: int, body: dict) -> None:
        if body.get("version_id") != vid or body.get("annotator") != annotator:
            raise ValueError("label belongs to another document or annotator")
        path = self.label_path(annotator, vid)
        path.parent.mkdir(parents=True, exist_ok=True)
        body["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code: int, body, kind: str = "application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def who(self, annotator: str, vid: int) -> bool:
            if annotator in ANNOTATORS and store.assigned(annotator, vid):
                return True
            self.send(404, {"error": "not assigned"})
            return False

        def do_GET(self):
            path, _, query = self.path.partition("?")
            if path == "/":
                return self.send(200, PAGE.read_bytes(), "text/html")
            if path == "/api/state":
                annotator = dict(q.split("=", 1) for q in query.split("&") if "=" in q).get("a", "")
                if annotator not in ANNOTATORS:
                    return self.send(404, {"error": "unknown annotator"})
                return self.send(200, store.state(annotator))
            if m := _DOC_PATH.match(path):
                f = store.work / "docs" / f"{int(m[1])}.json"
                return self.send(200, f.read_bytes()) if f.exists() else self.send(404, {"error": "no such document"})
            if m := _LABEL_PATH.match(path):
                if self.who(m[1], int(m[2])):
                    f = store.label_path(m[1], int(m[2]))
                    self.send(200, f.read_bytes() if f.exists() else b"null")
                return None
            self.send(404, {"error": "not found"})

        def do_PUT(self):
            m = _LABEL_PATH.match(self.path)
            if not m:
                return self.send(404, {"error": "not found"})
            if not self.who(m[1], int(m[2])):
                return None
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                store.save(m[1], int(m[2]), body)
            except (ValueError, AttributeError) as e:
                return self.send(400, {"error": str(e)})
            self.send(200, {"ok": True})

    return Handler


def serve(work: Path, labels: Path, port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(Store(work, labels)))
    print(f"Labeling page: http://127.0.0.1:{port}/?a=gage  (or ?a=sam). Ctrl+C stops it.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


# --- disagree ----------------------------------------------------------------

def disagreements(a: dict, b: dict) -> tuple[list[dict], dict[str, list[int]]]:
    """Rows where two annotators' labels for one document differ, and per
    layer how many items both judged and how many of those differ. Passages
    one annotator judged and the other never saw (their own layer A marks)
    aren't disagreements."""
    rows, counts = [], {"answers": [0, 0], "passages": [0, 0], "pool_check": [0, 0]}

    def row(layer, check, idx, x, y):
        rows.append({"layer": layer, "check": check, "idx": idx, ANNOTATORS[0]: x, ANNOTATORS[1]: y})

    for check in sorted(set(a.get("answers", {})) & set(b.get("answers", {}))):
        x, y = a["answers"][check].get("status"), b["answers"][check].get("status")
        if x and y:
            counts["answers"][0] += 1
            if x != y:
                counts["answers"][1] += 1
                row("answers", check, "", x, y)
    for check in sorted(set(a.get("passages", {})) & set(b.get("passages", {}))):
        pa, pb = a["passages"][check], b["passages"][check]
        for idx in sorted(set(pa) & set(pb), key=int):
            counts["passages"][0] += 1
            if pa[idx] != pb[idx]:
                counts["passages"][1] += 1
                row("passages", check, int(idx), "yes" if pa[idx] else "no", "yes" if pb[idx] else "no")
    ca, cb = a.get("pool_check", {}), b.get("pool_check", {})
    for idx in sorted(set(ca) & set(cb), key=int):
        if ca[idx] is None or cb[idx] is None:
            continue
        counts["pool_check"][0] += 1
        if set(ca[idx]) != set(cb[idx]):
            counts["pool_check"][1] += 1
            row("pool_check", "", int(idx), " ".join(sorted(ca[idx])) or "none", " ".join(sorted(cb[idx])) or "none")
    return rows, counts


def write_disagreements(work: Path, labels: Path, out: Path, include_pilot: bool = False) -> str:
    tasks = json.loads((work / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    sets = ("pilot", "double") if include_pilot else ("double",)
    all_rows, lines = [], ["| Document | Answers differ | Passages differ | Pool check differs |",
                           "| --- | --- | --- | --- |"]
    totals = defaultdict(lambda: [0, 0])
    for t in tasks:
        if t["set"] not in sets:
            continue
        paths = [labels / who / f"{t['version_id']}.json" for who in ANNOTATORS]
        both = [json.loads(p.read_text(encoding="utf-8")) for p in paths if p.exists()]
        if len(both) < 2 or not all((lab.get("finished") or {}).get("pool_check") for lab in both):
            lines.append(f"| {t['domain']} ({t['doc_type']}) | not finished by both yet | | |")
            continue
        rows, counts = disagreements(*both)
        all_rows += [{"version_id": t["version_id"], "domain": t["domain"], **r, "settled": ""} for r in rows]
        cells = []
        for layer in ("answers", "passages", "pool_check"):
            n, d = counts[layer]
            totals[layer][0] += n
            totals[layer][1] += d
            cells.append(f"{d} of {n}")
        lines.append(f"| {t['domain']} ({t['doc_type']}) | {' | '.join(cells)} |")
    lines.append("| all | " + " | ".join(f"{totals[k][1]} of {totals[k][0]}"
                                         for k in ("answers", "passages", "pool_check")) + " |")
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["version_id", "domain", "layer", "check", "idx", *ANNOTATORS, "settled"])
        w.writeheader()
        w.writerows(all_rows)
    return "\n".join(lines) + "\n"


# --- cli ---------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="draw the gold and pilot documents")
    s.add_argument("dataset", type=Path, help="directory written by ml.dataset (the frozen split)")
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--privacy", type=int, default=N_PRIVACY)
    s.add_argument("--terms", type=int, default=N_TERMS)
    s.add_argument("--double", type=int, default=N_DOUBLE)
    s.add_argument("--seed", type=int, default=SEED)
    s.add_argument("--force", action="store_true", help="replace an existing sample")
    p = sub.add_parser("pool", help="candidate paragraphs and pool-check samples")
    p.add_argument("dataset", type=Path)
    p.add_argument("--sample", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--rubric", default=RUBRIC)
    v = sub.add_parser("serve", help="the labeling page")
    v.add_argument("work", type=Path, help="directory written by pool")
    v.add_argument("--labels", type=Path, required=True)
    v.add_argument("--port", type=int, default=8765)
    d = sub.add_parser("disagree", help="disagreements on the double-labeled documents")
    d.add_argument("work", type=Path)
    d.add_argument("--labels", type=Path, required=True)
    d.add_argument("--out", type=Path, help="CSV path (default: disagreements.csv in the labels folder)")
    d.add_argument("--pilot", action="store_true", help="compare the pilot documents too")
    args = ap.parse_args()

    if args.cmd == "sample":
        if args.out.exists() and not args.force:
            ap.error(f"{args.out} exists; the gold sample is drawn once (use --force to replace it)")
        docs = list(read_jsonl(args.dataset / "documents.jsonl"))
        sizes = substantive_counts(list(read_jsonl(args.dataset / "paragraphs.jsonl")))
        rows = draw_sample(docs, sizes, args.privacy, args.terms, args.double, args.seed)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, SAMPLE_FIELDS)
            w.writeheader()
            w.writerows(rows)
        for r in rows:
            print(f"{r['order']:>3} {r['set']:<7} {r['annotators']:<9} {r['domain']} ({r['doc_type']}, "
                  f"{r['paragraphs']} paragraphs)")
    elif args.cmd == "pool":
        print(write_pool(args.dataset, read_sample(args.sample), args.out, args.rubric))
    elif args.cmd == "serve":
        serve(args.work, args.labels, args.port)
    else:
        print(write_disagreements(args.work, args.labels, args.out or args.labels / "disagreements.csv", args.pilot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
