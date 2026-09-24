import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from rangtoy import flagging_concurrent as concurrent


def put_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value))


def staged(tmp_path, monkeypatch):
    prepared, acquired, root = (
        tmp_path / name for name in ("prepared", "acquired", "suite")
    )
    prepared.mkdir()
    acquired.mkdir()
    for name in ("original.ms", "work.ms"):
        (prepared / name).mkdir()
    (prepared / "state.npz").write_bytes(b"fake-readonly-input")
    put_json(prepared / "manifest.json", {})
    put_json(acquired / "acquisition-complete.json", {"bytes": 123})
    monkeypatch.setattr(concurrent, "_source_hashes", lambda: {"fake": "frozen"})
    monkeypatch.setattr(
        concurrent.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(
            free=concurrent.RESERVE_BYTES + concurrent.SUITE_ALLOCATION_BYTES
        ),
    )
    constructed = []

    def make_case(output, source, pattern, seed):
        constructed.append((output, source, pattern, seed))
        Path(output).mkdir(parents=True)

    monkeypatch.setattr(
        concurrent.importlib,
        "import_module",
        lambda _: SimpleNamespace(make_case=make_case),
    )
    concurrent.initialize(root, prepared, acquired)
    return root, prepared, acquired, constructed


def test_initialize_freezes_six_grouped_cases_before_measurements(
    tmp_path, monkeypatch
):
    root, prepared, _, constructed = staged(tmp_path, monkeypatch)
    assert len(constructed) == 6
    config = json.loads((root / "concurrent-config.json").read_text())
    assert config["scatter"] == 3
    assert config["iterations"] == 50
    assert config["independent_observation_transfer"] is False
    cases = json.loads((root / "transfer-cases.json").read_text())["cases"]
    assert [case["seed"] for case in cases] == [101, 101, 103, 103, 105, 105]
    assert [case["split"] for case in cases] == [
        "train",
        "train",
        "validation",
        "validation",
        "test",
        "test",
    ]
    assert {case["group_id"] for case in cases} == {"seed101", "seed103", "seed105"}
    assert (prepared / "state.npz").read_bytes() == b"fake-readonly-input"
    assert not (root / "experiments").exists()


def test_initialize_refuses_existing_nested_and_bad_iterations(tmp_path, monkeypatch):
    root, prepared, acquired, _ = staged(tmp_path, monkeypatch)
    for output in (root, prepared / "nested", tmp_path):
        with pytest.raises(ValueError):
            concurrent.initialize(output, prepared, acquired)
    for iterations in (True, 49, 50.0):
        with pytest.raises(ValueError):
            concurrent.initialize(tmp_path / "fresh", prepared, acquired, iterations)


def test_initialize_refuses_incomplete_acquisition_and_disk_budget(
    tmp_path, monkeypatch
):
    root, prepared, acquired, _ = staged(tmp_path, monkeypatch)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="acquisition"):
        concurrent.initialize(tmp_path / "fresh", prepared, empty)
    monkeypatch.setattr(
        concurrent.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=concurrent.RESERVE_BYTES),
    )
    with pytest.raises(ValueError, match="reserve"):
        concurrent.initialize(tmp_path / "fresh", prepared, acquired)
    assert not (tmp_path / "fresh").exists()
    assert root.exists()


def test_worker_failure_retained_and_other_branch_can_finish(tmp_path, monkeypatch):
    root, _, _, _ = staged(tmp_path, monkeypatch)

    def run(output, *args, **kwargs):
        if output.endswith("balanced-clean"):
            raise RuntimeError("simulated failure")
        put_json(Path(output) / "result.json", {"synthetic_test": True})
        return {}

    monkeypatch.setattr(
        concurrent.importlib, "import_module", lambda _: SimpleNamespace(run=run)
    )
    monkeypatch.setenv("NUMBA_CACHE_DIR", str(tmp_path / "cache"))
    failed = concurrent.run_workstream(root, "balanced-clean")
    assert not failed["complete"]
    assert failed["error"] == "simulated failure"
    success = concurrent.run_workstream(root, "time-burst-seed101")
    assert success["complete"]
    assert (root / "status-balanced-clean.json").is_file()
    assert (root / "status-time-burst-seed101.json").is_file()


def test_worker_refuses_unknown_and_source_changes(tmp_path, monkeypatch):
    root, _, _, _ = staged(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="unknown"):
        concurrent.run_workstream(root, "../escape")
    monkeypatch.setattr(concurrent, "_source_hashes", lambda: {"fake": "changed"})
    with pytest.raises(ValueError, match="changed"):
        concurrent.run_workstream(root, "signal")
    assert not (root / "status-signal.json").exists()


def test_transfer_waits_for_actual_labels(tmp_path, monkeypatch):
    root, _, _, _ = staged(tmp_path, monkeypatch)
    monkeypatch.setattr(
        concurrent.importlib, "import_module", lambda _: pytest.fail("must not fit")
    )
    status = concurrent.fit_transfer(root)
    assert not status["complete"]
    assert "labels unavailable" in status["error"]
    assert not (root / "experiments" / "transfer").exists()


def test_transfer_calls_frozen_group_input_after_all_required_labels(
    tmp_path, monkeypatch
):
    root, _, _, _ = staged(tmp_path, monkeypatch)
    for case in concurrent.CASES:
        put_json(root / f"status-{case}.json", {"complete": True})
    called = []

    def run(output, cases_path):
        called.append(cases_path)
        put_json(Path(output) / "result.json", {"synthetic_test": True})

    monkeypatch.setattr(
        concurrent.importlib, "import_module", lambda _: SimpleNamespace(run=run)
    )
    assert concurrent.fit_transfer(root)["complete"]
    assert called == [str(root / "transfer-cases.json")]


def test_gather_preserves_missing_status_and_source_audit(tmp_path, monkeypatch):
    root, prepared, _, _ = staged(tmp_path, monkeypatch)
    (prepared / "state.npz").write_bytes(b"changed-input")
    with pytest.raises(RuntimeError, match="preserved checkpoints"):
        concurrent.gather(root)
    result = json.loads((root / "result.json").read_text())
    assert result["all_complete"] is False
    assert result["audit"]["prepared_source_unchanged"] is False
    assert len(result["failures"]) == 11
