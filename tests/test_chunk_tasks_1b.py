# SPDX-License-Identifier: MIT
"""Stage 1b of the chunk task API (research/chunk-task-api-1b.md, section
3, criterion 7): CASA-table apply by row chunk and the chain solves by chunk
and by field through the local process pool give the tables and columns of
one process. The comparisons on the W3/W3b sets are
`tools/oracles/chunk_tasks/run_1b.py`."""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import (
    applycal,
    cal_chain,
    cal_chunks,
    cal_delay,
    cal_gain,
    core_ms,
    core_ms_write,
    core_tasks,
)
from test_c2e_calibrate import CONFIG, calibrator_ms
from test_w2_commands import STRATEGY, cli
from test_w3b_chainchunks import budget, unit

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

# A term with two fields (a `chain-field` task each) before F.
TWO_FIELDS = """\
      - {type: G, name: G2, field: [CAL, TGT], solint: int, preapply: [K, B],
         interp: [linear, linear]}
      - {type: F, name: F, preapply: [K, B], interp: [linear, linear]}
"""


@pytest.fixture(scope="module")
def cal_ms(tmp_path_factory):
    return calibrator_ms(tmp_path_factory.mktemp("cta1b") / "x.ms")


def _columns(ms, names=("FLAG", "CORRECTED_DATA", "WEIGHT", "WEIGHT_SPECTRUM")):
    with core_ms.open_table(ms) as t:
        have = t.colnames()
        return {k: t.getcol(k).tobytes() for k in names if k in have}


def test_the_new_specs_round_trip_through_json(cal_ms, tmp_path):
    k = cal_delay.gaincal(cal_ms, field_id=0, refant=0, model=unit(cal_ms, 0),
                          weight_column="WEIGHT")[0]  # fmt: skip
    path = tmp_path / "K"
    applycal.caltable.write(k, path)
    ctx = applycal.ApplyContext(
        tables=[k], interp=["linear"], maps=[{0: "pooled", 1: 0}], fields=[0, 1],
        scan=None, applymode="calflag", column="CORRECTED_DATA", weighted=[False],
        spectrum=True, sigma_spectrum=False, nchan=16, info={}, threads=0,
        parang=True, angle_tables={0: (np.arange(3.0), np.ones((3, 4)))},
        parang_flags="spread",
    )  # fmt: skip
    specs = core_tasks.plan_apply_casa(cal_ms, [(0, 7), (7, 7)], ctx, [str(path)])
    chunk = core_tasks.chain_chunk_spec({"ms": str(cal_ms), "term": {"name": "G"},
                                         "field": 0}, 3, 50, 2.0, True)  # fmt: skip
    for spec in [*specs, chunk]:
        back = core_tasks.ChunkSpec.from_json(spec.to_json())
        assert core_tasks.same_spec(spec, back)
        json.loads(spec.to_json())


def _apply(ms, tables, executor, **kw):
    applycal.applycal(ms, tables, field=[0, 1], chunk_rows=7, executor=executor, **kw)
    return _columns(ms)


def test_casa_apply_does_not_depend_on_the_process_count(cal_ms, tmp_path):
    k = cal_delay.gaincal(cal_ms, field_id=0, refant=0, model=unit(cal_ms, 0),
                          weight_column="WEIGHT")[0]  # fmt: skip
    g = cal_gain.gaincal(cal_ms, field_id=0, refant=0, solint="int", gaintable=[k],
                         minblperant=3, model=unit(cal_ms, 0),
                         weight_column="WEIGHT")[0]  # fmt: skip
    paths = []
    for name, t in (("K", k), ("G", g)):
        applycal.caltable.write(t, tmp_path / name)
        paths.append(str(tmp_path / name))
    out = {}
    for arm, processes in (("one", 1), ("pool", 2)):
        ms = Path(shutil.copytree(cal_ms, tmp_path / arm / "x.ms"))
        with core_tasks.executor(
            {"data": {"processes": processes, "threads": 2}}
        ) as ex:
            out[arm] = _apply(ms, paths, ex, calwt=[False, True])
            out[arm + " tasks"] = ex.describe().get("tasks", {})
    assert out["one"] == out["pool"]
    assert out["pool tasks"].get("apply-casa", 0) > 1
    assert out["one tasks"] == {}  # inline: no specs at all


def test_caltables_given_as_objects_stay_inline(cal_ms, tmp_path):
    k = cal_delay.gaincal(cal_ms, field_id=0, refant=0, model=unit(cal_ms, 0),
                          weight_column="WEIGHT")[0]  # fmt: skip
    ms = Path(shutil.copytree(cal_ms, tmp_path / "x.ms"))
    with core_tasks.executor({"data": {"processes": 2, "threads": 2}}) as ex:
        _apply(ms, [k], ex)
        assert "tasks" not in ex.describe()


def test_a_replayed_solve_runs_its_chunks_in_workers(cal_ms):
    """`cal_chunks.replayed` inside a `Dispatch`: the same solution as the
    serial replay, with every chunk of both passes through the pool."""
    tables = {}
    term = {"type": "G", "name": "G", "fields": [0], "solint": "int", "combine": "",
            "refant": 0, "refantmode": "flex", "minsnr": 3.0, "minblperant": 3,
            "uvrange": "", "preapply": [], "interp": [], "max_iterations": 50,
            "stop_criterion": 1e-7, "stop_fraction": 0.99, "model": "unit",
            "calmode": "ap"}  # fmt: skip
    common = {"model_column": "MODEL_DATA", "weight_column": "WEIGHT",
              "budget": budget(400, rows=7)}  # fmt: skip
    one = cal_chain._solve_one(cal_ms, term, 0, tables, common)
    r = cal_chain.recipe("solve_one", cal_ms, term, 0, tables, common)
    assert r is not None
    with core_tasks.executor({"data": {"processes": 2, "threads": 2}}) as ex:
        with cal_chunks.dispatching(cal_chunks.Dispatch(ex, r)):
            got = cal_chain._solve_one(cal_ms, term, 0, tables, common)
        tasks = ex.describe()["tasks"]
    assert cal_chain._sha(one[0]) == cal_chain._sha(got[0])
    assert one[1].iterations == got[1].iterations
    assert tasks["chain-chunk"] >= 4  # two passes of two chunks or more


def test_a_replayed_k_zero_start_solve_runs_its_chunks_in_workers(cal_ms):
    """research/k-ambiguity.md section 10: K with `zero_start` traces two
    runs and pass 2 takes one iteration count per run, through `chain-chunk`
    specs and workers too; the same solution as the one call."""
    tables = {}
    term = {"type": "K", "name": "K", "fields": [0], "solint": "int", "combine": "",
            "refant": 0, "refantmode": "flex", "minsnr": 3.0, "minblperant": 3,
            "uvrange": "", "preapply": [], "interp": [], "max_iterations": 50,
            "stop_criterion": 1e-7, "stop_fraction": 0.99, "model": "unit"}  # fmt: skip
    common = {
        "model_column": "MODEL_DATA",
        "weight_column": "WEIGHT",
        "zero_start": True,
    }
    one = cal_chain._solve_one(cal_ms, term, 0, tables, common)
    common["budget"] = budget(400, rows=7)
    r = cal_chain.recipe("solve_one", cal_ms, term, 0, tables, common)
    assert r is not None
    with core_tasks.executor({"data": {"processes": 2, "threads": 2}}) as ex:
        with cal_chunks.dispatching(cal_chunks.Dispatch(ex, r)):
            got = cal_chain._solve_one(cal_ms, term, 0, tables, common)
        tasks = ex.describe()["tasks"]
    assert cal_chain._sha(one[0]) == cal_chain._sha(got[0])
    assert one[1].iterations == got[1].iterations
    assert (
        got[1].settings["zero_start_intervals"]
        == one[1].settings["zero_start_intervals"]
    )
    assert tasks["chain-chunk"] >= 4


def _command(tmp_path, arm, data, config):
    src = tmp_path / "src" / "x.ms"
    if not src.exists():
        calibrator_ms(src)
    work = tmp_path / arm
    work.mkdir()
    ms = Path(shutil.copytree(src, work / "x.ms"))
    (work / "strategy.yaml").write_text(STRATEGY, encoding="utf-8")
    path = work / "config.yaml"
    path.write_text(config.replace("version: 1\n", "version: 1\n" + data))
    state = cli("run", path, ms)
    assert state["stages"]["apply"]["status"] == "done"
    run = ms.with_name("x.ms.rang-run")
    summaries = {
        s: json.loads((run / s / "summary.json").read_text())
        for s in ("calibrate", "apply")
    }
    return {
        "cols": _columns(ms),
        "files": {
            p.relative_to(run): p.read_bytes()
            for p in sorted((run / "calibrate").rglob("*"))
            if p.is_file() and p.name != "summary.json"
        },
        "steps": [s.get("solutions") for s in summaries["calibrate"]["steps"]],
        "tasks": {s: summaries[s]["chunking"].get("tasks", {}) for s in summaries},
    }


@pytest.mark.parametrize("two_fields", [False, True])
def test_the_chain_stages_do_not_depend_on_the_process_count(tmp_path, two_fields):
    config = CONFIG
    if two_fields:
        old = "      - {type: F, name: F, preapply: [K, B], interp: [linear, linear]}\n"
        assert old in config
        config = config.replace(old, TWO_FIELDS)
    one = _command(tmp_path, "one", "data: {chunk_rows: 7}\n", config)
    pool = _command(
        tmp_path, "pool", "data: {chunk_rows: 7, processes: 2, threads: 2}\n", config
    )
    assert one["cols"] == pool["cols"]
    assert one["files"] == pool["files"]
    assert one["steps"] == pool["steps"]
    assert pool["tasks"]["apply"].get("apply-casa", 0) > 0
    assert pool["tasks"]["calibrate"].get("chain-chunk", 0) > 0
    if two_fields:
        assert pool["tasks"]["calibrate"].get("chain-field", 0) == 2


@pytest.fixture(scope="module")
def pol_ms(cal_ms, tmp_path_factory):
    pytest.importorskip("astropy")
    from test_c6w_polwire import _with_feed

    return _with_feed(
        Path(shutil.copytree(cal_ms, tmp_path_factory.mktemp("pol") / "x.ms"))
    )


def test_gpol_runs_its_chunks_in_workers(pol_ms, tmp_path):
    """A Gpol solve (P-rotated model, a pre-applied K read from its path)
    through `chain-chunk` tasks equals the serial solve."""
    k = cal_delay.gaincal(pol_ms, field_id=0, refant=0, model=unit(pol_ms, 0),
                          weight_column="WEIGHT")[0]  # fmt: skip
    applycal.caltable.write(k, tmp_path / "K")
    tables = {
        "K": {"table": k, "type": "K", "fields": [0], "path": str(tmp_path / "K")}
    }
    term = {"type": "Gpol", "name": "Gpol", "fields": [1], "solint": "int",
            "combine": "", "refant": 0, "refantmode": "flex", "minsnr": 3.0,
            "minblperant": 2, "uvrange": "", "preapply": ["K"], "interp": [],
            "max_iterations": 50, "stop_criterion": 1e-7, "stop_fraction": 0.99,
            "model": "unit", "parang": True, "frame": "casa"}  # fmt: skip
    common = {"model_column": "MODEL_DATA", "weight_column": "WEIGHT",
              "budget": budget(400, rows=7)}  # fmt: skip
    one = cal_chain._solve_pol(pol_ms, term, 1, tables, common)
    r = cal_chain.recipe("solve_pol", pol_ms, term, 1, tables, common)
    assert r is not None
    with core_tasks.executor({"data": {"processes": 2, "threads": 2}}) as ex:
        with cal_chunks.dispatching(cal_chunks.Dispatch(ex, r)):
            got = cal_chain._solve_pol(pol_ms, term, 1, tables, common)
        tasks = ex.describe()["tasks"]
    assert cal_chain._sha(one[0]) == cal_chain._sha(got[0])
    assert one[1] == got[1]
    assert tasks["chain-chunk"] >= 4


def test_apply_with_parang_does_not_depend_on_the_process_count(pol_ms, tmp_path):
    k = cal_delay.gaincal(pol_ms, field_id=0, refant=0, model=unit(pol_ms, 0),
                          weight_column="WEIGHT")[0]  # fmt: skip
    applycal.caltable.write(k, tmp_path / "K")
    out = {}
    for arm, processes in (("one", 1), ("pool", 2)):
        ms = Path(shutil.copytree(pol_ms, tmp_path / arm / "x.ms"))
        with core_tasks.executor(
            {"data": {"processes": processes, "threads": 2}}
        ) as ex:
            out[arm] = _apply(ms, [str(tmp_path / "K")], ex, parang=True)
            out[arm + " tasks"] = ex.describe().get("tasks", {})
    assert out["one"] == out["pool"]
    assert out["pool tasks"].get("apply-casa", 0) > 1


def test_a_failing_task_raises_after_the_partials_before_it(cal_ms, tmp_path):
    """The pool yields the partials in plan order and raises a task's error
    at its turn: the reduce has every earlier partial, none after."""
    k = cal_delay.gaincal(cal_ms, field_id=0, refant=0, model=unit(cal_ms, 0),
                          weight_column="WEIGHT")[0]  # fmt: skip
    applycal.caltable.write(k, tmp_path / "K")
    info = applycal.ms_info(Path(cal_ms))
    ctx = applycal.ApplyContext(
        tables=[k], interp=["linear"], maps=[applycal.field_map(k, "", info)],
        fields=[0, 1], scan=None, applymode="calflag", column="DATA",
        weighted=[False], spectrum=True, sigma_spectrum=False, nchan=16, info=info,
        threads=0, parang=False, angle_tables={}, parang_flags="spread",
    )  # fmt: skip
    specs = core_tasks.plan_apply_casa(
        cal_ms, [(0, 7), (7, 7), (14, 7), (21, 7)], ctx, [str(tmp_path / "K")]
    )
    specs[2].params["tables"] = [str(tmp_path / "missing")]
    seen = []
    with (
        core_tasks.executor({"data": {"processes": 2, "threads": 2}}) as ex,
        pytest.raises(Exception),  # noqa: B017 (the reader's own error)
    ):
        for part in ex.map(specs):
            seen.append(part["start"])
    assert seen == [0, 7]
