"""Certified CLEAN through the extension (research/clean-certified-imaging.md)."""

import numpy as np
import pytest
from rang import core_clean

C = 299_792_458.0
SIDE = 32
SCALE_ARCSEC = 20.0


def _scene(seed=3):
    """Random sampling (metres = wavelengths at f = c), two point sources on
    pixel centres and the exact direct-sum visibilities in the gridder's
    convention (pixel (i, j) at l = (i - side/2) dl, m = (j - side/2) dm)."""
    rng = np.random.default_rng(seed)
    nrow = 400
    uvw = np.zeros((nrow, 3))
    uvw[:, :2] = rng.uniform(-3000.0, 3000.0, (nrow, 2))
    freq = np.array([C])
    cell = SCALE_ARCSEC * core_clean.ARCSEC
    truth = {(20, 9): 1.0, (8, 14): -0.4}
    vis = np.zeros((nrow, 1), np.complex128)
    for (i, j), flux in truth.items():
        l, m = (i - SIDE // 2) * cell, (j - SIDE // 2) * cell
        vis[:, 0] += flux * np.exp(-2j * np.pi * (uvw[:, 0] * l + uvw[:, 1] * m))
    weights = rng.uniform(0.5, 1.5, (nrow, 1))
    return uvw, freq, vis, weights, truth


def _run(**kw):
    uvw, freq, vis, weights, truth = _scene()
    settings = {
        "side": SIDE,
        "scale_arcsec": SCALE_ARCSEC,
        "epsilon": 1e-12,
        "wgridding": False,
        "flip_v": False,
        "flip_w": False,
        "threshold": 1e-4,
        "max_components": 2000,
        "max_major": 50,
        "audit": True,
    }
    settings.update(kw)
    return core_clean.certified_clean(uvw, freq, vis, weights, **settings), truth


def test_exact_beam_is_gram_consistent_and_descends():
    out, _truth = _run(rule="mgain", mgain=0.8, floor_iterations=100)
    summary, cycles = out["summary"], out["cycles"]
    assert summary["major_cycles"] == len(cycles) >= 2
    assert summary["f"] == 0.0
    assert summary["ascending_steps"] == 0
    assert summary["q_final"] < 1e-3 * summary["q0"]
    for c in cycles:
        assert abs(c["gap_relative"]) < 1e-8
        assert c["dq_exact"] < 0
    # The brightest model pixel is the bright source.
    assert np.unravel_index(np.argmax(out["model"]), out["model"].shape) == (20, 9)
    assert summary["q_floor"] is not None and 0 <= summary["q_floor"] < summary["q0"]


def test_provable_rule_with_a_patch_never_ascends():
    out, _ = _run(rule="provable", patch=2)
    assert out["summary"]["ascending_steps"] == 0
    assert out["summary"]["f"] > 0
    assert any(abs(c["gap_relative"]) > 1e-8 for c in out["cycles"])
    assert all(c["dq_exact"] <= 0 for c in out["cycles"])


def test_refuses_bad_inputs():
    uvw, freq, vis, weights, _ = _scene()
    with pytest.raises(ValueError):
        core_clean.certified_clean(uvw[:-1], freq, vis, weights, side=SIDE)
    with pytest.raises(ValueError):
        core_clean.certified_clean(uvw, freq, vis, weights, side=SIDE, rule="högbom")
