"""Paragraph dataset builder (ml/dataset.py): labels, quote placement, splits."""

from ml.dataset import QuoteCounts, assign_splits, groups, label_document
from imbroglio.verify import quote_offsets

TEXT = ("Privacy Policy\n"
        "We collect your email address when you sign up.\n"
        "\n"
        "We never sell your personal information to anyone.\n"
        "We keep your data for as long as necessary\n"
        "to provide the service.")
DOC = {"version_id": 7, "domain": "example.com", "doc_type": "privacy", "text": TEXT}


def label(check, status, quotes=(), flags=()):
    return {"check_id": check, "status": status, "quotes": list(quotes), "quotes_verified": list(flags)}


def by_idx(paras):
    return {p.idx: p for p in paras}


def test_quote_offsets_point_at_the_documents_own_words():
    [offsets] = quote_offsets(["we NEVER sell your personal information"], TEXT)
    a, b = offsets[0]
    assert TEXT[a:b] == "We never sell your personal information"
    assert quote_offsets(["We sell your personal information to anyone."], TEXT) == [None]


def test_positive_negative_and_keyword_failed_labels():
    counts = QuoteCounts()
    paras = by_idx(label_document(DOC, [
        label("sells_personal_data", "no", ["We never sell your personal information to anyone."], [True]),
        label("collects_sensitive_data", "yes", ["We collect your email address when you sign up."], [False]),
        label("breach_notification", "not_disclosed"),
    ], counts))

    assert sorted(paras) == [0, 1, 3, 4, 5]          # the blank line is not a paragraph
    assert paras[3].pos == {"sells_personal_data": "no"}
    assert paras[1].pos == {} and paras[1].kw_failed == ["collects_sensitive_data"]
    assert all(p.neg == ["breach_notification"] for p in paras.values())
    assert (counts.verified, counts.kw_failed, counts.not_found, counts.lost) == (1, 1, 0, 0)


def test_quote_across_two_lines_labels_both_and_misses_are_counted():
    counts = QuoteCounts()
    paras = by_idx(label_document(DOC, [
        label("retention_period", "vague",
              ["We keep your data for as long as necessary to provide the service.",
               "We delete everything after thirty days without exception."], [True, False]),
    ], counts))
    assert paras[4].pos == paras[5].pos == {"retention_period": "vague"}
    assert counts.verified == 1 and counts.not_found == 1


def test_positive_wins_over_keyword_failed_for_the_same_check():
    paras = by_idx(label_document(DOC, [
        label("sells_personal_data", "no",
              ["We never sell your personal information", "your personal information to anyone"],
              [True, False]),
    ], QuoteCounts()))
    assert paras[3].pos == {"sells_personal_data": "no"} and paras[3].kw_failed == []


DOCS = [{"domain": d, "content_hash": h} for d, h in
        [("a.com", "x"), ("a.com", "y"), ("b.com", "x"), ("c.com", "z"), ("d.com", "w"), ("e.com", "v")]]


def test_groups_join_sites_sharing_a_text_and_extra_groups():
    g = groups(DOCS, {"d.com": "tmpl", "e.com": "tmpl", "nowhere.com": "tmpl"})
    assert g["a.com"] == g["b.com"] == "a.com"
    assert g["d.com"] == g["e.com"] == "d.com"
    assert g["c.com"] == "c.com"


def test_splits_keep_groups_whole_and_are_deterministic():
    docs = [{"domain": f"s{i}.com", "content_hash": f"h{i // 2}"} for i in range(200)]
    g = groups(docs)
    split = assign_splits(docs, g, seed=3)
    assert split == assign_splits(docs, g, seed=3)
    per_doc = [split[g[d["domain"]]] for d in docs]
    assert all(per_doc[i] == per_doc[i + 1] for i in range(0, 200, 2))   # pairs share a text
    assert [per_doc.count(s) for s in ("train", "dev", "test")] == [140, 30, 30]
