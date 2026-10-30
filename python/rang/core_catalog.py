"""Paired real MeerKAT L-band sky-model experiment, not a flagging win claim.

Verbatim extract of the frozen `rangtoy.flagging_sky` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_sky.py at commit
2da566c (now history/python/flagging_sky.py),
sha256 964728135a142faa1000655d45f13e368ecdbaa127ed5021d61df994ff5e347d.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import numpy as np


def point_catalog_predict(
    uvw, radec, phase_centre, frequencies, flux, coefficients, reference
):
    """Independent NumPy DFT for this catalog's POINT/ordinary-polynomial sources.

    Positive Fourier phase matches the installed Africanus/MS convention.
    Spectral coefficients are additive Jy coefficients, not spectral indices.
    This tiny-check path does not replace Crystalball's full prediction.
    """
    uvw, radec = np.asarray(uvw, float), np.asarray(radec, float)
    frequencies, reference = (
        np.asarray(frequencies, float),
        np.asarray(reference, float),
    )
    flux, coefficients = np.asarray(flux, float), np.asarray(coefficients, float)
    ra0, dec0 = phase_centre
    ra, dec = radec.T
    difference = ra - ra0
    l = np.cos(dec) * np.sin(difference)
    m = np.sin(dec) * np.cos(dec0) - np.cos(dec) * np.sin(dec0) * np.cos(difference)
    n_minus_one = np.sqrt(1 - l * l - m * m) - 1
    x = frequencies[None] / reference[:, None] - 1
    spectrum = flux[:, None] + sum(
        coefficients[:, k, None] * x ** (k + 1) for k in range(coefficients.shape[1])
    )
    distance = uvw @ np.stack((l, m, n_minus_one))
    phase = 2j * np.pi / 299792458 * distance[..., None] * frequencies
    return np.sum(np.exp(phase) * spectrum[None], axis=1)
