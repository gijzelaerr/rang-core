"""Cut verbatim from tests/test_flagging_balanced.py at 43dc3c7 (task P8, research/p8-history.md).

Tests a file that moved to history/; not collected (testpaths = tests).
The repository paths below are the pre-move ones: run at 43dc3c7.
"""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("case", ["nested", "existing_logs", "ancestor", "override"])
def test_balanced_wrapper_fails_before_cache_logs_or_docker(tmp_path, case):
    repository = Path(__file__).resolve().parents[1]
    tools = tmp_path / "tools/flagging"
    tools.mkdir(parents=True)
    for name in ("run-balanced.sh", "preflight.py"):
        shutil.copy2(repository / "tools/flagging" / name, tools / name)
    source = tmp_path / "outputs/prepared"
    source.mkdir(parents=True)
    (source / "protected.dat").write_bytes(b"original")
    run, prepared, extra = "outputs/prepared/new", "outputs/prepared", []
    if case == "existing_logs":
        run = "outputs/new"
        (tmp_path / "outputs/new-logs").mkdir()
    elif case == "ancestor":
        run, prepared = "outputs/ancestor", "outputs/ancestor/child"
        (tmp_path / prepared).mkdir(parents=True)
    elif case == "override":
        run, extra = "outputs/new", ["run-dir=outputs/prepared/new"]
    before = {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    completed = subprocess.run(
        ["bash", str(tools / "run-balanced.sh"), run, prepared, *extra],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert not list((tmp_path / "outputs").glob("*numba-cache"))
    after = {
        str(path.relative_to(tmp_path)): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert before == after
