"""Storing a document fetched by hand (cli store-document), for sites that block crawlers."""

from imbroglio import cli, db
from imbroglio.analyze import MIN_MANUAL_CHARS, store_manual

POLICY = "Canva collects the information you give us and shares it with our service providers. " * 30


def _run(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["imbroglio", "store-document", *argv])
    return cli.main()


def test_first_store_then_same_text_then_changed_text(conn):
    pasted = POLICY.replace(". ", ".\n")                 # one sentence per line, as a copy-paste comes out
    first = store_manual("canva.com", "privacy", "https://www.canva.com/policies/privacy-policy/",
                         "  " + pasted.replace("\n", " \r\n") + "\n\n\n")
    assert first.status == "stored-new"
    assert first.fetch_method == "manual" and first.discovered_via == "manual"
    assert first.chars == len(pasted.strip())            # normalized before hashing

    again = store_manual("canva.com", "privacy", "https://www.canva.com/policies/privacy-policy/", pasted)
    assert again.status == "unchanged" and again.version_id == first.version_id

    changed = store_manual("canva.com", "privacy", "https://www.canva.com/policies/privacy-policy/",
                           POLICY + " We now also sell it.")
    assert changed.status == "changed" and changed.version_id != first.version_id
    assert conn.execute("SELECT count(*) FROM change_events").fetchone()[0] == 1
    assert conn.execute("SELECT fetch_method FROM document_versions WHERE id = %s",
                        (changed.version_id,)).fetchone()[0] == "manual"


def test_a_page_saved_as_html_is_extracted_first(conn):
    page = ("<!DOCTYPE html><html><head><title>Privacy</title><style>p{color:red}</style></head>"
            "<body><nav><a href='/'>Home</a><a href='/pricing'>Pricing</a></nav>"
            f"<main><h1>Privacy Policy</h1><p>{POLICY}</p></main>"
            "<footer>Copyright Canva</footer><script>track()</script></body></html>")
    outcome = store_manual("canva.com", "privacy", "https://www.canva.com/privacy", page)
    assert outcome.status == "stored-new"
    stored = db.latest_text(conn, "canva.com", "privacy")
    assert "Canva collects" in stored
    for junk in ("<p>", "color:red", "track()", "Pricing"):
        assert junk not in stored


def test_too_short_to_be_a_policy_is_refused(conn):
    outcome = store_manual("canva.com", "privacy", "https://www.canva.com/privacy", "Access denied.")
    assert outcome.status == "failed" and str(MIN_MANUAL_CHARS) in outcome.notes
    assert conn.execute("SELECT count(*) FROM services").fetchone()[0] == 0


def test_cli_reads_the_file_and_reports(conn, monkeypatch, capsys, tmp_path):
    f = tmp_path / "canva-privacy.txt"
    f.write_text(POLICY, encoding="utf-8")
    assert _run(monkeypatch, "canva.com", "privacy", "https://www.canva.com/privacy", str(f)) == 0
    out = capsys.readouterr().out
    assert "stored-new" in out and "canva.com" in out and "extract canva.com" in out
    assert db.latest_text(conn, "canva.com", "privacy").startswith("Canva collects")

    f.write_text("blocked", encoding="utf-8")
    assert _run(monkeypatch, "canva.com", "terms", "https://www.canva.com/terms", str(f)) == 1
    assert "failed" in capsys.readouterr().out
