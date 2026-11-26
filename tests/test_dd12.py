# SPDX-License-Identifier: MIT
"""DD12's gate M2: GeMClean's multi-scale minor cycle through
`rang._core.multiscale_image` on a synthetic image (research/dd12-msclean.md,
section 5)."""

import numpy as np
import pytest

_core = pytest.importorskip("rang._core")


def _bm(model, psf2n):
    from scipy.signal import fftconvolve

    n = model.shape[0]
    return fftconvolve(model, psf2n, mode="full")[n : 2 * n, n : 2 * n]


def test_multiscale_image_recovers_extended_flux():
    n = 128
    y, x = np.mgrid[-n:n, -n:n].astype(float)
    psf2n = np.exp(-(x**2 + y**2) / (2 * 1.5**2))
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    sky = np.exp(-((yy - 60) ** 2 + (xx - 70) ** 2) / (2 * 6.0**2))
    sky *= 1.0 / sky.sum()
    sky[40, 30] += 0.5
    dirty = _bm(sky, psf2n)
    mask = np.zeros((n, n), np.uint8)
    mask[8:-8, 8:-8] = 1
    threshold = 1e-3
    model = np.zeros((n, n))
    residual = np.zeros((n, n))
    rec = _core.multiscale_image(
        n, np.ascontiguousarray(dirty), np.ascontiguousarray(psf2n), mask, threshold,
        0.1, 5000, 50, [0.0, 4.0, 8.0, 16.0], 0, 0.6, 0.2, 1.0, 16, model, residual,
    )  # fmt: skip
    assert rec["end"] in ("normal", "stalled")
    assert rec["components"] > 0
    assert abs(model.sum() - 1.5) <= 0.02 * 1.5
    assert np.abs(residual[mask > 0]).max() < 2 * threshold
    exact = dirty - _bm(model, psf2n)
    assert np.abs(residual - exact).max() <= 1e-10 * np.abs(dirty).max()
    # the extended source is taken mostly at the non-zero scales
    big = sum(s[6] for s in rec["scales"] if s[0] > 0)
    assert big > 0.5
