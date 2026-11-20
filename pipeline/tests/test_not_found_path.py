"""What happens when we can't find or can't rate a site: the reason we give,
the www fallback, and a policy link a visitor pastes in. Fake pages, no
network. The API tests at the bottom need local Postgres."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import db, failure, jobs, locate, search
from imbroglio.api import POLICY_LINK_ERROR, router
from imbroglio.normalize import content_hash

POLICY = ("Privacy Policy. We collect personal data such as your IP address. "
          "We share information with third parties and use cookies. ") * 30
TERMS = ("Terms of Service. By using the site you agree to these terms. Our liability is limited. "
         "We may terminate your account. See also our Privacy Policy, which covers cookies "
         "and third parties and your personal data. ") * 30


def page(body: str) -> str:
    return f"<html><body><main>{body}</main></body></html>"


@pytest.fixture
def web(monkeypatch):
    """URL -> HTML, or URL -> (None, status) for a failure. Anything else 404s."""
    pages: dict = {}
    fetched: list[str] = []

    def fake_static(url, session=None):
        fetched.append(url)
        hit = pages.get(url.rstrip("/"))
        if hit is None:
            return None, "404"
        if isinstance(hit, tuple):
            return hit
        return hit, "200"

    monkeypatch.setattr(locate, "fetch_static", fake_static)
    monkeypatch.setattr(locate, "fetch_rendered", lambda url: (None, "playwright:off"))
    return pages, fetched


def _notes(result):
    return [n for loc in result.values() for n in loc.notes]


# --- the reason we give ---------------------------------------------------------

@pytest.mark.parametrize("notes, reason", [
    (["homepage static -> ConnectionError", "www homepage static -> ConnectionError", "host unreachable"],
     "unreachable"),
    (["homepage static -> blocked: no public address", "host unreachable"], "unreachable"),
    (["homepage static -> blocked: bot challenge", "blocked: bot challenge"], "blocked"),
    (["homepage static -> 403", "common-path https://x.com/privacy -> 403"], "blocked"),
    (["common-path https://x.com/privacy -> 403", "common-path https://x.com/terms -> 403",
      "common-path https://x.com/legal -> 404"], "blocked"),
    (["blocked: captcha wall"], "blocked"),
    (["link-text https://x.com/privacy.pdf -> 200 (non-html: application/pdf)",
      "common-path https://x.com/privacy -> 404"], "pdf_only"),
    (["common-path https://x.com/privacy -> 404", "time budget exceeded"], "timed_out"),
    (["common-path https://x.com/privacy -> 404", "common-path https://x.com/terms -> 404",
      "href https://x.com/about -> no privacy signals (2000 chars, 1 hit)"], "no_policy"),
    ([], "no_policy"),
])
def test_reason_from_the_crawl_notes(notes, reason):
    assert failure.classify(notes) == reason


def test_one_blocked_link_among_many_misses_is_not_a_blocked_site():
    notes = ["link-text https://x.com/a -> 403"] + [f"common-path https://x.com/p{i} -> 404" for i in range(5)]
    assert failure.classify(notes) == "no_policy"


def test_stored_notes_are_split_and_tried_reads_plainly():
    stored = ("homepage static -> 403; common-path https://x.com/privacy -> 404; "
              "common-path https://x.com/privacy -> 404; "
              "link-text https://x.com/p.pdf -> 200 (non-html: application/pdf)")
    tried = failure.tried(stored, "x.com")
    assert tried == ["https://x.com (home page): the site turned us away",
                     "https://x.com/privacy: page not found",
                     "https://x.com/p.pdf: a PDF, which we can't read yet"]


def test_tried_never_names_why_a_host_was_refused():
    # netguard: a private address and a missing name read the same
    lines = failure.tried(["homepage static -> blocked: no public address"], "intranet.example")
    assert lines == ["https://intranet.example (home page): couldn't connect"]


def test_request_failure():
    assert failure.for_request("running", None, "x.com") is None
    assert failure.for_request("failed", None, "x.com")["reason"] == "error"
    found = {"documents": [{"doc_type": "privacy", "found": True, "notes": ""},
                           {"doc_type": "terms", "found": False, "notes": "host unreachable"}]}
    assert failure.for_request("done", found, "x.com") is None
    none = {"documents": [{"doc_type": "privacy", "found": False, "notes": "blocked: bot challenge"},
                          {"doc_type": "terms", "found": False, "notes": "blocked: bot challenge"}]}
    out = failure.for_request("done", none, "x.com")
    assert out["reason"] == "blocked" and out["message"] == failure.MESSAGES["blocked"]


# --- www fallback ---------------------------------------------------------------

def test_www_is_tried_when_the_bare_domain_does_not_connect(web):
    pages, fetched = web
    pages["https://wwwonly.example"] = (None, "ConnectionError")
    pages["https://www.wwwonly.example"] = page("Welcome")
    pages["https://www.wwwonly.example/privacy"] = page(POLICY)
    result = locate.locate_all("wwwonly.example", use_playwright=False)
    assert result["privacy"].ok
    assert result["privacy"].url == "https://www.wwwonly.example/privacy"  # guessed paths go to www
    assert "https://wwwonly.example/privacy" not in fetched


def test_www_is_tried_when_the_bare_domain_has_no_homepage(web):
    pages, _ = web
    pages["https://www.bare404.example"] = page('<a href="/legal/privacy">Privacy Policy</a>')
    pages["https://www.bare404.example/legal/privacy"] = page(POLICY)
    result = locate.locate_all("bare404.example", use_playwright=False)
    assert result["privacy"].url == "https://www.bare404.example/legal/privacy"


def test_unreachable_only_when_www_fails_too(web):
    pages, fetched = web
    pages["https://gone.example"] = (None, "ConnectionError")
    pages["https://www.gone.example"] = (None, "blocked: no public address")
    result = locate.locate_all("gone.example", use_playwright=False)
    assert not result["privacy"].ok
    assert fetched == ["https://gone.example", "https://www.gone.example"]  # no guessed paths
    assert failure.classify(_notes(result)) == "unreachable"


def test_bare_answers_with_an_error_so_the_site_is_not_unreachable(web):
    pages, _ = web
    pages["https://down.example"] = (None, "503")
    pages["https://www.down.example"] = (None, "ConnectionError")
    result = locate.locate_all("down.example", use_playwright=False)
    assert failure.classify(_notes(result)) == "no_policy"


# --- a policy link a visitor gives us -------------------------------------------

@pytest.mark.parametrize("url, domain, expected", [
    ("https://x.com/legal/privacy#top", "x.com", "https://x.com/legal/privacy"),
    ("HTTPS://help.x.com/privacy?lang=en", "x.com", "https://help.x.com/privacy?lang=en"),
    ("x.com/privacy", "x.com", "https://x.com/privacy"),
    ("https://www.bbc.co.uk/usingthebbc/privacy", "bbc.co.uk", "https://www.bbc.co.uk/usingthebbc/privacy"),
    ("https://y.com/privacy", "x.com", None),
    ("https://x.com.evil.example/privacy", "x.com", None),
    ("https://user:pw@x.com/privacy", "x.com", None),
    ("javascript:alert(1)", "x.com", None),
    ("ftp://x.com/privacy", "x.com", None),
    ("https://x.com/a b", "x.com", None),
    ("https://x.com:99999/privacy", "x.com", None),
    ("https://x.com/" + "a" * 3000, "x.com", None),
])
def test_same_site_link(url, domain, expected):
    assert locate.same_site_link(url, domain) == expected


def test_given_link_is_tried_first_and_found(web):
    pages, fetched = web
    pages["https://odd.example"] = page("Nothing in the footer")
    pages["https://odd.example/company/data-notice"] = page(POLICY)
    result = locate.locate_all("odd.example", use_playwright=False,
                               policy_url="https://odd.example/company/data-notice")
    assert result["privacy"].ok and result["privacy"].discovered_via == "supplied"
    assert fetched[1] == "https://odd.example/company/data-notice"  # right after the homepage


def test_given_terms_link_is_never_stored_as_the_privacy_policy(web):
    pages, _ = web
    pages["https://t.example"] = page("Home")
    pages["https://t.example/legal/doc"] = page(TERMS)
    result = locate.locate_all("t.example", use_playwright=False, policy_url="https://t.example/legal/doc")
    assert result["terms"].ok and result["terms"].discovered_via == "supplied"
    assert not result["privacy"].ok
    assert "isn't the privacy policy" in " ".join(result["privacy"].notes)


def test_given_link_to_a_random_page_is_not_accepted(web):
    pages, _ = web
    pages["https://r.example"] = page("Home")
    pages["https://r.example/privacy-blog"] = page("Our team went hiking. " * 200)
    result = locate.locate_all("r.example", use_playwright=False, policy_url="https://r.example/privacy-blog")
    assert not result["privacy"].ok and not result["terms"].ok


def test_given_link_on_another_site_is_ignored(web):
    pages, fetched = web
    pages["https://mine.example"] = page("Home")
    pages["https://other.example/privacy"] = page("Mine.example " + POLICY)
    result = locate.locate_all("mine.example", use_playwright=False, policy_url="https://other.example/privacy")
    assert not result["privacy"].ok
    assert not any("other.example" in u for u in fetched)


def test_given_link_is_still_tried_when_the_homepage_is_walled(web):
    pages, _ = web
    pages["https://walled.example"] = ('<html><head><title>Just a moment...</title></head>'
                                       '<script src="/cdn-cgi/challenge-platform/x"></script></html>')
    pages["https://legal.walled.example/privacy"] = page(POLICY)
    result = locate.locate_all("walled.example", use_playwright=False,
                               policy_url="https://legal.walled.example/privacy")
    assert result["privacy"].ok and result["privacy"].url == "https://legal.walled.example/privacy"
    assert not result["terms"].ok
    assert failure.classify(result["terms"].notes) == "blocked"


# --- API and storage (local Postgres) -------------------------------------------

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    from imbroglio import api
    monkeypatch.setattr(api, "_limiter", api._RateLimiter(api.REQUESTS_PER_HOUR))
    monkeypatch.setattr(api, "_daily_limiter", api._RateLimiter(api.REQUESTS_PER_DAY, window=86400))


def _failed(conn, domain, notes):
    for dt in ("privacy", "terms"):
        db.insert_attempt(conn, None, domain, dt, False, "failed", None, None, None, 0, notes, 3.0)
    conn.commit()


def _store(conn, domain, doc_type="privacy"):
    text = f"{domain} {doc_type} policy. We collect personal data. " * 80
    sid = db.upsert_service(conn, domain)
    did = db.upsert_document(conn, sid, doc_type, f"https://{domain}/{doc_type}", "link-text")
    vid = db.insert_version(conn, did, content_hash(text), text, "static")
    conn.commit()
    return vid


def test_site_says_why_nothing_was_found(conn):
    _failed(conn, "walled.example", "homepage static -> 403; homepage render -> blocked: bot challenge; "
                                    "blocked: bot challenge")
    site = client.get("/v1/sites/walled.example").json()
    assert site["state"] == "no_policy_found"
    assert site["failure"]["reason"] == "blocked"
    assert site["failure"]["message"] == failure.MESSAGES["blocked"]
    assert site["failure"]["tried"] == ["https://walled.example (home page): the site turned us away"]
    cached = client.post("/v1/requests", json={"domain": "walled.example"}).json()
    assert cached["status"] == "no_policy_found" and cached["failure"]["reason"] == "blocked"


def test_a_new_policy_link_gets_past_the_nothing_found_cache_once(conn):
    _failed(conn, "hidden.example", "common-path https://hidden.example/privacy -> 404")
    assert client.post("/v1/requests", json={"domain": "hidden.example"}).json()["status"] == "no_policy_found"

    link = "https://hidden.example/about/data#x"
    r = client.post("/v1/requests", json={"domain": "hidden.example", "policy_url": link})
    assert r.status_code == 202 and r.json()["created"]
    row = conn.execute("SELECT policy_url FROM analysis_requests WHERE domain = 'hidden.example'").fetchone()
    assert row[0] == "https://hidden.example/about/data"
    claimed = jobs.claim(conn, "w")
    assert claimed[1:] == ("hidden.example", True, "https://hidden.example/about/data")
    jobs.finish(conn, claimed[0], True, {"documents": []})

    # the same link again is answered from the cache
    again = client.post("/v1/requests", json={"domain": "hidden.example", "policy_url": link})
    assert again.status_code == 200 and again.json()["status"] == "no_policy_found"


def test_policy_link_on_another_site_is_refused(conn):
    r = client.post("/v1/requests", json={"domain": "mine.example", "policy_url": "https://other.example/privacy"})
    assert r.status_code == 400 and r.json()["error"] == POLICY_LINK_ERROR


def test_policy_link_for_a_site_missing_one_document(conn):
    _store(conn, "half.example", "privacy")
    assert client.post("/v1/requests", json={"domain": "half.example"}).json()["status"] == "already_available"
    r = client.post("/v1/requests", json={"domain": "half.example", "policy_url": "https://half.example/tos"})
    assert r.status_code == 202
    # a site with both documents is never re-crawled for a link
    _store(conn, "whole.example", "privacy")
    _store(conn, "whole.example", "terms")
    r = client.post("/v1/requests", json={"domain": "whole.example", "policy_url": "https://whole.example/x"})
    assert r.json()["status"] == "already_available"


def test_request_status_carries_the_reason(conn):
    rid, _, _, public_id = jobs.enqueue(conn, "gone.example")
    jobs.claim(conn, "w")
    jobs.finish(conn, rid, True, {"documents": [
        {"doc_type": dt, "found": False, "notes": "homepage static -> ConnectionError; host unreachable"}
        for dt in ("privacy", "terms")]})
    body = client.get(f"/v1/requests/{public_id}").json()
    assert body["failure"]["reason"] == "unreachable"
    assert body["failure"]["message"] == "We couldn't reach this site. Check the spelling."


def test_not_rated_says_what_the_rating_leaves_out(conn, monkeypatch):
    from imbroglio import analysis
    from imbroglio.rubric import load
    monkeypatch.setattr(analysis, "RUBRIC_VERSION", "v0.3")
    rubric = load("v0.3")
    vid = _store(conn, "onedoc.example", "privacy")
    _store(conn, "onedoc.example", "terms")   # stored, never analyzed
    conn.execute(
        """INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                 quotes_verified, verified, model)
           VALUES (%s, 'v0.3', 'sells_personal_data', %s, 'no', %s, %s, true, 'test')""",
        (vid, rubric.check("sells_personal_data").category, ["onedoc.example privacy policy."], [True]))
    conn.commit()
    site = client.get("/v1/sites/onedoc.example").json()
    assert site["scorecard"]["documents"] == ["privacy"]
    assert site["missing"] == [] and site["not_rated"] == ["terms"]


def test_search_leaves_out_sites_we_never_found_anything_on(conn):
    search.clear_cache()
    db.upsert_service(conn, "typo-domian.example")   # a request that found nothing
    conn.commit()
    _store(conn, "real-domain.example")
    body = client.get("/v1/search", params={"q": "domain.example"}).json()
    assert [r["domain"] for r in body["results"]] == ["real-domain.example"]
    body = client.get("/v1/search", params={"q": "typo-domian.example"}).json()
    assert body["results"] == [] and body["can_request"] == "typo-domian.example"
    search.clear_cache()
