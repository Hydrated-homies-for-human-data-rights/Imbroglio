"""The site's own opt-out and settings pages, harvested from the HTML the
pipeline already fetches: the homepage and each policy page.

A link counts when its text or its path says what it is ("Your Privacy
Choices", "Do Not Sell or Share My Personal Information", "Delete your
account", "/optout"). Each kind maps to the rubric category whose advice it
answers, so the website and the extension can put the site's own page next
to the finding. Nothing is guessed: a site without such a link gets none,
and the clients show no button.

Links must point at the site itself or at one of the consent vendors sites
hand this to (OneTrust, TrustArc and the like); anything else is dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .locate import site_of

# Kinds in priority order: when a site has several links for one category,
# the first kind listed wins. Text patterns match the link's words, path
# patterns its URL path (and fragment).
KINDS: list[tuple[str, str, re.Pattern, re.Pattern | None]] = [
    ("ai_training", "ai_training",
     re.compile(r"\bai\b[^.]{0,30}\b(train|training|model)|\b(train|training)\b[^.]{0,20}\bai\b|"
                r"model training|generative ai|machine learning", re.I),
     re.compile(r"ai[-_]?(training|opt|settings)|training[-_]?opt", re.I)),
    ("privacy_choices", "selling_sharing",
     re.compile(r"do not (sell|share)|don.?t sell|your privacy choices|privacy choices|"
                r"opt[- ]?out of (the )?(sale|sharing)|limit the use of my|sale of (my |your )?personal", re.I),
     re.compile(r"/(opt[-_]?out|do[-_]?not[-_]?sell|privacy[-_]?choices|ccpa|dnsmpi)\b", re.I)),
    ("ad_preferences", "selling_sharing",
     re.compile(r"\bad(s|vertising|vertisement)? ?(preferences|settings|choices|personali[sz]ation|controls)|"
                r"personali[sz]ed ad|interest[- ]based|adchoices", re.I),
     re.compile(r"/(ad[-_]?(preferences|settings|choices)|adchoices)\b", re.I)),
    ("cookie_settings", "collection",
     re.compile(r"cookie (settings|preferences|choices|consent|options|manager)|manage cookies", re.I),
     re.compile(r"/cookie[-_]?(settings|preferences|choices|consent)\b", re.I)),
    ("delete_account", "retention",
     re.compile(r"delet(e|ing) (my |your |an? )?(account|data|information|profile)|"
                r"close (my |your )?account|account deletion|deactivat(e|ing) (my |your )?account", re.I),
     re.compile(r"/(delete[-_]?(account|data)|account[-_]?deletion|close[-_]?account)\b", re.I)),
    ("data_request", "user_rights",
     re.compile(r"download (my |your |a copy of )?(data|information)|(request|access|export) (my |your )?(data|information)|"
                r"data (subject|access) request|privacy request|exercise your (privacy |data )?rights|"
                r"submit a (privacy |data )?request|\bdsar\b|your (privacy |data protection )?rights", re.I),
     re.compile(r"/(dsar|privacy[-_]?request|data[-_]?request|download[-_]?(my[-_]?)?data|your[-_]?data)\b", re.I)),
    ("privacy_settings", "user_rights",
     re.compile(r"privacy (settings|center|centre|dashboard|portal|preferences|controls|hub)|manage (my |your )?privacy", re.I),
     re.compile(r"/privacy[-_]?(settings|center|centre|dashboard|portal|preferences|controls)\b", re.I)),
]

# Where sites send people to exercise choices instead of a page of their own.
VENDOR_SITES = {
    "onetrust.com", "trustarc.com", "truste.com", "securiti.ai", "transcend.io", "osano.com",
    "ketch.com", "cookiebot.com", "privacy-request.com", "datagrail.io", "didomi.io",
    "usercentrics.eu", "aboutads.info", "youradchoices.com", "optout.networkadvertising.org",
    "networkadvertising.org", "youronlinechoices.com", "globalprivacycontrol.org",
}
MAX_TEXT = 90
_SKIP_SCHEMES = ("javascript:", "mailto:", "tel:", "data:")


@dataclass(frozen=True)
class Link:
    kind: str
    category: str
    url: str
    text: str
    source: str  # homepage | privacy | terms


def classify(text: str, url: str) -> tuple[str, str] | None:
    """(kind, category) for a link, or None when it isn't one of ours."""
    path = urlparse(url).path + ("#" + urlparse(url).fragment if urlparse(url).fragment else "")
    for kind, category, by_text, by_path in KINDS:
        if by_text.search(text) or (by_path is not None and by_path.search(path)):
            return kind, category
    return None


def _allowed(url: str, domain: str) -> bool:
    host = urlparse(url).hostname or ""
    site = site_of(host)
    return site == site_of(domain) or site in VENDOR_SITES or host in VENDOR_SITES


def harvest(html: str | None, base_url: str, domain: str, source: str) -> list[Link]:
    """Every opt-out or settings link on one page, deduplicated by URL."""
    if not html:
        return []
    out: list[Link] = []
    seen: set[str] = set()
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(_SKIP_SCHEMES) or href == "#":
            continue
        url = urljoin(base_url, href)
        if not url.startswith(("http://", "https://")) or not _allowed(url, domain):
            continue
        text = " ".join(a.get_text(" ").split())
        label = " ".join((a.get("aria-label") or a.get("title") or "").split())
        words = text if text else label
        if not words or len(words) > MAX_TEXT:
            continue
        found = classify(f"{text} {label}".strip(), url)
        if found is None or url in seen:
            continue
        # A link to a section of the page it sits on is a table of contents
        # entry ("11. Privacy Request Metrics"), not a page of the site's own.
        # The exception is a consent control that opens in place ("Your
        # Privacy Choices" on a OneTrust page).
        if _same_page_anchor(url, base_url) and not (found[0] in _IN_PLACE_KINDS and _CONTROL_TEXT.match(words)):
            continue
        seen.add(url)
        out.append(Link(found[0], found[1], url, words[:MAX_TEXT], source))
    return out


_IN_PLACE_KINDS = {"privacy_choices", "ad_preferences", "cookie_settings"}
# A control's label is short and imperative; a heading asks or numbers itself
# ("What are your cookie choices and controls", "11. Privacy Request Metrics").
_CONTROL_TEXT = re.compile(r"^(?!(what|how|why|when|where|\d))[^.?]{1,32}$", re.I)


def _same_page_anchor(url: str, base_url: str) -> bool:
    u, b = urlparse(url), urlparse(base_url)
    return bool(u.fragment) and (u.scheme, u.netloc, u.path.rstrip("/"), u.query) == \
        (b.scheme, b.netloc, b.path.rstrip("/"), b.query)


_PRIORITY = {kind: i for i, (kind, *_rest) in enumerate(KINDS)}


def best(links: list[Link]) -> list[Link]:
    """One link per category: the highest-priority kind, the site's own page
    before a vendor's, the policy page's link before the homepage's (it tends
    to be the more specific one)."""
    chosen: dict[str, Link] = {}

    def rank(link: Link) -> tuple:
        own = site_of(urlparse(link.url).hostname or "") not in VENDOR_SITES
        return (_PRIORITY[link.kind], 0 if own else 1, 0 if link.source != "homepage" else 1)

    for link in sorted(links, key=rank):
        chosen.setdefault(link.category, link)
    return list(chosen.values())


def dedupe(links: list[Link]) -> list[Link]:
    seen: set[str] = set()
    out = []
    for link in links:
        if link.url not in seen:
            seen.add(link.url)
            out.append(link)
    return out
