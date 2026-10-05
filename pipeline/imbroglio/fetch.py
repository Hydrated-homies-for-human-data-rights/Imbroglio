"""HTTP layer: static fetch with identifying UA, Playwright render fallback.

Ported from Spike A with its hard-won lessons baked in:
  * networkidle never fires on analytics-heavy sites -> domcontentloaded + wait
  * bot managers block a Chrome UA with a non-Chrome suffix -> Playwright uses
    the default browser UA; static keeps the honest identifying UA
  * single attempts flake (observed: canva.com) -> retry with backoff
"""

from __future__ import annotations

import time
from urllib.parse import urljoin

import requests

from .netguard import BlockedURL, check_url, is_allowed

IDENTIFYING_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36 "
    "Imbroglio/0.1 (student research project; policy analysis)"
)
HEADERS = {
    "User-Agent": IDENTIFYING_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 15
RETRIES = 2
MAX_REDIRECTS = 5
BACKOFF = 3.0  # seconds, doubled per retry


def _get_checked(sess: requests.Session, url: str) -> requests.Response:
    """GET with redirects followed by hand, so every hop passes the SSRF
    guard (requests' built-in redirect handling would not re-check)."""
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url)
        resp = sess.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False)
        if resp.is_redirect and resp.headers.get("location"):
            url = urljoin(url, resp.headers["location"])
            resp.close()
            continue
        return resp
    raise requests.TooManyRedirects(f"more than {MAX_REDIRECTS} redirects")


def fetch_static(url: str, session: requests.Session | None = None) -> tuple[str | None, str]:
    """Fetch a URL with retry/backoff. Returns (html, status_note)."""
    sess = session or requests.Session()
    last_status = "unknown"
    for attempt in range(RETRIES + 1):
        try:
            resp = _get_checked(sess, url)
        except BlockedURL as exc:
            return None, f"blocked: {exc}"  # permanent; never retry
        except requests.Timeout as exc:
            # Silent drops are a bot-defense pattern (observed: adobe.com,
            # hidemyass.com); retrying burned ~70s per site in batch 2/3.
            # Return now and let the caller try the headless browser.
            return None, type(exc).__name__
        except requests.RequestException as exc:
            last_status = type(exc).__name__
        else:
            if resp.status_code == 200:
                ctype = resp.headers.get("content-type", "")
                if "html" in ctype or "xml" in ctype:
                    return resp.text, "200"
                return None, f"200 (non-html: {ctype.split(';')[0]})"
            last_status = str(resp.status_code)
            if resp.status_code in (404, 410):
                return None, last_status  # permanent; retrying is pointless
        if attempt < RETRIES:
            time.sleep(BACKOFF * (2**attempt))
    return None, last_status


def fetch_rendered(url: str) -> tuple[str | None, str]:
    """Headless-Chromium fallback for JS-rendered pages.

    Requires: pip install playwright && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "playwright-not-installed"
    if not is_allowed(url):
        return None, "blocked: non-public address"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # Default browser UA on purpose — see module docstring.
            page = browser.new_page()
            # SSRF guard for everything the page loads: navigations, iframes,
            # scripts, XHR. A page script fetching an internal endpoint and
            # writing it into the DOM would otherwise leak it into our text.
            page.route("**/*", lambda route: route.continue_() if is_allowed(route.request.url)
                       else route.abort("blockedbyclient"))
            page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
            page.wait_for_timeout(3000)  # hydration settle
            html = page.content()
            browser.close()
            return html, "200 (rendered)"
    except Exception as exc:
        return None, f"playwright:{type(exc).__name__}"
