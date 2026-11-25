# SPDX-License-Identifier: MIT
"""DD7's helpers (research/dd7-cause.md): baseline selection, the phase
scramble, the linear-term split across the band, the matched control draw
and the rank correlation."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dd7", ROOT / "tools" / "oracles" / "dd7" / "dd7.py"
)
dd7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dd7)


def test_baseline_mask_either_order():
    a1 = np.array([0, 0, 1, 2, 3])
    a2 = np.array([1, 2, 2, 3, 0])
    m = dd7.baseline_mask(a1, a2, [(1, 0), (0, 3)])
    assert m.tolist() == [True, False, False, False, True]


def test_phase_scramble_keeps_modulus():
    rng = np.random.default_rng(1)
    r = (rng.normal(size=(50, 4, 2)) + 1j * rng.normal(size=(50, 4, 2))).astype(
        np.complex64
    )
    s = dd7.phase_scramble(r, np.random.default_rng(2))
    assert s.dtype == r.dtype
    np.testing.assert_allclose(np.abs(s), np.abs(r), rtol=1e-6)
    assert abs(np.mean(s)) < 0.3


def test_linear_term_recovers_slope_and_is_orthogonal():
    nrow, nchan = 6, 16
    x = np.arange(nchan)
    rng = np.random.default_rng(3)
    a = rng.normal(size=(nrow, 1, 2)) + 1j * rng.normal(size=(nrow, 1, 2))
    b = rng.normal(size=(nrow, 1, 2)) + 1j * rng.normal(size=(nrow, 1, 2))
    z = a + b * x[None, :, None]
    ok = np.ones(z.shape, bool)
    ok[0, :3, 0] = False  # flagged channels
    ok[1, :, 1] = False  # a fully flagged row and hand
    ok[2, 1:, 0] = False  # one channel only: no slope
    lin, const = dd7.linear_term(z, ok)
    # Linear part plus constant part reproduce z exactly where it is linear.
    rec = lin + const
    sel = ok.copy()
    sel[2, :, 0] = False
    np.testing.assert_allclose(rec[sel], z[sel], atol=1e-10)
    assert np.all(lin[~ok] == 0) and np.all(lin[2, :, 0] == 0)
    # Orthogonal to the constant over each row's unflagged channels.
    assert np.abs((np.conj(const) * lin * ok).sum(1)).max() < 1e-9


def test_linear_share_of_noise_is_one_over_n():
    rng = np.random.default_rng(4)
    z = rng.normal(size=(4000, 64, 2)) + 1j * rng.normal(size=(4000, 64, 2))
    ok = np.ones(z.shape, bool)
    lin, _ = dd7.linear_term(z, ok)
    share = (np.abs(lin) ** 2).sum() / (np.abs(z) ** 2).sum()
    assert share == pytest.approx(1 / 64, rel=0.05)


def test_matched_control_share_and_exclusion():
    rng = np.random.default_rng(5)
    w = rng.uniform(0.5, 1.5, 200)
    exclude = np.zeros(200, bool)
    exclude[:20] = True
    target = w[:20].sum() / w.sum()
    pick, share, _ = dd7.matched_control(
        w, exclude, 20, target, np.random.default_rng(6)
    )
    assert len(pick) == 20 and not exclude[pick].any()
    assert abs(share / target - 1) <= dd7.CONTROL_TOL


def test_spearman():
    a = np.arange(10.0)
    assert dd7.spearman(a, a**3) == pytest.approx(1.0)
    assert dd7.spearman(a, -a) == pytest.approx(-1.0)


def test_regen_noise_matches_dd5_draw():
    w = np.full((3, 4, 2), 4.0, np.float32)
    w[0, 0, 0] = 0.0
    n = dd7.regen_noise(w, 0.5)
    rng = np.random.default_rng(dd7.dd5.SEEDS["noise"])
    ref = rng.standard_normal(w.shape + (2,))
    sd = np.sqrt(0.5 / 4.0)
    assert n[0, 0, 0] == 0
    np.testing.assert_allclose(
        n[1, 2, 1], sd * (ref[1, 2, 1, 0] + 1j * ref[1, 2, 1, 1]), rtol=1e-6
    )


def test_matched_control_falls_back_to_nearest_weight():
    w = np.concatenate([np.full(20, 0.1), np.linspace(0.05, 3.0, 180)])
    exclude = np.zeros(200, bool)
    exclude[:20] = True
    target = w[:20].sum() / w.sum()
    pick, share, ndraw = dd7.matched_control(
        w, exclude, 20, target, np.random.default_rng(7), draws=50
    )
    assert ndraw == -1 and len(set(pick)) == 20 and not exclude[pick].any()
    assert abs(share / target - 1) <= dd7.CONTROL_TOL
