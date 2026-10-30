"""Time-local elimination and compact global pointing information audits.

Local nuisance columns are unconstrained. Their elimination is exact up to
numerical rank decisions; smoothness across time cannot be imposed on these
eliminated parameters afterward. Keep such parameters global instead.
"""

from time import perf_counter

import jax
import jax.numpy as jnp
import numpy as np
from scipy.linalg import null_space

from .observability import nuisance_information_budget
from .pointing import Observation, real_stack, resolve_predictor
from .projector import project_grouped, project_out


def prepare_blocked_design(
    components,
    observation,
    antenna_count,
    *,
    noise_jy,
    predictor=None,
    beam_axis_ratio=1.0,
    beam_quartic=0.0,
    gain_model="per_time_channel",
    differential_pointing=True,
    backend="rust",
    frequency_blocking=False,
):
    """Compress a local linearization while retaining common motion and sky.

    Frequencies and observed time indices are sorted; the target projection
    uses equally weighted observed times. Unobserved times are not inferred.
    All positive source/channel log amplitudes remain global and initially free.
    """
    started = perf_counter()
    if not jax.config.x64_enabled:
        raise ValueError("enable JAX 64-bit mode before constructing inputs")
    if not isinstance(antenna_count, int) or antenna_count < 2:
        raise ValueError("antenna_count must be an integer >=2")
    if not np.isfinite(noise_jy) or noise_jy <= 0:
        raise ValueError("noise_jy must be finite and positive")
    if gain_model not in ("fixed", "per_time", "per_time_channel"):
        raise ValueError(
            "blocked gain model must be fixed, per_time or per_time_channel"
        )
    if backend not in ("rust", "numpy"):
        raise ValueError("backend must be rust or numpy")
    if frequency_blocking and gain_model != "per_time_channel":
        raise ValueError("frequency blocking requires per_time_channel gains")
    obs = Observation(*(jnp.asarray(x) for x in observation))
    rows = len(obs.frequency_hz)
    if (
        not rows
        or np.shape(obs.uvw_m) != (rows, 3)
        or any(np.shape(x) != (rows,) for x in obs[1:])
        or not all(np.isfinite(x).all() for x in obs)
    ):
        raise ValueError("observation must contain finite, consistently shaped rows")
    for array, limit in (
        (obs.antenna1, antenna_count),
        (obs.antenna2, antenna_count),
        (obs.time_index, None),
    ):
        a = np.asarray(array)
        if (
            not np.issubdtype(a.dtype, np.integer)
            or np.any(a < 0)
            or (limit is not None and np.any(a >= limit))
        ):
            raise ValueError("antenna/time indices must be valid nonnegative integers")
    if np.any(np.asarray(obs.frequency_hz) <= 0) or np.any(
        np.asarray(components.flux_jy) <= 0
    ):
        raise ValueError("positive frequencies and component fluxes required")
    prediction = resolve_predictor(
        obs, predictor, beam_axis_ratio=beam_axis_ratio, beam_quartic=beam_quartic
    )
    frequency = np.unique(obs.frequency_hz)
    times = np.unique(obs.time_index)
    ns = len(components.flux_jy)
    sky_count = ns * len(frequency)

    def local_forward(offsets, flux, block_obs):
        return (
            real_stack(
                prediction(components._replace(flux_jy=flux), block_obs, offsets[None])
            )
            / noise_jy
        )

    jacobian = jax.jit(jax.jacfwd(local_forward, argnums=(0, 1)))
    blocks, rotations, ranks, original_rows = [], [], [], []
    raw_information = np.zeros((2, 2))
    for time in times:
        selected = np.asarray(obs.time_index) == time
        block = Observation(*(x[selected] for x in obs))._replace(
            time_index=jnp.zeros(np.sum(selected), dtype=int)
        )
        angles = np.asarray(block.beam_angle_rad)
        if not np.allclose(angles, angles[0], atol=1e-12, rtol=0):
            raise ValueError("one beam angle per observed time required")
        c, s = np.cos(angles[0]), np.sin(angles[0])
        rotation = np.array([[c, s], [-s, c]])
        rotations.append(rotation)
        point, flux = jacobian(jnp.zeros((antenna_count, 2)), components.flux_jy, block)
        point, flux = np.asarray(point), np.asarray(flux)
        common = np.sum(point, axis=1)
        raw = common @ rotation
        raw_information += raw.T @ raw
        sky = np.concatenate(
            [
                flux
                * np.asarray(components.flux_jy)[None, :]
                * np.repeat(np.asarray(block.frequency_hz) == f, 2)[:, None]
                for f in frequency
            ],
            axis=1,
        )
        target = np.column_stack((common, sky))
        nuisance = []
        if gain_model != "fixed":
            stacked = flux @ np.asarray(components.flux_jy)
            visibility = stacked[::2] + 1j * stacked[1::2]
            p, q = np.asarray(block.antenna1), np.asarray(block.antenna2)
            groups = (
                [np.ones(len(p), dtype=bool)]
                if gain_model == "per_time" or frequency_blocking
                else [np.asarray(block.frequency_hz) == f for f in frequency]
            )
            for group in groups:
                for antenna in range(antenna_count):
                    first, second = (
                        (p == antenna).astype(float),
                        (q == antenna).astype(float),
                    )
                    for derivative in (first + second, 1j * (first - second)):
                        value = group * visibility * derivative
                        nuisance.append(
                            np.stack((value.real, value.imag), axis=1).ravel()
                        )
        differential = np.zeros((len(point), 0))
        if differential_pointing:
            differential = (point[:, :-1] - point[:, -1:]).reshape(len(point), -1)
            if not frequency_blocking:
                nuisance.extend(differential.T)
        a = np.column_stack(nuisance) if nuisance else np.zeros((len(point), 0))
        if frequency_blocking:
            _, labels = np.unique(np.asarray(block.frequency_hz), return_inverse=True)
            projected, rank = project_grouped(
                a, differential, target, np.repeat(labels, 2), backend=backend
            )
        elif backend == "rust":
            projected, rank = project_out(a, target)
        else:
            coefficients, _, rank, _ = np.linalg.lstsq(a, target, rcond=1e-12)
            projected = target - a @ coefficients
        # A thin QR preserves every target/sky inner product after projection.
        compressed = np.linalg.qr(projected, mode="r")
        blocks.append(compressed)
        ranks.append(int(rank))
        original_rows.append(len(point))
    total_rows = sum(len(b) for b in blocks)
    matrix = np.zeros((max(total_rows, 1), 2 * len(times) + sky_count))
    start = 0
    for t, block in enumerate(blocks):
        matrix[start : start + len(block), 2 * t : 2 * t + 2] = block[:, :2]
        matrix[start : start + len(block), 2 * len(times) :] = block[:, 2:]
        start += len(block)
    return {
        "matrix": matrix,
        "rotations": np.asarray(rotations),
        "source_count": ns,
        "frequencies_hz": frequency,
        "observed_time_indices": times,
        "raw_information": raw_information,
        "local_nuisance_ranks": ranks,
        "original_real_rows": sum(original_rows),
        "compressed_rows": total_rows,
        "backend": backend,
        "gain_model": gain_model,
        "frequency_blocking": bool(frequency_blocking),
        "differential_pointing": differential_pointing,
        "beam_metadata": getattr(
            prediction,
            "metadata",
            {
                "profile": "analytic",
                "axis_ratio": beam_axis_ratio,
                "quartic": beam_quartic,
            },
        ),
        "prepare_seconds": perf_counter() - started,
    }


def audit_blocked_design(
    design,
    *,
    common_time_variation=True,
    fixed_flux_sources=(),
    log_flux_prior_covariance=None,
):
    """Audit a prepared design repeatedly without regenerating large Jacobians."""
    matrix = np.asarray(design["matrix"])
    count = len(design["observed_time_indices"])
    h = np.asarray(design["rotations"]).reshape(2 * count, 2)
    b = matrix[:, : 2 * count] @ h
    sky = matrix[:, 2 * count :]
    fixed = np.asarray(fixed_flux_sources)
    ns = design["source_count"]
    if fixed.size and (
        not np.issubdtype(fixed.dtype, np.integer)
        or np.any(fixed < 0)
        or np.any(fixed >= ns)
    ):
        raise ValueError("fixed_flux_sources must contain valid indices")
    free = np.tile(~np.isin(np.arange(ns), fixed), len(design["frequencies_hz"]))
    sky = sky[:, free]
    temporal = (
        matrix[:, : 2 * count] @ null_space(h.T)
        if common_time_variation
        else np.zeros((len(matrix), 0))
    )
    a = np.column_stack((sky, temporal))
    raw_scale = np.sqrt(max(np.linalg.eigvalsh(design["raw_information"])[-1], 0.0))
    data_budget = nuisance_information_budget(
        b, a, np.zeros((0, a.shape[1])), reference_scale=raw_scale
    )
    result = {
        "observable_common_modes": data_budget["data_only_rank"],
        "local_crlb_arcsec": None
        if data_budget["local_covariance"] is None
        else (60 * np.sqrt(np.diag(data_budget["local_covariance"]))).tolist(),
        "data_only_information": data_budget["data_only_information"],
        "singular_values_per_arcmin": data_budget["data_only_singular_values"],
        "beam_metadata": design["beam_metadata"],
        "backend": design["backend"],
        "original_real_rows": design["original_real_rows"],
        "compressed_rows": design["compressed_rows"],
        "local_nuisance_ranks": design["local_nuisance_ranks"],
        "prepare_seconds": design["prepare_seconds"],
    }
    if log_flux_prior_covariance is not None:
        covariance = np.asarray(log_flux_prior_covariance)
        if (
            fixed.size
            or covariance.shape != (sky.shape[1], sky.shape[1])
            or np.iscomplexobj(covariance)
            or not np.isfinite(covariance).all()
            or not np.allclose(covariance, covariance.T, atol=1e-15, rtol=1e-12)
        ):
            raise ValueError(
                "finite symmetric log-flux covariance required, without fixed sources"
            )
        try:
            factor = np.linalg.solve(
                np.linalg.cholesky(covariance), np.eye(len(covariance))
            )
        except np.linalg.LinAlgError as error:
            raise ValueError("log-flux covariance must be positive definite") from error
        prior = np.pad(factor, ((0, 0), (0, a.shape[1] - factor.shape[1])))
        budget = nuisance_information_budget(b, a, prior, reference_scale=raw_scale)
        budget["local_sigma_arcsec"] = (
            None
            if budget["local_covariance"] is None
            else (60 * np.sqrt(np.diag(budget["local_covariance"]))).tolist()
        )
        result["information_budget"] = budget
    return result
