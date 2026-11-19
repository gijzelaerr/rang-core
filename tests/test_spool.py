"""The spool executor (research/multinode-executor.md, section 3): flag,
calibrate and apply through spool workers equal the inline path; a failed
task raises in plan order; a lost claim is re-queued; a worker of another
build is refused; the keys are validated and leave the stage hash alone. The
comparisons on the public fixture and on w3.ms are
`tools/oracles/multinode/run.py`."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from rang import core_config, core_spool, core_tasks
from rang import core_pipeline as pipe

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "test_chunk_tasks_for_spool", ROOT / "tests" / "test_chunk_tasks.py"
)
cta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cta)
_equal, _run, needs_writer, w2, w3 = (
    cta._equal,
    cta._run,
    cta.needs_writer,
    cta.w2,
    cta.w3,
)


class Workers:
    """`n` spool workers in their own processes, stopped on exit."""

    def __init__(self, spool, n, threads=1):
        core_spool.prepare(spool)
        self.spool = spool
        self.procs = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "rang.core_spool",
                    "worker",
                    str(spool),
                    "--threads",
                    str(threads),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(n)
        ]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        core_spool.stop(self.spool)
        for p in self.procs:
            try:
                p.wait(30)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


def _spool_data(spool, n, extra=""):
    return (
        f"data: {{executor: spool, spool: {json.dumps(spool.as_posix())}, "
        f"processes: {n}, spool_wait_s: 120{extra}}}\n"
    )


# -- keys ---------------------------------------------------------------------------


def test_the_spool_keys_are_resource_keys_and_validated(tmp_path):
    a, _ = core_config.resolve({"version": 1})
    b, errors = core_config.resolve(
        {
            "version": 1,
            "data": {
                "executor": "spool",
                "spool": str(tmp_path),
                "spool_wait_s": 30,
                "processes": 8,
            },
        }
    )
    assert errors == []
    for stage in core_config.STAGES:
        assert core_config.stage_hash(a, stage) == core_config.stage_hash(b, stage)
    assert core_tasks.spool_settings(b) == (str(tmp_path), 30.0)
    _, errors = core_config.resolve(
        {"version": 1, "data": {"executor": "spool", "spool_wait_s": 0}}
    )
    assert {p for p, _ in errors} == {"data.spool", "data.spool_wait_s"}
    relative, _ = core_config.resolve(
        {"version": 1, "data": {"executor": "spool", "spool": "spool"}}
    )
    assert any("absolute" in p for p in core_tasks.problems(relative))
    with pytest.raises(core_tasks.ExecutorError, match="data.spool"):
        core_tasks.Executor(2, kind="spool")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_a_spool_open_to_others_is_refused(tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir(mode=0o755)
    os.chmod(spool, 0o755)
    with pytest.raises(core_spool.SpoolError, match="open to other users"):
        core_spool.prepare(spool)


# -- the executor -------------------------------------------------------------------


def _flag_specs(tmp_path, max_rows=12):
    ms = w2.make_ms(tmp_path / "x.ms")
    info = pipe.inspect_ms(ms)
    groups = pipe._groups(info["rows"], np.arange(info["nrows"]))
    specs, _ = core_tasks.plan_flag(
        ms.resolve(), info, groups, max_rows, "DATA", "or", w2.STRATEGY, []
    )
    for s in specs:
        s.ms = str(s.ms)
    return specs


@needs_writer
def test_a_failed_spool_task_raises_in_plan_order(tmp_path):
    specs = _flag_specs(tmp_path)
    assert len(specs) > 4
    specs[3].params["column"] = "NO_SUCH_COLUMN"
    inline = list(core_tasks.INLINE.map(specs[:3], None))
    spool = tmp_path / "spool"
    got = []
    with Workers(spool, 2):
        ex = core_tasks.Executor(2, kind="spool", spool=spool, spool_wait_s=60)
        try:
            with pytest.raises(core_spool.SpoolError, match="NO_SUCH_COLUMN"):
                got.extend(ex.map(specs, None))
        finally:
            ex.close()
    assert len(got) == 3
    for a, b in zip(inline, got):
        assert a["flag"].tobytes() == b["flag"].tobytes()
        assert (a["before"], a["after"]) == (b["before"], b["after"])
    assert not list((spool / "tasks").iterdir())
    assert not [p for p in (spool / "done").iterdir()]


def test_discard_waits_for_a_running_task(tmp_path):
    """A task a live worker is still running when the parent discards writes
    its partial afterwards; discard waits for it, so the spool ends empty of
    the session (the race behind the plan-order test's empty-spool checks)."""
    import threading

    spool = core_spool.prepare(tmp_path / "spool")
    sp = core_spool.Spool(spool, wait_s=30)
    tag = f"{sp.session}-0001-00000004"
    (spool / "tasks" / f"{tag}.json").write_text("{}")
    worker = "livehost-1-abcdef"
    (spool / "workers" / f"{worker}.beat").touch()
    claim = spool / "claimed" / tag
    claim.write_text(worker)

    def finish():  # the worker's order: partial, task, claim
        time.sleep(0.5)
        (spool / "done" / f"{tag}.pkl").write_bytes(b"partial")
        (spool / "tasks" / f"{tag}.json").unlink(missing_ok=True)
        claim.unlink()

    t = threading.Thread(target=finish)
    t.start()
    t0 = time.time()
    sp.discard()
    t.join()
    assert time.time() - t0 >= 0.4  # it waited for the running task
    for sub in ("tasks", "done", "claimed"):
        assert not list((spool / sub).glob(f"{sp.session}-*")), sub


def test_discard_does_not_wait_for_a_dead_worker(tmp_path):
    spool = core_spool.prepare(tmp_path / "spool")
    sp = core_spool.Spool(spool, wait_s=30)
    tag = f"{sp.session}-0001-00000004"
    dead = "deadhost-1-abcdef"
    beat = spool / "workers" / f"{dead}.beat"
    beat.touch()
    os.utime(beat, (time.time() - 600, time.time() - 600))
    (spool / "claimed" / tag).write_text(dead)
    t0 = time.time()
    sp.discard()
    assert time.time() - t0 < 5
    assert not list((spool / "claimed").iterdir())


@needs_writer
def test_a_lost_claim_is_requeued(tmp_path, monkeypatch):
    """A claim whose worker stopped beating goes back into the queue and is
    run by a live worker; the partial equals the inline one."""
    monkeypatch.setattr(core_spool, "LEASE_S", 30.0)
    specs = _flag_specs(tmp_path)[:2]
    spool = core_spool.prepare(tmp_path / "spool")
    sp = core_spool.Spool(spool, wait_s=60)
    map_id = sp.new_map()
    tags = [sp.submit(s, map_id) for s in specs]
    # A dead worker took the first task: its heartbeat is a minute old.
    dead = "deadhost-1-abcdef"
    (spool / "claimed" / tags[0]).write_text(dead)
    beat = spool / "workers" / f"{dead}.beat"
    beat.touch()
    os.utime(beat, (time.time() - 600, time.time() - 600))
    with Workers(spool, 1):
        got = [sp.result(t) for t in tags]
    assert sp.counts["requeued"] == 1
    inline = list(core_tasks.INLINE.map(specs, None))
    for a, b in zip(inline, got):
        assert a["flag"].tobytes() == b["flag"].tobytes()


@needs_writer
def test_a_worker_of_another_build_is_refused(tmp_path):
    specs = _flag_specs(tmp_path)[:1]
    spool = core_spool.prepare(tmp_path / "spool")
    sp = core_spool.Spool(spool, wait_s=60)
    tag = sp.submit(specs[0], sp.new_map())
    path = spool / "tasks" / f"{tag}.json"
    body = json.loads(path.read_text())
    body["build"]["core_sha256"] = "0" * 64
    path.write_text(json.dumps(body))
    assert core_spool.serve(spool, max_tasks=1, log=lambda m: None) == 1
    with pytest.raises(core_spool.SpoolError, match="build mismatch"):
        sp.result(tag)


def test_no_live_worker_is_an_error_not_a_hang(tmp_path, monkeypatch):
    monkeypatch.setattr(core_spool, "BEAT_S", 0.2)
    spool = core_spool.prepare(tmp_path / "spool")
    sp = core_spool.Spool(spool, wait_s=1.0)
    spec = core_tasks.ChunkSpec("flag", "flag-block", 0, str(tmp_path / "x.ms"))
    tag = sp.submit(spec, sp.new_map())
    t0 = time.time()
    with pytest.raises(core_spool.SpoolError, match="no live worker"):
        sp.result(tag)
    assert time.time() - t0 < 30


# -- the stages ---------------------------------------------------------------------


@needs_writer
def test_the_stages_through_spool_workers_equal_one_process(tmp_path):
    out = {}
    for arm in ("one", "spool"):
        work = tmp_path / arm
        work.mkdir()
        ms = w2.make_ms(work / "x.ms")
        spool = tmp_path / "spooldir"  # not the arm's own directory
        data = _spool_data(spool, 2, ", chunk_rows: 7") if arm == "spool" else ""
        config = w3._config(work, w3.CONFIG, data)
        args = (
            work,
            ms,
            config,
            ("flag", "calibrate", "apply"),
            ("FLAG", "MODEL_DATA", "CORRECTED_DATA"),
        )
        if arm == "spool":
            with Workers(spool, 2):
                out[arm] = _run(*args)
        else:
            out[arm] = _run(*args)
    _equal(out["one"], out["spool"])
    chunking = out["spool"]["chunking"]
    assert all(chunking[s]["executor"] == "spool" for s in chunking)
    assert max(p["chunks"] for p in chunking["calibrate"]["partitions"]) > 1
    assert max(chunking["flag"]["blocks"]) > 1
