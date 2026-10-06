"""LLM extraction (design spec: Extraction Service, naive v1).

One call per document answers every rubric check with a status and verbatim
quotes. "Naive" per the spec: whole document, fixed prompt, no retrieval; it
is the baseline that the retrieval workstream has to beat.

The model only extracts. Everything it returns is checked in code:
  * unknown check ids are dropped; unanswered checks are recorded as such
  * a status outside the rubric's list for that check is rejected
  * every quote is verified against the stored text (verify.py)
Scoring happens elsewhere, deterministically (scorer.py).

Reproducibility (N2): Opus 5 and Sonnet 5 don't accept sampling settings, so
determinism is measured (repeat runs) rather than configured; Haiku 4.5 runs
at temperature 0.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .rubric import NOT_DISCLOSED, Rubric
from .verify import verify_quotes

UNANSWERED = "unanswered"
MAX_DOCUMENT_CHARS = 400_000   # ~100k tokens; refuse rather than silently truncate
MAX_QUOTES = 3

# USD per million tokens (input, output). Cache reads bill at 10% of input.
MODELS = {
    "claude-opus-5": {"label": "Opus 5", "price": (5.00, 25.00)},
    "claude-sonnet-5": {"label": "Sonnet 5", "price": (2.00, 10.00)},
    "claude-haiku-4-5": {"label": "Haiku 4.5", "price": (1.00, 5.00)},
}
ALIASES = {"opus": "claude-opus-5", "sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5"}


def system_prompt(rubric: Rubric) -> str:
    """Static per rubric version (cache-friendly: nothing request-specific)."""
    lines = [
        "You read a website's privacy policy or terms of service and answer a fixed list of "
        "questions about it for a public scorecard. Every answer you give will be shown to the "
        "public next to the quotes you cite, so accuracy matters more than coverage.",
        "",
        "Rules:",
        "1. Answer every check below, once each, using its check_id.",
        "2. Choose the status only from that check's allowed statuses.",
        f"3. If the document does not address the question, answer \"{NOT_DISCLOSED}\" with no "
        "quotes. Never infer a practice the document doesn't state, and never rely on outside "
        "knowledge of the company.",
        f"4. Otherwise give 1 to {MAX_QUOTES} quotes copied character-for-character from the "
        "document: no paraphrasing, no fixing typos, no joining separate sentences. Prefer one "
        "complete sentence. Use \" ... \" only to skip words inside a single passage.",
        "5. The explanation is one plain sentence linking the quote to the status. Describe what "
        "the document says, never the company's motives.",
        "",
        f"Rubric {rubric.version} checks:",
    ]
    for c in rubric.checks:
        lines.append("")
        lines.append(f"check_id: {c.id}  (category: {rubric.categories[c.category]})")
        lines.append(f"question: {c.question}")
        if c.guidance:
            lines.append(f"guidance: {c.guidance}")
        lines.append("allowed statuses:")
        for s in c.statuses.values():
            lines.append(f"  - {s.name}: {s.meaning}")
        lines.append(f"  - {NOT_DISCLOSED}: The document does not address this")
    return "\n".join(lines)


def output_schema(rubric: Rubric) -> dict:
    return {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "check_id": {"type": "string", "enum": [c.id for c in rubric.checks]},
                        "status": {"type": "string"},
                        "quotes": {"type": "array", "items": {"type": "string"}},
                        "explanation": {"type": "string"},
                    },
                    "required": ["check_id", "status", "quotes", "explanation"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["findings"],
        "additionalProperties": False,
    }


@dataclass
class Finding:
    check_id: str
    category: str
    status: str
    quotes: list[str]
    quotes_verified: list[bool]
    verified: bool
    explanation: str


@dataclass
class Extraction:
    model: str                      # the model that actually answered
    status: str                     # ok | refused | error
    findings: list[Finding] = field(default_factory=list)
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str | None = None

    @property
    def quote_verification_rate(self) -> float | None:
        flags = [v for f in self.findings for v in f.quotes_verified]
        return sum(flags) / len(flags) if flags else None


def cost(model: str, input_tokens: int, output_tokens: int, cache_read: int) -> float:
    price_in, price_out = MODELS.get(model, MODELS["claude-opus-5"])["price"]
    return (input_tokens * price_in + cache_read * price_in * 0.1 + output_tokens * price_out) / 1e6


def check_findings(rubric: Rubric, raw: list[dict], document: str) -> list[Finding]:
    """Validate model output against the rubric and verify every quote."""
    by_id: dict[str, dict] = {}
    for item in raw:
        if item.get("check_id") in {c.id for c in rubric.checks} and item["check_id"] not in by_id:
            by_id[item["check_id"]] = item
    out = []
    for c in rubric.checks:
        item = by_id.get(c.id)
        if item is None:
            out.append(Finding(c.id, c.category, UNANSWERED, [], [], False,
                               "The model did not answer this check."))
            continue
        status = str(item.get("status", "")).strip()
        quotes = [q for q in (item.get("quotes") or []) if isinstance(q, str) and q.strip()][:MAX_QUOTES]
        explanation = str(item.get("explanation", "")).strip()
        if status not in c.allowed():
            out.append(Finding(c.id, c.category, status, quotes, [False] * len(quotes), False,
                               f"Rejected: '{status}' is not an allowed status for this check."))
            continue
        if status == NOT_DISCLOSED:
            # A claim of silence has nothing to quote; quotes would contradict it.
            out.append(Finding(c.id, c.category, status, [], [], not quotes, explanation))
            continue
        flags = verify_quotes(quotes, document)
        out.append(Finding(c.id, c.category, status, quotes, flags, any(flags), explanation))
    return out


def extract(document: str, rubric: Rubric, model: str, client=None) -> Extraction:
    """Run one extraction call. Never raises for API problems: the returned
    Extraction carries status/error so callers can record the attempt."""
    import anthropic

    model = ALIASES.get(model, model)
    if len(document) > MAX_DOCUMENT_CHARS:
        return Extraction(model, "error", error=f"document too long ({len(document):,} chars)")
    client = client or anthropic.Anthropic()

    kwargs: dict = dict(
        model=model,
        max_tokens=16000,
        system=system_prompt(rubric),
        messages=[{"role": "user", "content":
                   f"<document>\n{document}\n</document>\n\nAnswer every check for this document."}],
    )
    output_config: dict = {"format": {"type": "json_schema", "schema": output_schema(rubric)}}
    if model.startswith("claude-haiku"):
        kwargs["extra_body"] = {"temperature": 0}   # still honored by Haiku 4.5
    else:
        output_config["effort"] = "medium"
    if model == "claude-opus-5":
        # Server-side fallback if the model declines (e.g. a policy page that
        # trips a safety classifier): the API re-runs on a fallback model.
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs.setdefault("extra_body", {})["fallbacks"] = "default"
    kwargs["output_config"] = output_config

    t0 = time.monotonic()
    try:
        resp = client.beta.messages.create(**kwargs)
    except anthropic.APIStatusError as exc:
        return Extraction(model, "error", seconds=time.monotonic() - t0,
                          error=f"{type(exc).__name__} {exc.status_code}: {str(exc)[:300]}")
    except anthropic.APIConnectionError as exc:
        return Extraction(model, "error", seconds=time.monotonic() - t0,
                          error=f"connection: {str(exc)[:300]}")
    seconds = time.monotonic() - t0

    served_by = getattr(resp, "model", None) or model
    usage = resp.usage
    result = Extraction(
        served_by, "ok", stop_reason=resp.stop_reason, seconds=seconds,
        input_tokens=usage.input_tokens or 0, output_tokens=usage.output_tokens or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
    )
    result.cost_usd = cost(served_by, result.input_tokens, result.output_tokens,
                           result.cache_read_tokens)
    if resp.stop_reason == "refusal":
        result.status, result.error = "refused", "model declined"
        return result
    if resp.stop_reason == "max_tokens":
        result.status, result.error = "error", "response cut off at max_tokens"
        return result
    text = next((b.text for b in resp.content if b.type == "text"), None)
    try:
        raw = json.loads(text or "")["findings"]
    except (ValueError, KeyError, TypeError) as exc:
        result.status, result.error = "error", f"unparseable output: {exc}"
        return result
    result.findings = check_findings(rubric, raw, document)
    return result
