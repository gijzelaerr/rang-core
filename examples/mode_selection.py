"""Equal-budget validation comparison of full and information-selected pointing."""

import argparse
import json
import sys
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rang import toy_output
from rang.pointing import Observation, component_list, predict, solve_pointing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(1, 21)))
    parser.add_argument("--noise", type=float, default=0.01)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/mode-selection")
    args = parser.parse_args()
    jax.config.update("jax_enable_x64", True)
    fixture = json.loads(toy_output("--pointing-reference").encode())
    rows, sources = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    actual_sky = component_list(
        sources[:, 0], sources[:, 1], sources[:, 2], sources[:, 3]
    )
    pattern = jnp.array([0, 1, -1, 1])
    sky = actual_sky._replace(
        flux_jy=actual_sky.flux_jy * (1 + 0.02 * pattern),
        spectral_index=actual_sky.spectral_index + 0.1 * pattern,
    )
    flux_prior = np.asarray(sky.flux_jy) * 0.05
    flux_prior[0] = 0
    alpha_prior = [0, 0.2, 0.2, 0.2]
    obs = Observation(
        jnp.asarray(rows[:, :3]),
        jnp.asarray(rows[:, 3]),
        *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(rows[:, 7]),
    )
    time_index = np.asarray(obs.time_index)
    validation, test = time_index % 4 == 1, time_index % 4 == 2
    train = ~(validation | test)
    times, knots = np.linspace(0, 21600, 24), np.linspace(0, 21600, 6)
    smoothness_grid = [0.0001, 0.001, 0.01, 0.1, 1.0]
    output = []
    for seed in args.seeds:
        rng = np.random.default_rng(seed)
        bias, phase = rng.normal(0, 0.3, (8, 2)), rng.uniform(0, 2 * np.pi, (8, 2))
        truth = bias[None] + 0.25 * np.sin(
            2 * np.pi * times[:, None, None] / times[-1] + phase
        )
        data = np.asarray(predict(actual_sky, obs, jnp.asarray(truth))) + args.noise * (
            rng.normal(size=len(rows)) + 1j * rng.normal(size=len(rows))
        )

        def fit(mask, smoothness, threshold, data=data):
            return solve_pointing(
                sky,
                Observation(*(a[mask] for a in obs)),
                data[mask],
                times,
                knots,
                8,
                noise_jy=args.noise,
                smoothness=smoothness,
                flux_prior_jy=flux_prior,
                spectral_index_prior=alpha_prior,
                minimum_mode_information=threshold,
            )

        def prediction(solution):
            fitted_sky = sky._replace(
                flux_jy=jnp.asarray(solution["flux_jy"]),
                spectral_index=jnp.asarray(solution["spectral_index"]),
            )
            return np.asarray(
                predict(fitted_sky, obs, jnp.asarray(solution["offsets_arcmin"]))
            )

        for method, threshold in [("full_joint", None), ("selected_joint", 1.0)]:
            candidates = []
            for smoothness in smoothness_grid:
                solution = fit(train, smoothness, threshold)
                score = float(
                    np.mean(np.abs((prediction(solution) - data)[validation]) ** 2)
                )
                candidates.append(
                    {
                        "smoothness": smoothness,
                        "validation_mse": score,
                        "success": solution["success"],
                        "retained": solution["retained_pointing_modes"],
                    }
                )
            valid = [c for c in candidates if c["success"]]
            if not valid:
                raise RuntimeError(f"No converged candidates: seed {seed}, {method}")
            chosen = min(valid, key=lambda c: c["validation_mse"])
            # Refit on train + validation only after selecting hyperparameters.
            solution = fit(~test, chosen["smoothness"], threshold)
            error = prediction(solution) - data
            output.append(
                {
                    "seed": seed,
                    "method": method,
                    "candidates": candidates,
                    "smoothness": chosen["smoothness"],
                    "success": solution["success"],
                    "retained": solution["retained_pointing_modes"],
                    "pointing_rmse_arcsec": float(
                        60 * np.sqrt(np.mean((solution["offsets_arcmin"] - truth) ** 2))
                    ),
                    "test_rms_mjy": float(
                        1000 * np.sqrt(np.mean(np.abs(error[test]) ** 2) / 2)
                    ),
                    "flux_rmse_mjy": float(
                        1000
                        * np.sqrt(
                            np.mean((solution["flux_jy"][1:] - sources[1:, 2]) ** 2)
                        )
                    ),
                }
            )
        print(
            f"Seed {seed}: "
            + ", ".join(
                f"{r['method']} {r['pointing_rmse_arcsec']:.2f} arcsec"
                for r in output[-2:]
            ),
            flush=True,
        )
    summary = {
        method: {
            key: float(np.mean([r[key] for r in output if r["method"] == method]))
            for key in [
                "pointing_rmse_arcsec",
                "test_rms_mjy",
                "flux_rmse_mjy",
                "retained",
            ]
        }
        for method in ["full_joint", "selected_joint"]
    }
    result = {
        "seeds": args.seeds,
        "noise_jy": args.noise,
        "smoothness_grid": smoothness_grid,
        "mode_threshold": 1.0,
        "training_rows": int(train.sum()),
        "validation_rows": int(validation.sum()),
        "test_rows": int(test.sum()),
        "runs": output,
        "summary": summary,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if not all(r["success"] for r in output):
        raise SystemExit("Nonconverged final fits are retained in results")


if __name__ == "__main__":
    main()
