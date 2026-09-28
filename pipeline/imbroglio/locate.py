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

import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

log = logging.getLogger("imbroglio")

import requests
from bs4 import BeautifulSoup

from .extract import extract_text
from .fetch import fetch_rendered, fetch_static

TEXT_PATTERNS = {
    # English first; then the link text ToS;DR's non-English services use in
    # their footers (German, French, Spanish, Italian, Dutch, Portuguese,
    # Japanese, Chinese, Korean).
    "privacy": re.compile(
        r"privacy\s*(policy|notice|statement)?|datenschutz|confidentialit[ée]|"
        r"privacidad|privacidade|informativa sulla privacy|privacyverklaring|"
        r"プライバシー|個人情報|隐私|개인정보", re.I),
    "terms": re.compile(
        r"terms\s*(of\s*(service|use))?|conditions\s*of\s*use|user\s*agreement|"
        r"\bagb\b|nutzungsbedingungen|conditions g[ée]n[ée]rales|mentions l[ée]gales|"
        r"t[ée]rminos|termini|algemene voorwaarden|termos de uso|"
        r"利用規約|服务条款|用户协议|이용약관", re.I),
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
MIN_KEYWORD_HITS = 2  # distinct signals, so one stray word can't validate a page

# Each entry is one independent signal; a document must hit MIN_KEYWORD_HITS
# distinct ones. Batch 2 showed a single-keyword English list rejecting real
# policies (privacy-respecting sites that "collect nothing" never say
# "information we collect"; German/French policies use their own words).
VALIDATION_SIGNALS = {
    "privacy": [re.compile(p, re.I) for p in (
        r"personal (data|information)|personally identifiable",
        r"(information|data) (we|that we) (collect|process|store)|we (do not |don't )?collect",
        r"third[- ]part(y|ies)",
        r"cookies?\b",
        r"ip address|log ?files?|server logs",
        r"data protection|gdpr|ccpa|data controller",
        r"retain|retention|delete your",
        r"privacy (policy|notice|statement)",
        r"datenschutz|personenbezogen|donn[ée]es personnelles|datos personales|"
        r"dati personali|persoonsgegevens|dados pessoais",
    )],
    "terms": [re.compile(p, re.I) for p in (
        r"terms (of (service|use)|and conditions)|user agreement",
        r"\bagree(ment)?\b",
        r"liab(le|ility)",
        r"terminat(e|ion)",
        r"governing law|jurisdiction|arbitration",
        r"warrant(y|ies)|as is",
        r"licen[cs]e",
        r"prohibited|you (may|must) not",
        r"intellectual property|copyright",
        r"nutzungsbedingungen|\bagb\b|conditions g[ée]n[ée]rales|t[ée]rminos y condiciones|"
        r"termini e condizioni|algemene voorwaarden",
    )],
}

# Iframes worth following: same site, or a URL that looks like a legal doc.
# Batch 2 followed captcha walls, Stripe widgets and ad banners.
LEGAL_URL = re.compile(r"privacy|terms|legal|polic(y|ies)|tos\b|datenschutz|agb", re.I)
CAPTCHA_URL = re.compile(r"captcha|challenge|cf-chl|perimeterx|px-cdn|datadome", re.I)

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


def _iframe_srcs(html: str, base_url: str, domain: str) -> tuple[list[str], bool]:
    """Returns (followable iframe URLs, page_is_captcha_wall)."""
    soup = BeautifulSoup(html, "html.parser")
    follow: list[str] = []
    captcha = False
    for fr in soup.find_all("iframe", src=True):
        url = urljoin(base_url, fr["src"])
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            continue
        if CAPTCHA_URL.search(url):
            captcha = True
            continue
        host = parsed.hostname or ""
        if host == domain or host.endswith("." + domain) or LEGAL_URL.search(parsed.path):
            follow.append(url)
    return follow, captcha


def _validate(doc_type: str, text: str) -> tuple[bool, str]:
    """Returns (ok, reason). The reason separates a short page from a long
    page that doesn't read like this document type; batch 2's notes lumped
    both together as 'thin'."""
    if len(text) < MIN_CHARS:
        return False, f"too short ({len(text)} chars)"
    hits = sum(1 for sig in VALIDATION_SIGNALS[doc_type] if sig.search(text))
    if hits < MIN_KEYWORD_HITS:
        return False, f"no {doc_type} signals ({len(text)} chars, {hits} hit)"
    return True, ""


def _try_url(url: str, doc_type: str, session: requests.Session,
             use_playwright: bool) -> tuple[str | None, str, str, str]:
    """Returns (html, text, status, method) — html None on fetch failure."""
    html, status = fetch_static(url, session)
    method = "static"
    # A 404/410 or a non-HTML response won't change by rendering it; batch 2
    # spent most of its time budget launching Chromium on guessed-path 404s.
    permanent = status in ("404", "410") or status.startswith("200 (non-html")
    if html is None and use_playwright and not permanent:
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
                    use_playwright: bool,
                    deadline: float | None = None) -> Located:
    result = Located(doc_type)
    probes = candidates + [
        (f"https://{domain}{p}", "common-path") for p in COMMON_PATHS[doc_type]
    ]
    tried: set[str] = set()
    seen_texts: set[str] = set()
    i = 0
    while i < len(probes) and i < MAX_PROBES:
        if deadline is not None and time.monotonic() > deadline:
            log.info("[%s] time budget spent, giving up", doc_type)
            result.notes.append("time budget exceeded")
            break
        url, via = probes[i]
        i += 1
        if url in tried:
            continue
        tried.add(url)

        log.info("[%s] trying %s (%s)", doc_type, url, via)
        html, text, status, method = _try_url(url, doc_type, session, use_playwright)
        if html is None:
            log.info("[%s]   fetch failed (%s)", doc_type, status)
            result.notes.append(f"{via} {url} -> {status}")
            continue

        result.url, result.discovered_via, result.fetch_method = url, via, method
        ok, reason = _validate(doc_type, text)
        if ok:
            log.info("[%s]   got %s chars via %s fetch — looks like a real document",
                     doc_type, f"{len(text):,}", method)
            result.ok, result.text = True, text
            return result
        log.info("[%s]   rejected: %s", doc_type, reason)
        result.notes.append(f"{via} {url} -> {reason}")

        # Soft 404: the site serves the same page for any path. Once a guessed
        # path repeats earlier content, the remaining guesses will too.
        if text in seen_texts and via == "common-path":
            log.info("[%s]   same page as an earlier probe (soft 404), skipping guessed paths", doc_type)
            result.notes.append("soft 404: guessed paths all return the same page")
            probes = probes[:i] + [p for p in probes[i:] if p[1] != "common-path"]
            continue
        seen_texts.add(text)

        frames, captcha = _iframe_srcs(html, url, domain)
        if captcha:
            log.info("[%s]   captcha wall, stopping", doc_type)
            result.notes.append("blocked: captcha wall")
            break
        for src in frames:  # shell page? follow its iframes
            log.info("[%s]   page embeds an iframe, queueing %s", doc_type, src)
            probes.append((src, "iframe"))
    if not result.ok:
        log.info("[%s] no candidate produced a valid document", doc_type)
    return result


def locate_all(domain: str, use_playwright: bool = True,
               time_budget: float | None = None) -> dict[str, Located]:
    """Discover and extract both document types for a domain.

    time_budget (seconds) caps the probe loop for batch runs, so one slow or
    hostile site can't hold a worker for minutes. Checked between probes, so a
    single in-flight fetch can overrun it by up to one fetch timeout.
    """
    deadline = time.monotonic() + time_budget if time_budget else None
    session = requests.Session()
    homepage = f"https://{domain}"
    log.info("fetching homepage %s", homepage)
    html, home_status = fetch_static(homepage, session)
    home_notes: list[str] = [] if html else [f"homepage static -> {home_status}"]

    cands: dict[str, list[tuple[str, str]]] = {"privacy": [], "terms": []}
    if html:
        cands = _candidates(html, homepage)
        log.info("homepage links: %d privacy candidate(s), %d terms candidate(s)",
                 len(cands["privacy"]), len(cands["terms"]))
    else:
        log.info("homepage static fetch failed")
    # Re-render when EITHER type is missing: batch 3 had JS-built footers
    # (gls.de, nicovideo.jp) where a stray match for one type suppressed the
    # re-render the other type needed.
    if use_playwright and not (cands["privacy"] and cands["terms"]):
        log.info("missing candidates in static HTML — re-rendering homepage in headless browser")
        rendered, rstatus = fetch_rendered(homepage)  # JS-shell homepage
        if not rendered:
            home_notes.append(f"homepage render -> {rstatus}")
        if rendered:
            rcands = _candidates(rendered, homepage)
            # Merge: keep static finds first, add anything the render revealed.
            for dt in ("privacy", "terms"):
                have = {u for u, _ in cands[dt]}
                cands[dt] += [c for c in rcands[dt] if c[0] not in have]
            log.info("rendered homepage links: %d privacy, %d terms",
                     len(cands["privacy"]), len(cands["terms"]))

    # Unreachable host: the homepage failed at the connection level (not an
    # HTTP status) both statically and rendered. Guessed paths on the same
    # host fail the same way, and batch 4 showed them burning the whole time
    # budget (cyberghostvpn.com, hidemyass.com, ok.ru, adobe.com).
    home_failed_rendered = any(n.startswith("homepage render") for n in home_notes)
    if not html and not home_status.isdigit() and (home_failed_rendered or not use_playwright):
        log.info("host unreachable, skipping discovery")
        return {dt: Located(dt, notes=home_notes + ["host unreachable"])
                for dt in ("privacy", "terms")}

    results = {
        dt: locate_document(domain, dt, cands[dt], session, use_playwright, deadline)
        for dt in ("privacy", "terms")
    }
    for loc in results.values():
        if not loc.ok:
            loc.notes[:0] = home_notes  # homepage outcome explains most misses
    return results
