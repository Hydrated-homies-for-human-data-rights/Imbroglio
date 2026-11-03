"""Gold set tooling (ml/gold.py): sample, pools, the label server, disagreements."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from imbroglio.rubric import load
from ml.gold import Store, disagreements, draw_sample, make_handler, pool_document, write_pool

LONG = "x" * 50


def docs_and_sizes():
    docs, sizes = [], {}
    for vid in range(1, 201):
        split = "test" if vid <= 120 else "dev"
        doc_type = "privacy" if vid % 2 else "terms"
        docs.append({"version_id": vid, "domain": f"s{vid}.com", "doc_type": doc_type, "split": split})
        sizes[vid] = 300 if vid % 10 == 0 else 60      # every tenth document is too long
    return docs, sizes


def test_sample_is_stratified_capped_and_balanced():
    docs, sizes = docs_and_sizes()
    rows = draw_sample(docs, sizes)
    assert rows == draw_sample(docs, sizes)
    gold = [r for r in rows if r["set"] != "pilot"]
    assert sum(r["doc_type"] == "privacy" for r in gold) == 13 and len(gold) == 24
    assert all(r["split"] == "test" and r["paragraphs"] <= 250 for r in gold)
    assert [r["doc_type"] for r in rows if r["set"] == "pilot"] == ["privacy", "terms"]
    assert all(r["split"] == "dev" for r in rows if r["set"] == "pilot")
    double = [r for r in rows if r["set"] == "double"]
    assert len(double) == 12 and sum(r["doc_type"] == "privacy" for r in double) == 6
    single = [r["annotators"] for r in rows if r["set"] == "single"]
    assert single.count("gage") == single.count("sam") == 6
    assert len({r["version_id"] for r in rows}) == len(rows)


def para(idx, text, pos=None, kw=None):
    return {"version_id": 7, "idx": idx, "text": text, "pos": pos or {}, "kw_failed": kw or []}


def test_pool_takes_quotes_kw_failed_and_evidence_words_and_samples_the_rest():
    rubric = load("v0.2")
    paras = [para(0, "We do not sell data.", pos={"sells_personal_data": "no"}),   # short, but quoted
             para(1, "Advertising"),                                               # heading: no evidence match
             para(2, "We share information with advertising partners for marketing purposes."),
             para(3, "Some words here " + LONG, kw={"opt_out_of_tracking"})]
    paras += [para(i, f"Paragraph {i} about nothing in particular, {LONG}") for i in range(4, 30)]
    pools, sources, check = pool_document(paras, rubric)
    assert sources["sells_personal_data"][0] == ["quote"]
    assert 1 not in pools["shares_for_advertising"] and 2 in pools["shares_for_advertising"]
    assert sources["opt_out_of_tracking"][3] == ["quote_kw_failed"]
    assert len(check) == 10 and set(check) <= set(range(4, 30))
    assert pool_document(paras, rubric)[2] == check


def test_disagreements_compare_only_what_both_judged():
    a = {"answers": {"x": {"status": "yes"}, "y": {"status": "no"}},
         "passages": {"x": {"1": True, "2": False, "5": True}},
         "pool_check": {"9": [], "10": ["x"], "11": None}}
    b = {"answers": {"x": {"status": "yes"}, "y": {"status": "not_disclosed"}},
         "passages": {"x": {"1": True, "2": True}},
         "pool_check": {"9": ["y"], "10": ["x"], "11": []}}
    rows, counts = disagreements(a, b)
    assert counts == {"answers": [2, 1], "passages": [2, 1], "pool_check": [2, 1]}
    assert [(r["layer"], r["check"], r["idx"]) for r in rows] == [
        ("answers", "y", ""), ("passages", "x", 2), ("pool_check", "", 9)]


@pytest.fixture
def server(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    paras = [{**para(i, f"Line {i} {LONG}"), "split": "test", "domain": "s7.com"} for i in range(20)]
    (data / "paragraphs.jsonl").write_text("\n".join(json.dumps(p) for p in paras), encoding="utf-8")
    (data / "documents.jsonl").write_text(json.dumps({"version_id": 7, "split": "test"}), encoding="utf-8")
    sample = [{"order": 1, "set": "single", "annotators": "sam", "version_id": 7, "domain": "s7.com",
               "doc_type": "privacy", "split": "test", "paragraphs": 20}]
    write_pool(data, sample, tmp_path / "work")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Store(tmp_path / "work", tmp_path / "labels")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path / "labels"
    srv.shutdown()


def call(url, method="GET", body=None):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_server_saves_and_returns_labels_only_for_the_assigned_annotator(server):
    base, labels = server
    state = call(f"{base}/api/state?a=sam")
    assert [t["version_id"] for t in state["tasks"]] == [7] and len(state["rubric"]["checks"]) == 14
    assert call(f"{base}/api/state?a=gage")["tasks"] == []
    doc = call(f"{base}/api/doc/7")
    assert len(doc["lines"]) == 20 and len(doc["pool_check"]) == 10
    assert call(f"{base}/api/labels/sam/7") is None

    label = {"version_id": 7, "annotator": "sam", "answers": {}, "finished": {"answers": "now"}}
    assert call(f"{base}/api/labels/sam/7", "PUT", label) == {"ok": True}
    assert call(f"{base}/api/labels/sam/7")["finished"] == {"answers": "now"}
    assert (labels / "sam" / "7.json").exists()
    assert call(f"{base}/api/state?a=sam")["tasks"][0]["finished"] == {"answers": "now"}

    with pytest.raises(urllib.error.HTTPError) as e:
        call(f"{base}/api/labels/gage/7", "PUT", {**label, "annotator": "gage"})
    assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        call(f"{base}/api/labels/sam/7", "PUT", {**label, "version_id": 8})
    assert e.value.code == 400
