"""Near-duplicate grouping (ml/neardup.py) and the in_train flag."""

import random

import numpy as np

from ml.dataset import Paragraph, mark_in_train
from ml.neardup import jaccard_matrix, leakage, linked_groups, lsh_pairs, minhash, shingles

WORDS = ["".join(random.Random(i).choices("abcdefghij", k=5)) for i in range(400)]   # letters only: digits are masked


def text(seed: int, n: int = 300) -> str:
    rng = random.Random(seed)
    return " ".join(rng.choice(WORDS) for _ in range(n))


def test_shingles_ignore_urls_emails_and_digits():
    a = "Contact us at help@acme.com or https://acme.com/help by 2024 for any question about this"
    b = "Contact us at privacy@other.org or https://other.org/x by 1999 for any question about this"
    assert shingles(a) == shingles(b)
    assert shingles(a) != shingles(a.replace("question", "request"))


def test_jaccard_matrix_matches_set_arithmetic():
    sets = [shingles(text(s)) for s in range(4)] + [shingles(text(0) + " " + text(9, 60))]
    sim = jaccard_matrix(sets)
    for i in range(5):
        for j in range(5):
            expected = len(sets[i] & sets[j]) / len(sets[i] | sets[j])
            assert abs(sim[i, j] - expected) < 1e-6


def test_minhash_agreement_estimates_jaccard_and_lsh_finds_the_close_pair():
    base = text(1, 600)
    near = base.rsplit(" ", 40)[0] + " " + text(2, 40)       # same text, new ending
    sets = [shingles(base), shingles(near), shingles(text(3, 600))]
    sigs = minhash(sets, num_perm=256)
    true = len(sets[0] & sets[1]) / len(sets[0] | sets[1])
    assert abs((sigs[0] == sigs[1]).mean() - true) < 0.1
    pairs = lsh_pairs(sigs, bands=64, rows=4)
    assert (0, 1) in pairs and (0, 2) not in pairs


def test_linked_groups_chain_across_sites_and_skip_same_site_pairs():
    docs = [{"domain": d} for d in ["a.com", "b.com", "c.com", "d.com", "d.com"]]
    sim = np.zeros((5, 5))
    sim[0, 1] = sim[1, 2] = 0.5      # a~b, b~c: one group by chaining
    sim[3, 4] = 0.9                  # d's own two documents: no link
    assert linked_groups(docs, sim, 0.3) == {"a.com": "a.com", "b.com": "a.com", "c.com": "a.com"}
    assert linked_groups(docs, sim, 0.6) == {}


def test_leakage_drops_to_zero_when_copies_are_grouped():
    shared = "\n".join(f"Shared paragraph number {i} of the common template text." for i in range(30))
    docs = [{"domain": f"s{i}.com", "content_hash": str(i), "text": shared if i < 40 else text(i)}
            for i in range(80)]
    loose = leakage(docs, {}, seed=0)
    together = leakage(docs, {f"s{i}.com": "tmpl" for i in range(40)}, seed=0)
    assert loose > 0 and together == 0


def test_in_train_flags_only_dev_and_test_copies():
    def para(split, t):
        return Paragraph(1, "x.com", "privacy", 0, t, split=split)
    ps = [para("train", "We may update this policy."), para("test", "we may  update this policy."),
          para("dev", "Something else entirely."), para("train", "Only in training.")]
    mark_in_train(ps)
    assert [p.in_train for p in ps] == [False, True, False, False]
