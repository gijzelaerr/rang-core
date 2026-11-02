"""The F1 adjoint against finite differences on a tiny scan (research/f1-tv-flagger.md)."""

import numpy as np
import pytest

pytest.importorskip("jax")

from rang import core
from rang import tvflag_adjoint as ta
from rang.core_policy import axis_weights, gain_tv, polar_gauge


def scan(nant=6, ndump=8, nchan=64, seed=3):
    rng = np.random.default_rng(seed)
    p, q = np.triu_indices(nant, 1)
    a1 = np.tile(p, ndump).astype(np.uint32)
    a2 = np.tile(q, ndump).astype(np.uint32)
    time_bin = (np.repeat(np.arange(ndump), len(p)) // 2).astype(np.uint32)
    freq_bin = (np.arange(nchan) // 16).astype(np.uint32)
    gains = np.tile(np.eye(2, dtype=complex), (nant, 1, 1))
    gains[:, 0, 0] *= np.exp(1j * rng.uniform(-1, 1, nant))
    gains[:, 1, 1] *= 1 + 0.05 * rng.normal(size=nant)
    model = np.zeros((len(a1), nchan, 4), np.complex64)
    model[..., 0], model[..., 3] = 10, 10
    m = model.reshape(len(a1), nchan, 2, 2)
    vis = gains[a1][:, None] @ m @ np.conj(np.swapaxes(gains[a2], -1, -2))[:, None]
    vis = vis + 0.2 * (rng.normal(size=vis.shape) + 1j * rng.normal(size=vis.shape))
    data = vis.reshape(len(a1), nchan, 4).astype(np.complex64)
    return (
        data,
        model,
        np.full(data.shape, 25.0, np.float32),
        a1,
        a2,
        time_bin,
        freq_bin,
    )


def solve(data, model, weights, a1, a2, tb, fb, nant=6):
    flag = np.zeros(data.shape, bool)
    return core.solve_complex(
        data,
        weights,
        flag,
        np.zeros(len(a1), bool),
        a1,
        a2,
        tb,
        fb,
        ntime_bins=int(tb.max()) + 1,
        nfreq_bins=int(fb.max()) + 1,
        nant=nant,
        model=model,
        max_iterations=5000,
        stop_criterion=1e-13,
        stop_fraction=1.0,
        options="anderson=3",
    )


@pytest.fixture(scope="module")
def problem():
    ta.enable_x64()
    data, model, weights, a1, a2, tb, fb = scan()
    solution = solve(data, model, weights, a1, a2, tb, fb)
    x, valid, raw = ta.sanitize(solution.gains, solution.flags)
    axes = (np.arange(4.0), np.arange(4.0))
    scale = float(np.median(np.linalg.norm(solution.gains[raw], axis=(-1, -2))))
    support = ta.make_support(
        valid, axis_weights(axes[0]), axis_weights(axes[1]), scale
    )
    cells = ta.make_cells(
        data,
        model,
        weights,
        np.ones(data.shape[:2], bool),
        a1,
        a2,
        tb,
        fb,
        (4, 4),
        gain_valid=valid,
        chunk=1 << 14,
    )
    operator = ta.Operator(cells, x, valid)
    gradient = ta.tv_gradient(x, support)
    lam, residual, _ = ta.minres(operator, gradient, iterations=100)
    s = operator.cell_saliency(lam)[0]
    return locals()


def test_jax_tv_equals_rust_tv(problem):
    aligned, valid = polar_gauge(problem["solution"].gains, problem["raw"])
    axes = problem["axes"]
    rust = gain_tv(aligned, valid, *axes, scale=problem["scale"])["total"]
    assert ta.tv(problem["x"], problem["support"]) == pytest.approx(rust, rel=1e-12)


def test_fixed_point_and_gauge(problem):
    assert problem["residual"].max() < 1e-6
    assert np.abs(problem["operator"].stationarity()).max() < 1e-6
    # The polar-gauge TV does not see a right-multiplied unitary.
    gains = ta.to_complex(problem["x"])
    rotated = gains @ np.array([[0.6, 0.8j], [0.8j, 0.6]])
    value = ta.tv(ta.to_real(rotated), problem["support"])
    assert value == pytest.approx(ta.tv(problem["x"], problem["support"]), rel=1e-10)


def test_homogeneity(problem):
    cells, s = problem["cells"], problem["s"]
    key = problem["tb"][cells.rows].astype(np.int64) * 4 + problem["fb"][cells.channels]
    total = np.bincount(key, s)
    assert np.abs(total).max() <= 1e-6 * np.bincount(key, np.abs(s)).max()


def test_finite_differences(problem):
    cells, s = problem["cells"], problem["s"]
    data, model, weights = problem["data"], problem["model"], problem["weights"]
    a1, a2, tb, fb = problem["a1"], problem["a2"], problem["tb"], problem["fb"]
    rng = np.random.default_rng(1)
    picks = rng.choice(np.flatnonzero(np.abs(s) > np.quantile(np.abs(s), 0.5)), 6)
    for i in picks:
        r, c = cells.rows[i], cells.channels[i]
        values = []
        for sign in (1, -1):
            w = weights.copy()
            w[r, c] *= 1 + sign * 0.01
            solution = solve(data, model, w, a1, a2, tb, fb)
            x = ta.sanitize(solution.gains, solution.flags)[0]
            values.append(ta.tv(x, problem["support"]))
        assert (values[0] - values[1]) / 0.02 == pytest.approx(s[i], rel=0.05)


def test_dense_adjoint_matches_minres(problem):
    dense = ta.DenseAdjoint(problem["cells"], problem["x"])
    lam, residual = dense.solve(problem["gradient"])
    assert residual.max() < 1e-6
    s = problem["operator"].cell_saliency(lam)[0]
    error = np.linalg.norm(s - problem["s"]) / np.linalg.norm(s)
    assert error < 1e-5
