"""Rubric v0.3: the calibration of v0.2 from the first production reports."""

import pytest

from imbroglio import analysis, db, scorer
from imbroglio.cli import main
from imbroglio.llm_extract import Extraction, Finding
from imbroglio.normalize import content_hash
from imbroglio.rubric import load, looks_english

V02, V03 = load("v0.2"), load("v0.3")
CLEAN = [scorer.ScoredFinding("sells_personal_data", "no", True),
         scorer.ScoredFinding("retention_period", "specific", True),
         scorer.ScoredFinding("deletion_on_request", "all_users", True),
         scorer.ScoredFinding("access_and_export", "all_users", True)]


def test_same_questions_with_plain_lines_and_the_ai_split():
    assert [c.id for c in V03.checks] == [c.id for c in V02.checks]
    assert V03.categories == V02.categories and scorer.version_for(V03) == "s2"
    assert all(s.plain for c in V03.checks for s in c.statuses.values())
    assert set(V03.check("trains_ai_on_user_data").statuses) == {
        "private_content", "private_content_opt_out", "other_data", "other_data_opt_out", "opt_in", "no"}
    assert V03.high_concern_checks == V02.high_concern_checks


def test_as_long_as_necessary_is_shown_but_costs_nothing():
    vague = V03.check("retention_period").statuses["vague"]
    assert (vague.concern, vague.exposure) == ("info", 0)
    sc = scorer.score(V03, [CLEAN[0], scorer.ScoredFinding("retention_period", "vague", True), *CLEAN[2:],
                            scorer.ScoredFinding("shares_for_advertising", "yes", True)])
    assert sc.value == 88      # v0.2: 76, two medium concerns


@pytest.mark.parametrize("answer, headline", [
    ("private_content", "EXTENSIVE"), ("private_content_opt_out", "LIMITED"),
    ("other_data", "LIMITED"), ("other_data_opt_out", "LIMITED"),
])
def test_ai_training_rated_by_what_is_trained_on(answer, headline):
    assert scorer.rate(V03, [*CLEAN, scorer.ScoredFinding("trains_ai_on_user_data", answer, True)])[1] == headline


@pytest.mark.parametrize("check_id, quote", [
    ("collects_from_third_parties", "we can link the generated data with the third-party platforms of Meta"),
    ("opt_out_of_tracking", "AudiobookSTORE does not currently follow or respond to browser do-not-track signals."),
    ("trains_ai_on_user_data", "to improve its products and machine-learning technologies"),
    ("collects_from_third_parties", "credit history information from credit bureaus, which we use to help prevent fraud"),
    ("collects_sensitive_data", "voice recordings when you speak to Alexa"),
    ("access_and_export", "You have the right to request information at any time about all your personal data."),
])
def test_v03_lets_in_on_topic_quotes_v02_turned_away(check_id, quote):
    assert not V02.check(check_id).relevant(quote)
    assert V03.check(check_id).relevant(quote)


@pytest.mark.parametrize("quote", [
    "Vous pouvez aussi vous opposer au suivi de votre navigation sur ce site web en cliquant ici.",
    "Sämtliche Daten werden nach gesetzlichen Speicherfristen längstens 6 Monate archiviert oder gelöscht",
    "예를 들어, 귀하의 Dailymotion 광고 쿠키 ID는 6개월 동안 보유됩니다.",
    "当社がセキュリティシステムの違反を覚知した場合",
])
def test_quotes_in_other_languages_skip_the_english_word_check(quote):
    assert not looks_english(quote)
    assert V03.check("retention_period").relevant(quote)
    assert not V02.check("retention_period").relevant(quote)


@pytest.mark.parametrize("quote", [
    "name, phone number, fax number, email address, address, employer, user type, postal code, city",
    "We collect non-personal information such as browser type.",
    "You must be at least 13 years old to use the service.",
])
def test_english_quotes_without_an_evidence_word_still_fail(quote):
    assert looks_english(quote)
    assert not V03.check("collects_sensitive_data").relevant(quote)


# --- rebase, then re-ask only where an answer has to change ------------------------------

POLICY = ("We do not sell your personal information. We keep data as long as necessary. "
          "We use your messages to train our machine-learning models. You can opt out in settings. ")


def _doc(conn, domain, text=POLICY * 20):
    sid = db.upsert_service(conn, domain)
    did = db.upsert_document(conn, sid, "privacy", f"https://{domain}/privacy", "link-text")
    return db.insert_version(conn, did, content_hash(text), text, "static")


def _v02(conn, vid, answers):
    for check_id, status, quote in answers:
        conn.execute(
            """INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                     quotes_verified, verified, model)
               VALUES (%s, 'v0.2', %s, %s, %s, %s, %s, true, 'test')""",
            (vid, check_id, V02.check(check_id).category, status, [quote], [True]))
    analysis._write_scores(conn, vid, "v0.2")
    conn.commit()


ANSWERS = [("sells_personal_data", "no", "We do not sell your personal information."),
           ("retention_period", "vague", "We keep data as long as necessary."),
           ("trains_ai_on_user_data", "yes", "We use your messages to train our machine-learning models."),
           ("opt_out_of_tracking", "yes", "You can opt out in settings.")]


def _status(conn, vid, check_id, version="v0.3"):
    return conn.execute("""SELECT status, verified FROM findings WHERE version_id = %s AND rubric_version = %s
                           AND check_id = %s""", (vid, version, check_id)).fetchone()


def test_rebase_carries_answers_and_leaves_split_ones_for_the_rerun(conn):
    vid = _doc(conn, "a.example")
    _v02(conn, vid, ANSWERS)
    assert analysis.rebase(conn, vid, "v0.2", "v0.3") == "rebased"
    assert _status(conn, vid, "sells_personal_data") == ("no", True)
    assert _status(conn, vid, "retention_period") == ("vague", True)
    assert _status(conn, vid, "trains_ai_on_user_data") == ("yes", False)   # not a v0.3 answer: not counted


def _fake_extract(answers):
    def extract(text, rubric, model, client=None):
        return Extraction("claude-test", "ok", cost_usd=0.03, findings=[
            Finding(c, rubric.check(c).category, s, [q], [True], True, "") for c, s, q in answers])
    return extract


def test_reanalyze_replaces_only_the_named_questions(conn, monkeypatch):
    a, b, c = _doc(conn, "a.example"), _doc(conn, "copy.example"), _doc(conn, "other.example", "Other text. " * 300)
    for vid in (a, b):
        _v02(conn, vid, ANSWERS)
    _v02(conn, c, [ANSWERS[0], ("trains_ai_on_user_data", "no", "Other text.")])
    for vid in (a, b, c):
        analysis.rebase(conn, vid, "v0.2", "v0.3")

    groups = analysis.reanalysis_targets(conn, "v0.2", {"trains_ai_on_user_data": ["yes", "yes_with_opt_out"]})
    assert sorted(map(sorted, groups)) == [sorted([a, b])]      # identical text read once; c answered no

    monkeypatch.setattr(analysis, "extraction_enabled", lambda: True)
    monkeypatch.setattr(analysis, "extract", _fake_extract([
        ("trains_ai_on_user_data", "private_content_opt_out", "We use your messages to train our machine-learning models."),
        ("sells_personal_data", "sold_for_money", "We do not sell your personal information."),   # must be ignored
    ]))
    assert analysis.reanalyze_checks(conn, sorted(groups[0]), "v0.3", ["trains_ai_on_user_data"]) == "reanalyzed"
    for vid in (a, b):
        assert _status(conn, vid, "trains_ai_on_user_data") == ("private_content_opt_out", True)
        assert _status(conn, vid, "sells_personal_data") == ("no", True)     # untouched
    assert conn.execute("SELECT count(*) FROM extraction_runs WHERE rubric_version = 'v0.3'").fetchone()[0] == 1
    tiers = dict(conn.execute("SELECT category, tier FROM scores WHERE version_id = %s AND rubric_version = 'v0.3'",
                              (b,)).fetchall())
    assert tiers["ai_training"] == "MODERATE" and tiers["retention"] == "INFO"


def test_reanalyze_waits_for_the_rebase(conn, monkeypatch):
    vid = _doc(conn, "a.example")
    _v02(conn, vid, ANSWERS)
    monkeypatch.setattr(analysis, "extraction_enabled", lambda: True)
    assert analysis.reanalyze_checks(conn, [vid], "v0.3", ["trains_ai_on_user_data"]).startswith(
        "skipped:no v0.3 findings yet")


def test_skip_done_leaves_out_documents_already_read(conn, monkeypatch, capsys):
    read, unread = _doc(conn, "read.example"), _doc(conn, "unread.example", "Other text. " * 300)
    copy = _doc(conn, "copy.example")          # same text as read.example: one group with it
    for vid in (read, unread, copy):
        _v02(conn, vid, ANSWERS)
        analysis.rebase(conn, vid, "v0.2", "v0.3")
    monkeypatch.setattr(analysis, "extraction_enabled", lambda: True)
    monkeypatch.setattr(analysis, "extract", _fake_extract([
        ("trains_ai_on_user_data", "private_content", "We use your messages to train our machine-learning models.")]))
    assert analysis.reanalyze_checks(conn, [read, copy], "v0.3", ["trains_ai_on_user_data"]) == "reanalyzed"
    assert analysis.reread_versions(conn, "v0.3") == {read}

    args = ["imbroglio.cli", "reanalyze", "--rubric", "v0.3", "--from", "v0.2",
            "--where", "trains_ai_on_user_data=yes,yes_with_opt_out", "--dry-run"]
    monkeypatch.setattr("sys.argv", args)
    assert main() == 0
    assert "2 distinct documents to read (3 stored copies)" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", args + ["--skip-done"])
    assert main() == 0
    out = capsys.readouterr().out
    assert "1 already read under v0.3, skipped" in out
    assert "1 distinct documents to read (1 stored copies)" in out


def test_reanalyze_command_dry_run_and_bad_input(conn, monkeypatch, capsys):
    vid = _doc(conn, "a.example")
    _v02(conn, vid, ANSWERS)
    monkeypatch.setattr("sys.argv", ["imbroglio.cli", "reanalyze", "--rubric", "v0.3", "--from", "v0.2",
                                     "--where", "trains_ai_on_user_data=yes,yes_with_opt_out",
                                     "--where", "opt_out_of_tracking=limited", "--dry-run"])
    assert main() == 0
    assert "1 distinct documents to read (1 stored copies)" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["imbroglio.cli", "reanalyze", "--rubric", "v0.3", "--from", "v0.2",
                                     "--where", "trains_ai_on_user_data=private_content"])
    assert main() == 2          # not a v0.2 answer
    assert "aren't answers in v0.2" in capsys.readouterr().out


# --- "In short" on the report --------------------------------------------------------------

from fastapi import FastAPI                     # noqa: E402
from fastapi.testclient import TestClient       # noqa: E402

from imbroglio.api import router                # noqa: E402

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)


def _site(conn, domain, answers, version):
    rubric = load(version)
    vid = _doc(conn, domain, f"{domain} policy. " * 100)
    for check_id, status in answers:
        conn.execute(
            """INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                     quotes_verified, verified, model)
               VALUES (%s, %s, %s, %s, %s, %s, %s, true, 'test')""",
            (vid, version, check_id, rubric.check(check_id).category, status, [f"{domain} policy."], [True]))
    analysis._write_scores(conn, vid, version)
    conn.commit()


CLEAN_ANSWERS = [("sells_personal_data", "no"), ("retention_period", "specific"),
                 ("deletion_on_request", "all_users"), ("access_and_export", "all_users")]


def test_in_short_puts_the_biggest_concerns_first_then_protections(conn, monkeypatch):
    monkeypatch.setattr(analysis, "RUBRIC_VERSION", "v0.3")
    _site(conn, "ai.example", CLEAN_ANSWERS + [("trains_ai_on_user_data", "private_content"),
                                               ("shares_for_advertising", "yes")], "v0.3")
    summary = _client.get("/v1/sites/ai.example").json()["scorecard"]["summary"]
    assert summary == [
        "They can use your private content, like messages, files or AI chats, to train AI.",
        "They share your information with other companies for advertising or marketing.",
        "They say they don't sell your personal information.",
        "Anyone can ask them to delete their information.",
    ]


def test_in_short_for_a_clean_site_and_a_thin_one(conn, monkeypatch):
    monkeypatch.setattr(analysis, "RUBRIC_VERSION", "v0.3")
    _site(conn, "clean.example", CLEAN_ANSWERS, "v0.3")
    _site(conn, "thin.example", CLEAN_ANSWERS[:1], "v0.3")
    clean = _client.get("/v1/sites/clean.example").json()["scorecard"]["summary"]
    assert clean[0] == "Nothing in their documents took points off." and len(clean) == 4
    thin = _client.get("/v1/sites/thin.example").json()["scorecard"]["summary"]
    assert thin == ["Their documents answer too few of the key questions to give a full rating.",
                    "Nothing in their documents took points off.",
                    "They say they don't sell your personal information."]


def test_no_in_short_without_plain_lines(conn, monkeypatch):
    monkeypatch.setattr(analysis, "RUBRIC_VERSION", "v0.2")
    _site(conn, "old.example", CLEAN_ANSWERS, "v0.2")
    assert _client.get("/v1/sites/old.example").json()["scorecard"]["summary"] is None
