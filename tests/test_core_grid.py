import math

import numpy as np
from rangtoy import core_grid

C_LIGHT = 299792458.0


def test_kernel_matches_wsclean_transcription():
    kernel = core_grid.kernel(7, 1023)
    reference = core_grid.kernel_reference(7, 1023)
    assert kernel.shape == (7 * 1023,)
    np.testing.assert_allclose(kernel, reference, rtol=0, atol=1e-15)
    assert kernel[len(kernel) // 2] == 1.0
    np.testing.assert_array_equal(kernel, kernel[::-1])


def test_stokes_i_reader_rule():
    data = np.zeros((2, 3, 4), np.complex64)
    data[..., 0] = 2.0
    data[..., 3] = 4.0 + 2j
    weights = np.ones((2, 3, 4), np.float32)
    weights[0, 0, 0] = 0.25
    weights[0, 1, 3] = 0.5
    flags = np.zeros((2, 3, 4), bool)
    flags[0, 2, 1] = True  # XY flag does not matter
    flags[1, 0, 3] = True
    sample, weight = core_grid.stokes_i_reader(data, weights, flags, [False, False])
    np.testing.assert_array_equal(sample, np.full((2, 3), 3.0 + 1j, np.complex64))
    assert weight[0, 0] == 1.0 and weight[0, 1] == 2.0 and weight[0, 2] == 4.0
    assert weight[1, 0] == 0.0
    _, rowless = core_grid.stokes_i_reader(data, weights, flags, [True, False])
    assert rowless[0].sum() == 0.0 and rowless[1, 1] == 4.0


def _point_source_case(l_pixels, m_pixels, width=48, scale_arcsec=60.0):
    scale = scale_arcsec * math.pi / 648000.0
    l, m = l_pixels * scale, m_pixels * scale
    n = math.sqrt(1.0 - l * l - m * m)
    frequencies = np.array([1.0e9, 1.1e9])
    rng = np.random.default_rng(20261029)
    radius = rng.uniform(5.0, 120.0, 80)
    angle = rng.uniform(0.0, 2 * math.pi, 80)
    uvw = np.stack(
        [radius * np.cos(angle), radius * np.sin(angle), rng.normal(0, 4, 80)], 1
    )
    wavelengths = C_LIGHT / frequencies
    phase = (
        2
        * math.pi
        * (uvw[:, :1] * l + uvw[:, 1:2] * m + uvw[:, 2:3] * (n - 1))
        / wavelengths
    )
    data = np.exp(1j * phase).astype(np.complex64)
    weights = np.ones(data.shape, np.float32)
    return uvw, frequencies, data, weights, width


def test_point_source_lands_at_wsclean_pixel_and_psf_is_unit():
    uvw, frequencies, data, weights, width = _point_source_case(7, -4)
    result = core_grid.invert(
        uvw,
        frequencies,
        data,
        weights,
        weights,
        width=width,
        height=width,
        scale_arcsec=60.0,
        w_layers=5,
    )
    dirty, psf = result["dirty"], result["psf"]
    y, x = np.unravel_index(np.argmax(dirty), dirty.shape)
    assert (x, y) == (width // 2 - 7, width // 2 - 4)
    assert abs(psf[width // 2, width // 2] - 1.0) <= 2.3e-16  # x * (1 / x), as WSClean
    assert abs(dirty[y, x] - 1.0) < 0.05
    stats = result["stats"]
    assert stats["gridded_count"] == data.size
    assert stats["image_weight"] == float(np.float32(data.size))
    assert stats["n_w_layers"] == 5
    assert 0.0 <= stats["min_w"] <= stats["max_w"]


def test_wcs_header_and_fits_orientation(tmp_path):
    frequencies = 856e6 + 208984.375 * np.arange(1024, 3072)
    header = core_grid.wcs_header((5.1461782, -1.11199581), 512, 512, 8.0, frequencies)
    assert header["CRPIX1"] == 257.0 and header["CRPIX2"] == 257.0
    assert math.isclose(header["CRVAL1"], -65.1457083333333, abs_tol=1e-6)
    assert math.isclose(header["CRVAL2"], -63.7126666666667, abs_tol=1e-6)
    assert math.isclose(header["CDELT1"], -8 / 3600) and math.isclose(
        header["CDELT2"], 8 / 3600
    )
    assert header["CRVAL3"] == 1283895507.8125 and header["CDELT3"] == 428000000.0
    image = np.zeros((4, 6), np.float32)
    image[1, 4] = 3.0
    path = tmp_path / "image.fits"
    core_grid.write_fits(
        path, image, core_grid.wcs_header((0.1, 0.2), 6, 4, 8.0, frequencies)
    )
    from astropy.io import fits

    with fits.open(str(path)) as hdus:
        back = hdus[0].data
        assert back.shape == (1, 1, 4, 6)
        assert back[0, 0, 1, 4] == 3.0
        assert hdus[0].header["CTYPE1"] == "RA---SIN"
