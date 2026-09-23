"""Sky-track model conventions and fixed-comparison safeguards."""

import numpy as np
import pytest
from rangtoy.flagging_sky import (
    array_digest,
    comparison_summary,
    model_provenance,
    point_catalog_predict,
    require_scalar_model,
)


def test_scalar_sky_required_for_common_polar_gauge():
    sky = np.zeros((2, 3, 4), complex)
    sky[..., 0] = sky[..., 3] = 2 + 3j
    assert require_scalar_model(sky, sky.shape) is sky
    bad = sky.copy()
    bad[0, 0, 1] = 0.1
    with pytest.raises(ValueError, match="unpolarized"):
        require_scalar_model(bad, bad.shape)
    bad[0, 0, 1] = np.nan
    with pytest.raises(ValueError, match="nonfinite"):
        require_scalar_model(bad, bad.shape)
    with pytest.raises(ValueError, match="shape"):
        require_scalar_model(sky, (3, 3, 4))


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


def test_fixed_reference_normalization_and_support_are_not_diluted():
    point_edges = np.array([[1, 3, np.nan], [2, np.nan, np.nan]])
    sky_edges = np.array([[0.5, 1.5, 100], [1, 100, 100]])
    point = {"losses": {"train": 10, "validation": 20, "test": 30}}
    sky = {"losses": {"train": 9, "validation": 22, "test": None}}
    result = comparison_summary(point, sky, point_edges, sky_edges)
    assert result["point_fixed_support_tv"] == 4
    assert result["sky_fixed_support_tv"] == 2
    assert result["fixed_support_tv_ratio"] == 0.5
    assert result["weighted_mse_ratios"] == {
        "train": 0.9,
        "validation": 1.1,
        "test": None,
    }
    sky_edges[0, 0] = np.nan
    result = comparison_summary(point, sky, point_edges, sky_edges)
    assert result["lost_reference_edges"] == 1
    assert result["fixed_support_tv_ratio"] is None


def test_model_download_identity_and_shape_sensitive_array_hash(tmp_path):
    wrong = tmp_path / "wrong-model.txt"
    wrong.write_text("Format = Name\nnot a verified model\n")
    with pytest.raises(ValueError, match="checksum"):
        model_provenance(wrong)
    vector = np.arange(6, dtype=np.float64)
    assert array_digest(vector) != array_digest(vector.reshape(2, 3))
    assert array_digest(vector) == array_digest(vector.copy())
