"""Five-track dispatch/schema/boundary contracts, without external operations."""

import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest
from rangtoy import flagging_next as campaign


class LocalBudget:
    """Only test-temp files; no solver, network, MS or real quota interaction."""

    calls: ClassVar[list] = []

    def __init__(self, root, limit):
        self.root, self.limit = Path(root), limit

    def check(self, needed=0):
        self.calls.append((self.root, self.limit, needed))
        return 0

    def mkdir(self, path):
        Path(path).mkdir(parents=True, exist_ok=False)

    def json(self, path, value):
        with Path(path).open("x") as stream:
            json.dump(value, stream, allow_nan=False)


def config_fixture(tmp_path, monkeypatch):
    root = tmp_path / "campaign"
    root.mkdir()
    (root / "experiments").mkdir()
    sources = {}
    for name in (
        "prepared_dir",
        "historical_dir",
        "response_dir",
        "provenance_dir",
        "caracal_dir",
    ):
        source = tmp_path / name
        source.mkdir()
        sources[name] = {"path": str(source), "digest": "stable"}
    config = {
        "sources": sources,
        "runtime_receipts": {"module": "frozen"},
        "allocated_campaign_limit_bytes": 8 * 1024**3,
    }
    (root / "config.json").write_text(json.dumps(config))
    monkeypatch.setattr(campaign, "source_receipts", lambda: {"module": "frozen"})
    monkeypatch.setattr(campaign, "tree_digest", lambda _: "stable")
    monkeypatch.setattr(campaign, "CampaignBudget", LocalBudget)
    monkeypatch.setenv("NUMBA_CACHE_DIR", str(tmp_path / "cache"))
    LocalBudget.calls = []
    return root, config


@pytest.mark.parametrize("track", campaign.TRACKS)
def test_five_isolated_dispatches_with_explicit_imaging_sources(
    tmp_path, monkeypatch, track
):
    root, config = config_fixture(tmp_path, monkeypatch)
    calls = []
    imported = []

    def import_module(name):
        imported.append(name)
        return SimpleNamespace(
            run=lambda *args: calls.append(args) or {"mocked": track}
        )

    monkeypatch.setattr(campaign.importlib, "import_module", import_module)
    result = campaign.run_track(root, track)
    assert result == {"mocked": track}
    assert calls[0][0] == root / "experiments" / track
    module = "signal_guard" if track == "signal" else track
    assert imported == [f"rangtoy.flagging_{module}"]
    if track == "signal":
        assert calls[0][1] == [
            root / "inputs/cases/time-burst-seed107",
            root / "inputs/cases/time-burst-seed109",
        ]
    elif track == "prospective":
        assert calls[0][1] == root / "inputs"
    elif track == "imaging":
        assert calls[0][1:] == (
            config["sources"]["response_dir"]["path"],
            config["sources"]["caracal_dir"]["path"],
        )
    else:
        source = "historical_dir" if track == "trend" else "provenance_dir"
        assert calls[0][1] == config["sources"][source]["path"]
    assert LocalBudget.calls[-1] == (root, 8 * 1024**3, 0)
    assert (tmp_path / "cache" / track).is_dir()


@pytest.mark.parametrize(
    "mutation", ["unknown", "runtime", "source", "existing", "symlink"]
)
def test_invalid_dispatch_refused_before_import_or_cache_write(
    tmp_path, monkeypatch, mutation, symlink
):
    root, _ = config_fixture(tmp_path, monkeypatch)
    track = "trend"
    if mutation == "unknown":
        track = "../../outside"
    elif mutation == "runtime":
        monkeypatch.setattr(campaign, "source_receipts", lambda: {"module": "changed"})
    elif mutation == "source":
        monkeypatch.setattr(campaign, "tree_digest", lambda _: "changed")
    elif mutation == "existing":
        (root / "experiments/trend").mkdir()
    else:
        symlink(root / "experiments/trend", tmp_path / "missing")
    monkeypatch.setattr(
        campaign.importlib,
        "import_module",
        lambda _: pytest.fail("must not import/dispatch"),
    )
    with pytest.raises((ValueError, RuntimeError, FileExistsError)):
        campaign.run_track(root, track)
    assert not (tmp_path / "cache").exists()


def test_initialize_freezes_five_sources_and_checked_worker_resource_contract(
    tmp_path, monkeypatch
):
    sources = {}
    for name in (
        "prepared_dir",
        "historical_dir",
        "response_dir",
        "provenance_dir",
        "caracal_dir",
    ):
        path = tmp_path / name
        path.mkdir()
        sources[name] = path
    root = tmp_path / "fresh"
    monkeypatch.setattr(campaign, "CampaignBudget", LocalBudget)
    monkeypatch.setattr(campaign, "source_receipts", lambda: {"module": "frozen"})
    monkeypatch.setattr(campaign, "tree_digest", lambda _: "stable")
    prepared_calls = []
    monkeypatch.setattr(
        campaign, "prepare_inputs", lambda *args: prepared_calls.append(args)
    )
    LocalBudget.calls = []
    config = campaign.initialize(root, **sources)
    assert set(config["sources"]) == set(sources)
    assert (
        config["tracks"]
        == campaign.TRACKS
        == ("trend", "prospective", "signal", "provenance", "imaging")
    )
    assert config["scatter_workers"] == 3
    assert config["maximum_concurrent_QC_workers"] == 2
    assert config["maximum_concurrent_imagers"] == 1
    assert config["runtime_network"] == "none"
    assert config["allocated_campaign_limit_bytes"] == 8 * 1024**3
    assert config["logical_provenance_limit_bytes"] == 8 * 1024**2
    assert not config["independent_observation_transfer"]
    assert LocalBudget.calls[0] == (root, 8 * 1024**3, 7 * 1024**3)
    assert prepared_calls == [(root / "inputs", sources["prepared_dir"])]


@pytest.mark.parametrize("mutation", ["runtime", "source", "missing_result"])
def test_gather_refuses_mutation_or_missing_branches_and_never_writes_result(
    tmp_path, monkeypatch, mutation
):
    root, _ = config_fixture(tmp_path, monkeypatch)
    for track in campaign.TRACKS:
        directory = root / "experiments" / track
        directory.mkdir()
        if mutation != "missing_result" or track != "imaging":
            (directory / "result.json").write_text(json.dumps({"track": track}))
    if mutation == "runtime":
        monkeypatch.setattr(campaign, "source_receipts", lambda: {"module": "changed"})
    elif mutation == "source":
        monkeypatch.setattr(campaign, "tree_digest", lambda _: "changed")
    with pytest.raises((RuntimeError, FileNotFoundError)):
        campaign.gather(root)
    assert not (root / "result.json").exists()


def test_gather_all_five_results_without_inventing_scientific_success(
    tmp_path, monkeypatch
):
    root, _ = config_fixture(tmp_path, monkeypatch)
    for track in campaign.TRACKS:
        directory = root / "experiments" / track
        directory.mkdir()
        (directory / "result.json").write_text(
            json.dumps({"track": track, "diagnostic_only": True})
        )
    result = campaign.gather(root)
    assert set(result["tracks"]) == set(campaign.TRACKS)
    assert all(result["audit"].values())
    assert "not a validated science flagger" in result["status"]


def test_source_receipts_cover_modules_rust_recipes_and_actual_native_file(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    files = {
        "python/rangtoy/flagging_next.py": b"campaign",
        "python/rangtoy/flagging_signal_guard.py": b"signal",
        "src/lib.rs": b"Rust",
        "recipes/tv-flagging-next.yaml": b"recipe",
        "recipes/unrelated.yaml": b"not a flagging recipe",
        "Cargo.toml": b"manifest",
        "Cargo.lock": b"lock",
        "pyproject.toml": b"python manifest",
        "tools/flagging/run-next.sh": b"wrapper",
        "tools/flagging/Dockerfile": b"base image",
        "tools/flagging/next/Dockerfile": b"suite image",
        "tools/flagging/requirements.lock.txt": b"dependencies",
        "tools/flagging/next/helper.py": b"entrypoint",
        "tools/flagging/unrelated.bin": b"not source",
        "native/lib.so": b"native",
    }
    for name, value in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    monkeypatch.setattr(
        campaign, "__file__", str(root / "python/rangtoy/flagging_next.py")
    )
    monkeypatch.setattr(
        campaign,
        "_native_library",
        lambda: SimpleNamespace(_name=str(root / "native/lib.so")),
    )
    receipts = campaign.source_receipts()
    assert str(root / "recipes/unrelated.yaml") not in receipts
    assert str(root / "tools/flagging/unrelated.bin") not in receipts
    assert set(receipts) == {
        str(root / name)
        for name in files
        if name not in ("recipes/unrelated.yaml", "tools/flagging/unrelated.bin")
    }
    assert receipts[str(root / "native/lib.so")] == sha256(b"native").hexdigest()
    (root / "native/lib.so").write_bytes(b"changed")
    assert campaign.source_receipts() != receipts
