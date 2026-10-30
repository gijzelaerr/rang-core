"""Numerical and namespace safeguards for paired faint-sky template response.

Live part of tests/test_flagging_signal.py at commit 2da566c
(now history/tests/test_flagging_signal.py,
sha256 dd1492aff7c40a4b5348bfadddd9178bdd3593ae3edd196d15f136ee9299d48f):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

import numpy as np
from rang.core_templates import REFERENCE_HZ, SOURCES, corrected_intensity


def test_frozen_sources_and_reference_frequency():
    assert REFERENCE_HZ == 1283791015.625
    assert [
        (
            s["flux_jy"],
            s["l_arcmin"],
            s["m_arcmin"],
            s["fwhm_arcmin"],
            s["spectral_index"],
        )
        for s in SOURCES
    ] == [
        (0.05, 12.0, 8.0, 0.0, -0.7),
        (0.1, -15.0, 10.0, 10.0, -1.0),
    ]


def test_full_jones_inverse_and_weight_propagation_match_basis_response():
    rng = np.random.default_rng(91)
    gp = np.broadcast_to(np.eye(2), (2, 3, 2, 2)).astype(complex).copy()
    gp += 0.15 * (rng.normal(size=gp.shape) + 1j * rng.normal(size=gp.shape))
    gq = gp[::-1].copy() * (1 + 0.2j)
    coherency = rng.normal(size=gp.shape) + 1j * rng.normal(size=gp.shape)
    observed = (gp @ coherency @ gq.conj().swapaxes(-1, -2)).reshape(2, 3, 4)
    native_weights = np.broadcast_to([1, 2, 3, 4], observed.shape)
    intensity, variance, good = corrected_intensity(
        observed, gp, gq, np.ones((2, 3), bool), native_weights
    )
    np.testing.assert_allclose(
        intensity, np.trace(coherency, axis1=-2, axis2=-1) / 2, atol=1e-14
    )
    assert good.all()
    expected = np.zeros((2, 3))
    for corr in range(4):
        basis = np.zeros((2, 2), complex)
        basis.flat[corr] = 1
        coefficient = (
            np.trace(
                np.linalg.inv(gp) @ basis @ np.linalg.inv(gq).conj().swapaxes(-1, -2),
                axis1=-2,
                axis2=-1,
            )
            / 2
        )
        expected += np.abs(coefficient) ** 2 / native_weights[..., corr]
    np.testing.assert_allclose(variance, expected, atol=1e-14)
    # Common right-unitary full-Jones gauge changes do not change trace response.
    unitary = np.linalg.qr(rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2)))[0]
    rotated, rotated_variance, rotated_good = corrected_intensity(
        observed, gp @ unitary, gq @ unitary, good, native_weights
    )
    np.testing.assert_allclose(rotated, intensity, atol=1e-14)
    np.testing.assert_allclose(rotated_variance, variance, atol=1e-14)
    assert rotated_good.all()


def test_singular_or_unsupported_jones_are_unavailable_not_silently_inverted():
    gains = np.broadcast_to(np.eye(2), (2, 3, 2, 2)).astype(complex).copy()
    gains[0, 0] = 0
    mask = np.ones((2, 3), bool)
    mask[1, 1] = False
    intensity, variance, good = corrected_intensity(
        np.ones((2, 3, 4), complex), gains, gains, mask, np.ones((2, 3, 4))
    )
    assert not good[0, 0] and not good[1, 1]
    assert np.isnan(intensity[0, 0]) and np.isnan(variance[1, 1])
    assert good[0, 1]
