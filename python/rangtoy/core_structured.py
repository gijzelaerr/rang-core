"""Matched structured-action search with actual frozen full-Jones TV objectives.

Verbatim extract of the frozen `rangtoy.flagging_structured` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_structured.py at commit
2da566c (now history/python/flagging_structured.py),
sha256 6586bdf96eb9978f702d8d0f32796d070d3bbe0184b12e3801234811cc9c2feb.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import numpy as np


def choose_action(records, ranking_ids, baseline_objective):
    """Choose an admissible strict improvement without consulting any test loss."""
    admissible = [
        record
        for record in records
        if record["mask_id"] in ranking_ids
        and record.get("guard_pass", False)
        and record.get("objective") is not None
        and np.isfinite(record["objective"])
        and record["objective"] < baseline_objective
    ]
    return (
        min(
            admissible,
            key=lambda record: (
                record["objective"],
                record["metrics"]["added_fraction"],
                record["mask_id"],
            ),
        )["mask_id"]
        if admissible
        else None
    )


def _compact(candidate):
    return {key: value for key, value in candidate.items() if key != "indices"}
