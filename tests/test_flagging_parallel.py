"""Exclusive suite ownership, safe dispatch and retained branch failures."""

import json
from hashlib import sha256
from types import SimpleNamespace

import pytest
from rangtoy import flagging_parallel as parallel


def initialized(tmp_path, monkeypatch, modes=("actions", "injections")):
    archive = tmp_path / "fixture.zip"
    archive.write_bytes(b"unit-test fixture, not observational data")
    monkeypatch.setattr(
        parallel, "FIXTURE_SHA256", sha256(archive.read_bytes()).hexdigest()
    )
    root = tmp_path / "suite"
    parallel.initialize(root, archive, workstreams=modes)
    monkeypatch.setenv("NUMBA_CACHE_DIR", str(tmp_path / "cache"))
    return root


def test_suite_creation_is_exclusive_and_resources_checked_before_creation(
    tmp_path, monkeypatch
):
    root = initialized(tmp_path, monkeypatch)
    config = json.loads((root / "parallel-config.json").read_text())
    with pytest.raises(FileExistsError):
        parallel.initialize(root, config["archive"], workstreams=("actions",))
    with pytest.raises(ValueError, match="unique"):
        parallel.initialize(
            tmp_path / "invalid", config["archive"], workstreams=("actions", "actions")
        )
    with pytest.raises(ValueError, match="requires"):
        parallel.initialize(
            tmp_path / "missing-sky", config["archive"], workstreams=("sky",)
        )
    assert (
        not (tmp_path / "invalid").exists() and not (tmp_path / "missing-sky").exists()
    )


def test_workers_dispatch_separate_outputs_and_complete_gather(tmp_path, monkeypatch):
    root = initialized(tmp_path, monkeypatch)
    invoked = []

    def fake_run(**arguments):
        branch = parallel.Path(arguments["run_dir"])
        invoked.append(arguments)
        branch.mkdir(exist_ok=False)
        parallel.write_json(branch / "result.json", {"unit_test": True})

    monkeypatch.setattr(
        parallel.importlib, "import_module", lambda name: SimpleNamespace(run=fake_run)
    )
    # Runtime native scatter gives each worker a separate process/environment.
    for mode in ("actions", "injections"):
        monkeypatch.setenv("NUMBA_CACHE_DIR", str(tmp_path / "cache"))
        parallel.run_workstream(root, mode)
    assert invoked[0]["run_dir"] != invoked[1]["run_dir"]
    assert invoked[0]["action_count"] == 16 and invoked[1]["strengths"] == [3, 10]
    parallel.gather(root)
    result = json.loads((root / "result.json").read_text())
    assert result["all_complete"] and not result["failures"]
    with pytest.raises(ValueError, match="authorized"):
        parallel.run_workstream(root, "../actions")


def test_failed_worker_retained_without_preventing_other_branch(tmp_path, monkeypatch):
    root = initialized(tmp_path, monkeypatch)

    def failing(**arguments):
        raise RuntimeError("deliberate unit-test branch failure")

    def complete(**arguments):
        branch = parallel.Path(arguments["run_dir"])
        branch.mkdir(exist_ok=False)
        parallel.write_json(branch / "result.json", {"unit_test": True})

    monkeypatch.setattr(
        parallel.importlib,
        "import_module",
        lambda name: SimpleNamespace(
            run=failing if name.endswith("actions") else complete
        ),
    )
    parallel.run_workstream(root, "actions")
    monkeypatch.setenv("NUMBA_CACHE_DIR", str(tmp_path / "cache"))
    parallel.run_workstream(root, "injections")
    with pytest.raises(RuntimeError, match="branches failed: actions"):
        parallel.gather(root)
    result = json.loads((root / "result.json").read_text())
    assert result["failures"] == ["actions"]
    assert result["branches"]["injections"]["status"]["complete"]
    assert "deliberate" in result["branches"]["actions"]["status"]["error"]


def test_missing_worker_status_is_not_reported_complete(tmp_path, monkeypatch):
    root = initialized(tmp_path, monkeypatch, modes=("actions",))
    with pytest.raises(RuntimeError, match="branches failed"):
        parallel.gather(root)
    result = json.loads((root / "result.json").read_text())
    assert not result["all_complete"] and result["failures"] == ["actions"]
