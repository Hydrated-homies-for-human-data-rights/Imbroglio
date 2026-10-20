"""Training-data export for the classifier workstream.

    python -m imbroglio.cli export-labels --out exports/labels-v0.1

Writes, for the latest analyzed version of every document:
  labels.jsonl     one row per (document, rubric check): status, quotes, verified flags
  documents.jsonl  one row per document version: the full normalized text
  rubric.yaml      the rubric the labels were made with
plus README.md (copied from export_README.md) explaining the format and its traps.

With --stdout it prints both kinds of rows as JSON lines instead (each with a
"kind" field), for running on the production container over SSH without
writing files there; split_stdout() turns that stream back into the files.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .rubric import RUBRIC_DIR, load

README = Path(__file__).parent / "export_README.md"


def rows(conn, rubric_version: str):
    rubric = load(rubric_version)
    latest = conn.execute(
        """WITH latest AS (
             SELECT DISTINCT ON (v.document_id) v.id, v.document_id
             FROM document_versions v
             WHERE EXISTS (SELECT 1 FROM findings f WHERE f.version_id = v.id AND f.rubric_version = %s)
             ORDER BY v.document_id, v.fetched_at DESC)
           SELECT l.id, s.domain, d.doc_type, d.url, v.content_hash, v.normalized_text
           FROM latest l JOIN documents d ON d.id = l.document_id
           JOIN services s ON s.id = d.service_id
           JOIN document_versions v ON v.id = l.id
           ORDER BY s.domain, d.doc_type""", (rubric_version,)).fetchall()
    for version_id, domain, doc_type, url, chash, text in latest:
        yield {"kind": "document", "version_id": version_id, "domain": domain, "doc_type": doc_type,
               "url": url, "content_hash": chash, "text": text}
        for check_id, status, quotes, flags, verified, expl, model, prov in conn.execute(
                """SELECT check_id, status, quotes, quotes_verified, verified, explanation, model, provenance
                   FROM findings WHERE version_id = %s AND rubric_version = %s ORDER BY check_id""",
                (version_id, rubric_version)):
            check = rubric.check(check_id)
            st = check.statuses.get(status)
            yield {"kind": "label", "version_id": version_id, "domain": domain, "doc_type": doc_type,
                   "rubric_version": rubric_version, "check_id": check_id, "category": check.category,
                   "status": status, "exposure": st.exposure if st else None,
                   "quotes": list(quotes or []), "quotes_verified": list(flags or []),
                   "verified": verified, "explanation": expl, "labeler": model, "provenance": prov}


def write(out: Path, stream, rubric_version: str) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    counts = {"document": 0, "label": 0}
    with (out / "documents.jsonl").open("w", encoding="utf-8") as docs, \
         (out / "labels.jsonl").open("w", encoding="utf-8") as labels:
        for row in stream:
            kind = row.pop("kind")
            (docs if kind == "document" else labels).write(json.dumps(row, ensure_ascii=False) + "\n")
            counts[kind] += 1
    shutil.copy(RUBRIC_DIR / f"{rubric_version}.yaml", out / "rubric.yaml")
    shutil.copy(README, out / "README.md")
    return counts


def split_stdout(lines, out: Path, rubric_version: str) -> dict[str, int]:
    return write(out, (json.loads(l) for l in lines if l.strip().startswith("{")), rubric_version)


def run(out: Path | None, rubric_version: str, to_stdout: bool) -> int:
    from . import db

    conn = db.connect()
    try:
        if to_stdout:
            for row in rows(conn, rubric_version):
                sys.stdout.write(json.dumps(row, ensure_ascii=False) + "\n")
            return 0
        counts = write(out, rows(conn, rubric_version), rubric_version)
    finally:
        conn.close()
    print(f"wrote {counts['document']} documents and {counts['label']} labels -> {out}")
    return 0
