"""Isolated-process resource benchmark of structured nuisance projection.

Synthetic Jacobian dimensions, not telescope simulation or calibration quality.
Gain derivatives use baseline incidence; shared/target derivatives are random.
"""

import argparse
import json
import os
import platform
import resource
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rang.projector import project_grouped, project_out


def fixture(antennas, channels, seed=71):
    rng = np.random.default_rng(seed)
    p, q = np.triu_indices(antennas, 1)
    baselines = len(p)
    visibility = rng.normal(size=(channels, baselines)) + 1j * rng.normal(
        size=(channels, baselines)
    )
    amplitude = np.zeros((baselines, antennas))
    phase = np.zeros_like(amplitude)
    amplitude[np.arange(baselines), p] = 1
    amplitude[np.arange(baselines), q] = 1
    phase[np.arange(baselines), p] = 1
    phase[np.arange(baselines), q] = -1
    derivative = np.concatenate(
        (visibility[..., None] * amplitude, 1j * visibility[..., None] * phase), axis=-1
    ).reshape(-1, 2 * antennas)
    gains = np.stack((derivative.real, derivative.imag), axis=1).reshape(
        -1, 2 * antennas
    )
    groups = np.repeat(np.arange(channels), 2 * baselines)
    shared = rng.normal(size=(len(gains), 2 * (antennas - 1)))
    target = rng.normal(size=(len(gains), 2))
    return gains, shared, target, groups


def worker(args):
    gains, shared, target, groups = fixture(args.worker_antennas, args.channels)

    def run():
        if args.worker_method.startswith("grouped"):
            return project_grouped(
                gains, shared, target, groups, backend=args.worker_method.split("_")[1]
            )
        expanded = np.column_stack(
            [gains * (groups == g)[:, None] for g in range(args.channels)] + [shared]
        )
        if args.worker_method == "full_rust":
            return project_out(expanded, target)
        coefficients, _, rank, _ = np.linalg.lstsq(expanded, target, rcond=1e-12)
        return target - expanded @ coefficients, int(rank)

    run()
    elapsed = []
    for _ in range(args.repeats):
        start = perf_counter()
        projected, rank = run()
        elapsed.append(perf_counter() - start)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    print(
        json.dumps(
            {
                "antennas": args.worker_antennas,
                "channels": args.channels,
                "method": args.worker_method,
                "seconds": elapsed,
                "median_seconds": float(np.median(elapsed)),
                "process_peak_rss_bytes": peak_bytes,
                "rank": rank,
                "target_gram": (projected.T @ projected).tolist(),
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--antennas", type=int, nargs="+", default=[8, 16, 32, 64])
    parser.add_argument("--channels", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "outputs/projector-scaling"
    )
    parser.add_argument("--worker-antennas", type=int)
    parser.add_argument(
        "--worker-method",
        choices=["full_numpy", "full_rust", "grouped_numpy", "grouped_rust"],
    )
    args = parser.parse_args()
    if (
        args.channels < 2
        or args.repeats < 1
        or min(args.antennas) < 4
        or (args.worker_antennas is not None and args.worker_antennas < 4)
    ):
        parser.error("at least two channels, four antennas and one repeat required")
    if args.worker_antennas:
        if args.worker_method is None:
            parser.error("worker method required")
        worker(args)
        return
    rows = []
    for antennas in args.antennas:
        reference = None
        for method in ("full_numpy", "full_rust", "grouped_numpy", "grouped_rust"):
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker-antennas",
                str(antennas),
                "--worker-method",
                method,
                "--channels",
                str(args.channels),
                "--repeats",
                str(args.repeats),
            ]
            env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
            row = json.loads(subprocess.check_output(command, env=env))
            gram = np.asarray(row["target_gram"])
            if reference is None:
                reference = gram
            row["relative_gram_error"] = float(
                np.linalg.norm(gram - reference) / np.linalg.norm(reference)
            )
            expected_rank = args.channels * (2 * antennas - 1) + 2 * (antennas - 1)
            if row["rank"] != expected_rank or row["relative_gram_error"] > 1e-10:
                raise RuntimeError(f"projection equivalence failed: {row}")
            rows.append(row)
            print(json.dumps(row), flush=True)
            args.output.mkdir(parents=True, exist_ok=True)
            payload = {
                "scope": "Synthetic local Jacobian projection only; no sky, beam, geometry, nonlinear solve or imaging. Not a state-of-the-art calibration benchmark.",
                "timing_scope": "Input expansion and projection; fixture creation and one warmup excluded. Each method/dimension uses a fresh process.",
                "memory_scope": "Whole worker peak RSS including interpreter, fixture, warmup and repeated projection; not incremental kernel allocation.",
                "seed": 71,
                "platform": platform.platform(),
                "numpy_version": np.__version__,
                "thread_environment": {
                    "OPENBLAS_NUM_THREADS": "1",
                    "OMP_NUM_THREADS": "1",
                },
                "thread_count_note": "Actual BLAS thread count is not measured; OpenBLAS settings do not control Apple's Accelerate backend.",
                "blas_build": np.__config__.CONFIG.get("Build Dependencies", {}).get(
                    "blas", {}
                ),
                "source_sha256": {
                    path: sha256((ROOT / path).read_bytes()).hexdigest()
                    for path in (
                        "src/projector.rs",
                        "python/rang/projector.py",
                        "examples/projector_scaling.py",
                    )
                },
                "results": rows,
            }
            (args.output / "results.json").write_text(
                json.dumps(payload, indent=2) + "\n"
            )


if __name__ == "__main__":
    main()
