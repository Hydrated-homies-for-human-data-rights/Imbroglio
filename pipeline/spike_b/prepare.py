"""Spike B step 1: download OPP-115 and build the classifier corpus.

OPP-115 (Wilson et al., ACL 2016): 115 privacy policies, segmented, each
segment annotated by 3 law-student annotators into 10 practice categories.
Segments can carry multiple categories (multilabel).

This script:
  1. Downloads and unpacks the corpus into pipeline/data/opp115/ (gitignored).
  2. Parses sanitized policy HTML (segments delimited by "|||") and the
     per-policy annotation CSVs.
  3. Builds a segment-level multilabel table using MAJORITY VOTE: a category
     applies to a segment when >= 2 of its annotators assigned it.
  4. Splits train/dev/test 80/10/10 BY POLICY (not by segment) so no policy
     leaks across splits, with a fixed seed for reproducibility.

Outputs (pipeline/data/opp115/processed/):
  segments.csv   policy_id, split, segment_id, text, one 0/1 column per category
  splits.json    policy-id lists per split (committed decisions, fixed seed)

Usage: python prepare.py
"""

from __future__ import annotations

import csv
import io
import json
import random
import re
import sys
import zipfile
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

import requests

HERE = Path(__file__).parent
DATA = HERE.parent / "data" / "opp115"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"

CORPUS_URL = "https://usableprivacy.org/static/data/OPP-115_v1_0.zip"

CATEGORIES = [
    "First Party Collection/Use",
    "Third Party Sharing/Collection",
    "User Choice/Control",
    "User Access, Edit and Deletion",
    "Data Retention",
    "Data Security",
    "Policy Change",
    "Do Not Track",
    "International and Specific Audiences",
    "Other",
]

SEED = 42
SPLIT_FRACTIONS = (0.8, 0.1, 0.1)  # train / dev / test, by policy
MAJORITY = 2  # of 3 annotators


class _TextExtractor(HTMLParser):
    """Strip HTML tags from a policy segment (stdlib only — lxml is blocked
    by Windows Smart App Control on some team machines)."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def strip_html(fragment: str) -> str:
    p = _TextExtractor()
    p.feed(fragment)
    return p.text()


def download() -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    zip_path = RAW / "OPP-115_v1_0.zip"
    if zip_path.exists() and zip_path.stat().st_size > 90_000_000:
        print(f"corpus zip already present: {zip_path}")
        return zip_path
    print(f"downloading {CORPUS_URL} (~95 MB) ...")
    with requests.get(CORPUS_URL, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(zip_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    print(f"saved {zip_path.stat().st_size:,} bytes")
    return zip_path


def unpack(zip_path: Path) -> Path:
    root = RAW / "unpacked"
    if root.exists() and any(root.rglob("*.csv")):
        print("already unpacked")
        return root
    # Selective extraction: original_policies/ contains saved-page asset files
    # with absurdly long names that blow past Windows MAX_PATH, and we don't
    # need them — only annotations and sanitized segment HTML.
    wanted = ("annotations/", "sanitized_policies/", "documentation/")
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if any(w in m for w in wanted)]
        zf.extractall(root, members=members)
    return root


def _find_dir(root: Path, name: str) -> Path:
    hits = [p for p in root.rglob(name) if p.is_dir()]
    if not hits:
        sys.exit(f"could not find '{name}' under {root} — corpus layout changed?")
    return hits[0]


def load_segments(root: Path) -> dict[int, list[str]]:
    """policy_id -> ordered list of segment texts."""
    seg_dir = _find_dir(root, "sanitized_policies")
    out: dict[int, list[str]] = {}
    for path in sorted(seg_dir.glob("*.html")):
        policy_id = int(path.name.split("_")[0])
        raw = path.read_text(encoding="utf-8", errors="replace")
        out[policy_id] = [strip_html(s) for s in raw.split("|||")]
    return out


def load_annotations(root: Path) -> dict[tuple[int, int], dict[str, set[str]]]:
    """(policy_id, segment_id) -> {category -> set(annotator_ids)}."""
    ann_dir = _find_dir(root, "annotations")
    votes: dict[tuple[int, int], dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for path in sorted(ann_dir.glob("*.csv")):
        # Corpus policy id = CSV filename prefix ("1017_sci-news.com.csv").
        # Column 3 in the rows is an internal DB id that does NOT match the
        # sanitized_policies filenames — keying on it yields zero labels.
        policy_id = int(path.name.split("_")[0])
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            for row in csv.reader(fh):
                # columns: annotation_id, batch_id, annotator_id, internal_db_id,
                #          segment_id, category, attributes_json, date, url
                if len(row) < 6:
                    continue
                annotator, segment_id, category = row[2], row[4], row[5]
                if not segment_id.isdigit():
                    continue  # header or malformed line
                if category not in CATEGORIES:
                    continue
                votes[(policy_id, int(segment_id))][category].add(annotator)
    return votes


def make_splits(policy_ids: list[int]) -> dict[str, list[int]]:
    rng = random.Random(SEED)
    ids = sorted(policy_ids)
    rng.shuffle(ids)
    n = len(ids)
    n_train = round(n * SPLIT_FRACTIONS[0])
    n_dev = round(n * SPLIT_FRACTIONS[1])
    return {
        "train": sorted(ids[:n_train]),
        "dev": sorted(ids[n_train : n_train + n_dev]),
        "test": sorted(ids[n_train + n_dev :]),
    }


def main() -> int:
    root = unpack(download())
    segments = load_segments(root)
    votes = load_annotations(root)
    print(f"policies: {len(segments)}, annotated segments: {len(votes)}")

    splits = make_splits(list(segments.keys()))
    split_of = {pid: name for name, pids in splits.items() for pid in pids}

    PROCESSED.mkdir(parents=True, exist_ok=True)
    (PROCESSED / "splits.json").write_text(json.dumps(splits, indent=2))

    n_rows = 0
    label_counts: dict[str, int] = defaultdict(int)
    with open(PROCESSED / "segments.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["policy_id", "split", "segment_id", "text"] + CATEGORIES)
        for policy_id, seg_texts in sorted(segments.items()):
            for seg_id, text in enumerate(seg_texts):
                if not text:
                    continue
                seg_votes = votes.get((policy_id, seg_id), {})
                labels = [
                    1 if len(seg_votes.get(cat, ())) >= MAJORITY else 0
                    for cat in CATEGORIES
                ]
                for cat, flag in zip(CATEGORIES, labels):
                    label_counts[cat] += flag
                writer.writerow(
                    [policy_id, split_of[policy_id], seg_id, text] + labels
                )
                n_rows += 1

    print(f"\nwrote {n_rows} segments -> {PROCESSED / 'segments.csv'}")
    print(f"splits (by policy): { {k: len(v) for k, v in splits.items()} }")
    print("\nsegments per category (majority-vote >= 2 of 3):")
    for cat in CATEGORIES:
        print(f"  {label_counts[cat]:5d}  {cat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
