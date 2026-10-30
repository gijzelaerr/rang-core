import numpy as np
import pytest
from rang.uncertainty import propagated_standard_deviation


def test_propagation_matches_linear_gaussian_covariance():
    rng = np.random.default_rng(42)
    j, h = rng.normal(size=(30, 5)), rng.normal(size=(9, 5))
    expected = np.sqrt(np.diag(h @ np.linalg.inv(j.T @ j) @ h.T))
    np.testing.assert_allclose(
        propagated_standard_deviation(j, h), expected, rtol=1e-12
    )


def test_uncertainty_rejects_unidentified_parameters():
    with pytest.raises(ValueError, match="rank deficient"):
        propagated_standard_deviation(np.ones((5, 2)), np.eye(2))
    with pytest.raises(ValueError):
        propagated_standard_deviation(np.eye(2), np.eye(3))
    with pytest.raises(ValueError):
        propagated_standard_deviation([[np.nan]], [[1]])
    np.testing.assert_array_equal(
        propagated_standard_deviation(np.zeros((4, 0)), np.zeros((3, 0))), 0
    )
