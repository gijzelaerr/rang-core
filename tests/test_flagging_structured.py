"""Structured selection must prefer no-change and ignore test labels."""

import pytest
from rangtoy import flagging_structured


def record(mask_id, objective, fraction=0.01, test=1e20, guard=True):
    return {
        "mask_id": mask_id,
        "objective": objective,
        "guard_pass": guard,
        "metrics": {"added_fraction": fraction, "losses": {"test": test}},
    }


def test_selection_uses_only_budgeted_ranking_and_strict_improvements():
    records = [record("a", 1.25), record("b", 1.24), record("c", 1.0)]
    assert flagging_structured.choose_action(records, ["a"], 1.25) is None
    assert flagging_structured.choose_action(records, ["a", "b"], 1.25) == "b"
    assert flagging_structured.choose_action(records, [], 1.25) is None


def test_test_labels_never_choose_action_and_rejections_cannot_win():
    records = [record("a", 1.24, test=0), record("b", 1.23, test=1e20)]
    assert flagging_structured.choose_action(records, ["a", "b"], 1.25) == "b"
    records[0]["metrics"]["losses"]["test"] = 1e40
    records[1]["metrics"]["losses"]["test"] = 0
    assert flagging_structured.choose_action(records, ["a", "b"], 1.25) == "b"
    records[1]["guard_pass"] = False
    assert flagging_structured.choose_action(records, ["a", "b"], 1.25) == "a"
    records[0]["objective"] = float("nan")
    assert flagging_structured.choose_action(records, ["a", "b"], 1.25) is None


def test_equal_objectives_prefer_less_flagging_then_stable_mask_id():
    records = [record("z", 1.2, 0.01), record("b", 1.2, 0.001), record("a", 1.2, 0.001)]
    assert flagging_structured.choose_action(records, ["a", "b", "z"], 1.25) == "a"


@pytest.mark.parametrize("reverse", [False, True])
def test_nested_paths_rejected_before_outputs(tmp_path, reverse):
    source, output = tmp_path / "input", tmp_path / "input/output"
    source.mkdir()
    if reverse:
        source, output = output, source
    with pytest.raises(ValueError, match="not be nested"):
        flagging_structured.run(output, source)
    assert not (tmp_path / "input/output").exists()


@pytest.mark.parametrize("budget,iterations", [(9, 50), (8, 0), (8, True), (8, 1.5)])
def test_settings_rejected_before_creating_output(tmp_path, budget, iterations):
    with pytest.raises(ValueError, match="frozen ranking"):
        flagging_structured.run(
            tmp_path / "output", tmp_path / "input", budget, iterations
        )
    assert not (tmp_path / "output").exists()
