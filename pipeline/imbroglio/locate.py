"""Document discovery: domain -> (url, clean text, provenance).

The escalation ladder Spike A earned the hard way, in cost order:
  1. static homepage -> link-text candidates (cheapest, ~70% of sites)
  2. href-pattern candidates, then well-known paths (/privacy, /legal/terms)
  3. Playwright homepage re-render when static HTML is a JS shell
  4. Playwright render of candidate pages that extract thin
  5. iframe follow when a candidate page is a shell around the real document

Each rung only fires when the cheaper one fails, so the common case stays
fast and the crawler stays polite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .extract import extract_text
from .fetch import fetch_rendered, fetch_static

TEXT_PATTERNS = {
    "privacy": re.compile(r"privacy\s*(policy|notice|statement)?", re.I),
    "terms": re.compile(r"terms\s*(of\s*(service|use))?|conditions\s*of\s*use|user\s*agreement", re.I),
}
HREF_PATTERNS = {
    "privacy": re.compile(r"privacy", re.I),
    "terms": re.compile(r"terms|tos\b|conditions|user-?agreement|eula", re.I),
}
COMMON_PATHS = {
    "privacy": ["/privacy", "/privacy-policy", "/legal/privacy", "/policies/privacy",
                "/legal/privacy-policy", "/about/privacy"],
    "terms": ["/terms", "/terms-of-service", "/legal/terms", "/policies/terms",
              "/tos", "/terms-of-use", "/legal/terms-of-service"],
}

MIN_CHARS = 1500
VALIDATION_KEYWORDS = {
    "privacy": re.compile(
        r"personal (data|information)|information we collect|data we collect|"
        r"how we (use|share|collect)|third[- ]part(y|ies)|cookies", re.I),
    "terms": re.compile(
        r"agree|liab(le|ility)|termination|governing law|warrant(y|ies)|"
        r"license|prohibited|dispute", re.I),
}

MAX_PROBES = 12


@dataclass
class Located:
    doc_type: str
    ok: bool = False
    url: str | None = None
    discovered_via: str | None = None
    fetch_method: str | None = None
    text: str = ""
    notes: list[str] = field(default_factory=list)


def _candidates(html: str, base_url: str) -> dict[str, list[tuple[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, list[tuple[str, str]]] = {"privacy": [], "terms": []}
    seen: dict[str, set[str]] = {"privacy": set(), "terms": set()}

    def add(doc_type: str, href: str, via: str) -> None:
        url = urljoin(base_url, href)
        if urlparse(url).scheme in ("http", "https") and url not in seen[doc_type]:
            seen[doc_type].add(url)
            out[doc_type].append((url, via))

    anchors = soup.find_all("a", href=True)
    for a in anchors:  # link text: strongest signal
        text = a.get_text(" ", strip=True)
        if text and len(text) <= 60:
            for doc_type, pat in TEXT_PATTERNS.items():
                if pat.search(text):
                    add(doc_type, a["href"], "link-text")
    for a in anchors:  # href fallback
        for doc_type, pat in HREF_PATTERNS.items():
            if pat.search(a["href"]):
                add(doc_type, a["href"], "href")
    return out


def _iframe_srcs(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [
        urljoin(base_url, fr["src"])
        for fr in soup.find_all("iframe", src=True)
        if urlparse(urljoin(base_url, fr["src"])).scheme in ("http", "https")
    ]


def _validate(doc_type: str, text: str) -> bool:
    return len(text) >= MIN_CHARS and bool(VALIDATION_KEYWORDS[doc_type].search(text))


def _try_url(url: str, doc_type: str, session: requests.Session,
             use_playwright: bool) -> tuple[str | None, str, str, str]:
    """Returns (html, text, status, method) — html None on fetch failure."""
    html, status = fetch_static(url, session)
    method = "static"
    if html is None and use_playwright:
        html, status = fetch_rendered(url)
        method = "playwright"
    if html is None:
        return None, "", status, method
    text = extract_text(html)
    if len(text) < MIN_CHARS and use_playwright and method == "static":
        rendered, rstatus = fetch_rendered(url)
        if rendered:
            rtext = extract_text(rendered)
            if len(rtext) > len(text):
                return rendered, rtext, rstatus, "playwright"
    return html, text, status, method


def locate_document(domain: str, doc_type: str,
                    candidates: list[tuple[str, str]],
                    session: requests.Session,
                    use_playwright: bool) -> Located:
    result = Located(doc_type)
    probes = candidates + [
        (f"https://{domain}{p}", "common-path") for p in COMMON_PATHS[doc_type]
    ]
    tried: set[str] = set()
    i = 0
    while i < len(probes) and i < MAX_PROBES:
        url, via = probes[i]
        i += 1
        if url in tried:
            continue
        tried.add(url)

        html, text, status, method = _try_url(url, doc_type, session, use_playwright)
        if html is None:
            result.notes.append(f"{via} {url} -> {status}")
            continue

        result.url, result.discovered_via, result.fetch_method = url, via, method
        if _validate(doc_type, text):
            result.ok, result.text = True, text
            return result
        result.notes.append(f"{via} {url} -> thin ({len(text)} chars)")
        for src in _iframe_srcs(html, url):  # shell page? follow its iframes
            probes.append((src, "iframe"))
    return result


def locate_all(domain: str, use_playwright: bool = True) -> dict[str, Located]:
    """Discover and extract both document types for a domain."""
    session = requests.Session()
    homepage = f"https://{domain}"
    html, _status = fetch_static(homepage, session)

    cands: dict[str, list[tuple[str, str]]] = {"privacy": [], "terms": []}
    if html:
        cands = _candidates(html, homepage)
    if use_playwright and not (cands["privacy"] or cands["terms"]):
        rendered, _ = fetch_rendered(homepage)  # JS-shell homepage
        if rendered:
            cands = _candidates(rendered, homepage)

    return {
        dt: locate_document(domain, dt, cands[dt], session, use_playwright)
        for dt in ("privacy", "terms")
    }
