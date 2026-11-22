"""Which address the per-client rate limit counts. Callers can type any
header they like, so only the platform's header and our own website (with
its key) are believed."""

import pytest
from starlette.requests import Request

from imbroglio import api


def _request(headers: dict[str, str], peer: str = "10.0.0.5") -> Request:
    return Request({
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 40000),
    })


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.setattr(api, "CLIENT_IP_HEADER", "")
    monkeypatch.setattr(api, "WEB_CLIENT_KEY", "")


def test_forwarded_for_is_ignored_by_default():
    assert api.client_address(_request({"X-Forwarded-For": "1.2.3.4"})) == "10.0.0.5"


def test_platform_header_is_used_when_configured(monkeypatch):
    monkeypatch.setattr(api, "CLIENT_IP_HEADER", "x-real-ip")
    assert api.client_address(_request({"X-Real-IP": "8.8.8.8"})) == "8.8.8.8"
    # a header we weren't told to trust still counts for nothing
    assert api.client_address(_request({"X-Forwarded-For": "1.2.3.4"})) == "10.0.0.5"


def test_platform_list_header_uses_the_entry_the_platform_added(monkeypatch):
    monkeypatch.setattr(api, "CLIENT_IP_HEADER", "x-forwarded-for")
    faked = _request({"X-Forwarded-For": "1.2.3.4, 9.9.9.9"})
    assert api.client_address(faked) == "9.9.9.9"


def test_website_can_pass_on_its_visitor_with_the_key(monkeypatch):
    monkeypatch.setattr(api, "WEB_CLIENT_KEY", "k" * 32)
    ok = _request({"X-Imbroglio-Web-Key": "k" * 32, "X-Imbroglio-Visitor-IP": "5.6.7.8"})
    assert api.client_address(ok) == "visitor 5.6.7.8"


def test_visitor_header_without_the_right_key_is_ignored(monkeypatch):
    monkeypatch.setattr(api, "WEB_CLIENT_KEY", "k" * 32)
    wrong = _request({"X-Imbroglio-Web-Key": "guess", "X-Imbroglio-Visitor-IP": "5.6.7.8"})
    assert api.client_address(wrong) == "10.0.0.5"
    missing = _request({"X-Imbroglio-Visitor-IP": "5.6.7.8"})
    assert api.client_address(missing) == "10.0.0.5"


def test_visitor_header_is_ignored_when_no_key_is_set():
    r = _request({"X-Imbroglio-Web-Key": "", "X-Imbroglio-Visitor-IP": "5.6.7.8"})
    assert api.client_address(r) == "10.0.0.5"


@pytest.mark.parametrize("given, counted", [
    ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
    ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),  # same /64, same limit
    ("::ffff:8.8.8.8", "8.8.8.8"),
    ("8.8.8.8", "8.8.8.8"),
])
def test_an_ipv6_visitor_counts_as_its_slash_64(monkeypatch, given, counted):
    # One home or phone gets a whole /64; counting single addresses would let
    # anyone rotate past the limits.
    monkeypatch.setattr(api, "CLIENT_IP_HEADER", "x-real-ip")
    assert api.client_address(_request({"X-Real-IP": given})) == counted
    monkeypatch.setattr(api, "WEB_CLIENT_KEY", "k" * 32)
    via_site = _request({"X-Imbroglio-Web-Key": "k" * 32, "X-Imbroglio-Visitor-IP": given})
    assert api.client_address(via_site) == "visitor " + counted


@pytest.mark.parametrize("given, counted", [
    ("2001:db8:1:2:aaaa::1", "2001:db8:1::/48"),
    ("2001:db8:1:ffff::1", "2001:db8:1::/48"),      # another /64 in the same /48
    ("::ffff:8.8.8.8", "8.8.8.8"),
    ("8.8.8.8", "8.8.8.8"),                          # IPv4 stays per address
])
def test_the_daily_limit_counts_an_ipv6_visitor_by_its_slash_48(monkeypatch, given, counted):
    # One customer often holds a /48, which is 65,536 /64s: enough to use up
    # the whole day's cap one /64 at a time.
    monkeypatch.setattr(api, "CLIENT_IP_HEADER", "x-real-ip")
    r = _request({"X-Real-IP": given})
    assert api.client_address(r, api.DAILY_IPV6_PREFIX) == counted
    monkeypatch.setattr(api, "WEB_CLIENT_KEY", "k" * 32)
    via_site = _request({"X-Imbroglio-Web-Key": "k" * 32, "X-Imbroglio-Visitor-IP": given})
    assert api.client_address(via_site, api.DAILY_IPV6_PREFIX) == "visitor " + counted


def test_rotating_slash_64s_in_one_slash_48_shares_the_daily_limit(monkeypatch):
    monkeypatch.setattr(api, "CLIENT_IP_HEADER", "x-real-ip")
    day = api._RateLimiter(2, window=86400)
    keys = [api.client_address(_request({"X-Real-IP": f"2001:db8:7:{n:x}::1"}), api.DAILY_IPV6_PREFIX)
            for n in range(3)]
    assert [day.allow(k) for k in keys] == [True, True, False]
    # the hourly limit still tells those /64s apart
    assert len({api.client_address(_request({"X-Real-IP": f"2001:db8:7:{n:x}::1"})) for n in range(3)}) == 3


def test_the_daily_limit_holds_past_the_hourly_window():
    day = api._RateLimiter(2, window=86400)
    assert day.allow("a") and day.allow("a") and not day.allow("a")
    assert day.allow("b")
