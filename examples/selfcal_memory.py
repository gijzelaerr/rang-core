# SPDX-License-Identifier: MIT
"""selfcal-memory (issue #34, research/selfcal-memory.md): one self-calibration
solve on its own, as `rang-core selfcal` runs it, for the peak and the gates.

    python examples/selfcal_memory.py solve MS --type Sp --solint inf --limit 8 \\
        --stream auto --out OUT.npz
    python examples/selfcal_memory.py compare A.npz B.npz

`solve` reads the MS as the selfcal stage does (`core_pipeline.inspect_ms`,
the budget of `data.memory_limit_gb` LIMIT with the selfcal figure, field 0,
DATA against MODEL_DATA, the weight column of `data.weights: as_is`, refant
0, the gain clip) and saves the solution and a JSON record beside OUT. `--limit
none` gives no budget (the one-call solve). `compare` prints whether two
solutions are identical (gains, flags, iterations, converged fraction, times)
and the largest gain difference; exit status 1 when they are not.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np


def cmd_solve(a):
    from rang import cal_selfcal, core_chunks
    from rang import core_pipeline as pipe

    started = time.perf_counter()
    info = pipe.inspect_ms(a.ms)
    limit = None if a.limit == "none" else float(a.limit)
    budget = None
    plan = None
    if limit is not None:
        plan = core_chunks.budget({"data": {"memory_limit_gb": limit}}, info)
        budget = plan.selfcal()
    rows = pipe._selected_rows(info["rows"], [a.field], ())
    term = {"name": a.type, "type": a.type, "solint": a.solint, "freqint": "inf"}
    if a.solint not in ("inf", "int") and not a.solint.endswith("s"):
        term["solint"] = int(a.solint)
    stream = {"auto": "auto", "true": True, "false": False}[a.stream]
    t0 = time.perf_counter()
    sol = cal_selfcal.solve(
        a.ms, term, rows=rows, field_id=a.field, input_column="DATA",
        model_column="MODEL_DATA", weight_column=pipe.weight_column(info, "as_is"),
        refant=0, minuvw_m=0.0, gain_clip=(0.5, 2.0), budget=budget, stream=stream,
    )  # fmt: skip
    solve_s = time.perf_counter() - t0
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        out, gains=sol.gains, flags=sol.flags, gain_time=sol.gain_time,
        iterations=sol.iterations, converged_fraction=sol.converged_fraction,
    )  # fmt: skip
    record = {
        "ms": str(a.ms),
        "term": term,
        "memory_limit_gb": limit,
        "stream": a.stream,
        "selfcal_cell_bytes": core_chunks.CELL_BYTES["selfcal"],
        "rows": len(rows),
        "cell": list(info["cell"]),
        "summary": sol.summary(),
        "solve_seconds": solve_s,
        "wall_seconds": time.perf_counter() - started,
    }
    if plan is not None:
        tb, _, _ = cal_selfcal.time_bins(
            info["rows"]["TIME"][rows], info["rows"]["SCAN_NUMBER"][rows],
            info["rows"]["FIELD_ID"][rows], term["solint"],
        )  # fmt: skip
        largest = int(np.bincount(tb).max()) * int(np.prod(info["cell"]))
        record["largest_interval_cells"] = largest
        record["plan_gib_one_interval"] = budget.need_gb(len(rows), largest, False)
    out.with_suffix(".json").write_text(json.dumps(record, indent=1, default=str))
    print(json.dumps({k: record[k] for k in ("term", "solve_seconds")}, default=str))


def cmd_compare(a):
    x, y = np.load(a.a), np.load(a.b)
    same = {k: bool(np.array_equal(x[k], y[k])) for k in x.files}
    g = np.where(x["flags"] | y["flags"], 0, x["gains"] - y["gains"])
    report = {
        "a": a.a,
        "b": a.b,
        "identical": all(same.values()),
        "fields": same,
        "max_abs_gain_difference": float(np.abs(g).max()),
        "iterations": [int(x["iterations"]), int(y["iterations"])],
    }
    print(json.dumps(report))
    return 0 if report["identical"] else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("solve")
    s.add_argument("ms")
    s.add_argument("--type", choices=("Sp", "Sa"), required=True)
    s.add_argument("--solint", default="inf")
    s.add_argument("--limit", default="8")
    s.add_argument("--stream", choices=("auto", "true", "false"), default="auto")
    s.add_argument("--field", type=int, default=0)
    s.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    a = p.parse_args(argv)
    if a.cmd == "solve":
        cmd_solve(a)
        return 0
    return cmd_compare(a)


if __name__ == "__main__":
    sys.exit(main())
