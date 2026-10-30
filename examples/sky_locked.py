"""Spectrum-prior-free recovery of an array-common sky-frame pointing mode."""

import json
import sys
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rang import toy_output
from rang.observability import channel_design, solve_sky_locked
from rang.pointing import Observation, component_list


def main():
    jax.config.update("jax_enable_x64", True)
    fixture = json.loads(toy_output("--pointing-reference").encode())
    rows, sources = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    sky = component_list(sources[:, 0], sources[:, 1], sources[:, 2], sources[:, 3])
    obs = Observation(
        jnp.asarray(rows[:, :3]),
        jnp.asarray(rows[:, 3]),
        *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(rows[:, 7]),
    )
    shift = np.array([0.3, -0.2])
    frequencies = np.unique(rows[:, 3])
    # Non-power-law per-channel amplitudes; fixed across the twenty noise seeds.
    flux = (
        sources[:, 2][None, :]
        * (frequencies[:, None] / 1.28e9) ** sources[:, 3][None, :]
        * (1 + np.random.default_rng(61).normal(0, 0.05, (4, 4)))
    ).ravel()
    results = []
    conditions = [
        (1, 1, False),
        (1.1, 1.1, False),
        (1.1, 1.08, False),
        (1.1, 1.0, True),
    ]
    for actual_ratio, model_ratio, fit_shape in conditions:
        matrix = np.asarray(
            channel_design(sky, obs, 8, jnp.asarray(shift), actual_ratio)
        )
        for seed in range(1, 21):
            y = matrix @ flux + 0.001 * np.random.default_rng(seed).normal(
                size=matrix.shape[0]
            )
            data = y[::2] + 1j * y[1::2]
            fit = solve_sky_locked(
                sky,
                obs,
                data,
                8,
                noise_jy=0.001,
                beam_axis_ratio=model_ratio,
                fit_beam_axis_ratio=fit_shape,
            )
            fit.update(
                seed=seed,
                actual_axis_ratio=actual_ratio,
                model_axis_ratio=model_ratio,
                fit_beam_axis_ratio=fit_shape,
            )
            results.append(fit)
        print(f"Beam {actual_ratio} / model {model_ratio} complete", flush=True)
    summary = []
    for actual, model, fit_shape in conditions:
        selected = [
            r
            for r in results
            if r["actual_axis_ratio"] == actual
            and r["model_axis_ratio"] == model
            and r["fit_beam_axis_ratio"] == fit_shape
        ]
        usable = [r for r in selected if r["identifiable"] and r["success"]]
        row = {
            "actual_axis_ratio": actual,
            "model_axis_ratio": model,
            "fit_beam_axis_ratio": fit_shape,
            "refused": sum(not r["identifiable"] for r in selected),
            "converged": len(usable),
        }
        if usable:
            error = 60 * (np.array([r["shift_arcmin"] for r in usable]) - shift)
            row.update(
                rmse_arcsec=float(np.sqrt(np.mean(error**2))),
                bias_arcsec=error.mean(axis=0).tolist(),
                mean_local_sigma_arcsec=np.mean(
                    [r["local_sigma_arcsec"] for r in usable], axis=0
                ).tolist(),
            )
        summary.append(row)
    output = ROOT / "outputs/sky-locked"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(
        json.dumps(
            {
                "truth_shift_arcmin": shift.tolist(),
                "true_channel_flux_jy": flux.tolist(),
                "noise_jy_per_component": 0.001,
                "seeds": list(range(1, 21)),
                "summary": summary,
                "runs": results,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
