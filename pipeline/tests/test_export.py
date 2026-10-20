"""Classifier training-data export (real Postgres, fake extractor)."""

import json

from imbroglio import analysis, db, export
from imbroglio.llm_extract import Extraction, check_findings
from imbroglio.normalize import content_hash

TEXT = ("Privacy Policy\nWe do not sell your personal information.\n"
        "We use your content to train our machine learning models.")


def test_export_writes_documents_labels_rubric_and_readme(conn, monkeypatch, tmp_path):
    def fake_extract(text, rubric, model):
        raw = [{"check_id": "sells_personal_data", "status": "no",
                "quotes": ["We do not sell your personal information."], "explanation": "no sale"},
               {"check_id": "trains_ai_on_user_data", "status": "yes",
                "quotes": ["We sell everything forever."], "explanation": "fabricated"}]
        return Extraction(model, "ok", findings=check_findings(rubric, raw, text))

    monkeypatch.setattr(analysis, "extract", fake_extract)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    sid = db.upsert_service(conn, "export.example")
    did = db.upsert_document(conn, sid, "privacy", "https://export.example/privacy", "link-text")
    vid = db.insert_version(conn, did, content_hash(TEXT), TEXT, "static")
    conn.commit()
    analysis.ensure_analyzed(conn, vid, rubric_version="v0.1")

    lines = [json.dumps(r) for r in export.rows(conn, "v0.1")]
    counts = export.split_stdout(["noise from ssh\n"] + lines, tmp_path, "v0.1")
    assert counts["document"] == 1
    assert counts["label"] == 14                      # every check answered for every document

    labels = {r["check_id"]: r for r in map(json.loads, (tmp_path / "labels.jsonl").open(encoding="utf-8"))}
    assert labels["sells_personal_data"]["verified"] is True
    assert labels["sells_personal_data"]["exposure"] == 0
    assert labels["trains_ai_on_user_data"]["verified"] is False       # fabricated quote stays flagged
    assert labels["retention_period"]["status"] == "unanswered"
    doc = json.loads((tmp_path / "documents.jsonl").read_text(encoding="utf-8"))
    assert doc["text"] == TEXT and doc["version_id"] == vid
    assert (tmp_path / "rubric.yaml").read_text(encoding="utf-8").startswith("# Rubric v0.1")
    assert "Split by site" in (tmp_path / "README.md").read_text(encoding="utf-8")
