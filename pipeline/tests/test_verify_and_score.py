"""Quote verification and deterministic scoring: the two places where a silent
bug would publish a wrong claim instead of crashing."""

import pytest

from imbroglio import scorer
from imbroglio.rubric import load
from imbroglio.scorer import ScoredFinding
from imbroglio.verify import exact_quote, verify_quote, verify_quotes

DOC = """Privacy Policy
We collect your email address, device identifiers, and approximate location
when you use the Service.
We do not sell your personal information. We may share information with
advertising partners to show you relevant ads.
We do not sell your personal information to anyone, including advertisers or data brokers.
We retain your data for as long as necessary to provide the Service."""


@pytest.mark.parametrize("quote", [
    "We do not sell your personal information.",
    "we do not sell your personal information",                     # case
    "We collect your email address, device identifiers, and approximate location",  # line break in source
    "“We do not sell your personal information.”",        # curly quotes around it
    "We collect your email address ... approximate location",       # ellipsis, pieces in order
    "We collect your email address, device identifers, and approximate location",   # one typo, long quote
])
def test_verified(quote):
    assert verify_quote(quote, DOC)


@pytest.mark.parametrize("quote", [
    "We never sell your personal information.",                      # reworded: must fail
    "We sell your personal information.",                            # meaning inverted: must fail
    "We may share information with marketing partners",              # changed word
    "approximate location ... We collect your email address",        # pieces out of order
    "We do",                                                         # too short to prove anything
    "We retain your data for 30 days.",                              # fabricated
    # dropping "not" from a long sentence stays above 95% similarity; must still fail
    "We do sell your personal information to anyone, including advertisers or data brokers.",
])
def test_rejected(quote):
    assert not verify_quote(quote, DOC)


def test_exact_quote_returns_the_documents_own_words():
    doc = ("License. You grant us a non-exclusive, transferable, sub-licensable, royalty-free, and worldwide "
           "license to host, use, distribute, modify, run, copy, publicly perform or display, translate, and "
           "create derivative works of your content.")
    # the model dropped two letters ("publly"); the fuzzy pass accepts it, but what we
    # store and show must be the document's text
    typo = ("you grant us a non-exclusive, transferable, sub-licensable, royalty-free, and worldwide license "
            "to host, use, distribute, modify, run, copy, publly perform or display")
    assert verify_quote(typo, doc)
    exact = exact_quote(typo, doc)
    assert exact.startswith("You grant us") and "publicly perform or display" in exact and "publly" not in exact


@pytest.mark.parametrize("quote, expected", [
    ("“We do not sell your personal information.”", "We do not sell your personal information."),
    ("we collect your email address, device identifiers, and approximate location",
     "We collect your email address, device identifiers, and approximate location"),   # line break collapsed
    ("We collect your email address ... approximate location",
     "We collect your email address ... approximate location"),
    ("We retain your data for 30 days.", None),
])
def test_exact_quote_cases(quote, expected):
    assert exact_quote(quote, DOC) == expected


def test_verify_quotes_batch():
    assert verify_quotes(["We do not sell your personal information.", "made up text here"], DOC) == [True, False]


# --- scorer ---

RUBRIC = load("v0")


def F(check_id, status, verified=True):
    return ScoredFinding(check_id, status, verified)


def test_category_takes_worst_verified_finding():
    tiers = scorer.category_tiers(RUBRIC, [
        F("sells_personal_data", "no"),                 # exposure 0
        F("shares_for_advertising", "yes"),             # exposure 2
    ])
    assert tiers["selling_sharing"] == "EXTENSIVE"


def test_unverified_findings_never_count():
    tiers = scorer.category_tiers(RUBRIC, [F("sells_personal_data", "yes", verified=False)])
    assert tiers["selling_sharing"] == "NOT_DISCLOSED"


def test_all_categories_present_and_silence_is_not_disclosed():
    tiers = scorer.category_tiers(RUBRIC, [F("retention_period", "not_disclosed")])
    assert set(tiers) == set(RUBRIC.categories)
    assert tiers["retention"] == "NOT_DISCLOSED"


def test_headline_is_worst_not_average():
    tiers = {"a": "LIMITED", "b": "LIMITED", "c": "LIMITED", "d": "SEVERE"}
    assert scorer.headline(tiers) == "SEVERE"


def test_disclosed_tier_beats_not_disclosed_when_combining_documents():
    privacy = {"ai_training": "NOT_DISCLOSED", "security": "LIMITED"}
    terms = {"ai_training": "SEVERE", "security": "NOT_DISCLOSED"}
    assert scorer.combine(privacy, terms) == {"ai_training": "SEVERE", "security": "LIMITED"}


def test_scoring_is_deterministic():
    findings = [F(c.id, next(iter(c.statuses))) for c in RUBRIC.checks]
    assert scorer.category_tiers(RUBRIC, findings) == scorer.category_tiers(RUBRIC, list(reversed(findings)))
