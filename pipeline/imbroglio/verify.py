"""Quote verification (F4, design goal 2: "no quote, no finding").

Every quote the model returns must be found in the stored document text. The
comparison forgives only differences that don't change meaning:

  * whitespace and line breaks
  * typographic vs straight quotes, dashes, ellipsis characters
  * letter case
  * an ellipsis inside the quote ("We collect ... your email address") —
    each piece must appear, in order, close to the one before (_spans)

Anything else — a paraphrase, a changed word, a merged sentence — fails, and a
finding with no verified quote is stored but never shown or scored. A strict
fuzzy pass (>= 0.95 similarity over a candidate window) only absorbs OCR-like
noise such as a dropped character, never a reworded clause, and never a
quote whose negations (not, never, no, n't, ...) differ from the source.

Because of that tolerance, the model's copy of a quote can differ slightly
from the document (seen: "publly perform" for "publicly perform").
exact_quote() returns the document's own words for a verified quote, and
that is what gets stored and shown: a receipt must be verbatim.
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


def _canon_map(text: str) -> tuple[str, list[int]]:
    """Canonical form (see module docstring) plus, for every canonical
    character, the index of the original character it came from, so a match
    in canonical text can be cut back out of the original document."""
    out: list[str] = []
    origin: list[int] = []
    space = True                      # drops leading whitespace
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKC", ch).translate(_TRANSLATE).lower():
            if c.isspace():
                if space:
                    continue
                c, space = " ", True
            else:
                space = False
            out.append(c)
            origin.append(i)
    if out and out[-1] == " ":         # and trailing whitespace
        out.pop()
        origin.pop()
    return "".join(out), origin


def canon(text: str) -> str:
    return _canon_map(text)[0]


def _find_piece(piece: str, doc: str, start: int) -> tuple[int, int] | None:
    """(start, end) of `piece` in `doc` at or after `start`, or None."""
    i = doc.find(piece, start)
    if i >= 0:
        return i, i + len(piece)
    if len(piece) < 40:
        return None  # short pieces must match exactly; fuzzy would accept near-anything
    # Anchor on the longest exact run, then compare a same-sized window.
    # Only the rest of the document: a quote's pieces come in order, and
    # rescanning from the top on every anchor try would multiply the work.
    m = SequenceMatcher(None, doc[start:], piece, autojunk=False)
    block = max(m.get_matching_blocks(), key=lambda b: b.size)
    if block.size < len(piece) * 0.3:
        return None
    lo = max(start, start + block.a - block.b - 10)
    window = doc[lo: lo + len(piece) + 20]
    best = SequenceMatcher(None, window, piece, autojunk=False)
    if best.ratio() * (len(window) + len(piece)) / (2 * len(piece)) < FUZZY_THRESHOLD:
        return None
    # A near-match may differ by only a few characters, and "not" is three:
    # "we do sell" vs "we do not sell". Never let fuzziness flip a negation.
    if _negations(window) != _negations(piece):
        return None
    blocks = [b for b in best.get_matching_blocks() if b.size]
    return lo + blocks[0].a, lo + blocks[-1].a + blocks[-1].size


_NEGATION = re.compile(r"\b(?:not|no|never|none|nor|neither|cannot|without)\b|n't\b")


def _negations(text: str) -> int:
    return len(_NEGATION.findall(text))


# An ellipsis skips words inside one passage; it must not stitch a claim
# together from words scattered across the document ("We ... sell ... your
# data"). So the pieces must sit close together, none may be a lone word,
# and one of them must be a real clause. A four-word floor for every piece
# was tried and would reject quotes like "We collect your email address ...
# approximate location", where a list ends in a short noun phrase.
MAX_PIECE_GAP = 300        # canonical characters skipped between two pieces
MIN_PIECE_WORDS = 2
MIN_ANCHOR_WORDS = 4       # the longest piece of an ellipsis quote
MAX_ANCHOR_TRIES = 50      # places tried for the first piece of an ellipsis quote
MAX_PIECES = 4             # ellipsis pieces in one quote (bounds the work per quote)


def _chain(pieces: list[str], doc: str, start: int) -> list[tuple[int, int]] | None:
    """Spans of `pieces` in order with the first at or after `start`, each
    taken at its earliest place after the one before, or None."""
    spans: list[tuple[int, int]] = []
    pos = start
    for piece in pieces:
        span = _find_piece(piece, doc, pos)
        if span is None or (spans and span[0] - spans[-1][1] > MAX_PIECE_GAP):
            return None
        # What the ellipsis skips must not hold a negation: "We do ... sell
        # your data" is not a quote of "We do not sell your data".
        if spans and _negations(doc[spans[-1][1]:span[0]]):
            return None
        spans.append(span)
        pos = span[1]
    return spans


def _spans(quote: str, doc: str) -> list[tuple[int, int]] | None:
    """Canonical-text spans of each piece of `quote`, in order, or None."""
    q = canon(quote).strip(" \"'")
    if len(q) < MIN_QUOTE_CHARS:
        return None
    pieces = [p for p in (p.strip(" \"'") for p in _ELLIPSIS.split(q)) if p]
    if not pieces:
        return None
    if len(pieces) == 1:
        return _chain(pieces, doc, 0)
    if len(pieces) > MAX_PIECES:
        return None
    words = [len(p.split()) for p in pieces]
    if min(words) < MIN_PIECE_WORDS or max(words) < MIN_ANCHOR_WORDS:
        return None
    # The first piece's earliest place can be too far from the second while a
    # later one is close (boilerplate repeats), so try its other exact places.
    start = 0
    for _ in range(MAX_ANCHOR_TRIES):
        spans = _chain(pieces, doc, start)
        if spans is not None:
            return spans
        nxt = doc.find(pieces[0], start)
        if nxt < 0:
            return None
        start = nxt + 1
    return None


def verify_quote(quote: str, document: str, *, _doc_canon: str | None = None) -> bool:
    doc = _doc_canon if _doc_canon is not None else canon(document)
    return _spans(quote, doc) is not None


def verify_quotes(quotes: list[str], document: str) -> list[bool]:
    doc = canon(document)
    return [verify_quote(q, document, _doc_canon=doc) for q in quotes]


def quote_offsets(quotes: list[str], document: str) -> list[list[tuple[int, int]] | None]:
    """For each quote: the (start, end) offsets in `document` of each piece
    where it matched, or None if it doesn't verify. Evidence words are the
    rubric's business, not checked here."""
    doc, origin = _canon_map(document)
    out: list[list[tuple[int, int]] | None] = []
    for q in quotes:
        spans = _spans(q, doc)
        out.append(None if spans is None else [(origin[s], origin[e - 1] + 1) for s, e in spans])
    return out


def exact_quotes(quotes: list[str], document: str) -> list[str | None]:
    """For each quote: the document's own words where it matched (pieces of
    an ellipsis quote joined with " ... ", whitespace collapsed), or None if
    it doesn't verify."""
    return [None if offsets is None else
            " ... ".join(" ".join(document[a:b].split()) for a, b in offsets)
            for offsets in quote_offsets(quotes, document)]


def exact_quote(quote: str, document: str) -> str | None:
    return exact_quotes([quote], document)[0]
