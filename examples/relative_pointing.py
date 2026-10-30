"""Controlled relative/common pointing recovery with a scalar katbeam beam."""

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rangtoy import toy_output
from rangtoy.beams import beam_table, load_katbeam, make_beam_predictor
from rangtoy.pointing import Observation, component_list, solve_pointing, spline_design


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[7, 11, 19])
    parser.add_argument(
        "--antenna-beam-log-width-std",
        type=float,
        default=0.0,
        help="Inject independent antenna log-width errors, demeaned across antennas",
    )
    parser.add_argument(
        "--known-antenna-beam",
        action="store_true",
        help="Oracle control: supply the injected per-antenna widths to the fitter",
    )
    parser.add_argument(
        "--beam-antenna-log-width-prior",
        type=float,
        default=None,
        help="Fit zero-mean per-antenna log-width deviations with this contrast prior sigma",
    )
    parser.add_argument(
        "--gain-frequency-degree",
        type=int,
        default=None,
        help="Fit Chebyshev-polynomial log gains instead of independent channels",
    )
    parser.add_argument(
        "--common-prior-arcmin",
        type=float,
        default=None,
        help="Fit shared pointing with a zero-centred knot prior (gain-only baseline still fixes all pointing)",
    )
    parser.add_argument(
        "--beam-log-width-prior",
        type=float,
        default=None,
        help="Jointly fit shared beam width with this log-width prior sigma",
    )
    parser.add_argument(
        "--holdout-mode", choices=["interleaved", "contiguous"], default="interleaved"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Report conditional local interval coverage for joint-flux zero-common case only",
    )
    parser.add_argument(
        "--truth-seed",
        type=int,
        default=None,
        help="Keep pointing and gain truth fixed while varying noise seeds",
    )
    parser.add_argument(
        "--missing-source-jy",
        type=float,
        default=0.0,
        help="Inject an unmodelled point source at direction cosines (0.003,-0.004)",
    )
    parser.add_argument(
        "--chromatic-gain-curvature",
        type=float,
        default=0.0,
        help="Scale of quadratic-frequency log-gain truth with .02/.03 knot sigmas",
    )
    parser.add_argument(
        "--chromatic-gain-truth",
        type=float,
        default=0.0,
        help="Scale of smooth spectral gain slopes: 1 gives knot std .02 log-amplitude and .03 rad per .4 GHz",
    )
    parser.add_argument(
        "--spectral-index-prior",
        type=float,
        default=None,
        help="Jointly fit source spectral indices with this prior sigma in joint-flux/gain-only cases",
    )
    parser.add_argument(
        "--gain-per-channel",
        action="store_true",
        help="Fit independent time-smooth gains per frequency",
    )
    parser.add_argument(
        "--beam-width-error",
        type=float,
        default=0.0,
        help="Fractional true FWHM change absent from fitted beam",
    )
    parser.add_argument(
        "--pointing-ripple-arcmin",
        type=float,
        default=0.0,
        help="Out-of-family sinusoidal pointing amplitude",
    )
    parser.add_argument(
        "--held-out",
        action="store_true",
        help="Hold out every fourth time and add a gain/sky-only baseline",
    )
    parser.add_argument(
        "--joint-gains",
        action="store_true",
        help="Inject and fit smooth gains (achromatic unless specified otherwise)",
    )
    args = parser.parse_args()
    if (
        not np.isfinite(args.antenna_beam_log_width_std)
        or args.antenna_beam_log_width_std < 0
    ):
        parser.error("antenna beam scatter must be finite and nonnegative")
    if args.known_antenna_beam and args.antenna_beam_log_width_std == 0:
        parser.error("known antenna beam control requires nonzero beam scatter")
    if not np.isfinite(args.chromatic_gain_truth) or args.chromatic_gain_truth < 0:
        parser.error("chromatic gain truth scale must be finite and nonnegative")
    if (
        not np.isfinite(args.chromatic_gain_curvature)
        or args.chromatic_gain_curvature < 0
    ):
        parser.error("chromatic gain curvature must be finite and nonnegative")
    if (
        args.chromatic_gain_truth or args.chromatic_gain_curvature
    ) and not args.joint_gains:
        parser.error("chromatic gain truth requires --joint-gains")
    if args.spectral_index_prior is not None and (
        not np.isfinite(args.spectral_index_prior) or args.spectral_index_prior <= 0
    ):
        parser.error("spectral index prior must be finite and positive")
    if not np.isfinite(args.missing_source_jy) or args.missing_source_jy < 0:
        parser.error("missing source flux must be finite and nonnegative")
    if args.gain_per_channel and not args.joint_gains:
        parser.error("--gain-per-channel requires --joint-gains")
    if not np.isfinite(args.beam_width_error) or args.beam_width_error <= -1:
        parser.error("beam width error must be finite and greater than -1")
    if not np.isfinite(args.pointing_ripple_arcmin) or args.pointing_ripple_arcmin < 0:
        parser.error("pointing ripple must be finite and nonnegative")
    if args.held_out and not args.joint_gains:
        parser.error(
            "--held-out requires --joint-gains for the gain/sky-only comparison"
        )
    jax.config.update("jax_enable_x64", True)
    raw = toy_output("--pointing-full-reference").encode()
    fixture = json.loads(raw)
    r, s = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    obs = Observation(
        jnp.asarray(r[:, :3]),
        jnp.asarray(r[:, 3]),
        *(jnp.asarray(r[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(r[:, 7]),
    )
    sky = component_list(s[:, 0], s[:, 1], s[:, 2], s[:, 3])
    true_sky = sky
    if args.missing_source_jy:
        true_sky = component_list(
            np.r_[s[:, 0], 0.003],
            np.r_[s[:, 1], -0.004],
            np.r_[s[:, 2], args.missing_source_jy],
            np.r_[s[:, 3], -0.7],
        )
    table, metadata = load_katbeam("H")
    predictor = make_beam_predictor(table, metadata=metadata)
    true_table = beam_table(
        table.frequency_hz,
        table.squint_rad,
        table.fwhm_rad * (1 + args.beam_width_error),
    )
    times, knots = np.linspace(0, 21600, 24), np.linspace(0, 21600, 4)
    design, _ = spline_design(times, knots)
    sigma = 0.001
    test = (
        np.asarray(obs.time_index) % 4 == 2
        if args.held_out
        else np.zeros(len(r), dtype=bool)
    )
    if args.held_out and args.holdout_mode == "contiguous":
        test = (np.asarray(obs.time_index) >= 9) & (np.asarray(obs.time_index) <= 14)
    train_obs = Observation(*(a[~test] for a in obs))
    results = []
    for seed in args.seeds:
        antenna_widths = None
        if args.antenna_beam_log_width_std:
            beam_rng = np.random.default_rng(
                np.random.SeedSequence(
                    [seed if args.truth_seed is None else args.truth_seed, 2189]
                )
            )
            antenna_widths = beam_rng.normal(0, args.antenna_beam_log_width_std, 8)
            antenna_widths -= antenna_widths.mean()
        true_predictor = make_beam_predictor(
            true_table, antenna_log_width=antenna_widths
        )
        if args.known_antenna_beam:
            predictor = make_beam_predictor(
                table, metadata=metadata, antenna_log_width=antenna_widths
            )
        rng = np.random.default_rng(
            seed if args.truth_seed is None else args.truth_seed
        )
        coefficients = rng.normal(0, 0.3, (4, 8, 2))
        coefficients -= coefficients.mean(axis=1, keepdims=True)
        relative = np.einsum("tk,kad->tad", design, coefficients)
        ripple = args.pointing_ripple_arcmin * np.sin(
            2 * np.pi * times[:, None, None] / 5400 + np.arange(16).reshape(1, 8, 2)
        )
        relative += ripple - ripple.mean(axis=1, keepdims=True)
        noise_rng = rng if args.truth_seed is None else np.random.default_rng(seed)
        noise = sigma * (
            noise_rng.normal(size=len(r)) + 1j * noise_rng.normal(size=len(r))
        )
        gains = np.ones((24, 8), dtype=complex)
        if args.joint_gains:
            logamp = design @ rng.normal(0, 0.02, (4, 8))
            phase = design @ rng.normal(0, 0.03, (4, 8))
            phase -= phase[:, :1]
            gains = np.exp(logamp + 1j * phase)
        baseline_gain = (
            gains[obs.time_index, obs.antenna1]
            * gains[obs.time_index, obs.antenna2].conj()
        )
        if args.chromatic_gain_truth or args.chromatic_gain_curvature:
            amplitude_slope = design @ rng.normal(0, 0.02, (4, 8))
            phase_slope = design @ rng.normal(0, 0.03, (4, 8))
            phase_slope -= phase_slope[:, :1]
            coordinate = (np.asarray(obs.frequency_hz) - 1.3e9) / 0.4e9
            slopes = args.chromatic_gain_truth * (amplitude_slope + 1j * phase_slope)
            row_log_gains = coordinate[:, None] * slopes[obs.time_index]
            if args.chromatic_gain_curvature:
                amplitude_curve = design @ rng.normal(0, 0.02, (4, 8))
                phase_curve = design @ rng.normal(0, 0.03, (4, 8))
                phase_curve -= phase_curve[:, :1]
                curves = args.chromatic_gain_curvature * (
                    amplitude_curve + 1j * phase_curve
                )
                row_log_gains += coordinate[:, None] ** 2 * curves[obs.time_index]
            row_gains = np.exp(row_log_gains)
            baseline_gain *= (
                row_gains[np.arange(len(r)), obs.antenna1]
                * row_gains[np.arange(len(r)), obs.antenna2].conj()
            )
        for common_arcmin in (0.0,) if args.coverage else (0.0, 0.5):
            truth = relative + np.array([common_arcmin, -common_arcmin])[None, None, :]
            clean = np.asarray(true_predictor(true_sky, obs, jnp.asarray(truth)))
            clean = clean * baseline_gain
            data = clean + noise
            cases = ["known_sky", "wrong_fixed_sky", "joint_flux"]
            if args.held_out:
                cases.append("gain_sky_only")
            if args.coverage:
                cases = ["joint_flux"]
            for case in cases:
                supplied = (
                    sky
                    if case == "known_sky"
                    else sky._replace(
                        flux_jy=sky.flux_jy * jnp.array([1.0, 1.02, 0.98, 1.02])
                    )
                )
                started = perf_counter()
                fit = solve_pointing(
                    supplied,
                    train_obs,
                    data[~test],
                    times,
                    knots,
                    8,
                    noise_jy=sigma,
                    smoothness=0.01,
                    predictor=predictor,
                    zero_mean_pointing=True,
                    fit_pointing=case != "gain_sky_only",
                    gain_prior_sigma=(0.1, 0.1) if args.joint_gains else None,
                    gain_per_channel=args.gain_per_channel,
                    gain_frequency_degree=args.gain_frequency_degree,
                    estimate_uncertainty=args.coverage,
                    beam_log_width_prior=args.beam_log_width_prior,
                    beam_antenna_log_width_prior=args.beam_antenna_log_width_prior,
                    common_pointing_prior_arcmin=args.common_prior_arcmin
                    if case != "gain_sky_only"
                    else None,
                    flux_prior_jy=np.asarray(supplied.flux_jy) * 0.05
                    if case in ("joint_flux", "gain_sky_only")
                    else None,
                    spectral_index_prior=args.spectral_index_prior
                    if case in ("joint_flux", "gain_sky_only")
                    else None,
                )
                solve_seconds = perf_counter() - started
                recovered_sky = supplied._replace(
                    flux_jy=jnp.asarray(fit["flux_jy"]),
                    spectral_index=jnp.asarray(fit["spectral_index"]),
                )
                model = np.asarray(
                    predictor.with_log_width(
                        recovered_sky,
                        obs,
                        jnp.asarray(fit["offsets_arcmin"]),
                        np.log(fit["beam_width_multiplier"]),
                    )
                )
                if args.beam_antenna_log_width_prior is not None:
                    model = np.asarray(
                        predictor.with_antenna_shape(
                            recovered_sky,
                            obs,
                            jnp.asarray(fit["offsets_arcmin"]),
                            fit["beam_shape_parameters"],
                            fit["beam_antenna_log_width"],
                        )
                    )
                recovered_gains = fit["gains"]
                if fit["gain_frequencies_hz"] is not None:
                    fi = np.searchsorted(
                        fit["gain_frequencies_hz"], np.asarray(obs.frequency_hz)
                    )
                    recovered_gains = recovered_gains[np.asarray(obs.time_index), fi]
                    model = (
                        model
                        * recovered_gains[np.arange(len(r)), obs.antenna1]
                        * recovered_gains[np.arange(len(r)), obs.antenna2].conj()
                    )
                else:
                    model = (
                        model
                        * recovered_gains[obs.time_index, obs.antenna1]
                        * recovered_gains[obs.time_index, obs.antenna2].conj()
                    )
                result = {
                    "seed": seed,
                    "case": case,
                    "common_offset_per_axis_arcmin": common_arcmin,
                    "success": fit["success"],
                    "nfev": fit["nfev"],
                    "parameter_count": fit["parameter_count"],
                    "true_antenna_log_width": None
                    if antenna_widths is None
                    else antenna_widths.tolist(),
                    "beam_width_multiplier": fit["beam_width_multiplier"],
                    "fitted_relative_antenna_log_width": fit[
                        "beam_antenna_log_width"
                    ].tolist(),
                    "antenna_log_width_rmse": float(
                        np.sqrt(
                            np.mean(
                                (
                                    fit["beam_antenna_log_width"]
                                    - (
                                        np.zeros(8)
                                        if antenna_widths is None
                                        or args.known_antenna_beam
                                        else antenna_widths
                                    )
                                )
                                ** 2
                            )
                        )
                    ),
                    "solve_seconds_including_compilation": solve_seconds,
                    "relative_rmse_arcsec": float(
                        60
                        * np.sqrt(
                            np.mean((fit["relative_offsets_arcmin"] - relative) ** 2)
                        )
                    ),
                    "common_pointing_rmse_arcsec": float(
                        60
                        * np.sqrt(
                            np.mean(
                                (
                                    fit["common_offsets_arcmin"]
                                    - np.array([common_arcmin, -common_arcmin])
                                )
                                ** 2
                            )
                        )
                    ),
                    "maximum_mean_arcsec": float(
                        60 * np.max(np.abs(fit["offsets_arcmin"].mean(axis=1)))
                    ),
                    "clean_visibility_rms_mjy": float(
                        1000 * np.sqrt(np.mean(np.abs(model - clean) ** 2))
                    ),
                    "whitened_residual_mean_square": float(
                        np.mean(np.abs(model - data) ** 2) / (2 * sigma**2)
                    ),
                    "flux_fractional_error": (
                        np.asarray(fit["flux_jy"]) / np.asarray(sky.flux_jy) - 1
                    ).tolist(),
                    "spectral_index_error": (
                        fit["spectral_index"] - np.asarray(sky.spectral_index)
                    ).tolist(),
                    "maximum_flux_ratio_fractional_error": float(
                        np.max(
                            np.abs(
                                (fit["flux_jy"] / fit["flux_jy"][0])
                                / np.asarray(sky.flux_jy / sky.flux_jy[0])
                                - 1
                            )
                        )
                    ),
                }
                results.append(result)
                if args.coverage:
                    uncertainty = fit["uncertainty"]
                    error = fit["offsets_arcmin"] - relative
                    std = uncertainty["offset_std_arcmin"]
                    flux_error = np.asarray(fit["flux_jy"]) - np.asarray(sky.flux_jy)
                    result["pointing_coverage_95_fraction"] = float(
                        np.mean(np.abs(error) <= 1.959963984540054 * std)
                    )
                    result["pointing_standardized_error_rms"] = float(
                        np.sqrt(np.mean((error / std) ** 2))
                    )
                    result["median_pointing_std_arcsec"] = float(60 * np.median(std))
                    for name, delta in (
                        ("relative", fit["relative_offsets_arcmin"] - relative),
                        (
                            "common",
                            fit["common_offsets_arcmin"]
                            - np.array([common_arcmin, -common_arcmin]),
                        ),
                    ):
                        marginal_std = uncertainty[name + "_offset_std_arcmin"]
                        result[name + "_pointing_coverage_95_fraction"] = float(
                            np.mean(np.abs(delta) <= 1.959963984540054 * marginal_std)
                        )
                        result[name + "_median_pointing_std_arcsec"] = float(
                            60 * np.median(marginal_std)
                        )
                    result["flux_coverage_95_per_source"] = (
                        np.abs(flux_error)
                        <= 1.959963984540054 * uncertainty["flux_std_jy"]
                    ).tolist()
                    result["flux_std_jy"] = uncertainty["flux_std_jy"].tolist()
                    result["beam_log_width_std"] = uncertainty["beam_log_width_std"]
                    result["beam_antenna_log_width_std"] = uncertainty[
                        "beam_antenna_log_width_std"
                    ].tolist()
                    if args.beam_antenna_log_width_prior is not None:
                        expected_widths = (
                            np.zeros(8)
                            if antenna_widths is None or args.known_antenna_beam
                            else antenna_widths
                        )
                        result["beam_antenna_width_coverage_95_fraction"] = float(
                            np.mean(
                                np.abs(fit["beam_antenna_log_width"] - expected_widths)
                                <= 1.959963984540054
                                * uncertainty["beam_antenna_log_width_std"]
                            )
                        )
                    ratio = np.asarray(fit["flux_jy"]) / fit["flux_jy"][0]
                    true_ratio = np.asarray(sky.flux_jy) / sky.flux_jy[0]
                    ratio_std = uncertainty["flux_ratio_to_first_std"]
                    result["flux_ratio_coverage_95_offaxis"] = (
                        np.abs(ratio[1:] - true_ratio[1:])
                        <= 1.959963984540054 * ratio_std[1:]
                    ).tolist()
                    result["flux_ratio_std"] = ratio_std.tolist()
                if args.held_out:
                    for label, mask in (("train", ~test), ("test", test)):
                        result[label + "_whitened_residual_mean_square"] = float(
                            np.mean(np.abs(model[mask] - data[mask]) ** 2)
                            / (2 * sigma**2)
                        )
                        result[label + "_clean_visibility_rms_mjy"] = float(
                            1000
                            * np.sqrt(np.mean(np.abs(model[mask] - clean[mask]) ** 2))
                        )
                print(json.dumps(result), flush=True)
    payload = {
        "fixture_sha256": sha256(raw).hexdigest(),
        "beam": metadata,
        "antenna_beam_log_width_std_before_demeaning": args.antenna_beam_log_width_std,
        "known_antenna_beam": args.known_antenna_beam,
        "noise_per_real_component_jy": sigma,
        "joint_gains": args.joint_gains,
        "truth_seed": args.truth_seed,
        "coverage": args.coverage,
        "beam_log_width_prior": args.beam_log_width_prior,
        "beam_antenna_log_width_prior": args.beam_antenna_log_width_prior,
        "common_pointing_prior_arcmin": args.common_prior_arcmin,
        "gain_per_channel": args.gain_per_channel,
        "gain_frequency_degree": args.gain_frequency_degree,
        "chromatic_gain_truth_scale": args.chromatic_gain_truth,
        "chromatic_gain_curvature_scale": args.chromatic_gain_curvature,
        "spectral_index_prior": args.spectral_index_prior,
        "true_fractional_beam_width_error": args.beam_width_error,
        "pointing_ripple_arcmin": args.pointing_ripple_arcmin,
        "missing_source_jy": args.missing_source_jy,
        "held_out": args.held_out,
        "holdout_mode": args.holdout_mode,
        "test_time_indices": np.unique(np.asarray(obs.time_index)[test]).tolist(),
        "train_rows": int((~test).sum()),
        "test_rows": int(test.sum()),
        "limitations": "Synthetic beam/spline model with specified perturbations. Held-out mode withholds whole times listed in test_time_indices (interpolation, not extrapolation); hyperparameters fixed beforehand. Coverage uses correlated coordinates, not independent trials, and local Gauss-Newton intervals including priors. Injected log gains optionally have linear and quadratic frequency dependence with smooth temporal coefficients; fitted gains may be per-channel or polynomial. Gain slopes and prior scales are assumptions, not empirical measurements. Polynomial coefficient priors differ from independent-channel priors. Absolute flux scale and common spectral slope are prior-dependent. Historical pointing records are not injected. Timings include compilation and are not a controlled performance benchmark.",
        "results": results,
    }
    output = ROOT / (
        "outputs/joint-gain-pointing"
        if args.joint_gains
        else "outputs/relative-pointing"
    )
    if args.held_out:
        output = output.with_name(output.name + "-heldout")
        if args.holdout_mode == "contiguous":
            output = output.with_name(output.name + "-contiguous")
    if args.antenna_beam_log_width_std:
        output = output.with_name(
            output.name + f"-antbeam{args.antenna_beam_log_width_std:g}"
        )
    if args.known_antenna_beam:
        output = output.with_name(output.name + "-knownantbeam")
    if args.coverage:
        output = output.with_name(output.name + f"-coverage-truth{args.truth_seed}")
    if args.common_prior_arcmin is not None:
        output = output.with_name(
            output.name + f"-commonprior{args.common_prior_arcmin:g}"
        )
    if args.beam_log_width_prior is not None:
        output = output.with_name(
            output.name + f"-beamprior{args.beam_log_width_prior:g}"
        )
    if args.beam_antenna_log_width_prior is not None:
        output = output.with_name(
            output.name + f"-antbeamprior{args.beam_antenna_log_width_prior:g}"
        )
    if args.gain_per_channel:
        output = output.with_name(output.name + "-channelgains")
    if args.gain_frequency_degree is not None:
        output = output.with_name(
            output.name + f"-gainpoly{args.gain_frequency_degree}"
        )
    if args.chromatic_gain_truth:
        output = output.with_name(
            output.name + f"-chromatic{args.chromatic_gain_truth:g}"
        )
    if args.chromatic_gain_curvature:
        output = output.with_name(
            output.name + f"-curvature{args.chromatic_gain_curvature:g}"
        )
    if args.spectral_index_prior is not None:
        output = output.with_name(
            output.name + f"-spectralprior{args.spectral_index_prior:g}"
        )
    if args.missing_source_jy:
        output = output.with_name(output.name + f"-missing{args.missing_source_jy:g}")
    if args.beam_width_error or args.pointing_ripple_arcmin:
        output = output.with_name(
            output.name
            + f"-width{args.beam_width_error:g}-ripple{args.pointing_ripple_arcmin:g}"
        )
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
