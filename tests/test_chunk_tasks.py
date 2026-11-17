"""Chunk tasks and the local process pool (research/chunk-task-api.md,
section 3, criterion 6): specs round-trip through JSON, the executor keys
leave the stage hash alone, and flag, calibrate and apply give the same
columns, stores and summaries at any process count. The comparisons on the
W3/W3b sets are `tools/oracles/chunk_tasks/run.py`."""

import importlib.util
import json
import os
import zipfile
from pathlib import Path

import numpy as np
import pytest
from rang import core_chunks, core_config, core_ms, core_ms_write, core_tasks
from rang import core_pipeline as pipe

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


w2 = _load("test_w2_commands")
w3 = _load("test_w3_chunking")

needs_writer = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)
STRATEGY = (
    ROOT
    / "research"
    / "results"
    / "e2-acceptance-scripts"
    / "mk_rfi_flagging_calibrator_fields_firstpass.yaml"
)


# -- specs and keys ------------------------------------------------------------------


@needs_writer
def test_a_spec_round_trips_through_json(tmp_path):
    ms = w2.make_ms(tmp_path / "x.ms")
    info = pipe.inspect_ms(ms)
    rows = np.arange(info["nrows"])
    groups = pipe._groups(info["rows"], rows)
    specs, blocks = core_tasks.plan_flag(
        ms, info, groups, 7, "DATA", "or", w2.STRATEGY, [np.array([1.4e9, 1.5e9])]
    )
    assert len(specs) == sum(blocks) > len(groups)
    assert [s.index for s in specs] == list(range(len(specs)))
    for spec in specs[:3]:
        back = core_tasks.ChunkSpec.from_json(spec.to_json())
        assert core_tasks.same_spec(spec, back)
        json.loads(spec.to_json())  # plain JSON


def test_the_executor_keys_are_resource_keys():
    a, _ = core_config.resolve({"version": 1})
    b, errors = core_config.resolve(
        {"version": 1, "data": {"executor": "local", "processes": 4, "threads": 8}}
    )
    assert errors == []
    for stage in core_config.STAGES:
        assert core_config.stage_hash(a, stage) == core_config.stage_hash(b, stage)
    assert core_tasks.settings(a) == ("local", 1, None)
    assert core_tasks.settings(b) == ("local", 4, 8)
    _, errors = core_config.resolve(
        {"version": 1, "data": {"executor": "dask", "processes": 0, "threads": 0}}
    )
    assert {p for p, _ in errors} == {
        "data.executor",
        "data.processes",
        "data.threads",
    }


def test_the_budget_is_shared_out_among_the_processes():
    one = core_chunks.Budget(8.0, 1000, (64, 4))
    four = core_chunks.Budget(8.0, 1000, (64, 4), processes=4)
    assert four.limit_bytes == one.limit_bytes // 4
    assert four.rows("flag") < one.rows("flag")
    assert "per process" in four.limit_text and "per process" not in one.limit_text
    with pytest.raises(core_chunks.MemoryLimitError, match="per process"):
        _ = core_chunks.Budget(1.0, 1000, (64, 4), processes=4).chunk_bytes


def test_threads_are_shared_out(monkeypatch):
    monkeypatch.setenv("RAYON_NUM_THREADS", "12")
    assert core_tasks.Executor(1).threads_per_process is None
    assert core_tasks.Executor(4).threads_per_process == 3
    assert core_tasks.Executor(4, threads=2).threads_per_process == 1
    with pytest.raises(core_tasks.ExecutorError):
        core_tasks.Executor(1, kind="dask")


# -- the executor ---------------------------------------------------------------------


@needs_writer
@pytest.mark.parametrize("processes", [1, 2])
def test_a_failed_task_raises_in_plan_order(tmp_path, processes):
    """The partials before a failed task are delivered (and written by the
    caller), the failure is raised in its turn, and nothing after it."""
    ms = w2.make_ms(tmp_path / "x.ms")
    info = pipe.inspect_ms(ms)
    groups = pipe._groups(info["rows"], np.arange(info["nrows"]))
    specs, _ = core_tasks.plan_flag(ms, info, groups, 12, "DATA", "or", w2.STRATEGY, [])
    assert len(specs) > 4
    specs[3].params["column"] = "NO_SUCH_COLUMN"
    got = []
    ex = core_tasks.Executor(processes, threads=processes)
    try:
        with pytest.raises(Exception, match="NO_SUCH_COLUMN"):
            got.extend(ex.map(specs, None))
    finally:
        ex.close()
    assert len(got) == 3
    for spec, part in zip(specs, got):
        np.testing.assert_array_equal(part["rows"], spec.arrays["rows"])


@needs_writer
def test_the_solve_trace_needs_one_process(tmp_path, monkeypatch):
    ms = w2.make_ms(tmp_path / "x.ms")
    config = w3._config(tmp_path, w3.CONFIG, "data: {processes: 2}\n")
    monkeypatch.setenv("RANG_SOLVE_TRACE", str(tmp_path / "trace.json"))
    with pytest.raises(SystemExit) as exit_:
        w2.cli("calibrate", str(config), str(ms))
    assert exit_.value.code == 2
    assert not ms.with_name("x.ms.rang-run").exists()
    parsed = core_config.validate_file(config, ["calibrate"])
    assert any("RANG_SOLVE_TRACE" in p for p in core_tasks.problems(parsed))


@needs_writer
def test_a_limit_too_small_per_process_is_refused_before_writing(tmp_path):
    ms = w2.make_ms(tmp_path / "x.ms")
    config = w3._config(
        tmp_path, w3.CONFIG, "data: {memory_limit_gb: 2, processes: 4}\n"
    )
    before = w3._columns(ms, "FLAG")
    with pytest.raises(SystemExit) as exit_:
        w2.cli("flag", str(config), str(ms))
    assert exit_.value.code == 2
    assert before["FLAG"].tobytes() == w3._columns(ms, "FLAG")["FLAG"].tobytes()
    assert not ms.with_name("x.ms.flagversions").exists()
    problems = pipe.memory_problems(
        core_config.validate_file(config, ["flag"]), pipe.inspect_ms(ms), ["flag"]
    )
    assert problems and "per process" in problems[0]


# -- the stages at any process count ------------------------------------------------------

VOLATILE = (
    "seconds",
    "started",
    "finished",
    "updated",
    "created",
    "flag_version",
    "store",
    "receipt",
    "path",
    "chunking",
    "rang_original_saved_now",
    "restored_before",
)


def _clean(value):
    if isinstance(value, dict):
        return {
            k: _clean(v)
            for k, v in value.items()
            if not any(s in str(k) for s in VOLATILE)
            and str(k) not in ("ms", "strategy")
        }
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _run(work, ms, config, stages, columns):
    for stage in stages:
        state = w2.cli(stage, str(config), str(ms))
        assert state["stages"][stage]["status"] == "done", stage
    run = ms.with_name(ms.name + ".rang-run")
    return {
        "columns": w3._columns(ms, *columns),
        "stores": {
            str(p.relative_to(run)): p.read_bytes()
            for p in sorted((run / "calibrate").rglob("*"))
            if p.is_file() and p.name != "summary.json"
        },
        "summaries": {
            s: _clean(json.loads((run / s / "summary.json").read_text()))
            for s in stages
        },
        "chunking": {
            s: json.loads((run / s / "summary.json").read_text())["chunking"]
            for s in stages
        },
    }


def _equal(a, b):
    for name, value in a["columns"].items():
        assert value.tobytes() == b["columns"][name].tobytes(), name
    assert a["stores"] == b["stores"]
    assert a["summaries"] == b["summaries"]


@needs_writer
def test_the_stages_do_not_depend_on_the_process_count(tmp_path):
    out = {}
    for arm, data in (
        ("one", ""),
        ("pool", "data: {processes: 2, threads: 2, chunk_rows: 7}\n"),
    ):
        work = tmp_path / arm
        work.mkdir()
        ms = w2.make_ms(work / "x.ms")
        config = w3._config(work, w3.CONFIG, data)
        out[arm] = _run(
            work,
            ms,
            config,
            ("flag", "calibrate", "apply"),
            ("FLAG", "MODEL_DATA", "CORRECTED_DATA"),
        )
    _equal(out["one"], out["pool"])
    pool = out["pool"]["chunking"]
    assert all(pool[s]["processes"] == 2 for s in pool)
    assert pool["calibrate"]["threads_per_process"] == 1
    assert max(p["chunks"] for p in pool["calibrate"]["partitions"]) > 1
    assert max(pool["flag"]["blocks"]) > 1
    assert out["one"]["chunking"]["flag"]["processes"] == 1


def _fixture_zip():
    configured = os.environ.get("RANG_FIXTURE")
    if configured and configured.endswith(".zip") and Path(configured).is_file():
        return Path(configured)
    candidate = ROOT / "outputs" / "ska-pointing" / "outer_scans.zip"
    return candidate if candidate.is_file() else None


FIXTURE_CONFIG = """\
version: 1
fields: {{fcal: [J1939-6342]}}
{data}flag: {{strategy: {strategy}}}
calibrate:
  model: {{source: setjy}}
  primary:
    terms:
      - {{type: complex, name: Gint, solint: int, freqint: 16}}
      - {{type: complex, name: G2, solint: 2, freqint: 512}}
      - {{type: complex, name: Gchan, solint: inf, freqint: 1}}
"""


@needs_writer
@pytest.mark.skipif(
    _fixture_zip() is None, reason="fixture outer_scans.zip not present"
)
def test_the_public_fixture_does_not_depend_on_the_process_count(tmp_path):
    out = {}
    for arm, data in (
        ("one", ""),
        ("pool", "data: {processes: 2, threads: 2, chunk_rows: 7}\n"),
    ):
        work = tmp_path / arm
        work.mkdir()
        with zipfile.ZipFile(_fixture_zip()) as z:
            names = [n for n in z.namelist() if "_scan_9.ms/" in n]
            z.extractall(work, names)
        ms = next(work.rglob("*_scan_9.ms"))
        config = work / "config.yaml"
        config.write_text(
            FIXTURE_CONFIG.format(data=data, strategy=STRATEGY.as_posix()),
            encoding="utf-8",
        )
        out[arm] = _run(
            work,
            ms,
            config,
            ("flag", "calibrate", "apply"),
            ("FLAG", "MODEL_DATA", "CORRECTED_DATA"),
        )
    _equal(out["one"], out["pool"])
    assert (
        max(p["chunks"] for p in out["pool"]["chunking"]["calibrate"]["partitions"]) > 1
    )
    with core_ms.open_table(next((tmp_path / "one").rglob("*_scan_9.ms"))) as t:
        assert t.nrows == 140
