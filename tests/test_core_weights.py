import numpy as np
import pytest
from rang import core_weights

SCALE = 8.0 * np.pi / (180.0 * 60.0 * 60.0)


def test_padded_size_and_grid_shape():
    assert core_weights.padded_size(512) == 616
    assert core_weights.padded_size(1024) == 1232
    assert core_weights.grid_shape(616, 616) == (616, 616)
    assert core_weights.grid_shape(616, 616, 3.0) == (206, 206)


def test_wavelengths_round_long_double_division():
    freq = np.array([856e6, 1.711791015625e9])
    wavelength = core_weights.wsclean_wavelengths(freq)
    np.testing.assert_allclose(wavelength, 299792458.0 / freq, rtol=1e-15)
    assert wavelength.dtype == np.float64


def test_stokes_i_matches_wsclean_rules():
    data = np.zeros((2, 3, 4), dtype=np.complex64)
    data[..., 0] = 1 + 2j
    data[..., 3] = 3 - 2j
    data[1, 2, 0] = np.nan
    weights = np.full((2, 3, 4), 2.0, dtype=np.float32)
    weights[0, 1, 3] = 0.5
    flags = np.zeros((2, 3, 4), dtype=bool)
    flags[0, 0, 3] = True
    vis, weight = core_weights.stokes_i(data, weights, flags)
    assert vis.dtype == np.complex64 and weight.dtype == np.float32
    assert vis[0, 1] == np.complex64(2 + 0j)
    assert vis[1, 2] == 0
    assert weight[0, 0] == 0  # YY flagged
    assert weight[0, 1] == np.float32(2.0)  # min(8, 2)
    assert weight[0, 2] == np.float32(8.0)
    assert weight[1, 2] == 0  # XX not finite


def test_briggs_weights_follow_the_formula_and_skip_unselected_rows():
    uvw = np.array([[100.0, 50.0, 0.0], [-100.0, -50.0, 0.0], [100.0, 50.0, 0.0]])
    wavelength = np.array([0.2, 0.25])
    weights = np.ones((3, 2), dtype=np.float32)
    weights[0, 1] = 3.0
    result = core_weights.imaging_weights(
        uvw, wavelength, weights, [True, True, False], mode="briggs", robust=0.5
    )
    out = result["weights"]
    assert out.shape == (3, 2) and out.dtype == np.float32
    assert np.all(out[2] == 0)
    assert np.array_equal(out[0], out[1]), "conjugate rows share cells"
    grid = result["grid"]
    assert grid.shape == (308, 616)
    assert np.count_nonzero(grid) == 2
    total = 1 + 3 + 1 + 1
    avg_w = (2.0**2 + 4.0**2) / total
    f = 5.0 * 10.0**-0.5
    expected = 1.0 / (1.0 + np.array([2.0, 4.0]) * f * f / avg_w)
    np.testing.assert_array_equal(np.sort(out[0]), np.sort(expected.astype(np.float32)))
    sums = result["sums"]
    assert sums["count"] == 4
    assert sums["visibility_weight_sum"] == 6.0
    numpy_sums = core_weights.weight_sums(weights, out)
    assert numpy_sums["count"] == 4
    assert numpy_sums["total_weight"] == pytest.approx(sums["total_weight"], rel=1e-12)


def test_uniform_and_natural():
    uvw = np.array([[100.0, 50.0, 0.0], [100.0, 50.0, 0.0]])
    wavelength = np.array([0.2])
    weights = np.array([[2.0], [3.0]], dtype=np.float32)
    uniform = core_weights.imaging_weights(
        uvw, wavelength, weights, [True, True], mode="uniform", return_grid=False
    )
    assert np.all(uniform["weights"] == np.float32(0.2))
    assert "grid" not in uniform
    natural = core_weights.imaging_weights(
        uvw, wavelength, weights, [True, True], mode="natural", rank_filter=None
    )
    assert np.all(natural["weights"] == 1.0)


def test_rejects_bad_shapes_and_modes():
    with pytest.raises(ValueError):
        core_weights.imaging_weights(
            np.zeros((2, 3)), np.ones(1), np.ones((3, 1)), [1, 1]
        )
    with pytest.raises(ValueError):
        core_weights.imaging_weights(
            np.zeros((1, 3)), np.ones(1), np.ones((1, 1)), [1], mode="robust"
        )
    with pytest.raises(ValueError):
        core_weights.stokes_i(np.zeros((2, 2)), np.zeros((2, 2)), np.zeros((2, 2)))
