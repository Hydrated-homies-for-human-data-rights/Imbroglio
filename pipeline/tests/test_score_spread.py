"""score-spread: the score out of 100 across stored sites, read-only."""

import csv

from imbroglio import db, score_spread
from imbroglio.cli import main
from imbroglio.rubric import load

V02 = load("v0.2")
CLEAN = [("sells_personal_data", "no"), ("retention_period", "specific"),
         ("deletion_on_request", "all_users"), ("access_and_export", "all_users")]


def rows(answers, verified=True):
    return [("hash", c, s, verified, None) for c, s in answers]


def test_scores_each_site_as_the_api_does():
    scored = score_spread.score_sites(V02, {
        "clean.example": rows(CLEAN),
        "ai.example": rows(CLEAN + [("trains_ai_on_user_data", "yes")]),
        "thin.example": rows(CLEAN[:1]),
    })
    got = {s.domain: (s.headline, s.score.value if s.score else None) for s in scored}
    assert got == {"clean.example": ("LIMITED", 100), "ai.example": ("EXTENSIVE", 58),
                   "thin.example": ("UNCLEAR", None)}


def test_report_shows_spread_bunching_and_adjustments():
    four_medium = [CLEAN[0], *CLEAN[2:], ("breach_notification", "no"), ("shares_for_advertising", "yes"),
                   ("retention_period", "vague"), ("trains_ai_on_user_data", "yes_with_opt_out")]
    scored = score_spread.score_sites(V02, {
        **{f"ai{i}.example": rows(CLEAN + [("trains_ai_on_user_data", "yes")]) for i in range(3)},
        "moderate.example": rows(four_medium),
        "thin.example": rows(CLEAN[:1]),
    })
    text = score_spread.report(V02, scored)
    assert "5 analyzed sites, 4 with a score" in text and "No score (by rating): UNCLEAR 1" in text
    assert "| EXTENSIVE | 40 to 59 | 3 | 58 | 58 | 58 | 1 | 58 (100%) | 0 |" in text
    assert "| MODERATE | 60 to 79 | 1 | 60 | 60 | 60 | 1 | 60 (100%) | 1 |" in text
    assert "| `trains_ai_on_user_data` = `yes` | -42 | 3 |" in text
    assert "moderate.example: MODERATE, 52 kept at 60" in text
    assert " 50-59 " in text and " 90-100" in text


def test_report_with_nothing_scored():
    assert "Nothing to score yet." in score_spread.report(V02, [])


def test_command_reads_the_database_and_writes_nothing(conn, monkeypatch, tmp_path, capsys):
    from tests.test_scorer_s2 import _site
    _site(conn, "onehigh.example", CLEAN + [("trains_ai_on_user_data", "yes")])
    before = conn.execute("SELECT (SELECT count(*) FROM findings), (SELECT count(*) FROM scores)").fetchone()
    monkeypatch.setattr("sys.argv", ["imbroglio.cli", "score-spread", "--rubric", "v0.2",
                                     "--out", str(tmp_path / "spread.md"), "--csv", str(tmp_path / "s.csv")])
    assert main() == 0
    assert "| EXTENSIVE | 40 to 59 | 1 | 58 |" in capsys.readouterr().out
    assert (tmp_path / "spread.md").read_text(encoding="utf-8").startswith("# Score spread, rubric v0.2")
    with (tmp_path / "s.csv").open(encoding="utf-8") as f:
        assert list(csv.DictReader(f))[0] == {"domain": "onehigh.example", "rating": "EXTENSIVE", "score": "58",
                                             "unadjusted": "58", "deductions": "trains_ai_on_user_data=yes -42"}
    assert conn.execute("SELECT (SELECT count(*) FROM findings), (SELECT count(*) FROM scores)").fetchone() == before
