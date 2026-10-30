"""Analytic controls for information supplied by nuisance-parameter constraints."""

import pytest

pytest.importorskip("jax")
import numpy as np
from rang.observability import nuisance_information_budget


def test_exact_degeneracy_with_external_anchor():
    # y = pointing + nuisance + noise, with a unit-sigma nuisance prior.
    result = nuisance_information_budget(np.eye(2), np.eye(2), np.eye(2))
    np.testing.assert_allclose(result["data_only_information"], 0, atol=1e-28)
    np.testing.assert_allclose(result["conditioned_data_information"], 0.25 * np.eye(2))
    np.testing.assert_allclose(result["external_information"], 0.25 * np.eye(2))
    np.testing.assert_allclose(result["total_information"], 0.5 * np.eye(2))
    np.testing.assert_allclose(result["local_covariance"], 2 * np.eye(2))
    np.testing.assert_allclose(result["data_only_fraction_eigenvalues"], 0, atol=1e-28)


def test_information_partition_and_nuisance_reparameterization():
    rng = np.random.default_rng(17)
    b, a, l = rng.normal(size=(12, 2)), rng.normal(size=(12, 4)), np.eye(4)
    result = nuisance_information_budget(b, a, l)
    change = np.diag([0.1, 0.5, 2, 10])
    changed = nuisance_information_budget(b, a @ change, l @ change)
    for key in (
        "data_only_information",
        "conditioned_data_information",
        "external_information",
        "total_information",
        "local_covariance",
    ):
        np.testing.assert_allclose(changed[key], result[key], rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(
        np.asarray(result["conditioned_data_information"])
        + result["external_information"],
        result["total_information"],
    )
    assert all(0 <= x <= 1 for x in result["data_only_fraction_eigenvalues"])
    unanchored = nuisance_information_budget(np.eye(2), np.eye(2), np.zeros((0, 2)))
    assert unanchored["constrained_rank"] == 0
    assert unanchored["local_covariance"] is None


def test_invalid_information_designs():
    with pytest.raises(ValueError, match="incompatible"):
        nuisance_information_budget(np.eye(2), np.eye(3), np.eye(2))
    with pytest.raises(ValueError, match="finite"):
        nuisance_information_budget(np.eye(2) * np.nan, np.eye(2), np.eye(2))
