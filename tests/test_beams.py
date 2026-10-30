"""Stable beam derivatives, upstream comparisons and predictor integration."""

import pytest

jax = pytest.importorskip("jax")
jax.config.update("jax_enable_x64", True)
import jax.numpy as jnp
import numpy as np
from rang.beams import (
    beam_table,
    cosine_taper,
    load_katbeam,
    make_beam_predictor,
    predict_tabulated,
    voltage_beam,
)
from rang.observability import sky_locked_information
from rang.pointing import C, predict, solve_pointing


@pytest.fixture(scope="module")
def fixture(pointing_reference):
    # Session-scoped in conftest.py: built once for every module.
    _, components, obs = pointing_reference
    return components, obs


def test_cosine_taper_center_half_power_and_removable_pole():
    scale = 1.1889647809329453
    assert cosine_taper(0.0) == pytest.approx(1.0)
    assert cosine_taper(0.25) == pytest.approx(np.sqrt(0.5), abs=1e-14)
    pole = 0.25 / scale**2
    assert cosine_taper(pole) == pytest.approx(np.pi / 4, abs=1e-14)
    assert jax.grad(cosine_taper)(pole) == pytest.approx(
        -np.pi * scale**2 / 4, abs=1e-12
    )
    assert jax.grad(cosine_taper)(0.0) == pytest.approx((4 - np.pi**2 / 2) * scale**2)
    hessian = jax.hessian(lambda x: cosine_taper(jnp.sum(x**2)))(jnp.zeros(2))
    np.testing.assert_allclose(
        hessian, 2 * (4 - np.pi**2 / 2) * scale**2 * np.eye(2), atol=1e-12
    )
    # Signed sidelobes, rather than sqrt(power), retain the voltage convention.
    assert cosine_taper(4.0) < 0


@pytest.mark.parametrize("pol", ["H", "V"])
def test_beam_matches_pinned_katbeam(pol):
    katbeam = pytest.importorskip("katbeam")
    table, metadata = load_katbeam(pol)
    rng = np.random.default_rng(8)
    x, y = rng.uniform(-2, 2, (6, 25)), rng.uniform(-2, 2, (6, 25))
    frequencies = np.array([900.0, 975.0, 1150.0, 1284.0, 1550.0, 1650.0])
    actual = np.asarray(
        voltage_beam(
            jnp.deg2rad(x), jnp.deg2rad(y), jnp.asarray(frequencies * 1e6), table
        )
    )
    model = katbeam.JimBeam("MKAT-AA-L-JIM-2020")
    evaluate = model.HH if pol == "H" else model.VV
    expected = np.stack([evaluate(x[i], y[i], f) for i, f in enumerate(frequencies)])
    # Upstream 0.1 rounds the radius scale to eight decimal places.
    np.testing.assert_allclose(actual, expected, rtol=1e-7, atol=2e-9)
    assert metadata["katbeam_version"] == "0.1"


def test_tabulated_gaussian_reproduces_original_dft(fixture):
    sky, obs = fixture
    frequencies = np.unique(obs.frequency_hz)
    width = 1.02 * C / frequencies / 13.5
    ratio = 1.1
    table = beam_table(
        frequencies,
        np.zeros((4, 2)),
        width[:, None] * np.array([1 / np.sqrt(ratio), np.sqrt(ratio)]),
    )
    offsets = jnp.asarray(np.random.default_rng(21).normal(0, 0.4, (24, 8, 2)))
    np.testing.assert_allclose(
        predict_tabulated(sky, obs, offsets, table, "gaussian"),
        predict(sky, obs, offsets, beam_axis_ratio=ratio),
        atol=1e-13,
    )


def test_table_validation_and_no_extrapolation(fixture):
    _, obs = fixture
    with pytest.raises(ValueError, match="strictly increasing"):
        beam_table([1e9, 1e9], np.zeros((2, 2)), np.ones((2, 2)))
    with pytest.raises(ValueError, match="positive"):
        beam_table([1e9, 2e9], np.zeros((2, 2)), -np.ones((2, 2)))
    table = beam_table([1e9, 1.5e9], np.zeros((2, 2)), np.ones((2, 2)))
    predictor = make_beam_predictor(table)
    with pytest.raises(ValueError, match="outside"):
        predictor.validate_observation(obs)
    assert np.isnan(
        voltage_beam(jnp.zeros((1, 1)), jnp.zeros((1, 1)), jnp.array([2e9]), table)
    ).all()


def test_custom_predictor_derivatives_and_solver(fixture):
    pytest.importorskip("katbeam")
    sky, obs = fixture
    table, metadata = load_katbeam()
    predictor = make_beam_predictor(table, metadata=metadata)
    offsets = jnp.ones((24, 8, 2)) * 0.2
    derivative = jax.jacfwd(lambda a: predictor(sky, obs, offsets.at[:, 0, 0].add(a)))(
        0.0
    )
    step = 1e-4
    finite = (
        predictor(sky, obs, offsets.at[:, 0, 0].add(step))
        - predictor(sky, obs, offsets.at[:, 0, 0].add(-step))
    ) / (2 * step)
    np.testing.assert_allclose(derivative, finite, atol=2e-11)
    fitted = solve_pointing(
        sky,
        obs,
        predictor(sky, obs, offsets),
        np.linspace(0, 21600, 24),
        [0, 21600],
        8,
        noise_jy=1e-5,
        offset_prior_arcmin=1e4,
        predictor=predictor,
    )
    assert fitted["success"]
    np.testing.assert_allclose(fitted["offsets_arcmin"], offsets, atol=1e-6)
    with pytest.raises(ValueError, match="cannot be combined"):
        sky_locked_information(
            sky, obs, 8, noise_jy=0.001, predictor=predictor, beam_axis_ratio=1.1
        )


def test_joint_width_recovery_and_derivative(fixture):
    pytest.importorskip("katbeam")
    sky, obs = fixture
    table, _ = load_katbeam()
    predictor = make_beam_predictor(table)
    offsets = jnp.zeros((24, 8, 2))
    fn = lambda width: predictor.with_log_width(sky, obs, offsets, width)
    step = 1e-5
    np.testing.assert_allclose(
        jax.jacfwd(fn)(0.01),
        (fn(0.01 + step) - fn(0.01 - step)) / (2 * step),
        atol=1e-10,
    )
    fit = solve_pointing(
        sky,
        obs,
        fn(np.log(1.01)),
        np.linspace(0, 21600, 24),
        [0, 21600],
        8,
        noise_jy=1e-5,
        zero_mean_pointing=True,
        gain_prior_sigma=(0.1, 0.1),
        beam_log_width_prior=0.03,
        predictor=predictor,
        estimate_uncertainty=True,
    )
    assert fit["success"]
    assert fit["beam_width_multiplier"] == pytest.approx(1.01, abs=1e-7)
    assert fit["uncertainty"]["beam_log_width_std"] > 0
    np.testing.assert_allclose(fit["offsets_arcmin"], 0, atol=1e-4)


def test_antenna_widths_match_uniform_table_change_and_derivatives(fixture):
    pytest.importorskip("katbeam")
    sky, obs = fixture
    table, _ = load_katbeam()
    offsets = jnp.full((24, 8, 2), 0.2)
    nominal = make_beam_predictor(table)
    uniform = make_beam_predictor(table, antenna_log_width=np.full(8, 0.01))
    uniform.validate_observation(obs)
    np.testing.assert_allclose(
        uniform(sky, obs, offsets),
        nominal.with_log_width(sky, obs, offsets, 0.01),
        atol=1e-13,
    )
    widths = jnp.linspace(-0.02, 0.02, 8)
    function = lambda delta: predict_tabulated(
        sky, obs, offsets, table, antenna_log_width=widths.at[3].add(delta)
    )
    derivative = jax.jacfwd(function)(0.0)
    step = 1e-5
    np.testing.assert_allclose(
        derivative, (function(step) - function(-step)) / (2 * step), atol=1e-9
    )
    unaffected = (np.asarray(obs.antenna1) != 3) & (np.asarray(obs.antenna2) != 3)
    np.testing.assert_array_equal(derivative[unaffected], 0)
    assert np.linalg.norm(derivative) > 0
    for invalid in ([], [np.nan], [[0]], [1000]):
        with pytest.raises(ValueError, match="antenna_log_width"):
            make_beam_predictor(table, antenna_log_width=invalid)
    with pytest.raises(ValueError, match="antenna indices"):
        make_beam_predictor(table, antenna_log_width=[0]).validate_observation(obs)


def test_joint_relative_antenna_width_and_common_pointing_recovery(fixture):
    pytest.importorskip("katbeam")
    sky, obs = fixture
    table, _ = load_katbeam()
    predictor = make_beam_predictor(table)
    widths = jnp.linspace(-0.015, 0.015, 8)
    offsets = jnp.full((24, 8, 2), 0.2)
    parameters = jnp.array([0.01, 0.0, 0.0])
    function = lambda a: predictor.with_antenna_shape(
        sky, obs, offsets, parameters, widths.at[2].add(a)
    )
    step = 1e-5
    np.testing.assert_allclose(
        jax.jacfwd(function)(0.0),
        (function(step) - function(-step)) / (2 * step),
        atol=1e-9,
    )
    fit = solve_pointing(
        sky,
        obs,
        function(0.0),
        np.linspace(0, 21600, 24),
        [0, 21600],
        8,
        noise_jy=1e-5,
        zero_mean_pointing=True,
        gain_prior_sigma=(0.1, 0.1),
        beam_log_width_prior=0.03,
        beam_antenna_log_width_prior=0.03,
        common_pointing_prior_arcmin=1.0,
        predictor=predictor,
        estimate_uncertainty=True,
    )
    assert fit["success"]
    np.testing.assert_allclose(fit["beam_antenna_log_width"], widths, atol=1e-6)
    assert abs(fit["beam_antenna_log_width"].mean()) < 1e-16
    np.testing.assert_allclose(fit["offsets_arcmin"], offsets, atol=1e-4)
    assert fit["beam_width_multiplier"] == pytest.approx(np.exp(0.01), abs=1e-6)
    assert np.all(fit["uncertainty"]["beam_antenna_log_width_std"] > 0)
    assert fit["uncertainty"]["flux_std_jy"].shape == (4,)
    assert fit["uncertainty"]["relative_offset_std_arcmin"].shape == (24, 8, 2)
    assert fit["uncertainty"]["common_offset_std_arcmin"].shape == (24, 2)
    assert np.all(fit["uncertainty"]["common_offset_std_arcmin"] > 0)


@pytest.mark.parametrize("prior", [0.0, -0.01, np.nan])
def test_invalid_relative_antenna_width_prior(fixture, prior):
    sky, obs = fixture
    with pytest.raises(ValueError, match="antenna beam prior"):
        solve_pointing(
            sky,
            obs,
            np.zeros(len(obs.time_index), complex),
            np.linspace(0, 21600, 24),
            [0, 21600],
            8,
            noise_jy=0.001,
            beam_antenna_log_width_prior=prior,
        )


def test_antenna_width_fit_requires_predictor_support(fixture):
    sky, obs = fixture
    with pytest.raises(ValueError, match="with_antenna_shape"):
        solve_pointing(
            sky,
            obs,
            np.zeros(len(obs.time_index), complex),
            np.linspace(0, 21600, 24),
            [0, 21600],
            8,
            noise_jy=0.001,
            beam_antenna_log_width_prior=0.03,
        )


def test_beam_shape_derivatives_and_joint_recovery(fixture):
    pytest.importorskip("katbeam")
    sky, obs = fixture
    table, _ = load_katbeam()
    predictor = make_beam_predictor(table)
    offsets = jnp.zeros((24, 8, 2))
    truth = jnp.array([0.01, -0.005, 0.02])
    fn = lambda p: predictor.with_shape(sky, obs, offsets, p)
    jac = jax.jacfwd(fn)(truth)
    for i in range(3):
        step = np.eye(3)[i] * 1e-5
        np.testing.assert_allclose(
            jac[:, i], (fn(truth + step) - fn(truth - step)) / 2e-5, atol=1e-10
        )
    np.testing.assert_allclose(
        predictor.with_shape(sky, obs, offsets, jnp.array([0.01, 0, 0])),
        predictor.with_log_width(sky, obs, offsets, 0.01),
        atol=1e-14,
    )
    fit = solve_pointing(
        sky,
        obs,
        fn(truth),
        np.linspace(0, 21600, 24),
        [0, 21600],
        8,
        noise_jy=1e-5,
        zero_mean_pointing=True,
        predictor=predictor,
        gain_prior_sigma=(0.1, 0.1),
        beam_shape_prior=[0.03] * 3,
        estimate_uncertainty=True,
    )
    assert fit["success"]
    np.testing.assert_allclose(fit["beam_shape_parameters"], truth, atol=1e-6)
    assert np.all(fit["uncertainty"]["beam_shape_std"] > 0)


@pytest.mark.parametrize("prior", [[1, 2], [1, -1, 0], [1, np.nan, 0]])
def test_invalid_shape_prior(fixture, prior):
    sky, obs = fixture
    with pytest.raises(ValueError, match="three finite nonnegative"):
        solve_pointing(
            sky,
            obs,
            jnp.zeros(len(obs.frequency_hz)),
            np.linspace(0, 21600, 24),
            [0, 21600],
            8,
            noise_jy=0.001,
            beam_shape_prior=prior,
        )


def test_common_and_relative_pointing_decomposition(fixture):
    pytest.importorskip("katbeam")
    sky, obs = fixture
    table, _ = load_katbeam()
    predictor = make_beam_predictor(table)
    times = np.linspace(0, 21600, 24)
    relative = np.random.default_rng(6).normal(0, 0.1, (1, 8, 2))
    relative -= relative.mean(axis=1, keepdims=True)
    relative = np.broadcast_to(relative, (24, 8, 2))
    common = np.column_stack((np.linspace(0.3, 0.6, 24), np.linspace(-0.2, -0.1, 24)))
    total = relative + common[:, None, :]
    data = predictor(sky, obs, jnp.asarray(total))
    fit = solve_pointing(
        sky,
        obs,
        data,
        times,
        [0, 21600],
        8,
        noise_jy=1e-5,
        zero_mean_pointing=True,
        common_pointing_prior_arcmin=3,
        gain_prior_sigma=(0.1, 0.1),
        predictor=predictor,
        estimate_uncertainty=True,
    )
    assert fit["success"]
    np.testing.assert_allclose(
        fit["relative_offsets_arcmin"].mean(axis=1), 0, atol=1e-15
    )
    np.testing.assert_allclose(
        fit["offsets_arcmin"],
        fit["relative_offsets_arcmin"] + fit["common_offsets_arcmin"][:, None, :],
        atol=1e-15,
    )
    np.testing.assert_allclose(fit["common_offsets_arcmin"], common, atol=1e-4)
    np.testing.assert_allclose(fit["relative_offsets_arcmin"], relative, atol=1e-4)
    with pytest.raises(ValueError, match="requires zero-mean"):
        solve_pointing(
            sky,
            obs,
            data,
            times,
            [0, 21600],
            8,
            noise_jy=0.001,
            common_pointing_prior_arcmin=1,
        )


def test_chromatic_shape_lifts_the_gaussian_gauge(fixture, pointing_full_reference):
    pytest.importorskip("katbeam")
    sky, _ = fixture
    obs = pointing_full_reference[2]
    table, metadata = load_katbeam()
    zero_squint = table._replace(squint_rad=jnp.zeros_like(table.squint_rad))
    kwargs = {
        "noise_jy": 0.001,
        "gain_model": "per_time_channel",
        "differential_pointing": True,
        "common_time_variation": True,
    }
    native = sky_locked_information(
        sky,
        obs,
        8,
        predictor=make_beam_predictor(zero_squint, "gaussian", metadata),
        **kwargs,
    )
    assert native["observable_common_modes"] == 2
    np.testing.assert_allclose(
        native["local_crlb_arcsec"], [8.40284, 8.30909], atol=0.002
    )
    widths = np.asarray(table.fwhm_rad)
    geometric = np.sqrt(np.prod(widths, axis=1))
    fixed = zero_squint._replace(
        fwhm_rad=jnp.asarray(
            geometric[:, None] * np.array([1 / np.sqrt(1.03), np.sqrt(1.03)])
        )
    )
    null = sky_locked_information(
        sky, obs, 8, predictor=make_beam_predictor(fixed, "gaussian"), **kwargs
    )
    assert null["observable_common_modes"] == 0
