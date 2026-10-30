"""Local sky-prior-free observability of an array-common sky-frame shift."""

import jax
import jax.numpy as jnp
import numpy as np
from scipy.linalg import null_space
from scipy.optimize import least_squares

from .pointing import predict, real_stack, resolve_predictor


def nuisance_information_budget(
    pointing, nuisance, prior_factor, *, reference_scale=None
):
    """Local information split for whitened data and a Gaussian nuisance prior.

    prior_factor maps nuisance perturbations to whitened external residuals.
    No pointing prior is imposed. Matrices are in the supplied pointing units.
    The conditioned data term is not the independently identifiable data term.
    """
    b, a, l = map(np.asarray, (pointing, nuisance, prior_factor))
    if (
        b.ndim != 2
        or a.ndim != 2
        or l.ndim != 2
        or b.shape[0] != a.shape[0]
        or l.shape[1] != a.shape[1]
    ):
        raise ValueError("incompatible two-dimensional design matrices")
    if not all(np.isfinite(x).all() and not np.iscomplexobj(x) for x in (b, a, l)):
        raise ValueError("design matrices must be finite and real")
    data_only = b - a @ np.linalg.lstsq(a, b, rcond=None)[0]
    augmented = np.vstack((a, l))
    target = np.vstack((b, np.zeros((len(l), b.shape[1]))))
    response = np.linalg.lstsq(augmented, target, rcond=None)[0]
    data_residual = b - a @ response
    external_residual = l @ response
    f_data = data_only.T @ data_only
    f_conditioned = data_residual.T @ data_residual
    f_external = external_residual.T @ external_residual
    f_total = f_conditioned + f_external
    _, singular, vh = np.linalg.svd(
        np.vstack((data_residual, external_residual)), full_matrices=False
    )
    raw_scale = np.linalg.norm(b, ord=2) if reference_scale is None else reference_scale
    if not np.isfinite(raw_scale) or raw_scale < 0:
        raise ValueError("reference scale must be finite and nonnegative")
    data_singular = np.linalg.svd(data_only, compute_uv=False)
    rank = int(np.sum(singular > raw_scale * 1e-10))
    fraction = None
    covariance = None
    if rank == b.shape[1]:
        whitening = (vh.T / singular) @ vh
        fraction = np.linalg.eigvalsh(whitening @ f_data @ whitening).tolist()
        covariance = ((vh.T / singular**2) @ vh).tolist()
    return {
        "data_only_information": f_data.tolist(),
        "data_only_rank": int(np.sum(data_singular > raw_scale * 1e-10)),
        "data_only_singular_values": data_singular.tolist(),
        "conditioned_data_information": f_conditioned.tolist(),
        "external_information": f_external.tolist(),
        "total_information": f_total.tolist(),
        "data_only_fraction_eigenvalues": fraction,
        "constrained_rank": rank,
        "local_covariance": covariance,
    }


def channel_design(
    components, observation, antenna_count, shift_arcmin, beam_axis_ratio=1.0
):
    """Real-stacked DFT matrix for independent source/channel integrated fluxes.

    Columns ordered frequency then source. All antennas share a constant
    sky-frame shift, rotated row-by-row into antenna coordinates. No spectral
    smoothness is imposed. The spectral indices in components are ignored.
    """
    ntime = int(np.max(np.asarray(observation.time_index))) + 1
    angles = np.zeros(ntime)
    for t in range(ntime):
        values = np.asarray(observation.beam_angle_rad)[
            np.asarray(observation.time_index) == t
        ]
        if len(values):
            angles[t] = values[0]
    cos, sin = jnp.cos(jnp.asarray(angles)), jnp.sin(jnp.asarray(angles))
    a = shift_arcmin
    shifted = jnp.stack((cos * a[0] + sin * a[1], -sin * a[0] + cos * a[1]), axis=1)
    offsets = jnp.broadcast_to(shifted[:, None, :], (ntime, antenna_count, 2))

    def flux_model(flux):
        sky = components._replace(flux_jy=flux, spectral_index=jnp.zeros_like(flux))
        return predict(sky, observation, offsets, beam_axis_ratio=beam_axis_ratio)

    responses = jax.jacfwd(flux_model)(jnp.zeros_like(components.flux_jy))
    columns = jnp.concatenate(
        [
            responses * jnp.asarray(np.asarray(observation.frequency_hz) == f)[:, None]
            for f in np.unique(observation.frequency_hz)
        ],
        axis=1,
    )
    return jnp.stack((columns.real, columns.imag), axis=1).reshape(
        2 * columns.shape[0], columns.shape[1]
    )


def solve_sky_locked(
    components,
    observation,
    visibilities,
    antenna_count,
    *,
    noise_jy,
    beam_axis_ratio=1.0,
    fit_beam_axis_ratio=False,
):
    """Profile arbitrary channel fluxes and fit just two shared pointing modes.

    Refuse if the local sky-prior-free audit finds a null direction. Other
    pointing modes and direction-independent gains are held fixed. This is
    an isolated ambiguity experiment, not the full per-antenna solver. When
    fit_beam_axis_ratio is True, jointly fit log axial ratio and check local
    rank at the resulting solution; the initial shape audit is not a veto.
    """
    data = np.asarray(visibilities)
    if data.shape != np.shape(observation.frequency_hz) or not np.isfinite(data).all():
        raise ValueError(
            "visibilities must be a finite vector matching observation rows"
        )
    audit = sky_locked_information(
        components,
        observation,
        antenna_count,
        noise_jy=noise_jy,
        beam_axis_ratio=beam_axis_ratio,
    )
    if audit["observable_common_modes"] < 2 and not fit_beam_axis_ratio:
        return {
            "identifiable": False,
            "success": False,
            "shift_arcmin": None,
            "reason": "Common sky-frame pointing is degenerate with free channel fluxes",
            "audit": audit,
        }
    y = real_stack(jnp.asarray(visibilities)) / noise_jy

    def profiled(parameters):
        a = parameters[:2]
        ratio = jnp.exp(parameters[2]) if fit_beam_axis_ratio else beam_axis_ratio
        design = (
            channel_design(components, observation, antenna_count, a, ratio) / noise_jy
        )
        flux = jnp.linalg.solve(design.T @ design, design.T @ y)
        return design @ flux - y

    fun = jax.jit(profiled)
    jac = jax.jit(jax.jacfwd(profiled))
    fit = least_squares(
        lambda a: np.asarray(fun(a)),
        np.array([0.0, 0.0, np.log(beam_axis_ratio)])
        if fit_beam_axis_ratio
        else np.zeros(2),
        jac=lambda a: np.asarray(jac(a)),
        ftol=1e-11,
        xtol=1e-11,
        gtol=1e-11,
    )
    singular = np.linalg.svd(fit.jac, compute_uv=False)
    if singular[-1] <= singular[0] * 1e-10:
        return {
            "identifiable": False,
            "success": False,
            "shift_arcmin": None,
            "reason": "Profiled pointing/shape Jacobian is rank deficient at the fitted solution",
            "audit": audit,
        }
    fitted_ratio = float(np.exp(fit.x[2])) if fit_beam_axis_ratio else beam_axis_ratio
    design = np.asarray(
        channel_design(
            components, observation, antenna_count, jnp.asarray(fit.x[:2]), fitted_ratio
        )
    )
    flux = np.linalg.lstsq(
        design, np.asarray(real_stack(jnp.asarray(visibilities))), rcond=None
    )[0]
    return {
        "identifiable": True,
        "success": bool(fit.success),
        "message": fit.message,
        "shift_arcmin": fit.x[:2].tolist(),
        "fitted_beam_axis_ratio": fitted_ratio,
        "fit_beam_axis_ratio": fit_beam_axis_ratio,
        "channel_flux_jy": flux.tolist(),
        "local_sigma_arcsec": (
            60 * np.sqrt(np.diag(np.linalg.inv(fit.jac.T @ fit.jac))[:2])
        ).tolist(),
        "cost": float(fit.cost),
        "audit": audit,
    }


def sky_locked_information(
    components,
    observation,
    antenna_count,
    *,
    noise_jy,
    beam_axis_ratio=1.0,
    gain_model="fixed",
    differential_pointing=False,
    common_time_variation=False,
    beam_quartic=0.0,
    fixed_flux_sources=(),
    log_flux_prior_covariance=None,
    predictor=None,
):
    """Project common pointing derivatives off free source/channel fluxes.

    Linearize at zero pointing. Each source has an independent amplitude at
    each observed frequency, with no sky prior unless its index is in
    fixed_flux_sources (then its channel fluxes are known exactly).
    This is a local Fisher audit,
    not a fit or an uncertainty interval for a nonlinear trajectory estimate.
    Optional complex antenna gains are unconstrained nuisances, constant over
    the observation (constant) or independent at each time (per_time). Both
    models share gains across frequency; per_time_channel instead frees each
    time/channel gain. Linearization is at unit gains;
    least-squares projection handles the redundant gain/sky gauge columns.
    differential_pointing frees zero-mean antenna offsets independently at
    each time, without a smoothness prior. Other common temporal modes remain
    fixed unless common_time_variation is True. That option frees the
    Euclidean-orthogonal complement of the two sky-locked trajectories.
    log_flux_prior_covariance optionally supplies a positive-definite external
    log-flux covariance, ordered frequency then source. It cannot be combined
    with exactly fixed sources. Log flux requires positive component fluxes.
    """
    if not jax.config.x64_enabled:
        raise ValueError("enable JAX 64-bit mode before constructing inputs")
    prediction = resolve_predictor(
        observation,
        predictor,
        beam_axis_ratio=beam_axis_ratio,
        beam_quartic=beam_quartic,
    )
    if not np.isfinite(noise_jy) or noise_jy <= 0:
        raise ValueError("noise must be finite and positive")
    if not np.isfinite(beam_axis_ratio) or beam_axis_ratio <= 0:
        raise ValueError("beam axis ratio must be finite and positive")
    if not np.isfinite(beam_quartic) or beam_quartic < 0:
        raise ValueError("beam_quartic must be finite and nonnegative")
    fixed_flux_sources = np.asarray(fixed_flux_sources)
    if fixed_flux_sources.size and (
        not np.issubdtype(fixed_flux_sources.dtype, np.integer)
        or np.any(fixed_flux_sources < 0)
        or np.any(fixed_flux_sources >= len(components.flux_jy))
    ):
        raise ValueError("fixed_flux_sources must contain valid source indices")
    if gain_model not in ("fixed", "constant", "per_time", "per_time_channel"):
        raise ValueError(
            "gain_model must be fixed, constant, per_time or per_time_channel"
        )
    ntime = int(np.max(np.asarray(observation.time_index))) + 1
    angles = np.zeros(ntime)
    for t in range(ntime):
        values = np.asarray(observation.beam_angle_rad)[
            np.asarray(observation.time_index) == t
        ]
        if len(values):
            if not np.allclose(values, values[0], atol=1e-12, rtol=0):
                raise ValueError("one common beam angle per time required")
            angles[t] = values[0]
    cos, sin = jnp.cos(jnp.asarray(angles)), jnp.sin(jnp.asarray(angles))

    def common_offsets(a):
        shift = jnp.stack((cos * a[0] + sin * a[1], -sin * a[0] + cos * a[1]), axis=1)
        return jnp.broadcast_to(shift[:, None, :], (ntime, antenna_count, 2))

    def forward(a, flux):
        return (
            real_stack(
                prediction(
                    components._replace(flux_jy=flux),
                    observation,
                    common_offsets(a),
                )
            )
            / noise_jy
        )

    pointing = np.asarray(
        jax.jacfwd(forward, argnums=0)(jnp.zeros(2), components.flux_jy)
    )
    source = np.asarray(
        jax.jacfwd(forward, argnums=1)(jnp.zeros(2), components.flux_jy)
    )
    frequency = np.asarray(observation.frequency_hz)
    if log_flux_prior_covariance is not None:
        if fixed_flux_sources.size or np.any(np.asarray(components.flux_jy) <= 0):
            raise ValueError(
                "log-flux priors require positive fluxes and no fixed sources"
            )
        source = source * np.asarray(components.flux_jy)[None, :]
    source = source[:, ~np.isin(np.arange(source.shape[1]), fixed_flux_sources)]
    nuisance = np.concatenate(
        [source * np.repeat(frequency == f, 2)[:, None] for f in np.unique(frequency)],
        axis=1,
    )
    sky_count = nuisance.shape[1]
    if gain_model != "fixed":
        visibility = (
            np.asarray(
                prediction(
                    components,
                    observation,
                    common_offsets(jnp.zeros(2)),
                )
            )
            / noise_jy
        )
        p, q = np.asarray(observation.antenna1), np.asarray(observation.antenna2)
        time = np.asarray(observation.time_index)
        groups = (
            [np.ones(len(time), dtype=bool)]
            if gain_model == "constant"
            else [time == t for t in np.unique(time)]
        )
        if gain_model == "per_time_channel":
            groups = [
                group & (frequency == f)
                for group in groups
                for f in np.unique(frequency)
            ]
        columns = []
        for group in groups:
            for antenna in range(antenna_count):
                first, second = (
                    (p == antenna).astype(float),
                    (q == antenna).astype(float),
                )
                # g_p conjugate(g_q): log amplitudes add, phases subtract.
                for derivative in (first + second, 1j * (first - second)):
                    value = visibility * group * derivative
                    columns.append(np.stack((value.real, value.imag), axis=1).ravel())
        nuisance = np.column_stack((nuisance, *columns))
    gain_count = nuisance.shape[1] - sky_count
    if differential_pointing:
        # Independent zero-mean antenna deviations at each time. The last
        # antenna balances the other antennas, excluding the common modes.
        def differential_model(values):
            offsets = jnp.concatenate(
                (values, -jnp.sum(values, axis=1, keepdims=True)), axis=1
            )
            return (
                real_stack(
                    prediction(
                        components,
                        observation,
                        offsets,
                    )
                )
                / noise_jy
            )

        derivative = np.asarray(
            jax.jacfwd(differential_model)(jnp.zeros((ntime, antenna_count - 1, 2)))
        ).reshape(len(pointing), -1)
        nuisance = np.column_stack((nuisance, derivative))
    differential_count = nuisance.shape[1] - sky_count - gain_count
    if common_time_variation:
        target = np.asarray(jax.jacfwd(common_offsets)(jnp.zeros(2)))[:, 0].reshape(
            -1, 2
        )
        complement = jnp.asarray(null_space(target.T))

        def common_model(values):
            shifts = (complement @ values).reshape(ntime, 2)
            offsets = jnp.broadcast_to(shifts[:, None, :], (ntime, antenna_count, 2))
            return (
                real_stack(
                    prediction(
                        components,
                        observation,
                        offsets,
                    )
                )
                / noise_jy
            )

        derivative = np.asarray(
            jax.jacfwd(common_model)(jnp.zeros(complement.shape[1]))
        )
        nuisance = np.column_stack((nuisance, derivative))
    residual = pointing - nuisance @ np.linalg.lstsq(nuisance, pointing, rcond=None)[0]
    singular = np.linalg.svd(residual, compute_uv=False)
    raw_singular = np.linalg.svd(pointing, compute_uv=False)
    tolerance = raw_singular[0] * 1e-10
    rank = int(np.sum(singular > tolerance))
    crlb = None
    if rank == 2:
        crlb = (60 * np.sqrt(np.diag(np.linalg.inv(residual.T @ residual)))).tolist()
    result = {
        "beam_metadata": getattr(
            prediction,
            "metadata",
            {
                "profile": "analytic",
                "axis_ratio": beam_axis_ratio,
                "quartic": beam_quartic,
            },
        ),
        "beam_axis_ratio": beam_axis_ratio,
        "beam_quartic": beam_quartic,
        "noise_jy_per_component": noise_jy,
        "sky_nuisance_parameters": sky_count,
        "fixed_flux_sources": fixed_flux_sources.astype(int).tolist(),
        "gain_model": gain_model,
        "gain_nuisance_parameters": gain_count,
        "differential_pointing_parameters": differential_count,
        "common_time_nuisance_parameters": nuisance.shape[1]
        - sky_count
        - gain_count
        - differential_count,
        "observable_common_modes": rank,
        "singular_values_per_arcmin": singular.tolist(),
        "known_sky_singular_values_per_arcmin": raw_singular.tolist(),
        "retained_derivative_norm_fraction": float(
            np.linalg.norm(residual) / max(np.linalg.norm(pointing), 1e-30)
        ),
        "local_crlb_arcsec": crlb,
    }
    if log_flux_prior_covariance is not None:
        covariance = np.asarray(log_flux_prior_covariance)
        if (
            covariance.shape != (sky_count, sky_count)
            or np.iscomplexobj(covariance)
            or not np.isfinite(covariance).all()
            or not np.allclose(covariance, covariance.T, rtol=1e-12, atol=1e-15)
        ):
            raise ValueError(
                "log-flux covariance must be finite, symmetric and match all source/channel amplitudes"
            )
        try:
            factor = np.linalg.solve(np.linalg.cholesky(covariance), np.eye(sky_count))
        except np.linalg.LinAlgError as error:
            raise ValueError("log-flux covariance must be positive definite") from error
        prior = np.pad(factor, ((0, 0), (0, nuisance.shape[1] - sky_count)))
        budget = nuisance_information_budget(pointing, nuisance, prior)
        budget["local_sigma_arcsec"] = (
            None
            if budget["local_covariance"] is None
            else (60 * np.sqrt(np.diag(budget["local_covariance"]))).tolist()
        )
        result["information_budget"] = budget
    return result
