"""Solver convergence curve on the LUNO four-station slice (S1 review).

Usage: python convergence.py <fetched-dir> <out.json>

Solves the task K `original` arm with max_iterations = k for k in a grid
and records the converged fraction, the iteration count, the wall time and
the largest gain difference (and baseline-product difference) from the
50-iteration solution on gains valid in both. Read-only on every input.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

from rangtoy import core_campaign, core_fetch
from rangtoy.core_workflow import core_solve


def main():
    fetched, out = sys.argv[1], Path(sys.argv[2])
    arrays, _ = core_fetch.decode_slice(fetched)
    rows = np.asarray(json.loads((Path(fetched) / "result.json").read_text())["rows"])
    extra = core_campaign.decode_extra(fetched, rows)
    state = core_campaign.build_state(arrays, extra)
    zero = np.zeros_like(state["train"])
    ref_metrics, _, _, _, ref = core_solve(state, zero, 2, 32, 50)
    g50, v50 = ref["gains"], ref["gain_valid"]
    records = []
    for k in [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 35, 40, 45, 50, 60, 80, 100, 150, 200]:
        t = time.perf_counter()
        metrics, _, _, _, diag = core_solve(state, zero, 2, 32, k)
        wall = time.perf_counter() - t
        g, v = diag["gains"], diag["gain_valid"]
        both = v & v50
        dg = float(np.abs(g[both] - g50[both]).max()) if both.any() else None
        # Gauge-invariant check: baseline products G_p G_q^H on pairs valid in both.
        dprod = 0.0
        for p in range(g.shape[2]):
            for q in range(p + 1, g.shape[2]):
                pair = both[..., p] & both[..., q]
                if pair.any():
                    a = g[..., p, :, :] @ g[..., q, :, :].conj().swapaxes(-1, -2)
                    b = g50[..., p, :, :] @ g50[..., q, :, :].conj().swapaxes(-1, -2)
                    dprod = max(dprod, float(np.abs(a[pair] - b[pair]).max()))
        records.append(
            {
                "max_iterations": k,
                "iterations": metrics["solver"]["iterations"],
                "converged_fraction": metrics["solver"]["converged_fraction"],
                "valid_gain_fraction": metrics["valid_gain_fraction"],
                "valid_equal_to_50": bool(np.array_equal(v, v50)),
                "max_abs_gain_diff_vs_50": dg,
                "max_abs_baseline_product_diff_vs_50": dprod,
                "polar_tv": metrics["tv"],
                "polar_tv_rel_diff_vs_50": abs(metrics["tv"] - ref_metrics["tv"]) / ref_metrics["tv"],
                "validation_loss": metrics["losses"]["validation"],
                "train_loss": metrics["losses"]["train"],
                "wall_s": wall,
            }
        )
        print(json.dumps(records[-1]))
    out.write_text(json.dumps({"reference": ref_metrics["solver"], "records": records}, indent=1) + "\n")


if __name__ == "__main__":
    main()
