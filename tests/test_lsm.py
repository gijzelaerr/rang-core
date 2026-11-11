"""Tests of the Tigger ASCII lsm reader (research/l1-model-completeness.md)."""

import math

import numpy as np
import pytest
from rang import core, lsm

HEADER = (
    "#format: name ra_h ra_m ra_s dec_d dec_m dec_s i i_err emaj_s emin_s pa_d "
    "freq0 spi spi_err spi2 spi2_err spi3 spi3_err spi4 spi4_err"
)
LINES = (
    HEADER,
    (
        "A0 19 39 25.03 -63 42 45.7 15.0 -4e-06 0.0 0.0 0.0 1300000000.0 "
        "-0.1 1e-5 -0.6 4e-5 -0.04 -3e-4 -0.55 -1e-3"
    ),
    "# a comment",
    "",
    (
        "G1 19 37 32.09 -63 35 59.49 0.01 7e-05 12.0 4.0 54.0 1300000000.0 "
        "-3.1 0.03 0.0 9999.0 0.0 9999.0 0.0 9999.0"
    ),
    (
        "Z0 00 00 0.0 -0 30 0.0 1.0 0.0 0.0 0.0 0.0 1300000000.0 "
        "0.0 9999.0 0.0 9999.0 0.0 9999.0 0.0 9999.0"
    ),
)
TEXT = "\n".join(LINES)


def test_positions_fluxes_and_errors():
    sources = lsm.loads(TEXT)
    assert [s.name for s in sources] == ["A0", "G1", "Z0"]
    a0 = sources[0]
    ra = math.radians((19 + 39 / 60 + 25.03 / 3600) * 15)
    dec = -math.radians(63 + 42 / 60 + 45.7 / 3600)
    assert a0.ra == pytest.approx(ra, abs=1e-15)
    assert a0.dec == pytest.approx(dec, abs=1e-15)
    assert a0.i == 15.0 and a0.q == a0.u == a0.v == 0.0
    assert a0.freq0 == 1.3e9
    assert a0.spi == (-0.1, -0.6, -0.04, -0.55)
    assert a0.errors["spi2"] == 4e-5 and a0.errors["i"] == -4e-6
    assert not a0.gaussian
    # -0 degrees keeps its sign from the string
    assert sources[2].dec == pytest.approx(-math.radians(0.5))
    # trailing zero spectral terms are dropped, as Tigger does
    assert sources[1].spi == (-3.1,)
    assert sources[2].spi == ()


def test_gaussian_extents_are_fwhm_radians_and_pa_radians():
    g = lsm.loads(TEXT)[1]
    assert g.gaussian
    assert g.emaj == pytest.approx(math.radians(12.0 / 3600))
    assert g.emin == pytest.approx(math.radians(4.0 / 3600))
    assert g.pa == pytest.approx(math.radians(54.0))


def test_spectrum_is_tigger_power_law_with_log_curvature():
    a0 = lsm.loads(TEXT)[0]
    nu = np.array([1.07e9, 1.3e9, 1.5e9])
    x = np.log(nu / 1.3e9)
    tigger = 15.0 * (nu / 1.3e9) ** (-0.1 + -0.6 * x + -0.04 * x**2 + -0.55 * x**3)
    assert np.allclose(a0.flux(nu), tigger, rtol=1e-13)
    assert a0.flux(1.3e9) == pytest.approx(15.0)


def test_default_format_without_header():
    text = "S1 1 0 0 -10 0 0 2.0 0.1 0.2 0.3 -0.7 0 0 0 0 1.4e9\n"
    (s,) = lsm.loads(text)
    assert (s.i, s.q, s.u, s.v) == (2.0, 0.1, 0.2, 0.3)
    assert s.spi == (-0.7,) and s.freq0 == 1.4e9
    assert s.ra == pytest.approx(math.radians(15.0))
    assert lsm.summary([s])["polarised"] == 1


def test_unknown_columns_kept_as_strings():
    text = "#format: name ra_d dec_d i tag\nX 10.0 -20.0 1.5 calibrator\n"
    (s,) = lsm.loads(text)
    assert s.extra == {"tag": "calibrator"}
    assert s.ra == pytest.approx(math.radians(10.0))
    assert s.dec == pytest.approx(math.radians(-20.0))


@pytest.mark.parametrize(
    "text",
    [
        "#format: name ra_d dec_d\nX 1 2\n",  # no flux column
        "#format: name ra_d dec_d i spi\nX 1 2 3 -0.7\n",  # spi without freq0
        "#format: name ra_d dec_d i\nX 1 2\n",  # short line
        "#format: name name ra_d dec_d i\nX X 1 2 3\n",  # duplicate column
    ],
)
def test_malformed_files_raise(text):
    with pytest.raises(ValueError):
        lsm.loads(text)


def test_direction_cosines_small_offsets():
    ra0, dec0 = 1.0, -1.1
    eps = 1e-6
    l, m = lsm.direction_cosines(
        [ra0, ra0 + eps, ra0], [dec0, dec0, dec0 + eps], ra0, dec0
    )
    assert l[0] == m[0] == 0.0
    assert l[1] == pytest.approx(eps * math.cos(dec0), rel=1e-6)
    assert m[2] == pytest.approx(eps, rel=1e-6)


def test_components_map_to_the_core_log_polynomial():
    sources = lsm.loads(TEXT)
    comps = lsm.components(sources, (sources[0].ra, sources[0].dec))
    assert comps["coeffs"].shape == (3, 4)
    assert np.array_equal(comps["coeffs"][0], [-0.1, -0.6, -0.04, -0.55])
    assert np.array_equal(comps["coeffs"][1], [-3.1, 0, 0, 0])
    assert np.array_equal(comps["kind"], [0, 1, 0])
    assert comps["log_poly"].all()
    assert np.array_equal(comps["lm"][0], [0.0, 0.0])
    # a phase-centre component predicts exactly its Tigger spectrum
    nu = np.linspace(1.07e9, 1.5e9, 7)
    uvw = np.array([[100.0, -50.0, 3.0], [2000.0, 700.0, -10.0]])
    one = {k: v[:1] for k, v in comps.items()}
    vis = core.predict_components(
        uvw,
        nu,
        one["lm"],
        one["kind"],
        one["flux"],
        one["coeffs"],
        one["log_poly"],
        one["ref_freq"],
        one["gauss_shape"],
    )
    assert np.allclose(vis, sources[0].flux(nu)[None, :], rtol=1e-12, atol=0)


def test_summary():
    s = lsm.summary(lsm.loads(TEXT))
    assert s["components"] == 3 and s["gaussians"] == 1 and s["polarised"] == 0
    assert s["brightest"] == "A0" and s["max_spectral_terms"] == 4
    assert s["reference_frequencies_hz"] == [1.3e9]
