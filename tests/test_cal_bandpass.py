"""The bandpass B and the chain K, G, B (task C2c, research/c2c-bandpass.md):
per-channel solve with CASA's rules, `fillgaps`, the `B Jones` table, and the
chain driver, on seeded simulated arrays."""

import numpy as np
import pytest
from rang import cal_apply, cal_bandpass
from rang.formats import caltable


def simulate(nant=6, ntime=2, nchan=24, noise=0.0, seed=20261106):
    """`V = B_p M B_q^H` with a per-channel complex bandpass per antenna and
    hand, constant in time."""
    rng = np.random.default_rng(seed)
    b = rng.uniform(0.6, 1.4, (nant, nchan, 2)) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (nant, nchan, 2))
    )
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    a1, a2 = np.tile(a1, ntime), np.tile(a2, ntime)
    tb = np.repeat(np.arange(ntime), nbl)
    nrow = len(a1)
    model = np.zeros((nrow, nchan, 4), complex)
    model[..., 0] = 10 + rng.normal(0, 1, (nrow, nchan))
    model[..., 3] = 9 + rng.normal(0, 1, (nrow, nchan))
    bp, bq = b[a1], b[a2]
    data = model.copy()
    data[..., 0] *= bp[..., 0] * np.conj(bq[..., 0])
    data[..., 3] *= bp[..., 1] * np.conj(bq[..., 1])
    data += noise * (rng.normal(size=data.shape) + 1j * rng.normal(size=data.shape))
    pos = np.zeros((nant, 3))
    pos[:, 0] = np.arange(nant) * 100.0
    return {
        "data": data.astype(np.complex64),
        "model": model.astype(np.complex64),
        "weights": np.ones(data.shape, np.float32),
        "flag": np.zeros(data.shape, bool),
        "flag_row": np.zeros(nrow, bool),
        "a1": a1,
        "a2": a2,
        "tb": tb,
        "nant": nant,
        "b": b,
        "positions": pos,
    }


def run(s, **kw):
    kw.setdefault("positions", s["positions"])
    kw.setdefault("minblperant", 3)
    return cal_bandpass.solve(
        s["data"], s["model"], s["weights"], s["flag"], s["flag_row"], s["a1"],
        s["a2"], s["tb"], nant=s["nant"], **kw,
    )  # fmt: skip


TIGHT = {"stop_fraction": 1.0, "stop_criterion": 1e-12, "max_iterations": 200}


def products(g):
    p, q = np.triu_indices(g.shape[-2], 1)
    return g[..., p, :] * np.conj(g[..., q, :])


def test_noise_free_bandpass_products_are_recovered():
    s = simulate()
    sol = run(s, refant=0, **TIGHT)
    assert not sol.flags.any()
    got = products(sol.gains.astype(complex))  # (t, chan, pair, hand)
    want = products(s["b"].transpose(1, 0, 2))[None]
    assert np.abs(got - want).max() < 1e-5
    # Referenced per channel: the refant's phase is zero.
    assert np.abs(np.angle(sol.gains[:, :, 0])).max() < 1e-6


def test_fillgaps_fills_short_gaps_after_the_solve():
    s = simulate(nchan=24)
    s["flag"][:, 5:7] = True  # a gap of two channels
    s["flag"][:, 12:17] = True  # a gap of five
    fill = run(s, refant=0, fillgaps=3, **TIGHT)
    keep = run(s, refant=0, fillgaps=0, **TIGHT)
    assert keep.flags[:, 5:7].all() and keep.flags[:, 12:17].all()
    assert not fill.flags[:, 5:7].any() and fill.filled[:, 5:7].all()
    assert fill.flags[:, 12:17].all() and not fill.filled[:, 12:17].any()
    # Linear in amplitude and phase between the neighbours (float32).
    g = fill.gains[0, :, 1, 0]
    a = np.abs(g[4]) + (np.abs(g[7]) - np.abs(g[4])) / 3
    assert abs(np.abs(g[5]) - a) < 1e-5


def test_fill_gaps_on_arrays_matches_flags_rule():
    g = np.ones((1, 6, 1, 2), np.complex64)
    f = np.zeros((1, 6, 1, 2), bool)
    f[0, 0] = True  # leading: never filled
    f[0, 2:4] = True
    _, of = cal_bandpass.fill_gaps(g, f, 2)
    assert of[0, 0].all() and not of[0, 2:4].any()
    _, of = cal_bandpass.fill_gaps(g, f, 1)
    assert of[0, 2:4].all()


def test_minsnr_is_per_channel():
    s = simulate(noise=0.2)
    s["weights"][..., 9, :] = 1e-8  # one channel without signal-to-noise
    sol = run(s, refant=0)
    assert sol.flags[:, 9].all()
    assert not sol.flags[:, 8].any()


def test_b_table_applies_back_to_the_model(tmp_path):
    s = simulate(nant=4, nchan=16)
    sol = run(s, refant=0, **TIGHT)
    nchan = s["data"].shape[1]
    freq = 1e9 + 1e6 * np.arange(nchan)
    times = 1000.0 + np.arange(2) * 8.0
    subtables = {
        "ANTENNA": {"NAME": [f"m{a:03d}" for a in range(4)]},
        "SPECTRAL_WINDOW": {"CHAN_FREQ": [freq]},
    }
    table = caltable.from_gains(
        "B", times, list(range(4)), sol.gains.transpose(0, 2, 1, 3),
        sol.flags.transpose(0, 2, 1, 3), subtables=subtables, refant=0,
    )  # fmt: skip
    corrected, flags = cal_apply.apply(
        s["data"], s["flag"], times[s["tb"]], s["a1"], s["a2"], freq, [table],
        interp="nearest",
    )  # fmt: skip
    assert not flags.any()
    par = (0, 3)
    assert np.allclose(corrected[..., par], s["model"][..., par], rtol=2e-5, atol=2e-5)


def test_refant_out_of_range():
    s = simulate(nant=3, ntime=1, nchan=4)
    with pytest.raises(ValueError):
        run(s, refant=3)
