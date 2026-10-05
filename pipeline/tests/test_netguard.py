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
    netguard._host_allowed.cache_clear()
    with pytest.raises(BlockedURL):
        check_url("http://totally-public.example/")
    netguard._host_allowed.cache_clear()


def test_public_host_allowed(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo",
                        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))])
    from imbroglio import netguard
    netguard._host_allowed.cache_clear()
    check_url("https://example.com/privacy")
    netguard._host_allowed.cache_clear()


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
