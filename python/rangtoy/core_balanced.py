"""Frozen geometry-balanced whole-rectangle search, not observation transfer.

Verbatim extract of the frozen `rangtoy.flagging_balanced` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_balanced.py at commit
2da566c (now history/python/flagging_balanced.py),
sha256 8fd6ada217130689067dda7c0379f20c0d43f1a445ace9f3debb0d172892d141.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import numpy as np

from . import core_proposals as flagging_structured_proposals

GROUPS = ("global", "antenna-star", "baseline")


RANKINGS = ("residual", "tv", "random")


RANDOM_SEED = 137


def balanced_rank(candidates, mode="residual", per_group=2, random_seed=RANDOM_SEED):
    """Pick two distinct canonical masks per group without borrowing slots.

    Geometry aliases follow the existing generator's first canonical metadata;
    a mask cannot count as two different groups. Random draws use lists sorted
    by mask SHA256 and one seed137 RNG consumed in GROUPS order. Neither family
    iteration order, score values (random mode) nor held-out values affect draws.
    """
    if mode not in RANKINGS or per_group != 2 or random_seed != RANDOM_SEED:
        raise ValueError(
            "frozen residual/tv/random ranking, two slots and seed137 required"
        )
    if len({item["mask_id"] for item in candidates}) != len(candidates):
        raise ValueError("balanced ranking requires distinct masks")
    if any(item["metadata"]["group"] not in GROUPS for item in candidates):
        raise ValueError("unexpected canonical geometry group")
    rng = np.random.default_rng(random_seed)
    result = []
    for group in GROUPS:
        items = [item for item in candidates if item["metadata"]["group"] == group]
        if mode == "random":
            items = sorted(items, key=lambda item: item["mask_id"])
            if items:
                indices = rng.choice(
                    len(items), min(per_group, len(items)), replace=False
                )
                result.extend(items[int(index)] for index in indices)
        else:
            result.extend(
                flagging_structured_proposals.rank_candidates(
                    items, mode=mode, limit=per_group
                )
            )
    return result
