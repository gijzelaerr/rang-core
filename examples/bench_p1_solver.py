"""Task P1 benchmark and equality harness (research/p1-solver.md).

Usage:
    python examples/bench_p1_solver.py run <out.json> [--repeats N]
    python examples/bench_p1_solver.py sweep outputs/<fresh-dir> \
        --python base=<venv>/bin/python --python new=<venv>/bin/python \
        [--threads 1,2,4,8,16] [--rounds 3] [--repeats 5]

`run` loads the phase 2 LUNO arrays and the fixture clean case, solves each
with the core's ported QuartiCal solver (rang's frozen settings), runs the
fused pass at the solved gains with every product requested, hashes every
output and times both kernels (wall from `time.perf_counter`, CPU from
`time.process_time`, which counts every thread of the process). It uses
the extension of the interpreter that runs it. `sweep` compares builds by
interpreter: each `--python NAME=PATH` is a venv with its own `rang`
extension (task P9, research/p9-cli.md; P7 removed the `RANG_CORE_LIB`
library switch that `--lib` used).

`sweep` runs one `run` subprocess per (round, thread count, interpreter)
with `RAYON_NUM_THREADS` and `OPENBLAS_NUM_THREADS=1` set, alternating the
order between rounds so that both builds see the same load. It
writes every child's JSON, `summary.json` with minimum and median per cell
and the equality verdict: every child's hashes must equal those of the
first library at the first thread count (the reference).
"""

import argparse
import json
import os
import platform
import resource
import statistics
import subprocess
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LUNO_ARRAYS = ROOT / "outputs/core-phase2-inputs-20261029-01/arrays.npz"
FIXTURE = ROOT / "outputs/tv-response-wsl-20261029-01/clean"
FIXTURE_FLAGS = FIXTURE / "backups/clean-t2-f32-solve.npz"
GRID = (2, 32)
SPLIT_SEED = 7


def loadavg():
    return float(Path("/proc/loadavg").read_text().split()[0])


def digest(array):
    return sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def bins(times, nchan, grid=GRID):
    """Time and frequency bin maps as validate_core_phase2.bins builds them."""
    _, inverse = np.unique(times, return_inverse=True)
    return (inverse // grid[0]).astype(np.uint32), (np.arange(nchan) // grid[1]).astype(
        np.uint32
    )


def luno():
    with np.load(LUNO_ARRAYS) as z:
        a = {k: z[k] for k in z.files}
    tb, fb = bins(a["TIME"], a["DATA"].shape[1])
    rng = np.random.default_rng(SPLIT_SEED)
    split = rng.integers(0, 4, a["DATA"].shape[:2]).astype(np.uint8)
    return {
        "data": a["DATA"],
        "weights": a["WEIGHT_SPECTRUM"],
        "flag": a["FLAG"],
        "flag_row": a["FLAG_ROW"],
        "antenna1": a["ANTENNA1"],
        "antenna2": a["ANTENNA2"],
        "time_bin": tb,
        "freq_bin": fb,
        "model": a["MODEL_DATA"],
        "split": split,
    }


def fixture():
    from rang import core

    with np.load(FIXTURE / "state.npz") as z:
        s = {k: z[k] for k in z.files}
    with np.load(FIXTURE_FLAGS) as z:
        flag, flag_row = z["FLAG"], z["FLAG_ROW"]
    tb, fb = bins(s["times"], s["data"].shape[1])
    return {
        "data": s["data"],
        "weights": s["weights"],
        "flag": flag,
        "flag_row": flag_row,
        "antenna1": s["antenna1"],
        "antenna2": s["antenna2"],
        "time_bin": tb,
        "freq_bin": fb,
        "model": s["model"],
        "split": core.split_labels(
            train=s["train"], validation=s["validation"], test=s["test"]
        ),
    }


def timed(fn, repeats):
    wall, cpu, out = [], [], None
    for _ in range(repeats):
        t, c = time.perf_counter(), time.process_time()
        out = fn()
        wall.append(time.perf_counter() - t)
        cpu.append(time.process_time() - c)
    return out, {
        "wall": wall,
        "cpu": cpu,
        "wall_min": min(wall),
        "wall_median": statistics.median(wall),
        "cpu_min": min(cpu),
    }


# Early-stop settings (research/p1-solver.md): the archived inputs both run to
# the 50-iteration cap, so these exercise the stop test at other iterations.
VARIANTS = {
    "luno": [{"stop_fraction": f} for f in (0.05, 0.45, 0.75, 0.94)],
    "fixture": [{"max_iterations": k} for k in (1, 3, 12)] + [{"stop_fraction": 0.5}],
}


def run_one(name, case, repeats):
    from rang import core

    tb, fb = case["time_bin"], case["freq_bin"]
    nt, nf = int(tb.max()) + 1, int(fb.max()) + 1
    na = int(max(case["antenna1"].max(), case["antenna2"].max())) + 1

    def solve(**settings):
        return core.solve_complex(
            case["data"],
            case["weights"],
            case["flag"],
            case["flag_row"],
            case["antenna1"],
            case["antenna2"],
            tb,
            fb,
            ntime_bins=nt,
            nfreq_bins=nf,
            nant=na,
            model=case["model"],
            **settings,
        )

    solution, solve_t = timed(solve, repeats)
    variants = {}
    for settings in VARIANTS[name]:
        other = solve(**settings)
        variants[json.dumps(settings, sort_keys=True)] = {
            "gains": digest(other.gains),
            "flags": digest(other.flags),
            "iterations": other.iterations,
            "converged_fraction": other.converged_fraction.hex(),
        }

    def fused():
        return core.fused_pass(
            case["data"],
            case["weights"],
            case["antenna1"],
            case["antenna2"],
            tb,
            fb,
            solution.gains,
            solution.flags == 0,
            case["split"],
            model=case["model"],
        )

    result, fused_t = timed(fused, repeats)
    return {
        "shape": {"nrow": len(tb), "nchan": len(fb), "nt": nt, "nf": nf, "nant": na},
        "hashes": {
            "gains": digest(solution.gains),
            "flags": digest(solution.flags),
            "iterations": solution.iterations,
            "converged_fraction": solution.converged_fraction.hex(),
            "residuals": digest(result.residuals),
            "scores": digest(result.scores),
            "diag_h": digest(result.diag_h),
            "diag_b": digest(result.diag_b),
            "diag_count": digest(result.diag_count),
            "split_stats": json.dumps(
                {
                    k: {**v, "sum": float(v["sum"]).hex()}
                    for k, v in result.split_stats.items()
                },
                sort_keys=True,
            ),
            "variants": variants,
        },
        "solve": solve_t,
        "fused": fused_t,
    }


def run(out, repeats):
    from rang import core

    before = loadavg()
    started = time.perf_counter()
    cases = {"luno": luno(), "fixture": fixture()}
    load_seconds = time.perf_counter() - started
    result = {
        "protocol": "research/p1-solver.md",
        "backend": core.backend_name(),
        "library": str(core.library_path()),
        "library_sha256": sha256(core.library_path().read_bytes()).hexdigest(),
        "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
        "repeats": repeats,
        "load_before": before,
        "input_load_seconds": load_seconds,
        "cases": {name: run_one(name, case, repeats) for name, case in cases.items()},
        "load_after": loadavg(),
        "max_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    Path(out).write_text(json.dumps(result, indent=1) + "\n")
    return result


def extension_of(python):
    """The `rang._core` file and its SHA256 that `python` loads (task P9:
    one venv per extension build replaces `RANG_CORE_LIB`)."""
    origin = subprocess.run(
        [
            python,
            "-c",
            "import importlib.util; print(importlib.util.find_spec("
            + "'rang._core').origin)",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return {"path": origin, "sha256": sha256(Path(origin).read_bytes()).hexdigest()}


def sweep(out_dir, libs, threads, rounds, repeats):
    out_dir = Path(out_dir)
    if not str(out_dir).startswith("outputs/"):
        raise SystemExit("output directory must be beneath outputs/")
    out_dir.mkdir(parents=True, exist_ok=False)
    names = list(libs)
    children = []
    for r in range(rounds):
        order = names if r % 2 == 0 else names[::-1]
        for n in threads:
            for name in order:
                path = out_dir / f"r{r}-t{n}-{name}.json"
                env = {
                    **os.environ,
                    "RAYON_NUM_THREADS": str(n),
                    "OPENBLAS_NUM_THREADS": "1",
                }
                t = time.perf_counter()
                subprocess.run(
                    [
                        libs[name],
                        __file__,
                        "run",
                        str(path),
                        "--repeats",
                        str(repeats),
                    ],
                    env=env,
                    check=True,
                )
                child = json.loads(path.read_text())
                child["process_wall"] = time.perf_counter() - t
                children.append((r, n, name, child))
                print(
                    f"round {r} threads {n:2d} {name}: solve luno "
                    f"{child['cases']['luno']['solve']['wall_min']:.4f} s, fused luno "
                    f"{child['cases']['luno']['fused']['wall_min']:.4f} s, "
                    f"load {child['load_before']:.1f}",
                    flush=True,
                )
    reference = children[0][3]["cases"]
    table = {}
    equal = {}
    for r, n, name, child in children:
        key = f"{name} t{n}"
        cell = table.setdefault(key, {"rss_mb": [], "load": []})
        cell["rss_mb"].append(child["max_rss_mb"])
        cell["load"].append(child["load_before"])
        for case, values in child["cases"].items():
            for kernel in ("solve", "fused"):
                cell.setdefault(f"{case}_{kernel}_wall", []).extend(
                    values[kernel]["wall"]
                )
                cell.setdefault(f"{case}_{kernel}_cpu", []).extend(
                    values[kernel]["cpu"]
                )
            equal[f"r{r} {key} {case}"] = values["hashes"] == reference[case]["hashes"]
    summary = {
        "protocol": "research/p1-solver.md",
        "interpreters": {
            k: {"python": str(v), "extension": extension_of(v)} for k, v in libs.items()
        },
        "threads": threads,
        "rounds": rounds,
        "repeats": repeats,
        "reference": f"{names[0]} t{threads[0]} round 0",
        "reference_hashes": {k: v["hashes"] for k, v in reference.items()},
        "all_equal": all(equal.values()),
        "unequal": [k for k, ok in equal.items() if not ok],
        "table": {
            key: {
                metric: {"min": min(v), "median": statistics.median(v)}
                for metric, v in cell.items()
            }
            for key, cell in table.items()
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(
        json.dumps({"all_equal": summary["all_equal"], "unequal": summary["unequal"]})
    )
    for key, cell in summary["table"].items():
        print(
            f"{key:12s} luno solve {cell['luno_solve_wall']['min']:.4f} "
            f"(cpu {cell['luno_solve_cpu']['min']:.3f}) fused "
            f"{cell['luno_fused_wall']['min']:.4f} | fixture solve "
            f"{cell['fixture_solve_wall']['min']:.4f} fused "
            f"{cell['fixture_fused_wall']['min']:.4f} | rss "
            f"{cell['rss_mb']['median']:.0f} MB"
        )
    if not summary["all_equal"]:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("out")
    p_run.add_argument("--repeats", type=int, default=5)
    p_sweep = sub.add_parser("sweep")
    p_sweep.add_argument("out_dir")
    p_sweep.add_argument(
        "--python", action="append", required=True, help="NAME=venv interpreter"
    )
    p_sweep.add_argument("--threads", default="1,2,4,8,16")
    p_sweep.add_argument("--rounds", type=int, default=3)
    p_sweep.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.mode == "run":
        run(args.out, args.repeats)
    else:
        libs = dict(item.split("=", 1) for item in args.python)
        threads = [int(x) for x in args.threads.split(",")]
        sweep(args.out_dir, libs, threads, args.rounds, args.repeats)


if __name__ == "__main__":
    main()
