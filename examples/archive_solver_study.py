"""Compact archive of the L5 solver study (research/l5-solver-science.md).

Usage: python examples/archive_solver_study.py research/results/l5-solver-science.json \
    fixture=outputs/<sweep> slice=outputs/<sweep> array=outputs/<sweep> \
    confirm=outputs/<confirm> [confirm=...] diagnose=outputs/<diagnose> [--table]

Reads the run directories' result.json files and writes one JSON with the
numbers the report quotes (no per-interval arrays). `--table` also prints
Markdown tables of the arms.
"""

import json
import sys
from hashlib import sha256
from pathlib import Path

ARM_KEYS = (
    "options",
    "max_iterations",
    "stop_criterion",
    "stop_fraction",
    "iterations",
    "converged_fraction",
    "trace_predicted_iterations",
    "matches_trace",
    "hit_safety_cap",
    "valid_gain_fraction",
    "flagged_gains",
    "losses",
    "invalid_predictions",
    "polar_tv",
    "wall_seconds",
    "cpu_seconds",
    "gains_sha256",
    "mixes_to_stop",
    "resets_to_stop",
)


def arm(record):
    out = {k: record[k] for k in ARM_KEYS if k in record}
    out["vs_default_relative"] = record["vs_default"]["relative"]
    out["vs_default_dropped"] = record["vs_default"]["dropped"]
    out["vs_reference_relative"] = record["vs_reference"]["relative"]
    for key in (
        "product_distance_to_reference",
        "product_distance_to_reference_observed",
        "product_distance_to_default",
        "product_distance_to_default_observed",
    ):
        out[key] = record[key]
    return out


def sweep(path):
    d = json.loads((Path(path) / "result.json").read_text())
    return {
        "run_dir": str(path),
        "result_sha256": sha256((Path(path) / "result.json").read_bytes()).hexdigest(),
        "environment": d["environment"],
        "load": d["load"],
        "wall_seconds": d["wall_seconds"],
        "default_gains_sha256": d["default_gains_sha256"],
        "default_reproduces_archive": d.get("default_reproduces_archive"),
        "q1": d["q1"],
        "long_runs": {
            label: {k: v for k, v in run.items() if k not in ("curves",)}
            | {
                "curves_every_iteration": {
                    name: values
                    for name, values in run["curves"].items()
                    if name
                    in (
                        "gain_1e-7",
                        "product_0.0001",
                        "loss_1e-06",
                        "max_product_change",
                        "chi2_total",
                    )
                }
            }
            for label, run in d["long_runs"].items()
        },
        "arms": {label: arm(record) for label, record in d["arms"].items()},
        "curve_along_R": d["curve_along_R"],
    }


def confirm(path):
    d = json.loads((Path(path) / "result.json").read_text())
    return {
        "run_dir": str(path),
        "result_sha256": sha256((Path(path) / "result.json").read_bytes()).hexdigest(),
        "dataset": d["dataset"],
        "candidate": d["candidate"],
        "environment": d["environment"],
        "ab_pairs": d["ab_pairs"],
        "median_wall": d["median_wall"],
        "median_cpu": d["median_cpu"],
        "candidate_vs_default": arm(d["candidate_vs_default"]),
        "images": {
            label: {
                k: m.get(k)
                for k in (
                    "peak",
                    "residual_rms",
                    "residual_rms_offsource",
                    "rms_offsource",
                    "flux_recovery",
                    "dirty_sha256",
                    "psf_sha256",
                    "image_wall_seconds",
                )
            }
            for label, m in d.get("images", {}).items()
        },
        "residual_rms_ratio_C_over_D": d.get("residual_rms_ratio_C_over_D"),
        "wall_seconds": d["wall_seconds"],
    }


def table(name, s):
    print(f"\n### {name}\n")
    print(
        "| Arm | Iter. | MSE_test vs D | MSE_val vs D | Prod. dist. to R (obs., max) | Polar TV | Wall s |"
    )
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for label, a in s["arms"].items():
        r = a["vs_default_relative"]
        pd = a["product_distance_to_reference_observed"]["max"]
        print(
            f"| {label} | {a['iterations']} | {r['test']:+.2e} | {r['validation']:+.2e} | "
            f"{pd:.1e} | {a['polar_tv']:.6f} | {a['wall_seconds']:.2f} |"
        )


def main():
    out = Path(sys.argv[1])
    payload = {
        "task": "L5",
        "protocol": "research/l5-solver-science.md",
        "sweeps": {},
        "confirms": [],
    }
    show = "--table" in sys.argv
    for item in sys.argv[2:]:
        if item == "--table":
            continue
        key, path = item.split("=", 1)
        if key == "confirm":
            payload["confirms"].append(confirm(path))
        elif key == "diagnose":
            d = json.loads((Path(path) / "result.json").read_text())
            payload["diagnose_fixed_points_post_hoc"] = {
                k: d[k]
                for k in (
                    "dataset",
                    "max_distance_to_R5000",
                    "intervals_above_1e-9",
                    "total_train_loss",
                    "worst_intervals",
                    "wall_seconds",
                )
            } | {"run_dir": path}
        else:
            payload["sweeps"][key] = sweep(path)
            if show:
                table(key, payload["sweeps"][key])
    out.write_text(json.dumps(payload, indent=1, default=float) + "\n")


if __name__ == "__main__":
    main()
