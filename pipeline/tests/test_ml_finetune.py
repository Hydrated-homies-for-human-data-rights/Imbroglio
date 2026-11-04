"""Training targets for the transformer (ml/finetune.py). Needs the training
environment (ml/requirements-train.txt); skipped where PyTorch isn't installed."""

import pytest

pytest.importorskip("torch")

from ml.finetune import positive_weights, targets  # noqa: E402

CHECKS = ["a", "b", "c", "d"]
PARA = {"pos": {"a": "yes"}, "kw_failed": ["b"], "neg": ["c"]}     # d: unlabeled


@pytest.mark.parametrize("w", [0.0, 0.3, 1.0])
def test_unlabeled_weight_only_moves_unlabeled_paragraphs(w):
    y, weight = targets(PARA, CHECKS, w)
    assert y == [1.0, 0.0, 0.0, 0.0]
    assert weight == [1.0, 0.0, 1.0, w]


def test_positive_weights_balance_by_effective_counts():
    rows = [("t", [1, 0], [1, 1])] + [("t", [0, 0], [1, 0.5])] * 9
    pw = positive_weights(rows, 2, "full")
    assert pw[0].item() == pytest.approx(9.0)
    assert pw[1].item() == pytest.approx(5.5)       # no positives: divides by 1, clean 1 + 9 x 0.5
    assert positive_weights(rows, 2, "sqrt")[0].item() == pytest.approx(3.0)
