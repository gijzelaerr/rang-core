"""Prepared-state preservation/leakage boundaries without casacore."""

from copy import deepcopy

import numpy as np
import pytest
from rangtoy import flagging_prepared
from rangtoy.flagging_prepared import (
    reject_nested_paths,
    validate_prepared_arrays,
    validate_prepared_manifest,
    validate_prepared_state,
)


def boundaries():
    shape = (4, 6, 4)
    data = np.ones(shape, complex)
    flags = np.zeros(shape, bool)
    flags[0, 0, 1] = True
    rows = np.array([False, False, True, False])
    p, q = np.array([0, 0, 0, 1]), np.array([1, 1, 1, 1])
    train, validation, test = [np.zeros(shape[:2], bool) for _ in range(3)]
    train[0, 1:3] = True
    validation[1, 1:3] = True
    test[1, 3:5] = True
    window = np.array([True, True, True, True, True, False])
    model = np.zeros(shape, complex)
    model[..., 0] = model[..., 3] = 14
    state = {
        "data": data,
        "original_flags": flags,
        "original_rows": rows,
        "weights": np.ones(shape),
        "model": model,
        "times": np.arange(shape[0], dtype=float),
        "antenna1": p,
        "antenna2": q,
        "frequencies": np.linspace(1.1e9, 1.2e9, shape[1]),
        "names": np.array(["m000", "m001"]),
        "train": train,
        "validation": validation,
        "test": test,
        "window": window,
    }
    original = {
        "data": data.copy(),
        "flags": flags.copy(),
        "rows": rows.copy(),
        **{
            key: state[key].copy()
            for key in ("weights", "times", "antenna1", "antenna2")
        },
    }
    work = {**deepcopy(original), "model": model.copy()}
    metadata = {
        key: {
            "telescope": ["MeerKAT"],
            "frequencies": state["frequencies"].copy(),
            "names": state["names"].copy(),
            "correlations": np.array([[9, 10, 11, 12]]),
            "spw_rows": 1,
        }
        for key in ("original", "work")
    }
    return state, original, work, metadata


def test_prepared_boundary_accepts_unchanged_and_documented_injected_data():
    state, original, work, metadata = boundaries()
    audit = validate_prepared_arrays(state, original, work, metadata)
    assert audit["validated"] and not audit["working_data_differs_from_original"]
    state["data"][state["train"]] += 3j
    work["data"] = state["data"].copy()
    audit = validate_prepared_arrays(state, original, work, metadata)
    assert audit["working_data_differs_from_original"]
    assert audit["original_flags_and_rows_match"]


@pytest.mark.parametrize(
    "field,index", [("original_flags", (0, 0, 1)), ("original_rows", 2)]
)
def test_saved_state_cannot_hide_actual_original_flags(field, index):
    state, original, work, metadata = boundaries()
    state[field][index] = False
    with pytest.raises(ValueError, match="original FLAG"):
        validate_prepared_arrays(state, original, work, metadata)


@pytest.mark.parametrize(
    "table,field",
    [("work", "data"), ("work", "model"), ("work", "weights"), ("original", "weights")],
)
def test_data_model_and_active_native_weights_are_authoritative(table, field):
    state, original, work, metadata = boundaries()
    actual = original if table == "original" else work
    actual[field][0, 1, 0] += 1
    with pytest.raises(ValueError, match="boundary mismatch"):
        validate_prepared_arrays(state, original, work, metadata)


@pytest.mark.parametrize("index", [(0, 0), (2, 1), (3, 1), (0, 5)])
def test_split_masks_exclude_original_cells_rows_autos_and_outside_window(index):
    state, original, work, metadata = boundaries()
    state["train"][index] = True
    with pytest.raises(ValueError, match="protected/ineligible"):
        validate_prepared_arrays(state, original, work, metadata)


def test_visibility_holdout_leakage_and_non_boolean_masks_are_rejected():
    state, original, work, metadata = boundaries()
    state["validation"][0, 1] = True
    with pytest.raises(ValueError, match="overlap"):
        validate_prepared_arrays(state, original, work, metadata)
    state, original, work, metadata = boundaries()
    state["train"] = state["train"].astype(int)
    with pytest.raises(ValueError, match="bool shape"):
        validate_prepared_arrays(state, original, work, metadata)


@pytest.mark.parametrize("invalid", [np.nan, 0.0, -1.0])
def test_nonfinite_and_nonpositive_weight_samples_cannot_enter_any_split(invalid):
    state, original, work, metadata = boundaries()
    for actual in (state, original, work):
        actual["weights"][1, 3, 0] = invalid
    with pytest.raises(ValueError, match="test split includes"):
        validate_prepared_arrays(state, original, work, metadata)


def test_polar_model_requires_finite_unpolarized_scalar_correlations():
    state, original, work, metadata = boundaries()
    state["model"][0, 1, 1] = 1
    work["model"] = state["model"].copy()
    with pytest.raises(ValueError, match="unpolarized scalar"):
        validate_prepared_arrays(state, original, work, metadata)
    state["model"][0, 1, 1] = np.nan
    work["model"] = state["model"].copy()
    with pytest.raises(ValueError, match="finite four"):
        validate_prepared_arrays(state, original, work, metadata)


def test_original_nonfinite_data_cannot_be_made_eligible_by_injection():
    state, original, work, metadata = boundaries()
    original["data"][0, 1, 0] = np.nan
    with pytest.raises(ValueError, match="train split includes"):
        validate_prepared_arrays(state, original, work, metadata)


def test_manifest_channels_splits_and_gain_grid_must_describe_actual_state():
    state, _, _, _ = boundaries()
    manifest = {
        "channels": [0, 5],
        "split_gain_intervals": [2, 2],
        "split_counts": {
            key: int(state[key].sum()) for key in ("train", "validation", "test")
        },
    }
    assert validate_prepared_manifest(state, manifest)[
        "manifest_channels_and_split_counts_match"
    ]
    changed = deepcopy(manifest)
    changed["channels"] = [1, 5]
    with pytest.raises(ValueError, match="manifest channel window"):
        validate_prepared_manifest(state, changed)
    changed = deepcopy(manifest)
    changed["split_counts"]["train"] += 1
    with pytest.raises(ValueError, match="train split count"):
        validate_prepared_manifest(state, changed)
    for grid in ([0, 2], [2.0, 2], [True, 2], [2]):
        changed = {**manifest, "split_gain_intervals": grid}
        with pytest.raises(ValueError, match="positive integers"):
            validate_prepared_manifest(state, changed)


def test_actual_observation_metadata_enforces_meerkat_lband_and_coordinates():
    state, original, work, metadata = boundaries()
    metadata["original"]["telescope"] = ["VLA"]
    with pytest.raises(ValueError, match="MeerKAT observation"):
        validate_prepared_arrays(state, original, work, metadata)
    metadata["original"]["telescope"] = ["MeerKAT"]
    metadata["work"]["frequencies"] += 1e9
    with pytest.raises(ValueError, match="L-band"):
        validate_prepared_arrays(state, original, work, metadata)
    state, original, work, metadata = boundaries()
    work["times"][0] += 1
    with pytest.raises(ValueError, match="work times"):
        validate_prepared_arrays(state, original, work, metadata)


def test_working_flags_cannot_already_violate_original_bounds():
    state, original, work, metadata = boundaries()
    work["flags"][0, 0, 1] = False
    with pytest.raises(ValueError, match="original protection"):
        validate_prepared_arrays(state, original, work, metadata)


def test_original_digest_is_checked_before_any_table_access(tmp_path, monkeypatch):
    (tmp_path / "original.ms").mkdir()

    def forbidden_read(*args, **kwargs):
        pytest.fail("digest mismatch must fail before casacore table access")

    monkeypatch.setattr(flagging_prepared, "_read_measurement_set", forbidden_read)
    with pytest.raises(ValueError, match="original MS digest"):
        validate_prepared_state(tmp_path, {}, {"original_copy_digest": "wrong"})


@pytest.mark.parametrize(
    "output,source",
    [("input/new", "input"), ("output", "output/input"), ("same", "same")],
)
def test_nested_paths_rejected_in_either_direction_before_creating_output(
    tmp_path, output, source
):
    with pytest.raises(ValueError, match="must not be nested"):
        reject_nested_paths(tmp_path / output, tmp_path / source)
    assert not (tmp_path / output).exists()
    actual_output, actual_source = reject_nested_paths(
        tmp_path / "new", tmp_path / "existing"
    )
    assert actual_output == tmp_path / "new" and actual_source == tmp_path / "existing"
