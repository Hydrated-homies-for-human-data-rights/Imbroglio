"""HTTP layer: static fetch with identifying UA, Playwright render fallback.

Ported from Spike A with its hard-won lessons baked in:
  * networkidle never fires on analytics-heavy sites -> domcontentloaded + wait
  * bot managers block a Chrome UA with a non-Chrome suffix -> Playwright uses
    the default browser UA; static keeps the honest identifying UA
  * single attempts flake (observed: canva.com) -> retry with backoff
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

from .netguard import NO_PUBLIC_ADDRESS, BlockedURL, check_url, is_allowed

log = logging.getLogger("imbroglio")

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
# Wall clock for one fetch_static call: every redirect hop, retry, header and
# body byte. A slow but honest site finishes well inside it.
MAX_SECONDS = 30.0
# Wall clock for one fetch_rendered call once the browser is up (page load,
# settle time, reading the DOM).
RENDER_SECONDS = 45.0


class TooLarge(requests.RequestException):
    """The response went over MAX_BYTES."""


class TooSlow(requests.RequestException):
    """The fetch ran past MAX_SECONDS."""


_active = threading.local()  # the _Deadline of the fetch running on this thread


def _shutdown(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass  # already closed by the other side


class _Deadline:
    """A hard time limit on one static fetch, headers included. The socket
    timeout only bounds each wait for the next byte, so a server that drips
    one byte every few seconds never trips it, while reading headers or the
    body. When time runs out a timer thread shuts down every socket the fetch
    is using, and the blocked read returns at once."""

    def __init__(self, seconds: float) -> None:
        self.expired = False
        self._socks: list[socket.socket] = []
        self._lock = threading.Lock()
        self._timer = threading.Timer(seconds, self._expire)
        self._timer.daemon = True

    def __enter__(self) -> _Deadline:
        _active.deadline = self
        self._timer.start()
        return self

    def __exit__(self, *exc) -> None:
        self._timer.cancel()
        _active.deadline = None
        with self._lock:  # never close a handle while _expire is shutting it down
            for s in self._socks:
                s.close()
            self._socks = []

    def watch(self, sock: socket.socket) -> None:
        # A duplicate handle of our own: shutdown acts on the connection, not
        # the handle, so this still cuts the read off after TLS has wrapped
        # (and taken over) the original socket.
        try:
            dup = socket.fromfd(sock.fileno(), sock.family, sock.type)
        except (OSError, ValueError):
            return
        with self._lock:
            self._socks.append(dup)
            if self.expired:
                _shutdown(dup)

    def _expire(self) -> None:
        with self._lock:
            self.expired = True
            for s in self._socks:
                _shutdown(s)


def _watch(sock: socket.socket) -> None:
    deadline = getattr(_active, "deadline", None)
    if deadline is not None:
        deadline.watch(sock)


# urllib3 classes that hand every socket a fetch uses to its _Deadline: new
# connections when they connect, kept-alive ones when they are reused.
class _WatchedHTTPConnection(HTTPConnection):
    def _new_conn(self):
        sock = super()._new_conn()
        _watch(sock)
        return sock


class _WatchedHTTPSConnection(HTTPSConnection):
    def _new_conn(self):
        sock = super()._new_conn()
        _watch(sock)
        return sock


class _WatchedHTTPPool(HTTPConnectionPool):
    ConnectionCls = _WatchedHTTPConnection

    def _get_conn(self, timeout=None):
        conn = super()._get_conn(timeout)
        if conn.sock is not None:
            _watch(conn.sock)
        return conn


class _WatchedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _WatchedHTTPSConnection

    def _get_conn(self, timeout=None):
        conn = super()._get_conn(timeout)
        if conn.sock is not None:
            _watch(conn.sock)
        return conn


class _WatchedAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {"http": _WatchedHTTPPool,
                                                   "https": _WatchedHTTPSPool}


def _watched(sess: requests.Session) -> requests.Session:
    """The session, with adapters whose sockets a _Deadline can cut off.
    Callers share one session across a crawl, so this is done once."""
    if not isinstance(sess.get_adapter("https://"), _WatchedAdapter):
        sess.mount("https://", _WatchedAdapter())
        sess.mount("http://", _WatchedAdapter())
    return sess


def _read_capped(resp: requests.Response, deadline: _Deadline | None = None) -> str:
    """The body as text, refusing more than MAX_BYTES or a body still coming
    in when the deadline passed."""
    size, chunks = 0, []
    try:
        for chunk in resp.iter_content(64 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise TooLarge(f"over {MAX_BYTES // (1024 * 1024)} MB")
            if deadline is not None and deadline.expired:
                raise TooSlow(f"took over {MAX_SECONDS:.0f}s")
            chunks.append(chunk)
    finally:
        resp.close()
    # A cut-off socket can read as a normal end of the body; never return half a page.
    if deadline is not None and deadline.expired:
        raise TooSlow(f"took over {MAX_SECONDS:.0f}s")
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
    sess = _watched(session or requests.Session())
    last_status = "unknown"
    too_slow = f"too slow: took over {MAX_SECONDS:.0f}s"  # permanent; never retry
    with _Deadline(MAX_SECONDS) as deadline:
        for attempt in range(RETRIES + 1):
            try:
                resp = _get_checked(sess, url)
            except BlockedURL as exc:
                return None, f"blocked: {exc}"  # permanent; never retry
            except requests.Timeout as exc:
                if deadline.expired:
                    return None, too_slow
                # Silent drops are a bot-defense pattern (observed: adobe.com,
                # hidemyass.com); retrying burned ~70s per site in batch 2/3.
                # Return now and let the caller try the headless browser.
                return None, type(exc).__name__
            except (requests.RequestException, OSError) as exc:
                if deadline.expired:
                    return None, too_slow
                last_status = type(exc).__name__
            else:
                if deadline.expired:
                    # Cut off mid-headers, http.client can hand back what it
                    # had as a short "200" with no headers (seen on Linux).
                    resp.close()
                    return None, too_slow
                ctype = resp.headers.get("content-type", "")
                if resp.status_code == 200 and ("html" in ctype or "xml" in ctype):
                    try:
                        return _read_capped(resp, deadline), "200"
                    except TooLarge as exc:
                        return None, f"too large: {exc}"  # permanent; never retry
                    except TooSlow:
                        return None, too_slow
                    except (requests.RequestException, OSError) as exc:
                        if deadline.expired:
                            return None, too_slow
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
                if deadline.expired:
                    break
    return None, too_slow if deadline.expired else last_status


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


class _RenderWatchdog:
    """Closes the browser when a render runs past its time. A page script
    stuck in a loop blocks page.content() and page.evaluate() forever (they
    take no timeout), and Playwright's sync API may only be called from the
    thread that owns it. While a sync call waits, Playwright runs an asyncio
    loop underneath; closing the browser through that loop (the thread-safe
    way in) makes the stuck call raise. This reaches into two private
    attributes, _loop and _impl_obj; test_fetch_deadline covers it."""

    def __init__(self, browser, seconds: float) -> None:
        self.fired = False
        self._browser = browser
        self._timer = threading.Timer(seconds, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def cancel(self) -> None:
        self._timer.cancel()

    def _fire(self) -> None:
        self.fired = True
        try:
            loop, impl = self._browser._loop, self._browser._impl_obj

            def close() -> None:
                task = loop.create_task(impl.close())
                task.add_done_callback(lambda t: t.cancelled() or t.exception())

            loop.call_soon_threadsafe(close)
        except Exception:
            log.exception("could not stop a render that ran past %ss", RENDER_SECONDS)


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
    watchdog = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
            watchdog = _RenderWatchdog(browser, RENDER_SECONDS)
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
                # Measured inside the browser first, so a script that built a
                # huge DOM never gets it copied into this process.
                size = page.evaluate("() => document.documentElement ? document.documentElement.outerHTML.length : 0")
                if size > MAX_BYTES:
                    return None, f"too large: rendered page over {MAX_BYTES // (1024 * 1024)} MB"
                html = page.content()
                if len(html) > MAX_BYTES:  # grew between the two reads
                    return None, f"too large: rendered page over {MAX_BYTES // (1024 * 1024)} MB"
                return html, "200 (rendered)"
            finally:
                watchdog.cancel()
                browser.close()  # also on errors; leaked browsers held memory
    except Exception as exc:
        if watchdog is not None and watchdog.fired:
            return None, f"too slow: took over {RENDER_SECONDS:.0f}s"
        return None, f"playwright:{type(exc).__name__}"
    finally:
        _browser_slots.release()
