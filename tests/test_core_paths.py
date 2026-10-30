"""Prepared-state preservation/leakage boundaries without casacore.

Live part of tests/test_flagging_prepared.py at commit 2da566c
(now history/tests/test_flagging_prepared.py,
sha256 121e47f17c361e3ab4cabc1ec561791653e591405c78337d47c30f55a20a2257):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

import pytest
from rang.core_paths import reject_nested_paths


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
