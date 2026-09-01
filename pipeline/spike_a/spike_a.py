"""Spike A: policy document discovery + extraction feasibility test.

Week-1 go/no-go gate. For each domain in sites.txt:

  1. Fetch the homepage.
  2. Find candidate privacy-policy and terms-of-service links
     (link-text match first, then href match, then common paths).
  3. Fetch the best candidate and extract clean text with trafilatura.
  4. Validate: minimum length + document-type keyword check.
  5. Optionally retry with headless Chromium (--playwright) when static
     fetch fails or extraction comes back empty (JS-rendered pages).

Outputs:
  results/report.md           pass/fail table for the week-2 demo
  results/report.json         same data, machine-readable
  results/<domain>/<type>.txt extracted text for manual verification

Success gate (proposal objective 1): >= 16/20 domains yield a validated
privacy policy.

Usage:
  python spike_a.py                  # all sites in sites.txt
  python spike_a.py --domain notion.so
  python spike_a.py --playwright     # enable JS-rendering fallback
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# trafilatura gives the cleanest extraction but depends on lxml, whose
# unsigned DLLs are blocked by Windows Smart App Control on some machines.
# Fall back to a pure-Python BeautifulSoup extractor when unavailable.
try:
    import trafilatura
except Exception:  # ImportError or DLL-load failure inside the import
    trafilatura = None

HERE = Path(__file__).parent
RESULTS = HERE / "results"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36 "
    "ImbroglioSpike/0.1 (student research project; policy analysis feasibility test)"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 20
POLITENESS_DELAY = 1.0  # seconds between domains

# --- link discovery -----------------------------------------------------------

# Matched against visible link text (strongest signal).
TEXT_PATTERNS = {
    "privacy": re.compile(r"privacy\s*(policy|notice|statement)?", re.I),
    "terms": re.compile(r"terms\s*(of\s*(service|use))?|conditions\s*of\s*use|user\s*agreement", re.I),
}

# Matched against the href path (weaker signal).
HREF_PATTERNS = {
    "privacy": re.compile(r"privacy", re.I),
    "terms": re.compile(r"terms|tos\b|conditions|user-?agreement|eula", re.I),
}

# Last resort: probe well-known paths directly.
COMMON_PATHS = {
    "privacy": ["/privacy", "/privacy-policy", "/legal/privacy", "/policies/privacy", "/legal/privacy-policy", "/about/privacy"],
    "terms": ["/terms", "/terms-of-service", "/legal/terms", "/policies/terms", "/tos", "/terms-of-use", "/legal/terms-of-service"],
}

# --- validation ---------------------------------------------------------------

MIN_CHARS = 1500  # real policies are long; short pages are nav shells or errors

VALIDATION_KEYWORDS = {
    "privacy": re.compile(
        r"personal (data|information)|information we collect|data we collect|"
        r"how we (use|share|collect)|third[- ]part(y|ies)|cookies",
        re.I,
    ),
    "terms": re.compile(
        r"agree|liab(le|ility)|termination|governing law|warrant(y|ies)|"
        r"license|prohibited|dispute",
        re.I,
    ),
}


@dataclass
class DocResult:
    doc_type: str
    url: str | None = None
    discovered_via: str | None = None  # link-text | href | common-path
    fetch_status: str | None = None    # http code or error string
    method: str | None = None          # static | playwright
    chars: int = 0
    validated: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class SiteResult:
    domain: str
    homepage_status: str | None = None
    privacy: DocResult = field(default_factory=lambda: DocResult("privacy"))
    terms: DocResult = field(default_factory=lambda: DocResult("terms"))

    @property
    def passed(self) -> bool:
        # Gate counts privacy policy; terms tracked as secondary signal.
        return self.privacy.validated


# --- fetching -----------------------------------------------------------------


def fetch_static(url: str, session: requests.Session) -> tuple[str | None, str]:
    """Return (html, status_note). html is None on failure."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        return None, type(exc).__name__
    if resp.status_code != 200:
        return None, str(resp.status_code)
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and "xml" not in ctype:
        return None, f"200 (non-html: {ctype.split(';')[0]})"
    return resp.text, "200"


def fetch_playwright(url: str) -> tuple[str | None, str]:
    """JS-rendering fallback. Requires: pip install playwright && playwright install chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "playwright-not-installed"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # Default browser UA here, NOT our identifying UA: bot managers
            # (observed: Akamai on privacy.microsoft.com) block a Chrome UA
            # string with a non-Chrome suffix harder than a plain one.
            # Static fetches keep the identifying UA; revisit this trade-off
            # for the production crawler.
            page = browser.new_page()
            # networkidle never fires on sites with constant analytics traffic
            # (observed: duolingo.com) — settle on DOM + fixed hydration wait.
            page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
            return html, "200 (rendered)"
    except Exception as exc:  # playwright raises many types; spike just records them
        return None, f"playwright:{type(exc).__name__}"


# --- discovery ----------------------------------------------------------------


def find_candidates(html: str, base_url: str) -> dict[str, list[tuple[str, str]]]:
    """Return {doc_type: [(url, discovered_via), ...]} ranked best-first."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, list[tuple[str, str]]] = {"privacy": [], "terms": []}
    seen: dict[str, set[str]] = {"privacy": set(), "terms": set()}

    def add(doc_type: str, href: str, via: str) -> None:
        url = urljoin(base_url, href)
        if urlparse(url).scheme not in ("http", "https"):
            return
        if url not in seen[doc_type]:
            seen[doc_type].add(url)
            out[doc_type].append((url, via))

    anchors = soup.find_all("a", href=True)
    # Pass 1: visible link text (strongest signal).
    for a in anchors:
        text = a.get_text(" ", strip=True)
        if not text or len(text) > 60:
            continue
        for doc_type, pat in TEXT_PATTERNS.items():
            if pat.search(text):
                add(doc_type, a["href"], "link-text")
    # Pass 2: href path.
    for a in anchors:
        for doc_type, pat in HREF_PATTERNS.items():
            if pat.search(a["href"]):
                add(doc_type, a["href"], "href")
    return out


# --- extraction ---------------------------------------------------------------


_STRIP_TAGS = ["script", "style", "noscript", "nav", "header", "footer",
               "aside", "form", "button", "svg", "iframe"]


def _bs4_extract(html: str) -> str:
    """Pure-Python fallback: strip chrome, prefer main/article, join text."""
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
            favor_recall=True,  # policies: better to grab too much than truncate
        )
        if text:
            return text
    return _bs4_extract(html)


def validate(doc_type: str, text: str) -> tuple[bool, list[str]]:
    notes = []
    if len(text) < MIN_CHARS:
        notes.append(f"too short ({len(text)} chars < {MIN_CHARS})")
        return False, notes
    if not VALIDATION_KEYWORDS[doc_type].search(text):
        notes.append("length OK but no doc-type keywords found")
        return False, notes
    return True, notes


# --- per-site pipeline --------------------------------------------------------


def _iframe_srcs(html: str, base_url: str) -> list[str]:
    """Some sites embed the policy in an iframe (observed: bear.app)."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for frame in soup.find_all("iframe", src=True):
        url = urljoin(base_url, frame["src"])
        if urlparse(url).scheme in ("http", "https"):
            out.append(url)
    return out


def process_document(
    domain: str,
    doc_type: str,
    candidates: list[tuple[str, str]],
    session: requests.Session,
    use_playwright: bool,
) -> DocResult:
    result = DocResult(doc_type)

    # Discovered candidates first, then common-path probes; iframe srcs get
    # appended dynamically when a candidate page turns out to be a shell.
    probes = candidates + [
        (f"https://{domain}{path}", "common-path") for path in COMMON_PATHS[doc_type]
    ]
    tried: set[str] = set()

    i = 0
    while i < len(probes) and i < 12:  # cap attempts per doc type
        url, via = probes[i]
        i += 1
        if url in tried:
            continue
        tried.add(url)
        html, status = fetch_static(url, session)
        method = "static"
        if html is None and use_playwright:
            html, status = fetch_playwright(url)
            method = "playwright"
        if html is None:
            result.notes.append(f"{via} {url} -> {status}")
            continue

        text = extract_text(html)
        if len(text) < MIN_CHARS and use_playwright and method == "static":
            # Static fetch worked but extraction is thin — likely JS-rendered body.
            rendered, rstatus = fetch_playwright(url)
            if rendered:
                rtext = extract_text(rendered)
                if len(rtext) > len(text):
                    html, text, status, method = rendered, rtext, rstatus, "playwright"

        ok, notes = validate(doc_type, text)
        result.url = url
        result.discovered_via = via
        result.fetch_status = status
        result.method = method
        result.chars = len(text)
        result.validated = ok
        result.notes.extend(notes)

        if ok:
            out_dir = RESULTS / domain
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{doc_type}.txt").write_text(text, encoding="utf-8")
            return result
        # Shell page? Its iframes may hold the real document.
        for src in _iframe_srcs(html, url):
            probes.append((src, "iframe"))
        # Keep best-so-far recorded, but try the next candidate.
    return result


def process_site(domain: str, use_playwright: bool) -> SiteResult:
    site = SiteResult(domain)
    session = requests.Session()

    homepage = f"https://{domain}"
    html, status = fetch_static(homepage, session)
    if html is None and use_playwright:
        html, status = fetch_playwright(homepage)
    site.homepage_status = status

    candidates: dict[str, list[tuple[str, str]]] = {"privacy": [], "terms": []}
    if html:
        candidates = find_candidates(html, homepage)
    if use_playwright and not (candidates["privacy"] or candidates["terms"]):
        # Static homepage was a JS shell (or blocked) — re-render and retry
        # discovery on the hydrated DOM.
        rendered, rstatus = fetch_playwright(homepage)
        if rendered:
            site.homepage_status = rstatus
            candidates = find_candidates(rendered, homepage)

    site.privacy = process_document(domain, "privacy", candidates["privacy"], session, use_playwright)
    site.terms = process_document(domain, "terms", candidates["terms"], session, use_playwright)
    return site


# --- reporting ----------------------------------------------------------------


def doc_cell(doc: DocResult) -> str:
    if doc.validated:
        return f"PASS ({doc.chars:,} chars, {doc.discovered_via}, {doc.method})"
    if doc.url is None:
        return "FAIL (no candidate found)"
    return f"FAIL ({'; '.join(doc.notes[-2:]) or doc.fetch_status})"


def write_report(sites: list[SiteResult]) -> None:
    RESULTS.mkdir(exist_ok=True)
    passed = sum(s.passed for s in sites)
    gate = "PASS" if passed >= 0.8 * len(sites) else "FAIL"

    lines = [
        "# Spike A — Extraction Feasibility Report",
        "",
        f"**Result: {passed}/{len(sites)} privacy policies extracted and validated — gate {gate}**",
        "(gate: >= 80% per proposal objective 1)",
        "",
        "| Domain | Privacy policy | Terms of service |",
        "| --- | --- | --- |",
    ]
    for s in sites:
        lines.append(f"| {s.domain} | {doc_cell(s.privacy)} | {doc_cell(s.terms)} |")
    lines += [
        "",
        "Extracted text is in `results/<domain>/` — manually verify a sample",
        "against the live page (proposal requires manual verification).",
    ]
    (RESULTS / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (RESULTS / "report.json").write_text(
        json.dumps([asdict(s) for s in sites], indent=2), encoding="utf-8"
    )


# --- main ---------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--domain", help="run a single domain instead of sites.txt")
    ap.add_argument("--playwright", action="store_true", help="enable headless-browser fallback")
    args = ap.parse_args()

    if args.domain:
        domains = [args.domain]
    else:
        sites_file = HERE / "sites.txt"
        domains = [
            line.strip()
            for line in sites_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]

    results: list[SiteResult] = []
    for i, domain in enumerate(domains):
        print(f"[{i + 1}/{len(domains)}] {domain} ...", flush=True)
        site = process_site(domain, args.playwright)
        results.append(site)
        print(f"    privacy: {doc_cell(site.privacy)}")
        print(f"    terms:   {doc_cell(site.terms)}")
        if i < len(domains) - 1:
            time.sleep(POLITENESS_DELAY)

    write_report(results)
    passed = sum(s.passed for s in results)
    print(f"\n{passed}/{len(results)} passed — report at {RESULTS / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
