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
