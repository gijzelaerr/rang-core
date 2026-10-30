"""Sky-track model conventions and fixed-comparison safeguards.

Live part of tests/test_flagging_sky.py at commit 2da566c
(now history/tests/test_flagging_sky.py,
sha256 a6b3c2548f626bfba4cdf5e243600e13616cc6168f42853a32a96c9b1671da03):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

import numpy as np
from rangtoy.core_catalog import point_catalog_predict


def test_independent_point_dft_and_additive_ordinary_spectrum():
    frequencies = np.array([1e9, 1.5e9, 2e9])
    result = point_catalog_predict(
        [[0, 0, 0], [40, 30, 20]],
        [[1, -0.5]],
        [1, -0.5],
        frequencies,
        [10],
        [[2, 3]],
        [1e9],
    )
    # At phase centre all fringe phases vanish. Coefficients are additive Jy.
    np.testing.assert_allclose(result, [[10, 11.75, 15]] * 2, atol=1e-12)
    offset = np.array([[1.1, -0.5]])
    result = point_catalog_predict(
        [[10, 0, 0]], offset, [1, -0.5], [1e9], [2], [[0]], [1e9]
    )
    expected = 2 * np.exp(
        2j * np.pi * 10 * np.cos(-0.5) * np.sin(0.1) * 1e9 / 299792458
    )
    np.testing.assert_allclose(result, [[expected]], atol=1e-12)
