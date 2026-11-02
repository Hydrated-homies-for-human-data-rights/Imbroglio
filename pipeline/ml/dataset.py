"""Paragraph dataset from a label export (see ml/README.md).

    python -m ml.dataset exports/labels-v0.2 --out data/imbroglio/v0.2-split0

Turns `cli export-labels` output (whole documents plus one answer per
document and check) into one row per paragraph with, per check, a positive
(a verified quote lies in it), a negative (the document doesn't address the
check) or nothing (unlabeled). Assigns train/dev/test by group so documents
with the same text never land in two splits.

Pure functions over the export files: no database, no model calls.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from imbroglio.rubric import NOT_DISCLOSED
from imbroglio.verify import quote_offsets

SPLITS = ("train", "dev", "test")
FRACTIONS = (0.70, 0.15, 0.15)
SEED = 0


@dataclass
class Paragraph:
    version_id: int
    domain: str
    doc_type: str
    idx: int                                             # line number in the document text
    text: str
    pos: dict[str, str] = field(default_factory=dict)    # check -> status of the quoted answer
    neg: list[str] = field(default_factory=list)         # checks the document doesn't address
    kw_failed: list[str] = field(default_factory=list)   # found word for word, no evidence word
    split: str = ""


@dataclass
class QuoteCounts:
    verified: int = 0       # placed, and counted as a positive
    kw_failed: int = 0      # in the document, but rejected for lacking an evidence word
    not_found: int = 0      # not in the document at all
    lost: int = 0           # flagged verified but couldn't be placed: should stay 0


def lines_of(text: str) -> tuple[list[str], list[int]]:
    """The document's lines and the offset where each one starts."""
    lines = text.split("\n")
    starts, pos = [], 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1
    return lines, starts


def lines_touched(starts: list[int], a: int, b: int) -> range:
    """Line numbers that the character span [a, b) falls on."""
    return range(bisect.bisect_right(starts, a) - 1, bisect.bisect_right(starts, b - 1))


def label_document(doc: dict, labels: list[dict], counts: QuoteCounts) -> list[Paragraph]:
    text = doc["text"]
    lines, starts = lines_of(text)
    paras = {i: Paragraph(doc["version_id"], doc["domain"], doc["doc_type"], i, line.strip())
             for i, line in enumerate(lines) if line.strip()}

    quoted = [(lab, q, flag) for lab in labels if lab["status"] != NOT_DISCLOSED
              for q, flag in zip(lab["quotes"], lab["quotes_verified"])]
    offsets = quote_offsets([q for _, q, _ in quoted], text)
    for (lab, _, flag), spans in zip(quoted, offsets):
        if spans is None:
            if flag:
                counts.lost += 1
            else:
                counts.not_found += 1
            continue
        if flag:
            counts.verified += 1
        else:
            counts.kw_failed += 1
        for a, b in spans:
            for i in lines_touched(starts, a, b):
                if i not in paras:
                    continue
                if flag:
                    paras[i].pos[lab["check_id"]] = lab["status"]
                elif lab["check_id"] not in paras[i].kw_failed:
                    paras[i].kw_failed.append(lab["check_id"])

    silent = sorted(lab["check_id"] for lab in labels if lab["status"] == NOT_DISCLOSED)
    for p in paras.values():
        p.neg = silent
        p.kw_failed = sorted(c for c in p.kw_failed if c not in p.pos)
    return [paras[i] for i in sorted(paras)]


# --- splits ------------------------------------------------------------------

def groups(docs: list[dict], extra: dict[str, str] | None = None) -> dict[str, str]:
    """domain -> group id. Domains sharing a document text, or a group name in
    `extra`, end up in one group, named after its alphabetically first domain."""
    parent = {d["domain"]: d["domain"] for d in docs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    first_with: dict[str, str] = {}
    keys = [("hash", d["content_hash"], d["domain"]) for d in docs]
    keys += [("extra", g, dom) for dom, g in (extra or {}).items() if dom in parent]
    for kind, key, domain in keys:
        if (kind, key) in first_with:
            union(first_with[(kind, key)], domain)
        else:
            first_with[(kind, key)] = domain
    return {d: find(d) for d in parent}


def assign_splits(docs: list[dict], group_of: dict[str, str], seed: int = SEED,
                  fractions: tuple[float, float, float] = FRACTIONS) -> dict[str, str]:
    """group id -> split. Groups are shuffled with a fixed seed and dealt out
    until each split holds its share of documents."""
    size = Counter(group_of[d["domain"]] for d in docs)
    order = sorted(size)
    random.Random(seed).shuffle(order)
    bounds = [sum(fractions[:i + 1]) * len(docs) for i in range(len(SPLITS))]
    out, seen, k = {}, 0, 0
    for g in order:
        while k < len(SPLITS) - 1 and seen >= bounds[k]:
            k += 1
        out[g] = SPLITS[k]
        seen += size[g]
    return out


# --- build -------------------------------------------------------------------

def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def build(export: Path, extra_groups: dict[str, str] | None = None, seed: int = SEED):
    docs = list(read_jsonl(export / "documents.jsonl"))
    labels: dict[int, list[dict]] = defaultdict(list)
    for lab in read_jsonl(export / "labels.jsonl"):
        labels[lab["version_id"]].append(lab)

    group_of = groups(docs, extra_groups)
    split_of_group = assign_splits(docs, group_of, seed)
    counts = QuoteCounts()
    paragraphs: list[Paragraph] = []
    doc_rows = []
    for d in docs:
        split = split_of_group[group_of[d["domain"]]]
        for p in label_document(d, labels[d["version_id"]], counts):
            p.split = split
            paragraphs.append(p)
        doc_rows.append({"version_id": d["version_id"], "domain": d["domain"],
                         "doc_type": d["doc_type"], "split": split, "group": group_of[d["domain"]],
                         "answers": {lab["check_id"]: {"status": lab["status"], "verified": lab["verified"]}
                                     for lab in labels[d["version_id"]]}})
    return paragraphs, doc_rows, counts


def stats(paragraphs: list[Paragraph], doc_rows: list[dict], counts: QuoteCounts,
          checks: list[str]) -> str:
    lines = ["# Paragraph dataset", "",
             f"Quotes: {counts.verified} verified and placed, {counts.kw_failed} found word for word "
             f"but rejected for lacking an evidence word, {counts.not_found} not in the document, "
             f"{counts.lost} flagged verified but not placed.", "",
             "| Split | Documents | Sites | Groups | Paragraphs |", "| --- | --- | --- | --- | --- |"]
    for s in SPLITS:
        ds = [d for d in doc_rows if d["split"] == s]
        lines.append(f"| {s} | {len(ds)} | {len({d['domain'] for d in ds})} | "
                     f"{len({d['group'] for d in ds})} | {sum(p.split == s for p in paragraphs)} |")
    chars = sorted(len(p.text) for p in paragraphs)
    lines += ["", f"Paragraph length in characters: median {statistics.median(chars):.0f}, "
              f"90th percentile {chars[int(0.9 * len(chars))]}, "
              f"{sum(c < 40 for c in chars)} under 40 (mostly headings).", "",
              "## Per check", "",
              "Positive paragraphs (and the documents they come from) per split, then negative "
              "paragraphs and keyword-failed paragraphs over all splits.", "",
              "| Check | train | dev | test | negative | kw_failed |",
              "| --- | --- | --- | --- | --- | --- |"]
    for c in checks:
        cells = []
        for s in SPLITS:
            hit = [p for p in paragraphs if p.split == s and c in p.pos]
            cells.append(f"{len(hit)} ({len({p.version_id for p in hit})})")
        lines.append(f"| {c} | {' | '.join(cells)} | {sum(c in p.neg for p in paragraphs)} | "
                     f"{sum(c in p.kw_failed for p in paragraphs)} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export", type=Path, help="directory written by cli export-labels")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--groups", type=Path, help="CSV of domain,group to keep together")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    extra = None
    if args.groups:
        with args.groups.open(encoding="utf-8", newline="") as fh:
            extra = {row[0]: row[1] for row in csv.reader(fh) if len(row) >= 2}
    paragraphs, doc_rows, counts = build(args.export, extra, args.seed)

    from imbroglio.rubric import load
    checks = [c.id for c in load(next(read_jsonl(args.export / "labels.jsonl"))["rubric_version"]).checks]
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "paragraphs.jsonl").open("w", encoding="utf-8") as fh:
        for p in paragraphs:
            fh.write(json.dumps(p.__dict__, ensure_ascii=False) + "\n")
    with (args.out / "documents.jsonl").open("w", encoding="utf-8") as fh:
        for d in doc_rows:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    report = stats(paragraphs, doc_rows, counts, checks)
    (args.out / "stats.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
