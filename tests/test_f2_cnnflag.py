"""F2: the Rust flagger kernel against the NumPy features and JAX network
(research/f2-flagger.md, section 3)."""

import numpy as np
import pytest

jax = pytest.importorskip("jax")

from rang import f2flag as ff


def problem(seed=3, nant=5, nt=7, nc=96):
    rng = np.random.default_rng(seed)
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    times = np.repeat(np.arange(nt) * 8.0, nbl)
    p = np.tile(a1, nt).astype(np.int32)
    q = np.tile(a2, nt).astype(np.int32)
    vis = rng.normal(size=(nt * nbl, nc, 4)) + 1j * rng.normal(size=(nt * nbl, nc, 4))
    vis[..., [0, 3]] += 5.0
    vis[rng.random(vis.shape[:2]) < 0.02] *= 30
    vis = vis.astype(np.complex64)
    flagged = rng.random((nt * nbl, nc)) < 0.1
    flagged[:, 10:14] = True
    flagged[3] = True
    # A missing row: drop the last row of the first time.
    keep = np.ones(len(p), bool)
    keep[nbl - 1] = False
    return vis[keep], flagged[keep], p[keep], q[keep], times[keep]


def test_weight_count():
    assert ff.count_weights(ff.init_params(0)) == 2785


def test_rust_matches_numpy_and_jax():
    vis, flagged, p, q, times = problem()
    params = ff.init_params(1)
    rust = ff.rust_logits(vis, flagged, p, q, times, ff.flat_weights(params))
    planes = ff.Planes(p, q, times)
    x, _ = ff.features(planes.to_planes(vis, 0), planes.to_planes(flagged, True))
    ref = planes.from_planes(ff.logits_numpy(params, x))
    diff = np.abs(rust - ref)[~flagged]
    assert np.quantile(diff, 0.999) <= 1e-4
    assert diff.max() <= 1e-3
    assert np.mean((rust > 0) != (ref > 0)) <= 1e-3


def test_flags_are_independent_of_row_order():
    vis, flagged, p, q, times = problem(seed=5)
    w = ff.flat_weights(ff.init_params(2))
    a = ff.rust_logits(vis, flagged, p, q, times, w)
    order = np.random.default_rng(0).permutation(len(p))
    b = ff.rust_logits(vis[order], flagged[order], p[order], q[order], times[order], w)
    np.testing.assert_array_equal(a[order], b)
