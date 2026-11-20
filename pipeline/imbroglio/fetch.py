"""HTTP layer: static fetch with identifying UA, Playwright render fallback.

Ported from Spike A with its hard-won lessons baked in:
  * networkidle never fires on analytics-heavy sites -> domcontentloaded + wait
  * bot managers block a Chrome UA with a non-Chrome suffix -> Playwright uses
    the default browser UA; static keeps the honest identifying UA
  * single attempts flake (observed: canva.com) -> retry with backoff
"""

from __future__ import annotations

import os
import threading
import time
from urllib.parse import urljoin

import requests

from .netguard import NO_PUBLIC_ADDRESS, BlockedURL, check_url, is_allowed

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

# Process-wide cap on simultaneous headless browsers (env MAX_BROWSERS).
MAX_BROWSERS = int(os.environ.get("MAX_BROWSERS", "2"))
BROWSER_WAIT = 60  # seconds to wait for a free browser slot before giving up
_browser_slots = threading.BoundedSemaphore(MAX_BROWSERS)
CHROMIUM_ARGS = [
    "--disable-dev-shm-usage",  # containers ship a tiny /dev/shm; use /tmp instead
    "--disable-gpu",
    "--disable-extensions",
    "--mute-audio",
]
BACKOFF = 3.0  # seconds, doubled per retry
# A page is read in full only up to these limits. requests' timeout bounds
# each wait for the next bytes, not the whole download, so a site that sends
# a byte every few seconds (or gigabytes) would hold a worker thread forever.
# The longest real policy seen is about 1.5 MB of HTML.
MAX_BYTES = 5 * 1024 * 1024
MAX_SECONDS = 30.0


class TooLarge(requests.RequestException):
    """The response went over MAX_BYTES or took longer than MAX_SECONDS."""


def _read_capped(resp: requests.Response) -> str:
    """The body as text, refusing more than MAX_BYTES or MAX_SECONDS."""
    started, size, chunks = time.monotonic(), 0, []
    try:
        for chunk in resp.iter_content(64 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise TooLarge(f"over {MAX_BYTES // (1024 * 1024)} MB")
            if time.monotonic() - started > MAX_SECONDS:
                raise TooLarge(f"took over {MAX_SECONDS:.0f}s")
            chunks.append(chunk)
    finally:
        resp.close()
    body = b"".join(chunks)
    return body.decode(resp.encoding or resp.apparent_encoding or "utf-8", errors="replace")


def _get_checked(sess: requests.Session, url: str) -> requests.Response:
    """GET with redirects followed by hand, so every hop passes the SSRF
    guard (requests' built-in redirect handling would not re-check). The body
    is streamed: read it with _read_capped."""
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url)
        resp = sess.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False, stream=True)
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
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ("html" in ctype or "xml" in ctype):
                try:
                    return _read_capped(resp), "200"
                except TooLarge as exc:
                    return None, f"too large: {exc}"  # permanent; never retry
                except requests.RequestException as exc:
                    last_status = type(exc).__name__  # dropped mid-body: retry
            else:
                resp.close()
                if resp.status_code == 200:
                    return None, f"200 (non-html: {ctype.split(';')[0]})"
                last_status = str(resp.status_code)
                if resp.status_code in (404, 410):
                    return None, last_status  # permanent; retrying is pointless
        if attempt < RETRIES:
            time.sleep(BACKOFF * (2**attempt))
    return None, last_status


def _guard(route) -> None:
    """Route handler for the headless browser. A route handler only sees the
    first URL of a redirect chain (Playwright's documented behavior), so a
    navigation is fetched here without following redirects, and a redirect
    to a non-public address is refused before the browser can follow it."""
    req = route.request
    if not is_allowed(req.url):
        route.abort("blockedbyclient")
        return
    if not req.is_navigation_request():
        route.continue_()
        return
    try:
        resp = route.fetch(max_redirects=0, timeout=TIMEOUT * 1000)
    except Exception:
        route.abort("failed")
        return
    location = resp.headers.get("location")
    if 300 <= resp.status < 400 and location and not is_allowed(urljoin(req.url, location)):
        route.abort("blockedbyclient")
        return
    route.fulfill(response=resp)


def fetch_rendered(url: str) -> tuple[str | None, str]:
    """Headless-Chromium fallback for JS-rendered pages.

    Requires: pip install playwright && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "playwright-not-installed"
    if not is_allowed(url):
        return None, f"blocked: {NO_PUBLIC_ADDRESS}"
    # Each Chromium costs ~150-300 MB. On a 1 GB container, unbounded
    # concurrency (web requests + batch workers) exhausted memory and stalled
    # every connection in the process, including the database's.
    if not _browser_slots.acquire(timeout=BROWSER_WAIT):
        return None, "playwright:busy"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
            try:
                # Default browser UA on purpose — see module docstring. Service
                # workers are blocked: their requests would skip the route below.
                page = browser.new_context(service_workers="block").new_page()
                # SSRF guard for everything the page loads: navigations, iframes,
                # scripts, XHR. A page script fetching an internal endpoint and
                # writing it into the DOM would otherwise leak it into our text.
                page.route("**/*", _guard)
                response = page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
                # Belt and braces: every hop the page actually took, and where
                # it ended up, must be public.
                hops = [page.url]
                req = response.request if response is not None else None
                while req is not None:
                    hops.append(req.url)
                    req = req.redirected_from
                if not all(is_allowed(h) for h in hops):
                    return None, f"blocked: redirected, {NO_PUBLIC_ADDRESS}"
                page.wait_for_timeout(3000)  # hydration settle
                return page.content(), "200 (rendered)"
            finally:
                browser.close()  # also on errors; leaked browsers held memory
    except Exception as exc:
        return None, f"playwright:{type(exc).__name__}"
    finally:
        _browser_slots.release()
