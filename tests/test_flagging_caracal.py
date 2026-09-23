"""Pinned full-strategy boundaries, native command and honest control scoring."""

import numpy as np
import pytest
from rangtoy import flagging_caracal


def test_strategy_validation_rejects_unflag_and_missing_original_union():
    valid = [{"task": "sum_threshold"}, {"task": "combine_with_input_flags"}]
    flagging_caracal.validate_strategy_steps(valid)
    with pytest.raises(ValueError, match="unflag"):
        flagging_caracal.validate_strategy_steps([{"task": "unflag"}, *valid])
    with pytest.raises(ValueError, match="end with"):
        flagging_caracal.validate_strategy_steps(valid[:-1])
    with pytest.raises(ValueError, match="nonempty"):
        flagging_caracal.validate_strategy_steps([])


def test_modified_or_unknown_strategy_rejected_before_yaml_dependency(tmp_path):
    path = tmp_path / "calibrator_mild_flagging.yaml"
    path.write_text("altered research input")
    with pytest.raises(ValueError, match="altered pinned"):
        flagging_caracal.strategy_provenance(path)


def test_native_command_matches_caracal_polarisation_and_preserves_flags():
    command = flagging_caracal.native_command(
        "/isolated/bin/python", "copy.ms", "pinned.yaml"
    )
    assert command[0] == "/isolated/bin/tricolour"
    assert command[command.index("--flagging-strategy") + 1] == "polarisation"
    assert command[command.index("--data-column") + 1] == "DATA"
    assert "--ignore-flags" not in command
    assert "--subtract-model-column" not in command
    assert "--disable-post-mortem" in command


def test_native_flag_import_never_changes_heldout_eligibility():
    state = {"data": np.zeros((3, 5, 4), complex), "train": np.zeros((3, 5), bool)}
    state["train"][0, 1:3] = True
    flags = np.ones_like(state["data"], bool)
    proposal = flagging_caracal.training_proposal(state, flags)
    np.testing.assert_array_equal(proposal, state["train"])
    flags[:] = False
    flags[0, 1, 2] = True
    assert flagging_caracal.training_proposal(state, flags).sum() == 1
    with pytest.raises(ValueError, match="bool correlation"):
        flagging_caracal.training_proposal(state, flags.astype(int))


def test_control_guards_never_use_test_metric():
    baseline = {"tv": 2.0, "losses": {"validation": 10.0}}
    metrics = {"added_fraction": 0.01, "losses": {"validation": 9.0, "test": 1e12}}
    first = flagging_caracal.score_control(metrics, 1.9, baseline)
    metrics["losses"]["test"] = -1e12
    assert first == flagging_caracal.score_control(metrics, 1.9, baseline)
    assert first["guard_pass"] and first["objective"] == pytest.approx(1.195)
    metrics["added_fraction"] = 0.021
    assert not flagging_caracal.score_control(metrics, 1.9, baseline)["guard_pass"]
    assert not flagging_caracal.score_control(metrics, None, baseline)["guard_pass"]
    metrics["losses"]["validation"] = 10.2
    assert (
        len(flagging_caracal.score_control(metrics, None, baseline)["guard_reasons"])
        == 3
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_input_output_nesting_rejected_before_creation(tmp_path, reverse):
    source, output = tmp_path / "prepared", tmp_path / "prepared/new"
    source.mkdir()
    if reverse:
        source, output = output, source
    with pytest.raises(ValueError, match="not be nested"):
        flagging_caracal.run(output, source, tmp_path / "strategies")
    assert not (tmp_path / "prepared/new").exists()


def test_unknown_settings_rejected_without_native_dependencies(tmp_path):
    with pytest.raises(ValueError, match="unique strategies"):
        flagging_caracal.run(
            tmp_path / "new",
            tmp_path / "source",
            tmp_path / "strategies",
            strategies=["../../outside.yaml"],
        )
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1.0])
@pytest.mark.parametrize(
    "field",
    ["validation", "baseline_validation", "fixed_tv", "baseline_tv", "fraction"],
)
def test_nonfinite_or_negative_diagnostic_inputs_cannot_pass_guard(field, invalid):
    baseline = {"tv": 2.0, "losses": {"validation": 10.0}}
    metrics = {"added_fraction": 0.01, "losses": {"validation": 9.0}}
    fixed_tv = 1.9
    if field == "validation":
        metrics["losses"]["validation"] = invalid
    elif field == "baseline_validation":
        baseline["losses"]["validation"] = invalid
    elif field == "fixed_tv":
        fixed_tv = invalid
    elif field == "baseline_tv":
        baseline["tv"] = invalid
    else:
        metrics["added_fraction"] = invalid
    result = flagging_caracal.score_control(metrics, fixed_tv, baseline)
    assert not result["guard_pass"]
    assert result["objective"] is None
