"""Run and plot a small MeerKAT pointing-calibration experiment."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from rangtoy import run_experiment

LABELS = {
    "fixed_beam": "Fixed beam",
    "pointing_only": "Pointing only",
    "joint_sky": "Joint sky",
    "joint_beam": "Joint sky + beam",
    "protected_modes": "Protected modes",
    "known_pointing": "Known pointing",
}


def summary(experiments: list[dict]) -> dict:
    result = {}
    for name in LABELS:
        rows = [
            next(row for row in ex["results"] if row["method"] == name)
            for ex in experiments
        ]
        result[name] = {}
        for key in [
            "flux_jy",
            "heldout_rms_jy",
            "pointing_rmse_arcmin",
            "template_transfer",
            "off_template_transfer",
            "template_distortion",
            "off_template_distortion",
            "fitted_beam_width_error",
        ]:
            values = [row[key] for row in rows]
            result[name][key] = {
                "mean": statistics.mean(values),
                "std": statistics.stdev(values) if len(values) > 1 else 0.0,
            }
    return result


def plot(experiments: list[dict], stats: dict, output: Path) -> None:
    # Keep caches in generated output, including in filesystem-restricted sessions.
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(output / ".cache"))
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Plotting needs matplotlib: install '.[plot]' or use --no-plot"
        ) from exc

    plt.rcParams.update(
        {"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}
    )
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), layout="constrained")
    names = list(LABELS)
    positions = list(range(len(names)))
    colors = ["#8996a5", "#cf6a42", "#247a92", "#ba9b32", "#7862a5", "#529b67"]
    for ax, key, scale, title, ylabel in [
        (
            axes[0],
            "flux_jy",
            1000,
            "Recovered extended-source flux",
            "Flux at 1.28 GHz (mJy)",
        ),
        (
            axes[1],
            "heldout_rms_jy",
            1000,
            "Prediction on the last 6 time samples",
            "RMS per visibility component (mJy)",
        ),
    ]:
        means = [stats[name][key]["mean"] * scale for name in names]
        errors = [stats[name][key]["std"] * scale for name in names]
        ax.bar(positions, means, color=colors, alpha=0.85)
        if len(experiments) > 1:
            ax.errorbar(
                positions, means, yerr=errors, fmt="none", color="#263442", capsize=3
            )
        ax.set_title(title)
        ax.set_ylabel(ylabel)
    axes[0].axhline(
        experiments[0]["true_flux_jy"] * 1000,
        color="#263442",
        linestyle="--",
        label="Injected truth",
    )
    axes[0].legend(frameon=False)
    axes[1].axhline(
        experiments[0]["noise_jy"] * 1000,
        color="#263442",
        linestyle="--",
        label="Noise sigma",
    )
    axes[1].legend(frameon=False)
    ax = axes[2]
    for key, offset, color, label in [
        ("template_transfer", -0.12, "#247a92", "Target morphology"),
        ("off_template_transfer", 0.12, "#cf6a42", "Different sky position"),
    ]:
        ax.errorbar(
            [i + offset for i in positions],
            [100 * stats[n][key]["mean"] for n in names],
            yerr=[100 * stats[n][key]["std"] for n in names],
            fmt="o",
            color=color,
            capsize=3,
            label=label,
        )
    ax.axhline(100, color="#263442", linestyle="--")
    ax.set_title("Finite injection with complete refitting")
    ax.set_ylabel("Residual signal response (%)")
    ax.legend(frameon=False)
    for ax in axes:
        ax.set_xticks(positions, list(LABELS.values()), rotation=30, ha="right")
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    fig.suptitle(
        "Rang | MeerKAT core toy: Gaussian beam, scalar RIME, known source positions",
        fontsize=14,
    )
    suffix = (
        "Error bars: standard deviation across seeds, not confidence intervals."
        if len(experiments) > 1
        else "One realization; no uncertainty intervals."
    )
    fig.supxlabel(
        f"{len(experiments)} seed(s). {suffix}  Signal response is not image fidelity.",
        fontsize=9,
    )
    fig.savefig(output / "comparison.png", dpi=180)
    fig.savefig(output / "comparison.pdf")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[7])
    parser.add_argument("--noise", type=float, default=0.01)
    parser.add_argument("--pointing", type=float, default=0.6)
    parser.add_argument("--beam-error", type=float, default=0.0)
    parser.add_argument("--budget", type=float, default=0.01)
    parser.add_argument("--target-flux", type=float, default=0.02)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "toy")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()
    experiments = []
    for seed in args.seeds:
        print(f"Running seed {seed}...", flush=True)
        experiments.append(
            run_experiment(
                seed=seed,
                noise=args.noise,
                pointing=args.pointing,
                beam_error=args.beam_error,
                budget=args.budget,
                target_flux=args.target_flux,
            )
        )
    stats = summary(experiments)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    artifact = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiments": experiments,
        "summary": stats,
        "error_bars": "sample standard deviation across seeds",
    }
    (output / "results.json").write_text(json.dumps(artifact, indent=2) + "\n")
    print(f"\nTruth: {args.target_flux * 1000:.2f} mJy | {len(experiments)} seed(s)")
    print(
        f"{'Method':19} {'Flux mJy':>10} {'Pointing RMSE ′':>17} {'Test RMS mJy':>14} {'Response %':>12}"
    )
    for name, label in LABELS.items():
        row = stats[name]
        print(
            f"{label:19} {row['flux_jy']['mean'] * 1000:10.3f} {row['pointing_rmse_arcmin']['mean']:17.4f} "
            f"{row['heldout_rms_jy']['mean'] * 1000:14.3f} {row['template_transfer']['mean'] * 100:12.3f}"
        )
    if not args.no_plot:
        plot(experiments, stats, output)
    print(f"\nArtifacts: {output}")
    print(
        "Compare protected modes with joint sky; equality means no demonstrated added benefit."
    )


if __name__ == "__main__":
    main()
