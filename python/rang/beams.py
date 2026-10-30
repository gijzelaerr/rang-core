"""Differentiable scalar beams with frequency-dependent measured parameters.

The optional katbeam adapter reads SARAO's BSD-licensed model tables at runtime;
no upstream coefficient table is redistributed here. These are simplified
holography-informed beams, not measured full-Jones beam cubes.
"""

from functools import partial
from hashlib import sha256
from importlib.metadata import version
from typing import NamedTuple

import jax
import jax.numpy as jnp
import numpy as np

from .pointing import ARCMIN, C


class BeamTable(NamedTuple):
    frequency_hz: jax.Array
    squint_rad: jax.Array
    fwhm_rad: jax.Array


def beam_table(frequency_hz, squint_rad, fwhm_rad):
    """Validate table arrays: frequencies (F,), squint and power FWHM (F,2)."""
    frequency, squint, fwhm = map(np.asarray, (frequency_hz, squint_rad, fwhm_rad))
    if (
        frequency.ndim != 1
        or len(frequency) < 2
        or not np.isfinite(frequency).all()
        or np.any(frequency <= 0)
        or np.any(np.diff(frequency) <= 0)
    ):
        raise ValueError(
            "beam frequencies must be finite, positive and strictly increasing"
        )
    if squint.shape != (len(frequency), 2) or fwhm.shape != squint.shape:
        raise ValueError("squint and FWHM must have shape (frequency_count, 2)")
    if (
        not np.isfinite(squint).all()
        or not np.isfinite(fwhm).all()
        or np.any(fwhm <= 0)
    ):
        raise ValueError("squint must be finite and FWHM finite and positive")
    return BeamTable(*(jnp.asarray(x) for x in (frequency, squint, fwhm)))


def load_katbeam(polarization="H"):
    """Read the MKAT-AA-L-JIM-2020 co-polar voltage model's parameter table.

    H and V are separate scalar experiments, not full-polarization calibration.
    Upstream squint/FWHM attributes use degrees; Rang uses radians.
    """
    from katbeam import JimBeam

    if polarization not in ("H", "V"):
        raise ValueError("polarization must be H or V")
    model = JimBeam("MKAT-AA-L-JIM-2020")
    columns = slice(0, 2) if polarization == "H" else slice(2, 4)
    table = beam_table(
        model.freqMHzlist * 1e6,
        np.deg2rad(model.squintlist[columns].T),
        np.deg2rad(model.fwhmlist[columns].T),
    )
    metadata = {
        "model": model.name,
        "polarization": polarization,
        "katbeam_version": version("katbeam"),
        "parameter_sha256": sha256(
            b"".join(np.asarray(x, dtype="<f8").tobytes() for x in table)
        ).hexdigest(),
        "source": "https://github.com/ska-sa/katbeam",
        "description": "simplified holography-informed co-polar voltage beam",
    }
    return table, metadata


@jax.jit
def cosine_taper(radius_squared):
    """Cosine-aperture voltage taper with stable derivatives at r=0 and rr=1/2.

    Normalized radius r=0.5 is the half-power point. The sinc form removes
    the apparent pole in cos(pi*rr)/(1-4*rr**2). A near-origin power series
    avoids differentiating sqrt at zero. The signed sidelobes are retained.
    """
    q2 = radius_squared * 1.1889647809329453**2
    small = q2 < 1e-8
    q = jnp.sqrt(jnp.where(small, 1.0, q2))
    regular = jnp.pi * jnp.sinc(q - 0.5) / (4 * (q + 0.5))
    c1 = 4 - jnp.pi**2 / 2
    c2 = 16 - 2 * jnp.pi**2 + jnp.pi**4 / 24
    c3 = 64 - 8 * jnp.pi**2 + jnp.pi**4 / 6 - jnp.pi**6 / 720
    series = 1 + q2 * (c1 + q2 * (c2 + q2 * c3))
    return jnp.where(small, series, regular)


@partial(jax.jit, static_argnames=("profile",))
def voltage_beam(
    x_rad, y_rad, frequency_hz, table, profile="cosine", width_multiplier=1.0
):
    """Voltage at row-by-source beam coordinates; no frequency extrapolation."""
    squint = jnp.stack(
        [
            jnp.interp(
                frequency_hz,
                table.frequency_hz,
                table.squint_rad[:, i],
                left=jnp.nan,
                right=jnp.nan,
            )
            for i in range(2)
        ],
        axis=1,
    )
    width = jnp.stack(
        [
            jnp.interp(
                frequency_hz,
                table.frequency_hz,
                table.fwhm_rad[:, i],
                left=jnp.nan,
                right=jnp.nan,
            )
            for i in range(2)
        ],
        axis=1,
    )
    width = width * jnp.asarray(width_multiplier)[..., None]
    radius2 = ((x_rad - squint[:, 0, None]) / width[:, 0, None]) ** 2 + (
        (y_rad - squint[:, 1, None]) / width[:, 1, None]
    ) ** 2
    if profile == "cosine":
        return cosine_taper(radius2)
    if profile == "gaussian":
        return jnp.exp(-2 * jnp.log(2.0) * radius2)
    raise ValueError("profile must be cosine or gaussian")


@partial(jax.jit, static_argnames=("profile",))
def predict_tabulated(
    components,
    observation,
    offsets_arcmin,
    table,
    profile="cosine",
    antenna_log_width=None,
):
    """Scalar component DFT with the same full w phase as the analytic baseline."""
    obs = observation
    lm = components.lmn[:, :2]
    c, s = jnp.cos(obs.beam_angle_rad)[:, None], jnp.sin(obs.beam_angle_rad)[:, None]
    x, y = c * lm[:, 0] + s * lm[:, 1], -s * lm[:, 0] + c * lm[:, 1]

    def beam(antenna):
        offset = offsets_arcmin[obs.time_index, antenna] * ARCMIN
        return voltage_beam(
            x - offset[:, 0, None],
            y - offset[:, 1, None],
            obs.frequency_hz,
            table,
            profile,
            1.0 if antenna_log_width is None else jnp.exp(antenna_log_width[antenna]),
        )

    direction = components.lmn - jnp.array([0.0, 0.0, 1.0])
    phase = -2 * jnp.pi * (obs.uvw_m @ direction.T) * obs.frequency_hz[:, None] / C
    flux = (
        components.flux_jy
        * (obs.frequency_hz[:, None] / components.reference_hz)
        ** components.spectral_index
    )
    return jnp.sum(
        flux * beam(obs.antenna1) * beam(obs.antenna2) * jnp.exp(1j * phase), axis=1
    )


def make_beam_predictor(
    table, profile="cosine", metadata=None, *, antenna_log_width=None
):
    """Create a predictor callback accepted by Rang's pointing solver and audit."""
    if profile not in ("cosine", "gaussian"):
        raise ValueError("profile must be cosine or gaussian")
    table = beam_table(*table)
    if antenna_log_width is not None:
        widths = np.asarray(antenna_log_width, float)
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            multipliers = np.exp(widths)
        if (
            widths.ndim != 1
            or not len(widths)
            or not np.isfinite(widths).all()
            or not np.isfinite(multipliers).all()
            or np.any(multipliers <= 0)
        ):
            raise ValueError(
                "antenna_log_width must be a finite vector with positive finite exponentials"
            )
        antenna_log_width = jnp.asarray(widths)

    def prediction(components, observation, offsets_arcmin):
        return predict_tabulated(
            components, observation, offsets_arcmin, table, profile, antenna_log_width
        )

    def validate(observation):
        frequency = np.asarray(observation.frequency_hz)
        if (
            not np.isfinite(frequency).all()
            or np.any(frequency < float(table.frequency_hz[0]))
            or np.any(frequency > float(table.frequency_hz[-1]))
        ):
            raise ValueError("observation frequency lies outside the beam table")
        if antenna_log_width is not None:
            for indices in (observation.antenna1, observation.antenna2):
                indices = np.asarray(indices)
                if not np.issubdtype(indices.dtype, np.integer) or np.any(
                    (indices < 0) | (indices >= len(antenna_log_width))
                ):
                    raise ValueError("antenna indices lie outside antenna_log_width")

    def with_log_width(components, observation, offsets_arcmin, log_width):
        adjusted = table._replace(fwhm_rad=table.fwhm_rad * jnp.exp(log_width))
        return predict_tabulated(
            components,
            observation,
            offsets_arcmin,
            adjusted,
            profile,
            antenna_log_width,
        )

    def shaped_table(parameters):
        # Parameters: log geometric width at 1.3 GHz, log-width slope per
        # 0.4 GHz, log(y/x FWHM) correction. Squint is unchanged.
        frequency_coordinate = (table.frequency_hz - 1.3e9) / 0.4e9
        width = parameters[0] + parameters[1] * frequency_coordinate
        axes = parameters[2] * jnp.array([-0.5, 0.5])
        return table._replace(fwhm_rad=table.fwhm_rad * jnp.exp(width[:, None] + axes))

    def with_shape(components, observation, offsets_arcmin, parameters):
        return predict_tabulated(
            components,
            observation,
            offsets_arcmin,
            shaped_table(parameters),
            profile,
            antenna_log_width,
        )

    def with_antenna_shape(
        components, observation, offsets_arcmin, parameters, relative_widths
    ):
        widths = relative_widths
        if antenna_log_width is not None:
            if len(widths) != len(antenna_log_width):
                raise ValueError("fitted and known antenna width counts must match")
            widths = widths + antenna_log_width
        return predict_tabulated(
            components,
            observation,
            offsets_arcmin,
            shaped_table(parameters),
            profile,
            widths,
        )

    prediction.validate_observation = validate
    prediction.with_log_width = with_log_width
    prediction.with_shape = with_shape
    prediction.with_antenna_shape = with_antenna_shape
    prediction.metadata = dict(metadata or {}, profile=profile)
    if antenna_log_width is not None:
        prediction.metadata["antenna_log_width"] = np.asarray(
            antenna_log_width
        ).tolist()
    return prediction
