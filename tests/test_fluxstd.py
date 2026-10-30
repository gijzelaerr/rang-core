"""FS1 flux standards against the CASA setjy oracle archive."""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import fluxstd, lsm

ARCHIVE = (
    Path(__file__).resolve().parents[1] / "research/results/fs1-flux-standards.json"
)


@pytest.fixture(scope="module")
def result():
    return json.loads(ARCHIVE.read_text())


def test_acceptance_recorded(result):
    assert all(result["acceptance"].values())


def test_doubles_match_setjy(result):
    for std, per_source in result["archive"]["oracle"].items():
        for src, v in per_source.items():
            nu, casa = np.array(v["freq_hz"]), np.array(v["casa_fluxd_i"])
            if std == "manual":
                port = fluxstd.manual(nu, **fluxstd.CARACAL_1934)
            else:
                port = fluxstd.flux(src, nu, std, extrapolate=True)[:, 0]
            assert np.max(np.abs(port / casa - 1)) < 1e-13, (std, src)


def test_lband_float32_model_data_exact(result):
    nu = np.array(result["archive"]["lband_freq_hz"])
    for std, per_source in result["archive"]["oracle"].items():
        for src, v in per_source.items():
            if std == "manual":
                port = fluxstd.manual(nu, **fluxstd.CARACAL_1934)
            else:
                port = fluxstd.flux(src, nu, std)[:, 0]
            casa = np.array(v["lband_casa_i_f32"], dtype=np.float32)
            assert np.array_equal(port.astype(np.float32), casa), (std, src)


def test_dense_1934_breaks(result):
    for std, v in result["archive"]["dense_1934"].items():
        nu, casa = np.array(v["freq_hz"]), np.array(v["casa_fluxd_i"])
        port = fluxstd.flux("1934-638", nu, std)[:, 0]
        assert np.max(np.abs(port / casa - 1)) < 1e-13, std
    assert 11.14e9 < fluxstd.SR2016_BREAK_HZ < 11.15e9


def test_1934_standards_coincide_below_10ghz():
    nu = np.linspace(0.05e9, 10e9, 2001)
    sr = fluxstd.flux("1934-638", nu, "SR2016")
    pb = fluxstd.flux("J1939-6342", nu, "PB2010")
    assert np.array_equal(sr, pb)
    reynolds = 10 ** np.polynomial.polynomial.polyval(
        np.log10(nu / 1e6), fluxstd.REYNOLDS_1994_MHZ
    )
    assert np.max(np.abs(sr[:, 0] / reynolds - 1)) < 3e-7  # float32 storage only


def test_quv_zero_and_shape():
    out = fluxstd.flux("3C286", np.full((2, 3), 1.4e9), "Perley-Butler 2010")
    assert out.shape == (2, 3, 4)
    assert np.all(out[..., 1:] == 0)


def test_refusals():
    with pytest.raises(ValueError, match="not in"):
        fluxstd.flux("3C123", [1.4e9], "Perley-Butler 2010")  # CASA: 1 Jy
    with pytest.raises(ValueError, match="not in"):
        fluxstd.flux("3C286", [1.4e9], "Stevens-Reynolds 2016")
    with pytest.raises(ValueError, match="outside"):
        fluxstd.flux("3C286", [20e9], "Baars")
    with pytest.raises(ValueError, match="not verified"):
        fluxstd.flux("3C286", [1.4e9], "Perley-Butler 2017")
    with pytest.raises(ValueError, match="unknown standard"):
        fluxstd.flux("3C286", [1.4e9], "Perley-Butler 2013")
    with pytest.raises(ValueError, match="positive"):
        fluxstd.flux("3C286", [0.0], "Perley-Butler 2010")


def test_pb2017_paper_values():
    # Perley & Butler 2017: a0 is log10 S at 1 GHz.
    s = fluxstd.flux("3C286", [1e9], "PB2017", unverified_ok=True)[0, 0]
    assert s == pytest.approx(10**1.2481, rel=1e-15)
    with pytest.raises(ValueError, match="outside"):
        fluxstd.flux("Fornax A", [1e9], "PB2017", unverified_ok=True)


def test_aliases_identical():
    nu = np.linspace(0.9e9, 1.7e9, 11)
    for alias, name in fluxstd.ALIASES.items():
        for std in ("Perley-Butler 2010", "Baars"):
            if (std, name) in fluxstd.MODELS:
                assert np.array_equal(
                    fluxstd.flux(alias, nu, std), fluxstd.flux(name, nu, std)
                )


def test_lsm_source_exact_and_break_refused():
    nu = np.linspace(0.856e9, 1.712e9, 257)
    s = fluxstd.lsm_source("1934-638", "SR2016", 1.0, -1.1, 1.284e9, (nu[0], nu[-1]))
    assert isinstance(s, lsm.Source)
    want = fluxstd.flux("1934-638", nu, "SR2016")[:, 0]
    assert np.max(np.abs(s.flux(nu) / want - 1)) < 1e-14
    with pytest.raises(ValueError, match="crosses"):
        fluxstd.lsm_source("1934-638", "SR2016", 0.0, 0.0, 10e9, (9e9, 12e9))
    m = fluxstd.manual_lsm_source(0.0, 0.0, **fluxstd.CARACAL_1934)
    ref = fluxstd.manual(nu, **fluxstd.CARACAL_1934)
    assert np.max(np.abs(m.flux(nu) / ref - 1)) < 1e-14


def test_tigger_spi_reexpansion():
    coeffs = (1.2, -0.7, -0.2, 0.05, 0.01)
    i0, spi = fluxstd.tigger_spi(coeffs, 1e9, 1.3e9)
    nu = np.geomspace(0.1e9, 20e9, 50)
    got = i0 * np.exp(sum(c * np.log(nu / 1.3e9) ** (k + 1) for k, c in enumerate(spi)))
    assert np.max(np.abs(got / fluxstd.log10_poly(coeffs, 1e9, nu) - 1)) < 1e-12


@pytest.mark.skipif(shutil.which("cargo") is None, reason="needs cargo")
def test_rust_kernel_matches_python():
    lib = fluxstd.rust_library()
    nu = np.geomspace(0.05e9, 50e9, 301)
    for m in fluxstd.MODELS.values():
        for p in m.pieces:
            rs = fluxstd.rust_log10_poly(lib, p.coeffs, p.unit_hz, nu)
            py = fluxstd.log10_poly(p.coeffs, p.unit_hz, nu)
            assert np.max(np.abs(rs / py - 1)) < 1e-13
    with pytest.raises(ValueError):
        fluxstd.rust_log10_poly(lib, (1.0,), 1e9, [-1.0])
