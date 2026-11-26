# SPDX-License-Identifier: MIT
"""DD6's helpers (research/dd6-d0.md): the d0 composition, the free-d0 solve
on a seeded noiseless array, and the cycle-0 parity gates on converged
cells."""

import importlib.util
from pathlib import Path

import numpy as np
from rang import cal_gain

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dd6", ROOT / "tools" / "oracles" / "dd6" / "dd6.py"
)
dd6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dd6)


def test_compose_replaces_facet_d0_only():
    idx = np.array([[0, 1], [2, 0]])
    base = np.array([[1.0, 2.0], [3.0, 4.0]])
    d0 = np.array([[10.0, 20.0], [30.0, 40.0]])
    assert np.array_equal(dd6.compose(idx, base, d0), [[10.0, 2.0], [3.0, 40.0]])
    assert dd6.facet_abs_error(idx, base, d0, 3) == [45.0, 18.0, 27.0]


def test_pinned_for():
    assert dd6.pinned_for(True) == []
    assert dd6.pinned_for(False) == [0]


def _simulate(nant=8, ntime=2, nchan=6, ndir=3, seed=20261125):
    rng = np.random.default_rng(seed)
    gains = np.exp(rng.normal(0, 0.05, (ntime, nant, ndir, 2))) * np.exp(
        1j * rng.normal(0, 0.4, (ntime, nant, ndir, 2))
    )
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    a1, a2 = np.tile(a1, ntime), np.tile(a2, ntime)
    tb = np.repeat(np.arange(ntime), nbl)
    nrow = len(a1)
    uv = rng.normal(0, 300, (nrow, 2))
    lm = rng.uniform(-0.02, 0.02, (ndir, 2))
    nu = 1 + 0.05 * np.arange(nchan)
    models = np.zeros((nrow, nchan, ndir, 4), np.complex64)
    data = np.zeros((nrow, nchan, 4), complex)
    for d in range(ndir):
        m = (
            (1.0 / (1 + d)) * np.exp(2j * np.pi * (uv @ lm[d])[:, None] * nu[None])
        ).astype(np.complex64)
        models[:, :, d, 0] = models[:, :, d, 3] = m
        gp, gq = gains[tb, a1, d], gains[tb, a2, d]
        for k, h in ((0, 0), (3, 1)):
            data[..., k] += gp[:, None, h] * m * np.conj(gq[:, None, h])
    return gains, data, models, a1, a2, tb, nant


def test_free_d0_recovers_every_direction_pinned_does_not():
    gains, data, models, a1, a2, tb, nant = _simulate()
    nrow, nchan = data.shape[:2]
    args = (data, models, np.ones((nrow, nchan, 4)), np.zeros((nrow, nchan, 4), bool),
            np.zeros(nrow, bool), a1, a2, tb)  # fmt: skip
    kw = {
        "nant": nant,
        "refant": 0,
        "max_iterations": 400,
        "stop_criterion": 1e-10,
        "stop_fraction": 1.0,
    }
    p, q = np.triu_indices(nant, 1)
    truth = gains[:, p] * np.conj(gains[:, q])
    free = cal_gain.solve_dd(*args, pinned_directions=dd6.pinned_for(True), **kw)
    solved = free.gains[:, 0][:, p] * np.conj(free.gains[:, 0][:, q])
    assert np.max(np.abs(solved - truth) / np.abs(truth)) < 1e-5
    pinned = cal_gain.solve_dd(*args, pinned_directions=dd6.pinned_for(False), **kw)
    assert np.allclose(pinned.gains[:, 0, :, 0], 1.0)  # d0 held at 1, its truth is not


def _gains(seed, shape=(2, 1, 5, 3, 2)):
    rng = np.random.default_rng(seed)
    return np.exp(1j * rng.normal(0, 0.3, shape)) * (1 + 0.1 * rng.normal(size=shape))


def test_parity_gates_read_on_converged_cells():
    gr = _gains(1)
    go = gr.copy()
    flags = np.zeros(gr.shape[:-1], np.int8)
    conv = np.ones(gr.shape[:-1], bool)
    rec = dd6.parity_gates(gr, flags, go, flags, conv, 0.9, 0.9)
    assert rec["parity"] and rec["max_converged"] == 0.0
    # A large difference on one antenna's unconverged cell fails the
    # maximum over unflagged cells but not the gate on converged cells.
    go[0, 0, 3, 1, 0] += 1e-3
    conv[0, 0, 3, 1] = False
    rec = dd6.parity_gates(gr, flags, go, flags, conv, 0.9, 0.9)
    assert rec["parity"] and rec["max_unflagged"] > 1e-4
    # The same difference on a converged cell fails.
    rec = dd6.parity_gates(gr, flags, go, flags, np.ones_like(conv), 0.9, 0.9)
    assert not rec["parity"] and not rec["gains_ok"]
    # Flags and the aggregate fraction are gated too.
    fo = flags.copy()
    fo[1, 0, 2, 2] = 1
    assert not dd6.parity_gates(gr, flags, gr, fo, conv, 0.9, 0.9)["flags_equal"]
    rec = dd6.parity_gates(gr, flags, gr, flags, conv, 0.9, 0.9 + 2e-6)
    assert not rec["fraction_equal"] and not rec["parity"]
