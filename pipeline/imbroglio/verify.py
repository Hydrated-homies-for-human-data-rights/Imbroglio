"""Quote verification (F4, design goal 2: "no quote, no finding").

Every quote the model returns must be found in the stored document text. The
comparison forgives only differences that don't change meaning:

  * whitespace and line breaks
  * typographic vs straight quotes, dashes, ellipsis characters
  * letter case
  * an ellipsis inside the quote ("We collect ... your email") — each piece
    must appear, in order

Anything else — a paraphrase, a changed word, a merged sentence — fails, and a
finding with no verified quote is stored but never shown or scored. A strict
fuzzy pass (>= 0.95 similarity over a candidate window) only absorbs OCR-like
noise such as a dropped character, never a reworded clause, and never a
quote whose negations (not, never, no, n't, ...) differ from the source.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

MIN_QUOTE_CHARS = 12      # shorter "quotes" ("we do", "yes") prove nothing
FUZZY_THRESHOLD = 0.95

_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
    " ": " ", " ": " ", " ": " ",
})
_ELLIPSIS = re.compile(r"\s*(?:\.\s*\.\s*\.|…|\[\s*\.\.\.\s*\])\s*")


def canon(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_TRANSLATE)
    return re.sub(r"\s+", " ", text).strip().lower()


def _find_piece(piece: str, doc: str, start: int) -> int:
    """Index just past `piece` in `doc` at or after `start`, or -1."""
    i = doc.find(piece, start)
    if i >= 0:
        return i + len(piece)
    if len(piece) < 40:
        return -1  # short pieces must match exactly; fuzzy would accept near-anything
    # Anchor on the longest exact run, then compare a same-sized window.
    m = SequenceMatcher(None, doc, piece, autojunk=False)
    block = max(m.get_matching_blocks(), key=lambda b: b.size)
    if block.size < len(piece) * 0.3:
        return -1
    lo = max(start, block.a - block.b - 10)
    window = doc[lo: lo + len(piece) + 20]
    best = SequenceMatcher(None, window, piece, autojunk=False)
    if best.ratio() * (len(window) + len(piece)) / (2 * len(piece)) < FUZZY_THRESHOLD:
        return -1
    # A near-match may differ by only a few characters, and "not" is three:
    # "we do sell" vs "we do not sell". Never let fuzziness flip a negation.
    if _negations(window) != _negations(piece):
        return -1
    return lo + len(window)


_NEGATION = re.compile(r"\b(?:not|no|never|none|nor|neither|cannot|without)\b|n't\b")


def _negations(text: str) -> int:
    return len(_NEGATION.findall(text))


def verify_quote(quote: str, document: str, *, _doc_canon: str | None = None) -> bool:
    q = canon(quote).strip(" \"'")
    if len(q) < MIN_QUOTE_CHARS:
        return False
    doc = _doc_canon if _doc_canon is not None else canon(document)
    pos = 0
    for piece in (p.strip(" \"'") for p in _ELLIPSIS.split(q)):
        if not piece:
            continue
        pos = _find_piece(piece, doc, pos)
        if pos < 0:
            return False
    return True


def verify_quotes(quotes: list[str], document: str) -> list[bool]:
    doc = canon(document)
    return [verify_quote(q, document, _doc_canon=doc) for q in quotes]
