"""Calibration lab: scoring schemes over stored answers (pure functions, no DB)."""

import pytest

from imbroglio import calibrate
from imbroglio.rubric import load

RUBRIC = load("v0.1")


def score(key, answers):
    scheme = next(s for s in calibrate.SCHEMES if s.key == key)
    return scheme.score(RUBRIC, answers)


def test_site_answers_takes_most_exposed_verified_status():
    answers = calibrate.site_answers(RUBRIC, [
        ("retention_period", "specific", True),       # privacy policy
        ("retention_period", "indefinite", True),     # terms: worse, wins
        ("sells_personal_data", "yes", False),        # unverified: ignored
        ("deletion_on_request", "not_disclosed", True),
        ("access_and_export", "maybe", True),         # not a rubric status: ignored
    ])
    assert answers == {"retention_period": "indefinite"}


def test_current_scheme_matches_production_scorer():
    r = score("current", {"discloses_to_government": "broad", "security_measures": "specific"})
    assert r.headline == "EXTENSIVE"


def test_capped_scheme_stops_boilerplate_setting_the_headline():
    boilerplate = {"collects_from_third_parties": "yes", "content_license": "broad",
                   "discloses_to_government": "broad", "security_measures": "generic",
                   "breach_notification": "no"}
    assert score("current", boilerplate).headline == "EXTENSIVE"
    assert score("capped", boilerplate).headline == "MODERATE"
    assert score("capped", {**boilerplate, "sells_personal_data": "yes"}).headline == "SEVERE"


@pytest.mark.parametrize("answers, tier", [
    ({"sells_personal_data": "yes", "trains_ai_on_user_data": "yes"}, "SEVERE"),
    ({"trains_ai_on_user_data": "yes"}, "EXTENSIVE"),
    ({"shares_for_advertising": "yes", "retention_period": "vague"}, "MODERATE"),
    ({"shares_for_advertising": "yes", "discloses_to_government": "broad"}, "LIMITED"),
    ({}, "NOT_DISCLOSED"),
])
def test_red_flags(answers, tier):
    assert score("flags", answers).headline == tier


def test_red_flags_lists_the_reasons():
    r = score("flags", {"sells_personal_data": "yes", "shares_for_advertising": "yes"})
    assert "Personal information is sold" in r.reasons
    assert "Shared with third parties for advertising or marketing" in r.reasons


def test_coverage_gate_never_calls_a_silent_site_clean():
    thin = {"sells_personal_data": "no", "shares_for_advertising": "no"}
    assert score("flags", thin).headline == "LIMITED"
    assert score("flags+coverage", thin).headline == "UNCLEAR"
    covered = {"sells_personal_data": "no", "retention_period": "specific",
               "deletion_on_request": "all_users", "access_and_export": "all_users"}
    assert score("flags+coverage", covered).headline == "LIMITED"
    # a red flag is reported whatever the coverage
    assert score("flags+coverage", {"sells_personal_data": "yes"}).headline == "EXTENSIVE"


def test_points_good_practices_subtract():
    bad = score("points", {"sells_personal_data": "yes", "trains_ai_on_user_data": "yes",
                           "deletion_on_request": "no"})
    good = score("points", {"sells_personal_data": "no", "trains_ai_on_user_data": "no",
                            "deletion_on_request": "all_users"})
    assert bad.points == 15 and bad.headline == "SEVERE"
    assert good.points == -7 and good.headline == "LIMITED"


def test_spearman():
    assert calibrate.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert calibrate.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert calibrate.spearman([1, 1, 2, 2], [1, 2, 3, 4]) == pytest.approx(0.894, abs=1e-3)  # ties
    assert calibrate.spearman([1, 2], [1, 2]) is None
    assert calibrate.spearman([1, 1, 1], [1, 2, 3]) is None


def test_spread():
    assert calibrate.spread(["SEVERE"] * 10) == 0
    assert calibrate.spread(["SEVERE", "EXTENSIVE", "MODERATE", "LIMITED"]) == pytest.approx(1.0)
    assert calibrate.spread(["SEVERE", "UNCLEAR", "NOT_DISCLOSED"]) == 0   # only real tiers count


def test_report_renders():
    sites = {"a.com": {"sells_personal_data": "yes", "trains_ai_on_user_data": "yes"},
             "b.com": {"sells_personal_data": "no"}, "c.com": {}}
    text = calibrate.evaluate(RUBRIC, sites, {"a.com": "E", "b.com": "B"})
    assert "| Red flags + coverage |" in text
    assert "| a.com | 2 | E |" in text
