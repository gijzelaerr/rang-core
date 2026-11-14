"""A heavy-lock run inside a heavy-lock hold does not queue again (2026-11-14).

A session wrapped tools/check_all.py (which locks itself) in heavy_lock.py run:
the wrapper held 4 slots idle for five hours while the inner ticket waited.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "heavy_lock.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


hl = _load("heavy_lock")
ca = _load("check_all")

PRINT_HELD = [
    sys.executable,
    "-c",
    "import os; print('held=' + os.environ['RANG_HEAVY_LOCK_HELD'])",
]


def test_held_parses_the_variable():
    assert hl.held({}) is None
    assert hl.held({hl.HELD_VAR: "4:8"}) == (4, 8.0)
    assert hl.held({hl.HELD_VAR: "garbage"}) is None
    assert ca._held("6:12.5") == (6, 12.5) and ca._held("") is None


def test_shared_run_tells_its_child_the_hold(tmp_path, monkeypatch, capfd):
    monkeypatch.setenv("RANG_HEAVY_LOCK", str(tmp_path / "heavy"))
    monkeypatch.delenv(hl.HELD_VAR, raising=False)
    assert hl.run(PRINT_HELD, poll=0.02, slots=2, mem=3.0) == 0
    assert "held=2:3" in capfd.readouterr().out
    assert not list((tmp_path / "heavy-slots").glob("*"))  # heartbeat removed


def test_nested_run_does_not_queue(tmp_path, monkeypatch, capfd):
    monkeypatch.setenv("RANG_HEAVY_LOCK", str(tmp_path / "heavy"))
    monkeypatch.setenv(hl.HELD_VAR, "4:8")
    # the exclusive lock is taken by someone else: a queueing run would wait forever
    assert hl.try_acquire(tmp_path / "heavy", ["someone else"])
    assert hl.run(PRINT_HELD, poll=0.02, slots=2, mem=4.0) == 0
    out, err = capfd.readouterr()
    assert "already inside a heavy-lock hold (4 slots, 8 GB" in err
    assert "warning" not in err and out.strip() == "held=4:8"
    assert (
        not (tmp_path / "heavy-queue").exists()
        and not (tmp_path / "heavy-slots").exists()
    )


def test_nested_run_asking_for_more_warns_and_runs(tmp_path, monkeypatch, capfd):
    monkeypatch.setenv("RANG_HEAVY_LOCK", str(tmp_path / "heavy"))
    monkeypatch.setenv(hl.HELD_VAR, "4:8")
    assert hl.run(PRINT_HELD, poll=0.02, slots=None) == 0  # exclusive request
    out, err = capfd.readouterr()
    assert "warning: asked for" in err and out.strip() == "held=4:8"
    assert not (tmp_path / "heavy-queue").exists()


def test_wrapped_wrapper_end_to_end(tmp_path, monkeypatch):
    """heavy_lock run --slots 2 -- heavy_lock run --slots 4 -- cmd finishes."""
    env = {k: v for k, v in os.environ.items() if k != hl.HELD_VAR}
    env["RANG_HEAVY_LOCK"] = str(tmp_path / "heavy")
    inner = [
        sys.executable,
        str(HELPER),
        "run",
        "--poll",
        "0.05",
        "--slots",
        "4",
        "--mem",
        "2",
        "--",
        *PRINT_HELD,
    ]
    outer = [
        sys.executable,
        str(HELPER),
        "run",
        "--poll",
        "0.05",
        "--slots",
        "2",
        "--mem",
        "2",
        "--",
        *inner,
    ]
    r = subprocess.run(
        outer, check=False, env=env, capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stderr
    assert "already inside a heavy-lock hold (2 slots, 2 GB" in r.stderr
    assert "warning: asked for 4 slots" in r.stderr and r.stdout.strip() == "held=2:2"


def _check_all(tmp_path, monkeypatch, argv):
    calls = []
    monkeypatch.setattr(
        ca, "ensure_venv", lambda root, extras, dry_run: Path(sys.executable)
    )
    monkeypatch.setattr(
        ca.subprocess, "call", lambda command, cwd=None: calls.append(command) or 0
    )
    assert ca.main([*argv, "--root", str(tmp_path)]) == 0
    (command,) = calls
    return command


def test_check_all_queues_when_not_inside_a_hold(tmp_path, monkeypatch):
    monkeypatch.delenv(ca.HELD_VAR, raising=False)
    command = _check_all(tmp_path, monkeypatch, ["--quick"])
    assert Path(command[1]).name == "heavy_lock.py" and command[2] == "run"


def test_check_all_inside_a_hold_does_not_queue(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(ca.HELD_VAR, "4:8")
    command = _check_all(tmp_path, monkeypatch, ["--quick"])
    assert "heavy_lock.py" not in " ".join(command) and "--inner" in command
    out = capsys.readouterr().out
    assert "already inside a heavy-lock hold" in out and "warning" not in out


def test_check_all_inside_a_smaller_hold_warns(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(ca.HELD_VAR, "2:4")
    command = _check_all(tmp_path, monkeypatch, [])  # full check wants 8 slots, 12 GB
    assert "heavy_lock.py" not in " ".join(command)
    assert "warning: wants 8 slots, 12 GB" in capsys.readouterr().out
