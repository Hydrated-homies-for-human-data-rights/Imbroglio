"""Analysis step: stored document version -> findings -> scores.

    ensure_analyzed(conn, version_id)

Called by the worker after a crawl and by the backfill CLI. Order of
preference, cheapest first:

  1. already analyzed with this rubric -> nothing to do
  2. identical text already analyzed for another site (same content hash)
     -> copy those findings, no LLM call (design goal 6, M3)
  3. otherwise one LLM extraction call, if the daily budget allows

Every call is recorded in extraction_runs; findings and scores are written in
the same transaction so a scorecard is never half-updated.
"""

from __future__ import annotations

import logging
import os

import psycopg

from . import scorer
from .llm_extract import Extraction, extract
from .rubric import load

log = logging.getLogger("imbroglio")

RUBRIC_VERSION = os.environ.get("RUBRIC_VERSION", "v0.1")
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "claude-sonnet-5")
# Hard ceiling on LLM spend per rolling 24 hours (all callers combined). When
# reached, crawling continues but analysis waits; the Console spend limit is
# the second, independent backstop.
DAILY_BUDGET_USD = float(os.environ.get("EXTRACTION_DAILY_BUDGET_USD", "5"))


def extraction_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("EXTRACTION_ENABLED", "1") == "1"


def spent_last_24h(conn: psycopg.Connection) -> float:
    row = conn.execute("""SELECT coalesce(sum(cost_usd), 0) FROM extraction_runs
                          WHERE created_at > now() - interval '24 hours'""").fetchone()
    return float(row[0])


def _has_findings(conn, version_id: int, rubric_version: str) -> bool:
    return conn.execute("SELECT 1 FROM findings WHERE version_id = %s AND rubric_version = %s LIMIT 1",
                        (version_id, rubric_version)).fetchone() is not None


def _reusable_version(conn, version_id: int, rubric_version: str) -> int | None:
    """Another version with the same text that already has findings."""
    row = conn.execute(
        """SELECT other.id FROM document_versions me
           JOIN document_versions other ON other.content_hash = me.content_hash AND other.id <> me.id
           WHERE me.id = %s
             AND EXISTS (SELECT 1 FROM findings f WHERE f.version_id = other.id AND f.rubric_version = %s)
           ORDER BY other.fetched_at DESC LIMIT 1""",
        (version_id, rubric_version),
    ).fetchone()
    return row[0] if row else None


def _write_scores(conn, version_id: int, rubric_version: str) -> dict[str, str]:
    rubric = load(rubric_version)
    rows = conn.execute("SELECT check_id, status, verified FROM findings WHERE version_id = %s AND rubric_version = %s",
                        (version_id, rubric_version)).fetchall()
    tiers = scorer.category_tiers(rubric, [scorer.ScoredFinding(*r) for r in rows])
    for category, tier in tiers.items():
        conn.execute(
            """INSERT INTO scores (version_id, rubric_version, scorer_version, category, tier)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (version_id, rubric_version, scorer_version, category)
               DO UPDATE SET tier = EXCLUDED.tier, created_at = now()""",
            (version_id, rubric_version, scorer.SCORER_VERSION, category, tier),
        )
    return tiers


def _store(conn, version_id: int, rubric_version: str, ex: Extraction, run_id: int) -> None:
    for f in ex.findings:
        conn.execute(
            """INSERT INTO findings (version_id, run_id, rubric_version, check_id, category, status,
                                     quotes, quotes_verified, verified, explanation, model)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (version_id, rubric_version, check_id) DO UPDATE SET
                 run_id = EXCLUDED.run_id, status = EXCLUDED.status, quotes = EXCLUDED.quotes,
                 quotes_verified = EXCLUDED.quotes_verified, verified = EXCLUDED.verified,
                 explanation = EXCLUDED.explanation, model = EXCLUDED.model,
                 reused_from_version_id = NULL, created_at = now()""",
            (version_id, run_id, rubric_version, f.check_id, f.category, f.status, f.quotes,
             f.quotes_verified, f.verified, f.explanation, ex.model),
        )


def _copy_findings(conn, source_version: int, version_id: int, rubric_version: str) -> None:
    conn.execute(
        """INSERT INTO findings (version_id, run_id, rubric_version, check_id, category, status, quotes,
                                 quotes_verified, verified, explanation, model, provenance,
                                 reused_from_version_id)
           SELECT %s, run_id, rubric_version, check_id, category, status, quotes, quotes_verified,
                  verified, explanation, model, provenance, version_id
           FROM findings WHERE version_id = %s AND rubric_version = %s
           ON CONFLICT (version_id, rubric_version, check_id) DO NOTHING""",
        (version_id, source_version, rubric_version),
    )


def ensure_analyzed(conn: psycopg.Connection, version_id: int, *, force: bool = False,
                    model: str | None = None, rubric_version: str | None = None) -> str:
    """Returns what happened: done-already | reused | analyzed | skipped:<why> | failed:<why>."""
    rubric_version = rubric_version or RUBRIC_VERSION
    if not force and _has_findings(conn, version_id, rubric_version):
        return "done-already"

    source = None if force else _reusable_version(conn, version_id, rubric_version)
    if source is not None:
        _copy_findings(conn, source, version_id, rubric_version)
        _write_scores(conn, version_id, rubric_version)
        conn.commit()
        log.info("analysis: identical text already analyzed (version %d), reused", source)
        return "reused"

    if not extraction_enabled():
        return "skipped:extraction disabled or no API key"
    spent = spent_last_24h(conn)
    if spent >= DAILY_BUDGET_USD:
        log.info("analysis: daily LLM budget reached ($%.2f of $%.2f), skipping", spent, DAILY_BUDGET_USD)
        return "skipped:daily budget reached"

    text = conn.execute("SELECT normalized_text FROM document_versions WHERE id = %s",
                        (version_id,)).fetchone()[0]
    rubric = load(rubric_version)
    log.info("analysis: reading the document with %s (%d checks)", model or EXTRACTION_MODEL,
             len(rubric.checks))
    ex = extract(text, rubric, model or EXTRACTION_MODEL)
    run_id = conn.execute(
        """INSERT INTO extraction_runs (version_id, rubric_version, model, status, stop_reason,
               input_tokens, output_tokens, cache_read_tokens, cost_usd, seconds, error)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (version_id, rubric_version, ex.model, ex.status, ex.stop_reason, ex.input_tokens,
         ex.output_tokens, ex.cache_read_tokens, ex.cost_usd, ex.seconds, ex.error),
    ).fetchone()[0]
    if ex.status != "ok":
        conn.commit()
        log.info("analysis: extraction %s (%s)", ex.status, ex.error)
        return f"failed:{ex.status}"
    _store(conn, version_id, rubric_version, ex, run_id)
    tiers = _write_scores(conn, version_id, rubric_version)
    conn.commit()
    verified = sum(f.verified and f.status != "not_disclosed" for f in ex.findings)
    log.info("analysis: %d verified findings, headline %s, $%.3f", verified,
             scorer.headline(tiers), ex.cost_usd)
    return "analyzed"


def rebase(conn: psycopg.Connection, version_id: int, from_version: str, to_version: str) -> str:
    """Carry a document's findings from one rubric version to another
    without a new LLM call: the model's answers and quotes are kept, and
    every quote is re-checked under the new rubric's rules (statuses,
    evidence terms), then the document is re-scored. Valid when the new
    rubric keeps the same checks and statuses (calibration changes);
    question changes need a fresh extraction instead."""
    from .llm_extract import check_findings

    if _has_findings(conn, version_id, to_version):
        return "done-already"
    rows = conn.execute(
        """SELECT check_id, status, quotes, explanation, model, run_id, provenance, reused_from_version_id
           FROM findings WHERE version_id = %s AND rubric_version = %s""",
        (version_id, from_version)).fetchall()
    if not rows:
        return "skipped:no findings to rebase"
    text = conn.execute("SELECT normalized_text FROM document_versions WHERE id = %s",
                        (version_id,)).fetchone()[0]
    rubric = load(to_version)
    raw = [{"check_id": r[0], "status": r[1], "quotes": r[2], "explanation": r[3] or ""} for r in rows]
    meta = {r[0]: r for r in rows}
    for f in check_findings(rubric, raw, text):
        if f.check_id not in meta:
            continue  # the new rubric added a check: needs a real extraction
        _, _, _, _, model, run_id, provenance, reused_from = meta[f.check_id]
        conn.execute(
            """INSERT INTO findings (version_id, run_id, rubric_version, check_id, category, status,
                                     quotes, quotes_verified, verified, explanation, model,
                                     provenance, reused_from_version_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (version_id, rubric_version, check_id) DO NOTHING""",
            (version_id, run_id, to_version, f.check_id, f.category, f.status, f.quotes,
             f.quotes_verified, f.verified, f.explanation, model, provenance, reused_from),
        )
    _write_scores(conn, version_id, to_version)
    conn.commit()
    return "rebased"
