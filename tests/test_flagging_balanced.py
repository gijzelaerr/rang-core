"""Frozen geometry slots, random controls and safe prepared-copy boundaries."""

import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from rangtoy import flagging_balanced as balanced


def candidates():
    return [
        {
            "mask_id": f"{group_index}{index:03}",
            "metadata": {"group": group},
            "residual_score": float(index),
            "tv_score": float(10 - index),
        }
        for group_index, group in enumerate(balanced.GROUPS)
        for index in range(5)
    ]


@pytest.mark.parametrize("mode", balanced.RANKINGS)
def test_all_rankers_take_two_distinct_masks_per_canonical_group(mode):
    selected = balanced.balanced_rank(candidates(), mode)
    assert len(selected) == len({item["mask_id"] for item in selected}) == 6
    assert Counter(item["metadata"]["group"] for item in selected) == {
        group: 2 for group in balanced.GROUPS
    }
    assert [item["metadata"]["group"] for item in selected] == [
        group for group in balanced.GROUPS for _ in range(2)
    ]


@pytest.mark.parametrize("mode", balanced.RANKINGS)
def test_empty_or_short_groups_never_borrow_slots(mode):
    family = [item for item in candidates() if item["metadata"]["group"] != "global"]
    assert len(balanced.balanced_rank(family, mode)) == 4
    family.append(candidates()[0])
    assert len(balanced.balanced_rank(family, mode)) == 5
    assert balanced.balanced_rank([], mode) == []


def test_random_mask_choices_ignore_scores_and_family_iteration_order():
    family = candidates()
    expected = [item["mask_id"] for item in balanced.balanced_rank(family, "random")]
    for item in family:
        item["residual_score"], item["tv_score"] = np.nan, np.inf
    assert [
        item["mask_id"]
        for item in balanced.balanced_rank(list(reversed(family)), "random")
    ] == expected


def test_residual_and_tv_rank_exact_existing_scores_with_hash_ties():
    family = candidates()
    residual = balanced.balanced_rank(family, "residual")
    tv = balanced.balanced_rank(family, "tv")
    assert [item["residual_score"] for item in residual] == [4, 3] * 3
    assert [item["residual_score"] for item in tv] == [0, 1] * 3
    for item in family:
        item["residual_score"] = 1
    tied = balanced.balanced_rank(list(reversed(family)), "residual")
    assert [item["mask_id"] for item in tied] == [
        f"{g}{index:03}" for g in range(3) for index in range(2)
    ]


def test_invalid_protocol_and_duplicate_masks_are_rejected():
    family = candidates()
    with pytest.raises(ValueError, match="seed137"):
        balanced.balanced_rank(family, "random", random_seed=138)
    with pytest.raises(ValueError, match="two slots"):
        balanced.balanced_rank(family, per_group=3)
    with pytest.raises(ValueError, match="distinct masks"):
        balanced.balanced_rank(family + [family[0]])


def prepared_fixture(tmp_path, monkeypatch, *, contaminated=False):
    output, source = tmp_path / "output", tmp_path / "source"
    (output / "backups").mkdir(parents=True)
    source.mkdir()
    shape = (4, 1024, 4)
    flags = np.zeros(shape, bool)
    rows = np.zeros(shape[0], bool)
    train = np.ones(shape[:2], bool)
    validation, test = np.zeros_like(train), np.zeros_like(train)
    train[:, ::7] = False
    validation[:, ::7] = True
    validation[:, ::14] = False
    test[:, ::14] = True
    state = {
        "original_flags": flags,
        "original_rows": rows,
        "data": np.ones(shape, complex),
        "model": np.ones(shape, complex),
        "weights": np.full(shape, 4.0),
        "times": np.arange(shape[0], dtype=float),
        "antenna1": np.zeros(shape[0], int),
        "antenna2": np.ones(shape[0], int),
        "train": train,
        "validation": validation,
        "test": test,
        "window": np.ones(shape[1], bool),
    }
    np.savez_compressed(output / "backups/source-state.npz", **state)
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "original_copy_digest": "fixed",
                "source_digest": "fixed",
                "source": str(source),
            }
        )
    )
    monkeypatch.setattr(
        balanced, "_clone", lambda *_args, **_kwargs: (output, source, "fixed")
    )
    monkeypatch.setattr(balanced, "tree_digest", lambda _path: "fixed")
    monkeypatch.setattr(
        balanced.flagging_prepared,
        "validate_prepared_state",
        lambda *_args: {
            "validated": True,
            "working_data_differs_from_original": contaminated,
        },
    )
    monkeypatch.setattr(
        balanced, "_all_weights", lambda _path: {"WEIGHT": np.ones((4, 4))}
    )
    monkeypatch.setattr(balanced, "_weights_equal", lambda *_args: True)
    return output, source, state


def test_make_case_never_injects_an_already_contaminated_source(tmp_path, monkeypatch):
    output, source, _ = prepared_fixture(tmp_path, monkeypatch, contaminated=True)
    monkeypatch.setattr(
        balanced, "_write_data", lambda *_args: pytest.fail("DATA must not be written")
    )
    with pytest.raises(ValueError, match="requires clean"):
        balanced.make_case(output, source, "time-burst")
    assert not (output / "injection.npz").exists()
    assert not (output / "state.npz").exists()


@pytest.mark.parametrize("pattern", ["time-burst", "antenna-local"])
def test_make_case_has_exact_train_only_delta_and_preserves_original_state(
    tmp_path, monkeypatch, pattern
):
    output, source, original = prepared_fixture(tmp_path, monkeypatch)
    written = []
    monkeypatch.setattr(
        balanced,
        "_write_data",
        lambda _path, data, _label: written.append(data.copy()) or "backup-digest",
    )
    report = balanced.make_case(output, source, pattern)
    assert report["audit"]["training_only_injection"]
    with (
        np.load(output / "state.npz") as active,
        np.load(output / "injection.npz") as truth,
    ):
        mask = truth["injected"]
        assert mask.any() and not mask[~original["train"]].any()
        np.testing.assert_array_equal(active["data"], written[0])
        np.testing.assert_array_equal(active["data"][~mask], original["data"][~mask])
        np.testing.assert_array_equal(
            active["original_flags"], original["original_flags"]
        )
        np.testing.assert_allclose(
            active["data"][mask] - original["data"][mask], truth["delta"]
        )


def test_clone_rejects_nested_paths_before_mkdir(tmp_path):
    source = tmp_path / "prepared"
    source.mkdir()
    with pytest.raises(ValueError, match="must not be nested"):
        balanced._clone(source / "output", source)
    assert list(source.iterdir()) == []


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
