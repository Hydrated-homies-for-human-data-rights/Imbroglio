"""rejected-quotes: real quotes the evidence-word check turned away, read-only."""

import csv

from imbroglio import analysis, db, rejected_quotes as rq
from imbroglio.cli import main
from imbroglio.normalize import content_hash
from imbroglio.rubric import load

V02 = load("v0.2")

SELL = "We do not sell your personal information to anyone."
THIRD = "We receive information about you from our advertising partners."
OTHER_USERS = "Other users may provide information about you when they upload their contacts."
OTHER_USERS_2 = "Other users can upload their contacts, which may include information about you."
OFF_TOPIC = "You must be at least 13 years old to use the service."


def doc(*sentences):
    return " ".join(sentences) + " Filler text that says nothing in particular." * 20


ROWS = [
    ("a.example", "privacy", doc(SELL, THIRD, OTHER_USERS),
     [("sells_personal_data", "no", [SELL]),
      ("collects_from_third_parties", "yes", [THIRD, OTHER_USERS])]),
    ("b.example", "privacy", doc(SELL, OTHER_USERS_2, OFF_TOPIC),
     [("sells_personal_data", "no", [SELL]),
      # no counting quote at all: one real but without an evidence word, one off topic
      ("collects_from_third_parties", "yes", [OTHER_USERS_2, OFF_TOPIC]),
      # not in the document at all: a misquote, not an evidence-word miss
      ("retention_period", "vague", ["We keep everything for as long as we like forever."]),
      ("deletion_on_request", "not_disclosed", [])]),
]


def test_quotes_are_rechecked_both_ways():
    quotes = rq.check_quotes(V02, ROWS)
    third = [q for q in quotes if q.check_id == "collects_from_third_parties"]
    assert [(q.found, q.relevant) for q in third] == [(True, True), (True, False), (True, False), (True, False)]
    misquote = next(q for q in quotes if q.check_id == "retention_period")
    assert (misquote.found, misquote.relevant) == (False, False)
    assert not any(q.check_id == "deletion_on_request" for q in quotes)   # not_disclosed has no quotes


def test_summary_counts_turned_away_and_rescuable_answers():
    r = rq.summarize(V02, rq.check_quotes(V02, ROWS))["collects_from_third_parties"]
    assert (r.quotes, r.found, r.counted, len(r.rejected)) == (4, 4, 1, 3)
    # a.example's answer already counts; b.example's has real quotes but none counting
    assert (r.answers, r.answers_counted, r.answers_rescuable) == (2, 1, 1)
    retention = rq.summarize(V02, rq.check_quotes(V02, ROWS))["retention_period"]
    assert (retention.found, len(retention.rejected), retention.answers_rescuable) == (0, 0, 0)


def test_suggestions_rescue_quotes_without_matching_everything():
    quotes = rq.check_quotes(V02, ROWS)
    sugg = {s.term: s for s in rq.suggest(V02, quotes, "collects_from_third_parties")}
    assert "other users" in sugg and sugg["other users"].rescued == 2
    assert sugg["other users"].answers == 1          # b.example's answer would start counting
    assert sugg["other users"].elsewhere == 0
    # words already covered by the list, stopwords, and one-off words aren't suggested
    assert "partners" not in sugg and "about" not in sugg and "years" not in sugg


def test_terms_skip_stopwords():
    assert rq.terms("They may upload their contacts") == {"upload", "contacts", "may upload",
                                                          "upload their", "their contacts"}


def test_report_and_csv(tmp_path):
    quotes = rq.check_quotes(V02, ROWS)
    text = rq.report(V02, quotes)
    assert "7 cited quotes" in text and "3 real quotes were turned away" in text
    assert "| `collects_from_third_parties` | 4 | 100.0% | 25.0% | 3 | 1 of 2 | 1 |" in text
    assert "| `other users` | 2 | 1 | 0% |" in text
    assert 'b.example (privacy, `yes`): "You must be at least 13 years old to use the service."' in text
    only = rq.report(V02, quotes, only="sells_personal_data")
    assert "## `collects_from_third_parties`" not in only

    rq.write_csv(tmp_path / "r.csv", quotes)
    with (tmp_path / "r.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3 and rows[0]["on_topic"] == "" and rows[0]["check_id"] == "collects_from_third_parties"


def test_command_reads_the_database_and_writes_nothing(conn, monkeypatch, tmp_path, capsys):
    for domain, doc_type, text, findings in ROWS:
        sid = db.upsert_service(conn, domain)
        did = db.upsert_document(conn, sid, doc_type, f"https://{domain}/privacy", "link-text")
        vid = db.insert_version(conn, did, content_hash(text), text, "static")
        for check_id, status, quotes in findings:
            conn.execute(
                """INSERT INTO findings (version_id, rubric_version, check_id, category, status, quotes,
                                         quotes_verified, verified, model)
                   VALUES (%s, 'v0.2', %s, %s, %s, %s, %s, false, 'test')""",
                (vid, check_id, V02.check(check_id).category, status, quotes, [False] * len(quotes)))
        analysis._write_scores(conn, vid, "v0.2")
    conn.commit()
    before = conn.execute("SELECT (SELECT count(*) FROM findings), (SELECT count(*) FROM scores)").fetchone()

    monkeypatch.setattr("sys.argv", ["imbroglio.cli", "rejected-quotes", "--rubric", "v0.2",
                                     "--out", str(tmp_path / "r.md"), "--csv", str(tmp_path / "r.csv")])
    assert main() == 0
    out = capsys.readouterr().out
    assert "3 real quotes were turned away" in out and "| `other users` | 2 | 1 | 0% |" in out
    assert (tmp_path / "r.md").exists() and (tmp_path / "r.csv").exists()
    assert conn.execute("SELECT (SELECT count(*) FROM findings), (SELECT count(*) FROM scores)").fetchone() == before

    monkeypatch.setattr("sys.argv", ["imbroglio.cli", "rejected-quotes", "--rubric", "v0.2", "--check", "nope"])
    assert main() == 2
