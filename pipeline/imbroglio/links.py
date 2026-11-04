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
from pathlib import Path
from urllib.parse import urljoin, urlparse

import yaml
from bs4 import BeautifulSoup

from .locate import site_of

# Kinds in priority order: when a site has several links for one category,
# the first kind listed wins. Text patterns match the link's words, path
# patterns its URL path (and fragment).
KINDS: list[tuple[str, str, re.Pattern, re.Pattern | None]] = [
    # AI is a product topic on half the web ("AI Gateway", "AI control plane",
    # a course on AI), so an AI-training link needs both: the subject and a
    # word that says it is a choice ("opt out of AI training", "AI data
    # preferences"), or a path that says so outright.
    ("ai_training", "ai_training",
     re.compile(r"(?=.*\b(ai|artificial intelligence|model training|training data|machine learning|llm)\b)"
                r"(?=.*\b(opt[- ]?out|turn off|disable|do not use|don.?t use|manage|preferences?|settings?|choices?|consent)\b)", re.I),
     re.compile(r"ai[-_]?(training[-_]?)?(opt[-_]?out|settings|preferences|choices)|training[-_]?opt[-_]?out", re.I)),
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
     re.compile(r"download (my|your|a copy of (my|your)) (data|information)|"
                r"(request|access|export) (my|your) (personal )?(data|information)|"
                r"data (subject|access) request|privacy request|exercise your (privacy |data )?rights|"
                r"submit a (privacy |data )?request|\bdsar\b|your (privacy|data protection) rights", re.I),
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
        if found is None or url in seen or _NOT_A_PAGE.search(f"{words} {urlparse(url).path}"):
            continue
        # A link into a section of a page ("#infodelete" on the policy, a table
        # of contents entry) is a place to read, not a page of the site's own
        # for doing something. The exception is a consent control on the page
        # itself that opens in place ("Your Privacy Choices" on a OneTrust page).
        if urlparse(url).fragment and not (found[0] in _IN_PLACE_KINDS and _CONTROL_TEXT.match(words)
                                           and _same_page_anchor(url, base_url)):
            continue
        seen.add(url)
        out.append(Link(found[0], found[1], url, words[:MAX_TEXT], source))
    return out


_IN_PLACE_KINDS = {"privacy_choices", "ad_preferences", "cookie_settings"}
# Documents about a topic, not pages for doing something: a CCPA addendum
# for business customers, a supplemental privacy statement, a blog post.
_NOT_A_PAGE = re.compile(r"addendum|agreement|\bdpa\b|supplemental|statement|whitepaper|faq|"
                         r"/(blog|news|press|docs?|help/articles?|learn|courses?|tutorials?|guides?)/", re.I)
# A control's label is short and imperative; a heading asks or numbers itself
# ("What are your cookie choices and controls", "11. Privacy Request Metrics").
_CONTROL_TEXT = re.compile(r"^(?!(what|how|why|when|where|\d))[^.?]{1,32}$", re.I)


def _same_page_anchor(url: str, base_url: str) -> bool:
    u, b = urlparse(url), urlparse(base_url)
    return (u.scheme, u.netloc, u.path.rstrip("/"), u.query) == (b.scheme, b.netloc, b.path.rstrip("/"), b.query)


_PRIORITY = {kind: i for i, (kind, *_rest) in enumerate(KINDS)}
_PRIORITY["known"] = -1  # a page someone on the team checked beats any harvested one


def best(links: list[Link]) -> list[Link]:
    """One link per category: a known page first, then the highest-priority
    kind, the site's own page before a vendor's, the policy page's link
    before the homepage's (it tends to be the more specific one)."""
    chosen: dict[str, Link] = {}

    def rank(link: Link) -> tuple:
        own = site_of(urlparse(link.url).hostname or "") not in VENDOR_SITES
        return (_PRIORITY[link.kind], 0 if own else 1, 0 if link.source != "homepage" else 1)

    for link in sorted(links, key=rank):
        chosen.setdefault(link.category, link)
    return list(chosen.values())


# --- known pages ---------------------------------------------------------------
#
# The sites people use most keep their choices inside account settings,
# where no homepage or policy links to them, so the harvest never sees
# them. known_links.yaml lists those pages by hand, with the date someone
# on the team last confirmed each address. They are served through the
# same `links` field, with kind and source "known", and win over a
# harvested page for the same category.

KNOWN_FILE = Path(__file__).resolve().parent / "known_links.yaml"
_known_cache: dict[str, list[Link]] | None = None


def _load_known() -> dict[str, list[Link]]:
    global _known_cache
    if _known_cache is None:
        raw = yaml.safe_load(KNOWN_FILE.read_text(encoding="utf-8")) or {}
        _known_cache = {
            domain.lower(): [Link("known", e["category"], e["url"], e["text"], "known") for e in entries or []]
            for domain, entries in raw.items()
        }
    return _known_cache


def known(domain: str) -> list[Link]:
    """The hand-listed pages for a domain or the site it belongs to
    ('docs.github.com' gets github.com's)."""
    table = _load_known()
    return list(table.get(domain.lower()) or table.get(site_of(domain)) or [])


def known_domains() -> list[str]:
    return sorted(_load_known())


def dedupe(links: list[Link]) -> list[Link]:
    seen: set[str] = set()
    out = []
    for link in links:
        if link.url not in seen:
            seen.add(link.url)
            out.append(link)
    return out
