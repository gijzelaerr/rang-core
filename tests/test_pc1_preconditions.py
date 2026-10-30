"""The L1 and L2 campaign preconditions end to end (research/pc1-preconditions.md).

Both replay K's frozen run -01 on K's four stations through the array and
PKS 1830 drivers. Nothing else in the suite reaches those replay paths, so a
change to a shared helper (P5's index-form additions) or to the image bits
(P2) broke them unnoticed. About 10 s each; skipped when the archived LUNO
inputs or K's run -01 are not on this host.
"""

from pathlib import Path

import pytest
from rangtoy import core_campaign_1830 as l2
from rangtoy import core_campaign_array as array

SURVEY_COLUMNS = ("MODEL_DATA", "FLAG", "WEIGHT_SPECTRUM")


def _present(keys, roots):
    return all(any((Path(r) / k).exists() for r in roots) for k in keys)


def _k_present():
    return (
        (array.K_RUN / "result.json").exists()
        and (array.K_RUN / "candidates.json").exists()
        and _present(array.input_keys(), array.ROOTS)
    )


needs_k = pytest.mark.skipif(not _k_present(), reason="LUNO inputs or K run -01 absent")


@needs_k
def test_l1_precondition_replays_k(tmp_path):
    result = array.precondition(tmp_path / "l1")
    assert result["passed"] == {"k_precondition": True, "replay": True, "groups": True}
    # The exact comparison differs on image products only (P2).
    exact = result["replay"]
    assert exact["tolerant"]["all_equal"]
    for label, same in exact["arms"].items():
        if isinstance(same, dict):
            assert all(v for k, v in same.items() if not k.startswith("image_")), label
    assert all(exact["candidates"].values())
    assert all(exact["tricolour_newly_flagged"].values())


@needs_k
@pytest.mark.skipif(
    not _present(l2.tile_keys(l2.GROUP, SURVEY_COLUMNS), l2.roots_for(l2.GROUP)),
    reason="PKS 1830 inputs absent",
)
def test_l2_precondition_replays_k(tmp_path):
    result = l2.precondition(tmp_path / "l2")
    assert result["passed"] == {"k_precondition": True, "replay": True, "survey": True}
