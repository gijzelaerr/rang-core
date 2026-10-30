"""Paired full-Jones flagging/calibration response to evaluation-only faint sky.

Verbatim extract of the frozen `rangtoy.flagging_signal` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_signal.py at commit
2da566c (now history/python/flagging_signal.py),
sha256 60743c3972d8fb24a3017931d5c79ca2085c30576a848b4ec567605fe3aad81b.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import numpy as np

REFERENCE_HZ = 1283791015.625


ARCMIN = np.pi / 10800


SOURCES = (
    {
        "name": "compact",
        "flux_jy": 0.05,
        "l_arcmin": 12.0,
        "m_arcmin": 8.0,
        "fwhm_arcmin": 0.0,
        "spectral_index": -0.7,
    },
    {
        "name": "extended",
        "flux_jy": 0.1,
        "l_arcmin": -15.0,
        "m_arcmin": 10.0,
        "fwhm_arcmin": 10.0,
        "spectral_index": -1.0,
    },
)


INVERSE_CONDITION_LIMIT = 1e8


def spatial_templates(uvw, frequencies, sources=SOURCES):
    """Bounded independent NumPy CASA-sign DFT and circular-Gaussian FT.

    l/m are direction cosines scaled by the arcminute-to-radian factor, not RA
    and declination differences. Gaussian shape uses the usual tangent-plane
    Fourier transform; its central noncoplanar phase includes w(n-1).
    """
    uvw, frequencies = np.asarray(uvw, float), np.asarray(frequencies, float)
    if uvw.ndim != 2 or uvw.shape[1] != 3 or frequencies.ndim != 1:
        raise ValueError("UVW(row,3) and frequency(channel) required")
    if (
        not np.isfinite(uvw).all()
        or not np.isfinite(frequencies).all()
        or np.any(frequencies <= 0)
    ):
        raise ValueError("finite coordinates and positive frequencies required")
    result = []
    wavelength_uv = uvw[:, :2, None] * frequencies[None, None] / 299792458
    for source in sources:
        l, m = source["l_arcmin"] * ARCMIN, source["m_arcmin"] * ARCMIN
        width = source["fwhm_arcmin"] * ARCMIN
        if not np.isfinite([l, m, width]).all() or l * l + m * m >= 1 or width < 0:
            raise ValueError(
                "finite small source direction and nonnegative width required"
            )
        distance = uvw @ [l, m, np.sqrt(1 - l * l - m * m) - 1]
        phase = np.exp(2j * np.pi / 299792458 * distance[:, None] * frequencies)
        shape = np.exp(
            -(np.pi**2) * width**2 / (4 * np.log(2)) * np.sum(wavelength_uv**2, axis=1)
        )
        result.append(phase * shape)
    return np.asarray(result)


def corrected_intensity(data, gp, gq, gain_valid, native_weights):
    """Gauge-invariant Stokes-I trace and original-weight variance propagation.

    Independent native correlation noises with complex variance 1/WEIGHT are a
    diagnostic assumption, not a calibrated noise model. Paired differences
    share the same noisy input, so their variance is not the sum of two variances.
    """
    data, native_weights = np.asarray(data), np.asarray(native_weights, float)
    gp, gq = np.asarray(gp), np.asarray(gq)
    valid = np.asarray(gain_valid, bool).copy()
    if (
        data.shape[-1] != 4
        or data.shape != native_weights.shape
        or gp.shape != (*data.shape[:2], 2, 2)
        or gq.shape != gp.shape
        or valid.shape != data.shape[:2]
    ):
        raise ValueError(
            "four correlations and matched per-sample Jones/weights required"
        )
    valid &= (
        np.isfinite(data).all(axis=-1)
        & np.isfinite(native_weights).all(axis=-1)
        & (native_weights > 0).all(axis=-1)
    )
    valid &= np.isfinite(gp).all(axis=(-1, -2)) & np.isfinite(gq).all(axis=(-1, -2))
    # Invalid matrices are never inverted or silently included in a fit.
    safe_p = np.where(valid[..., None, None], gp, np.eye(2))
    safe_q = np.where(valid[..., None, None], gq, np.eye(2))
    valid &= (np.linalg.cond(safe_p) <= INVERSE_CONDITION_LIMIT) & (
        np.linalg.cond(safe_q) <= INVERSE_CONDITION_LIMIT
    )
    safe_p = np.where(valid[..., None, None], gp, np.eye(2))
    safe_q = np.where(valid[..., None, None], gq, np.eye(2))
    inverse_p, inverse_q = np.linalg.inv(safe_p), np.linalg.inv(safe_q)
    coefficients = 0.5 * (inverse_q.conj().swapaxes(-1, -2) @ inverse_p).swapaxes(
        -1, -2
    ).reshape(data.shape)
    intensity = np.sum(coefficients * data, axis=-1)
    variance = np.sum(
        np.abs(coefficients) ** 2 / np.where(native_weights > 0, native_weights, 1),
        axis=-1,
    )
    valid &= np.isfinite(intensity) & np.isfinite(variance) & (variance > 0)
    return np.where(valid, intensity, np.nan), np.where(valid, variance, np.nan), valid
