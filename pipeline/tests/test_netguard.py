"""SSRF guard: every way of pointing the fetcher at an internal address."""

import pytest
import requests

from imbroglio import fetch
from imbroglio.netguard import BlockedURL, check_url, is_allowed


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",   # cloud metadata
    "http://127.0.0.1:8765/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://[::1]/",
    "http://0.0.0.0/",
    "http://localhost/",
    "http://api.localhost/",
    "http://metadata.google.internal/",
    "http://printer.local/",
    "file:///etc/passwd",
    "ftp://example.com/",
    "javascript:alert(1)",
])
def test_blocked(url):
    assert not is_allowed(url)


def test_hostname_resolving_to_loopback_is_blocked(monkeypatch):
    # A public-looking name that resolves to 127.0.0.1 (DNS-based SSRF).
    monkeypatch.setattr("socket.getaddrinfo",
                        lambda host, port: [(2, 1, 6, "", ("127.0.0.1", 0))])
    from imbroglio import netguard
    netguard.clear_host_cache()
    with pytest.raises(BlockedURL):
        check_url("http://totally-public.example/")
    netguard.clear_host_cache()


def test_private_and_unresolvable_hosts_read_the_same(monkeypatch):
    """The refusal reaches the public request log, so it must not name the
    host or say whether the name resolved privately or not at all: that would
    let anyone map internal names from where the worker runs."""
    import socket
    from imbroglio import netguard

    def fake_dns(host, port):
        if host == "intranet.example":
            return [(2, 1, 6, "", ("10.1.2.3", 0))]
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr("socket.getaddrinfo", fake_dns)
    netguard.clear_host_cache()
    try:
        notes = [fetch.fetch_static(f"https://{h}/privacy")
                 for h in ("intranet.example", "no-such-name.example")]
        assert notes[0] == notes[1] == (None, f"blocked: {netguard.NO_PUBLIC_ADDRESS}")
        assert not any(h in str(notes) for h in ("intranet", "no-such-name"))
        assert fetch.fetch_rendered("https://intranet.example/") ==             fetch.fetch_rendered("https://no-such-name.example/")
    finally:
        netguard.clear_host_cache()


def test_a_malformed_host_is_refused_not_crashed_on():
    # usf.edu, Nov 17: one such link raised UnicodeError and ended the site's crawl
    for url in ("https://www..usf.edu/privacy", f"https://{'a' * 64}.usf.edu/"):
        assert not is_allowed(url)
        html, status = fetch.fetch_static(url)
        assert html is None and status.startswith("blocked: not a valid host name")


def test_public_host_allowed(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo",
                        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))])
    from imbroglio import netguard
    netguard.clear_host_cache()
    check_url("https://example.com/privacy")
    netguard.clear_host_cache()


class _FakeResp:
    def __init__(self, status, location=None):
        self.status_code = status
        self.headers = {"location": location} if location else {"content-type": "text/html"}
        self.is_redirect = location is not None
        self.text = "<html></html>"

    def close(self):
        pass


def test_redirect_to_internal_address_is_blocked(monkeypatch):
    """A public page that redirects to the metadata endpoint must not be followed."""
    monkeypatch.setattr("imbroglio.fetch.check_url",
                        lambda url: None if "public.example" in url else check_url(url))
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        assert kwargs["allow_redirects"] is False
        return _FakeResp(302, "http://169.254.169.254/latest/meta-data/")

    sess = requests.Session()
    monkeypatch.setattr(sess, "get", fake_get)
    html, status = fetch.fetch_static("https://public.example/", sess)
    assert html is None
    assert status.startswith("blocked")
    assert calls == ["https://public.example/"]  # never requested the internal URL


def test_browser_cap_returns_busy_instead_of_launching(monkeypatch):
    """With every browser slot taken, fetch_rendered must not start Chromium."""
    import threading
    monkeypatch.setattr(fetch, "_browser_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(fetch, "BROWSER_WAIT", 0.05)
    monkeypatch.setattr(fetch, "is_allowed", lambda url: True)
    assert fetch._browser_slots.acquire(blocking=False)
    try:
        html, status = fetch.fetch_rendered("https://example.com/")
    finally:
        fetch._browser_slots.release()
    assert html is None and status == "playwright:busy"


@pytest.mark.parametrize("url", [
    # urlparse reads example.com, requests connects to 127.0.0.1 (audit, Nov 21)
    "http://127.0.0.1\\@example.com/x",
    "http://169.254.169.254\\@example.com/",
    "http://example.com\\@127.0.0.1/",
    "http://user:pass@example.com/",
    "http://127.0.0.1@example.com/",
    "http://exa\tmple.com/",
    "http://example.com\n.evil/",
    "http://[::ffff:127.0.0.1]/",
])
def test_addresses_two_parsers_could_read_differently_are_refused(url, monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo",
                        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))])
    from imbroglio import netguard
    netguard.clear_host_cache()
    try:
        assert not is_allowed(url)
        html, status = fetch.fetch_static(url)
        assert html is None and status.startswith("blocked")
    finally:
        netguard.clear_host_cache()


@pytest.mark.parametrize("url", [
    "https://example.com/privacy?x=1#top",
    "https://EXAMPLE.com.:443/legal/privacy",
    "https://münchen.de/datenschutz",
    "https://example.com/a@b/terms",
])
def test_ordinary_policy_addresses_still_pass(url, monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo",
                        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))])
    from imbroglio import netguard
    netguard.clear_host_cache()
    try:
        check_url(url)
    finally:
        netguard.clear_host_cache()


def test_a_connection_that_lands_on_a_private_address_is_refused(monkeypatch):
    """DNS rebinding: the name looked public when checked, then the socket
    connected somewhere private. check_peer looks at where it really went."""
    import socket
    import threading

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    served = []

    def serve():
        try:
            conn, _ = srv.accept()
        except OSError:
            return
        served.append(conn.recv(65536))
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 6\r\n\r\nsecret")
        conn.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    monkeypatch.setattr(fetch, "check_url", lambda url: None)  # "resolved public"
    try:
        html, status = fetch.fetch_static(f"http://127.0.0.1:{srv.getsockname()[1]}/privacy")
    finally:
        srv.close()
    assert html is None
    assert status == "blocked: no public address"
    assert not served or not served[0]  # the request itself was never sent


def test_fetches_ignore_proxy_and_netrc_settings():
    sess = fetch._watched(requests.Session())
    assert sess.trust_env is False
