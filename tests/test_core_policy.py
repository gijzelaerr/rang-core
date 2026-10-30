"""Scientific invariants: flag protection, full-Jones TV and selection safeguards.

Live part of tests/test_flagging.py at commit 2da566c
(now history/tests/test_flagging.py,
sha256 e8b4ef016a5cd29b22a7c08fcf46c0cb3a5038bc04b97058ca32ed39389ebaea):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

import numpy as np
from rang.core_policy import (
    axis_weights,
    fixed_support_tv,
    gain_tv,
    polar_gauge,
    policy_mask,
    split_holdout,
)


def test_rust_tv_matches_independent_full_complex_frobenius_norm():
    rng = np.random.default_rng(41)
    gains = rng.normal(size=(3, 5, 2, 2, 2)) + 1j * rng.normal(size=(3, 5, 2, 2, 2))
    valid = np.ones((3, 5, 2), bool)
    valid[1, 2, 0] = False
    times, frequencies = [0, 2, 4], [10, 20, 30, 40, 50]
    result = gain_tv(gains, valid, times, frequencies)
    for axis in (0, 1):
        difference = np.diff(gains, axis=axis)
        expected = np.linalg.norm(difference, axis=(-1, -2))
        lower, upper = [slice(None)] * 3, [slice(None)] * 3
        lower[axis], upper[axis] = slice(None, -1), slice(1, None)
        support = valid[tuple(lower)] & valid[tuple(upper)]
        actual = result["edges"][axis][tuple(lower)]
        np.testing.assert_allclose(actual[support], expected[support], atol=1e-14)
        assert np.isnan(actual[~support]).all()
    np.testing.assert_allclose(axis_weights([0, 1, 2, 100]), [1, 1, 0])


def test_polar_gauge_removes_unitary_ambiguity_preserves_common_amplitude_and_rime():
    rng = np.random.default_rng(3)
    unitary = np.stack(
        [
            np.linalg.qr(rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2)))[0]
            for _ in range(6)
        ]
    ).reshape(2, 3, 2, 2)
    gains = np.broadcast_to(unitary[:, :, None], (2, 3, 4, 2, 2)).copy()
    gains *= np.array([2, 3, 4, 5])[None, None, :, None, None]
    aligned, valid = polar_gauge(gains, np.ones((2, 3, 4), bool))
    expected = (
        np.broadcast_to(np.eye(2), gains.shape)
        * np.array([2, 3, 4, 5])[None, None, :, None, None]
    )
    np.testing.assert_allclose(aligned, expected, atol=1e-14)
    before = gains[:, :, 1] @ gains[:, :, 2].conj().swapaxes(-1, -2)
    after = aligned[:, :, 1] @ aligned[:, :, 2].conj().swapaxes(-1, -2)
    np.testing.assert_allclose(before, after, atol=1e-14)
    assert gain_tv(aligned, valid, [0, 1], [10, 20, 30])["total"] < 1e-13
    gains[0, 0, 0] = 0
    _, valid = polar_gauge(gains, valid)
    assert not valid[0, 0].any()


def test_missing_gain_edges_are_rejected_and_fixed_support_is_not_changed():
    base = np.array([[1, 2, np.nan], [3, np.nan, np.nan]])
    assert fixed_support_tv(base, base) == 4.5
    new = np.array([[0.5, 1, 100], [1.5, 100, 100]])
    assert fixed_support_tv(new, base) == 2.25
    new[0, 1] = np.nan
    assert fixed_support_tv(new, base) is None


def test_policy_requires_residual_evidence_respects_budget_and_protected_splits():
    eligible = np.ones((10, 10), bool)
    train, validation, test = split_holdout(eligible, 7)
    assert not (train & (validation | test)).any() and not (validation & test).any()
    assert np.array_equal(train | validation | test, eligible)
    np.testing.assert_array_equal(split_holdout(eligible, 7)[0], train)
    outliers = np.full((10, 10), 3.0)
    guidance = np.zeros((10, 10))
    guidance[2:4] = 10
    proposed = policy_mask(
        outliers, guidance, train, threshold=8, tv_weight=3, max_fraction=0.1
    )
    assert np.sum(proposed) <= int(0.1 * np.sum(train))
    assert not proposed[~train].any()
    assert not proposed[guidance == 0].any()
    assert not policy_mask(
        np.ones_like(outliers),
        guidance,
        train,
        threshold=3,
        tv_weight=100,
        max_fraction=0.9,
    ).any()


def test_sparse_gain_bins_are_not_emptied_by_holdout_selection():
    eligible = np.ones((1, 100), bool)
    groups = np.arange(100)[None]
    train, validation, test = split_holdout(eligible, 7, groups=groups)
    assert train.all() and not validation.any() and not test.any()
    groups[:] = np.arange(100) // 10
    train, validation, test = split_holdout(eligible, 7, groups=groups)
    assert min(np.count_nonzero(train[groups == i]) for i in range(10)) >= 2
    assert not (train & (validation | test)).any()
