"""Quotes the evidence-word check turned away, and the words that would let them in.

    python -m imbroglio.cli rejected-quotes --rubric v0.2
    python -m imbroglio.cli rejected-quotes --rubric v0.2 --check collects_from_third_parties --samples 40
    python -m imbroglio.cli rejected-quotes --rubric v0.2 --out runs/rejected.md --csv runs/rejected.csv

A quote counts only if it is in the document word for word AND contains one
of its question's evidence words (rubric `evidence`). Nearly every quote the
model cites is real (99.4%), but about a fifth fail the evidence check: some
are off topic, others answer the question in words the list doesn't have.
This report separates the two kinds of failure, shows samples of the
rejected quotes for a person to judge, and suggests evidence words, each with:

  rescued   how many rejected quotes it would let in
  answers   how many answers would gain their first counting quote (those
            answers start counting toward ratings)
  elsewhere how often the word appears in quotes that count for OTHER
            questions. High means it isn't specific to this question, so it
            would also let in off-topic quotes. Prefer words low here.

Read-only and free: it re-checks the stored quotes against the stored text in
code, with no model calls and no writes. Changing evidence words is a
calibration: a new rubric version with the wider lists can take the existing
findings with `cli rebase-rubric`, no new AI run.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .rubric import NOT_DISCLOSED, Rubric
from .verify import exact_quotes

# Words that carry no topic on their own. Suggestions skip these, and a
# two-word phrase needs at least one word that isn't one of them.
STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have
having he her here hers him his how i if in into is it its itself just may me might more most must my
no nor not of off on once only or other our ours out over own same shall she should so some such than
that the their theirs them then there these they this those through to too under until up upon us very
was we were what when where which while who whom why will with would you your yours
information personal data use used using including include includes such certain also services service
""".split())
WORD = re.compile(r"[a-z][a-z'-]*[a-z]|[a-z]")
MIN_RESCUED = 2           # a suggestion must rescue at least this many quotes
MAX_ELSEWHERE = 0.25      # and appear in at most this share of other questions' counting quotes


@dataclass
class Quote:
    check_id: str
    status: str
    domain: str
    doc_type: str
    text: str
    found: bool               # in the document word for word
    relevant: bool            # contains an evidence word
    answer: int               # which answer (finding) it belongs to


@dataclass
class CheckReport:
    check_id: str
    quotes: int = 0
    found: int = 0
    counted: int = 0
    rejected: list[Quote] = field(default_factory=list)     # found, but no evidence word
    answers: int = 0
    answers_counted: int = 0
    answers_rescuable: int = 0                               # no counting quote, but a found one


def terms(text: str) -> set[str]:
    """Lowercase words and two-word phrases in `text` that could serve as
    evidence words: no stopword alone, no phrase of two stopwords."""
    words = WORD.findall(text.lower())
    out = {w for w in words if w not in STOPWORDS and len(w) > 2}
    out |= {f"{a} {b}" for a, b in zip(words, words[1:]) if not (a in STOPWORDS and b in STOPWORDS)}
    return out


def check_quotes(rubric: Rubric, rows: list[tuple]) -> list[Quote]:
    """Rows are (domain, doc_type, normalized_text, [(check_id, status, quotes), ...]),
    one per document. Each quote is re-checked against the document's text,
    both ways (word for word, evidence words), exactly as llm_extract does."""
    out: list[Quote] = []
    answer = 0
    known = {c.id for c in rubric.checks}
    for domain, doc_type, text, findings in rows:
        for check_id, status, quotes in findings:
            if check_id not in known or status == NOT_DISCLOSED or not quotes:
                continue
            check = rubric.check(check_id)
            if status not in check.statuses:
                continue
            answer += 1
            for q, exact in zip(quotes, exact_quotes(quotes, text)):
                shown = exact if exact is not None else q
                out.append(Quote(check_id, status, domain, doc_type, shown, exact is not None,
                                 exact is not None and check.relevant(shown), answer))
    return out


def summarize(rubric: Rubric, quotes: list[Quote]) -> dict[str, CheckReport]:
    reports = {c.id: CheckReport(c.id) for c in rubric.checks}
    by_answer: dict[int, list[Quote]] = defaultdict(list)
    for q in quotes:
        r = reports[q.check_id]
        r.quotes += 1
        r.found += q.found
        r.counted += q.relevant
        if q.found and not q.relevant:
            r.rejected.append(q)
        by_answer[q.answer].append(q)
    for qs in by_answer.values():
        r = reports[qs[0].check_id]
        r.answers += 1
        if any(q.relevant for q in qs):
            r.answers_counted += 1
        elif any(q.found for q in qs):
            r.answers_rescuable += 1
    return reports


@dataclass(frozen=True)
class Suggestion:
    term: str
    rescued: int
    answers: int
    elsewhere: float


def suggest(rubric: Rubric, quotes: list[Quote], check_id: str, top: int = 15) -> list[Suggestion]:
    """Evidence words for `check_id`, best first: the most rejected quotes
    rescued, among words that are rare in other questions' counting quotes."""
    check = rubric.check(check_id)
    rejected = [q for q in quotes if q.check_id == check_id and q.found and not q.relevant]
    if not rejected:
        return []
    others = [terms(q.text) for q in quotes if q.check_id != check_id and q.relevant]
    # answers that have no counting quote yet: rescuing one of their quotes makes them count
    uncounted = {q.answer for q in quotes if q.check_id == check_id} - {
        q.answer for q in quotes if q.check_id == check_id and q.relevant}
    rescues: dict[str, list[Quote]] = defaultdict(list)
    for q in rejected:
        for t in terms(q.text):
            if not any(e in t or t in e for e in check.evidence):
                rescues[t].append(q)
    out = []
    for t, qs in rescues.items():
        if len(qs) < MIN_RESCUED:
            continue
        elsewhere = sum(t in o for o in others) / len(others) if others else 0.0
        if elsewhere > MAX_ELSEWHERE:
            continue
        out.append(Suggestion(t, len(qs), len({q.answer for q in qs} & uncounted), elsewhere))
    out.sort(key=lambda s: (-s.answers, -s.rescued, s.elsewhere, s.term))
    # drop a phrase when a word inside it rescues the same quotes (keep the shorter term)
    kept: list[Suggestion] = []
    for s in out:
        if not any(k.term in s.term and k.rescued >= s.rescued for k in kept):
            kept.append(s)
    return kept[:top]


def _pct(n: int, d: int) -> str:
    return f"{n / d:.1%}" if d else ""


def report(rubric: Rubric, quotes: list[Quote], *, only: str | None = None,
           samples: int = 12, top: int = 15) -> str:
    reports = summarize(rubric, quotes)
    total = len(quotes)
    found = sum(q.found for q in quotes)
    counted = sum(q.relevant for q in quotes)
    lines = [
        f"# Rejected quotes, rubric {rubric.version}",
        "",
        f"{total:,} cited quotes. {_pct(found, total)} found word for word in the document; "
        f"{_pct(counted, total)} also contain an evidence word and count. "
        f"{found - counted:,} real quotes were turned away by the evidence-word check.",
        "",
        "## By question, most turned away first",
        "",
        "| Question | Quotes | Word for word | Count | Turned away | Answers counting | Answers a wider list could rescue |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    order = sorted(reports.values(), key=lambda r: (-len(r.rejected), r.check_id))
    for r in order:
        if r.quotes:
            lines.append(f"| `{r.check_id}` | {r.quotes} | {_pct(r.found, r.quotes)} | {_pct(r.counted, r.quotes)} "
                         f"| {len(r.rejected)} | {r.answers_counted} of {r.answers} | {r.answers_rescuable} |")
    lines.append("")

    for r in order:
        if not r.rejected or (only and r.check_id != only):
            continue
        check = rubric.check(r.check_id)
        lines += [f"## `{r.check_id}`", "", f"{check.question}", "",
                  "Evidence words now: " + ", ".join(f"`{e}`" for e in check.evidence), ""]
        sugg = suggest(rubric, quotes, r.check_id, top)
        if sugg:
            lines += ["Suggested evidence words (judge each against the samples below):", "",
                      "| Word | Quotes rescued | Answers that would start counting | In other questions' quotes |",
                      "| --- | --- | --- | --- |"]
            lines += [f"| `{s.term}` | {s.rescued} | {s.answers} | {s.elsewhere:.0%} |" for s in sugg]
            lines.append("")
        lines += [f"Turned away ({len(r.rejected)}; first {min(samples, len(r.rejected))} shown, by site):", ""]
        for q in sorted(r.rejected, key=lambda q: (q.domain, q.text))[:samples]:
            text = q.text if len(q.text) <= 300 else q.text[:297] + "..."
            lines.append(f"- {q.domain} ({q.doc_type}, `{q.status}`): \"{text}\"")
        lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, quotes: list[Quote]) -> None:
    """Every turned-away quote, with an empty `on_topic` column for a person
    to fill in (yes / no): the answer key for choosing evidence words."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["check_id", "status", "domain", "document", "quote", "on_topic"])
        for q in sorted((q for q in quotes if q.found and not q.relevant), key=lambda q: (q.check_id, q.domain)):
            w.writerow([q.check_id, q.status, q.domain, q.doc_type, q.text, ""])


def load_rows(conn, rubric_version: str) -> list[tuple]:
    """Per latest document version with findings under this rubric:
    (domain, doc_type, normalized_text, [(check_id, status, quotes)]).
    Findings copied from an identical document are skipped, so shared
    boilerplate policies count once."""
    rows = conn.execute(
        """WITH latest AS (
               SELECT DISTINCT ON (d.id) s.domain, d.doc_type, v.id AS version_id, v.normalized_text
               FROM documents d JOIN services s ON s.id = d.service_id
               JOIN document_versions v ON v.document_id = d.id
               ORDER BY d.id, v.fetched_at DESC)
           SELECT l.domain, l.doc_type, l.normalized_text, f.check_id, f.status, f.quotes
           FROM latest l JOIN findings f ON f.version_id = l.version_id
           WHERE f.rubric_version = %s AND f.reused_from_version_id IS NULL
           ORDER BY l.domain, l.doc_type, f.check_id""",
        (rubric_version,),
    ).fetchall()
    docs: dict[tuple, tuple] = {}
    for domain, doc_type, text, check_id, status, quotes in rows:
        key = (domain, doc_type)
        if key not in docs:
            docs[key] = (domain, doc_type, text, [])
        docs[key][3].append((check_id, status, list(quotes or [])))
    return list(docs.values())
