"""C1 closure kernel against an independent NumPy reference (research/c1-closure-arm.md)."""

import numpy as np
import pytest
from rang import core_closure as cc


def layout(nant, ntime, drop=()):
    a1, a2, ti = [], [], []
    for t in range(ntime):
        for i in range(nant):
            for j in range(i + 1, nant):
                if (i, j) in drop:
                    continue
                a1.append(i)
                a2.append(j)
                ti.append(t)
    return np.array(a1), np.array(a2), np.array(ti)


def random_jones(rng, shape, diag=1.0):
    j = rng.normal(size=(*shape, 2, 2)) + 1j * rng.normal(size=(*shape, 2, 2))
    j = 0.2 * j
    j[..., 0, 0] += diag
    j[..., 1, 1] += diag
    return j


def apply(gains, vis, a1, a2):
    """V_pq -> G_p V_pq G_q^H on (row, chan, 2, 2) visibilities."""
    return gains[a1][:, None] @ vis @ np.conj(np.swapaxes(gains[a2][:, None], -1, -2))


def case(
    seed=1,
    nant=7,
    ntime=3,
    nchan=4,
    usable_fraction=0.8,
    dtype=np.complex64,
    diagonal=False,
):
    rng = np.random.default_rng(seed)
    a1, a2, ti = layout(nant, ntime)
    nrow = len(a1)
    model = np.zeros((nrow, nchan, 2, 2), complex)
    model[..., 0, 0] = model[..., 1, 1] = 10 + rng.normal(size=(nrow, nchan))
    gains = random_jones(rng, (nant,))
    if diagonal:  # parallel-hand closures are invariant only under these
        gains[:, 0, 1] = gains[:, 1, 0] = 0
    data = apply(gains, model, a1, a2)
    data += 0.05 * (rng.normal(size=data.shape) + 1j * rng.normal(size=data.shape))
    weights = rng.uniform(0.5, 2.0, size=(nrow, nchan, 4)).astype(np.float32)
    usable = rng.random((nrow, nchan)) < usable_fraction
    return {
        "data": data.reshape(nrow, nchan, 4).astype(dtype),
        "model": model.reshape(nrow, nchan, 4).astype(dtype),
        "weights": weights,
        "usable": usable,
        "antenna1": a1,
        "antenna2": a2,
        "time_index": ti,
        "stations": np.arange(nant),
        "nchan": nchan,
        "ntime": ntime,
    }


def kernel(c, family, min_closures=3, reroute=cc.REROUTE):
    return cc.scores(
        c["data"],
        c["model"],
        c["weights"],
        c["usable"],
        c["antenna1"],
        c["antenna2"],
        c["time_index"],
        c["stations"],
        family,
        min_closures=min_closures,
        reroute=reroute,
    )


def reference(c, reroute=cc.REROUTE):
    return cc.Reference(
        c["data"],
        c["model"],
        c["weights"],
        c["usable"],
        c["antenna1"],
        c["antenna2"],
        c["time_index"],
        c["stations"],
        reroute=reroute,
    )


@pytest.mark.parametrize("family", ["trace", "phase", "logamp"])
def test_kernel_matches_numpy_reference(family):
    c = case()
    out = kernel(c, family)
    ref = reference(c)
    nrow = len(c["antenna1"])
    for row in range(nrow):
        a, b, t = (int(c[k][row]) for k in ("antenna1", "antenna2", "time_index"))
        for ch in range(c["nchan"]):
            if not c["usable"][row, ch]:
                assert out["count"][row, ch] == 0
                assert np.isnan(out["residual"][row, ch])
                continue
            r, v, n = ref.sample(family, t, a, b, ch, c["nchan"], c["ntime"], 3)
            assert out["count"][row, ch] == n
            np.testing.assert_allclose(out["residual"][row, ch], r, rtol=1e-5)
            np.testing.assert_allclose(out["tv"][row, ch], v, rtol=1e-5)


def test_closure_trace_is_gauge_invariant_float64():
    rng = np.random.default_rng(3)
    nant, nchan = 6, 2
    a1, a2, ti = layout(nant, 1)
    nrow = len(a1)
    vis = random_jones(rng, (nrow, nchan), diag=3.0)
    gains = random_jones(rng, (nant,), diag=1.0)
    corrupted = apply(gains, vis, a1, a2)
    model = vis.copy()
    w = np.ones((nrow, nchan, 4))
    ok = np.ones((nrow, nchan), bool)
    clean = cc.Reference(
        vis.reshape(nrow, nchan, 4),
        model.reshape(nrow, nchan, 4),
        w,
        ok,
        a1,
        a2,
        ti,
        range(nant),
    )
    dirty = cc.Reference(
        corrupted.reshape(nrow, nchan, 4),
        model.reshape(nrow, nchan, 4),
        w,
        ok,
        a1,
        a2,
        ti,
        range(nant),
    )
    checked = 0
    # (a, b) reversed and (s, b), (a, d) reversed orientations all occur.
    for a, b in [(0, 1), (1, 0), (4, 2), (5, 3)]:
        for s in range(nant):
            if s in (a, b):
                continue
            for ch in range(nchan):
                x = clean.closure("trace", 0, ch, a, b, s)
                y = dirty.closure("trace", 0, ch, a, b, s)
                # model == clean data, so the clean residual is zero; the
                # corrupted residual must be zero too, to rounding.
                assert abs(x[0][0]) < 1e-12
                assert abs(y[0][0]) < 1e-10
                checked += 1
    assert checked == 4 * (nant - 2) * nchan


def test_phase_invariant_under_diagonal_gains_only():
    c = case(seed=5, usable_fraction=1.0, dtype=np.complex128)
    rng = np.random.default_rng(9)
    nant = len(c["stations"])
    nrow, nchan = c["data"].shape[:2]
    model = c["model"].reshape(nrow, nchan, 2, 2)
    diag = np.zeros((nant, 2, 2), complex)
    diag[:, 0, 0] = np.exp(1j * rng.uniform(-3, 3, nant)) * rng.uniform(0.5, 2, nant)
    diag[:, 1, 1] = np.exp(1j * rng.uniform(-3, 3, nant)) * rng.uniform(0.5, 2, nant)
    full = random_jones(rng, (nant,), diag=1.0)
    full[:, 0, 1] += 0.3
    full[:, 1, 0] -= 0.3j
    a1, a2 = c["antenna1"], c["antenna2"]
    out = {}
    for name, g in (("diagonal", diag), ("full", full)):
        cc_case = dict(c, data=apply(g, model, a1, a2).reshape(nrow, nchan, 4))
        out[name] = {
            fam: kernel(cc_case, fam)["residual"]
            for fam in ("phase", "trace", "logamp")
        }
    # Noise-free data: residuals are rounding under diagonal gains.
    for fam in ("phase", "trace", "logamp"):
        assert np.nanmax(out["diagonal"][fam]) < 1e-4
    # Full gains: the trace stays invariant, phase and amplitude do not.
    assert np.nanmax(out["full"]["trace"]) < 1e-4
    assert np.nanmedian(out["full"]["phase"]) > 1e-3
    assert np.nanmedian(out["full"]["logamp"]) > 1e-3


@pytest.mark.parametrize("family", ["trace", "phase", "logamp"])
def test_planted_baseline_error_is_the_maximum(family):
    c = case(seed=2, nant=9, usable_fraction=1.0, diagonal=True)
    rows = np.flatnonzero((c["antenna1"] == 2) & (c["antenna2"] == 6))
    c["data"][rows, :, 0] *= 1.3 * np.exp(0.4j)
    c["data"][rows, :, 3] *= 0.8 * np.exp(-0.3j)
    out = kernel(c, family)
    labels, pairs = cc.baseline_index(c["antenna1"], c["antenna2"], 9)
    per_baseline = np.array(
        [np.nanmedian(out["residual"][labels == k]) for k in range(len(pairs))]
    )
    assert tuple(pairs[np.argmax(per_baseline)]) == (2, 6)


def test_reroute_recovers_quadrangles_around_a_missing_edge():
    c = case(seed=4, nant=8, usable_fraction=1.0)
    # Make baseline (3, 4) unusable: quadrangles that need it as (s, d) or
    # (a, d) re-route; with reroute=0 they are lost.
    rows = np.flatnonzero((c["antenna1"] == 3) & (c["antenna2"] == 4))
    c["usable"][rows] = False
    with_reroute = kernel(c, "trace", reroute=3)["count"]
    without = kernel(c, "trace", reroute=0)["count"]
    assert (with_reroute >= without).all()
    assert (with_reroute > without).any()
    ref = reference(c, reroute=3)
    row = int(np.flatnonzero((c["antenna1"] == 0) & (c["antenna2"] == 1))[0])
    _, _, n = ref.sample("trace", 0, 0, 1, 0, c["nchan"], c["ntime"], 3)
    assert with_reroute[row, 0] == n


def test_kernel_refuses_bad_inputs():
    c = case()
    with pytest.raises(ValueError, match="two rows"):
        cc.scores(
            np.concatenate([c["data"], c["data"][:1]]),
            np.concatenate([c["model"], c["model"][:1]]),
            np.concatenate([c["weights"], c["weights"][:1]]),
            np.concatenate([c["usable"], c["usable"][:1]]),
            np.r_[c["antenna1"], c["antenna1"][:1]],
            np.r_[c["antenna2"], c["antenna2"][:1]],
            np.r_[c["time_index"], c["time_index"][:1]],
            c["stations"],
            "trace",
        )
    with pytest.raises(ValueError, match="not in the cycle"):
        cc.scores(
            c["data"],
            c["model"],
            c["weights"],
            c["usable"],
            c["antenna1"],
            c["antenna2"],
            c["time_index"],
            c["stations"][:-1],
            "trace",
        )


def test_maps_and_statistics():
    labels = np.array([0, 1, 0, 1])
    time_bin = np.array([0, 0, 1, 1])
    freq_bin = np.array([0, 0, 1])
    values = np.array(
        [[1.0, 3.0, 5.0], [2.0, np.nan, 4.0], [7.0, 7.0, 7.0], [1.0, 1.0, 1.0]]
    )
    mask = np.ones(values.shape, bool)
    mask[2, 2] = False
    m, n = cc.bin_map(values, mask, time_bin, freq_bin, labels, (2, 2, 2), block=3)
    assert m[0, 0, 0] == 2.0 and n[0, 0, 0] == 2
    assert m[0, 0, 1] == 2.0 and n[0, 0, 1] == 1
    assert m[0, 1, 0] == 5.0 and m[0, 1, 1] == 4.0
    assert m[1, 0, 0] == 7.0 and np.isnan(m[1, 1, 0])
    pairs = np.array([[0, 1], [0, 2]])
    ant = cc.antenna_map(m, pairs, 3)
    assert ant[0, 0, 0] == 2.0 and ant[0, 0, 1] == 2.0 and ant[0, 1, 0] == 4.5
    assert cc.spearman([1, 2, 3, 4], [10, 20, 30, 45]) == pytest.approx(1.0)
    assert cc.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert cc.spearman([1, 2], [1, 2]) is None
    np.testing.assert_array_equal(cc.rank([3, 1, 3, 2]), [2.5, 0, 2.5, 1])
    assert cc.r_squared([1, 2, 4, 8], [2, 4, 8, 16]) == pytest.approx(1.0)
    o = cc.overlap([1, 2, 3, 4], [3, 4, 5, 6, 7, 8, 9, 10], 100)
    assert (
        o["both"] == 2
        and o["fraction_of_mask"] == 0.5
        and o["lift"] == pytest.approx(6.25)
    )
    assert o["coincides"]


def test_additive_r_squared_is_one_for_antenna_separable_maps():
    nant = 6
    a1, a2, _ = layout(nant, 1)
    pairs = np.stack([a1, a2], axis=1)
    rng = np.random.default_rng(0)
    level = rng.normal(size=(2, 3, nant))
    m = np.exp(level[..., a1] + level[..., a2])
    assert cc.additive_r_squared(m, pairs, nant) == pytest.approx(1.0)
    noisy = m * np.exp(rng.normal(size=m.shape))
    assert cc.additive_r_squared(noisy, pairs, nant) < 0.9


def test_robust_z_and_top_mask():
    rng = np.random.default_rng(1)
    residual = np.exp(rng.normal(scale=0.1, size=(40, 5))).astype(np.float32)
    residual[3, 2] = 50.0
    labels = np.repeat([0, 1], 20)
    train = np.ones(residual.shape, bool)
    train[0, 0] = False
    z = cc.robust_z(residual, train, labels)
    assert np.isnan(z[0, 0]) and z[3, 2] > 10
    assert (z[train] >= 0).all()
    cells, proposed = cc.top_mask(z, train, 5.0, 0.02)
    assert proposed == 1 and cells.tolist() == [3 * 5 + 2]
    cells, _ = cc.top_mask(z, train, 0.0, 0.02)
    assert len(cells) == int(np.floor(0.02 * train.sum()))
