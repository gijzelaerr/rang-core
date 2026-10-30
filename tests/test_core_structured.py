"""Structured selection must prefer no-change and ignore test labels.

Live part of tests/test_flagging_structured.py at commit 2da566c
(now history/tests/test_flagging_structured.py,
sha256 12102754994be7289453bbd173ee96d579dab7e5986cf0eecd07b7354a7ce657):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

from rang import core_structured as flagging_structured


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
