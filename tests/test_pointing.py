"""JAX DFT, derivative, spline and recovery controls."""

import pytest

jax = pytest.importorskip("jax")
jax.config.update("jax_enable_x64", True)
import jax.numpy as jnp
import numpy as np
from rangtoy.gauge import gaussian_gauge, predict_channels
from rangtoy.observability import (
    channel_design,
    sky_locked_information,
    solve_sky_locked,
)
from rangtoy.pointing import (
    component_list,
    image_components,
    predict,
    real_stack,
    solve_pointing,
    spline_design,
)


@pytest.fixture(scope="module")
def reference(pointing_reference):
    # Session-scoped in conftest.py: built once for every module.
    return pointing_reference


@pytest.fixture(scope="module")
def full_observation(pointing_full_reference):
    """Complete-coverage Observation, built once (conftest.py)."""
    return pointing_full_reference[2]


def test_dft_and_autodiff_agree_with_rust(reference):
    fixture, components, obs = reference
    theta = jnp.asarray(fixture["pointing_arcmin"])

    def forward(flat):
        offsets = jnp.broadcast_to(flat.reshape(1, 8, 2), (24, 8, 2))
        return real_stack(predict(components, obs, offsets))

    np.testing.assert_allclose(
        forward(theta), fixture["vis_re_im"], atol=2e-9, rtol=2e-9
    )
    jac = jax.jacfwd(forward)(theta)
    np.testing.assert_allclose(jac, fixture["jacobian"], atol=1e-10, rtol=1e-7)
    step = np.zeros(16)
    step[3] = 1e-4
    finite = (forward(theta + step) - forward(theta - step)) / 2e-4
    np.testing.assert_allclose(jac[:, 3], finite, atol=1e-10, rtol=1e-6)


def test_conjugacy_and_w_phase(reference):
    _, components, obs = reference
    offsets = jnp.zeros((24, 8, 2))
    reversed_obs = obs._replace(
        uvw_m=-obs.uvw_m, antenna1=obs.antenna2, antenna2=obs.antenna1
    )
    np.testing.assert_allclose(
        predict(components, reversed_obs, offsets),
        predict(components, obs, offsets).conj(),
        atol=1e-12,
    )
    flat = obs._replace(uvw_m=obs.uvw_m.at[:, 2].set(0))
    assert (
        np.max(
            np.abs(
                predict(components, flat, offsets) - predict(components, obs, offsets)
            )
        )
        > 1e-3
    )


def test_image_flux_and_spline_null_space():
    c = image_components([[1.0, 0], [-0.2, 0.5]], np.zeros((2, 2)), np.zeros((2, 2)))
    assert float(c.flux_jy.sum()) == pytest.approx(1.3)
    empty = image_components(np.zeros((2, 2)), np.zeros((2, 2)), np.zeros((2, 2)))
    assert empty.flux_jy.size == 0
    times = np.linspace(0, 600, 31)
    knots = np.array([0, 100, 350, 600])
    design, penalty = spline_design(times, knots)
    np.testing.assert_allclose(design @ knots, times, atol=1e-12)
    np.testing.assert_allclose(penalty @ knots, 0, atol=1e-10)
    scaled, p_scaled = spline_design(times / 60, knots / 60)
    np.testing.assert_allclose(design, scaled, atol=1e-12)
    np.testing.assert_allclose(penalty, p_scaled, atol=1e-12)
    assert np.linalg.norm(penalty @ [0, 1, -1, 0]) > 1


def test_smooth_pointing_recovery(reference):
    _, components, obs = reference
    times = np.linspace(0, 21600, 24)
    knots = np.linspace(0, 21600, 4)
    design, _ = spline_design(times, knots)
    coefficients = np.random.default_rng(11).normal(0, 0.3, (4, 8, 2))
    truth = np.einsum("tk,kad->tad", design, coefficients)
    data = predict(components, obs, jnp.asarray(truth))
    fit = solve_pointing(
        components, obs, data, times, knots, 8, noise_jy=1e-5, smoothness=0.01
    )
    assert fit["success"], fit["message"]
    assert np.sqrt(np.mean((fit["offsets_arcmin"] - truth) ** 2)) < 1e-3


@pytest.mark.parametrize("fit_pointing", [True, False])
@pytest.mark.parametrize("gain_mode", ["achromatic", "per_channel", "polynomial"])
def test_joint_smooth_gains_flux_and_relative_pointing(
    reference, fit_pointing, gain_mode
):
    _, components, obs = reference
    times, knots = np.linspace(0, 21600, 24), [0, 21600]
    design, _ = spline_design(times, knots)
    rng = np.random.default_rng(91)
    coefficients = rng.normal(0, 0.2, (2, 8, 2))
    coefficients -= coefficients.mean(axis=1, keepdims=True)
    if not fit_pointing:
        coefficients *= 0
    truth = np.einsum("tk,kad->tad", design, coefficients)
    logamp = design @ rng.normal(0, 0.02, (2, 8))
    phase = design @ rng.normal(0, 0.03, (2, 8))
    phase -= phase[:, :1]
    gains = np.exp(logamp + 1j * phase)
    if gain_mode != "achromatic":
        freq, fi = np.unique(obs.frequency_hz, return_inverse=True)
        if gain_mode == "polynomial":
            coordinate = (freq - freq.mean()) / np.ptp(freq)
            amplitude_slope = design @ rng.normal(0, 0.02, (2, 8))
            phase_slope = design @ rng.normal(0, 0.02, (2, 8))
            phase_slope -= phase_slope[:, :1]
            correction = (
                coordinate[None, :, None]
                * (amplitude_slope + 1j * phase_slope)[:, None, :]
            )
        else:
            correction = rng.normal(0, 0.01, (1, len(freq), 8))
        gains = gains[:, None, :] * np.exp(correction)
        row_gains = gains[np.asarray(obs.time_index), fi]
    else:
        row_gains = gains[np.asarray(obs.time_index)]
    data = (
        predict(components, obs, jnp.asarray(truth))
        * row_gains[np.arange(len(obs.time_index)), obs.antenna1]
        * row_gains[np.arange(len(obs.time_index)), obs.antenna2].conj()
    )
    wrong = components._replace(
        flux_jy=components.flux_jy * jnp.array([1, 1.02, 0.98, 1.02])
    )
    fit = solve_pointing(
        wrong,
        obs,
        data,
        times,
        knots,
        8,
        noise_jy=1e-5,
        smoothness=0.01,
        zero_mean_pointing=True,
        gain_prior_sigma=(0.1, 0.1),
        gain_per_channel=gain_mode == "per_channel",
        gain_frequency_degree=1 if gain_mode == "polynomial" else None,
        flux_prior_jy=np.array([0, 0.1, 0.1, 0.1]),
        fit_pointing=fit_pointing,
        estimate_uncertainty=True,
        max_nfev=100,
    )
    assert fit["success"], fit["message"]
    assert fit["gain_model"] == "smooth_" + gain_mode
    assert fit["fit_pointing"] == fit_pointing
    assert fit["uncertainty"]["offset_std_arcmin"].shape == truth.shape
    assert np.isfinite(fit["uncertainty"]["offset_std_arcmin"]).all()
    np.testing.assert_array_equal(fit["uncertainty"]["common_offset_std_arcmin"], 0)
    np.testing.assert_allclose(
        fit["uncertainty"]["relative_offset_std_arcmin"],
        fit["uncertainty"]["offset_std_arcmin"],
        atol=1e-14,
    )
    assert fit["uncertainty"]["flux_std_jy"][0] == 0
    if not fit_pointing:
        assert fit["retained_pointing_modes"] == 0
        np.testing.assert_array_equal(fit["offsets_arcmin"], 0)
        np.testing.assert_array_equal(fit["uncertainty"]["offset_std_arcmin"], 0)
    np.testing.assert_allclose(fit["offsets_arcmin"], truth, atol=1e-3)
    np.testing.assert_allclose(fit["gains"], gains, atol=1e-5)
    np.testing.assert_allclose(fit["flux_jy"], components.flux_jy, atol=1e-5)
    np.testing.assert_allclose(fit["gains"][..., 0].imag, 0, atol=1e-15)


@pytest.mark.parametrize("sigma", [0.1, [0, 1], [1, np.nan], [1, 2, 3]])
def test_invalid_gain_prior(reference, sigma):
    _, components, obs = reference
    data = predict(components, obs, jnp.zeros((24, 8, 2)))
    with pytest.raises(ValueError, match="gain_prior_sigma"):
        solve_pointing(
            components,
            obs,
            data,
            np.linspace(0, 21600, 24),
            [0, 21600],
            8,
            noise_jy=0.001,
            gain_prior_sigma=sigma,
        )


@pytest.mark.parametrize("degree", [-1, 4, 1.5, True])
def test_invalid_gain_frequency_degree(reference, degree):
    _, components, obs = reference
    data = predict(components, obs, jnp.zeros((24, 8, 2)))
    with pytest.raises((ValueError, TypeError), match="gain_frequency_degree"):
        solve_pointing(
            components,
            obs,
            data,
            np.linspace(0, 21600, 24),
            [0, 21600],
            8,
            noise_jy=0.001,
            gain_prior_sigma=(0.1, 0.1),
            gain_frequency_degree=degree,
        )


def test_degree_zero_matches_achromatic_parameterization(reference):
    _, components, obs = reference
    data = predict(components, obs, jnp.zeros((24, 8, 2))) * 1.01
    kwargs = {
        "noise_jy": 0.001,
        "fit_pointing": False,
        "gain_prior_sigma": (0.1, 0.1),
    }
    arguments = (components, obs, data, np.linspace(0, 21600, 24), [0, 21600], 8)
    ordinary = solve_pointing(*arguments, **kwargs)
    polynomial = solve_pointing(*arguments, gain_frequency_degree=0, **kwargs)
    assert ordinary["success"] and polynomial["success"]
    assert ordinary["parameter_count"] == polynomial["parameter_count"]
    assert polynomial["gain_model"] == "smooth_polynomial"
    for channel in range(len(polynomial["gain_frequencies_hz"])):
        np.testing.assert_allclose(
            polynomial["gains"][:, channel], ordinary["gains"], atol=1e-12
        )


@pytest.mark.parametrize("prior,per_channel", [(None, False), ((0.1, 0.1), True)])
def test_polynomial_gains_require_exclusive_gain_prior(reference, prior, per_channel):
    _, components, obs = reference
    data = predict(components, obs, jnp.zeros((24, 8, 2)))
    with pytest.raises(ValueError, match="polynomial gains"):
        solve_pointing(
            components,
            obs,
            data,
            np.linspace(0, 21600, 24),
            [0, 21600],
            8,
            noise_jy=0.001,
            gain_prior_sigma=prior,
            gain_per_channel=per_channel,
            gain_frequency_degree=1,
        )


@pytest.mark.parametrize("knots", [[0, 0, 1], [0], [0, np.nan]])
def test_invalid_knots(knots):
    with pytest.raises(ValueError):
        spline_design([0, 1], knots)


@pytest.mark.parametrize("minimum_information", [None, 0.0])
def test_zero_mean_pointing_recovery(reference, minimum_information):
    _, components, obs = reference
    times = np.linspace(0, 21600, 24)
    knots = np.linspace(0, 21600, 4)
    design, _ = spline_design(times, knots)
    coefficients = np.random.default_rng(71).normal(0, 0.3, (4, 8, 2))
    coefficients -= coefficients.mean(axis=1, keepdims=True)
    truth = np.einsum("tk,kad->tad", design, coefficients)
    data = predict(components, obs, jnp.asarray(truth))
    fit = solve_pointing(
        components,
        obs,
        data,
        times,
        knots,
        8,
        noise_jy=1e-5,
        smoothness=0.01,
        zero_mean_pointing=True,
        minimum_mode_information=minimum_information,
    )
    assert fit["success"], fit["message"]
    assert fit["zero_mean_pointing"]
    assert fit["parameter_count"] == 4 * 7 * 2
    np.testing.assert_allclose(fit["knot_offsets_arcmin"].mean(axis=1), 0, atol=1e-15)
    np.testing.assert_allclose(fit["offsets_arcmin"].mean(axis=1), 0, atol=1e-15)
    assert np.sqrt(np.mean((fit["offsets_arcmin"] - truth) ** 2)) < 1e-3


def test_joint_flux_recovers_pointing_with_wrong_sky(reference):
    _, components, obs = reference
    times = np.linspace(0, 21600, 24)
    knots = np.linspace(0, 21600, 4)
    design, _ = spline_design(times, knots)
    truth = np.einsum(
        "tk,kad->tad", design, np.random.default_rng(19).normal(0, 0.3, (4, 8, 2))
    )
    data = predict(components, obs, jnp.asarray(truth))
    wrong = components._replace(
        flux_jy=components.flux_jy * jnp.array([1, 1.02, 0.98, 1.02])
    )
    fixed = solve_pointing(
        wrong, obs, data, times, knots, 8, noise_jy=1e-4, smoothness=0.01
    )
    joint = solve_pointing(
        wrong,
        obs,
        data,
        times,
        knots,
        8,
        noise_jy=1e-4,
        smoothness=0.01,
        flux_prior_jy=[0, 0.035, 0.025, 0.015],
    )
    assert joint["success"], joint["message"]
    assert np.sqrt(np.mean((fixed["offsets_arcmin"] - truth) ** 2)) > 0.2
    assert np.sqrt(np.mean((joint["offsets_arcmin"] - truth) ** 2)) < 0.002
    np.testing.assert_allclose(joint["flux_jy"], components.flux_jy, atol=1e-5)
    assert joint["flux_jy"][0] == float(components.flux_jy[0])
    assert joint["parameter_count"] == fixed["parameter_count"] + 3


@pytest.mark.parametrize("sigma", [-1, np.nan, np.inf])
def test_invalid_flux_prior(reference, sigma):
    _, components, obs = reference
    with pytest.raises(ValueError, match="flux prior"):
        solve_pointing(
            components,
            obs,
            np.zeros(len(obs.frequency_hz)),
            np.linspace(0, 21600, 24),
            [0, 21600],
            8,
            noise_jy=0.001,
            flux_prior_jy=sigma,
        )


def test_joint_spectrum_recovery(reference):
    _, components, obs = reference
    times = np.linspace(0, 21600, 24)
    truth = jnp.zeros((24, 8, 2))
    data = predict(components, obs, truth)
    wrong = components._replace(
        flux_jy=components.flux_jy * jnp.array([1, 1.02, 0.98, 1.02]),
        spectral_index=components.spectral_index + jnp.array([0, 0.1, -0.1, 0.1]),
    )
    fit = solve_pointing(
        wrong,
        obs,
        data,
        times,
        [0, 7200, 14400, 21600],
        8,
        noise_jy=1e-5,
        smoothness=0.01,
        flux_prior_jy=[0, 0.035, 0.025, 0.015],
        spectral_index_prior=[0, 0.2, 0.2, 0.2],
    )
    assert fit["success"], fit["message"]
    np.testing.assert_allclose(
        fit["spectral_index"], components.spectral_index, atol=1e-4
    )
    assert np.sqrt(np.mean(fit["offsets_arcmin"] ** 2)) < 0.001


def test_mode_selection_can_freeze_every_pointing_parameter(reference):
    _, components, obs = reference
    times = np.linspace(0, 21600, 24)
    data = predict(components, obs, jnp.zeros((24, 8, 2)))
    fit = solve_pointing(
        components,
        obs,
        data,
        times,
        [0, 21600],
        8,
        noise_jy=0.01,
        minimum_mode_information=1e30,
    )
    assert fit["success"]
    assert fit["retained_pointing_modes"] == fit["parameter_count"] == 0
    assert fit["data_jacobian_rank"] == 0
    np.testing.assert_array_equal(fit["offsets_arcmin"], 0)


def test_full_information_basis_preserves_the_solution(reference):
    _, components, obs = reference
    times = np.linspace(0, 21600, 24)
    data = predict(components, obs, jnp.ones((24, 8, 2)) * 0.2)
    kwargs = {
        "noise_jy": 0.001,
        "flux_prior_jy": [0, 0.035, 0.025, 0.015],
        "spectral_index_prior": [0, 0.2, 0.2, 0.2],
    }
    full = solve_pointing(components, obs, data, times, [0, 21600], 8, **kwargs)
    selected = solve_pointing(
        components,
        obs,
        data,
        times,
        [0, 21600],
        8,
        minimum_mode_information=0,
        **kwargs,
    )
    assert selected["retained_pointing_modes"] == 32
    np.testing.assert_allclose(
        selected["offsets_arcmin"], full["offsets_arcmin"], atol=1e-5
    )


def test_circular_sky_locked_gauge_is_exact(reference):
    _, components, obs = reference
    frequencies = np.unique(obs.frequency_hz)
    a = np.array([0.3, -0.2])
    radians = a * np.pi / (180 * 60)
    k = 2 * np.log(2) / (1.02 * 299792458.0 / frequencies / 13.5) ** 2
    lm = np.asarray(components.lmn[:, :2])
    flux = np.tile(np.asarray(components.flux_jy), (len(frequencies), 1))
    changed = flux * np.exp(
        -4 * k[:, None] * (lm @ radians)[None, :] + 2 * k[:, None] * np.sum(radians**2)
    )
    before = np.asarray(channel_design(components, obs, 8, jnp.zeros(2))) @ flux.ravel()
    after = (
        np.asarray(channel_design(components, obs, 8, jnp.asarray(a))) @ changed.ravel()
    )
    np.testing.assert_allclose(after, before, atol=2e-12, rtol=2e-12)


def test_rotation_and_asymmetry_are_both_needed(reference):
    _, components, obs = reference
    circular = sky_locked_information(components, obs, 8, noise_jy=0.001)
    elliptical = sky_locked_information(
        components, obs, 8, noise_jy=0.001, beam_axis_ratio=1.1
    )
    fixed = sky_locked_information(
        components,
        obs._replace(beam_angle_rad=jnp.zeros_like(obs.beam_angle_rad)),
        8,
        noise_jy=0.001,
        beam_axis_ratio=1.1,
    )
    assert circular["observable_common_modes"] == fixed["observable_common_modes"] == 0
    assert elliptical["observable_common_modes"] == 2
    assert circular["retained_derivative_norm_fraction"] < 1e-12


def test_sky_locked_fit_recovers_without_spectral_priors(reference):
    _, components, obs = reference
    a = np.array([0.3, -0.2])
    flux = np.tile(np.asarray(components.flux_jy), 4) * np.linspace(0.9, 1.1, 16)
    y = np.asarray(channel_design(components, obs, 8, jnp.asarray(a), 1.1)) @ flux
    data = y[::2] + 1j * y[1::2]
    result = solve_sky_locked(
        components, obs, data, 8, noise_jy=0.001, beam_axis_ratio=1.1
    )
    assert result["success"]
    np.testing.assert_allclose(result["shift_arcmin"], a, atol=1e-7)
    inferred_shape = solve_sky_locked(
        components,
        obs,
        data,
        8,
        noise_jy=0.001,
        beam_axis_ratio=1.0,
        fit_beam_axis_ratio=True,
    )
    assert inferred_shape["success"]
    assert inferred_shape["fitted_beam_axis_ratio"] == pytest.approx(1.1, abs=1e-7)
    np.testing.assert_allclose(inferred_shape["shift_arcmin"], a, atol=1e-7)
    refused = solve_sky_locked(
        components, obs, data, 8, noise_jy=0.001, beam_axis_ratio=1
    )
    assert not refused["identifiable"]
    assert refused["shift_arcmin"] is None


def test_gain_nuisances_cannot_increase_pointing_information(reference):
    _, components, obs = reference
    results = [
        sky_locked_information(
            components, obs, 8, noise_jy=0.001, beam_axis_ratio=1.1, gain_model=model
        )
        for model in ("fixed", "constant", "per_time")
    ]
    fractions = [result["retained_derivative_norm_fraction"] for result in results]
    assert fractions[0] >= fractions[1] >= fractions[2]
    assert all(result["observable_common_modes"] == 2 for result in results)
    circular = sky_locked_information(
        components, obs, 8, noise_jy=0.001, gain_model="per_time"
    )
    assert circular["observable_common_modes"] == 0
    with pytest.raises(ValueError, match="gain_model"):
        sky_locked_information(components, obs, 8, noise_jy=0.001, gain_model="typo")


def test_complete_reference_preserves_thinned_fixture(
    reference, pointing_full_reference
):
    fixture, _, _ = reference
    full = pointing_full_reference[0]
    rows = np.asarray(full["rows"])
    assert rows.shape == (24 * 4 * 28, 8)
    np.testing.assert_array_equal(rows[::5], fixture["rows"])
    np.testing.assert_allclose(
        np.asarray(full["vis_re_im"]).reshape(-1, 2)[::5].ravel(), fixture["vis_re_im"]
    )
    for t in range(24):
        for f in np.unique(rows[:, 3]):
            selected = rows[(rows[:, 6] == t) & (rows[:, 3] == f)]
            assert len(set(map(tuple, selected[:, 4:6]))) == 28


def test_full_coverage_retains_modes_with_gains_and_differential_pointing(
    reference, full_observation
):
    _, sky, thinned = reference
    obs = full_observation
    kwargs = {
        "noise_jy": 0.001,
        "gain_model": "per_time_channel",
        "differential_pointing": True,
    }
    elliptical = sky_locked_information(sky, obs, 8, beam_axis_ratio=1.1, **kwargs)
    circular = sky_locked_information(sky, obs, 8, **kwargs)
    sparse = sky_locked_information(sky, thinned, 8, beam_axis_ratio=1.1, **kwargs)
    assert elliptical["observable_common_modes"] == 2
    assert elliptical["differential_pointing_parameters"] == 336
    assert elliptical["gain_nuisance_parameters"] == 1536
    assert max(elliptical["local_crlb_arcsec"]) < 1.2
    assert circular["observable_common_modes"] == sparse["observable_common_modes"] == 0


@pytest.mark.parametrize("ratio", [1.0, 1.1, 1.5])
def test_finite_gaussian_gauge_with_nonzero_pointing_and_complex_gains(
    reference, ratio
):
    _, sky, obs = reference
    rng = np.random.default_rng(71)
    offsets = rng.normal(0, 0.3, (24, 8, 2))
    flux = rng.uniform(0.2, 1, (4, 4))
    gains = np.exp(rng.normal(0, 0.1, (24, 8, 4)) + 1j * rng.normal(0, 0.2, (24, 8, 4)))
    changed = gaussian_gauge(obs, sky, offsets, flux, gains, [0.7, -0.4], ratio)
    before = predict_channels(sky, obs, offsets, flux, gains, ratio)
    after = predict_channels(
        sky,
        obs,
        changed["offsets_arcmin"],
        changed["channel_flux_jy"],
        changed["antenna_gains"],
        ratio,
    )
    np.testing.assert_allclose(after, before, rtol=2e-12, atol=2e-12)
    inverse = gaussian_gauge(
        obs,
        sky,
        changed["offsets_arcmin"],
        changed["channel_flux_jy"],
        changed["antenna_gains"],
        [-0.7, 0.4],
        ratio,
    )
    np.testing.assert_allclose(inverse["offsets_arcmin"], offsets, atol=1e-14)
    np.testing.assert_allclose(inverse["channel_flux_jy"], flux, atol=1e-14)
    np.testing.assert_allclose(inverse["antenna_gains"], gains, atol=1e-14)


def test_general_common_motion_restores_gaussian_ambiguity(reference):
    _, sky, obs = reference
    # Full coverage is not necessary for the exact Gaussian null space.
    fixed = sky_locked_information(sky, obs, 8, noise_jy=0.001, beam_axis_ratio=1.1)
    free = sky_locked_information(
        sky, obs, 8, noise_jy=0.001, beam_axis_ratio=1.1, common_time_variation=True
    )
    assert fixed["observable_common_modes"] == 2
    assert free["observable_common_modes"] == 0
    assert free["common_time_nuisance_parameters"] == 46


def test_nonquadratic_rotating_beam_breaks_local_gauge(reference, full_observation):
    _, sky, _ = reference
    obs = full_observation
    kwargs = {
        "noise_jy": 0.001,
        "gain_model": "per_time_channel",
        "differential_pointing": True,
        "common_time_variation": True,
        "beam_quartic": 0.1,
    }
    elliptical = sky_locked_information(sky, obs, 8, beam_axis_ratio=1.1, **kwargs)
    circular = sky_locked_information(sky, obs, 8, **kwargs)
    assert elliptical["observable_common_modes"] == 2
    assert min(elliptical["local_crlb_arcsec"]) > 50
    assert circular["observable_common_modes"] == 0
    with pytest.raises(ValueError, match="beam_quartic"):
        sky_locked_information(sky, obs, 8, noise_jy=0.001, beam_quartic=-1)


def test_flux_anchor_geometry_controls_number_of_common_modes(
    reference, full_observation
):
    _, sky, _ = reference
    obs = full_observation
    for fixed, expected in [([], 0), ([0], 0), ([0, 1], 1), ([0, 1, 2], 2)]:
        result = sky_locked_information(
            sky,
            obs,
            8,
            noise_jy=0.001,
            beam_axis_ratio=1.1,
            gain_model="per_time_channel",
            differential_pointing=True,
            common_time_variation=True,
            fixed_flux_sources=fixed,
        )
        assert result["observable_common_modes"] == expected
        assert result["sky_nuisance_parameters"] == 4 * (4 - len(fixed))
    with pytest.raises(ValueError, match="fixed_flux_sources"):
        sky_locked_information(sky, obs, 8, noise_jy=0.001, fixed_flux_sources=[4])

    lm = np.asarray(sky.lmn[:, :2]).copy()
    lm[2] = -0.8 * lm[1]
    collinear_sky = component_list(lm[:, 0], lm[:, 1], sky.flux_jy, sky.spectral_index)
    collinear = sky_locked_information(
        collinear_sky,
        obs,
        8,
        noise_jy=0.001,
        beam_axis_ratio=1.1,
        gain_model="per_time_channel",
        differential_pointing=True,
        common_time_variation=True,
        fixed_flux_sources=[0, 1, 2],
    )
    assert collinear["observable_common_modes"] == 1


def test_gauge_composition_and_noisy_likelihood(reference):
    _, sky, obs = reference
    rng = np.random.default_rng(29)
    offsets = rng.normal(0, 0.2, (24, 8, 2))
    flux = rng.uniform(0.2, 1, (4, 4))
    gains = np.exp(rng.normal(0, 0.1, (24, 8, 4)) + 1j * rng.normal(0, 0.1, (24, 8, 4)))
    first = gaussian_gauge(obs, sky, offsets, flux, gains, [0.3, -0.1], 1.1)
    composed = gaussian_gauge(
        obs,
        sky,
        first["offsets_arcmin"],
        first["channel_flux_jy"],
        first["antenna_gains"],
        [-0.2, 0.4],
        1.1,
    )
    direct = gaussian_gauge(obs, sky, offsets, flux, gains, [0.1, 0.3], 1.1)
    for key in ("offsets_arcmin", "channel_flux_jy", "antenna_gains"):
        np.testing.assert_allclose(composed[key], direct[key], atol=1e-14, rtol=1e-14)
    before = np.asarray(predict_channels(sky, obs, offsets, flux, gains, 1.1))
    after = np.asarray(
        predict_channels(
            sky,
            obs,
            direct["offsets_arcmin"],
            direct["channel_flux_jy"],
            direct["antenna_gains"],
            1.1,
        )
    )
    data = before + 0.001 * (
        rng.normal(size=len(before)) + 1j * rng.normal(size=len(before))
    )
    first_chi2 = np.sum(np.abs(before - data) ** 2) / 0.001**2
    second_chi2 = np.sum(np.abs(after - data) ** 2) / 0.001**2
    assert abs(first_chi2 - second_chi2) < 1e-8


def test_correlated_flux_constraints_do_not_create_data_information(
    reference, full_observation
):
    _, sky, thinned = reference
    obs = full_observation
    kwargs = {
        "noise_jy": 0.001,
        "beam_axis_ratio": 1.1,
        "gain_model": "per_time_channel",
        "differential_pointing": True,
        "common_time_variation": True,
    }
    covariance = 0.01**2 * np.eye(16)
    gaussian = sky_locked_information(
        sky, obs, 8, log_flux_prior_covariance=covariance, **kwargs
    )
    scale = sky_locked_information(
        sky,
        obs,
        8,
        log_flux_prior_covariance=covariance + 0.05**2 * np.ones((16, 16)),
        **kwargs,
    )
    budget = gaussian["information_budget"]
    assert gaussian["observable_common_modes"] == 0
    assert budget["constrained_rank"] == 2
    assert max(budget["data_only_fraction_eigenvalues"]) < 1e-12
    np.testing.assert_allclose(
        budget["local_sigma_arcsec"], [6.2691, 6.7314], atol=1e-3
    )
    np.testing.assert_allclose(
        scale["information_budget"]["total_information"],
        budget["total_information"],
        atol=1e-9,
    )
    shaped = sky_locked_information(
        sky, obs, 8, log_flux_prior_covariance=covariance, beam_quartic=0.1, **kwargs
    )
    assert shaped["observable_common_modes"] == 2
    assert all(
        0 < f < 0.02
        for f in shaped["information_budget"]["data_only_fraction_eigenvalues"]
    )
    # The validation runs after the nuisance design is built, so it is
    # checked on the thinned rows: the same four channels and 16 x 16 shape.
    with pytest.raises(ValueError, match="positive definite"):
        sky_locked_information(
            sky, thinned, 8, log_flux_prior_covariance=-covariance, **kwargs
        )
