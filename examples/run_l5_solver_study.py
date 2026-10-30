"""Task L5 solver study (research/l5-solver-science.md).

Usage:
    python examples/run_l5_solver_study.py sweep {fixture,slice,array} outputs/<fresh-dir>
    python examples/run_l5_solver_study.py select outputs/<slice-sweep-dir>/result.json
    python examples/run_l5_solver_study.py confirm {fixture,slice,array} outputs/<fresh-dir> \
        --candidate "<RANG_SOLVE_OPTIONS>" --max-iterations N --stop-fraction F \
        [--stop-criterion T] [--pairs 3] [--image]

`sweep` runs the default D (50 iterations), the long trace runs (R, R_T and
Anderson m = 2, 3, 5), every pre-registered criterion directly, and the
held-out curve along R; `select` applies the frozen selection rule on the
slice's validation losses; `confirm` times D against the candidate as
alternating A/B pairs in one process and, with `--image`, images D and the
candidate (and on the slice D_T and R). Writes only into the fresh run
directory; every input is read-only. `RAYON_NUM_THREADS` is the caller's.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))

from rangtoy import core, core_campaign, core_campaign_array
from rangtoy import core_solver_study as study
from rangtoy.core_workflow import gain_grid, solve_flags

DELTA = 1e-4
LONG = {"fixture": 500, "slice": 500, "array": 300}
PRODUCT = (1e-3, 1e-4, 1e-5, 1e-6)
LOSS = (1e-5, 1e-6, 1e-7, 1e-8)
CAPS = (8, 12, 16, 24)
GAIN = (1e-6, 1e-5)
ANDERSON = (2, 3, 5)
CURVE = {
    "fixture": (
        1,
        2,
        3,
        4,
        5,
        6,
        8,
        10,
        12,
        15,
        20,
        25,
        30,
        40,
        50,
        75,
        100,
        150,
        200,
        300,
        500,
    ),
    "slice": (
        1,
        2,
        3,
        4,
        5,
        6,
        8,
        10,
        12,
        15,
        20,
        25,
        30,
        40,
        50,
        75,
        100,
        150,
        200,
        300,
        500,
    ),
    "array": (2, 4, 8, 12, 16, 24, 32, 50, 75, 100, 150, 200, 300),
}
ARCHIVED_GAINS = {
    "slice": (
        "research/results/core-k-luno-campaign.json",
        "4ed2aa89a68aad5bce6f48a62da4071f948502e043c302812ceda094440d4aa8",
    ),
    "array": (
        "research/results/luno-array-campaign.json",
        "13ba1c667af257e464e0a165c569f8402c8f8fa1e570b541bd8b4f92aa558c35",
    ),
}
K_SPLIT = {"train": 94047, "validation": 11742, "test": 11767}
L1_SPLIT = {"train": 27401558, "validation": 3419206, "test": 3418059}


def meminfo_gib():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 2**20
    return None


def environment():
    return {
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--short"], cwd=ROOT, text=True
        ),
        "backend": core.backend_name(),
        "library_sha256": study.core_sha256(
            np.frombuffer(core.library_path().read_bytes(), np.uint8)
        ),
        "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "loadavg": os.getloadavg(),
        "mem_available_gib": meminfo_gib(),
    }


def load(dataset):
    """The problem, plus (state, extra) for imaging on the LUNO data."""
    started = time.perf_counter()
    if dataset == "fixture":
        from validate_core_phase2 import FIXTURE, FIXTURE_FLAGS, TRIAL, bins

        with np.load(FIXTURE / "state.npz") as z:
            s = {k: z[k] for k in z.files}
        with np.load(FIXTURE_FLAGS) as z:
            flag, flag_row = z["FLAG"], z["FLAG_ROW"]
        with np.load(TRIAL / "diagnostics.npz") as z:
            d = {k: z[k] for k in ("gains", "gain_times", "gain_frequencies")}
        tb, fb = bins(s["times"], s["data"].shape[1])
        problem = study.problem_from_state(
            s,
            flag,
            flag_row,
            tb,
            fb,
            d["gain_times"],
            d["gain_frequencies"],
            d["gains"].shape[2],
        )
        return problem, None, None, {"seconds": time.perf_counter() - started}
    stations = range(4) if dataset == "slice" else None
    arrays, rows, _ = core_campaign_array.decode_inputs(stations)
    extra = core_campaign_array.decode_extra(rows)
    nant = len(extra["antenna_names"]) if stations is None else max(stations) + 1
    state = core_campaign_array.build_state(arrays, extra, nant)
    del arrays
    counts = {
        k: int(np.count_nonzero(state[k])) for k in ("train", "validation", "test")
    }
    expected = K_SPLIT if dataset == "slice" else L1_SPLIT
    if counts != expected:
        raise RuntimeError(f"split counts {counts} differ from the archive {expected}")
    flags, frows = solve_flags(state, np.zeros_like(state["train"]))
    time_map, freq_map, gt, gf = gain_grid(state, *study.GRID)
    problem = study.problem_from_state(
        state, flags, frows, time_map, freq_map, gt, gf, nant
    )
    return (
        problem,
        state,
        extra,
        {
            "seconds": time.perf_counter() - started,
            "split": counts,
            "nant": nant,
            "rows": len(state["antenna1"]),
        },
    )


def write(path, payload):
    path.write_text(json.dumps(payload, indent=1, default=float) + "\n")


def sweep(dataset, out):
    out.mkdir(parents=True)
    (out / "traces").mkdir()
    started = time.perf_counter()
    result = {
        "task": "L5",
        "mode": "sweep",
        "dataset": dataset,
        "environment": environment(),
    }
    problem, _, _, info = load(dataset)
    result["load"] = info
    long_cap = LONG[dataset]

    D = study.solve(problem, "", max_iterations=50)
    scale = study.gain_scale(D["gains"], D["valid"])
    result["default_gains_sha256"] = study.core_sha256(D["gains"])
    if dataset in ARCHIVED_GAINS:
        result["default_reproduces_archive"] = (
            result["default_gains_sha256"] == ARCHIVED_GAINS[dataset][1]
        )
    print(
        "D",
        D["iterations"],
        D["converged_fraction"],
        f"{D['wall_seconds']:.2f} s",
        flush=True,
    )

    # Long trace runs (fraction 2: never stops before the cap).
    long_runs, traces = {}, {}
    for label, options in {
        "R": "",
        "R_T": "qp_weights=transposed",
        **{f"AA{m}": f"anderson={m}" for m in ANDERSON},
    }.items():
        path = out / "traces" / f"{label}.json"
        long_runs[label] = study.solve(
            problem, options, max_iterations=long_cap, stop_fraction=2.0, trace=path
        )
        traces[label] = study.load_trace(path)
        print(label, f"{long_runs[label]['wall_seconds']:.1f} s", flush=True)
    R = long_runs["R"]

    def curves(trace):
        return {
            "gain_1e-7": study.criterion_curve(trace, "gain").tolist(),
            **{
                f"product_{t:g}": study.criterion_curve(trace, "product", t).tolist()
                for t in PRODUCT
            },
            **{
                f"loss_{t:g}": study.criterion_curve(trace, "loss", t).tolist()
                for t in LOSS
            },
            "max_product_change": np.nanmax(trace["product_change"], axis=1).tolist(),
            "median_product_change": np.nanmedian(
                trace["product_change"], axis=1
            ).tolist(),
            "chi2_total": np.nansum(trace["chi2"], axis=1).tolist(),
        }

    def stops(trace):
        return {
            "gain_1e-7": study.stop_iteration(trace, "gain"),
            **{
                f"product_{t:g}": study.stop_iteration(trace, "product", t)
                for t in PRODUCT
            },
            **{f"loss_{t:g}": study.stop_iteration(trace, "loss", t) for t in LOSS},
        }

    result["long_runs"] = {
        label: {
            "options": run["options"],
            "wall_seconds": run["wall_seconds"],
            "cpu_seconds": run["cpu_seconds"],
            "settled": study.settled(traces[label]),
            "anderson_mixes": traces[label]["anderson_mixes"],
            "anderson_resets": traces[label]["anderson_resets"],
            "trace_stops": stops(traces[label]),
            "curves": curves(traces[label]),
            "product_distance_to_R": study.product_distance(
                run["gains"], run["valid"], R["gains"], R["valid"]
            ),
            "valid_gain_fraction": float(np.mean(run["valid"])),
            "flagged_gains": int(np.count_nonzero(run["flags"] != 0)),
            "losses": study.losses(
                problem,
                run["gains"],
                run["valid"],
                {k: problem[k] for k in ("train", "validation", "test")},
            ),
        }
        for label, run in long_runs.items()
    }

    # Arms run directly.
    arms = {"D": D}
    expected = {}
    arms["D_T"] = study.solve(problem, "qp_weights=transposed", max_iterations=50)
    arms["gain-1e-7-uncapped"] = study.solve(problem, "", max_iterations=long_cap)
    expected["gain-1e-7-uncapped"] = study.stop_iteration(traces["R"], "gain")
    for t in GAIN:
        arms[f"gain-{t:g}"] = study.solve(
            problem, "", max_iterations=long_cap, stop_criterion=t
        )
    for t in PRODUCT:
        label = f"product-{t:g}"
        arms[label] = study.solve(
            problem, f"stop=product:{t:g}", max_iterations=long_cap
        )
        expected[label] = study.stop_iteration(traces["R"], "product", t)
    for t in LOSS:
        label = f"loss-{t:g}"
        arms[label] = study.solve(problem, f"stop=loss:{t:g}", max_iterations=long_cap)
        expected[label] = study.stop_iteration(traces["R"], "loss", t)
    for k in CAPS:
        arms[f"cap-{k}"] = study.solve(problem, "", max_iterations=k, stop_fraction=2.0)
        expected[f"cap-{k}"] = k
    for m in ANDERSON:
        label = f"anderson-{m}"
        arms[label] = study.solve(problem, f"anderson={m}", max_iterations=long_cap)
        expected[label] = study.stop_iteration(traces[f"AA{m}"], "gain")
    result["arms"] = {}
    for label, run in arms.items():
        record = study.summary(problem, run, R, D, scale)
        if label in expected:
            want = expected[label] if expected[label] is not None else long_cap
            record["trace_predicted_iterations"] = want
            record["matches_trace"] = run["iterations"] == want
        record["hit_safety_cap"] = (
            run["max_iterations"] == long_cap and run["iterations"] == long_cap
        )
        result["arms"][label] = record
        print(label, run["iterations"], record["vs_default"]["relative"], flush=True)

    # Held-out curve along R (prefixes of the long run).
    curve = []
    for k in CURVE[dataset]:
        if k > long_cap:
            continue
        run = study.solve(problem, "", max_iterations=k, stop_fraction=2.0)
        split = study.losses(
            problem,
            run["gains"],
            run["valid"],
            {s: problem[s] for s in ("train", "validation", "test")},
        )
        curve.append(
            {
                "k": k,
                "losses": {s: v["loss"] for s, v in split.items()},
                "vs_reference": study.matched_losses(problem, run, R)["relative"],
                "product_distance_to_R": study.product_distance(
                    run["gains"], run["valid"], R["gains"], R["valid"]
                ),
                "product_distance_to_D": study.product_distance(
                    run["gains"], run["valid"], D["gains"], D["valid"]
                ),
                "polar_tv": study.polar_tv(problem, run["gains"], run["valid"], scale),
                "wall_seconds": run["wall_seconds"],
            }
        )
        print("curve", k, curve[-1]["vs_reference"], flush=True)
    result["curve_along_R"] = curve
    result["q1"] = {
        "R_T_vs_R": study.product_distance(
            long_runs["R_T"]["gains"], long_runs["R_T"]["valid"], R["gains"], R["valid"]
        ),
        "D_T_vs_D": study.product_distance(
            arms["D_T"]["gains"], arms["D_T"]["valid"], D["gains"], D["valid"]
        ),
        "gain_criterion_stop_R": study.stop_iteration(traces["R"], "gain"),
        "gain_criterion_stop_R_T": study.stop_iteration(traces["R_T"], "gain"),
    }
    result["wall_seconds"] = time.perf_counter() - started
    result["environment_end"] = environment()
    write(out / "result.json", result)
    print("sweep done", f"{result['wall_seconds']:.1f} s")


def select(path):
    """The frozen selection rule on the slice's validation losses."""
    result = json.loads(Path(path).read_text())
    if result["dataset"] != "slice":
        sys.exit("selection uses the slice sweep only")
    order = ["product", "loss", "cap", "gain"]
    adequate = []
    for label, arm in result["arms"].items():
        family = label.split("-")[0]
        if label in ("D", "D_T") or family not in order:
            continue
        rel = arm["vs_default"]["relative"]["validation"]
        if arm["hit_safety_cap"] or rel is None or abs(rel) > DELTA:
            continue
        adequate.append((arm["iterations"], order.index(family), label, rel))
    adequate.sort()
    print(
        json.dumps(
            {"adequate": adequate, "selected": adequate[0] if adequate else None},
            indent=1,
        )
    )


def confirm(
    dataset, out, candidate, max_iterations, stop_fraction, stop_criterion, pairs, image
):
    out.mkdir(parents=True)
    started = time.perf_counter()
    result = {
        "task": "L5",
        "mode": "confirm",
        "dataset": dataset,
        "candidate": {
            "options": candidate,
            "max_iterations": max_iterations,
            "stop_fraction": stop_fraction,
            "stop_criterion": stop_criterion,
        },
        "environment": environment(),
    }
    problem, state, extra, info = load(dataset)
    result["load"] = info

    def run_default():
        return study.solve(problem, "", max_iterations=50)

    def run_candidate():
        return study.solve(
            problem,
            candidate,
            max_iterations=max_iterations,
            stop_fraction=stop_fraction,
            stop_criterion=stop_criterion,
        )

    timings = []
    for i in range(pairs):
        load0 = os.getloadavg()[0]
        D = run_default()
        C = run_candidate()
        timings.append(
            {
                "pair": i,
                "loadavg_before": load0,
                "loadavg_after": os.getloadavg()[0],
                "D": {
                    "wall": D["wall_seconds"],
                    "cpu": D["cpu_seconds"],
                    "iterations": D["iterations"],
                },
                "C": {
                    "wall": C["wall_seconds"],
                    "cpu": C["cpu_seconds"],
                    "iterations": C["iterations"],
                },
            }
        )
        print("pair", timings[-1], flush=True)
    result["ab_pairs"] = timings
    result["median_wall"] = {
        a: float(np.median([t[a]["wall"] for t in timings])) for a in ("D", "C")
    }
    result["median_cpu"] = {
        a: float(np.median([t[a]["cpu"] for t in timings])) for a in ("D", "C")
    }
    scale = study.gain_scale(D["gains"], D["valid"])
    result["candidate_vs_default"] = study.summary(problem, C, D, D, scale)
    result["default"] = study.summary(problem, D, D, D, scale)
    if image and state is not None:
        solves = {"D": D, "C": C}
        if dataset == "slice":
            solves["D_T"] = study.solve(
                problem, "qp_weights=transposed", max_iterations=50
            )
            solves["R"] = study.solve(
                problem, "", max_iterations=LONG[dataset], stop_fraction=2.0
            )
            image_settings, groups, boxes = core_campaign.IMAGE, 1, None
        else:
            archive = json.loads((ROOT / ARCHIVED_GAINS["array"][0]).read_text())
            image_settings = core_campaign_array.ARRAY_IMAGE
            groups = core_campaign_array.ARRAY_CHANNEL_GROUPS
            boxes = archive["boxes"]
        images = {}
        zero = np.zeros_like(problem["train"])
        for label, run in solves.items():
            mark = time.perf_counter()
            metrics, _ = core_campaign_array.image_arm(
                state,
                extra,
                {
                    "added": zero,
                    "diagnostics": {"gains": run["gains"], "gain_valid": run["valid"]},
                },
                out / "images",
                label,
                image_settings,
                groups,
                boxes=boxes,
            )
            metrics["image_wall_seconds"] = time.perf_counter() - mark
            images[label] = metrics
            print("image", label, metrics["residual_rms"], flush=True)
        result["images"] = images
        result["residual_rms_ratio_C_over_D"] = (
            images["C"]["residual_rms"] / images["D"]["residual_rms"]
        )
    result["wall_seconds"] = time.perf_counter() - started
    result["environment_end"] = environment()
    write(out / "result.json", result)
    print("confirm done", f"{result['wall_seconds']:.1f} s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("sweep", "select", "confirm"))
    parser.add_argument("target")
    parser.add_argument("out", nargs="?")
    parser.add_argument("--candidate", default="")
    parser.add_argument("--max-iterations", type=int, default=50)
    parser.add_argument("--stop-fraction", type=float, default=0.99)
    parser.add_argument("--stop-criterion", type=float, default=1e-7)
    parser.add_argument("--pairs", type=int, default=3)
    parser.add_argument("--image", action="store_true")
    args = parser.parse_args()
    if args.mode == "select":
        select(args.target)
        return
    out = Path(args.out)
    if not str(out).startswith("outputs/l5-solver-") or out.exists():
        sys.exit("the run directory must be a fresh outputs/l5-solver-* path")
    if args.target == "array" and (meminfo_gib() or 0) < 20:
        sys.exit(
            f"MemAvailable {meminfo_gib():.1f} GiB < 20 GiB: the array run does not start"
        )
    if args.mode == "sweep":
        sweep(args.target, out)
    else:
        confirm(
            args.target,
            out,
            args.candidate,
            args.max_iterations,
            args.stop_fraction,
            args.stop_criterion,
            args.pairs,
            args.image,
        )


if __name__ == "__main__":
    main()
