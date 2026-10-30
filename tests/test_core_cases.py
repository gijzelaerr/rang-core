"""Full-matrix phase symmetry, frozen controls and missing outcome boundaries.

Live part of tests/test_flagging_equivariance.py at commit 2da566c
(now history/tests/test_flagging_equivariance.py,
sha256 09e4f355f94807960f029b4a4085f1658748263c99fd5f6ccc4e0f711280dd85):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

import numpy as np
import pytest
from rangtoy.core_cases import phase_factors


def test_identity_and_short_time_span_freeze():
    factors = phase_factors([0, 0.25], [1.07e9], "smooth-time")
    np.testing.assert_allclose(
        factors[1, 0], np.exp(1j * np.array([0, 0.2, -0.2, 0.4]))
    )
    np.testing.assert_array_equal(
        phase_factors([5], [1.07e9], "smooth-time"), np.ones((1, 1, 4))
    )
    np.testing.assert_array_equal(
        phase_factors([1, 2], [1.07e9, 1.08e9], "identity"), np.ones((2, 2, 4))
    )


@pytest.mark.parametrize(
    "times,frequencies,pattern",
    [
        ([], [1.07e9], "identity"),
        ([0, 0], [1.07e9], "identity"),
        ([0], [np.nan], "both"),
        ([0], [1.07e9], "not-frozen"),
    ],
)
def test_invalid_phase_controls_refused(times, frequencies, pattern):
    with pytest.raises(ValueError):
        phase_factors(times, frequencies, pattern)
