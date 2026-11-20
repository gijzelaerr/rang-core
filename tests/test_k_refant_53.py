# SPDX-License-Identifier: GPL-3.0-or-later
"""Issue #53 (research/k-refant-53.md, gate G2, noise-free): a K solve keeps
the antennas that have no unflagged baseline to the reference antenna.
Case A: every baseline to the first refant flagged in one interval (the
interval is referenced to the next refant). Case B: one antenna's baseline
to the refant flagged (it is solved through its other baselines). Where the
refant's baselines are present, flex equals CASA's strict rule bit for bit."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "tcd53", ROOT / "tests/test_cal_delay.py"
)
tcd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tcd)

TIGHT = {"stop_fraction": 1.0, "stop_criterion": 1e-12, "max_iterations": 200}
KINDS = ["delay", "delay_and_offset"]


def case(scale, a=True, b=True, seed=53):
    # Relative delays up to 2 x scale; 64 channels over 856 MHz repeat every
    # 74.8 ns, so the +-50 ns case uses 256 (299 ns), clear of aliasing.
    nchan = 64 if scale <= 10 else 256
    s = tcd.simulate(nant=12, ntime=4, nchan=nchan, scale=scale, seed=seed)
    a1, a2, tb = s["a1"], s["a2"], s["tb"]
    if a:  # case A: interval 1 loses every baseline to antenna 0
        s["flag_row"][(tb == 1) & ((a1 == 0) | (a2 == 0))] = True
    if b:  # case B: antenna 5 loses its baseline to antenna 0 in interval 2
        s["flag_row"][(tb == 2) & (a1 == 0) & (a2 == 5)] = True
    return s


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("scale", [8.0, 50.0])
def test_flex_solves_what_casa_flags(kind, scale):
    s = case(scale)
    sol = tcd.run(s, refant=[0, 1], kind=kind, **TIGHT)
    assert sol.refant_used.tolist() == [0, 1, 0, 0]
    for t in range(4):
        r = sol.refant_used[t]
        want = s["tau"][t] - s["tau"][t, r]
        live = np.ones(12, bool)
        if t == 1:
            live[0] = False  # antenna 0 has no data in interval 1
        assert not sol.flags[t, 0, live].any(), (
            t,
            np.flatnonzero(sol.flags[t, 0].any(-1)),
        )
        assert np.abs(sol.delays[t, 0, live] - want[live]).max() < 1e-6, t
        assert np.all(sol.delays[t, 0, r] == 0)
    assert sol.flags[1, 0, 0].all()


@pytest.mark.parametrize("kind", KINDS)
def test_strict_keeps_casas_rule(kind):
    s = case(8.0)
    sol = tcd.run(s, refant=[0, 1], kind=kind, refantmode="strict", **TIGHT)
    assert sol.refant_used.tolist() == [0, 0, 0, 0]
    assert sol.flags[1, 0, 1:].all() and not sol.flags[1, 0, 0].any()
    assert sol.flags[2, 0, 5].all()


def test_flex_without_a_listed_refant_takes_the_best_connected_antenna():
    s = case(8.0, b=False)
    sol = tcd.run(s, refant=[0], **TIGHT)
    r = int(sol.refant_used[1])
    assert r != 0 and not sol.flags[1, 0, 1:].any()
    want = s["tau"][1] - s["tau"][1, r]
    assert np.abs(sol.delays[1, 0, 1:] - want[1:]).max() < 1e-6


@pytest.mark.parametrize("kind", KINDS)
def test_flex_equals_strict_bit_for_bit_with_the_refant_present(kind):
    s = tcd.simulate(nant=12, ntime=4, nchan=64, noise=0.3, seed=7)
    rng = np.random.default_rng(1)
    away = (s["a1"] != 0) & (s["a2"] != 0)
    s["flag_row"][away & (rng.uniform(size=len(away)) < 0.2)] = True
    s["flag"][..., :] |= rng.uniform(size=s["flag"].shape[:2])[..., None] < 0.05
    f = tcd.run(s, refant=[0, 1], kind=kind)
    g = tcd.run(s, refant=[0, 1], kind=kind, refantmode="strict")
    assert np.array_equal(f.delays, g.delays) and np.array_equal(f.flags, g.flags)
    assert np.array_equal(f.err, g.err) and np.array_equal(f.offsets, g.offsets)
    assert f.iterations == g.iterations and f.refant_used.tolist() == [0, 0, 0, 0]


def test_refantmode_is_checked():
    with pytest.raises(ValueError, match="refantmode"):
        tcd.run(case(8.0), refant=0, refantmode="any")
