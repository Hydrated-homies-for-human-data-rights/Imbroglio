"""Rubric v0.2 and scorer s2 ("red flags + coverage"), docs/rubric.md."""

import hashlib

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import advice, analysis, db, rubric as rubric_mod, scorer
from imbroglio.api import router
from imbroglio.normalize import content_hash
from imbroglio.rubric import RubricError, load
from imbroglio.scorer import ScoredFinding as F

V02 = load("v0.2")
# Enough answered high-concern questions to pass the coverage gate, none of them a concern.
CLEAN = [F("sells_personal_data", "no", True), F("retention_period", "specific", True),
         F("deletion_on_request", "all_users", True), F("access_and_export", "all_users", True)]


def head(findings):
    return scorer.rate(V02, findings)[1]


def test_v02_marks_the_six_high_concern_questions():
    assert scorer.version_for(V02) == "s2" and scorer.version_for(load("v0.1")) == "s1"
    assert V02.high_concern_checks == {"sells_personal_data", "retention_period", "deletion_on_request",
                                       "access_and_export", "opt_out_of_tracking", "trains_ai_on_user_data"}
    sells = V02.check("sells_personal_data").statuses
    assert (sells["sold_for_money"].concern, sells["state_law_sale"].concern) == ("severe", "medium")
    assert V02.check("trains_ai_on_user_data").statuses["yes_with_opt_out"].concern == "medium"


def test_a_concern_level_must_match_its_exposure(tmp_path, monkeypatch):
    raw = yaml.safe_load((rubric_mod.RUBRIC_DIR / "v0.2.yaml").read_text(encoding="utf-8"))
    raw["version"] = "vtest"
    raw["checks"][0]["statuses"]["state_law_sale"]["exposure"] = 3   # medium concern shown as SEVERE
    (tmp_path / "vtest.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.setattr(rubric_mod, "RUBRIC_DIR", tmp_path)
    with pytest.raises(RubricError, match="concern medium means exposure 1"):
        rubric_mod.load.__wrapped__("vtest")


def test_same_concern_as_must_name_another_check(tmp_path, monkeypatch):
    raw = yaml.safe_load((rubric_mod.RUBRIC_DIR / "v0.2.yaml").read_text(encoding="utf-8"))
    raw["version"] = "vtest"
    raw["checks"][0]["statuses"]["state_law_sale"]["same_concern_as"] = "shares_for_ads"   # a typo
    (tmp_path / "vtest.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.setattr(rubric_mod, "RUBRIC_DIR", tmp_path)
    with pytest.raises(RubricError, match="same_concern_as must name another check"):
        rubric_mod.load.__wrapped__("vtest")


@pytest.mark.parametrize("extra, expected", [
    ([], "LIMITED"),
    ([F("opt_out_of_tracking", "no", True)], "EXTENSIVE"),                       # one high
    ([F("opt_out_of_tracking", "no", True), F("trains_ai_on_user_data", "yes", True)], "SEVERE"),
    ([F("breach_notification", "no", True)], "LIMITED"),                         # one medium isn't enough
    ([F("breach_notification", "no", True), F("shares_for_advertising", "yes", True)], "MODERATE"),
    ([F("discloses_to_government", "broad", True), F("security_measures", "generic", True)], "LIMITED"),
    ([F("opt_out_of_tracking", "no", False)], "LIMITED"),                        # unverified never counts
])
def test_headline_counts_concerns(extra, expected):
    assert head(CLEAN + extra) == expected


def test_selling_for_money_or_no_deletion_is_severe_alone():
    assert head([F("sells_personal_data", "sold_for_money", True), *CLEAN[1:]]) == "SEVERE"
    assert head([*CLEAN[:2], F("deletion_on_request", "no", True), CLEAN[3]]) == "SEVERE"
    # the state-law "sale" that 9 of 10 sites meant is only a medium concern
    assert head([F("sells_personal_data", "state_law_sale", True), *CLEAN[1:],
                 F("breach_notification", "no", True)]) == "MODERATE"


def test_one_medium_concern_shows_in_its_category_not_the_headline():
    # Only EXTENSIVE and SEVERE categories hold the headline up (design goal 5):
    # "kept as long as necessary" alone shouldn't stop a site being LIMITED.
    tiers, h = scorer.rate(V02, [*CLEAN[:1], F("retention_period", "vague", True), *CLEAN[2:]])
    assert tiers["retention"] == "MODERATE" and h == "LIMITED"
    tiers, h = scorer.rate(V02, CLEAN + [F("opt_out_of_tracking", "no", True)])
    assert tiers["user_rights"] == "EXTENSIVE" and h == "EXTENSIVE"


def test_selling_in_the_state_law_sense_and_ad_sharing_count_once():
    both = [F("sells_personal_data", "state_law_sale", True), *CLEAN[1:],
            F("shares_for_advertising", "yes", True)]
    assert head(both) == "LIMITED"                                         # one practice, one concern
    assert head(both + [F("breach_notification", "no", True)]) == "MODERATE"
    # without an ad-sharing concern the state-law sale still counts on its own
    assert head([F("sells_personal_data", "state_law_sale", True), *CLEAN[1:],
                 F("shares_for_advertising", "service_providers_only", True),
                 F("breach_notification", "no", True)]) == "MODERATE"


def test_two_high_concerns_rate_the_site_above_any_category():
    tiers, h = scorer.rate(V02, CLEAN + [F("opt_out_of_tracking", "no", True),
                                         F("trains_ai_on_user_data", "yes", True)])
    assert h == "SEVERE" and "SEVERE" not in tiers.values()


def test_too_few_answers_is_unclear_not_clean():
    assert head(CLEAN[:3]) == "UNCLEAR"                                    # 3 of 6 answered
    assert head(CLEAN[:3] + [F("breach_notification", "no", True)]) == "UNCLEAR"
    assert head(CLEAN[:3] + [F("opt_out_of_tracking", "no", True)]) == "EXTENSIVE"   # a concern is never hidden
    # nor are two confirmed medium ones: only LIMITED needs the coverage
    assert head(CLEAN[:3] + [F("breach_notification", "no", True),
                             F("shares_for_advertising", "yes", True)]) == "MODERATE"
    assert head([]) == "NOT_DISCLOSED"


def test_documents_combine_into_one_site():
    privacy = [F("sells_personal_data", "no", True), F("retention_period", "specific", True)]
    terms = [F("deletion_on_request", "all_users", True), F("access_and_export", "all_users", True),
             F("sells_personal_data", "state_law_sale", True), F("retention_period", "vague", True)]
    assert head(privacy) == "UNCLEAR" and head(privacy + terms) == "MODERATE"


def test_informational_answers_are_info_not_limited():
    tiers, h = scorer.rate(V02, CLEAN + [F("discloses_to_government", "broad", True),
                                         F("collects_sensitive_data", "yes", True),
                                         F("collects_from_third_parties", "no", True),
                                         F("trains_ai_on_user_data", "no", True)])
    assert tiers["government"] == "INFO" and tiers["collection"] == "INFO"   # INFO outranks a protective answer
    assert tiers["ai_training"] == "LIMITED" and h == "LIMITED"            # and never raises the headline
    tiers, _ = scorer.rate(V02, CLEAN + [F("security_measures", "generic", True),
                                         F("breach_notification", "no", True)])
    assert tiers["security"] == "MODERATE"
    assert scorer.answer_tier(V02.check("content_license").statuses["broad"]) == "INFO"
    assert scorer.answer_tier(V02.check("content_license").statuses["limited"]) == "LIMITED"


def test_s1_is_unchanged_for_v01():
    v01 = load("v0.1")
    found = [F("sells_personal_data", "yes", True), F("security_measures", "specific", True)]
    tiers, h = scorer.rate(v01, found)
    assert h == scorer.headline(tiers) == "SEVERE"


def test_published_rules_and_tiers_follow_the_version():
    assert scorer.rules_for(V02) is scorer.RULES_S2 and scorer.rules_for(load("v0.1")) is scorer.RULES_S1
    assert {"UNCLEAR", "INFO"} <= scorer.tier_meanings(V02).keys()
    assert not {"UNCLEAR", "INFO"} & scorer.tier_meanings(load("v0.1")).keys()


def test_every_advice_answer_exists_in_some_rubric():
    raw = yaml.safe_load(advice.ADVICE_FILE.read_text(encoding="utf-8"))
    versions = [load("v0.1"), V02]
    for check_id, a in raw["checks"].items():
        for status in a["applies_to"]:
            assert any(status in r.check(check_id).statuses for r in versions), (check_id, status)
    book = advice.load("v0.2")
    assert book.for_finding("sells_personal_data", "state_law_sale").title
    assert book.for_finding("sells_personal_data", "yes") is None


# --- the API on rubric v0.2 --------------------------------------------------------

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _site(conn, domain, answers):
    text = f"{domain} policy. " * 100
    sid = db.upsert_service(conn, domain)
    did = db.upsert_document(conn, sid, "privacy", f"https://{domain}/privacy", "link-text")
    vid = db.insert_version(conn, did, content_hash(text), text, "static")
    for check_id, status in answers:
        conn.execute(
            """INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                     quotes_verified, verified, model)
               VALUES (%s, 'v0.2', %s, %s, %s, %s, %s, true, 'test')""",
            (vid, check_id, V02.check(check_id).category, status, [f"{domain} policy."], [True]))
    analysis._write_scores(conn, vid, "v0.2")
    conn.commit()


def test_scorecard_lookup_and_search_agree_on_s2(conn, monkeypatch):
    monkeypatch.setattr(analysis, "RUBRIC_VERSION", "v0.2")
    monkeypatch.setattr("imbroglio.search._cache", None)
    _site(conn, "twohigh.example", [(f.check_id, f.status) for f in CLEAN]
          + [("opt_out_of_tracking", "no"), ("trains_ai_on_user_data", "yes"), ("collects_sensitive_data", "yes")])
    _site(conn, "thin.example", [("sells_personal_data", "no"), ("retention_period", "specific")])

    card = client.get("/v1/sites/twohigh.example").json()["scorecard"]
    assert (card["scorer_version"], card["headline"]) == ("s2", "SEVERE")
    assert set(card["headline_categories"]) == {"User rights", "AI and model training"}
    collection = next(c for c in card["categories"] if c["key"] == "collection")
    assert collection["tier"] == "INFO" and collection["findings"][0]["concern"] == "info"
    assert conn.execute("SELECT count(*) FROM scores WHERE tier = 'INFO'").fetchone()[0] == 1
    assert client.get("/v1/sites/thin.example").json()["scorecard"]["headline"] == "UNCLEAR"

    full = hashlib.sha256(b"twohigh.example").hexdigest()
    entry = next(s for s in client.get(f"/v1/lookup/{full[:5]}").json()["sites"] if s["hash"] == full)
    assert entry["scores"]["headline"] == "SEVERE"
    assert {c["key"]: c["tier"] for c in entry["scores"]["categories"]}["collection"] == "INFO"

    assert db.headlines(conn, "v0.2") == {"twohigh.example": "SEVERE", "thin.example": "UNCLEAR"}
    rubric = client.get("/v1/rubric").json()
    assert rubric["scorer_version"] == "s2" and {"UNCLEAR", "INFO"} <= {t["tier"] for t in rubric["tiers"]}
    license_ = next(k for c in rubric["categories"] for k in c["checks"] if k["check_id"] == "content_license")
    assert {s["status"]: (s["tier"], s["concern"]) for s in license_["statuses"]} == {
        "broad": ("INFO", "info"), "limited": ("LIMITED", None)}
