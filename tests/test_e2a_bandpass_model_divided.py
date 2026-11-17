# SPDX-License-Identifier: MIT
"""Task e2a-3b-diag (research/e2a-3b-diag.md): `calibrate.bandpass_model_divided`.

A K or G pre-applied in a B solve corrupts the model; with
`calibrate.average_time` and gains that vary inside the B interval,
averaging data and corrupted model separately is not the least-squares
solve. On, B divides by the model first (`cal_gain.model_divided`, CASA's
`divideCorrByModel`): the averaged B equals a NumPy reference of
divide-then-average and moves towards the unaveraged B. Off,
every solve and the stage hash are as before; the chain passes the key to
B only."""

import copy
import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import (
    cal_apply,
    cal_bandpass,
    cal_chain,
    cal_delay,
    cal_gain,
    core_config,
    core_ms,
    core_ms_write,
)
from test_a3_casa_phase_weights import np_divided
from test_e2_average_time import cal_ms, np_average, prepared, unit  # noqa: F401

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


@pytest.fixture(scope="module")
def exact(cal_ms, tmp_path_factory):  # noqa: F811
    """A copy of the calibrator MS whose field-0 DATA is B G(t) K applied
    to the unit model plus complex noise of 0.05, G's phases moved by up to
    1 rad per integration and antenna (a corrupted model that decorrelates
    in the B interval); and those tables."""
    model = unit(cal_ms, 0)
    k = cal_delay.gaincal(
        cal_ms, field_id=0, refant=0, model=model, weight_column="WEIGHT"
    )[0]
    g = cal_gain.gaincal(cal_ms, field_id=0, refant=0, solint="int", gaintable=[k],
                         model=model, minblperant=2, weight_column="WEIGHT")[0]  # fmt: skip
    b = cal_bandpass.bandpass(cal_ms, field_id=0, refant=0, combine="scan", minblperant=2,
                              gaintable=[k, g], model=model, weight_column="WEIGHT")[0]  # fmt: skip
    rng = np.random.default_rng(3)
    g = copy.deepcopy(g)
    g.main["CPARAM"] = [
        np.asarray(c) * np.exp(1j * rng.uniform(-1, 1)).astype(np.complex64)
        for c in g.main["CPARAM"]
    ]
    ms = Path(shutil.copytree(cal_ms, tmp_path_factory.mktemp("exact") / "x.ms"))
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)
    with core_ms_write.open_table(ms, readonly=False) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == 0)
        data = t.getcol("DATA")
        ones = np.zeros((len(rows), len(freq), 4), np.complex64)
        ones[..., 0] = ones[..., 3] = 1
        v, _ = cal_apply.apply(ones, np.zeros(ones.shape, bool), t.getcol("TIME")[rows],
                               t.getcol("ANTENNA1")[rows], t.getcol("ANTENNA2")[rows], freq,
                               [b, k, g], interp="linear", direction="corrupt")  # fmt: skip
        noise = rng.normal(0, 0.05, v.shape) + 1j * rng.normal(0, 0.05, v.shape)
        data[rows] = v + noise.astype(np.complex64)
        t.putcol("DATA", data)
    return ms, model, [k, g], b


def _b(ms, model, tables, **kw):
    return cal_bandpass.bandpass(ms, field_id=0, refant=0, combine="scan", minblperant=2,
                                 gaintable=tables, model=model, weight_column="WEIGHT",
                                 **kw)[0]  # fmt: skip


def _gains(t):
    return np.asarray(t.params), np.asarray(t.flags)


def test_divided_average_equals_the_numpy_reference(exact):
    """B with `average_time` and `model_divided`: the rows prepared (K, G
    corrupt the model), divided by the model (CASA's divideCorrByModel, in
    NumPy), averaged per interval and baseline (the E2 reference), then the
    unchanged solver."""
    ms, model, tables, _ = exact
    fld, arr, _ = prepared(
        ms, 0, "B", model=model, weight_column="WEIGHT", gaintable=tables
    )
    d, m_, w, f = np_divided(arr["data"], arr["model"], arr["weights"], arr["flag"])
    m = fld.meta
    tb, _ = cal_gain.solint_bins(
        m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], "inf", "scan"
    )
    ref, t2, p2, q2, fr = np_average(tb, m["ANTENNA1"], m["ANTENNA2"],
                                     fld.flag_row | fld.auto, d, m_, w, f)  # fmt: skip
    with core_ms.open_table(ms / "ANTENNA") as t:
        positions = t.getcol("POSITION")
    want = cal_gain.solve(ref["data"], ref["model"], ref["weights"], ref["flag"], fr,
                          p2, q2, t2, nant=4, freq_bin=np.arange(16), refant=0,
                          minblperant=2, positions=positions)  # fmt: skip
    got = cal_bandpass.bandpass(ms, field_id=0, refant=0, combine="scan", minblperant=2,
                                gaintable=tables, model=model, weight_column="WEIGHT",
                                average_time=True, model_divided=True)[1]  # fmt: skip
    ok = ~want.flags
    assert ok.any() and np.array_equal(got.flags, want.flags)
    assert np.allclose(got.gains[ok], want.gains[ok], atol=2e-6)


def test_divided_average_moves_towards_the_unaveraged_solve(exact):
    """With noise and a decorrelating corrupted model the separate average
    (the default) and the divided one differ, and the divided one is nearer
    the unaveraged B (on E2-A's subset it equals it to 1e-7,
    research/e2a-3b-diag.md)."""
    ms, model, tables, _ = exact
    plain, pf = _gains(_b(ms, model, tables))
    div, df = _gains(_b(ms, model, tables, average_time=True, model_divided=True))
    sep, sf = _gains(_b(ms, model, tables, average_time=True))
    ok = ~pf & ~df & ~sf
    assert ok.mean() > 0.5
    assert np.median(np.abs(div[ok] - sep[ok])) > 1e-3
    assert np.median(np.abs(div[ok] - plain[ok])) < 0.8 * np.median(
        np.abs(sep[ok] - plain[ok])
    )


def test_divided_without_averaging_is_unchanged(exact):
    ms, model, tables, _ = exact
    a, af = _gains(_b(ms, model, tables))
    d, df = _gains(_b(ms, model, tables, model_divided=True))
    assert np.array_equal(af, df)
    assert np.allclose(a[~af], d[~af], atol=1e-5)


def test_the_key_defaults_off_and_leaves_the_stage_hash():
    raw = {"version": 1, "fields": {"fcal": ["CAL"]},
           "calibrate": {"primary": {"terms": [{"type": "G", "name": "G"}]}}}  # fmt: skip
    config, errors = core_config.resolve(raw)
    assert not errors and config["calibrate"]["bandpass_model_divided"] is False
    before = core_config.stage_hash(config, "calibrate")
    gone = dict(config, calibrate={k: v for k, v in config["calibrate"].items()
                                   if k != "bandpass_model_divided"})  # fmt: skip
    assert core_config.stage_hash(gone, "calibrate") == before
    on = dict(config, calibrate=dict(config["calibrate"], bandpass_model_divided=True))
    assert core_config.stage_hash(on, "calibrate") != before


def test_the_chain_passes_it_to_b_only(monkeypatch, cal_ms):  # noqa: F811
    seen = {}

    def fake(kind):
        def solve(ms, **kw):
            seen[kind] = "model_divided" in kw
            raise StopIteration

        return solve

    monkeypatch.setattr(cal_chain.cal_delay, "gaincal", fake("K"))
    monkeypatch.setattr(cal_chain.cal_gain, "gaincal", fake("G"))
    monkeypatch.setattr(cal_chain.cal_bandpass, "bandpass", fake("B"))
    common = {
        "model_column": "MODEL_DATA",
        "weight_column": None,
        "model_divided": True,
    }
    for kind in ("K", "G", "B"):
        term = {"type": kind, "solint": "inf", "combine": "", "refant": 0,
                "refantmode": "flex", "minsnr": 3.0, "minblperant": 4, "uvrange": "",
                "preapply": [], "interp": [], "max_iterations": 50,
                "stop_criterion": 1e-7, "stop_fraction": 0.99, "model": "column",
                "calmode": "ap", "fillgaps": 0}  # fmt: skip
        with pytest.raises(StopIteration):
            cal_chain._solve_one(cal_ms, term, 0, {}, common)
    assert seen == {"K": False, "G": False, "B": True}


def test_divided_average_equals_unaveraged_when_flags_agree_over_correlations(
    exact, tmp_path
):
    """research/e2a-3b-k.md step 5: the fixture's 5e-3 between the divided
    average and the unaveraged B is the unaveraged kernel's cell rule (a cell
    with any correlation flagged is dropped; the averages are per
    correlation). With FLAG OR-ed over the correlations, as in E2-A's data,
    the two agree."""
    ms, model, tables, _ = exact
    ms2 = Path(shutil.copytree(ms, tmp_path / "y.ms"))
    with core_ms_write.open_table(ms2, readonly=False) as t:
        f = np.asarray(t.getcol("FLAG"), bool)
        t.putcol("FLAG", np.broadcast_to(f.any(-1, keepdims=True), f.shape).copy())
    plain, pf = _gains(_b(ms2, model, tables))
    div, df = _gains(_b(ms2, model, tables, average_time=True, model_divided=True))
    ok = ~pf & ~df
    assert ok.mean() > 0.5 and np.array_equal(pf, df)
    assert np.max(np.abs(div[ok] - plain[ok])) < 1e-5
