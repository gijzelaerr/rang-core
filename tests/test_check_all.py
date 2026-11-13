"""tools/check_all.py and the rang.check set-up fixes (research/speedup-tools.md)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from rang import check

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_all", ROOT / "tools" / "check_all.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_all"] = mod
    spec.loader.exec_module(mod)
    return mod


ca = _load()

UNC = r"\\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs"


@pytest.mark.parametrize(
    ("given", "want"),
    [
        (UNC, UNC),  # already right
        (UNC[1:], UNC),  # Git Bash dropped one backslash
        ("/wsl.localhost/Ubuntu/home/gijsm/Github/rang/outputs", UNC),
        (r"\wsl$\Ubuntu\x", r"\\wsl$\Ubuntu\x"),
        ("//wsl.localhost/Ubuntu/x", "//wsl.localhost/Ubuntu/x"),  # valid as is
        (r"C:\rang\outputs", r"C:\rang\outputs"),
        ("/home/gijsm/Github/rang/outputs", "/home/gijsm/Github/rang/outputs"),
        ("/mnt/d/rang/outputs", "/mnt/d/rang/outputs"),
    ],
)
def test_repair_unc(given, want):
    assert check.repair_unc(given) == want


def test_archive_outputs_set_repaired_default_and_absent():
    env = {check.ARCHIVE_ENV: UNC}
    assert check.archive_outputs(env) == (UNC, "set")
    env = {check.ARCHIVE_ENV: UNC[1:]}
    assert check.archive_outputs(env) == (UNC, "repaired")
    absent = check.archive_outputs({}, default="X", exists=lambda p: False)
    assert absent == (None, None)
    present = check.archive_outputs({}, default="X", exists=lambda p: True)
    assert present == (("X", "default") if os.name == "nt" else (None, None))


def test_pytest_paths_limit_pytest():
    argv = {s[0]: s[3] for s in check.steps("py", ["tests/test_a.py"])}["pytest"]
    assert argv[-1] == "tests/test_a.py"
    if "-n" in argv:
        assert argv[argv.index("-n") + 1] == "1"
    full = {s[0]: s[3] for s in check.steps("py")}["pytest"]
    assert not any(a.startswith("tests/") for a in full)


VV = "rustc 1.93.1 (01f6ddf75 2026-02-11)\ncommit-hash: aaaa\nrelease: 1.93.1\n"
OTHER = "rustc 1.99.1 (x 2026-08-27)\ncommit-hash: bbbb\nrelease: 1.99.1\n"


def _rustc_info(target: Path, *outputs: str) -> None:
    target.mkdir(parents=True, exist_ok=True)
    info = {"outputs": {str(i): {"stdout": o} for i, o in enumerate(outputs)}}
    (target / ".rustc_info.json").write_text(json.dumps(info), encoding="utf-8")


def test_stale_reason(tmp_path):
    t = tmp_path / "target"
    assert ca.stale_reason(t, VV) is None  # absent
    _rustc_info(t, "___.exe", VV)
    assert ca.stale_reason(t, VV) is None
    _rustc_info(t, OTHER, VV)  # both compilers seen: cargo keeps them apart
    assert ca.stale_reason(t, VV) is None
    _rustc_info(t, OTHER)
    assert "bbbb" in ca.stale_reason(t, VV)
    (t / ca.STAMP).write_text(VV, encoding="utf-8")  # the stamp wins
    assert ca.stale_reason(t, VV) is None
    (t / ca.STAMP).write_text(OTHER, encoding="utf-8")
    assert "bbbb != aaaa" in ca.stale_reason(t, VV)


def test_clear_stale_and_stamps(tmp_path):
    _rustc_info(tmp_path / "target", OTHER)
    _rustc_info(tmp_path / "core" / "py" / "target", VV)
    assert ca.clear_stale(tmp_path, VV, dry_run=True) == ["target"]
    assert (tmp_path / "target").exists()
    assert ca.clear_stale(tmp_path, VV) == ["target"]
    assert not (tmp_path / "target").exists()
    ca.write_stamps(tmp_path, VV)
    stamp = tmp_path / "core" / "py" / "target" / ca.STAMP
    assert stamp.read_text(encoding="utf-8") == VV


def test_quick_tests_follow_the_diff(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    files = {
        "test_mod.py": "from rang import cal_gain\n",
        "test_dotted.py": "import rang.formats.caltable\n",
        "test_core.py": "import rang.core as core\n",
        "test_tool.py": 'ROOT / "tools" / "heavy_lock.py"\n',
        "test_path.py": 'read("research/x.md")\n',
        "test_d1_docs.py": "\n",
        "test_other.py": "import numpy\n",
    }
    for name, text in files.items():
        (tests / name).write_text(text, encoding="utf-8")

    def pick(*changed):
        return [Path(p).name for p in ca.quick_tests(tmp_path, list(changed))]

    assert pick("python/rang/cal_gain.py") == ["test_mod.py"]
    assert pick("python/rang/formats/caltable.py") == ["test_dotted.py"]
    assert pick("core/src/grid.rs") == ["test_core.py"]
    assert pick("tools/heavy_lock.py") == ["test_tool.py"]
    assert pick("research/x.md") == ["test_path.py"]
    assert pick("docs/index.md") == ["test_d1_docs.py"]
    assert pick("tests/test_other.py") == ["test_other.py"]
    assert pick("CHANGELOG.md") == []


def test_the_lock_is_a_heavy_lock_helper():
    lock = ca.heavy_lock_script()
    assert lock.name == "heavy_lock.py" and lock.is_file()
