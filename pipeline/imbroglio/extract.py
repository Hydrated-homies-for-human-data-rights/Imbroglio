"""HTML -> clean policy text.

trafilatura when importable (best quality); pure-Python BeautifulSoup
fallback otherwise (lxml's unsigned DLLs are blocked by Windows Smart App
Control on some team machines — the fallback keeps everyone unblocked).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

try:
    import trafilatura
except Exception:  # ImportError or DLL-load failure inside the import
    trafilatura = None

_STRIP_TAGS = ["script", "style", "noscript", "nav", "header", "footer",
               "aside", "form", "button", "svg", "iframe"]


def _bs4_extract(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    root = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )
    text = root.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)


PARAGRAPH = 120        # a line this long is policy prose, not a menu item or heading
MIN_DROPPED = 3000     # chars of paragraphs trafilatura must have dropped to fall back


def _flat(text: str) -> str:
    return " ".join(text.split())


def _paragraphs(text: str) -> int:
    return sum(len(line) for line in text.splitlines() if len(line) >= PARAGRAPH)


def _dropped(full: str, kept: str) -> int:
    """Chars of paragraphs in `full` that `kept` doesn't contain."""
    k = _flat(kept)
    return sum(len(line) for line in full.splitlines()
               if len(line) >= PARAGRAPH and _flat(line)[:80] not in k)


def extract_text(html: str) -> str:
    if trafilatura is not None:
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            favor_recall=True,  # over-grab beats truncating legal text
        )
        if text:
            # On pages built from sibling sections trafilatura can keep just
            # one: 6k of Microsoft's 114k Services Agreement, and about half
            # of Pinterest's privacy policy. Survey of 927 stored documents
            # (Oct 30, 2026): 21 lost at least 3,000 chars of paragraphs, and
            # at least half again what they kept. Comparing whole paragraphs
            # keeps trafilatura where the fallback only adds menus (lovense)
            # or a second copy of the same text (ebay).
            full = _bs4_extract(html)
            dropped = _dropped(full, text)
            if dropped >= MIN_DROPPED and dropped >= _paragraphs(text) / 2:
                return full
            return text
    return _bs4_extract(html)
