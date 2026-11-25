# SPDX-License-Identifier: MIT
"""DD8's helpers (research/dd8-offaxis.md): the held-out draw, the clustered
standard error, the per-row held-out score and the entry parser."""

import importlib.util
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dd8", ROOT / "tools" / "oracles" / "dd8" / "dd8.py"
)
dd8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dd8)


def layout(nant=12, seed=0):
    b1, b2 = np.triu_indices(nant, 1)
    rng = np.random.default_rng(seed)
    length = rng.uniform(10, 8000, len(b1))
    return b1, b2, length


def test_draw_heldout_stratified_no_bad_covers_antennas():
    b1, b2, length = layout(20)
    bad = np.zeros(len(b1), bool)
    bad[::7] = True
    pick, seed, counts = dd8.draw_heldout(length, bad, b1, b2, 8801, 0.10)
    assert not bad[pick].any()
    assert len(np.unique(pick)) == len(pick)
    lb = np.digitize(length, dd8.LENGTH_BINS) - 1
    for i, (pool, n) in enumerate(counts):
        assert pool == int(((lb == i) & ~bad).sum())
        assert n == round(0.10 * pool)
        assert int((lb[pick] == i).sum()) == n
    assert np.isin(np.arange(20), np.union1d(b1[pick], b2[pick])).all()
    assert seed >= 8801
    again = dd8.draw_heldout(length, bad, b1, b2, 8801, 0.10)
    assert np.array_equal(again[0], pick)


def test_draw_heldout_raises_when_coverage_impossible():
    b1, b2, length = layout(30)
    bad = np.zeros(len(b1), bool)
    try:
        dd8.draw_heldout(length, bad, b1, b2, 1, fraction=0.001, tries=3)
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")


def test_clustered_ratio_and_se():
    rng = np.random.default_rng(3)
    n = rng.integers(50, 100, 40).astype(float)
    d = rng.normal(0.2, 1.0, 40) * n
    r, se = dd8.clustered(d, n)
    assert math.isclose(r, d.sum() / n.sum())
    m = len(n)
    ref = math.sqrt(m / (m - 1) * ((d - r * n) ** 2).sum()) / n.sum()
    assert math.isclose(se, ref)
    r0, _ = dd8.clustered(np.append(d, 5.0), np.append(n, 0.0))  # empty cluster ignored
    assert math.isclose(r0, r)


def test_reading_threshold():
    assert dd8.reading(0.31, 0.1, "a", "b", "c") == "a"
    assert dd8.reading(-0.31, 0.1, "a", "b", "c") == "b"
    assert dd8.reading(0.29, 0.1, "a", "b", "c") == "c"


def synthetic(rows=400, chans=8, ndir=3, seed=5):
    rng = np.random.default_rng(seed)
    V = rng.normal(size=(rows, chans, ndir)) + 1j * rng.normal(size=(rows, chans, ndir))
    gp = np.exp(
        0.1 * rng.normal(size=(rows, ndir, 2)) + 0.5j * rng.normal(size=(rows, ndir, 2))
    )
    gq = np.exp(
        0.1 * rng.normal(size=(rows, ndir, 2)) + 0.5j * rng.normal(size=(rows, ndir, 2))
    )
    P = gp[:, None] * V[..., None] * np.conj(gq[:, None])
    W = rng.uniform(0.5, 2.0, (rows, chans, 2))
    OK = rng.uniform(size=(rows, chans, 2)) > 0.1
    return V, gp, gq, P.sum(2), W, OK


def test_row_sums_exact_model_is_zero_and_unit_direction_is_its_power():
    V, gp, gq, D, W, OK = synthetic()
    k = 0.5
    s, sf, n = dd8.row_sums(D, W, OK, V, gp, gq, k)
    np.testing.assert_allclose(s, 0.0, atol=1e-18)
    assert np.array_equal(n, OK.sum((1, 2)))
    P = gp[:, None] * V[..., None] * np.conj(gq[:, None])
    for f in range(V.shape[2]):
        e = P[:, :, f, :] - V[:, :, f, None]
        ref = (np.where(OK, W / (2 * k), 0) * np.abs(e) ** 2).sum((1, 2))
        np.testing.assert_allclose(sf[f], ref, rtol=1e-10)


def test_row_sums_noise_gives_unit_h():
    V, gp, gq, D, W, OK = synthetic(rows=4000, seed=7)
    k = 0.53
    rng = np.random.default_rng(8)
    sd = np.sqrt(k / W)
    noise = sd * (rng.standard_normal(W.shape) + 1j * rng.standard_normal(W.shape))
    s, _, n = dd8.row_sums(D + noise, W, OK, V, gp, gq, k)
    assert abs(s.sum() / n.sum() - 1.0) < 0.01


def test_parse_entry_windows_paths():
    name, model, gains, ti = dd8.parse_entry(
        "RH-MF=D:/r/models/RM.npy:D:/r/grid/RH-MF.npz:16"
    )
    assert (name, model, gains, ti) == (
        "RH-MF",
        "D:/r/models/RM.npy",
        "D:/r/grid/RH-MF.npz",
        16,
    )
    assert dd8.parse_entry("u=D:/r/sky.npy:unit") == ("u", "D:/r/sky.npy", "unit", 4)
    assert dd8.parse_entry("t=/tmp/sky.npy:truth") == ("t", "/tmp/sky.npy", "truth", 4)
