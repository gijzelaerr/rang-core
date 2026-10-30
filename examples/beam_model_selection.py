"""Separate train/validation/test control for choosing one beam-width parameter."""

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
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(1, 13)))
    parser.add_argument(
        "--rich",
        action="store_true",
        help="Include chromatic width and axis-ratio candidates",
    )
    args = parser.parse_args()
    jax.config.update("jax_enable_x64", True)
    raw = toy_output("--pointing-full-reference").encode()
    fixture = json.loads(raw)
    rows, sources = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    obs = Observation(
        jnp.asarray(rows[:, :3]),
        jnp.asarray(rows[:, 3]),
        *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(rows[:, 7]),
    )
    sky = component_list(sources[:, 0], sources[:, 1], sources[:, 2], sources[:, 3])
    wrong_sky = sky._replace(flux_jy=sky.flux_jy * jnp.array([1, 1.02, 0.98, 1.02]))
    table, metadata = load_katbeam()
    predictor = make_beam_predictor(table, metadata=metadata)
    times, knots = np.linspace(0, 21600, 24), np.linspace(0, 21600, 4)
    basis, _ = spline_design(times, knots)
    ti = np.asarray(obs.time_index)
    validation, test = ti % 6 == 1, ti % 6 == 4
    train = ~(validation | test)
    train_obs = Observation(*(x[train] for x in obs))
    freq_coordinate = (np.asarray(table.frequency_hz) - 1.3e9) / 0.4e9
    widths = {
        "matched": table.fwhm_rad,
        "uniform_width": table.fwhm_rad * 1.01,
        "axis_ratio": table.fwhm_rad * jnp.exp(jnp.array([-0.01, 0.01])),
        "chromatic_width": table.fwhm_rad * (1 + 0.01 * freq_coordinate[:, None]),
    }
    sigma = 0.001
    results = []
    for seed in args.seeds:
        rng = np.random.default_rng(seed)
        coefficients = rng.normal(0, 0.3, (4, 8, 2))
        coefficients -= coefficients.mean(axis=1, keepdims=True)
        truth = np.einsum("tk,kad->tad", basis, coefficients)
        logamp = basis @ rng.normal(0, 0.02, (4, 8))
        phase = basis @ rng.normal(0, 0.03, (4, 8))
        phase -= phase[:, :1]
        gains = np.exp(logamp + 1j * phase)
        baseline_gain = gains[ti, obs.antenna1] * gains[ti, obs.antenna2].conj()
        noise = sigma * (rng.normal(size=len(rows)) + 1j * rng.normal(size=len(rows)))
        for name, width in widths.items():
            actual = make_beam_predictor(
                beam_table(table.frequency_hz, table.squint_rad, width)
            )
            clean = np.asarray(actual(sky, obs, jnp.asarray(truth))) * baseline_gain
            data = clean + noise
            candidates = []
            models = [("fixed", [0, 0, 0]), ("joint_width", [0.03, 0, 0])]
            if args.rich:
                models += [
                    ("width_slope", [0.03, 0.03, 0]),
                    ("width_slope_ratio", [0.03, 0.03, 0.03]),
                ]
            for model_name, prior in models:
                started = perf_counter()
                fit = solve_pointing(
                    wrong_sky,
                    train_obs,
                    data[train],
                    times,
                    knots,
                    8,
                    noise_jy=sigma,
                    smoothness=0.01,
                    zero_mean_pointing=True,
                    gain_prior_sigma=(0.1, 0.1),
                    flux_prior_jy=0.05 * np.asarray(wrong_sky.flux_jy),
                    predictor=predictor,
                    beam_shape_prior=prior,
                )
                elapsed = perf_counter() - started
                recovered_sky = wrong_sky._replace(flux_jy=jnp.asarray(fit["flux_jy"]))
                model = np.asarray(
                    predictor.with_shape(
                        recovered_sky,
                        obs,
                        jnp.asarray(fit["offsets_arcmin"]),
                        fit["beam_shape_parameters"],
                    )
                )
                recovered_gain = fit["gains"]
                model = (
                    model
                    * recovered_gain[ti, obs.antenna1]
                    * recovered_gain[ti, obs.antenna2].conj()
                )
                ratios = fit["flux_jy"] / fit["flux_jy"][0]
                true_ratios = np.asarray(sky.flux_jy / sky.flux_jy[0])
                candidate = {
                    "model": model_name,
                    "beam_shape_parameters": fit["beam_shape_parameters"].tolist(),
                    "success": fit["success"],
                    "width": fit["beam_width_multiplier"],
                    "seconds_including_compilation": elapsed,
                    "pointing_rmse_arcsec": float(
                        60 * np.sqrt(np.mean((fit["offsets_arcmin"] - truth) ** 2))
                    ),
                    "maximum_flux_ratio_fractional_error": float(
                        np.max(np.abs(ratios / true_ratios - 1))
                    ),
                }
                for label, mask in (
                    ("train", train),
                    ("validation", validation),
                    ("test", test),
                ):
                    candidate[label + "_residual"] = float(
                        np.mean(np.abs(model[mask] - data[mask]) ** 2) / (2 * sigma**2)
                    )
                    candidate[label + "_clean_rms_mjy"] = float(
                        1000 * np.sqrt(np.mean(np.abs(model[mask] - clean[mask]) ** 2))
                    )
                candidates.append(candidate)
            eligible = [c for c in candidates if c["success"]]
            selected = (
                min(eligible, key=lambda c: c["validation_residual"])["model"]
                if eligible
                else None
            )
            result = {
                "seed": seed,
                "truth_beam": name,
                "selected": selected,
                "candidates": candidates,
            }
            results.append(result)
            print(json.dumps(result), flush=True)
    payload = {
        "fixture_sha256": sha256(raw).hexdigest(),
        "beam": metadata,
        "split_time_indices": {
            label: np.unique(ti[mask]).tolist()
            for label, mask in (
                ("train", train),
                ("validation", validation),
                ("test", test),
            )
        },
        "selection": "lowest validation residual among converged candidates; no refit and no use of test scores for selection",
        "limitations": "Ordinary validation-selection baseline, not novel. Synthetic scalar beam; shared pointing zero. Width, ratio and chromatic perturbations are assumptions, not measured uncertainties. Running all candidates costs their combined fits. Timings include compilation, not controlled performance claims.",
        "results": results,
    }
    output = ROOT / "outputs/beam-model-selection"
    if args.rich:
        output = output.with_name(output.name + "-rich")
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
