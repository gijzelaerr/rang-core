# SPDX-License-Identifier: MIT
"""heavy_lock status counts CPU inside WSL for holds launched through wsl.exe
(2026-11-21): the Windows side of such a hold is one idle wsl.exe, so the
status showed ~0.0 cores IDLE for a 14-worker job inside WSL."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "heavy_lock_wsl", ROOT / "tools" / "heavy_lock.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["heavy_lock_wsl"] = mod
    spec.loader.exec_module(mod)
    return mod


hl = _load()


def table(rows):
    """rows: (pid, ppid, cpu, mark, cmd[, rss]) -> the probe's text, parsed."""
    lines = []
    for r in rows:
        pid, ppid, cpu, mark, cmd = r[:5]
        rss = r[5] if len(r) > 5 else 0
        lines.append("\t".join(map(str, (pid, ppid, cpu, rss, mark, cmd))))
    return hl.parse_wsl_table("\n".join(lines) + "\nnot a row\n")


def test_parse_reads_cpu_rss_marker_and_command():
    t = table([(10, 1, 2.5, "-", "bash -lc echo hi", 4096), (11, 10, 0.0, "77", "")])
    assert t == {
        10: (1, 2.5, "-", "bash -lc echo hi", 4096),
        11: (10, 0.0, "77", "", 0),
    }


def test_wsl_tail():
    assert hl.wsl_tail("wsl -d Ubuntu -- bash -lc run x") == "bash -lc run x"
    assert hl.wsl_tail(r"C:\Windows\System32\wsl.exe -e python3 a.py") == "python3 a.py"
    assert hl.wsl_tail("wsl.exe --exec sh") == "sh"
    assert hl.wsl_tail("python check.py") is None
    assert hl.wsl_tail("wsl -d Ubuntu") is None


def test_marker_counts_every_process_carrying_it():
    before = table(
        [(5, 1, 0.0, "4242", "a"), (6, 5, 0.0, "4242", "b"), (7, 1, 0.0, "-", "c")]
    )
    after = table(
        [(5, 1, 2.0, "4242", "a"), (6, 5, 6.0, "4242", "b"), (7, 1, 9.0, "-", "c")]
    )
    hold = {"system": "windows", "pid": 4242, "command": "bash run.sh"}
    assert hl.wsl_hold_cores(before, after, hold, 2.0) == 4.0


def test_command_fallback_takes_the_tree_of_the_matching_process():
    cmd = "bash -lc export X=1;   run  it"
    before = table(
        [(20, 1, 1.0, "-", "bash -lc export X=1; run it"), (21, 20, 0.0, "-", "worker")]
    )
    after = table(
        [
            (20, 1, 1.5, "-", "bash -lc export X=1; run it"),
            (21, 20, 3.5, "-", "worker"),
            (22, 20, 1.0, "-", "worker"),  # new since the first table
            (30, 1, 50.0, "-", "other"),
        ]
    )
    hold = {"system": "windows", "pid": 9, "command": f"wsl -d Ubuntu -- {cmd}"}
    assert hl.wsl_hold_cores(before, after, hold, 2.0) == (0.5 + 3.5 + 1.0) / 2.0


def test_a_hold_registered_from_wsl_is_its_pid_tree():
    before = table([(40, 1, 0.0, "-", "py"), (41, 40, 0.0, "-", "py")])
    after = table([(40, 1, 1.0, "-", "py"), (41, 40, 3.0, "-", "py")])
    assert hl.wsl_hold_cores(before, after, {"system": "wsl", "pid": 40}, 1.0) == 4.0


def test_nothing_found_is_none():
    t = table([(5, 1, 1.0, "-", "a")])
    hold = {"system": "windows", "pid": 1, "command": "python x.py"}
    assert hl.wsl_hold_cores(t, t, hold, 2.0) is None


def test_child_env_carries_the_hold_pid_into_wsl(monkeypatch):
    monkeypatch.setattr(hl.sys, "platform", "win32")
    monkeypatch.setenv("WSLENV", "FOO/u")
    env = hl._child_env(2, 4.0)
    assert env[hl.PID_VAR] == str(hl.os.getpid())
    assert env["WSLENV"] == f"FOO/u:{hl.PID_VAR}"
    assert hl.HELD_VAR not in env["WSLENV"]
    monkeypatch.setenv("WSLENV", f"{hl.PID_VAR}")
    assert hl._child_env(2, 4.0)["WSLENV"] == hl.PID_VAR


def test_tree_cores_counts_a_busy_child_under_a_waiting_wrapper():
    """The holder waits (`do_wait`) while its child works: the tree's CPU is
    the child's (nash, 2026-11-21: F6's holds looked idle; the tree sum was
    right, the jobs were in I/O wait).

    Deterministic on a loaded host (post hoc, 2026-11-21: a 0.5-core floor
    failed in a full check on a busy glacier): the child must be in the
    wrapper's measured tree, and its CPU time must rise between two tables
    (up to ten 0.5 s tries), not reach a rate."""
    import os
    import signal
    import subprocess
    import time

    busy = "import time\nt = time.time()\nwhile time.time() - t < 60: pass\n"
    wrapper = (
        f"import subprocess, sys\nsubprocess.call([sys.executable, '-c', {busy!r}])\n"
    )
    p = subprocess.Popen([sys.executable, "-c", wrapper])
    kids: set[int] = set()
    try:
        # The descendants appear under the wrapper (a venv's python.exe on
        # Windows is a launcher with the interpreter as its child, so the
        # busy process is some descendant, not necessarily the first).
        for _ in range(100):
            table = hl.process_table([p.pid]) or {}
            kids = hl._tree(table, p.pid) - {p.pid}
            if len(kids) >= 1 and any(table[k][1] > 0 for k in kids):
                break
            time.sleep(0.1)
        assert kids, "no child under the wrapper"
        before = {k: table[k][1] for k in kids}
        busy_pid = None
        for _ in range(10):
            time.sleep(0.5)
            table = hl.process_table([p.pid]) or {}
            tree = hl._tree(table, p.pid)
            risen = [k for k in tree - {p.pid} if table[k][1] > before.get(k, 0.0)]
            if risen:
                busy_pid = risen[0]
                break
        assert busy_pid is not None, "no descendant's CPU time rose in 5 s"
        assert busy_pid in hl._tree(table, p.pid)
        cores = hl.tree_cores([p.pid], 0.5)[p.pid]
        assert cores is not None and cores >= 0.0, cores
    finally:
        table = hl.process_table([p.pid]) or {}
        for k in sorted(hl._tree(table, p.pid) - {p.pid}, reverse=True):
            try:
                os.kill(k, signal.SIGTERM)
            except OSError:
                pass
        p.wait(timeout=30)


def test_wsl_resident_memory_of_a_hold():
    after = table(
        [
            (5, 1, 1.0, "4242", "a", 3 * 10**9),
            (6, 5, 1.0, "4242", "b", 2 * 10**9),
            (7, 1, 0, "-", "c", 9),
        ]
    )
    procs = hl.wsl_hold_procs(after, {"system": "windows", "pid": 4242, "command": "x"})
    assert procs == {5, 6}
    assert sum(after[q][4] for q in procs) == 5 * 10**9


def test_mem_note_flags_a_hold_over_its_booking():
    assert hl.mem_note(8, 5 * 10**9) == ", 5.0/8 GB resident"
    assert hl.mem_note(8, 9 * 10**9) == ", 9.0/8 GB resident OVER"
    assert hl.mem_note(0, 9 * 10**9) == ", 9.0/0 GB resident"
    assert hl.mem_note(8, None) == ""


def test_tree_rss_sums_a_child_that_holds_memory():
    import subprocess
    import time

    child = "b = bytearray(300 * 2**20)\nimport time\ntime.sleep(5)\n"
    wrapper = (
        f"import subprocess, sys\nsubprocess.call([sys.executable, '-c', {child!r}])\n"
    )
    p = subprocess.Popen([sys.executable, "-c", wrapper])
    try:
        time.sleep(2.0)
        rss = hl.tree_rss([p.pid])[p.pid]
    finally:
        p.wait(timeout=30)
    assert rss is not None and rss > 300 * 2**20, rss
