# SPDX-License-Identifier: MIT
"""selfcal-io (issues #49, #50, research/selfcal-io.md): the CORRECTED_1GC
copy made inside round 1's apply, its resume after an interruption, and the
time-averaged solves read through `cal_chunks.AverageCache`, each against
the present path bit for bit."""

import importlib.util
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import cal_chunks, cal_selfcal, core_chunks, core_cli, core_ms, core_ms_write
from rang import core_pipeline as pipe
from rang import core_writeback as wb

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "test_c5_selfcal", ROOT / "tests/test_c5_selfcal.py"
)
c5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c5)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)
POSIX = pytest.mark.skipif(os.name != "posix", reason="POSIX only")

NCHAN = c5.NCHAN


def averaged_budget(nrows, intervals=1, cell_bytes=45):
    """A selfcal budget whose averaged chunks hold `intervals` of the
    15 averaged rows of an interval (several chunks, blocks of 7 rows)."""
    held = nrows + nrows // 3  # source rows and averaged rows (solint 3)
    cells = 15 * NCHAN * 4 * intervals
    return core_chunks.ChainBudget(
        chunk_bytes=core_chunks.CHAIN_ROW_BYTES * held + cell_bytes * 2 * cells + 64,
        cell_bytes=cell_bytes,
    )


def same(a, b):
    assert np.array_equal(a.gains, b.gains, equal_nan=True)
    assert np.array_equal(a.flags, b.flags)
    assert a.iterations == b.iterations
    assert a.converged_fraction == b.converged_fraction
    assert np.array_equal(a.gain_time, b.gain_time)


def solve(ms, term, rows, budget, cache=None, model="MODEL_TRUE"):
    return cal_selfcal.solve(
        ms, {"name": term["type"], **term}, rows=rows, field_id=0,
        input_column="DATA", model_column=model, weight_column="WEIGHT",
        budget=budget, average_time=True,
        **({"average_cache": cache} if cache is not None else {}),
    )  # fmt: skip


@pytest.mark.parametrize("intervals", [None, 1, 2])
def test_cached_averaged_solves_are_bit_identical_and_read_the_input_once(
    tmp_path, intervals
):
    ms, _, row_block = c5.make_ms(tmp_path / "x.ms", "pa", noise=0.05)
    rows = np.arange(len(row_block))
    budget = None if intervals is None else averaged_budget(len(rows), intervals)
    if budget is not None:  # the replay runs: several chunks
        fld_tb = cal_selfcal.time_bins(*columns_tb(ms, rows), 3)[0]
        avg = cal_chunks.Average(fld_tb, *columns(ms, "ANTENNA1", "ANTENNA2"),
                                 np.zeros(len(rows), bool))  # fmt: skip
        chunks, block = cal_chunks.plan(
            avg.time_bin, NCHAN, 4, budget, per_channel=False, average=avg
        )
        assert len(chunks) == 4 // intervals and block < len(rows) // 4
    terms = [{"type": "Sp", "solint": 3}, {"type": "Sa", "solint": 3}]
    present = [solve(ms, t, rows, budget) for t in terms]
    with cal_chunks.AverageCache(tmp_path / "cache") as cache:
        cached = [solve(ms, t, rows, budget, cache) for t in terms]
        assert any((tmp_path / "cache").iterdir())
    assert not (tmp_path / "cache").exists()
    for a, b in zip(present, cached, strict=True):
        same(a, b)
    n = len(rows)
    assert cached[0].settings["reads"] == {"DATA": n, "FLAG": n, "WEIGHT": n,
                                           "MODEL_TRUE": n}  # fmt: skip
    assert cached[1].settings["reads"] == {"DATA": 0, "FLAG": n, "WEIGHT": n,
                                           "MODEL_TRUE": n}  # fmt: skip
    assert cache.reads == {"DATA": n, "FLAG": 2 * n, "WEIGHT": 2 * n,
                           "MODEL_TRUE": 2 * n}  # fmt: skip


def columns(ms, *names):
    with core_ms.open_table(ms) as t:
        return [t.getcol(n) for n in names]


def columns_tb(ms, rows):
    t, s, f = columns(ms, "TIME", "SCAN_NUMBER", "FIELD_ID")
    return t[rows], s[rows], f[rows]


def test_the_kept_average_falls_back_where_flags_or_intervals_change(tmp_path):
    ms, _, row_block = c5.make_ms(tmp_path / "x.ms", "pa", noise=0.05)
    rows = np.arange(len(row_block))
    n = len(rows)
    budget = averaged_budget(n, 1)
    with cal_chunks.AverageCache(tmp_path / "cache") as cache:
        solve(ms, {"type": "Sp", "solint": 3}, rows, budget, cache)
        # A flag in the last interval only: that chunk is read again.
        with core_ms_write.open_table(ms, readonly=False) as t:
            f = t.getcol("FLAG")
            f[n - 2, 3, :] = True
            t.putcol("FLAG", f)
        sa = solve(ms, {"type": "Sa", "solint": 3}, rows, budget, cache)
        assert sa.settings["reads"]["DATA"] == n // 4
        same(sa, solve(ms, {"type": "Sa", "solint": 3}, rows, budget))
        # Other intervals: another averaging, read whole.
        sa6 = solve(ms, {"type": "Sa", "solint": 6}, rows, budget, cache)
        assert sa6.settings["reads"]["DATA"] == n
        same(sa6, solve(ms, {"type": "Sa", "solint": 6}, rows, budget))


def test_the_cache_refuses_what_it_cannot_keep(tmp_path):
    ms, _, row_block = c5.make_ms(tmp_path / "x.ms", "pa")
    rows = np.arange(len(row_block))
    cache = cal_chunks.AverageCache(tmp_path / "cache")
    with pytest.raises(ValueError, match="average_time"):
        cal_selfcal.solve(
            ms, {"type": "Sa", "solint": 3}, rows=rows, field_id=0,
            input_column="DATA", model_column="MODEL_TRUE", average_cache=cache,
        )  # fmt: skip


def two_copies(tmp_path):
    """Two equal MSs with CORRECTED_DATA (DATA) and a solution on scan 1."""
    ms, _, _ = c5.make_ms(tmp_path / "a.ms", "pa", noise=0.05)
    with wb.WriteBack(ms, stage="test") as w:
        w.ensure_column("CORRECTED_DATA", init="data")
    other = tmp_path / "b.ms"
    shutil.copytree(ms, other)
    (scan,) = columns(ms, "SCAN_NUMBER")
    rows = np.flatnonzero(scan == 1)
    sol = cal_selfcal.solve(
        ms, {"type": "Sa", "solint": 3}, rows=rows, field_id=0,
        input_column="CORRECTED_DATA", model_column="MODEL_TRUE", weight_column="WEIGHT",
    )  # fmt: skip
    sol.flags[0, 0, 2] = True  # an invalid gain: the apply flags its rows
    return ms, other, sol


def test_the_copy_inside_the_apply_equals_copy_then_apply(tmp_path):
    present, fused, sol = two_copies(tmp_path)
    with wb.WriteBack(present, stage="test", chunk_rows=7) as w:
        pipe._copy_column(w, "CORRECTED_DATA", "CORRECTED_1GC")
        a = cal_selfcal.apply(
            w, sol, input_column="CORRECTED_1GC", output_column="CORRECTED_DATA",
            chunk_rows=11,
        )  # fmt: skip
    marks = []
    with wb.WriteBack(fused, stage="test", chunk_rows=7) as w:
        b = cal_selfcal.apply(
            w, sol, input_column="CORRECTED_DATA", output_column="CORRECTED_DATA",
            chunk_rows=11, copy_to="CORRECTED_1GC", on_copied=marks.append,
        )  # fmt: skip
    counts = ("rows", "cells", "cells_flagged_before", "cells_flagged_after")
    assert [a[k] for k in counts] == [b[k] for k in counts]
    assert a["cells_flagged_after"] > a["cells_flagged_before"]
    names = ("CORRECTED_DATA", "CORRECTED_1GC", "FLAG", "FLAG_ROW", "DATA")
    for x, y in zip(columns(present, *names), columns(fused, *names), strict=True):
        assert x.dtype == y.dtype and np.array_equal(x, y)
    nrows = len(columns(fused, "DATA")[0])
    assert marks == [min(nrows, s + 11) for s in range(0, nrows, 11)]
    # Every row copied, those of scan 2 (no solution) included.
    assert np.array_equal(columns(fused, "CORRECTED_1GC")[0], columns(fused, "DATA")[0])
    with wb.WriteBack(fused, stage="test") as w, pytest.raises(ValueError):
        cal_selfcal.apply(
            w, sol, input_column="CORRECTED_DATA", output_column="CORRECTED_DATA"
        )


def test_an_interrupted_copy_is_finished_from_its_mark(tmp_path):
    _, fused, sol = two_copies(tmp_path)
    (data,) = columns(fused, "DATA")

    class Stop(Exception):
        pass

    marks = []

    def mark(rows):
        marks.append(rows)
        if len(marks) == 3:
            raise Stop

    with pytest.raises(Stop), wb.WriteBack(fused, stage="test") as w:
        cal_selfcal.apply(
            w, sol, input_column="CORRECTED_DATA", output_column="CORRECTED_DATA",
            chunk_rows=10, copy_to="CORRECTED_1GC", on_copied=mark,
        )  # fmt: skip
    corrected, partial = columns(fused, "CORRECTED_DATA", "CORRECTED_1GC")
    assert not np.array_equal(corrected[:20], data[:20])  # chunks 1-2 corrected
    assert np.array_equal(corrected[20:], data[20:])  # the rest untouched
    assert np.array_equal(partial[:30], data[:30])
    # The marker of this apply with copied_rows: the stage resumes the copy.
    run = pipe.RunDir(tmp_path / "run", fused)
    run.path.mkdir(parents=True, exist_ok=True)
    (run.path / "selfcal-input.json").write_text(json.dumps(
        {"column": "CORRECTED_1GC", "copied_from": "CORRECTED_DATA",
         "apply_finished": "t", "copied_rows": marks[-1]}))  # fmt: skip
    config, errors = pipe.core_config.resolve(
        {
            "version": 1,
            "fields": {"target": ["TGT"]},
            "image": {"size": 32, "scale": "2asec"},
        }
    )
    assert errors == []
    with run.locked():
        run.state["stages"]["apply"] = {"status": "done", "finished": "t"}
        ctx = {"config": config, "ms": fused, "run": run}
        copy, record = pipe._selfcal_input(ctx)
        assert copy and record == {
            "column": "CORRECTED_1GC", "copied_from": "CORRECTED_DATA",
            "apply_finished": "t", "resume_from": 30,
        }  # fmt: skip
        run.state["stages"]["apply"]["finished"] = "t2"  # apply ran again
        copy, record = pipe._selfcal_input(ctx)
        assert copy and "resume_from" not in record
    with wb.WriteBack(fused, stage="test", chunk_rows=7, on_interrupted="restore") as w:
        pipe._copy_column(w, "CORRECTED_DATA", "CORRECTED_1GC", first=30)
    assert np.array_equal(columns(fused, "CORRECTED_1GC")[0], data)


@POSIX
def test_the_stage_copies_inside_round_one_and_reads_the_input_once(tmp_path):
    results = {}
    for arm in ("present", "fused"):
        (tmp_path / arm).mkdir()
        ms, _, _ = c5.make_ms(tmp_path / arm / "x.ms", "pa", noise=0.05)
        config = c5.write_config(
            tmp_path / arm,
            "  average_time: true\ndata: {weights: uniform, chunk_rows: 15}\n",
        )
        with wb.WriteBack(ms, stage="test") as w:
            w.ensure_column("CORRECTED_DATA", init="data")
        run = pipe.RunDir(Path(str(ms) + ".rang-run"), ms)
        with run.locked():
            run.state["stages"]["apply"] = {"status": "done", "finished": "t1"}
            run.save()
        if arm == "present":  # the copy made before the stage, as main did
            with wb.WriteBack(ms, stage="test") as w:
                pipe._copy_column(w, "CORRECTED_DATA", "CORRECTED_1GC")
            (run.path / "selfcal-input.json").write_text(json.dumps(
                {"column": "CORRECTED_1GC", "copied_from": "CORRECTED_DATA",
                 "apply_finished": "t1"}))  # fmt: skip
        core_cli.dispatch(["selfcal", str(config), str(ms)])
        summary = json.loads((run.path / "selfcal" / "summary.json").read_text())
        marker = json.loads((run.path / "selfcal-input.json").read_text())
        assert marker == {"column": "CORRECTED_1GC", "copied_from": "CORRECTED_DATA",
                          "apply_finished": "t1"}  # fmt: skip
        assert not (run.path / "selfcal" / "average-cache").exists()
        (field,) = summary["fields"]
        stores = [
            cal_selfcal.read_store(r["store"], r["term"]["type"])[0]
            for r in field["rounds"]
        ]
        results[arm] = (
            summary,
            stores,
            columns(ms, "CORRECTED_DATA", "CORRECTED_1GC", "MODEL_DATA", "FLAG"),
        )
    (sp, gp, cp), (sf, gf, cf) = results["present"], results["fused"]
    assert sp["input"]["copy"] is None and sf["input"]["copy"] == "fused"
    rounds = sf["fields"][0]["rounds"]
    assert rounds[0]["image"]["column"] == "CORRECTED_DATA"
    assert rounds[0]["solve"]["settings"]["input_column"] == "CORRECTED_DATA"
    assert rounds[1]["solve"]["settings"]["input_column"] == "CORRECTED_1GC"
    assert rounds[0]["apply"]["copied_to"] == "CORRECTED_1GC"
    n = rounds[0]["solve"]["rows"]
    assert rounds[0]["solve"]["settings"]["reads"]["CORRECTED_DATA"] == n
    assert rounds[1]["solve"]["settings"]["reads"]["CORRECTED_1GC"] == 0
    assert rounds[1]["solve"]["settings"]["reads"]["MODEL_DATA"] == n
    for a, b in zip(gp, gf, strict=True):
        assert np.array_equal(a, b)
    for a, b in zip(cp, cf, strict=True):
        assert np.array_equal(a, b)
