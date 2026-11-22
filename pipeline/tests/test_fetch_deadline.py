"""A site that sends one byte every few seconds never trips a socket timeout,
so fetch_static needs its own wall clock. These tests talk to a real local
socket server, because a mocked response can't show where urllib3 blocks."""

import socket
import threading
import time

import pytest

from imbroglio import fetch


class _Dripper:
    """Accepts connections and answers each with `head`, then drips `body`
    one byte per `every` seconds. Stops when the test ends."""

    def __init__(self, head: bytes, body: bytes = b"", every: float = 0.2):
        self.head, self.body, self.every = head, body, every
        self.stop = threading.Event()
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.sock.settimeout(0.2)
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}/privacy"
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            threading.Thread(target=self._answer, args=(conn,), daemon=True).start()

    def _drip(self, conn, data):
        for i in range(len(data)):
            if self.stop.wait(self.every):
                return False
            conn.sendall(data[i:i + 1])
        return True

    def _answer(self, conn):
        try:
            conn.recv(65536)
            if self.every and not self.head.endswith(b"\r\n\r\n"):
                self._drip(conn, self.head)       # slow headers
            else:
                conn.sendall(self.head)
                self._drip(conn, self.body)       # slow body
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self.stop.set()
        self.sock.close()


@pytest.fixture
def local(monkeypatch):
    # the SSRF guard refuses 127.0.0.1; these tests need it
    monkeypatch.setattr(fetch, "check_url", lambda url: None)
    monkeypatch.setattr(fetch, "check_peer", lambda sock: None)
    monkeypatch.setattr(fetch, "MAX_SECONDS", 1.5)
    monkeypatch.setattr(fetch, "BACKOFF", 0.01)
    servers = []
    yield servers
    for s in servers:
        s.close()


def _timed(url):
    started = time.monotonic()
    result = fetch.fetch_static(url)
    return result, time.monotonic() - started


def test_a_body_dripped_a_byte_at_a_time_is_cut_off(local):
    head = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 200\r\n\r\n"
    server = _Dripper(head, b"x" * 200, every=0.1)    # 20 s for the whole body
    local.append(server)
    (html, status), took = _timed(server.url)
    assert html is None and status.startswith("too slow")
    assert took < 3


def test_a_body_with_no_length_is_not_returned_half_read(local):
    # Without Content-Length the end of the body is the end of the connection,
    # so a cut-off socket looks like a finished page. It must not be stored.
    head = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
    server = _Dripper(head, b"<p>" + b"x" * 200, every=0.1)
    local.append(server)
    (html, status), took = _timed(server.url)
    assert html is None and status.startswith("too slow")
    assert took < 3


def test_headers_dripped_a_byte_at_a_time_are_cut_off(local):
    head = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nX-Pad: " + b"a" * 400
    server = _Dripper(head, every=0.1)
    local.append(server)
    (html, status), took = _timed(server.url)
    assert html is None and status.startswith("too slow")
    assert took < 3


def test_a_quick_page_is_read_whole(local):
    body = b"<html><p>privacy</p></html>"
    head = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
            + str(len(body)).encode() + b"\r\n\r\n")
    server = _Dripper(head, body, every=0)
    local.append(server)
    (html, status), _ = _timed(server.url)
    assert (html, status) == (body.decode(), "200")


def test_a_reused_connection_is_watched_too(local):
    # The crawl shares one session, so the second page on a host comes over a
    # kept-alive connection that was opened during the first fetch.
    import requests

    fast = b"<html>ok</html>"
    head = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
            + str(len(fast)).encode() + b"\r\n\r\n")
    state = {"n": 0}
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    url = f"http://127.0.0.1:{sock.getsockname()[1]}/"
    stop = threading.Event()

    def serve():
        conn, _ = sock.accept()
        try:
            conn.recv(65536)
            conn.sendall(head + fast)                # first request: fast
            conn.recv(65536)
            conn.sendall(b"HTTP/1.1 200 OK\r\n")     # second request, same connection: drip
            while not stop.wait(0.1):
                conn.sendall(b"X")
        except OSError:
            pass
        finally:
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    try:
        session = requests.Session()
        assert fetch.fetch_static(url, session) == (fast.decode(), "200")
        started = time.monotonic()
        html, status = fetch.fetch_static(url, session)
        assert html is None and time.monotonic() - started < 3
    finally:
        stop.set()
        sock.close()


def _browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


def test_a_page_script_stuck_in_a_loop_cannot_hold_the_browser(local, monkeypatch):
    """page.content() takes no timeout and waits on the page's main thread,
    which a script spinning forever never gives back."""
    if not _browser_available():
        pytest.skip("Chromium not installed (playwright install chromium)")
    page = b"<html><body><p>hello</p><script>setTimeout(() => { while (true) {} }, 50)</script></body></html>"
    head = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
            + str(len(page)).encode() + b"\r\n\r\n")
    server = _Dripper(head, page, every=0)
    local.append(server)
    monkeypatch.setattr(fetch, "is_allowed", lambda url: True)
    monkeypatch.setattr(fetch, "RENDER_SECONDS", 8.0)
    started = time.monotonic()
    html, status = fetch.fetch_rendered(server.url)
    assert html is None and status.startswith("too slow")
    assert time.monotonic() - started < 25
