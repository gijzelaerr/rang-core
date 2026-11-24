# SPDX-License-Identifier: MIT
"""DD4 gate S's tolerance (research/dd4-eso137.md section 5, DD3 section 4):
2 % only when the component lists first differ through a tie or a
near-threshold choice of the shared rule; any other gate L failure keeps the
frozen 0.1 %."""

import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dd4", ROOT / "tools" / "oracles" / "dd4" / "dd4.py"
)
dd4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dd4)

STOP = 0.02
LEVEL = dd4.dd3.GAIN * STOP


def test_equal_lists_are_not_up_to_the_rule():
    c = {(1, 1): 0.5, (2, 3): 0.1}
    assert not dd4.up_to_rule(c, dict(c), STOP)


def test_near_threshold_extra_component():
    cr = {(1, 1): 0.5, (7, 7): LEVEL * (1 + 5e-5)}
    co = {(1, 1): 0.5}
    assert dd4.up_to_rule(cr, co, STOP)


def test_tie_between_two_pixels():
    cr = {(1, 1): 0.5, (4, 4): 0.0300000}
    co = {(1, 1): 0.5, (4, 5): 0.0300001}
    assert dd4.up_to_rule(cr, co, STOP)


def test_genuine_difference_is_not_up_to_the_rule():
    cr = {(1, 1): 0.5, (4, 4): 0.03}
    co = {(1, 1): 0.5, (4, 5): 0.05}
    assert not dd4.up_to_rule(cr, co, STOP)
    # a flux mismatch well above the stop level
    assert not dd4.up_to_rule({(1, 1): 0.5}, {(1, 1): 0.6}, STOP)


def _cycle(d, comps, gains, residual, stop):
    d.mkdir(parents=True)
    keys = sorted(comps)
    np.savez(d / "components.npz", y=np.array([k[0] for k in keys], int),
             x=np.array([k[1] for k in keys], int), flux=np.array([comps[k] for k in keys]))  # fmt: skip
    np.savez(d / "gains.npz", gains=gains, flags=np.zeros(gains.shape[:-1], np.int8))
    np.save(d / "residual.npy", residual)
    np.save(d / "model.npy", np.zeros(residual.shape))
    (d / "info.json").write_text(json.dumps({"hogbom": {"stop": stop}}))


def _tolerance(tmp_path, comps_o, gain_offset):
    n = 4
    gains = np.ones((2, 1, n, 2, 2), complex)
    res = np.zeros((8, 8))
    res[3, 3] = 1.0
    ctx = {
        "c": {"ant_names": [f"a{i}" for i in range(n)]},
        "interior": np.ones((8, 8), bool),
    }
    comps_r = {(1, 1): 0.5}
    for k in range(dd4.NCYCLE + 1):
        _cycle(tmp_path / "R" / f"cycle-{k}", comps_r, gains, res, STOP)
        _cycle(tmp_path / "O" / f"cycle-{k}", comps_o, gains + gain_offset, res, STOP)
    dd4.measures = lambda run, ctx, arm, psf, sigma: {
        "offaxis_rms": {"d1": 1.0},
        "dynamic_range": 1.0,
    }
    dd4.restoring_beam = lambda psf: 1.0
    np.save(tmp_path / "psf.npy", np.zeros((16, 16)))
    for k in range(dd4.NCYCLE + 1):
        _cycle(tmp_path / "DI" / f"cycle-{k}", comps_r, gains, res, STOP)
    dd4.score(tmp_path, ctx=ctx)
    return json.loads((tmp_path / "score.json").read_text())


def test_score_relaxes_only_up_to_the_rule(tmp_path):
    near = {(1, 1): 0.5, (6, 6): LEVEL}
    rec = _tolerance(tmp_path / "a", near, 0.0)
    assert rec["L_first_fail"] == 0 and rec["L_parity_up_to_rule"]
    assert rec["S"]["tolerance"] == 0.02


def test_score_keeps_frozen_tolerance_on_gain_failure(tmp_path):
    rec = _tolerance(tmp_path / "b", {(1, 1): 0.5}, 1e-3)
    assert rec["L_first_fail"] == 0 and not rec["L_parity_up_to_rule"]
    assert rec["S"]["tolerance"] == 0.001
