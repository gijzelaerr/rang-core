"""W3b (research/w3b-chainchunks.md): the K, G, B, A, F and polarisation
terms read their fields in chunks of whole solution intervals and give the
one-call result bit for bit; their stop test is replayed from the counted
kernels, Df's gauge test is streamed exactly, the A step flags in blocks of
baselines, P's angles come from a table per unique time. The comparisons on
O-CASA's slice, A1, poldx and the whole-array set are
`tools/oracles/w3b/run.sh`."""

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
    core_flag,
    core_ms,
    core_ms_write,
)
from rang import core_pipeline as pipe
from test_c2e_calibrate import CONFIG, calibrator_ms
from test_c6w_polwire import _with_feed
from test_w2_commands import STRATEGY, cli

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


def budget(cells, rows=None, nrows=240):
    """A `ChainBudget` holding `cells` cells per chunk of a field of up to
    `nrows` rows."""
    return core_chunks.ChainBudget(
        chunk_bytes=core_chunks.CHAIN_ROW_BYTES * nrows
        + cells * core_chunks.CELL_BYTES["chain"],
        chunk_rows=rows,
    )


def same(a, b):
    """Two `(CalTable, solution, ...)` results with equal tables and
    iterations."""
    assert cal_chain._sha(a[0]) == cal_chain._sha(b[0])
    assert a[0].keywords == b[0].keywords
    for key in ("iterations", "converged_fraction", "used_alternate_refant"):
        if hasattr(a[1], key):
            assert getattr(a[1], key) == getattr(b[1], key), key


@pytest.fixture(scope="module")
def cal_ms(tmp_path_factory):
    ms = calibrator_ms(tmp_path_factory.mktemp("w3b") / "x.ms")
    # One integration of CAL wholly flagged: a flagged interval.
    with core_ms_write.open_table(ms, readonly=False) as t:
        flag = t.getcol("FLAG")
        flag[30:36] = True
        t.putcol("FLAG", flag)
    return ms


def unit(ms, field, stokes=(1.0, 0.0, 0.0, 0.0)):
    nrow, nchan = cal_fluxscale._field_rows(ms, field, 0)
    return cal_fluxscale.smodel_view(nrow, nchan, stokes)


# -- the counted kernels and the replay --------------------------------------------


def test_the_counted_kernels_reproduce_the_stop():
    rng = np.random.default_rng(3)
    nrow, nchan, nant = 60, 8, 4
    pairs = [(p, q) for p in range(nant) for q in range(p + 1, nant)]
    a1 = np.array([p for p, _ in pairs] * 10)
    a2 = np.array([q for _, q in pairs] * 10)
    g = np.exp(1j * rng.uniform(-1, 1, (nant, 2)))
    data = np.zeros((nrow, nchan, 4), np.complex64)
    data[..., 0] = (g[a1, 0] * np.conj(g[a2, 0]))[:, None]
    data[..., 3] = (g[a1, 1] * np.conj(g[a2, 1]))[:, None]
    data += 0.05 * rng.standard_normal(data.shape)
    tb = np.arange(nrow) // 6
    kw = {"nant": nant, "freq_bin": None, "calmode": "ap", "refants": [0], "minblperant": 2,
              "casa_rules": True, "max_iterations": 30, "stop_criterion": 1e-6}  # fmt: skip
    one = cal_gain._kernel(data, 1, 1, False, np.zeros(nrow, bool), a1, a2, tb,
                           stop_fraction=0.99, **kw)  # fmt: skip
    counts, error, ngains = cal_gain._kernel(
        data, 1, 1, False, np.zeros(nrow, bool), a1, a2, tb, stop_fraction=2.0,
        trace=True, **kw,
    )  # fmt: skip
    assert error is None and len(counts) == 30 and ngains == 10 * nant
    converged, flagged = counts[one["iterations"] - 1]
    assert converged / (ngains - flagged) == one["fraction"]


@pytest.mark.parametrize("stop", [0.5, 0.99, 1.0])
def test_replayed_chunked_k_g_b_equal_one_call(cal_ms, stop):
    """Stops early (0.5), at the default, and runs to the maximum (1.0)."""
    common = {"field_id": 0, "refant": 0, "weight_column": "WEIGHT", "model": unit(cal_ms, 0),
                  "stop_fraction": stop}  # fmt: skip
    # One `int` interval is 6 rows x 16 channels x 4 = 384 cells, an `inf`
    # one 7680 (a scan).
    for solint, sizes in (("int", (400, 1000)), ("inf", (8000,))):
        for kind in ("delay_and_offset", "delay"):
            one = cal_delay.gaincal(cal_ms, solint=solint, kind=kind, **common)
            for b in [budget(s) for s in sizes] + [budget(10_000, rows=7)]:
                same(one, cal_delay.gaincal(cal_ms, solint=solint, kind=kind,
                                            budget=b, **common))  # fmt: skip
    k = cal_delay.gaincal(cal_ms, solint="inf", **common)
    for calmode in ("ap", "p"):
        one = cal_gain.gaincal(cal_ms, solint="int", calmode=calmode,
                               gaintable=[k[0]], minblperant=2, **common)  # fmt: skip
        chunked = cal_gain.gaincal(cal_ms, solint="int", calmode=calmode,
                                   gaintable=[k[0]], minblperant=2, budget=budget(400),
                                   **common)  # fmt: skip
        same(one, chunked)
    g = cal_gain.gaincal(
        cal_ms, solint="int", gaintable=[k[0]], minblperant=2, **common
    )
    one = cal_bandpass.bandpass(cal_ms, combine="scan", fillgaps=2, minblperant=2,
                                gaintable=[k[0], g[0]], **common)  # fmt: skip
    # B's interval is CAL's 120 rows: one channel is 480 cells.
    for b in (budget(2000), budget(10_000, rows=7)):
        chunked = cal_bandpass.bandpass(cal_ms, combine="scan", fillgaps=2,
                                        minblperant=2, gaintable=[k[0], g[0]],
                                        budget=b, **common)  # fmt: skip
        same(one, chunked)


def test_f_and_the_unit_model_chunked_equal_one_call(cal_ms):
    k = cal_delay.gaincal(
        cal_ms, field_id=0, refant=0, model=unit(cal_ms, 0), weight_column="WEIGHT"
    )
    g = cal_gain.gaincal(cal_ms, field_id=0, refant=0, gaintable=[k[0]],
                         model=unit(cal_ms, 0), minblperant=2, weight_column="WEIGHT")  # fmt: skip
    kw = {
        "solint": "int",
        "refant": 0,
        "minblperant": 2,
        "gaintable": [k[0]],
        "weight_column": "WEIGHT",
    }
    one = cal_fluxscale.bootstrap(cal_ms, g[0], [1], **kw)
    chunked = cal_fluxscale.bootstrap(cal_ms, g[0], [1], budget=budget(400), **kw)
    assert cal_chain._sha(one[0]) == cal_chain._sha(chunked[0])
    assert cal_chain._sha(one[2]) == cal_chain._sha(chunked[2])


def test_a_unit_too_large_is_refused_naming_the_gib(cal_ms):
    with pytest.raises(core_chunks.MemoryLimitError, match="GiB"):
        cal_gain.gaincal(cal_ms, field_id=0, refant=0, model=unit(cal_ms, 0),
                         solint="inf", budget=budget(100), weight_column="WEIGHT")  # fmt: skip
    # B's smallest unit is one channel of the interval: it still runs.
    one = cal_bandpass.bandpass(cal_ms, field_id=0, refant=0, model=unit(cal_ms, 0),
                                combine="scan", minblperant=2, weight_column="WEIGHT")  # fmt: skip
    small = cal_bandpass.bandpass(cal_ms, field_id=0, refant=0, model=unit(cal_ms, 0),
                                  combine="scan", minblperant=2, weight_column="WEIGHT",
                                  budget=budget(2 * 120 * 4 + 64))  # fmt: skip
    same(one, small)


def test_replayed_raises_where_the_one_call_solve_raises():
    def run(chunk, max_iterations, stop_fraction, trace):
        if trace:
            if chunk == "b":
                return np.array([[0, 0], [1, 0]]), (2, "boom"), 4
            return np.array([[0, 0], [1, 0], [2, 0], [3, 0]]), None, 4
        return max_iterations

    # The summed fraction reaches 2/8 at the second iteration; the error of
    # chunk b comes at the third, so the stop at 0.25 is before it ...
    results, replay = cal_chunks.replayed(["a", "b"], run, max_iterations=4,
                                          stop_fraction=0.25)  # fmt: skip
    assert results == [2, 2] and replay == (2, 0.25)
    # ... and a stop never reached before the error raises it.
    with pytest.raises(ValueError, match="boom"):
        cal_chunks.replayed(["a", "b"], run, max_iterations=4, stop_fraction=0.9)


# -- the polarisation terms ---------------------------------------------------------


@pytest.fixture(scope="module")
def pol_ms(cal_ms, tmp_path_factory):
    pytest.importorskip("astropy")
    ms = Path(shutil.copytree(cal_ms, tmp_path_factory.mktemp("pol") / "x.ms"))
    return _with_feed(ms)


def test_polarisation_terms_chunked_equal_one_call(pol_ms):
    k = cal_delay.gaincal(
        pol_ms, field_id=0, refant=0, model=unit(pol_ms, 0), weight_column="WEIGHT"
    )
    tables = [k[0]]
    polarised = unit(pol_ms, 1, (1.0, 0.05, 0.08, 0.0))
    common = {
        "field_id": 1,
        "gaintable": tables,
        "model": polarised,
        "weight_column": "WEIGHT",
    }
    for b in (budget(1200), budget(10_000, rows=7)):
        same(cal_pol.gpol(pol_ms, solint="int", refant=0, minblperant=2, **common),
             cal_pol.gpol(pol_ms, solint="int", refant=0, minblperant=2, budget=b,
                          **common))  # fmt: skip
        same(cal_pol.kcross(pol_ms, solint="int", **common),
             cal_pol.kcross(pol_ms, solint="int", budget=b, **common))  # fmt: skip
        same(cal_pol.xf(pol_ms, combine="scan", **common),
             cal_pol.xf(pol_ms, combine="scan", budget=b, **common))  # fmt: skip
    # Df, degenerate (an unpolarised model) and not (the polarised model,
    # rotated by P over the scan), with the data-fraction rule.
    for field, model in ((0, unit(pol_ms, 0)), (1, polarised)):
        kw = {"field_id": field, "gaintable": tables, "model": model, "combine": "scan",
                  "minblperant": 2, "weight_column": "WEIGHT", "min_data_fraction": 0.5,
                  "minsnr": 0.0}  # fmt: skip
        one = cal_pol.df(pol_ms, **kw)
        for b in (budget(1200), budget(10_000, rows=7)):
            got = cal_pol.df(pol_ms, budget=b, **kw)
            assert cal_chain._sha(one[0]) == cal_chain._sha(got[0])
            assert one[1].gauge_fixed == got[1].gauge_fixed
        assert one[1].gauge_fixed == (field == 0)


@pytest.mark.parametrize("n", [1, 2, 7, 10, 1001])
def test_the_streamed_gauge_equals_unpolarised_gauge(n):
    rng = np.random.default_rng(n)
    model = rng.standard_normal((n, 3, 4)) + 1j * rng.standard_normal((n, 3, 4))
    model = model.astype(np.complex64)
    model[: n // 3, :, 3] = model[: n // 3, :, 0]  # repeated ratios
    flag = rng.random((n, 3, 4)) < 0.2
    want = cal_pol.unpolarised_gauge(model, flag)
    parts = [slice(0, n // 2), slice(n // 2, n)]
    got = cal_chunks.gauge(lambda: ((model[p], flag[p]) for p in parts))
    assert got[0] == want[0]
    assert np.complex64(got[1]) == np.complex64(want[1])
    # The degenerate case: one ratio everywhere.
    flat = np.ones((n, 3, 4), np.complex64)
    assert cal_chunks.gauge(lambda: ((flat[p], flag[p]) for p in parts)) == (
        cal_pol.unpolarised_gauge(flat, flag)
    )


def test_the_angle_table_equals_row_angles(pol_ms):
    with core_ms.open_table(pol_ms) as t:
        c = {k: t.getcol(k) for k in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID")}
    rows = np.flatnonzero(c["FIELD_ID"] == 1)
    want = cal_pol.row_angles(pol_ms, c["TIME"][rows], c["ANTENNA1"][rows],
                              c["ANTENNA2"][rows], 1)  # fmt: skip
    table = cal_pol.angle_table(pol_ms, c["TIME"][rows], c["ANTENNA1"][rows],
                                c["ANTENNA2"][rows], 1)  # fmt: skip
    part = rows[::7]
    got = cal_pol.table_angles(table, c["TIME"][part], c["ANTENNA1"][part],
                               c["ANTENNA2"][part])  # fmt: skip
    assert np.array_equal(got[0], want[0][::7]) and np.array_equal(got[1], want[1][::7])


# -- the A step and the command -----------------------------------------------------


def test_flag_corrected_in_blocks_equals_one_block(cal_ms, tmp_path):
    strategies = core_flag.parse_strategy(STRATEGY)
    out = {}
    for name, max_rows in (("one", None), ("blocks", 13)):
        ms = Path(shutil.copytree(cal_ms, tmp_path / name / "x.ms"))
        summary = cal_chain.flag_corrected(ms, [0, 1], strategies, masks=[],
                                           column="DATA", max_rows=max_rows)  # fmt: skip
        summary.pop("chunking", None)
        with core_ms.open_table(ms) as t:
            out[name] = (summary, t.getcol("FLAG"))
    assert out["one"][0] == out["blocks"][0]
    assert np.array_equal(out["one"][1], out["blocks"][1])


def test_the_chain_command_does_not_depend_on_the_chunking(tmp_path):
    src = calibrator_ms(tmp_path / "src" / "x.ms")
    out = {}
    for arm, data in (("one", "data: {chunk_rows: 100000}\n"),
                      ("tiny", "data: {chunk_rows: 7}\n")):  # fmt: skip
        work = tmp_path / arm
        work.mkdir()
        ms = Path(shutil.copytree(src, work / "x.ms"))
        (work / "strategy.yaml").write_text(STRATEGY, encoding="utf-8")
        config = work / "config.yaml"
        config.write_text(CONFIG.replace("version: 1\n", "version: 1\n" + data))
        state = cli("run", config, ms)
        assert state["stages"]["apply"]["status"] == "done"
        run = ms.with_name("x.ms.rang-run")
        summary = pipe.json.loads((run / "calibrate" / "summary.json").read_text())
        with core_ms.open_table(ms) as t:
            cols = {k: t.getcol(k).tobytes() for k in ("FLAG", "CORRECTED_DATA")}
        out[arm] = {
            "cols": cols,
            "files": {
                p.relative_to(run): p.read_bytes()
                for p in sorted((run / "calibrate").rglob("*"))
                if p.is_file() and p.name != "summary.json"
            },
            "chunks": summary.pop("chunking"),
            "steps": [s.get("solutions") for s in summary["steps"]],
        }
    one, tiny = out["one"], out["tiny"]
    assert one["cols"] == tiny["cols"] and one["files"] == tiny["files"]
    assert one["steps"] == tiny["steps"]
    assert max(s["chunks"] for s in tiny["chunks"]["solves"]) > 1
    assert all(s["chunks"] == 1 for s in one["chunks"]["solves"])


def test_preflight_refuses_only_what_cannot_be_split(tmp_path):
    ms = calibrator_ms(tmp_path / "x.ms")
    info = pipe.inspect_ms(ms)
    (tmp_path / "strategy.yaml").write_text(STRATEGY, encoding="utf-8")
    path = tmp_path / "c.yaml"
    path.write_text(CONFIG)
    config = core_config.validate_file(path, ["calibrate"])
    assert pipe.memory_problems(config, info, ["calibrate"]) == []
    plan = core_chunks.budget(config, info)
    # A limit above the largest interval (K, G and F inf: one scan of 120
    # rows x 16 channels) but below a field: everything runs in chunks.
    fixed = plan.fixed_bytes + core_chunks.CHAIN_ROW_BYTES * 120
    unit_bytes = 120 * 16 * 4 * core_chunks.CELL_BYTES["chain"]
    config["data"]["memory_limit_gb"] = (fixed + unit_bytes) / core_chunks.GIB
    assert pipe.memory_problems(config, info, ["calibrate"]) == []
    # Below one interval: K, G and F are refused, naming the GiB; B is not.
    config["data"]["memory_limit_gb"] = (fixed + unit_bytes // 2) / core_chunks.GIB
    problems = pipe.memory_problems(config, info, ["calibrate"])
    assert [p.split(":")[0] for p in problems] == [
        "calibrate.primary.terms[0] (K, K)",
        "calibrate.primary.terms[1] (G, G)",
        "calibrate.secondary.terms[0] (F, F)",
    ]
    assert all("GiB" in p and "solution interval" in p for p in problems)
