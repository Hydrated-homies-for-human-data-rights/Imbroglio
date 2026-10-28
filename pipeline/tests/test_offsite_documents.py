"""Stored documents that belong to another site (db.offsite_documents)."""

from imbroglio import cli, db
from imbroglio.normalize import content_hash

POLICY = "We collect personal data and share it with partners. " * 40


def _doc(conn, domain, doc_type, url, text):
    sid = db.upsert_service(conn, domain)
    did = db.upsert_document(conn, sid, doc_type, url, "hub-link")
    db.insert_version(conn, did, content_hash(text), text, "static")
    conn.commit()
    return did


def test_only_other_sites_documents_that_never_name_the_site_are_listed(conn):
    wrong = _doc(conn, "keepassxc.org", "privacy", "https://docs.github.com/privacy", "GitHub " + POLICY)
    _doc(conn, "keepassxc.org", "terms", "https://keepassxc.org/terms", "Terms. " + POLICY)
    _doc(conn, "wikipedia.org", "privacy", "https://foundation.wikimedia.org/privacy",
         "Wikipedia and the Wikimedia Foundation. " + POLICY)                 # another site, names it
    _doc(conn, "powerapps.com", "privacy", "https://go.microsoft.com/fwlink/?LinkId=1",
         "Microsoft Power Apps. " + POLICY)                                   # names it with a space
    assert db.offsite_documents(conn) == [
        (wrong, "keepassxc.org", "privacy", "https://docs.github.com/privacy", False)]


def test_remove_deletes_only_the_named_sites_documents(conn, monkeypatch, capsys):
    _doc(conn, "keepassxc.org", "privacy", "https://docs.github.com/privacy", "GitHub " + POLICY)
    _doc(conn, "leagueoflegends.com", "privacy", "https://www.riotgames.com/privacy", "Riot " + POLICY)
    run = lambda *a: (monkeypatch.setattr("sys.argv", ["imbroglio", "offsite-documents", *a]), cli.main())[1]

    assert run("--remove", "example.com") == 1                       # not listed: nothing happens
    assert len(db.offsite_documents(conn)) == 2
    assert run("--remove", "keepassxc.org") == 0                     # riotgames.com is Riot's own policy
    assert [d[1] for d in db.offsite_documents(conn)] == ["leagueoflegends.com"]
    assert "removed 1 documents" in capsys.readouterr().out
