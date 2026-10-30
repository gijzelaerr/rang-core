"""Build a core-solved mirror of the concurrent suite for the trend chain test.

Usage: python examples/build_core_trend_mirror.py <concurrent-suite> outputs/<fresh-mirror>

For each of the seven equivariance cases, copies `state.npz` and
`manifest.json` byte for byte and writes `trials/baseline/diagnostics.npz` and
`metrics.json` from `core_workflow.core_solve` (research/core-phase3-trend.md).
Also writes mirror-receipt.json with the comparison against QuartiCal's saved
baselines (criterion 1).
"""

import json
import shutil
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np
from rangtoy.core_cases import CASES
from rangtoy.core_state import load_state
from rangtoy.core_workflow import core_solve


def main():
    source, mirror = Path(sys.argv[1]), Path(sys.argv[2])
    if not str(mirror).startswith("outputs/") or mirror.exists():
        raise SystemExit("mirror must be new and beneath outputs/")
    started = time.perf_counter()
    receipt = {"source": str(source), "cases": {}}
    for case in CASES:
        src = source / "experiments" / case
        dst = mirror / "experiments" / case
        (dst / "trials/baseline").mkdir(parents=True)
        for name in ("state.npz", "manifest.json"):
            shutil.copy2(src / name, dst / name)
        manifest = json.loads((dst / "manifest.json").read_text())
        if manifest["split_gain_intervals"] != [2, 32]:
            raise ValueError("frozen 2x32 grid required")
        state = load_state(dst)
        metrics, _, _, _, diagnostics = core_solve(
            state, np.zeros_like(state["train"]), 2, 32, 50, trial="baseline"
        )
        np.savez_compressed(dst / "trials/baseline/diagnostics.npz", **diagnostics)
        solver = metrics.pop("solver")
        (dst / "trials/baseline/metrics.json").write_text(
            json.dumps(metrics, indent=2) + "\n"
        )
        with np.load(src / "trials/baseline/diagnostics.npz") as saved:
            qc_gains, qc_valid = saved["gains"], saved["gain_valid"]
        valid = diagnostics["gain_valid"]
        receipt["cases"][case] = {
            "state_sha256_equal": sha256((src / "state.npz").read_bytes()).hexdigest()
            == sha256((dst / "state.npz").read_bytes()).hexdigest(),
            "gain_valid_equal": bool(np.array_equal(valid, qc_valid)),
            "max_abs_gain_diff": float(
                np.max(np.abs(diagnostics["gains"] - qc_gains)[qc_valid])
            ),
            "solver": solver,
            "seconds": metrics["seconds"],
        }
    receipt["seconds_total"] = time.perf_counter() - started
    receipt["criterion_1_pass"] = all(
        c["state_sha256_equal"]
        and c["gain_valid_equal"]
        and c["max_abs_gain_diff"] <= 1e-6
        for c in receipt["cases"].values()
    )
    (mirror / "mirror-receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(
        json.dumps(
            {
                "criterion_1_pass": receipt["criterion_1_pass"],
                "worst_gain_diff": max(
                    c["max_abs_gain_diff"] for c in receipt["cases"].values()
                ),
                "seconds_total": receipt["seconds_total"],
            }
        )
    )


if __name__ == "__main__":
    main()
