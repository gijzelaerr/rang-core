# SPDX-License-Identifier: GPL-3.0-or-later
"""Bad-input and parity gaps closed by the correctness audit
(research/correctness-audit-2026-11-13.md): each test names the gap it
closes. Synthetic inputs only; no archive, no oracle."""

import numpy as np
import pytest
import test_cal_delay
import test_cal_gain
import test_cal_pol
from rang import cal_pol, core_grid, core_ms_write, core_writeback, fluxstd
from rang.formats import flagversions
from test_cal_gain import run, simulate
from test_w2_commands import make_ms

# -- gain solver (cal_gain._kernel) --------------------------------------------


def test_gain_solve_without_rows_names_the_problem():
    # Was numpy's "zero-size array to reduction operation maximum".
    s = simulate()
    for key in ("data", "model", "weights", "flag"):
        s[key] = s[key][:0]
    for key in ("flag_row", "a1", "a2", "tb"):
        s[key] = s[key][:0]
    with pytest.raises(ValueError, match="no data to solve"):
        run(s)


def test_gain_solve_refuses_per_row_arrays_of_the_wrong_length():
    # On main 30d9412 this input solved without a word: antenna1, antenna2
    # and flag_row one row longer than the data were cut by x[order].
    s = simulate()
    s["a1"] = np.append(s["a1"], 0)
    s["a2"] = np.append(s["a2"], 1)
    s["flag_row"] = np.append(s["flag_row"], False)
    with pytest.raises(ValueError, match="antenna1"):
        run(s)
    s = simulate()
    s["tb"] = s["tb"][:-1]
    with pytest.raises(ValueError, match="time_bin"):
        run(s)


def test_gain_solve_refuses_negative_bins():
    s = simulate()
    s["tb"] = s["tb"] - 1
    with pytest.raises(ValueError, match="negative"):
        run(s)


def test_gain_solve_all_flagged_flags_every_solution():
    s = simulate()
    s["flag"][:] = True
    sol = run(s)
    assert sol.flags.all()


@pytest.mark.parametrize(
    ("solver", "kw", "keys"),
    [
        ("gain", {}, ("gains", "snr", "err", "flags")),
        ("gain", {"calmode": "p"}, ("gains", "snr", "err", "flags")),
        ("gain", {"casa_rules": False}, ("gains", "snr", "err", "flags")),
        ("delay", {}, ("delays", "err", "flags")),
        ("delay", {"kind": "delay_and_offset"}, ("delays", "offsets", "err", "flags")),
    ],
)
def test_nan_cells_solve_as_flagged_cells(solver, kw, keys):
    # A real bug: cal/diag.rs and the delay kernels have no non-finite guard,
    # so one NaN visibility made every solution NaN with its flag clear. Now
    # NaN cells give exactly the solution of the same cells flagged.
    mod = test_cal_gain if solver == "gain" else test_cal_delay
    s = mod.simulate(noise=0.01)
    bad = np.random.default_rng(20261113).random(s["data"].shape[:2]) < 0.05
    nan = {**s, "data": s["data"].copy()}
    nan["data"][bad] = np.nan
    flagged = {**s, "flag": s["flag"].copy()}
    flagged["flag"][bad] = True
    a, b = mod.run(nan, **kw), mod.run(flagged, **kw)
    for key in keys:
        assert np.array_equal(getattr(a, key), getattr(b, key)), key
    assert np.isfinite(a.gains if solver == "gain" else a.delays).all()


def _poisoned(data, seed=3):
    bad = np.random.default_rng(seed).random(data.shape[:2]) < 0.05
    nan = data.copy()
    nan[bad] = np.nan
    flag = np.zeros(data.shape, bool)
    flag[bad] = True
    return nan, flag


def test_nan_cells_in_the_polarisation_solves_act_as_flagged_cells():
    # Df's leakages were all NaN with their flags clear from one NaN
    # visibility; KCROSS differed from the flagged solve. Now exact.
    rng = np.random.default_rng(3)
    nant, ntime, nchan = 6, 4, 64
    a1, a2, t = test_cal_pol._array(nant, ntime)
    freq = 856e6 + 856e6 * (np.arange(nchan) + 0.5) / nchan
    model = test_cal_pol._polarised_model(len(a1), nchan, np.linspace(-1, 1.2, 4)[t])
    data = model.copy()
    data[..., 1] *= np.exp(0.6j)
    data[..., 2] *= np.exp(-0.6j)
    data = data + 0.01 * (
        rng.normal(size=data.shape) + 1j * rng.normal(size=data.shape)
    )
    tb = np.zeros(len(a1), np.int64)
    nan, flag = _poisoned(data)
    loaded = test_cal_pol._loaded
    for solve, key in ((cal_pol.kcross_solve, "delay_ns"), (cal_pol.xf_solve, "x")):
        a = solve(loaded(nan, model, a1, a2, tb, freq, nant))
        b = solve(loaded(data, model, a1, a2, tb, freq, nant, flag=flag))
        assert np.array_equal(getattr(a, key), getattr(b, key)), key
        assert np.array_equal(a.ok, b.ok)
    nant, ntime, nchan = 7, 3, 4
    a1, a2, _t = test_cal_pol._array(nant, ntime)
    d = 0.02 * (
        rng.normal(size=(nant, nchan, 2)) + 1j * rng.normal(size=(nant, nchan, 2))
    )
    model = np.zeros((len(a1), nchan, 4), complex)
    model[..., 0] = model[..., 3] = 5.0
    data = model.copy()
    data[..., 1] += 5 * (d[a1, :, 0] + np.conj(d[a2, :, 1]))
    data[..., 2] += 5 * (d[a1, :, 1] + np.conj(d[a2, :, 0]))
    tb = np.zeros(len(a1), np.int64)
    nan, flag = _poisoned(data)
    ones = np.ones(nchan)
    a = cal_pol.df_solve(loaded(nan, model, a1, a2, tb, ones, nant), refant=3)
    b = cal_pol.df_solve(
        loaded(data, model, a1, a2, tb, ones, nant, flag=flag), refant=3
    )
    assert np.isfinite(a.d).all()
    assert np.array_equal(a.d, b.d) and np.array_equal(a.flags, b.flags)


def test_delay_solve_without_rows_names_the_problem():
    s = test_cal_delay.simulate()
    for key in ("data", "model", "weights", "flag", "flag_row", "a1", "a2", "tb"):
        s[key] = s[key][:0]
    with pytest.raises(ValueError, match="no data to solve"):
        test_cal_delay.run(s)


# -- gridder device -------------------------------------------------------------


def small_grid_inputs(nrow=40, nchan=2):
    rng = np.random.default_rng(1)
    uvw = rng.normal(0, 200, (nrow, 3))
    freq = np.array([1.0e9, 1.1e9])[:nchan]
    data = np.ones((nrow, nchan), np.complex64)
    w = np.ones((nrow, nchan), np.float32)
    return uvw, freq, data, w


def test_wgrid_never_runs_a_gpu_request_on_the_cpu(monkeypatch):
    # Was a silent CPU run, against the module's no-fallback promise.
    uvw, freq, data, w = small_grid_inputs()
    kw = {"width": 32, "height": 32, "scale_arcsec": 10.0, "gridder": "wgrid"}
    with pytest.raises(RuntimeError, match="CPU only"):
        core_grid.invert(uvw, freq, data, w, w, device="gpu", **kw)
    monkeypatch.setenv("RANG_GRIDDER_DEVICE", "gpu")
    with pytest.raises(RuntimeError, match="CPU only"):
        core_grid.invert(uvw, freq, data, w, w, **kw)
    out = core_grid.invert(uvw, freq, data, w, w, device="cpu", **kw)
    assert np.isfinite(out["dirty"]).all()


# -- write-back layout ----------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "value", "words"),
    [
        ("POLARIZATION_ID", -1, "POLARIZATION_ID -1"),
        ("POLARIZATION_ID", 5, "POLARIZATION_ID 5"),
        ("SPECTRAL_WINDOW_ID", -1, "SPECTRAL_WINDOW_ID -1"),
        ("SPECTRAL_WINDOW_ID", 3, "SPECTRAL_WINDOW_ID 3"),
    ],
)
def test_layout_refuses_data_description_ids_out_of_range(
    tmp_path, column, value, words
):
    # A negative id picked the last row through Python indexing; a large one
    # raised a bare IndexError.
    ms = make_ms(tmp_path / "x.ms")
    with core_ms_write.open_table(ms / "DATA_DESCRIPTION", readonly=False) as t:
        t.putcol(column, np.array([value], np.int32))
    with pytest.raises(core_writeback.UnsupportedLayout, match=words):
        core_writeback.layout(ms)


# -- flag versions --------------------------------------------------------------


@pytest.mark.parametrize("name", ["a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a|b"])
def test_flag_version_names_windows_refuses_are_refused_everywhere(tmp_path, name):
    flag = np.zeros((2, 1, 1), bool)
    with pytest.raises(ValueError, match="not allowed"):
        flagversions.save(
            tmp_path / "x.ms", name, flag=flag, flag_row=np.zeros(2, bool)
        )


# -- flux standards -------------------------------------------------------------


def test_manual_flux_refuses_non_positive_frequencies():
    # Was a quiet NaN or inf, where model() raises.
    with pytest.raises(ValueError):
        fluxstd.manual([1e9, 0.0], 1.0, 1.4e9, (0.0, -0.7))
    with pytest.raises(ValueError):
        fluxstd.manual([1e9], 1.0, 0.0, (0.0,))
    got = fluxstd.manual([1.4e9, 2.8e9], 2.0, 1.4e9, (-0.7,))
    assert np.allclose(got, [2.0, 2.0 * 2.0**-0.7], rtol=1e-12)
