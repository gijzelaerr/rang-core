# SPDX-License-Identifier: MIT
"""The heavy lock on hosts shared with other people (research/nash-host.md).

`RANG_HEAVY_NICE` starts every command of `heavy_lock.py run` under nice (and
idle I/O at 19); off Windows and WSL the lock directory defaults to the data
area `~/rang-data` instead of `/mnt/d`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


hl = _load("heavy_lock")

PRINT_NICE = [sys.executable, "-c", "import os; print('nice=%d' % os.nice(0))"]
posix = pytest.mark.skipif(sys.platform == "win32", reason="nice is POSIX only")


def test_nice_level_parses_the_variable():
    if sys.platform == "win32":
        assert hl.nice_level({hl.NICE_VAR: "19"}) is None
        return
    assert hl.nice_level({}) is None
    assert hl.nice_level({hl.NICE_VAR: "0"}) is None
    assert hl.nice_level({hl.NICE_VAR: "garbage"}) is None
    assert hl.nice_level({hl.NICE_VAR: "10"}) == 10
    assert hl.nice_level({hl.NICE_VAR: "40"}) == 19


def test_niced_leaves_the_command_alone_when_unset():
    assert hl.niced(["a", "b"], {}) == ["a", "b"]


@posix
def test_niced_prefixes_nice_and_idle_io(monkeypatch):
    monkeypatch.setattr(hl.shutil, "which", lambda name: "/usr/bin/" + name)
    assert hl.niced(["a"], {hl.NICE_VAR: "19"}) == [
        "nice", "-n", "19", "ionice", "-c3", "a",
    ]  # fmt: skip
    assert hl.niced(["a"], {hl.NICE_VAR: "5"}) == ["nice", "-n", "5", "a"]
    monkeypatch.setattr(hl.shutil, "which", lambda name: None)
    assert hl.niced(["a"], {hl.NICE_VAR: "19"}) == ["nice", "-n", "19", "a"]


@posix
@pytest.mark.parametrize("slots", [2, None])
def test_run_starts_its_command_niced(tmp_path, monkeypatch, capfd, slots):
    monkeypatch.setenv("RANG_HEAVY_LOCK", str(tmp_path / "heavy"))
    monkeypatch.delenv(hl.HELD_VAR, raising=False)
    monkeypatch.setenv(hl.NICE_VAR, "19")
    if slots is None:  # exclusive: the flock file lives in the home directory
        monkeypatch.setenv("HOME", str(tmp_path))
    assert hl.run(PRINT_NICE, poll=0.02, slots=slots, mem=1.0) == 0
    assert "nice=19" in capfd.readouterr().out


@posix
def test_nested_run_is_niced_too(tmp_path, monkeypatch, capfd):
    monkeypatch.setenv("RANG_HEAVY_LOCK", str(tmp_path / "heavy"))
    monkeypatch.setenv(hl.HELD_VAR, "4:8")
    monkeypatch.setenv(hl.NICE_VAR, "19")
    assert hl.run(PRINT_NICE, poll=0.02, slots=2, mem=1.0) == 0
    assert "nice=19" in capfd.readouterr().out


def test_lock_dir_off_windows_and_wsl_is_the_data_area(monkeypatch, tmp_path):
    monkeypatch.delenv("RANG_HEAVY_LOCK", raising=False)
    monkeypatch.setattr(hl.sys, "platform", "linux")
    monkeypatch.setattr(hl.platform, "release", lambda: "6.8.0-generic")
    monkeypatch.setattr(hl.Path, "home", classmethod(lambda cls: tmp_path))
    assert hl.lock_dir() == tmp_path / "rang-data" / "locks" / "heavy"
    monkeypatch.setattr(hl.platform, "release", lambda: "6.6.87-microsoft-standard")
    assert hl.lock_dir().as_posix() == "/mnt/d/rang/locks/heavy"
