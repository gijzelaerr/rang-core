"""Tests of the core_image_fit extract.

Live part of tests/test_flagging_imaging.py at commit 2da566c
(now history/tests/test_flagging_imaging.py,
sha256 bb52d577ad34024cf4d8e0179038a684655f6e0dc619528b01839ce2eee9f6c1):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

import numpy as np
import pytest
from rang import core_image_fit as imaging


@pytest.mark.parametrize("coeff", [[0.06, 0.12], [-0.06, -0.12], [0, 0]])
def test_known_family_image_fit_is_unrestricted(coeff):
    rng = np.random.default_rng(9)
    templates = rng.normal(size=(2, 8, 8))
    target = np.einsum("s,syx->yx", coeff, templates)
    fit = imaging.linear_image_fit(target, templates)
    assert fit["available"] and fit["rank"] == 2
    np.testing.assert_allclose(fit["coefficients_jy"], coeff, atol=1e-14)
    assert not fit["blind_flux_or_morphology_recovery"]


def test_rank_deficient_image_family_is_unavailable():
    fit = imaging.linear_image_fit(np.ones((8, 8)), np.ones((2, 8, 8)))
    assert not fit["available"] and fit["coefficients_jy"] is None


def test_invalid_image_pixels_are_not_silently_dropped():
    target = np.zeros((8, 8))
    target[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite image"):
        imaging.linear_image_fit(target, np.ones((2, 8, 8)))


def test_fixed_dirty_offsource_diagnostic_is_not_thermal_noise():
    a = imaging.image_diagnostics(np.ones((512, 512)))
    assert a["dirty_offsource_RMS_jy_per_beam"] == 1
    assert a["dirty_offsource_std_jy_per_beam"] == 0
    assert a["fixed_offsource_pixels"] > 100
    assert "not independent thermal" in a["RMS_role"]


@pytest.mark.parametrize("change", [None, "CDELT1", "CTYPE2", "CRVAL1", "missing"])
def test_image_geometry_frozen_scale_and_axes(change):
    header = {
        "CRPIX1": 257.0,
        "CRPIX2": 257.0,
        "CRVAL1": 0.0,
        "CRVAL2": -30.0,
        "CDELT1": -8 / 3600,
        "CDELT2": 8 / 3600,
        "CTYPE1": "RA---SIN",
        "CTYPE2": "DEC--SIN",
    }
    if change is None:
        assert imaging.image_geometry(header) == header
        return
    if change == "missing":
        del header["CRPIX1"]
    else:
        header[change] = {"CDELT1": -4 / 3600, "CTYPE2": "DEC--TAN", "CRVAL1": np.nan}[
            change
        ]
    with pytest.raises(RuntimeError, match="WCS|scale/axes"):
        imaging.image_geometry(header)
