"""Reject invalid namespaces before wrappers can create logs or start Docker."""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE_ROOT / "tools/flagging/preflight.py"
SPEC = importlib.util.spec_from_file_location("flagging_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def prepared(tmp_path):
    source = tmp_path / "outputs/prepared"
    source.mkdir(parents=True)
    (source / "protected.dat").write_bytes(b"immutable input placeholder")
    return source


def test_valid_preflight_is_read_only(tmp_path):
    source = prepared(tmp_path)
    paths = preflight.validate_paths(tmp_path, "outputs/new/run", "outputs/prepared")
    assert paths["run"] == tmp_path / "outputs/new/run"
    assert paths["log"] == tmp_path / "outputs/new/run-logs"
    assert paths["sources"] == [source]
    assert not (tmp_path / "outputs/new").exists()


@pytest.mark.parametrize(
    "run,source",
    [
        ("outputs/prepared/new", "outputs/prepared"),
        ("outputs/new", "outputs/new/child"),
    ],
)
def test_nested_paths_do_not_mutate_sources(tmp_path, run, source):
    (tmp_path / source).mkdir(parents=True)
    with pytest.raises(ValueError, match="not be nested|fresh run"):
        preflight.validate_paths(tmp_path, run, source)
    assert not Path(str(tmp_path / run) + "-logs").exists()


def test_reused_or_dangling_logs_rejected(tmp_path):
    prepared(tmp_path)
    logs = tmp_path / "outputs/new-logs"
    logs.symlink_to(tmp_path / "outputs/missing")
    with pytest.raises(ValueError, match="fresh log"):
        preflight.validate_paths(tmp_path, "outputs/new", "outputs/prepared")


def test_symlink_escape_and_strategy_overlap_rejected(tmp_path):
    prepared(tmp_path)
    (tmp_path / "outputs/escape").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="beneath outputs"):
        preflight.validate_paths(tmp_path, "outputs/escape/new", "outputs/prepared")
    with pytest.raises(ValueError, match="not be nested"):
        preflight.validate_paths(
            tmp_path, "outputs/prepared/strategy", "outputs/prepared"
        )


@pytest.mark.parametrize(
    "wrapper",
    [
        "run-structured.sh",
        "run-caracal.sh",
        "run-response.sh",
        "run-equivariance.sh",
        "run-influence.sh",
    ],
)
@pytest.mark.parametrize("case", ["nested", "existing_logs", "ancestor"])
def test_actual_wrappers_stop_before_cache_logs_or_docker(tmp_path, wrapper, case):
    source = prepared(tmp_path)
    tools = tmp_path / "tools/flagging"
    tools.mkdir(parents=True)
    for name in (wrapper, "preflight.py"):
        shutil.copy2(SOURCE_ROOT / "tools/flagging" / name, tools / name)
    run, input_path = "outputs/prepared/new", "outputs/prepared"
    if case == "existing_logs":
        run = "outputs/new"
        (tmp_path / "outputs/new-logs").mkdir()
        (tmp_path / "outputs/new-logs/previous.log").write_bytes(
            b"preserve previous log"
        )
    elif case == "ancestor":
        run, input_path = "outputs/ancestor", "outputs/ancestor/child"
        (tmp_path / input_path).mkdir(parents=True)
    before = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    completed = subprocess.run(
        ["bash", str(tools / wrapper), run, input_path],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert (
        "Flagging preflight" in completed.stderr or "fresh output" in completed.stderr
    )
    after = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert before == after
    assert (source / "protected.dat").read_bytes() == b"immutable input placeholder"
    assert not list((tmp_path / "outputs").glob("*numba-cache"))
    if case == "nested":
        assert list(source.iterdir()) == [source / "protected.dat"]
