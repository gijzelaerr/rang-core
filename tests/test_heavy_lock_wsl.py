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
    """rows: (pid, ppid, cpu, mark, cmd) -> the probe's text, parsed."""
    text = "\n".join("\t".join(map(str, r)) for r in rows) + "\nnot a row\n"
    return hl.parse_wsl_table(text)


def test_parse_keeps_command_lines_with_tabs_out():
    t = table([(10, 1, 2.5, "-", "bash -lc echo hi"), (11, 10, 0.0, "77", "")])
    assert t == {10: (1, 2.5, "-", "bash -lc echo hi"), 11: (10, 0.0, "77", "")}


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
