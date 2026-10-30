"""Exact Gaussian pointing/sky/gain ambiguity, for controlled small experiments."""

import jax.numpy as jnp
import numpy as np

from .pointing import ARCMIN, C, predict


def gaussian_gauge(
    observation,
    components,
    offsets_arcmin,
    channel_flux_jy,
    antenna_gains,
    shift_arcmin,
    beam_axis_ratio=1.0,
):
    """Transform a model without changing its Gaussian-beam visibilities.

    Arrays: offsets (time, antenna, 2); flux (frequency, source); complex
    gains (time, antenna, frequency). Frequencies are in sorted unique order.
    The two-vector shift parametrizes Q^{-1} R(t) shift, not R(t) shift.
    Assumes identical Gaussian beams, fixed axial ratio, 13.5 m dishes.
    """
    offsets = np.asarray(offsets_arcmin)
    ntime, nant, _ = offsets.shape
    frequencies = np.unique(observation.frequency_hz)
    if np.shape(channel_flux_jy) != (len(frequencies), len(components.flux_jy)):
        raise ValueError("channel flux shape must be (frequency, source)")
    if np.shape(antenna_gains) != (ntime, nant, len(frequencies)):
        raise ValueError("gain shape must be (time, antenna, frequency)")
    if not np.isfinite(beam_axis_ratio) or beam_axis_ratio <= 0:
        raise ValueError("beam axis ratio must be finite and positive")
    shift = np.asarray(shift_arcmin)
    if shift.shape != (2,) or not np.isfinite(shift).all():
        raise ValueError("shift must be a finite two-vector")
    angles = np.zeros(ntime)
    for t in range(ntime):
        values = np.asarray(observation.beam_angle_rad)[
            np.asarray(observation.time_index) == t
        ]
        if len(values):
            if not np.allclose(values, values[0], atol=1e-12, rtol=0):
                raise ValueError("one common beam angle per time required")
            angles[t] = values[0]
    c, s = np.cos(angles), np.sin(angles)
    rotated = np.stack(
        (c * shift[0] + s * shift[1], -s * shift[0] + c * shift[1]), axis=1
    )
    metric = np.array([beam_axis_ratio, 1 / beam_axis_ratio])
    h = rotated / metric
    kappa = 2 * np.log(2) / (1.02 * C / frequencies / 13.5) ** 2
    # All quadratic products below are in radians, not arcminutes.
    cross = np.sum(offsets * metric * h[:, None, :], axis=-1) * ARCMIN**2
    square = np.sum(h * metric * h, axis=-1) * ARCMIN**2
    gain_factor = np.exp((2 * cross + square[:, None])[:, :, None] * kappa)
    flux_factor = np.exp(
        -4 * kappa[:, None] * (np.asarray(components.lmn[:, :2]) @ (shift * ARCMIN))
    )
    return {
        "offsets_arcmin": offsets + h[:, None, :],
        "channel_flux_jy": np.asarray(channel_flux_jy) * flux_factor,
        "antenna_gains": np.asarray(antenna_gains) * gain_factor,
        "common_shift_arcmin": h,
    }


def predict_channels(
    components,
    observation,
    offsets_arcmin,
    channel_flux_jy,
    antenna_gains,
    beam_axis_ratio=1.0,
    beam_quartic=0.0,
):
    """Small reference prediction with independent channel fluxes and DI gains."""
    result = jnp.zeros(len(observation.frequency_hz), dtype=jnp.complex128)
    for f, frequency in enumerate(np.unique(observation.frequency_hz)):
        sky = components._replace(
            flux_jy=jnp.asarray(channel_flux_jy[f]),
            spectral_index=jnp.zeros_like(components.spectral_index),
        )
        value = predict(
            sky,
            observation,
            jnp.asarray(offsets_arcmin),
            beam_axis_ratio=beam_axis_ratio,
            beam_quartic=beam_quartic,
        )
        gains = jnp.asarray(antenna_gains)
        gp = gains[observation.time_index, observation.antenna1, f]
        gq = gains[observation.time_index, observation.antenna2, f]
        result += jnp.where(
            observation.frequency_hz == frequency, value * gp * jnp.conj(gq), 0
        )
    return result
