"""Recover smoothly varying per-antenna pointing from component visibilities."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rangtoy import toy_output
from rangtoy.pointing import Observation, component_list, predict, solve_pointing


def trajectory_svg(times, truth, fitted):
    """Dependency-free vector plot of sampled truth and fitted trajectories."""
    width, height = 920, 1020
    extent = (
        max(float(np.max(np.abs(truth))), float(np.max(np.abs(fitted))), 0.1) * 1.15
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Per-antenna pointing trajectories: truth and spline fit">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        '<g font-family="sans-serif" fill="#172b42">',
        '<text x="36" y="38" font-size="24" font-weight="bold">Rang · Smooth pointing solutions</text>',
        '<text x="36" y="64" font-size="14">Blue: axis 1 · Gold: axis 2 · Dashed: truth · Solid: fit</text>',
    ]
    for antenna in range(truth.shape[1]):
        left = 65 + (antenna % 2) * 450
        top = 110 + (antenna // 2) * 215
        w, h = 355, 145
        parts.append(
            f'<text x="{left}" y="{top - 15}" font-size="16">Antenna {antenna}</text>'
        )
        for value in [-extent, 0, extent]:
            y = top + h * (extent - value) / (2 * extent)
            parts.append(f'<path d="M {left} {y} h {w}" stroke="#dbe2ea"/>')
            parts.append(
                f'<text x="{left - 8}" y="{y + 4}" text-anchor="end" font-size="11">{value:.2f}</text>'
            )
        for hour in [0, 3, 6]:
            x = left + w * hour / 6
            parts.append(
                f'<text x="{x}" y="{top + h + 19}" text-anchor="middle" font-size="11">{hour} h</text>'
            )
        for axis, color in enumerate(["#247a92", "#ad7817"]):
            for values, dashed in [(truth, True), (fitted, False)]:
                points = " ".join(
                    f"{left + w * (t - times[0]) / (times[-1] - times[0]):.2f},{top + h * (extent - v) / (2 * extent):.2f}"
                    for t, v in zip(times, values[:, antenna, axis], strict=True)
                )
                dash = ' stroke-dasharray="5 4"' if dashed else ""
                parts.append(
                    f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"{dash}/>'
                )
    parts.extend(
        [
            '<text x="36" y="992" font-size="13">Offsets in arcminutes · Known sky and Gaussian beam · Single simulated realization</text>',
            "</g></svg>",
        ]
    )
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--noise", type=float, default=0.001)
    parser.add_argument("--smoothness", type=float, default=0.01)
    parser.add_argument("--knots", type=int, default=6)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/pointing")
    args = parser.parse_args()
    if not np.isfinite(args.noise) or args.noise <= 0 or args.knots < 2:
        parser.error("noise must be positive and finite; at least two knots required")
    jax.config.update("jax_enable_x64", True)
    fixture_bytes = toy_output("--pointing-reference").encode()
    fixture = json.loads(fixture_bytes)
    rows, sources = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    components = component_list(
        sources[:, 0], sources[:, 1], sources[:, 2], sources[:, 3]
    )
    obs = Observation(
        jnp.asarray(rows[:, :3]),
        jnp.asarray(rows[:, 3]),
        *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(rows[:, 7]),
    )
    times = np.linspace(0, 6 * 3600, fixture["time_count"])
    knots = np.linspace(times[0], times[-1], args.knots)
    rng = np.random.default_rng(args.seed)
    nants = fixture["antenna_count"]
    # Smooth truth is sinusoidal, not generated from the fitted spline basis.
    bias = rng.normal(0, 0.3, (nants, 2))
    phase = rng.uniform(0, 2 * np.pi, (nants, 2))
    truth = bias[None] + 0.25 * np.sin(
        2 * np.pi * times[:, None, None] / times[-1] + phase
    )
    noiseless = np.asarray(predict(components, obs, jnp.asarray(truth)))
    data = noiseless + args.noise * (
        rng.normal(size=len(rows)) + 1j * rng.normal(size=len(rows))
    )
    # Reserve interior times to assess interpolation, not extrapolation.
    heldout = np.asarray(obs.time_index) % 4 == 2
    train_obs = Observation(*(a[~heldout] for a in obs))
    started = time.perf_counter()
    fit = solve_pointing(
        components,
        train_obs,
        data[~heldout],
        times,
        knots,
        nants,
        noise_jy=args.noise,
        smoothness=args.smoothness,
    )
    elapsed = time.perf_counter() - started
    prediction = np.asarray(
        predict(components, obs, jnp.asarray(fit["offsets_arcmin"]))
    )
    fixed = np.asarray(predict(components, obs, jnp.zeros_like(truth)))

    def rms(residual):
        return float(np.sqrt(np.mean(np.abs(residual) ** 2) / 2))

    result = {
        "seed": args.seed,
        "noise_jy_per_component": args.noise,
        "smoothness": args.smoothness,
        "jax_version": jax.__version__,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "fit_seconds_including_compilation": elapsed,
        "pointing_rmse_arcmin": float(
            np.sqrt(np.mean((fit["offsets_arcmin"] - truth) ** 2))
        ),
        "fixed_heldout_rms_jy": rms((data - fixed)[heldout]),
        "fit_heldout_rms_jy": rms((data - prediction)[heldout]),
        "training_rows": int((~heldout).sum()),
        "heldout_rows": int(heldout.sum()),
        "truth_arcmin": truth.tolist(),
        **{
            k: (
                {"real": v.real.tolist(), "imag": v.imag.tolist()}
                if np.iscomplexobj(v)
                else v.tolist()
            )
            if isinstance(v, np.ndarray)
            else v
            for k, v in fit.items()
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.output / "trajectories.svg").write_text(
        trajectory_svg(times, truth, fit["offsets_arcmin"])
    )
    print(f"Converged: {fit['success']} ({fit['message']})")
    print(f"Pointing RMSE: {60 * result['pointing_rmse_arcmin']:.3f} arcsec")
    print(
        f"Held-out RMS: {1000 * result['fixed_heldout_rms_jy']:.3f} -> {1000 * result['fit_heldout_rms_jy']:.3f} mJy/component"
    )
    print(f"Results: {args.output / 'results.json'}")
    if not fit["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
