"""Frozen geometry slots, random controls and safe prepared-copy boundaries.

Live part of tests/test_flagging_balanced.py at commit 2da566c
(now history/tests/test_flagging_balanced.py,
sha256 576fe35d2a52cd6c8ceba21588c4a82def0bef5878252fed4a8916db88935be5):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

from collections import Counter

import numpy as np
import pytest
from rang import core_balanced as balanced


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
