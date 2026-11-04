"""Error analysis for any run: where a model goes wrong, with the text.

    python -m ml.errors data/imbroglio/v0.2-split1 data/imbroglio/runs/logreg-dev.npz

Per check, two lists:

  * false alarms: the highest-scoring paragraphs in documents that don't
    address the check at all. On Claude's labels these are the only
    paragraphs known to be wrong answers, so they are the honest place to
    look at precision
  * misses: quoted paragraphs the model ranked lowest within their own
    document, with the paragraph it put first instead

The output quotes policy text, so it goes next to the run under data/ and
stays out of git. Read it to name the kinds of error (wrong topic, negated
statement, heading, boilerplate, a label that looks wrong), not to tune on.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from ml.dataset import read_jsonl
from ml.metrics import load_run, load_split, ranks_of_positives

PER_LIST = 8
WIDTH = 300


def clip(text: str) -> str:
    return text if len(text) <= WIDTH else text[:WIDTH] + "..."


def analyze(dataset: Path, run: Path, split_name: str = "dev", per_list: int = PER_LIST) -> str:
    split = load_split(dataset, split_name)
    scores = load_run(run, split)
    texts = {(p["version_id"], p["idx"]): p["text"] for p in read_jsonl(dataset / "paragraphs.jsonl")
             if p["split"] == split_name}
    domain = [d["domain"] for d in split.docs]
    lines = [f"# Errors: {run.stem} on {split_name}", ""]
    for j, check in enumerate(split.checks):
        lines += [f"## {check}", "", "### False alarms (documents that don't address it)", ""]
        silent_rows = np.flatnonzero(split.silent[split.doc, j])
        for r in silent_rows[np.argsort(-scores[silent_rows, j])][:per_list]:
            v, i = split.keys[r]
            lines.append(f"- {scores[r, j]:.2f} | {domain[split.doc[r]]} line {i}: {clip(texts[(v, i)])}")
        misses = []
        for d in np.unique(split.doc[split.pos[:, j]]):
            rows = np.flatnonzero(split.doc == d)
            positive = split.pos[rows, j]
            rank = ranks_of_positives(scores[rows, j], positive)[0]      # the best-ranked quoted paragraph
            if rank > 1:
                top = rows[np.argmax(scores[rows, j])]
                quoted = rows[positive][np.argmax(scores[rows[positive], j])]
                misses.append((rank, len(rows), quoted, top))
        misses.sort(key=lambda m: -m[0])
        lines += ["", f"### Misses ({len(misses)} documents where no quoted paragraph ranked first)", ""]
        for rank, n, quoted, top in misses[:per_list]:
            vq, iq = split.keys[quoted]
            vt, it = split.keys[top]
            lines += [f"- {domain[split.doc[quoted]]}: quoted line {iq} ranked {rank} of {n}: {clip(texts[(vq, iq)])}",
                      f"  - ranked first, line {it}: {clip(texts[(vt, it)])}"]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dataset", type=Path, help="directory written by ml.dataset")
    ap.add_argument("run", type=Path)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--per-list", type=int, default=PER_LIST)
    ap.add_argument("--out", type=Path, help="default: <run>-errors.md next to the run")
    args = ap.parse_args()
    out = args.out or args.run.with_name(args.run.stem + "-errors.md")
    out.write_text(analyze(args.dataset, args.run, args.split, args.per_list), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
