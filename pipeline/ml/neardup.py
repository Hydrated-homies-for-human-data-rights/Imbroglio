"""Near-duplicate documents, grouped so they never straddle a split.

    python -m ml.neardup exports/labels-v0.2 --out data/imbroglio/neardup
    python -m ml.dataset exports/labels-v0.2 --groups data/imbroglio/neardup/groups.csv \
        --out data/imbroglio/v0.2-split1

Many sites publish the same policy: one company on several domains (Proton,
Microsoft and Bing) or a generated template with the company name swapped in.
If one copy is in training and another in test, a model is tested on text it
has already seen. Splitting by identical text catches only exact copies.

Method:
  * each document becomes a set of word 5-grams (shingles), with URLs, email
    addresses and digits masked so a changed contact line doesn't hide a copy
  * similarity is Jaccard, |A & B| / |A | B|, computed exactly for every pair
    with one sparse matrix product (973 documents take seconds)
  * documents from different sites at or above the threshold are linked, and
    linked sites form a group (connected components). Single linkage can chain
    unrelated documents together; for a split that errs in the safe direction
    (a bigger group), and the report lists every group so chains are visible
  * MinHash with LSH banding, the method that scales to millions of documents
    where exact pairs don't, is run alongside and checked against the exact
    answer, so the report says what the approximation would have missed

The leakage table is the evaluation: the share of substantive test paragraphs
that appear word for word in training, for each threshold and several seeds.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import random
import re
import zlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import scipy.sparse as sp

from imbroglio.verify import canon

from .dataset import assign_splits, groups, read_jsonl

K = 5                    # words per shingle
THRESHOLD = 0.3          # chosen from the leakage table; see ml/README.md
MIN_PARAGRAPH = 40       # characters; shorter lines are mostly headings
NUM_PERM = 128           # MinHash signature length
BANDS, ROWS = 32, 4      # LSH: 32 bands of 4 rows; pairs near J = (1/32)^(1/4) = 0.42 collide half the time
_PRIME = (1 << 31) - 1

_MASK = re.compile(r"https?://\S+|www\.\S+|\S+@\S+")
_DIGITS = re.compile(r"\d+")
_WORD = re.compile(r"[a-z]+|#")


# --- similarity ----------------------------------------------------------------

def shingles(text: str, k: int = K) -> set[int]:
    """Hashed word k-grams. crc32 rather than hash(), which changes per run."""
    words = _WORD.findall(_DIGITS.sub("#", _MASK.sub(" ", text.lower())))
    return {zlib.crc32(" ".join(words[i:i + k]).encode()) for i in range(max(1, len(words) - k + 1))}


def jaccard_matrix(sets: list[set[int]]) -> np.ndarray:
    """Exact Jaccard for every pair: intersections from X @ X.T, where X is the
    document-by-shingle 0/1 matrix, and |A | B| = |A| + |B| - |A & B|."""
    index: dict[int, int] = {}
    rows, cols = [], []
    for i, s in enumerate(sets):
        for h in s:
            rows.append(i)
            cols.append(index.setdefault(h, len(index)))
    x = sp.csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(len(sets), len(index)))
    inter = (x @ x.T).toarray()
    size = np.asarray(x.sum(axis=1)).ravel()
    union = size[:, None] + size[None, :] - inter
    return np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)


def minhash(sets: list[set[int]], num_perm: int = NUM_PERM, seed: int = 0) -> np.ndarray:
    """MinHash signatures: for each of num_perm random hash functions
    h(x) = (a x + b) mod p, the minimum over a document's shingles. Two
    documents' signatures agree in a position with probability equal to
    their Jaccard similarity."""
    rng = np.random.default_rng(seed)
    a = rng.integers(1, _PRIME, num_perm, dtype=np.uint64)
    b = rng.integers(0, _PRIME, num_perm, dtype=np.uint64)
    sigs = np.empty((len(sets), num_perm), dtype=np.uint64)
    for i, s in enumerate(sets):
        x = np.fromiter(s, dtype=np.uint64, count=len(s)) % _PRIME
        sigs[i] = ((np.outer(x, a) + b) % _PRIME).min(axis=0)
    return sigs


def lsh_pairs(sigs: np.ndarray, bands: int = BANDS, rows: int = ROWS) -> set[tuple[int, int]]:
    """Candidate pairs: documents whose signatures match exactly in at least
    one band of `rows` positions."""
    out: set[tuple[int, int]] = set()
    for band in range(bands):
        buckets: dict[bytes, list[int]] = defaultdict(list)
        for i, sig in enumerate(sigs[:, band * rows:(band + 1) * rows]):
            buckets[sig.tobytes()].append(i)
        for members in buckets.values():
            out.update((i, j) for n, i in enumerate(members) for j in members[n + 1:])
    return out


# --- groups --------------------------------------------------------------------

def linked_groups(docs: list[dict], sim: np.ndarray, threshold: float) -> dict[str, str]:
    """domain -> group name for sites linked by a cross-site pair at or above
    the threshold, in the `--groups` format ml.dataset reads. Sites with no
    link are left out (they stay their own group)."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    ii, jj = np.where(np.triu(sim, 1) >= threshold)
    for i, j in zip(ii, jj):
        a, b = docs[i]["domain"], docs[j]["domain"]
        if a != b:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    return {d: find(d) for d in parent}


def substantive(text: str) -> list[str]:
    return [canon(line) for line in text.split("\n") if len(line.strip()) >= MIN_PARAGRAPH]


def leakage(docs: list[dict], extra: dict[str, str], seed: int,
            paras: list[list[str]] | None = None) -> float:
    """Share of substantive test paragraphs whose text appears in training.
    `paras` is substantive() of each document, passed in when called often."""
    paras = paras or [substantive(d["text"]) for d in docs]
    group_of = groups(docs, extra)
    split_of = assign_splits(docs, group_of, seed)
    seen: set[str] = set()
    test: list[str] = []
    for d, ps in zip(docs, paras):
        split = split_of[group_of[d["domain"]]]
        if split == "train":
            seen.update(ps)
        elif split == "test":
            test.extend(ps)
    return sum(p in seen for p in test) / len(test) if test else 0.0


# --- report ----------------------------------------------------------------------

def review_sample(docs: list[dict], sim: np.ndarray, per_bin: int = 6, seed: int = 0) -> list[tuple]:
    """Cross-site pairs drawn evenly across similarity bins, for a person to
    judge whether each is one template or just shared boilerplate."""
    bins = [(0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.7), (0.7, 1.01)]
    ii, jj = np.triu_indices(len(docs), 1)
    v = sim[ii, jj]
    rng = random.Random(seed)
    out = []
    for lo, hi in bins:
        hits = [(float(v[k]), int(ii[k]), int(jj[k])) for k in np.where((v >= lo) & (v < hi))[0]
                if docs[ii[k]]["domain"] != docs[jj[k]]["domain"]]
        out += sorted(rng.sample(hits, min(per_bin, len(hits))), reverse=True)
    return out


def review_html(docs: list[dict], pairs: list[tuple]) -> str:
    """Side by side summary: the lines each document has that the other
    doesn't. A template pair differs only in names, dates and contact lines."""
    parts = ["<!doctype html><meta charset='utf-8'><title>Near-duplicate review</title>",
             "<style>body{font:14px system-ui;max-width:1100px;margin:2em auto;padding:0 16px}"
             ".pair{border-top:2px solid #888;margin-top:2em}.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}"
             "li{margin:.3em 0}.meta{color:#666}</style>",
             "<h1>Near-duplicate review</h1><p>For each pair, record in review.csv whether the two documents "
             "are <b>template</b> (same text, names and details swapped), <b>boilerplate</b> (only common "
             "stock sentences shared) or <b>different</b>.</p>"]
    for n, (j, a, b) in enumerate(pairs, 1):
        la, lb = ({canon(x): x.strip() for x in docs[i]["text"].split("\n") if len(x.strip()) >= MIN_PARAGRAPH}
                  for i in (a, b))
        shared = len(la.keys() & lb.keys())
        parts.append(f"<div class='pair'><h2>Pair {n}: Jaccard {j:.2f}</h2><p class='meta'>"
                     f"{html.escape(docs[a]['domain'])} ({docs[a]['doc_type']}) and "
                     f"{html.escape(docs[b]['domain'])} ({docs[b]['doc_type']}): {shared} paragraphs identical, "
                     f"{len(la) - shared} only in the first, {len(lb) - shared} only in the second</p><div class='cols'>")
        for mine, other in ((la, lb), (lb, la)):
            only = [t for k, t in mine.items() if k not in other][:8]
            parts.append("<ul>" + "".join(f"<li>{html.escape(t[:300])}</li>" for t in only) + "</ul>")
        parts.append("</div></div>")
    return "\n".join(parts)


def run(export: Path, out: Path, threshold: float = THRESHOLD, seeds: int = 5) -> str:
    docs = list(read_jsonl(export / "documents.jsonl"))
    sets = [shingles(d["text"]) for d in docs]
    sim = jaccard_matrix(sets)
    site = np.array([d["domain"] for d in docs])
    cross = site[:, None] != site[None, :]
    ii, jj = np.triu_indices(len(docs), 1)
    keep = cross[ii, jj]
    values = sim[ii, jj][keep]

    lines = ["# Near-duplicate documents", "",
             f"{len(docs)} documents from {len(set(site))} sites, word {K}-gram shingles, exact Jaccard "
             f"over {int(keep.sum()):,} cross-site pairs.", "",
             "## Cross-site pairs by similarity", "", "| Jaccard | Pairs |", "| --- | --- |"]
    edges = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    for lo, hi in zip(edges, edges[1:]):
        lines.append(f"| {lo:.1f} to {min(hi, 1.0):.1f} | {int(((values >= lo) & (values < hi)).sum())} |")

    lines += ["", "## Leakage by threshold", "",
              f"Share of substantive test paragraphs (at least {MIN_PARAGRAPH} characters) that appear word for "
              f"word in training, over {seeds} split seeds. \"none\" groups identical texts only (split 0).", "",
              "| Threshold | Leakage, mean | Range over seeds | Groups of 2+ sites | Largest group |",
              "| --- | --- | --- | --- | --- |"]
    paras = [substantive(d["text"]) for d in docs]
    for th in (None, 0.9, 0.7, 0.5, 0.4, 0.3, 0.2, 0.1):
        extra = {} if th is None else linked_groups(docs, sim, th)
        rates = [leakage(docs, extra, s, paras) for s in range(seeds)]
        sizes = Counter(groups(docs, extra).values())
        multi = sum(1 for n in sizes.values() if n > 1)
        mark = " (chosen)" if th == threshold else ""
        lines.append(f"| {'none' if th is None else th}{mark} | {100 * np.mean(rates):.1f}% | "
                     f"{100 * min(rates):.1f}% to {100 * max(rates):.1f}% | {multi} | {max(sizes.values())} sites |")

    chosen = linked_groups(docs, sim, threshold)
    members: dict[str, list[str]] = defaultdict(list)
    for d, g in chosen.items():
        members[g].append(d)
    lines += ["", f"## Groups at {threshold}", "",
              f"{len(members)} groups linking {len(chosen)} sites. Each line is one group.", ""]
    lines += [f"- {', '.join(sorted(m))}" for m in sorted(members.values(), key=lambda m: (-len(m), sorted(m)))]

    exact = {(int(i), int(j)) for i, j in zip(ii[keep], jj[keep]) if sim[i, j] >= threshold}
    found = lsh_pairs(minhash(sets))
    caught = len(exact & found)
    lines += ["", "## MinHash with LSH against exact", "",
              f"{NUM_PERM} hash functions in {BANDS} bands of {ROWS}. LSH proposed {len(found):,} candidate pairs "
              f"(of {len(ii):,} possible) and caught {caught} of the {len(exact)} cross-site pairs at or above "
              f"{threshold} ({100 * caught / max(len(exact), 1):.1f}% recall). Missed pairs:", ""]
    missed = sorted(exact - found, key=lambda p: -sim[p])
    lines += [f"- {docs[i]['domain']} ({docs[i]['doc_type']}) and {docs[j]['domain']} ({docs[j]['doc_type']}), "
              f"Jaccard {sim[i, j]:.2f}" for i, j in missed] or ["- none"]

    out.mkdir(parents=True, exist_ok=True)
    with (out / "groups.csv").open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(sorted(chosen.items()))
    with (out / "pairs.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["jaccard", "domain_a", "doc_type_a", "domain_b", "doc_type_b"])
        for k in np.argsort(-sim[ii, jj]):
            i, j = int(ii[k]), int(jj[k])
            if sim[i, j] < 0.1:
                break
            if cross[i, j]:
                w.writerow([f"{sim[i, j]:.3f}", docs[i]["domain"], docs[i]["doc_type"],
                            docs[j]["domain"], docs[j]["doc_type"]])
    sample = review_sample(docs, sim)
    (out / "review.html").write_text(review_html(docs, sample), encoding="utf-8")
    with (out / "review.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pair", "jaccard", "domain_a", "doc_type_a", "domain_b", "doc_type_b", "verdict"])
        for n, (j, a, b) in enumerate(sample, 1):
            w.writerow([n, f"{j:.3f}", docs[a]["domain"], docs[a]["doc_type"], docs[b]["domain"], docs[b]["doc_type"], ""])
    report = "\n".join(lines) + "\n"
    (out / "report.md").write_text(report, encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export", type=Path, help="directory written by cli export-labels")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()
    print(run(args.export, args.out, args.threshold, args.seeds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
