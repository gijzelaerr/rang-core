"""Post-hoc L5 diagnostic (research/l5-solver-science.md): where do long runs
of the plain, transposed-weight and Anderson solvers differ in gain products,
and which of them has the lower training χ² there?

Usage: python examples/diagnose_solver_study.py {fixture,slice} outputs/<fresh-dir>

Solves R at 500, 2000 and 5000 iterations, R_T at 500 and 2000 and Anderson
m = 2, 3, 5 at 500 (stop fraction 2: never stops early), then reports per
interval the largest relative product distance between them and the
interval's weighted training χ² under each. Read-only on every input.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))

from rang import core_solver_study as study
from run_l5_solver_study import environment, load

RUNS = {
    "R500": ("", 500),
    "R2000": ("", 2000),
    "R5000": ("", 5000),
    "R_T500": ("qp_weights=transposed", 500),
    "R_T2000": ("qp_weights=transposed", 2000),
    "AA2": ("anderson=2", 500),
    "AA3": ("anderson=3", 500),
    "AA5": ("anderson=5", 500),
}


def interval_products(gains, valid):
    """(interval, pair) products and validity."""
    nt, nf, na = gains.shape[:3]
    g = gains.reshape(nt * nf, na, 2, 2)
    v = valid.reshape(nt * nf, na)
    p, q = np.triu_indices(na, 1)
    prod = g[:, p] @ g[:, q].conj().swapaxes(-1, -2)
    return prod, v[:, p] & v[:, q]


def interval_distance(a, b):
    pa, va = interval_products(a["gains"], a["valid"])
    pb, vb = interval_products(b["gains"], b["valid"])
    both = va & vb
    rel = np.linalg.norm(pa - pb, axis=(-1, -2)) / np.linalg.norm(pb, axis=(-1, -2))
    rel = np.where(both, rel, 0.0)
    return rel.max(axis=1)


def interval_chi2(problem, run):
    """Training χ² per interval: the fused pass on each interval's cells."""
    nt, nf = run["gains"].shape[:2]
    out = np.full(nt * nf, np.nan)
    t, f = problem["time_map"], problem["freq_map"]
    for interval in range(nt * nf):
        ti, fi = divmod(interval, nf)
        mask = problem["train"] & (t[:, None] == ti) & (f[None] == fi)
        if mask.any():
            out[interval] = study.losses(
                problem, run["gains"], run["valid"], {"train": mask}
            )["train"]["loss"]
    return out


def main():
    dataset, out = sys.argv[1], Path(sys.argv[2])
    if not str(out).startswith("outputs/l5-solver-") or out.exists():
        sys.exit("the run directory must be a fresh outputs/l5-solver-* path")
    out.mkdir(parents=True)
    started = time.perf_counter()
    problem, _, _, info = load(dataset)
    runs = {}
    for label, (options, k) in RUNS.items():
        runs[label] = study.solve(problem, options, max_iterations=k, stop_fraction=2.0)
        print(label, f"{runs[label]['wall_seconds']:.1f} s", flush=True)
    ref = runs["R5000"]
    distances = {
        label: interval_distance(run, ref)
        for label, run in runs.items()
        if label != "R5000"
    }
    distances["AA5_vs_AA2"] = interval_distance(runs["AA5"], runs["AA2"])
    distances["R_T2000_vs_R_T500"] = interval_distance(runs["R_T2000"], runs["R_T500"])
    worst = sorted(
        {int(i) for d in distances.values() for i in np.argsort(d)[-3:] if d[i] > 1e-10}
    )
    chi2 = {label: interval_chi2(problem, run) for label, run in runs.items()}
    nant = problem["nant"]
    flags = {
        label: run["flags"].reshape(-1, nant).sum(axis=1).tolist()
        for label, run in runs.items()
    }
    result = {
        "task": "L5",
        "mode": "diagnose-fixed-points (post hoc)",
        "dataset": dataset,
        "environment": environment(),
        "load": info,
        "max_distance_to_R5000": {k: float(v.max()) for k, v in distances.items()},
        "median_interval_distance_to_R5000": {
            k: float(np.median(v)) for k, v in distances.items()
        },
        "intervals_above_1e-9": {
            k: int(np.count_nonzero(v > 1e-9)) for k, v in distances.items()
        },
        "worst_intervals": {
            str(i): {
                "distance_to_R5000": {k: float(v[i]) for k, v in distances.items()},
                "train_chi2": {k: float(c[i]) for k, c in chi2.items()},
                "hard_flagged_gains": {k: f[i] for k, f in flags.items()},
            }
            for i in worst
        },
        "total_train_loss": {
            k: study.losses(
                problem, r["gains"], r["valid"], {"train": problem["train"]}
            )["train"]["loss"]
            for k, r in runs.items()
        },
        "wall_seconds": {k: r["wall_seconds"] for k, r in runs.items()},
    }
    result["seconds"] = time.perf_counter() - started
    (out / "result.json").write_text(json.dumps(result, indent=1, default=float) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "max_distance_to_R5000",
                    "intervals_above_1e-9",
                    "total_train_loss",
                )
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
