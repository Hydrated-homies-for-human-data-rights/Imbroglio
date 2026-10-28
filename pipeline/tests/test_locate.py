"""Discovery rules, with fake pages (no network).

Regressions from production data: 11 sites stored Cloudflare's privacy policy
(their homepage was a Cloudflare challenge page) and two stored Google's
(they followed a reCAPTCHA footer link)."""

import pytest

from imbroglio import locate

POLICY = ("Privacy Policy. We collect personal data such as your IP address. "
          "We share information with third parties and use cookies. ") * 30
CHALLENGE = ('<html><head><title>Just a moment...</title></head><body>'
             '<script src="/cdn-cgi/challenge-platform/h/b/orchestrate"></script>'
             '<a href="https://www.cloudflare.com/privacypolicy/">Privacy</a></body></html>')


def page(body: str) -> str:
    return f"<html><body><main>{body}</main></body></html>"


@pytest.fixture
def web(monkeypatch):
    """Map URL -> HTML; anything else 404s. Records every URL fetched."""
    pages: dict[str, str] = {}
    fetched: list[str] = []

    def fake_static(url, session=None):
        fetched.append(url)
        html = pages.get(url.rstrip("/"))
        return (html, "200") if html is not None else (None, "404")

    monkeypatch.setattr(locate, "fetch_static", fake_static)
    monkeypatch.setattr(locate, "fetch_rendered", lambda url: (None, "playwright:off"))
    return pages, fetched


def test_challenge_homepage_is_blocked_and_its_links_ignored(web):
    pages, fetched = web
    pages["https://kickstarter.com"] = CHALLENGE
    pages["https://www.cloudflare.com/privacypolicy"] = page(POLICY)  # must never be used
    result = locate.locate_all("kickstarter.com", use_playwright=False)
    assert not result["privacy"].ok
    assert "bot challenge" in " ".join(result["privacy"].notes)
    assert not any("cloudflare.com" in u for u in fetched)


def test_external_vendor_policy_rejected_and_own_page_used(web):
    pages, _ = web
    # reCAPTCHA footer link appears before the site's own link
    pages["https://sololearn.com"] = page(
        '<a href="https://policies.google.com/privacy">Privacy Policy</a>'
        '<a href="/legal/privacy">Privacy</a>')
    pages["https://policies.google.com/privacy"] = page("Google " + POLICY)
    pages["https://sololearn.com/legal/privacy"] = page("Sololearn " + POLICY)
    result = locate.locate_all("sololearn.com", use_playwright=False)
    assert result["privacy"].ok
    assert result["privacy"].url == "https://sololearn.com/legal/privacy"


def test_external_policy_without_site_name_is_not_accepted(web):
    pages, _ = web
    pages["https://wishlist.com"] = page('<a href="https://policies.google.com/privacy">Privacy Policy</a>')
    pages["https://policies.google.com/privacy"] = page("Google " + POLICY)
    result = locate.locate_all("wishlist.com", use_playwright=False)
    assert not result["privacy"].ok
    assert "another site's document" in " ".join(result["privacy"].notes)


def test_external_policy_that_names_the_site_is_accepted(web):
    pages, _ = web
    pages["https://youtube.com"] = page('<a href="https://policies.google.com/privacy">Privacy</a>')
    pages["https://policies.google.com/privacy"] = page("Google and YouTube " + POLICY)
    result = locate.locate_all("youtube.com", use_playwright=False)
    assert result["privacy"].ok
    assert result["privacy"].discovered_via == "link-text-external"


def test_links_on_another_sites_page_are_still_external(web):
    # keepassxc.org: "Privacy" -> GitHub's policy was rejected (it never names
    # KeePassXC), but GitHub's own links from that page were then taken as
    # same-site, and GitHub's privacy policy and terms were stored for it.
    pages, fetched = web
    pages["https://keepassxc.org"] = page(
        '<a href="https://docs.github.com/site-policy">Privacy</a>'
        '<a href="/about">About</a>')
    pages["https://docs.github.com/site-policy"] = page(
        "GitHub site policy. " + POLICY
        + '<a href="https://docs.github.com/privacy-statement">GitHub General Privacy Statement</a>'
        + '<a href="https://docs.github.com/terms">Terms of Service</a>')
    pages["https://docs.github.com/privacy-statement"] = page("GitHub " + LONG_POLICY)
    pages["https://docs.github.com/terms"] = page("GitHub " + TERMS)
    result = locate.locate_all("keepassxc.org", use_playwright=False)
    assert not result["privacy"].ok and not result["terms"].ok
    assert "another site's document" in " ".join(result["privacy"].notes)


def test_another_sites_document_reached_through_a_sibling_link_is_checked(web):
    # A parent company's privacy policy that names the site is fine, but its
    # link to the parent's own terms doesn't make those the site's terms.
    pages, _ = web
    pages["https://brand.test"] = page('<a href="https://parent.test/privacy">Privacy Policy</a>')
    pages["https://parent.test/privacy"] = page(
        "Parent Co. and Brand " + LONG_POLICY + '<a href="/terms">Terms of Service</a>')
    pages["https://parent.test/terms"] = page("Parent Co. website " + TERMS)
    result = locate.locate_all("brand.test", use_playwright=False)
    assert result["privacy"].ok and result["privacy"].discovered_via == "link-text-external"
    assert not result["terms"].ok


def test_a_spaced_out_name_still_names_the_site():
    assert locate.names_site("powerapps.com", "Microsoft Power Apps privacy statement")
    assert locate.names_site("leagueoflegends.com", "Riot Games runs League of Legends")
    assert not locate.names_site("keepassxc.org", "GitHub General Privacy Statement")


# --- picking the right page (regressions: 11 of 44 rated sites, Oct 2026) ---

LONG_POLICY = POLICY * 3      # over SUBSTANTIAL_CHARS: a full document
TERMS = ("Terms of Service. By using the service you agree to these terms. Our liability is "
         "limited. We may terminate accounts. Governing law applies. ") * 60


def test_privacy_and_terms_link_to_terms_page_is_not_the_privacy_policy(web):
    # dropbox: footer "Privacy & terms" -> /terms was stored as the privacy policy
    pages, _ = web
    pages["https://dropbox.com"] = page('<a href="/terms">Privacy &amp; terms</a>')
    pages["https://dropbox.com/terms"] = page(TERMS + POLICY)
    pages["https://dropbox.com/privacy"] = page(LONG_POLICY)
    result = locate.locate_all("dropbox.com", use_playwright=False)
    assert result["privacy"].url == "https://dropbox.com/privacy"
    assert result["terms"].url == "https://dropbox.com/terms"


def test_short_privacy_hub_is_followed_to_the_full_policy(web):
    # reddit.com/privacy, apple.com/privacy: a short page that passes validation
    pages, _ = web
    pages["https://reddit.com"] = page('<a href="/privacy">Privacy</a>')
    pages["https://reddit.com/privacy"] = page(
        POLICY + '<a href="/policies/privacy-policy">Read our Privacy Policy</a>')
    pages["https://reddit.com/policies/privacy-policy"] = page(LONG_POLICY)
    result = locate.locate_all("reddit.com", use_playwright=False)
    assert result["privacy"].url == "https://reddit.com/policies/privacy-policy"
    assert result["privacy"].discovered_via == "hub-link"


def test_too_short_hub_is_followed_too(web):
    # airbnb, tumblr: the hub is a list of links, too short to validate at all
    pages, _ = web
    pages["https://tumblr.com"] = page('<a href="/policy/privacy">Privacy</a>')
    pages["https://tumblr.com/policy/privacy"] = page(
        'Choose your language: <a href="/privacy/en">Main Privacy Policy (English)</a> '
        '<a href="/privacy/de">Deutsch European Privacy Policy</a>')
    pages["https://tumblr.com/privacy/en"] = page(LONG_POLICY)
    pages["https://tumblr.com/privacy/de"] = page("Datenschutz " + LONG_POLICY)
    result = locate.locate_all("tumblr.com", use_playwright=False)
    assert result["privacy"].url == "https://tumblr.com/privacy/en"


def test_a_genuinely_short_policy_is_still_used(web):
    pages, _ = web
    pages["https://tiny.dev"] = page('<a href="/privacy">Privacy Policy</a>')
    pages["https://tiny.dev/privacy"] = page(POLICY)
    result = locate.locate_all("tiny.dev", use_playwright=False)
    assert result["privacy"].ok
    assert result["privacy"].url == "https://tiny.dev/privacy"


def test_settings_pages_side_terms_and_articles_rank_below_the_real_document(web):
    pages, _ = web
    pages["https://snap.test"] = page(
        '<a href="/blog/why-privacy">Privacy matters</a>'
        '<a href="/choices">Your Privacy Choices</a>'
        '<a href="/geofilter-terms">Community Geofilter Terms</a>'
        '<a href="/legal/privacy-policy">Privacy Policy</a>'
        '<a href="/legal/terms">Terms of Service</a>')
    for path in ("/blog/why-privacy", "/choices"):
        pages[f"https://snap.test{path}"] = page(LONG_POLICY)
    pages["https://snap.test/geofilter-terms"] = page(TERMS)
    pages["https://snap.test/legal/privacy-policy"] = page(LONG_POLICY)
    pages["https://snap.test/legal/terms"] = page(TERMS)
    result = locate.locate_all("snap.test", use_playwright=False)
    assert result["privacy"].url == "https://snap.test/legal/privacy-policy"
    assert result["terms"].url == "https://snap.test/legal/terms"


def test_summary_page_is_not_stored_when_the_full_policy_is_unreachable(web):
    # reddit: the full policy URL is blocked; the marketing summary must not be rated
    pages, _ = web
    pages["https://reddit.com"] = page('<a href="/privacy">Privacy</a>')
    pages["https://reddit.com/privacy"] = page(
        POLICY + '<a href="https://www.reddit.com/policies/privacy-policy?__hstc=1&utm_source=x">'
        'Read the full Privacy Policy</a>'
        '<a href="https://www.reddit.com/policies/privacy-policy?__hstc=2">Privacy Policy</a>')
    result = locate.locate_all("reddit.com", use_playwright=False)
    assert not result["privacy"].ok
    notes = " ".join(result["privacy"].notes)
    assert "summary page" in notes
    assert notes.count("policies/privacy-policy ->") == 1    # tracking params stripped: one probe


def test_side_program_document_is_never_stored_but_its_links_are_followed(web):
    # snapchat's Geofilter terms, paypal's Balance terms: long, valid, wrong
    pages, _ = web
    pages["https://pay.test"] = page('<a href="/balance-terms">PayPal Balance Terms and Conditions</a>')
    pages["https://pay.test/balance-terms"] = page(
        "PayPal Balance Terms and Conditions. " + TERMS + '<a href="/user-agreement">User Agreement</a>')
    pages["https://pay.test/user-agreement"] = page("User Agreement. " + TERMS)
    result = locate.locate_all("pay.test", use_playwright=False)
    assert result["terms"].url == "https://pay.test/user-agreement"

    pages["https://geo.test"] = page('<a href="/geofilter">Terms</a>')
    pages["https://geo.test/geofilter"] = page("Community Geofilter Terms. " + TERMS)
    assert not locate.locate_all("geo.test", use_playwright=False)["terms"].ok


def test_missing_document_found_through_the_other_documents_links(web):
    # twitch: no footer links, terms not on any guessed path, but the privacy
    # policy links to it
    pages, _ = web
    pages["https://tw.test"] = page("welcome")
    pages["https://tw.test/privacy"] = page(LONG_POLICY + '<a href="/p/legal/tos">Terms of Service</a>')
    pages["https://tw.test/p/legal/tos"] = page(TERMS)
    result = locate.locate_all("tw.test", use_playwright=False)
    assert result["terms"].url == "https://tw.test/p/legal/tos"
    assert result["terms"].discovered_via == "sibling-link"


def test_legal_hub_survives_soft_404(web):
    # spotify: /terms and /terms-of-service serve the same stub; /legal is the real terms
    pages, _ = web
    pages["https://sp.test"] = page("welcome")
    stub = page("Spotify. Some stub page with an agreement mention. " * 40)
    pages["https://sp.test/terms"] = stub
    pages["https://sp.test/terms-of-service"] = stub
    pages["https://sp.test/legal"] = page(TERMS)
    assert locate.locate_all("sp.test", use_playwright=False)["terms"].url == "https://sp.test/legal"


def test_strip_tracking_keeps_real_parameters():
    assert (locate._strip_tracking("https://x.com/p?locale.x=en_US&utm_source=a&__hstc=1")
            == "https://x.com/p?locale.x=en_US")
    assert locate._strip_tracking("https://x.com/p") == "https://x.com/p"


@pytest.mark.parametrize("doc_type,url,via,text,expected", [
    ("privacy", "https://x.com/help/article/3175", "link-text", "Privacy Policy", 0),  # airbnb
    ("privacy", "https://x.com/privacy", "link-text", "Privacy Policy", 0),
    ("privacy", "https://x.com/privacy", "link-text", "Privacy", 2),
    ("privacy", "https://x.com/privacy", "common-path", "", 5),
    ("privacy", "https://x.com/terms", "link-text", "Privacy & terms", 7),
    ("privacy", "https://x.com/opt-out", "link-text", "Your Privacy Choices", 5),
    ("privacy", "https://x.com/blog/privacy", "link-text", "Privacy", 8),
    ("terms", "https://x.com/rewards-terms", "link-text", "Rewards Program Terms", 5),
    ("privacy", "https://other.com/privacy", "link-text-external", "Privacy Policy", 10),
])
def test_rank(doc_type, url, via, text, expected):
    assert locate.rank(doc_type, url, via, text) == expected


@pytest.mark.parametrize("host,site", [
    ("policies.google.com", "google.com"),
    ("www.bbc.co.uk", "bbc.co.uk"),
    ("notion.so", "notion.so"),
])
def test_site_of(host, site):
    assert locate.site_of(host) == site
