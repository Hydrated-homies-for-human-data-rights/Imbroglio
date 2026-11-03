"""Opt-out link harvest (links.py): what counts, what is dropped, which
link a category gets, and how the links reach the API."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import db
from imbroglio.api import router
from imbroglio.links import Link, best, classify, harvest
from imbroglio.normalize import content_hash

HOME = """
<html><body>
<footer>
  <a href="/privacy">Privacy Policy</a>
  <a href="/optout">Your Privacy Choices</a>
  <a href="https://www.calm.com/cookies">Cookie Settings</a>
  <a href="https://privacyportal.onetrust.com/webform/abc/def">Do Not Sell or Share My Personal Information</a>
  <a href="https://other-company.example/do-not-sell">Do not sell (their partner)</a>
  <a href="javascript:void(0)">Do not sell</a>
  <a href="/help">Help</a>
  <a href="/account/delete">Delete your account</a>
  <a href="/settings/ai"><span>AI training</span> preferences</a>
</footer>
</body></html>
"""

POLICY = """
<html><body>
<p>To exercise your rights, <a href="https://www.calm.com/privacy-request">submit a privacy request</a>.</p>
<p>See our <a href="/optout">Do Not Sell or Share</a> page.</p>
<p>Ad settings: <a href="https://www.calm.com/ads/preferences" aria-label="Ad preferences"></a></p>
</body></html>
"""


def test_harvest_keeps_own_and_vendor_links_and_drops_the_rest():
    links = harvest(HOME, "https://calm.com", "calm.com", "homepage")
    urls = {l.url for l in links}
    assert "https://calm.com/optout" in urls
    assert "https://www.calm.com/cookies" in urls
    assert "https://privacyportal.onetrust.com/webform/abc/def" in urls
    assert "https://calm.com/account/delete" in urls
    assert "https://calm.com/settings/ai" in urls
    assert not any("other-company" in u or "javascript" in u or u.endswith("/help") or u.endswith("/privacy")
                   for u in urls)


def test_each_link_gets_its_kind_and_category():
    by_url = {l.url: l for l in harvest(HOME, "https://calm.com", "calm.com", "homepage")}
    assert (by_url["https://calm.com/optout"].kind, by_url["https://calm.com/optout"].category) == \
        ("privacy_choices", "selling_sharing")
    assert by_url["https://www.calm.com/cookies"].category == "collection"
    assert by_url["https://calm.com/account/delete"].category == "retention"
    assert by_url["https://calm.com/settings/ai"].category == "ai_training"
    assert by_url["https://calm.com/settings/ai"].text == "AI training preferences"


def test_path_alone_can_say_what_a_link_is():
    assert classify("Choices", "https://x.com/optout") == ("privacy_choices", "selling_sharing")
    assert classify("Manage", "https://x.com/privacy-request") == ("data_request", "user_rights")
    assert classify("Read more", "https://x.com/blog/privacy-day") is None


def test_section_anchors_on_the_same_page_are_not_pages_of_the_sites_own():
    page = """<a href="#your-privacy-rights">Your Privacy Rights</a>
              <a href="/privacy#11-privacy-request-metrics">11. Privacy Request Metrics</a>
              <a href="#optanon-toggle-info-display">Your Privacy Choices</a>
              <a href="/rights#top">Exercise your rights</a>"""
    links = harvest(page, "https://x.com/privacy", "x.com", "privacy")
    assert [(l.kind, l.url) for l in links] == [
        ("privacy_choices", "https://x.com/privacy#optanon-toggle-info-display"),
        ("data_request", "https://x.com/rights#top")]


def test_aria_label_counts_when_the_link_has_no_text():
    links = harvest(POLICY, "https://www.calm.com/privacy", "calm.com", "privacy")
    ads = [l for l in links if l.url.endswith("/ads/preferences")]
    assert ads and ads[0].kind == "ad_preferences" and ads[0].text == "Ad preferences"


def test_best_picks_one_link_per_category_by_kind_then_own_site_then_policy_page():
    links = (harvest(HOME, "https://calm.com", "calm.com", "homepage")
             + harvest(POLICY, "https://www.calm.com/privacy", "calm.com", "privacy"))
    chosen = {l.category: l for l in best(links)}
    # privacy_choices outranks ad_preferences; the site's own page beats OneTrust;
    # the policy page's link (resolved against the policy's address) beats the homepage's
    assert chosen["selling_sharing"].url == "https://www.calm.com/optout"
    assert chosen["selling_sharing"].source == "privacy"
    assert chosen["user_rights"].url == "https://www.calm.com/privacy-request"
    assert set(chosen) == {"selling_sharing", "collection", "retention", "ai_training", "user_rights"}


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _site(conn, domain, text="We collect personal data. " * 80):
    service_id = db.upsert_service(conn, domain)
    doc_id = db.upsert_document(conn, service_id, "privacy", f"https://{domain}/privacy", "link-text")
    db.insert_version(conn, doc_id, content_hash(text), text, "static")
    conn.commit()
    return service_id


def test_links_are_stored_whole_and_reach_the_site_and_the_lookup(conn):
    service_id = _site(conn, "calm.com")
    db.replace_links(conn, service_id, [
        Link("privacy_choices", "selling_sharing", "https://calm.com/optout", "Your Privacy Choices", "homepage"),
        Link("ad_preferences", "selling_sharing", "https://calm.com/ads", "Ad settings", "homepage"),
        Link("delete_account", "retention", "https://calm.com/account/delete", "Delete your account", "privacy"),
    ])
    site = client.get("/v1/sites/calm.com").json()
    assert {(l["category"], l["url"]) for l in site["links"]} == {
        ("selling_sharing", "https://calm.com/optout"), ("retention", "https://calm.com/account/delete")}

    prefix = db.domain_hash("calm.com")[:5]
    entry = next(s for s in client.get(f"/v1/lookup/{prefix}").json()["sites"]
                 if s["hash"] == db.domain_hash("calm.com"))
    assert [l["url"] for l in entry["links"]] == ["https://calm.com/optout", "https://calm.com/account/delete"]

    # a new harvest replaces the old links, and an empty harvest keeps them
    db.replace_links(conn, service_id, [Link("cookie_settings", "collection", "https://calm.com/cookies", "Cookies", "homepage")])
    assert [l["url"] for l in client.get("/v1/sites/calm.com").json()["links"]] == ["https://calm.com/cookies"]
    db.replace_links(conn, service_id, [])
    assert [l["url"] for l in client.get("/v1/sites/calm.com").json()["links"]] == ["https://calm.com/cookies"]
