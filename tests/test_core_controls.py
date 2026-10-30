"""Pinned full-strategy boundaries, native command and honest control scoring.

Live part of tests/test_flagging_caracal.py at commit 2da566c
(now history/tests/test_flagging_caracal.py,
sha256 07d30d1b4738e7d01d1a8889de7182517b1c3bba87e4d9859be31dae33d0da93):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

import numpy as np
import pytest
from rangtoy import core_controls as flagging_caracal


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
