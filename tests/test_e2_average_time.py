"""E2: `calibrate.average_time`, CASA's time pre-averaging within each
solution interval for K, G, B, F, Gpol, KCROSS, Xf and Df
(`rang.cal_chunks.Average`, `load_averaged`). Off, every solve and the stage
hash are as before; on, a solve equals a NumPy reference of the averaged
solve (rows prepared per row, then averaged per interval, baseline, channel
and correlation), chunked or not; E2's configurations pass the memory
preflight at 8 GiB on their metadata-only MSs."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import (
    cal_bandpass,
    cal_chain,
    cal_chunks,
    cal_delay,
    cal_fluxscale,
    cal_gain,
    cal_pol,
    core_chunks,
    core_config,
    core_ms,
    core_ms_write,
)
from rang import core_pipeline as pipe
from test_c2e_calibrate import calibrator_ms
from test_c6w_polwire import _with_feed

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "results" / "e2-acceptance-scripts"
PREFLIGHT = Path(r"D:\rang\outputs\e2-20261110-10-preflight")


def budget(cells, nrows=480):
    return core_chunks.ChainBudget(
        chunk_bytes=core_chunks.CHAIN_ROW_BYTES * nrows
        + cells * core_chunks.CELL_BYTES["chain"]
    )


@pytest.fixture(scope="module")
def cal_ms(tmp_path_factory):
    """The C2e calibrator MS with random weights (W1's FLAG and FLAG_ROW
    stay) and one integration of CAL wholly flagged."""
    ms = calibrator_ms(tmp_path_factory.mktemp("e2avg") / "x.ms", seed=611)
    rng = np.random.default_rng(612)
    with core_ms_write.open_table(ms, readonly=False) as t:
        w = t.getcol("WEIGHT")
        t.putcol("WEIGHT", rng.uniform(0.5, 2.0, w.shape).astype(w.dtype))
        flag = t.getcol("FLAG")
        flag[30:36] = True
        t.putcol("FLAG", flag)
    return ms


def unit(ms, field, stokes=(1.0, 0.0, 0.0, 0.0)):
    nrow, nchan = cal_fluxscale._field_rows(ms, field, 0)
    return cal_fluxscale.smodel_view(nrow, nchan, stokes)


def np_average(tb, a1, a2, skip, data, model, weights, flag):
    """The reference: per (interval, ANTENNA1, ANTENNA2) of the cross rows,
    in that order, the weighted means of the unflagged cells of rows not
    skipped; a cell without weight flagged."""
    keys = sorted({(int(t), int(p), int(q)) for t, p, q in zip(tb, a1, a2) if p != q})
    shape = (len(keys), *data.shape[1:])
    out = {
        "data": np.zeros(shape, np.complex64),
        "model": np.zeros(shape, np.complex64),
        "weights": np.zeros(shape, np.float32),
        "flag": np.ones(shape, bool),
    }
    row_flag = np.ones(len(keys), bool)
    for i, (t, p, q) in enumerate(keys):
        rows = np.flatnonzero((tb == t) & (a1 == p) & (a2 == q))
        used = ~np.asarray(flag[rows], bool) & ~skip[rows][:, None, None]
        w = np.where(used, np.asarray(weights[rows], float), 0.0)
        sw = w.sum(0)
        ok = sw > 0
        d = (w * np.where(used, data[rows], 0)).sum(0)
        m = (w * np.where(used, np.asarray(model)[rows], 0)).sum(0)
        out["data"][i] = np.where(ok, d / np.where(ok, sw, 1), 0)
        out["model"][i] = np.where(ok, m / np.where(ok, sw, 1), 0)
        out["weights"][i] = sw
        out["flag"][i] = ~ok
        row_flag[i] = skip[rows].all()
    k = np.array(keys).reshape(-1, 3)
    return out, k[:, 0], k[:, 1], k[:, 2], row_flag


def prepared(ms, field_id, solved, *, model, weight_column, gaintable=(), uvrange=""):
    """`rang.cal_gain._Field`'s per-row arrays of a whole field."""
    with core_ms.open_table(ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == field_id)
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)
    tables = list(gaintable)
    fld = cal_gain._Field(
        ms, rows, data_column="DATA", model=model, model_column="MODEL_DATA",
        weight_column=weight_column, sigma_column="SIGMA", tables=tables,
        interp="linear", nant=4, field_id=field_id, solved=solved, freq=freq,
        uvrange=uvrange,
    )  # fmt: skip
    cols = cal_gain._ms_columns(ms, fld.cells, rows)
    arr = fld.prepare(np.arange(len(rows)), cols)
    return fld, arr, freq


# -- off: nothing changes -----------------------------------------------------------


def test_off_is_the_unaveraged_solve(cal_ms):
    common = {"field_id": 0, "refant": 0, "weight_column": "WEIGHT",
              "model": unit(cal_ms, 0)}  # fmt: skip
    k0 = cal_delay.gaincal(cal_ms, **common)
    k1 = cal_delay.gaincal(cal_ms, average_time=False, **common)
    assert cal_chain._sha(k0[0]) == cal_chain._sha(k1[0])
    g0 = cal_gain.gaincal(
        cal_ms, solint="int", minblperant=2, gaintable=[k0[0]], **common
    )
    g1 = cal_gain.gaincal(cal_ms, solint="int", minblperant=2, gaintable=[k0[0]],
                          average_time=False, **common)  # fmt: skip
    assert cal_chain._sha(g0[0]) == cal_chain._sha(g1[0])


def test_the_key_at_its_default_leaves_the_stage_hash(tmp_path):
    raw = {"version": 1, "fields": {"fcal": ["CAL"]},
           "calibrate": {"primary": {"terms": [{"type": "G", "name": "G"}]}}}  # fmt: skip
    config, errors = core_config.resolve(raw)
    assert not errors and config["calibrate"]["average_time"] is False
    before = core_config.stage_hash(config, "calibrate")
    gone = dict(config, calibrate={k: v for k, v in config["calibrate"].items()
                                   if k != "average_time"})  # fmt: skip
    assert core_config.stage_hash(gone, "calibrate") == before
    on = dict(config, calibrate=dict(config["calibrate"], average_time=True))
    assert core_config.stage_hash(on, "calibrate") != before


def test_the_key_is_refused_with_a_complex_term():
    raw = {"version": 1, "fields": {"fcal": ["CAL"]},
           "calibrate": {"average_time": True,
                         "primary": {"terms": [{"type": "complex"}]}}}  # fmt: skip
    config, errors = core_config.resolve(raw)
    assert not errors
    paths = [r.path for r in core_config.refusals(config, ["calibrate"])]
    assert "calibrate.average_time" in paths


# -- on: the NumPy reference --------------------------------------------------------


def test_average_rows_and_sources():
    tb = np.array([0, 0, 0, 1, 1, 0, 1])
    a1 = np.array([0, 1, 0, 0, 2, 0, 2])
    a2 = np.array([1, 2, 0, 1, 2, 1, 2])  # rows 2 and 4 are autocorrelations
    skip = np.array([False, True, True, False, True, False, False])
    avg = cal_chunks.Average(tb, a1, a2, skip)
    assert avg.time_bin.tolist() == [0, 0, 1]
    assert list(zip(avg.antenna1, avg.antenna2)) == [(0, 1), (1, 2), (0, 1)]
    assert avg.inverse.tolist() == [0, 1, -1, 2, -1, 0, -1]
    assert avg.flag_row.tolist() == [False, True, False]
    src, loc = avg.sources(np.array([0, 2]))
    assert src.tolist() == [0, 3, 5] and loc.tolist() == [0, 1, 0]


@pytest.mark.parametrize("solint", ["inf", "int", 30.0])
def test_g_and_k_equal_the_numpy_reference(cal_ms, solint):
    model = unit(cal_ms, 0)
    k = cal_delay.gaincal(
        cal_ms, field_id=0, refant=0, model=model, weight_column="WEIGHT"
    )
    fld, arr, freq = prepared(cal_ms, 0, "G", model=model, weight_column="WEIGHT",
                              gaintable=[k[0]], uvrange=">200")  # fmt: skip
    m = fld.meta
    tb, keys = cal_gain.solint_bins(m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], solint)
    ref, t2, p2, q2, fr = np_average(tb, m["ANTENNA1"], m["ANTENNA2"],
                                     fld.flag_row | fld.auto, arr["data"],
                                     arr["model"], arr["weights"], arr["flag"])  # fmt: skip
    with core_ms.open_table(cal_ms / "ANTENNA") as t:
        positions = t.getcol("POSITION")
    want = cal_gain.solve(ref["data"], ref["model"], ref["weights"], ref["flag"], fr,
                          p2, q2, t2, nant=4, refant=0, minblperant=2,
                          positions=positions)  # fmt: skip
    kw = {"field_id": 0, "solint": solint, "refant": 0, "minblperant": 2,
          "gaintable": [k[0]], "model": model, "weight_column": "WEIGHT",
          "uvrange": ">200"}  # fmt: skip
    for b in (None, budget(1600)):
        _, got, info = cal_gain.gaincal(cal_ms, average_time=True, budget=b, **kw)
        assert np.array_equal(got.flags, want.flags)
        ok = ~want.flags
        assert np.allclose(got.gains[ok], want.gains[ok], rtol=0, atol=2e-6)
        assert len(info["intervals"]) == len(keys)
    # The solution times are the unaveraged solve's.
    plain = cal_gain.gaincal(cal_ms, **kw)[0]
    avg = cal_gain.gaincal(cal_ms, average_time=True, **kw)[0]
    assert plain.main["TIME"] == avg.main["TIME"]
    assert plain.main["INTERVAL"] == avg.main["INTERVAL"]
    # K: the delays of the averaged rows.
    fld, arr, _ = prepared(cal_ms, 0, "K", model=model, weight_column="WEIGHT")
    ref, t2, p2, q2, fr = np_average(tb, m["ANTENNA1"], m["ANTENNA2"],
                                     fld.flag_row | fld.auto, arr["data"],
                                     arr["model"], arr["weights"], arr["flag"])  # fmt: skip
    want = cal_delay.solve(ref["data"], ref["model"], ref["weights"], ref["flag"], fr,
                           p2, q2, t2, nant=4, chan_freq=freq, refant=0)  # fmt: skip
    for b in (None, budget(1600)):
        _, got, _ = cal_delay.gaincal(cal_ms, field_id=0, solint=solint, refant=0,
                                      model=model, weight_column="WEIGHT",
                                      average_time=True, budget=b)  # fmt: skip
        assert np.array_equal(got.flags, want.flags)
        assert np.allclose(got.delays, want.delays, rtol=0, atol=1e-5)  # ns


def test_one_row_per_interval_averages_to_itself(cal_ms):
    """solint int: one row per baseline and interval, so the averaged solve
    is the unaveraged one up to the rounding of w d / w."""
    kw = {"field_id": 0, "solint": "int", "refant": 0, "minblperant": 2,
          "model": unit(cal_ms, 0), "weight_column": "WEIGHT"}  # fmt: skip
    one = cal_gain.gaincal(cal_ms, **kw)[1]
    avg = cal_gain.gaincal(cal_ms, average_time=True, **kw)[1]
    assert np.array_equal(one.flags, avg.flags)
    assert np.allclose(one.gains[~one.flags], avg.gains[~one.flags], atol=1e-6)


def test_b_and_f_average_chunked_or_not(cal_ms):
    model = unit(cal_ms, 0)
    k = cal_delay.gaincal(
        cal_ms, field_id=0, refant=0, model=model, weight_column="WEIGHT"
    )
    g = cal_gain.gaincal(cal_ms, field_id=0, refant=0, gaintable=[k[0]], model=model,
                         minblperant=2, weight_column="WEIGHT")  # fmt: skip
    fld, arr, _ = prepared(cal_ms, 0, "B", model=model, weight_column="WEIGHT",
                           gaintable=[k[0], g[0]])  # fmt: skip
    m = fld.meta
    tb, _ = cal_gain.solint_bins(
        m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], "inf", "scan"
    )
    ref, t2, p2, q2, fr = np_average(tb, m["ANTENNA1"], m["ANTENNA2"],
                                     fld.flag_row | fld.auto, arr["data"],
                                     arr["model"], arr["weights"], arr["flag"])  # fmt: skip
    with core_ms.open_table(cal_ms / "ANTENNA") as t:
        positions = t.getcol("POSITION")
    want = cal_gain.solve(ref["data"], ref["model"], ref["weights"], ref["flag"], fr,
                          p2, q2, t2, nant=4, freq_bin=np.arange(16), refant=0,
                          minblperant=2, positions=positions)  # fmt: skip
    kw = {"field_id": 0, "refant": 0, "combine": "scan", "minblperant": 2,
          "gaintable": [k[0], g[0]], "model": model, "weight_column": "WEIGHT"}  # fmt: skip
    # 24 cells per channel of the averaged interval: one channel per chunk.
    for b in (None, budget(2 * 24 + 16 * 4 * 6)):
        _, got, _ = cal_bandpass.bandpass(cal_ms, average_time=True, budget=b, **kw)
        ok = ~want.flags
        assert np.array_equal(got.flags, want.flags)
        assert np.allclose(got.gains[ok], want.gains[ok], atol=2e-6)
    f = {"solint": "inf", "refant": 0, "minblperant": 2, "gaintable": [k[0]],
         "weight_column": "WEIGHT"}  # fmt: skip
    one = cal_fluxscale.bootstrap(cal_ms, g[0], [1], average_time=True, **f)
    chunked = cal_fluxscale.bootstrap(cal_ms, g[0], [1], average_time=True,
                                      budget=budget(1600), **f)  # fmt: skip
    plain = cal_fluxscale.bootstrap(cal_ms, g[0], [1], **f)
    for got in (one, chunked):
        a = np.array(got[2].main["CPARAM"])
        b = np.array(one[2].main["CPARAM"])
        assert np.allclose(a, b, atol=2e-6)
    # The averaged F is near the unaveraged one (a different estimator).
    a = np.array(one[0].main["CPARAM"])
    b = np.array(plain[0].main["CPARAM"])
    assert np.allclose(np.abs(a), np.abs(b), atol=1e-2)


@pytest.fixture(scope="module")
def pol_ms(cal_ms, tmp_path_factory):
    pytest.importorskip("astropy")
    ms = Path(shutil.copytree(cal_ms, tmp_path_factory.mktemp("pol") / "x.ms"))
    return _with_feed(ms)


def _averaged_loaded(ld):
    """`ld` (a whole-field `rang.cal_pol.Loaded`) averaged by the reference."""
    import dataclasses

    ref, t2, p2, q2, fr = np_average(
        ld.time_bin, ld.cols["ANTENNA1"], ld.cols["ANTENNA2"], ld.flag_row,
        ld.data, ld.model, ld.weights, ld.flag,
    )  # fmt: skip
    return dataclasses.replace(
        ld, data=ref["data"], model=ref["model"], weights=ref["weights"],
        flag=ref["flag"], flag_row=fr, time_bin=t2,
        cols={"ANTENNA1": p2, "ANTENNA2": q2},
    )  # fmt: skip


def test_polarisation_terms_equal_the_numpy_reference(pol_ms):
    """The model is rotated by P per row before the averaging."""
    k = cal_delay.gaincal(pol_ms, field_id=0, refant=0, model=unit(pol_ms, 0),
                          weight_column="WEIGHT")  # fmt: skip
    polarised = unit(pol_ms, 1, (1.0, 0.05, 0.08, 0.0))
    common = {"field_id": 1, "gaintable": [k[0]], "model": polarised,
              "weight_column": "WEIGHT"}  # fmt: skip
    for solint, combine in (("inf", ""), ("int", "")):
        ld = cal_pol.load(
            pol_ms, solved="Kcross", solint=solint, combine=combine, **common
        )
        want = cal_pol.kcross_solve(_averaged_loaded(ld))
        for b in (None, budget(2400)):
            _, got, _ = cal_pol.kcross(pol_ms, solint=solint, combine=combine,
                                       average_time=True, budget=b, **common)  # fmt: skip
            assert np.array_equal(got.ok, want.ok)
            assert np.allclose(got.delay_ns, want.delay_ns, atol=1e-6)
    ld = cal_pol.load(pol_ms, solved="Xf", combine="scan", **common)
    want = cal_pol.xf_solve(_averaged_loaded(ld))
    for b in (None, budget(400)):
        _, got, _ = cal_pol.xf(pol_ms, combine="scan", average_time=True, budget=b,
                               **common)  # fmt: skip
        assert np.array_equal(got.ok, want.ok)
        assert np.allclose(got.x[want.ok], want.x[want.ok], atol=2e-6)
    # Gpol: G on the P-rotated model, averaged.
    gk = {"field_id": 1, "gaintable": [k[0]], "weight_column": "WEIGHT", "refant": 0,
          "minblperant": 2, "solint": "inf"}  # fmt: skip
    a = cal_pol.gpol(pol_ms, model=polarised, average_time=True, **gk)[1]
    b = cal_pol.gpol(pol_ms, model=polarised, average_time=True, budget=budget(1600),
                     **gk)[1]  # fmt: skip
    assert np.array_equal(a.flags, b.flags)
    assert np.allclose(a.gains[~a.flags], b.gains[~a.flags], atol=2e-6)
    # Df on the unpolarised field (degenerate) and on the polarised one.
    for field, model in ((0, unit(pol_ms, 0)), (1, polarised)):
        kw = {"field_id": field, "gaintable": [k[0]], "model": model, "combine": "scan",
              "weight_column": "WEIGHT"}  # fmt: skip
        ld = cal_pol.load(pol_ms, solved="Df", **kw)
        want = cal_pol.df_solve(_averaged_loaded(ld), minblperant=2, minsnr=0.0)
        for b in (None, budget(400)):
            _, got, _ = cal_pol.df(pol_ms, minblperant=2, minsnr=0.0,
                                   average_time=True, budget=b, **kw)  # fmt: skip
            assert got.gauge_fixed == want.gauge_fixed == (field == 0)
            assert np.array_equal(got.flags, want.flags)
            ok = ~want.flags
            assert np.allclose(got.d[ok], want.d[ok], atol=2e-6)


# -- the memory plan ----------------------------------------------------------------


def test_the_plan_uses_the_averaged_size():
    """An inf interval of 20 times x 6 baselines x 16 channels: 7680 cells
    unaveraged, 384 averaged."""
    tb = np.zeros(120, np.int64)
    a1 = np.tile([0, 0, 0, 1, 1, 2], 20)
    a2 = np.tile([1, 2, 3, 2, 3, 3], 20)
    avg = cal_chunks.Average(tb, a1, a2, np.zeros(120, bool))
    b = budget(2000, nrows=240)
    with pytest.raises(core_chunks.MemoryLimitError, match="GiB"):
        cal_chunks.plan(tb, 16, 4, b, per_channel=False)
    chunks, block = cal_chunks.plan(avg.time_bin, 16, 4, b, per_channel=False,
                                    average=avg)  # fmt: skip
    assert len(chunks) == 1 and len(chunks[0].pos) == 6 and block >= 1


E2_CASES = [("e2a", "e2a-meta.ms"), ("e2b", "e2b-meta.ms")]


@pytest.mark.parametrize(("name", "ms"), E2_CASES)
def test_e2_configurations_fit_8_gib_with_the_key(name, ms):
    path = PREFLIGHT / ms
    if not path.exists():
        pytest.skip(f"{path} is not on this host")
    raw = core_config.load(SCRIPTS / f"{name}.yaml")
    info = pipe.inspect_ms(path)
    config = core_config.validate(raw, ["calibrate"])
    assert config["data"]["memory_limit_gb"] in (None, 8, 8.0)
    with pytest.raises(pipe.Refused, match="GiB"):
        pipe.preflight(config, info, ["calibrate"])
    raw["calibrate"]["average_time"] = True
    config = core_config.validate(raw, ["calibrate"])
    pipe.preflight(config, info, ["calibrate"])


def test_selfcal_average_time_gives_the_gains_back(tmp_path):
    """selfcal.average_time (task E2): Sp and Sa on rows averaged within each
    interval recover the gains of a noiseless perfect model, as the unaveraged
    solve does; Sd refuses the key; the config key leaves the stage hash alone
    at its default."""
    import importlib.util

    from rang import cal_selfcal, core_config

    spec = importlib.util.spec_from_file_location(
        "c5t", Path(__file__).with_name("test_c5_selfcal.py")
    )
    c5 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c5)
    for kind, term in (
        ("pa", {"type": "Sa", "solint": 3}),
        ("pa", {"type": "Sp", "solint": 3}),
    ):
        ms, _g, row_block = c5.make_ms(tmp_path / f"{term['type']}.ms", kind)
        rows = np.arange(len(row_block))
        kw = {"rows": rows, "field_id": 0, "input_column": "DATA",
              "model_column": "MODEL_TRUE", "weight_column": "WEIGHT"}  # fmt: skip
        plain = cal_selfcal.solve(ms, {"name": "S", **term}, **kw)
        avg = cal_selfcal.solve(ms, {"name": "S", **term}, average_time=True, **kw)
        assert np.array_equal(avg.time_bin, plain.time_bin)
        p, ok = c5.products(avg.gains, avg.flags)
        q, _ = c5.products(plain.gains, plain.flags)
        assert ok.all() and np.max(np.abs(p - q) / np.abs(q)) < 1e-5
    with pytest.raises(ValueError, match="Sp and Sa"):
        cal_selfcal.solve(
            ms, {"name": "S", "type": "Sd", "solint": 3}, average_time=True, **kw
        )
    base, _ = core_config.resolve({"version": 1})
    on, _ = core_config.resolve({"version": 1, "selfcal": {"average_time": True}})
    assert base["selfcal"]["average_time"] is False
    assert core_config.stage_hash(base, "selfcal") != core_config.stage_hash(
        on, "selfcal"
    )
