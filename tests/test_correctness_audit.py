# SPDX-License-Identifier: GPL-3.0-or-later
"""Bad-input and parity gaps closed by the correctness audit
(research/correctness-audit-2026-11-13.md): each test names the gap it
closes. Synthetic inputs only; no archive, no oracle."""

import numpy as np
import pytest
from rang import core_grid, core_ms_write, core_writeback, fluxstd
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
    # Was a silent truncation of antenna1 through x[order].
    s = simulate()
    s["a1"] = np.append(s["a1"], 0)
    with pytest.raises(ValueError):
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


def test_gain_solve_nan_cells_equal_flagged_cells():
    # solve.rs skips non-finite visibilities; the result must be the one of
    # the same cells flagged.
    s = simulate(noise=0.01)
    rng = np.random.default_rng(20261113)
    bad = rng.random(s["data"].shape[:2]) < 0.05
    nan = {**s, "data": s["data"].copy()}
    nan["data"][bad] = np.nan
    flagged = {**s, "flag": s["flag"].copy()}
    flagged["flag"][bad] = True
    a, b = run(nan), run(flagged)
    assert np.array_equal(a.flags, b.flags)
    ok = ~a.flags
    assert np.allclose(a.gains[ok], b.gains[ok], rtol=0, atol=1e-6)


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
