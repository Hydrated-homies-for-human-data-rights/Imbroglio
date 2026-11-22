"""The crawler fetches pages chosen by whoever requests a site, so a page
must not be able to hold a worker forever or fill its memory, and the
headless browser must not follow a redirect to a private address."""

import requests

from imbroglio import api, fetch


class _Body:
    """A streamed response: `chunks` come out of iter_content one by one."""

    def __init__(self, chunks, status=200, ctype="text/html; charset=utf-8"):
        self.chunks, self.status_code = chunks, status
        self.headers = {"content-type": ctype}
        self.encoding, self.apparent_encoding = "utf-8", "utf-8"
        self.is_redirect, self.closed = False, False

    def iter_content(self, size):
        yield from self.chunks

    def close(self):
        self.closed = True


def _serve(monkeypatch, body):
    monkeypatch.setattr(fetch, "_get_checked", lambda sess, url: body)


def test_a_normal_page_is_read_whole(monkeypatch):
    body = _Body([b"<html>", b"<p>privacy</p>", b"</html>"])
    _serve(monkeypatch, body)
    assert fetch.fetch_static("https://site.example/") == ("<html><p>privacy</p></html>", "200")
    assert body.closed


def test_a_huge_page_is_refused_not_read_into_memory(monkeypatch):
    chunk = b"x" * (1024 * 1024)
    body = _Body(chunk for _ in range(100))   # 100 MB, if anyone read it all
    _serve(monkeypatch, body)
    html, status = fetch.fetch_static("https://site.example/")
    assert html is None and status.startswith("too large")
    assert body.closed


# A page that drips bytes is covered against a real socket in test_fetch_deadline.


def test_a_non_html_answer_is_closed_without_reading(monkeypatch):
    body = _Body([b"%PDF"], ctype="application/pdf")
    _serve(monkeypatch, body)
    assert fetch.fetch_static("https://site.example/") == (None, "200 (non-html: application/pdf)")
    assert body.closed


class _Route:
    def __init__(self, url, *, navigation=True, status=200, location=None):
        self.request = type("R", (), {"url": url, "is_navigation_request": lambda self: navigation})()
        self._resp = type("F", (), {"status": status, "headers": {"location": location} if location else {}})()
        self.outcome = None

    def fetch(self, **kw):
        assert kw.get("max_redirects") == 0
        return self._resp

    def abort(self, why="failed"):
        self.outcome = "abort"

    def continue_(self):
        self.outcome = "continue"

    def fulfill(self, response):
        self.outcome = "fulfill"


def test_the_browser_refuses_a_redirect_to_a_private_address(monkeypatch):
    monkeypatch.setattr(fetch, "is_allowed", lambda url: "169.254" not in url and "internal" not in url)
    hop = _Route("https://evil.example/privacy", status=302, location="http://169.254.169.254/latest/")
    fetch._guard(hop)
    assert hop.outcome == "abort"
    ok = _Route("https://site.example/privacy", status=301, location="/legal/privacy")
    fetch._guard(ok)
    assert ok.outcome == "fulfill"
    direct = _Route("http://api.internal/", navigation=False)
    fetch._guard(direct)
    assert direct.outcome == "abort"
    script = _Route("https://cdn.example/app.js", navigation=False)
    fetch._guard(script)
    assert script.outcome == "continue"


def test_a_report_page_link_to_another_site_is_dropped():
    assert api._site_page("//evil.example/x") is None
    assert api._site_page("/\\evil.example") is None
    assert api._site_page("/site/notion.so") == "/site/notion.so"
    assert api._site_page("https://imbroglio.io/site/notion.so") == "https://imbroglio.io/site/notion.so"


def test_requests_raise_too_large_as_a_request_error():
    # fetch_static treats it as permanent; other callers see an ordinary RequestException
    assert issubclass(fetch.TooLarge, requests.RequestException)


def _text(monkeypatch, raw: bytes, ctype: str) -> str:
    _serve(monkeypatch, _Body([raw], ctype=ctype))
    html, status = fetch.fetch_static("https://site.example/")
    assert status == "200"
    return html


def test_utf8_sent_without_a_charset_is_not_read_as_latin1(monkeypatch):
    # bereal.com and two dozen others: "text/html" with no charset, UTF-8 body
    raw = "<p>We don’t sell your data — café</p>".encode("utf-8")
    assert _text(monkeypatch, raw, "text/html") == raw.decode("utf-8")


def test_a_latin1_label_on_utf8_bytes_is_not_believed(monkeypatch):
    raw = "<p>don’t</p>".encode("utf-8")
    assert _text(monkeypatch, raw, "text/html; charset=ISO-8859-1") == "<p>don’t</p>"


def test_real_windows_1252_still_decodes(monkeypatch):
    raw = "<p>don’t café</p>".encode("cp1252")
    assert _text(monkeypatch, raw, "text/html; charset=windows-1252") == "<p>don’t café</p>"


def test_a_charset_named_in_the_page_counts(monkeypatch):
    body = "<p>個人情報</p>"
    raw = b'<html><head><meta charset="shift_jis"></head>' + body.encode("shift_jis")
    assert _text(monkeypatch, raw, "text/html").endswith(body)
