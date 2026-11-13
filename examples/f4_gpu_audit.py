"""F4 Stage 4 audit (research/f4-flagger.md, "WSL GPU training audit"): does
examples/f3_train.py run with --nplanes 23 on the WSL GPU, and at what GPU
memory and step rate? Not training: synthetic shards (random planes and
labels, shapes of F3's calibrator shards with 23 planes), weights discarded.

Usage (WSL, the jax-cuda venv): python examples/f4_gpu_audit.py OUT [--steps 2000]

Writes OUT/shards/{train,validation}/*.npz, OUT/train/ (f3_train.py's output),
OUT/gpu.csv (nvidia-smi every second) and OUT/audit.json.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
NPLANES = 23
# (role, kind, time windows): F3 calibrator shapes, 256 baselines x 2048 channels.
SHARDS = [
    ("train", "real", 10),
    ("train", "real", 11),
    ("train", "sim", 16),
    ("train", "sim", 32),
    ("validation", "real", 10),
    ("validation", "sim", 16),
]


def make(out, seed=7):
    rng = np.random.default_rng(seed)
    for k, (role, kind, nt) in enumerate(SHARDS):
        d = out / "shards" / role
        d.mkdir(parents=True, exist_ok=True)
        x = rng.standard_normal((256, nt, 2048, NPLANES), dtype=np.float32)
        y = (rng.random((256, nt, 2048)) < 0.05).astype(np.int8)
        y[rng.random(y.shape) < 0.02] = -1
        np.savez(
            d / f"synthetic-{kind}-{k}.npz",
            x=x.astype(np.float16),
            y=y,
            kind=np.array(kind),
            meta=np.array("f4 gpu audit, synthetic"),
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--steps", type=int, default=2000)
    a = p.parse_args()
    t0 = time.perf_counter()
    make(a.out)
    t_make = time.perf_counter() - t0
    with open(a.out / "gpu.csv", "w") as gpu:
        smi = subprocess.Popen(
            [
                "nvidia-smi",
                "--query-gpu=timestamp,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
                "-l",
                "1",
            ],
            stdout=gpu,
        )
        t1 = time.perf_counter()
        rc = subprocess.call(
            [
                sys.executable,
                str(HERE / "examples/f3_train.py"),
                str(a.out / "shards"),
                str(a.out / "train"),
                "--seed",
                "1",
                "--steps",
                str(a.steps),
                "--nplanes",
                str(NPLANES),
            ]
        )
        wall = time.perf_counter() - t1
        smi.terminate()
        smi.wait()
    rows = [r.split(", ") for r in (a.out / "gpu.csv").read_text().splitlines() if r]
    mem = [int(r[1]) for r in rows]
    util = [int(r[2]) for r in rows]
    rec = json.loads((a.out / "train" / "train.json").read_text()) if rc == 0 else {}
    curve = rec.get("curve", [])
    # Steady rate from the last two curve points (the first includes JIT compilation).
    rate = None
    if len(curve) >= 2:
        rate = (curve[-1]["step"] - curve[-2]["step"]) / (
            curve[-1]["seconds"] - curve[-2]["seconds"]
        )
    res = {
        "rc": rc,
        "nplanes": NPLANES,
        "steps": a.steps,
        "make_seconds": t_make,
        "train_wall_seconds": wall,
        "devices": rec.get("devices"),
        "jax": rec.get("jax"),
        "weights": rec.get("weights"),
        "train_seconds": rec.get("train_seconds"),
        "load_seconds": rec.get("load_seconds"),
        "steps_per_second_steady": rate,
        "gpu_mem_mib_baseline": mem[0] if mem else None,
        "gpu_mem_mib_peak": max(mem) if mem else None,
        "gpu_util_pct_median": float(np.median(util)) if util else None,
        "extrapolated_30000_steps_seconds": 30000 / rate if rate else None,
    }
    (a.out / "audit.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res))
    sys.exit(rc)


if __name__ == "__main__":
    main()
