"""Paired fixed-sky/joint-flux pointing stress test with known-sky control."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rangtoy import toy_output
from rangtoy.pointing import Observation, component_list, predict, solve_pointing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(1, 21)))
    parser.add_argument("--flux-error", type=float, default=0.02)
    parser.add_argument("--flux-prior", type=float, default=0.05)
    parser.add_argument("--spectral-error", type=float, default=0.0)
    parser.add_argument("--spectral-prior", type=float)
    parser.add_argument("--noise", type=float, default=0.001)
    parser.add_argument("--smoothness", type=float, default=0.01)
    parser.add_argument("--minimum-mode-information", type=float)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/sky-uncertainty")
    args = parser.parse_args()
    if not np.isfinite(args.flux_error) or abs(args.flux_error) >= 1:
        parser.error("flux-error must be finite with absolute value below 1")
    if not np.isfinite(args.flux_prior) or args.flux_prior <= 0:
        parser.error("flux-prior must be finite and positive")
    if not np.isfinite(args.spectral_error):
        parser.error("spectral-error must be finite")
    if not np.isfinite(args.noise) or args.noise <= 0:
        parser.error("noise must be finite and positive")
    if args.spectral_prior is not None and (
        not np.isfinite(args.spectral_prior) or args.spectral_prior <= 0
    ):
        parser.error("spectral-prior must be finite and positive")
    jax.config.update("jax_enable_x64", True)
    fixture_bytes = toy_output("--pointing-reference").encode()
    fixture = json.loads(fixture_bytes)
    rows, sources = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    truth_sky = component_list(
        sources[:, 0], sources[:, 1], sources[:, 2], sources[:, 3]
    )
    # Fixed signs, not optimized to maximize or minimize pointing bias. The
    # central source remains correct and fixed as an explicit flux anchor.
    model_sky = truth_sky._replace(
        flux_jy=truth_sky.flux_jy * (1 + args.flux_error * jnp.array([0, 1, -1, 1])),
        spectral_index=truth_sky.spectral_index
        + args.spectral_error * jnp.array([0, 1, -1, 1]),
    )
    prior = args.flux_prior * np.asarray(model_sky.flux_jy)
    prior[0] = 0
    obs = Observation(
        jnp.asarray(rows[:, :3]),
        jnp.asarray(rows[:, 3]),
        *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(rows[:, 7]),
    )
    times, knots = np.linspace(0, 21600, 24), np.linspace(0, 21600, 6)
    heldout = np.asarray(obs.time_index) % 4 == 2
    training = Observation(*(a[~heldout] for a in obs))
    output = []
    for seed in args.seeds:
        rng = np.random.default_rng(seed)
        bias, phase = rng.normal(0, 0.3, (8, 2)), rng.uniform(0, 2 * np.pi, (8, 2))
        truth = bias[None] + 0.25 * np.sin(
            2 * np.pi * times[:, None, None] / times[-1] + phase
        )
        data = np.asarray(predict(truth_sky, obs, jnp.asarray(truth))) + args.noise * (
            rng.normal(size=len(rows)) + 1j * rng.normal(size=len(rows))
        )
        alpha_prior = (
            None
            if args.spectral_prior is None
            else np.array([0, 1, 1, 1]) * args.spectral_prior
        )
        methods = [
            ("known_sky", truth_sky, None, None, None),
            ("fixed_wrong_sky", model_sky, None, None, None),
            ("joint_flux_pointing", model_sky, prior, None, None),
        ]
        if alpha_prior is not None:
            methods.append(
                ("joint_spectrum_pointing", model_sky, prior, alpha_prior, None)
            )
        if args.minimum_mode_information is not None:
            methods.append(
                (
                    "selected_pointing_modes",
                    model_sky,
                    prior,
                    alpha_prior,
                    args.minimum_mode_information,
                )
            )
        for method, sky, sigma, alpha_sigma, threshold in methods:
            fit = solve_pointing(
                sky,
                training,
                data[~heldout],
                times,
                knots,
                8,
                noise_jy=args.noise,
                smoothness=args.smoothness,
                flux_prior_jy=sigma,
                spectral_index_prior=alpha_sigma,
                minimum_mode_information=threshold,
            )
            fitted_sky = sky._replace(
                flux_jy=jnp.asarray(fit["flux_jy"]),
                spectral_index=jnp.asarray(fit["spectral_index"]),
            )
            prediction = np.asarray(
                predict(fitted_sky, obs, jnp.asarray(fit["offsets_arcmin"]))
            )
            # Diagnostic only: projection of array-common trajectory error
            # onto a constant sky-frame shift rotated into the antenna frame.
            angles = np.array([rows[rows[:, 6] == t, 7][0] for t in range(len(times))])
            error_common = (fit["offsets_arcmin"] - truth).mean(axis=1)
            sky_error = np.column_stack(
                (
                    np.cos(angles) * error_common[:, 0]
                    - np.sin(angles) * error_common[:, 1],
                    np.sin(angles) * error_common[:, 0]
                    + np.cos(angles) * error_common[:, 1],
                )
            )
            locked_fraction = float(
                len(times)
                * np.sum(sky_error.mean(axis=0) ** 2)
                / max(np.sum(error_common**2), 1e-30)
            )
            output.append(
                {
                    "seed": seed,
                    "method": method,
                    "success": fit["success"],
                    "message": fit["message"],
                    "nfev": fit["nfev"],
                    "pointing_rmse_arcsec": float(
                        60 * np.sqrt(np.mean((fit["offsets_arcmin"] - truth) ** 2))
                    ),
                    "heldout_rms_mjy": float(
                        1000
                        * np.sqrt(
                            np.mean(np.abs((prediction - data)[heldout]) ** 2) / 2
                        )
                    ),
                    "flux_rmse_mjy": float(
                        1000
                        * np.sqrt(np.mean((fit["flux_jy"][1:] - sources[1:, 2]) ** 2))
                    ),
                    "flux_jy": fit["flux_jy"].tolist(),
                    "spectral_index": fit["spectral_index"].tolist(),
                    "spectral_rmse": float(
                        np.sqrt(
                            np.mean((fit["spectral_index"][1:] - sources[1:, 3]) ** 2)
                        )
                    ),
                    "retained_pointing_modes": fit["retained_pointing_modes"],
                    "sky_locked_common_error_fraction": locked_fraction,
                    "common_pointing_rmse_arcsec": float(
                        60
                        * np.sqrt(
                            np.mean((fit["offsets_arcmin"] - truth).mean(axis=1) ** 2)
                        )
                    ),
                    "differential_pointing_rmse_arcsec": float(
                        60
                        * np.sqrt(
                            np.mean(
                                (
                                    (fit["offsets_arcmin"] - truth)
                                    - (fit["offsets_arcmin"] - truth).mean(
                                        axis=1, keepdims=True
                                    )
                                )
                                ** 2
                            )
                        )
                    ),
                    "data_rank": fit["data_jacobian_rank"],
                    "parameters": fit["parameter_count"],
                }
            )
        print(f"Seed {seed} complete", flush=True)
    summary = {}
    for method in dict.fromkeys(row["method"] for row in output):
        selected = [row for row in output if row["method"] == method]
        summary[method] = {
            key: {
                "mean": float(np.mean([r[key] for r in selected])),
                "std": float(np.std([r[key] for r in selected], ddof=1))
                if len(selected) > 1
                else 0.0,
            }
            for key in [
                "pointing_rmse_arcsec",
                "heldout_rms_mjy",
                "flux_rmse_mjy",
                "spectral_rmse",
                "retained_pointing_modes",
                "common_pointing_rmse_arcsec",
                "differential_pointing_rmse_arcsec",
                "sky_locked_common_error_fraction",
            ]
        }
    result = {
        "seeds": args.seeds,
        "fractional_flux_error": args.flux_error,
        "fractional_flux_prior": args.flux_prior,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "noise_jy_per_component": args.noise,
        "smoothness": args.smoothness,
        "spectral_index_error": args.spectral_error,
        "spectral_index_prior": args.spectral_prior,
        "minimum_mode_information": args.minimum_mode_information,
        "offset_prior_arcmin": 3,
        "knots_s": knots.tolist(),
        "jax_version": jax.__version__,
        "truth_flux_jy": sources[:, 2].tolist(),
        "model_flux_jy": np.asarray(model_sky.flux_jy).tolist(),
        "runs": output,
        "summary": summary,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if not all(r["success"] for r in output):
        raise SystemExit("One or more fits failed; retained in results")


if __name__ == "__main__":
    main()
