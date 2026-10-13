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
    # "/legal" last: a legal hub (spotify) lists both documents by name, and
    # hub-link following takes it from there.
    "privacy": ["/privacy", "/privacy-policy", "/legal/privacy", "/policies/privacy",
                "/legal/privacy-policy", "/about/privacy", "/legal"],
    "terms": ["/terms", "/terms-of-service", "/legal/terms", "/policies/terms",
              "/tos", "/terms-of-use", "/legal/terms-of-service", "/legal"],
}

# Link text that names the document itself ("Privacy Policy") outranks a bare
# "Privacy" footer link.
STRONG_TEXT = {
    "privacy": re.compile(
        r"privacy\s*(policy|notice|statement)|datenschutzerkl[äa]rung|politique de confidentialit|"
        r"pol[íi]tica de privacidad|informativa sulla privacy|privacyverklaring|"
        r"プライバシーポリシー|隐私政策|개인정보\s*처리방침", re.I),
    "terms": re.compile(
        r"terms\s*(of\s*(service|use)|(and|&)\s*conditions)|user\s*agreement|conditions\s*of\s*use|"
        r"nutzungsbedingungen|\bagb\b|conditions g[ée]n[ée]rales|t[ée]rminos (y condiciones|de (uso|servicio))|"
        r"利用規約|服务条款|用户协议|이용약관", re.I),
}
# Pages about the document rather than the document: settings, opt-out forms,
# privacy hubs, regional supplements, terms for side programs. Observed on
# production data: snapchat "Your Privacy Choices", spotify "Safety & Privacy",
# paypal's Rewards Program terms, snapchat's Geofilter terms.
SIDE_DOC = {
    "privacy": re.compile(
        r"choices|cent(er|re)|settings|preferences|do[- ]not[- ](sell|share)|opt[- ]?out|cookie|safety|"
        r"supplement|european|\beu\b|\beea\b|\buk\b|california|outside the united states|"
        r"for (creators|business|enterprise|developers)", re.I),
    "terms": re.compile(
        r"reward|program|geofilter|seller|developer|\bapi\b|partner|promo|sweepstake|gift|affiliate|"
        r"advertis|creator|merchant|supplement|additional|community guidelines|acceptable use|brand|"
        r"balance|cashback|campaign|credit card|debit card|lens studio|creative tools",
        re.I),
}
# Narrower version for a fetched document's title (its opening characters):
# real policies often mention cookies or partners in their first sentence.
# The side word has to be attached to the document's name ("Privacy
# Supplement", "Geofilter Terms"): airbnb's main policy opens with "For a list
# of supplements to this Privacy Policy".
SIDE_TITLE = {
    "privacy": re.compile(
        r"privacy (policy |notice )?supplement|supplement(al)? privacy|cookie (policy|notice|statement)|"
        r"privacy (choices|settings|cent(er|re))|(policy|notice) for (creators|business|enterprise|developers)|"
        r"california privacy (notice|policy|rights)", re.I),
    "terms": re.compile(
        r"(reward|program|geofilter|seller|developer|partner|promo|sweepstake|gift card|affiliate|"
        r"advertis|creator|merchant|supplement|balance|cashback|campaign|credit card|debit card|"
        r"lens studio|creative tools|donor|giving fund)\w*[\w\s'’-]{0,25}?\b(terms|agreement|conditions)|"
        r"community guidelines|acceptable use", re.I),
}
# Articles, not policies (observed: proton.me's privacy link led to a blog post).
# Help-center "articles" are left out on purpose: airbnb and zendesk-hosted
# sites keep their real policies there.
NON_DOC_PATH = re.compile(r"/(blog|news|newsroom|press|stories|careers|jobs)(/|$)", re.I)

MIN_CHARS = 1500
# A valid page shorter than this is often a hub that links to the real policy
# (apple.com/privacy, reddit.com/privacy, paypal's privacy center). It is kept
# as a fallback while discovery follows its links; small sites with genuinely
# short policies still end up with it.
SUBSTANTIAL_CHARS = 6000
SIDE_HEAD_CHARS = 150   # how much of a document's opening counts as its title
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

MAX_PROBES = 16   # hub pages add probes; the time budget still caps the total

# Two-label public suffixes common in our data; good enough to tell
# "policies.google.com" apart from "sololearn.com" without a full suffix list.
_MULTI_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au", "co.jp",
    "ne.jp", "or.jp", "com.br", "com.cn", "co.nz", "co.in", "com.mx", "co.kr",
    "com.tr", "com.sg", "co.za", "com.ar", "com.tw", "com.hk",
}

# Bot-challenge / CAPTCHA interstitials. A homepage like this is a wall, not
# the site: its links (e.g. "Privacy" -> cloudflare.com/privacypolicy) belong
# to the wall's vendor. Observed: 11 sites stored Cloudflare's own policy.
CHALLENGE_MARKERS = re.compile(
    r"challenge-platform|cf-chl-|cf_chl_|<title>\s*just a moment|attention required! \| cloudflare|"
    r"checking (if the site connection is secure|your browser)|verify you are human|"
    r"captcha-delivery\.com|px-captcha|hcaptcha\.com/1/api|please enable js and disable any ad blocker",
    re.I,
)


def site_of(host: str) -> str:
    """Registrable domain: 'policies.google.com' -> 'google.com'."""
    labels = (host or "").lower().rstrip(".").split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _MULTI_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def brand_of(domain: str) -> str:
    """'linustechtips.com' -> 'linustechtips'; 'bbc.co.uk' -> 'bbc'."""
    return site_of(domain).split(".")[0]


def is_challenge(html: str) -> bool:
    return bool(html) and bool(CHALLENGE_MARKERS.search(html[:200_000]))


@dataclass
class Located:
    doc_type: str
    ok: bool = False
    url: str | None = None
    discovered_via: str | None = None
    fetch_method: str | None = None
    text: str = ""
    notes: list[str] = field(default_factory=list)
    html: str = field(default="", repr=False)   # the page itself, for its links to the other document


COMMON_PATH_RANK = 5
_FILLER = re.compile(
    r"\b(our|the|read|full|view|see|main|legal|global|updated|new|current|here|and|of|a|an|your|"
    r"website|site|english|en|us|policy|notice)\b|[^\w\s]", re.I)


def _qualified(text: str, match: re.Match, host: str) -> bool:
    """Does link text name something more specific than the document itself?
    Brand and filler words don't count: 'Read our PayPal User Agreement' is
    plain, 'PayPal Giving Fund Donor Terms of Service' is qualified."""
    rest = (text[:match.start()] + " " + text[match.end():]).lower()
    rest = rest.replace(brand_of(host), " ")
    return bool(_FILLER.sub(" ", rest).split())


def rank(doc_type: str, url: str, via: str, text: str = "") -> int:
    """Probe order, lower first. A link that names the document beats a bare
    footer link, which beats a guessed path; settings pages, side-program
    terms, articles and links to the other document type sink below the
    guessed paths; another site's link comes last."""
    other = "terms" if doc_type == "privacy" else "privacy"
    path = urlparse(url).path
    if via == "common-path":
        r = COMMON_PATH_RANK
    elif via.startswith("href"):
        r = 4
    else:  # link text, or a link followed from a hub page
        m = STRONG_TEXT[doc_type].search(text)
        r = 0 if m else 2
        if m and _qualified(text, m, urlparse(url).hostname or ""):
            r += 1          # "PayPal Giving Fund Donor Terms of Service" vs "User Agreement"
        if TEXT_PATTERNS[other].search(text):
            r += 1          # "Privacy & terms": could be either
    if SIDE_DOC[doc_type].search(text) or SIDE_DOC[doc_type].search(path):
        r += 3
    if HREF_PATTERNS[other].search(path) and not HREF_PATTERNS[doc_type].search(path):
        r += 4              # dropbox: "Privacy & terms" -> /terms
    if NON_DOC_PATH.search(path):
        r += 6
    if via.endswith("-external"):
        r += 10
    return r


_TRACKING_PARAM = re.compile(r"^(utm_\w+|__hs\w+|_ga|_gl|ref_?|fbclid|gclid|mc_[ce]id)$", re.I)


def _strip_tracking(url: str) -> str:
    """Drop analytics parameters, so one page linked three ways (reddit's
    HubSpot-tagged links) is one probe, not three."""
    p = urlparse(url)
    if not p.query:
        return url
    keep = [kv for kv in p.query.split("&") if not _TRACKING_PARAM.match(kv.split("=", 1)[0])]
    return p._replace(query="&".join(keep)).geturl()


def _same_page(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    host = lambda h: (h or "").lower().removeprefix("www.")
    return host(pa.hostname) == host(pb.hostname) and pa.path.rstrip("/") == pb.path.rstrip("/")


def _candidates(html: str, base_url: str, via_text: str = "link-text"
                ) -> dict[str, list[tuple[str, str, int]]]:
    """Policy-looking links as (url, via, rank), best first. Links to another
    site get a '-external' suffix on their via-label; they rank last and are
    only accepted if the document mentions the site (see _external_ok)."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, dict[str, tuple[str, int]]] = {"privacy": {}, "terms": {}}
    home_site = site_of(urlparse(base_url).hostname or "")

    def add(doc_type: str, href: str, via: str, text: str = "") -> None:
        url = _strip_tracking(urljoin(base_url, href).split("#")[0])
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return
        if site_of(parsed.hostname or "") != home_site:
            via += "-external"
        r = rank(doc_type, url, via, text)
        if url not in found[doc_type] or r < found[doc_type][url][1]:
            found[doc_type][url] = (via, r)   # same URL, better link text: keep the better rank

    anchors = soup.find_all("a", href=True)
    for a in anchors:  # link text: strongest signal
        text = a.get_text(" ", strip=True)
        if text and len(text) <= 80:
            for doc_type, pat in TEXT_PATTERNS.items():
                if pat.search(text):
                    add(doc_type, a["href"], via_text, text)
    for a in anchors:  # href fallback
        for doc_type, pat in HREF_PATTERNS.items():
            if pat.search(a["href"]):
                add(doc_type, a["href"], "href")
    # dicts keep insertion order, and sorted() is stable: page order breaks ties
    return {dt: sorted(((u, v, r) for u, (v, r) in found[dt].items()), key=lambda c: c[2])
            for dt in found}


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


def _external_ok(domain: str, text: str) -> bool:
    """A policy hosted on another site counts only if it names this site.
    Google's policy names YouTube (legit: youtube.com uses it); Cloudflare's
    and reCAPTCHA's links lead to policies that never name the site."""
    brand = brand_of(domain)
    return len(brand) >= 3 and brand.lower() in text.lower()


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
                    candidates: list[tuple[str, str, int]],
                    session: requests.Session,
                    use_playwright: bool,
                    deadline: float | None = None,
                    guess_paths: bool = True) -> Located:
    result = Located(doc_type)
    guesses = [(f"https://{domain}{p}", "common-path", COMMON_PATH_RANK)
               for p in COMMON_PATHS[doc_type]] if guess_paths else []
    probes = sorted(candidates + guesses, key=lambda p: p[2])
    tried: set[str] = set()
    seen_texts: set[str] = set()
    fallback: Located | None = None   # first valid but short page (maybe a hub)
    i = 0
    while i < len(probes) and i < MAX_PROBES:
        if deadline is not None and time.monotonic() > deadline:
            log.info("[%s] time budget spent, giving up", doc_type)
            result.notes.append("time budget exceeded")
            break
        url, via, _ = probes[i]
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

        if is_challenge(html):
            log.info("[%s]   bot-challenge page, skipping", doc_type)
            result.notes.append(f"{via} {url} -> blocked: bot challenge")
            continue

        result.url, result.discovered_via, result.fetch_method = url, via, method
        ok, reason = _validate(doc_type, text)
        if ok and via.endswith("-external") and not _external_ok(domain, text):
            ok, reason = False, f"another site's document (doesn't mention {brand_of(domain)})"
        # Links on this page that name the document ("Privacy Policy", "Main
        # Privacy Policy (English)") and point somewhere else: on a hub page,
        # those lead to the real document.
        named = [(u, v, r) for u, v, r in _candidates(html, url, "hub-link")[doc_type]
                 if v.startswith("hub-link") and r <= 1 + (10 if v.endswith("-external") else 0)
                 and not _same_page(u, url)]

        if ok and len(text) >= SUBSTANTIAL_CHARS and not SIDE_TITLE[doc_type].search(text[:SIDE_HEAD_CHARS]):
            log.info("[%s]   got %s chars via %s fetch — looks like a real document",
                     doc_type, f"{len(text):,}", method)
            result.ok, result.text, result.html = True, text, html
            return result
        if ok and SIDE_TITLE[doc_type].search(text[:SIDE_HEAD_CHARS]):
            # Real, but about a side program ("Community Geofilter Terms",
            # "PayPal Balance Terms"): never stored as the site's document.
            reason = "about a side program, not the main document"
        elif ok and named:
            # A short page pointing at a full policy is a summary or a hub
            # (reddit.com/privacy, apple.com/privacy): rating it would be
            # rating the marketing, so it is never stored either.
            reason = f"summary page ({len(text)} chars) that links to the full document"
        elif ok:
            # Short with no pointer elsewhere: maybe a small site's whole
            # policy. Used only if nothing fuller turns up.
            log.info("[%s]   valid but short (%s chars), still looking for a fuller version",
                     doc_type, f"{len(text):,}")
            result.notes.append(f"{via} {url} -> short ({len(text)} chars), kept as fallback")
            if fallback is None:
                fallback = Located(doc_type, True, url, via, method, text, html=html)
            reason = ""
        if reason:
            log.info("[%s]   rejected: %s", doc_type, reason)
            result.notes.append(f"{via} {url} -> {reason}")

        new_links = [n for n in named if n[0] not in tried]
        if new_links:
            log.info("[%s]   page links to %d named document(s), trying those next", doc_type, len(new_links))
            probes = probes[:i] + sorted(new_links + probes[i:], key=lambda p: p[2])

        # Soft 404: the site serves the same page for any path. Once a guessed
        # path repeats earlier content, the remaining guesses will too.
        if text in seen_texts and via == "common-path":
            log.info("[%s]   same page as an earlier probe (soft 404), skipping guessed paths", doc_type)
            result.notes.append("soft 404: guessed paths all return the same page")
            # ...except /legal, a hub that soft-404 sites (spotify) still serve for real
            probes = probes[:i] + [p for p in probes[i:]
                                   if p[1] != "common-path" or p[0].endswith("/legal")]
            continue
        seen_texts.add(text)

        frames, captcha = _iframe_srcs(html, url, domain)
        if captcha:
            log.info("[%s]   captcha wall, stopping", doc_type)
            result.notes.append("blocked: captcha wall")
            break
        for src in frames:  # shell page? follow its iframes
            log.info("[%s]   page embeds an iframe, queueing %s", doc_type, src)
            probes.append((src, "iframe", rank(doc_type, src, "iframe")))
    if fallback is not None:
        log.info("[%s] no fuller document found; using the short one (%s chars)",
                 doc_type, f"{len(fallback.text):,}")
        fallback.notes = result.notes
        return fallback
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

    cands: dict[str, list[tuple[str, str, int]]] = {"privacy": [], "terms": []}
    if html and is_challenge(html):
        log.info("homepage is a bot-challenge page; ignoring its links")
        home_notes.append("homepage static -> blocked: bot challenge")
        html = None
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
        if rendered and is_challenge(rendered):
            log.info("rendered homepage is a bot-challenge page; ignoring its links")
            home_notes.append("homepage render -> blocked: bot challenge")
            rendered = None
        if rendered:
            rcands = _candidates(rendered, homepage)
            # Merge: keep static finds first, add anything the render revealed.
            for dt in ("privacy", "terms"):
                have = {c[0] for c in cands[dt]}
                cands[dt] += [c for c in rcands[dt] if c[0] not in have]
            log.info("rendered homepage links: %d privacy, %d terms",
                     len(cands["privacy"]), len(cands["terms"]))

    # Unreachable host: the homepage failed at the connection level (not an
    # HTTP status) both statically and rendered. Guessed paths on the same
    # host fail the same way, and batch 4 showed them burning the whole time
    # budget (cyberghostvpn.com, hidemyass.com, ok.ru, adobe.com).
    walled = [n for n in home_notes if "bot challenge" in n]
    if walled and not (cands["privacy"] or cands["terms"]) and             (len(walled) == 2 or not use_playwright):
        log.info("blocked by a bot challenge, skipping discovery")
        return {dt: Located(dt, notes=home_notes + ["blocked: bot challenge"])
                for dt in ("privacy", "terms")}

    home_failed_rendered = any(n.startswith("homepage render") for n in home_notes)
    if not html and not home_status.isdigit() and (home_failed_rendered or not use_playwright):
        log.info("host unreachable, skipping discovery")
        return {dt: Located(dt, notes=home_notes + ["host unreachable"])
                for dt in ("privacy", "terms")}

    results = {
        dt: locate_document(domain, dt, cands[dt], session, use_playwright, deadline)
        for dt in ("privacy", "terms")
    }
    # Legal pages link to each other: when one document was found and the
    # other wasn't (twitch: no footer links, terms off the guessed paths),
    # follow the found page's own link to the missing one.
    for dt, other in (("terms", "privacy"), ("privacy", "terms")):
        found = results[other]
        if results[dt].ok or not found.ok or not found.html:
            continue
        siblings = [c for c in _candidates(found.html, found.url, "sibling-link")[dt]
                    if c[1].startswith("sibling-link") and c[2] <= 1 + (10 if c[1].endswith("-external") else 0)]
        if siblings:
            log.info("[%s] trying the %s page's own link(s) to it", dt, other)
            retry = locate_document(domain, dt, siblings, session, use_playwright, deadline,
                                    guess_paths=False)
            if retry.ok:
                results[dt] = retry
            else:
                results[dt].notes += retry.notes
    for loc in results.values():
        if not loc.ok:
            loc.notes[:0] = home_notes  # homepage outcome explains most misses
    return results
