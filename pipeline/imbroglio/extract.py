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


def extract_text(html: str) -> str:
    if trafilatura is not None:
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            favor_recall=True,  # over-grab beats truncating legal text
        )
        if text:
            return text
    return _bs4_extract(html)
