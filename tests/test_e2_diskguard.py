"""The E2-A rerun's disk stop rule (research/e2-acceptance.md 9.6):
`e2_diskguard.py` returns the command's exit code, refuses to start under the
floor, and stops the command's process tree when free space drops under it,
with a durable JSON-lines record in every case."""

import importlib.util
import json
import shutil
import sys
from collections import namedtuple
from pathlib import Path

import pytest

pytest.importorskip("psutil")

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "research/results/e2-acceptance-scripts/e2_diskguard.py"
)
spec = importlib.util.spec_from_file_location("e2_diskguard", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

Usage = namedtuple("Usage", "total used free")


def events(log):
    return [json.loads(line) for line in Path(log).read_text().splitlines()]


def test_passes_exit_code_and_records(tmp_path):
    log = tmp_path / "g.jsonl"
    rc = guard.main(
        ["--path", str(tmp_path), "--min-free-gib", "0", "--log", str(log),
         "--every", "0.1", "--record", "0",
         "--", sys.executable, "-c", "import time, sys; time.sleep(0.5); sys.exit(3)"]
    )  # fmt: skip
    assert rc == 3
    ev = events(log)
    assert ev[0]["event"] == "start" and ev[-1]["event"] == "end"
    assert ev[-1]["rc"] == 3
    assert any(e["event"] == "sample" for e in ev)


def test_refuses_under_the_floor(tmp_path):
    log = tmp_path / "g.jsonl"
    rc = guard.main(
        ["--path", str(tmp_path), "--min-free-gib", "1e9", "--log", str(log),
         "--", sys.executable, "-c", "open('ran', 'w')"]
    )  # fmt: skip
    assert rc == guard.HALT_RC
    assert [e["event"] for e in events(log)] == ["refused"]
    assert not Path("ran").exists()


def test_halts_the_tree_when_free_space_drops(tmp_path, monkeypatch):
    log = tmp_path / "g.jsonl"
    calls = {"n": 0}
    gib = guard.GIB

    def fake_usage(path):
        calls["n"] += 1
        free = 500 * gib if calls["n"] <= 3 else 100 * gib
        return Usage(1000 * gib, 1000 * gib - free, free)

    monkeypatch.setattr(shutil, "disk_usage", fake_usage)
    rc = guard.main(
        ["--path", str(tmp_path), "--min-free-gib", "160", "--log", str(log),
         "--every", "0.1", "--grace", "5",
         "--", sys.executable, "-c",
         ("import subprocess, sys, time; "
          "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
          "time.sleep(60)")]
    )  # fmt: skip
    assert rc == guard.HALT_RC
    ev = events(log)
    halt = [e for e in ev if e["event"] == "halt"]
    assert len(halt) == 1 and halt[0]["free_gib"] == 100
    assert halt[0]["processes_stopped"] >= 1
