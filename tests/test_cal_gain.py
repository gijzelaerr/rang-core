"""The gain term G (task C2a, research/c2a-gain.md): kernel, CASA's rules,
intervals, uvrange and the table route, on seeded simulated arrays."""

import numpy as np
import pytest
from rang import cal_apply, cal_gain
from rang.formats import caltable


def simulate(nant=6, ntime=4, nchan=8, noise=0.0, seed=20261106, phase_only=False):
    rng = np.random.default_rng(seed)
    amp = (
        np.ones((ntime, nant, 2))
        if phase_only
        else rng.uniform(0.7, 1.3, (ntime, nant, 2))
    )
    gains = amp * np.exp(1j * rng.uniform(-np.pi, np.pi, (ntime, nant, 2)))
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    a1, a2 = np.tile(a1, ntime), np.tile(a2, ntime)
    tb = np.repeat(np.arange(ntime), nbl)
    nrow = len(a1)
    model = np.zeros((nrow, nchan, 4), complex)
    model[..., 0] = 10 + rng.normal(0, 1, (nrow, nchan))
    model[..., 3] = 9 + rng.normal(0, 1, (nrow, nchan))
    model[..., 1] = 0.1 * rng.normal(0, 1, (nrow, nchan))
    model[..., 2] = 0.1 * rng.normal(0, 1, (nrow, nchan))
    gp, gq = gains[tb, a1], gains[tb, a2]
    data = model.copy()
    data[..., 0] *= gp[:, None, 0] * np.conj(gq[:, None, 0])
    data[..., 3] *= gp[:, None, 1] * np.conj(gq[:, None, 1])
    data[..., 1] *= gp[:, None, 0] * np.conj(gq[:, None, 1])
    data[..., 2] *= gp[:, None, 1] * np.conj(gq[:, None, 0])
    data += noise * (rng.normal(size=data.shape) + 1j * rng.normal(size=data.shape))
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
        "truth": gains,
        "positions": np.c_[np.arange(nant) * 10.0, np.zeros(nant), np.zeros(nant)],
    }


def run(s, **kw):
    kw.setdefault("positions", s["positions"])
    return cal_gain.solve(
        s["data"], s["model"], s["weights"], s["flag"], s["flag_row"],
        s["a1"], s["a2"], s["tb"], nant=s["nant"], **kw,
    )  # fmt: skip


def product_error(sol, truth):
    prod, ok, pairs = cal_gain.baseline_products(sol.gains, sol.flags)
    p, q = np.array(pairs).T
    want = truth[:, None, p, :] * np.conj(truth[:, None, q, :])
    return np.max(np.abs(prod - want)[ok]), ok


@pytest.mark.parametrize("calmode", ["ap", "p"])
def test_noise_free_products_and_refant_phase(calmode):
    s = simulate(phase_only=calmode == "p")
    sol = run(s, calmode=calmode, refant=2, minblperant=4, stop_fraction=1.0,
              stop_criterion=1e-10, max_iterations=200)  # fmt: skip
    err, ok = product_error(sol, s["truth"])
    assert ok.all() and err < 1e-5
    assert np.all(np.abs(np.angle(sol.gains[:, 0, 2])) < 1e-6)
    assert list(sol.refant_used) == [2] * 4


def test_quartical_referencing_without_casa_rules():
    s = simulate()
    sol = run(s, casa_rules=False, refant=1)
    assert np.all(np.abs(np.angle(sol.gains[:, 0, 1])) < 1e-9)
    assert sol.blperant_ok.all()


def test_minblperant_flags_an_antenna_and_its_data():
    s = simulate(nant=5)
    # Antenna 4 keeps only its baseline to 0 at interval 1.
    rows = (s["tb"] == 1) & ((s["a1"] == 4) | (s["a2"] == 4)) & (s["a1"] != 0)
    s["flag_row"][rows] = True
    sol = run(s, minblperant=2)
    assert not sol.blperant_ok[1, 0, 4] and sol.blperant_ok[1, 0, :4].all()
    assert sol.flags[1, 0, 4].all() and not sol.flags[0, 0, 4].any()


def test_minsnr_flags_low_snr_hands():
    s = simulate(nant=5, nchan=4, noise=3.0)
    sol = run(s, minsnr=1e9)
    assert sol.flags.all()
    sol = run(s, minsnr=0.0)
    assert not sol.flags.any()
    assert np.all(sol.snr > 0)


def test_flex_uses_an_alternate_and_strict_flags():
    s = simulate(nant=5)
    s["flag_row"][(s["tb"] == 2) & ((s["a1"] == 0) | (s["a2"] == 0))] = True
    flex = run(s, refant=0, refantmode="flex", minblperant=3)
    assert list(flex.refant_used) == [0, 0, 1, 1] and flex.used_alternate_refant
    strict = run(s, refant=0, refantmode="strict", minblperant=3)
    assert list(strict.refant_used) == [0, 0, -1, 0]
    assert strict.flags[2].all()


def test_solint_bins():
    time = np.r_[np.arange(10) * 8.0, 200 + np.arange(5) * 8.0]
    scan = np.r_[np.ones(10, int), 2 * np.ones(5, int)]
    fld = np.zeros(15, int)
    tb, keys = cal_gain.solint_bins(time, scan, fld, "inf")
    assert list(tb) == [0] * 10 + [1] * 5 and len(keys) == 2
    tb, _ = cal_gain.solint_bins(time, scan, fld, "inf", combine="scan")
    assert set(tb) == {0}
    tb, _ = cal_gain.solint_bins(time, scan, fld, "int")
    assert list(tb) == list(range(15))
    tb, _ = cal_gain.solint_bins(time, scan, fld, "20s")
    assert list(tb[:10]) == [0, 0, 0, 1, 1, 2, 2, 2, 3, 3] and list(tb[10:]) == [
        4,
        4,
        4,
        5,
        5,
    ]
    assert cal_gain.parse_solint("2min") == 120.0
    with pytest.raises(ValueError):
        cal_gain.parse_solint("10ch")


def test_uvrange():
    uvw = np.array([[100.0, 0, 0], [0, 200.0, 5], [30.0, 40.0, 0]])
    assert list(cal_gain.uvrange_keep(uvw, ">150")) == [False, True, False]
    assert list(cal_gain.uvrange_keep(uvw, "<60m")) == [False, False, True]
    assert list(cal_gain.uvrange_keep(uvw, "50~100")) == [True, False, True]
    assert cal_gain.uvrange_keep(uvw, "").all()
    with pytest.raises(ValueError):
        cal_gain.uvrange_keep(uvw, ">1klambda")


def test_table_applies_back_to_the_model(tmp_path):
    """The solved G written as a CASA table and applied by `rang.cal_apply`
    turns the data into the model (noise-free)."""
    s = simulate(nant=4, ntime=3, nchan=4)
    sol = run(s, refant=0, minblperant=3, stop_fraction=1.0, stop_criterion=1e-10,
              max_iterations=200)  # fmt: skip
    times = 1000.0 + np.arange(3) * 8.0
    subtables = {
        "ANTENNA": {"NAME": [f"m{a:03d}" for a in range(4)]},
        "SPECTRAL_WINDOW": {"CHAN_FREQ": [np.array([1.4e9])]},
    }
    table = caltable.from_gains(
        "G", times, list(range(4)), sol.gains[:, 0, :, None, :], sol.flags[:, 0, :, None, :],
        subtables=subtables,
    )  # fmt: skip
    freq = 1.4e9 + np.arange(4) * 1e6
    corrected, flags = cal_apply.apply(
        s["data"],
        s["flag"],
        times[s["tb"]],
        s["a1"],
        s["a2"],
        freq,
        [table],
        interp="nearest",
    )
    assert not flags.any()
    par = (0, 3)
    assert np.allclose(corrected[..., par], s["model"][..., par], rtol=1e-5, atol=1e-5)
