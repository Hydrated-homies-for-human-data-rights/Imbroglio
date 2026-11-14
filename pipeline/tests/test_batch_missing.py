"""batch --missing: look again for the document a stored site doesn't have."""

from imbroglio import batch, cli, db, locate
from imbroglio.normalize import content_hash


def _store(conn, domain, *doc_types):
    sid = db.upsert_service(conn, domain)
    for t in doc_types:
        did = db.upsert_document(conn, sid, t, f"https://{domain}/{t}", "link-text")
        db.insert_version(conn, did, content_hash(domain + t), f"{t} text", "static")


def test_domains_missing_lists_sites_rated_on_one_document(conn):
    _store(conn, "both.example", "privacy", "terms")
    _store(conn, "privacy-only.example", "privacy")
    _store(conn, "terms-only.example", "terms")
    conn.commit()
    assert db.domains_missing(conn, "terms") == ["privacy-only.example"]
    assert db.domains_missing(conn, "privacy") == ["terms-only.example"]


def test_batch_missing_runs_over_those_sites(conn, monkeypatch, capsys):
    _store(conn, "steampowered.example", "privacy")
    conn.commit()
    ran = {}
    monkeypatch.setattr(batch, "run_batch", lambda domains, source, **kw: ran.update(domains=domains, source=source) or 7)
    monkeypatch.setattr("sys.argv", ["imbroglio.cli", "batch", "--missing", "terms"])
    assert cli.main() == 0
    assert ran == {"domains": ["steampowered.example"], "source": "missing terms"}


def test_batch_needs_a_file_or_missing_but_not_both(tmp_path, monkeypatch):
    f = tmp_path / "d.txt"
    f.write_text("example.com\n")
    for argv in (["batch"], ["batch", str(f), "--missing", "terms"]):
        monkeypatch.setattr("sys.argv", ["imbroglio.cli", *argv])
        assert cli.main() == 2


def test_steams_link_tag_is_stripped():
    assert (locate._strip_tracking("https://store.steampowered.com/subscriber_agreement/?snr=1_4_4__global-responsive-menu")
            == "https://store.steampowered.com/subscriber_agreement/")
