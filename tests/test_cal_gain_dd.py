# SPDX-License-Identifier: MIT
"""The direction-dependent gain term (task DD1, research/dd1-facet-gains.md):
`rang.cal_gain.solve_dd` on a seeded noiseless array with three facet
directions."""

import numpy as np
import pytest
from rang import cal_gain


def simulate(nant=10, ntime=2, nchan=6, ndir=3, seed=20261123):
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
    flux = 1.0 / (1 + np.arange(ndir))
    models = np.zeros((nrow, nchan, ndir, 4), np.complex64)
    data = np.zeros((nrow, nchan, 4), complex)
    for d in range(ndir):
        phase = 2 * np.pi * (uv @ lm[d])[:, None] * nu[None]
        m = (flux[d] * np.exp(1j * phase)).astype(np.complex64)
        models[:, :, d, 0] = models[:, :, d, 3] = m
        gp, gq = gains[tb, a1, d], gains[tb, a2, d]
        for k, (h1, h2) in ((0, (0, 0)), (3, (1, 1))):
            data[..., k] += gp[:, None, h1] * m * np.conj(gq[:, None, h2])
    return gains, data, models, a1, a2, tb, nant


def test_solve_dd_recovers_noiseless_products():
    gains, data, models, a1, a2, tb, nant = simulate()
    nrow, nchan = data.shape[:2]
    sol = cal_gain.solve_dd(
        data, models, np.ones((nrow, nchan, 4)), np.zeros((nrow, nchan, 4), bool),
        np.zeros(nrow, bool), a1, a2, tb, nant=nant, refant=0,
        max_iterations=300, stop_criterion=1e-10, stop_fraction=1.0,
    )  # fmt: skip
    assert sol.gains.shape == (2, 1, nant, 3, 2)
    assert not sol.flags.any()
    p, q = np.triu_indices(nant, 1)
    solved = sol.gains[:, 0][:, p] * np.conj(sol.gains[:, 0][:, q])
    truth = gains[:, p] * np.conj(gains[:, q])
    assert np.max(np.abs(solved - truth) / np.abs(truth)) < 1e-5
    # Referenced per direction: antenna 0 has zero phase in every direction.
    assert np.allclose(np.angle(sol.gains[:, 0, 0]), 0, atol=1e-12)


def test_solve_dd_pinned_and_shape_errors():
    _, data, models, a1, a2, tb, nant = simulate(ndir=2)
    nrow, nchan = data.shape[:2]
    args = (
        np.ones((nrow, nchan, 4)), np.zeros((nrow, nchan, 4), bool),
        np.zeros(nrow, bool), a1, a2, tb,
    )  # fmt: skip
    sol = cal_gain.solve_dd(
        data, models, *args, nant=nant, refant=None, pinned_directions=[0],
        max_iterations=5,
    )  # fmt: skip
    assert np.all(sol.gains[..., 0, :] == 1)
    with pytest.raises(ValueError):
        cal_gain.solve_dd(data, models[:, :, :, :2], *args, nant=nant)
    with pytest.raises(ValueError):
        cal_gain.solve_dd(data, models, *args, nant=nant, pinned_directions=[2])


def test_solve_dd_phase_is_unit_modulus_and_referenced():
    _, data, models, a1, a2, tb, nant = simulate()
    nrow, nchan = data.shape[:2]
    for last in (True, False):
        sol = cal_gain.solve_dd(
            data, models, np.ones((nrow, nchan, 4)), np.zeros((nrow, nchan, 4), bool),
            np.zeros(nrow, bool), a1, a2, tb, nant=nant, refant=0, calmode="p",
            phase_last_direction_gain=last, max_iterations=50,
        )  # fmt: skip
        assert np.allclose(np.abs(sol.gains), 1, atol=1e-12)
        assert np.allclose(np.angle(sol.gains[:, 0, 0]), 0, atol=1e-12)
