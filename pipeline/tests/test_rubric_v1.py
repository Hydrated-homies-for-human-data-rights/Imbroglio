"""Rubric v1.0 draft (docs/rubric-v1.md): loads, rates as designed, plain lines served."""

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imbroglio import advice, analysis, db, rubric as rubric_mod, scorer
from imbroglio.api import router
from imbroglio.llm_extract import output_schema, system_prompt
from imbroglio.normalize import content_hash
from imbroglio.rubric import RubricError, load
from imbroglio.scorer import ScoredFinding as F

V1 = load("v1.0")
V02 = load("v0.2")
# Enough answered high-concern questions to pass the coverage gate, and an
# answer from the terms, none a concern.
CLEAN = [F("sells_personal_data", "no", True), F("retention_period", "specific", True),
         F("deletion_on_request", "all_users", True), F("access_and_export", "all_users", True),
         F("forced_arbitration", "no", True)]


def rate(*extra):
    return scorer.rate(V1, [*CLEAN, *extra])[1]


def test_v1_keeps_every_category_and_v02_question():
    assert V1.categories == {**V02.categories, "terms": "Terms of service"}
    assert {c.id for c in V02.checks} <= {c.id for c in V1.checks}
    assert len(V1.checks) == 28 and scorer.version_for(V1) == "s3"
    assert V1.high_concern_checks == {
        "sells_personal_data", "retention_period", "deletion_on_request", "access_and_export",
        "opt_out_of_tracking", "trains_ai_on_user_data", "shares_with_ai_providers", "childrens_data"}


def test_every_answer_has_a_plain_line_for_the_reader():
    for c in V1.checks:
        for s in c.statuses.values():
            assert s.plain and s.plain.endswith(".") and s.plain != s.meaning, f"{c.id}.{s.name}"
            assert "—" not in s.plain, f"{c.id}.{s.name}"


@pytest.mark.parametrize("answer, expected", [
    ("private_content", "EXTENSIVE"),           # private messages or AI chats: high
    ("private_content_opt_out", "MODERATE"),    # s3: any medium concern
    ("other_data", "MODERATE"),
    ("other_data_opt_out", "LIMITED"),
    ("opt_in", "LIMITED"),
])
def test_ai_training_is_rated_by_what_is_trained_on(answer, expected):
    assert rate(F("trains_ai_on_user_data", answer, True)) == expected


def test_trackers_and_state_law_sale_count_once_with_ad_sharing():
    two = rate(F("shares_for_advertising", "yes", True), F("third_party_trackers", "advertising", True))
    assert two == "MODERATE"   # one practice, one medium concern
    sc = scorer.score(V1, [*CLEAN, F("shares_for_advertising", "yes", True),
                           F("third_party_trackers", "advertising", True),
                           F("sells_personal_data", "state_law_sale", True)])
    assert sc.value == 88 and [d.check_id for d in sc.deductions] == ["shares_for_advertising"]


def test_new_concerns_add_up():
    assert rate(F("shares_with_ai_providers", "may_train", True),
                F("childrens_data", "yes_without_consent", True)) == "SEVERE"     # two high
    assert rate(F("policy_change_notice", "posted_only", True),
                F("forced_arbitration", "yes", True)) == "MODERATE"                # two medium


# Terms of service (Nov 14): the questions a test user's Steam question showed were missing.

def test_terms_category_holds_the_terms_questions():
    assert [c.id for c in V1.checks if c.category == "terms"] == [
        "policy_change_notice", "forced_arbitration", "account_termination",
        "purchases_on_termination", "subscription_changes", "content_license"]
    concerns = {(c.id, n): s.concern for c in V1.checks if c.category == "terms" for n, s in c.statuses.items()}
    assert concerns[("forced_arbitration", "yes")] == concerns[("forced_arbitration", "yes_with_opt_out")] == "medium"
    assert all(v in (None, "info", "medium") for v in concerns.values())   # terms alone never make a site EXTENSIVE


@pytest.mark.parametrize("finding", [
    F("forced_arbitration", "yes", True), F("forced_arbitration", "yes_with_opt_out", True),
    F("account_termination", "any_reason", True), F("purchases_on_termination", "lost_without_refund", True),
    F("content_license", "broad_continues", True), F("policy_change_notice", "posted_only", True),
    F("subscription_changes", "without_notice", True),
])
def test_each_terms_concern_alone_makes_a_site_moderate(finding):
    assert rate(finding) == "MODERATE"
    assert scorer.score(V1, [*CLEAN, finding]).value == 88


def test_steam_like_terms_take_points_off_a_clean_privacy_policy():
    # Steam's Subscriber Agreement (Sep 10, 2026): disputes go to court, 30 days' notice of changes,
    # accounts closed only for breaking the rules, but purchases lost without a refund when they are,
    # and a license to user content for the length of its copyright.
    steam = [*CLEAN[:4], F("forced_arbitration", "no", True), F("policy_change_notice", "advance_notice", True),
             F("account_termination", "for_cause", True),
             F("purchases_on_termination", "lost_without_refund", True),
             F("content_license", "broad_continues", True)]
    assert scorer.rate(V1, steam)[1] == "MODERATE" and scorer.score(V1, steam).value == 76


def test_v03_calibration_carried_into_v1():
    v03 = load("v0.3")
    assert V1.check("retention_period").statuses["vague"].concern == "info"
    assert V1.check("opt_out_of_tracking").guidance == v03.check("opt_out_of_tracking").guidance
    assert V1.check("trains_ai_on_user_data").guidance == v03.check("trains_ai_on_user_data").guidance
    for c in v03.checks:     # every v0.3 evidence word, except location words that moved to precise_location
        missing = set(c.evidence) - set(V1.check(c.id).evidence)
        assert missing <= ({"location", "precise", "coordinates", "latitude", "geolocat", "gps"}
                           if c.id == "collects_sensitive_data" else set()), (c.id, missing)
    assert V1.check("collects_sensitive_data").relevant("we collect voice recordings")
    assert V1.check("third_party_trackers").relevant("third-party cookies")       # lenient: hyphen as space


def test_gap_check_questions_are_shown_but_only_price_changes_cost_points():
    assert rate(F("honors_gpc", "no", True)) == "LIMITED"                         # info
    assert rate(F("combines_across_products", "yes", True)) == "LIMITED"          # info
    assert rate(F("subscription_changes", "without_notice", True)) == "MODERATE"
    assert V1.check("honors_gpc").relevant("We honor Global Privacy Control signals.")
    assert V1.check("subscription_changes").relevant("We may change our fees at any time.")


def test_no_terms_answer_means_no_limited_rating():
    privacy_only = CLEAN[:4]     # a clean privacy policy, terms never found
    assert scorer.rate(V1, privacy_only)[1] == "MODERATE"
    sc = scorer.score(V1, privacy_only)
    assert (sc.value, sc.adjusted) == (89, True)
    assert scorer.rate(V1, CLEAN)[1] == "LIMITED" and scorer.score(V1, CLEAN).value == 100
    assert scorer.rate(V1, [*CLEAN[:4], F("forced_arbitration", "not_disclosed", True)])[1] == "MODERATE"
    assert any("only rated LIMITED if its documents answer" in r for r in scorer.rules_for(V1))
    assert not any("only rated LIMITED if its documents answer" in r for r in scorer.rules_for(V02))


def test_limited_requires_must_name_a_category(tmp_path, monkeypatch):
    raw = yaml.safe_load((rubric_mod.RUBRIC_DIR / "v1.0.yaml").read_text(encoding="utf-8"))
    raw["version"], raw["limited_requires"] = "vtest", ["tos"]
    (tmp_path / "vtest.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.setattr(rubric_mod, "RUBRIC_DIR", tmp_path)
    with pytest.raises(RubricError, match="limited_requires names unknown categories"):
        rubric_mod.load.__wrapped__("vtest")


def test_extraction_prompt_covers_every_question():
    prompt = system_prompt(V1)
    for c in V1.checks:
        assert f"check_id: {c.id}" in prompt
    assert "private_content_opt_out" in prompt
    for c in V1.checks:      # the model answers against `meaning`, never the reader's line
        for s in c.statuses.values():
            assert s.plain not in prompt
    assert len(output_schema(V1)["properties"]["findings"]["items"]["properties"]["check_id"]["enum"]) == 28


def test_advice_loads_for_v1_and_covers_the_new_ai_answers():
    book = advice.load("v1.0")
    assert book.for_finding("trains_ai_on_user_data", "private_content") is not None
    assert book.for_finding("trains_ai_on_user_data", "opt_in") is None


def test_plain_lines_are_all_or_nothing(tmp_path, monkeypatch):
    raw = yaml.safe_load((rubric_mod.RUBRIC_DIR / "v1.0.yaml").read_text(encoding="utf-8"))
    raw["version"] = "vtest"
    del raw["checks"][0]["statuses"]["no"]["plain"]
    (tmp_path / "vtest.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.setattr(rubric_mod, "RUBRIC_DIR", tmp_path)
    with pytest.raises(RubricError, match="every answer needs a plain line"):
        rubric_mod.load.__wrapped__("vtest")


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_api_serves_plain_lines(conn, monkeypatch):
    monkeypatch.setattr(analysis, "RUBRIC_VERSION", "v1.0")
    text = "Example policy. " * 100
    sid = db.upsert_service(conn, "v1.example")
    did = db.upsert_document(conn, sid, "privacy", "https://v1.example/privacy", "link-text")
    vid = db.insert_version(conn, did, content_hash(text), text, "static")
    for f in [*CLEAN, F("trains_ai_on_user_data", "private_content", True)]:
        conn.execute(
            """INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                     quotes_verified, verified, model)
               VALUES (%s, 'v1.0', %s, %s, %s, %s, %s, true, 'test')""",
            (vid, f.check_id, V1.check(f.check_id).category, f.status, ["Example policy."], [True]))
    analysis._write_scores(conn, vid, "v1.0")
    conn.commit()

    card = client.get("/v1/sites/v1.example").json()["scorecard"]
    assert card["headline"] == "EXTENSIVE" and card["score"]["value"] == 58
    ai = next(c for c in card["categories"] if c["key"] == "ai_training")["findings"][0]
    assert ai["plain"] == "They can use your private content, like messages, files or AI chats, to train AI."
    assert card["score"]["deductions"][0]["plain"] == ai["plain"]
    rubric = client.get("/v1/rubric").json()
    sells = next(k for c in rubric["categories"] for k in c["checks"] if k["check_id"] == "sells_personal_data")
    assert sells["statuses"][0]["plain"] == "They can sell your personal information for money."
