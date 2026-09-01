"""Text canonicalization + content hashing.

Why this exists: change monitoring compares hashes of successive fetches.
Without canonicalization, cosmetic noise (whitespace layout, unicode encoding
of the same character, BOM, CRLF) produces spurious "changes" — the proposal
budget is at most 1 false positive per 100 document-checks, and this module
is where that budget is won or lost.

Deliberately NOT normalized: case, punctuation, wording. A visible edit to
the text is a real change and must alter the hash.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata


def normalize(text: str) -> str:
    # Unicode compatibility form: same glyph, same bytes.
    text = unicodedata.normalize("NFKC", text)
    # Strip BOM / zero-width characters that render invisibly.
    text = re.sub(r"[​‌‍﻿]", "", text)
    # Line endings and per-line trailing space.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # Collapse runs: many spaces -> one, 3+ newlines -> 2.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
