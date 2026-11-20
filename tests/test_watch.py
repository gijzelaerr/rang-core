# SPDX-License-Identifier: MIT
"""`rang-core watch` (research/live-view-scope.md, owner decision 6): reads a
run directory, a spool or any directory, and creates nothing."""

import io
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

from rang import watch


def _listing(root):
    return sorted(
        (p.relative_to(root).as_posix(), p.stat().st_mtime_ns) for p in root.rglob("*")
    )


def _state(tmp_path, **stage):
    started = datetime.now(timezone.utc) - timedelta(seconds=125)
    entry = {
        "status": "running",
        "attempts": 1,
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "started": started.isoformat(timespec="seconds"),
        "finished": None,
        "seconds": None,
        **stage,
    }
    ms = stage.pop("ms", str(tmp_path / "x.ms"))  # this system's path style
    entry.pop("ms", None)
    state = {"schema": "rang.run-state", "ms": ms, "stages": {"flag": entry}}
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return tmp_path


def test_finished_run_in_start_order(tmp_path):
    def done(start, seconds):
        return {
            "status": "done",
            "attempts": 1,
            "host": "nash",
            "pid": 1,
            "started": f"2026-11-19T{start}+00:00",
            "finished": "2026-11-19T23:00:00+00:00",
            "seconds": seconds,
        }

    stages = {
        "apply": done("08:40:35", 3998.4),
        "calibrate": done("07:31:44", 4131.0),
        "selfcal": done("09:47:15", 49613.0),
    }
    state = {"schema": "rang.run-state", "ms": "/data/e2n.ms", "stages": stages}
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "receipts").mkdir()
    (tmp_path / "receipts" / "run-1.rang-receipt.json").write_text("{}")
    (tmp_path / "selfcal").mkdir()
    (tmp_path / "selfcal" / "gemclean.log").write_text("x\nwall 11789.83 s\n")
    before = _listing(tmp_path)
    snap = watch.snapshot(tmp_path)
    assert snap["kind"] == "run" and snap["receipts"] == 1
    assert [s["stage"] for s in snap["stages"]] == ["calibrate", "apply", "selfcal"]
    assert snap["log"]["last_line"] == "wall 11789.83 s"
    text = "\n".join(watch.render(snap))
    assert "selfcal    done in 13 h 46 min" in text
    json.dumps(snap)
    assert _listing(tmp_path) == before


def test_running_stage_process(tmp_path):
    snap = watch.snapshot(_state(tmp_path))
    (stage,) = snap["stages"]
    assert stage["process"] == "alive" and 120 <= stage["elapsed_s"] < 600
    assert "running 2 min" in watch.render(snap)[1]
    # A pid that is not there: a child that has exited.
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    gone = watch.snapshot(_state(tmp_path, pid=child.pid))["stages"][0]
    assert gone["process"] == "gone"
    other = watch.snapshot(_state(tmp_path, host="elsewhere"))["stages"][0]
    assert other["process"] == "unknown (other host)"


def test_spool_and_plain_directory(tmp_path):
    for name in ("tasks", "claimed", "done", "workers"):
        (tmp_path / name).mkdir()
    (tmp_path / "tasks" / "0001.json").write_text("{}")
    (tmp_path / "tasks" / "0002.json").write_text("{}")
    (tmp_path / "claimed" / "0000").write_text("w1")
    (tmp_path / "done" / "a.pkl").write_bytes(b"x")
    (tmp_path / "done" / "b.err").write_text("boom")
    (tmp_path / "workers" / "w1.beat").write_text("")
    (tmp_path / "workers" / "w2.beat").write_text("")
    old = time.time() - 10 * watch.LEASE_S
    os.utime(tmp_path / "workers" / "w2.beat", (old, old))
    snap = watch.snapshot(tmp_path)
    assert snap["kind"] == "directory"
    (sp,) = snap["spools"]
    assert (sp["waiting"], sp["claimed"], sp["done"], sp["failed"]) == (2, 1, 1, 1)
    assert [w["live"] for w in sp["workers"]] == [True, False]
    assert "1 of 2 workers live" in "\n".join(watch.render(snap))


def test_tables_are_not_entered(tmp_path):
    table = tmp_path / "x.ms"
    (table / "SUB").mkdir(parents=True)
    (table / "table.dat").write_bytes(b"1")
    (table / "SUB" / "inner").write_bytes(b"22")
    (tmp_path / "run.log").write_text("first\nlast line\n\n")
    snap = watch.snapshot(tmp_path)
    assert snap["files"] == 2 and snap["log"]["last_line"] == "last line"


def test_ms_resolves_to_its_run_directory(tmp_path):
    ms = tmp_path / "a.ms"
    ms.mkdir()
    (ms / "table.dat").write_bytes(b"1")
    assert watch.resolve(ms) == ms
    run = tmp_path / "a.ms.rang-run"
    run.mkdir()
    _state(run)
    assert watch.resolve(ms) == run


def test_command_line(tmp_path):
    _state(tmp_path)
    before = _listing(tmp_path)
    out = io.StringIO()
    assert watch.main([str(tmp_path), "--interval", "1"], out, lambda s: None, 2) == 0
    lines = out.getvalue().splitlines()
    assert "run of " in lines[0] and "x.ms" in lines[0] and "flag" in lines[1]
    # The second tick: nothing but the clocks moved, so one line.
    assert "flag running" in lines[-1] and "process alive" in lines[-1]
    assert sum("run of" in line for line in lines) == 1
    out = io.StringIO()
    assert (
        watch.main(["--once", "--json", str(tmp_path), str(tmp_path / "no")], out) == 0
    )
    first, second = (json.loads(line) for line in out.getvalue().splitlines())
    assert first["schema"] == "rang.watch" and second["kind"] == "missing"
    assert _listing(tmp_path) == before


def test_through_rang_core(tmp_path):
    done = subprocess.run(
        [sys.executable, "-m", "rang.core_cli", "watch", "--once", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0 and "0 files" in done.stdout


def test_other_system_on_the_same_host(tmp_path):
    # WSL and its Windows host share a host name, not their process tables.
    foreign = "/home/x/a.ms" if os.name == "nt" else "D:\\data\\a.ms"
    (stage,) = watch.snapshot(_state(tmp_path, ms=foreign))["stages"]
    assert stage["process"] == "unknown (other system on this host)"
    assert watch.same_system(str(tmp_path / "a.ms"))


def test_unreadable_state_keeps_the_watch_going(tmp_path):
    (tmp_path / "state.json").write_text('{"stages": {"flag": {"status": "run')
    out = io.StringIO()
    assert watch.main([str(tmp_path)], out, lambda s: None, 2) == 0
    text = out.getvalue()
    assert "state.json: " in text and "no stage has started" not in text
    (tmp_path / "state.json").write_text('{"stages": [1, 2]}')
    assert "state.json: " in "\n".join(watch.render(watch.snapshot(tmp_path)))


def test_log_line_the_console_cannot_encode(tmp_path):
    line = "auto-mask: σ 8.19e-5 Jy, −3 dB"
    (tmp_path / "gemclean.log").write_text(line + "\n", encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="ascii")
    done = subprocess.run(
        [sys.executable, "-m", "rang.core_cli", "watch", "--once", str(tmp_path)],
        capture_output=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert b"auto-mask: \\u03c3 8.19e-5 Jy" in done.stdout


def test_run_directory_name_is_the_pipeline_s(tmp_path):
    from rang import core_pipeline

    ms = tmp_path / "a.ms"
    ms.mkdir()
    (ms / "table.dat").write_bytes(b"1")
    run = core_pipeline.default_run_dir(ms)
    run.mkdir()
    _state(run)
    assert watch.resolve(ms).resolve() == run


def test_reader_against_the_run_s_writer(tmp_path):
    """The pipeline rewrites state.json by replace while a watcher polls it
    (research/v030-review.md R-01): neither side may fail."""
    import threading

    from rang import core_pipeline

    _state(tmp_path)
    path = tmp_path / "state.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors, stop = [], threading.Event()

    def write():
        try:
            for k in range(300):
                payload["updated"] = str(k)
                core_pipeline._write_json(path, payload)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            stop.set()

    writer = threading.Thread(target=write)
    writer.start()
    reads = 0
    while not stop.is_set():
        snap = watch.snapshot(tmp_path)
        assert snap["kind"] == "run"
        reads += 1
    writer.join()
    assert not errors and reads > 0
