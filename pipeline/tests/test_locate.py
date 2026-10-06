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


@pytest.mark.parametrize("host,site", [
    ("policies.google.com", "google.com"),
    ("www.bbc.co.uk", "bbc.co.uk"),
    ("notion.so", "notion.so"),
])
def test_site_of(host, site):
    assert locate.site_of(host) == site
