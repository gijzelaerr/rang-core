"""Cut verbatim from tests/test_flagging_signal.py at 43dc3c7 (task P8, research/p8-history.md).

Tests a file that moved to history/; not collected (testpaths = tests).
The repository paths below are the pre-move ones: run at 43dc3c7.
"""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("case", ["nested", "existing_logs", "ancestor", "override"])
def test_signal_wrapper_invalid_namespaces_stop_before_cache_logs_or_docker(
    tmp_path, case
):
    repo = Path(__file__).resolve().parents[1]
    tools = tmp_path / "tools/flagging"
    tools.mkdir(parents=True)
    for name in ("run-signal.sh", "preflight.py"):
        shutil.copy2(repo / "tools/flagging" / name, tools / name)
    source = tmp_path / "outputs/prepared"
    source.mkdir(parents=True)
    protected = source / "protected.dat"
    protected.write_bytes(b"never modify source")
    run_dir, prepared, extra = "outputs/prepared/new", "outputs/prepared", []
    if case == "existing_logs":
        run_dir = "outputs/new"
        (tmp_path / "outputs/new-logs").symlink_to(tmp_path / "outputs/missing")
    elif case == "ancestor":
        run_dir, prepared = "outputs/ancestor", "outputs/ancestor/child"
        (tmp_path / prepared).mkdir(parents=True)
    elif case == "override":
        run_dir, extra = "outputs/new", ["run-dir=/workspace/outputs/prepared/new"]
    completed = subprocess.run(
        ["bash", str(tools / "run-signal.sh"), run_dir, prepared, *extra],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert protected.read_bytes() == b"never modify source"
    assert not list((tmp_path / "outputs").glob("*numba-cache"))
    if case != "ancestor":
        assert not (tmp_path / run_dir).exists()
    else:
        assert list((tmp_path / run_dir).iterdir()) == [tmp_path / prepared]
    assert list(source.iterdir()) == [protected]
