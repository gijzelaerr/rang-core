"""Independent comparator import, masking and coordinate invariants."""

import numpy as np
import pytest
import rangtoy.flagging_comparators as comparators
from rangtoy.flagging import protected_flags
from rangtoy.flagging_comparators import (
    import_proposals,
    injection_recovery,
    pack_training_windows,
    unpack_proposals,
)


def state():
    train = np.array(
        [[True, False, False], [False, True, False], [False, False, False]]
    )
    flags = np.zeros((3, 3, 4), bool)
    flags[0, 2, 1] = True
    return {
        "train": train,
        "original_flags": flags,
        "original_rows": np.array([False, False, True]),
        "data": np.ones((3, 3, 4), complex),
        "times": np.array([2.0, 1.0, 1.0]),
        "antenna1": np.array([0, 0, 0]),
        "antenna2": np.array([1, 1, 0]),
    }


def test_import_restores_all_protected_cells_and_only_adds_train():
    saved = state()
    proposals = import_proposals(saved, np.ones((3, 3, 4), bool))
    np.testing.assert_array_equal(proposals, saved["train"])
    flags, rows = protected_flags(
        saved["original_flags"],
        saved["original_rows"],
        np.broadcast_to(proposals[..., None], saved["original_flags"].shape),
    )
    assert flags[0, 2, 1] and flags[2].all() and rows[2]
    assert flags[0, 0].all() and not flags[0, 1].any()


def test_import_row_flags_and_shape_validation():
    saved = state()
    added = import_proposals(
        saved, np.zeros((3, 3, 4), bool), np.array([True, False, False])
    )
    assert added[0, 0] and added.sum() == 1
    with pytest.raises(ValueError, match="shape"):
        import_proposals(saved, np.zeros((3, 3), bool))
    with pytest.raises(ValueError, match="FLAG_ROW"):
        import_proposals(saved, np.zeros((3, 3, 4), bool), [False])


def test_packing_preserves_time_coordinates_and_never_reads_holdouts():
    saved = state()
    saved["data"][..., 0] = 3
    saved["data"][..., 3] = 5
    saved["data"][~saved["train"]] = 1e12
    windows, flags, rows = pack_training_windows(saved)
    assert windows.shape == (1, 1, 2, 3)
    np.testing.assert_array_equal(rows, [[1, 0]])
    assert windows[0, 0, 0, 1] == 4 and windows[0, 0, 1, 0] == 4
    assert np.count_nonzero(windows) == 2
    assert windows[flags].sum() == 0
    restored = unpack_proposals(np.ones_like(flags), rows, saved["train"])
    np.testing.assert_array_equal(restored, saved["train"])


def test_duplicate_baseline_time_rejected_instead_of_silent_average():
    saved = state()
    saved["times"][0] = saved["times"][1]
    with pytest.raises(ValueError, match="duplicate"):
        pack_training_windows(saved)


def test_unpack_missing_cells_and_shape_guard():
    train = np.ones((2, 3), bool)
    rows = np.array([[0, -1], [-1, 1]])
    flags = np.zeros((2, 1, 2, 3), bool)
    flags[1, 0, 1, 2] = True
    added = unpack_proposals(flags, rows, train)
    assert added.sum() == 1 and added[1, 2]
    with pytest.raises(ValueError, match="shape"):
        unpack_proposals(flags[..., :2], rows, train)


def test_injection_recall_and_unlabelled_outside_flags():
    train = np.array([[True, True, False], [True, True, True]])
    injected = np.array([[True, False, True], [False, True, False]])
    added = np.array([[True, True, False], [False, False, False]])
    metrics = injection_recovery(added, injected, train)
    assert metrics["known_injected_training_samples"] == 2
    assert metrics["recovered_injected_samples"] == 1
    assert metrics["injected_recall"] == 0.5
    assert metrics["additional_flags_outside_injections"] == 1
    assert metrics["outside_injections_fraction"] == pytest.approx(1 / 3)
    assert metrics["outside_injections_are_not_labelled_false_positives"]


@pytest.mark.parametrize(
    "output,source",
    [("input/new", "input"), ("output", "output/input"), ("same", "same")],
)
def test_run_rejects_nested_prepared_paths_before_creating_destination(
    tmp_path, output, source
):
    destination = tmp_path / output
    with pytest.raises(ValueError, match="must not be nested"):
        comparators.run(destination, prepared_dir=tmp_path / source)
    assert not destination.exists()


def test_actual_prepared_boundary_validation_precedes_every_flag_write(
    tmp_path, monkeypatch
):
    destination = tmp_path / "new"

    def fake_prepare(path, **kwargs):
        path.mkdir()
        (path / "manifest.json").write_text("{}")

    def reject_state(*args):
        raise ValueError("authoritative original flags do not match saved state")

    def forbidden_write(*args, **kwargs):
        pytest.fail("flag writes or solver execution preceded boundary validation")

    monkeypatch.setattr(comparators, "prepare", fake_prepare)
    monkeypatch.setattr(comparators, "load_state", lambda path: {})
    monkeypatch.setattr(comparators, "validate_prepared_state", reject_state)
    monkeypatch.setattr(comparators, "set_flags", forbidden_write)
    monkeypatch.setattr(comparators, "solve", forbidden_write)
    with pytest.raises(ValueError, match="authoritative original flags"):
        comparators.run(destination, archive="unused.zip")
    assert not (destination / "comparison-config.json").exists()
