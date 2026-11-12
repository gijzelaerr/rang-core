# SPDX-License-Identifier: GPL-3.0-or-later
"""The C-stream gate on the archived `complex` solves (C1 section 4, rule 2).

Task C2a (research/c2a-gain.md). Recomputes, through the unchanged
`core.solve_complex` path, the three archived results every calibration-stream
merge must leave as they are:

- `4ed2aa89...`: core K `original` on the LUNO four-station slice (seed-7
  split, `solve_flags(state, 0)`, grid 2 x 32, 50 iterations), the loader of
  `examples/run_l5_solver_study.py load slice`;
- `7b370c13...`: L5's D on the fixture clean case (archived solve flags, grid
  2 x 32, 50 iterations), `load fixture` of the same script;
- core phase 2 on LUNO (`outputs/core-phase2-inputs-20261029-01/arrays.npz`):
  50 iterations and converged fraction 0.9833234067897558, gain flags equal to
  QuartiCal 0.2.7's archived `gain_flags.npy` (research/core-phase2.md, criteria
  1 and 3; the rank survey, criterion 6, is not replayed here).

The archived inputs are ignored files of the main checkout. They are looked up
in `$RANG_ARCHIVE_OUTPUTS`, then `<checkout>/outputs`, then
`~/Github/rang/outputs` (a worktree has no `outputs/` of its own). Missing
inputs fail the gate unless `RANG_GAIN_HASHES=optional` is set, for hosts that
do not hold the archive; the output says which. Exit 0 only on equality.

    .venv/bin/python tools/gain_hash_gate.py [--json]
"""

import json
import os
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "slice_original": "4ed2aa89a68aad5bce6f48a62da4071f948502e043c302812ceda094440d4aa8",
    "fixture_D": "7b370c13c40170882ce44dac5e65cf387b7712a61a843f66033bfe161eb9e933",
}
LUNO_CONVERGED = 0.9833234067897558
LUNO_ITERATIONS = 50
SPLIT = {"train": 94047, "validation": 11742, "test": 11767}
GRID = (2, 32)
FIXTURE = "tv-response-wsl-20261029-01/clean"
SUPPORT = "luno-support-20261029-01/slice"
SOLVE_INPUTS = "luno-solve-20261029-02/inputs"
LUNO_ARRAYS = "core-phase2-inputs-20261029-01/arrays.npz"
LUNO_SOLVE = "luno-solve-20261029-02/solve"
NEEDED = (
    f"{FIXTURE}/state.npz",
    f"{FIXTURE}/backups/clean-t2-f32-solve.npz",
    f"{FIXTURE}/trials/clean-t2-f32/diagnostics.npz",
    SUPPORT,
    SOLVE_INPUTS,
    LUNO_ARRAYS,
    f"{LUNO_SOLVE}/gain_flags.npy",
)


def archive_root():
    """The first outputs directory that holds every archived input, or None."""
    candidates = []
    if os.environ.get("RANG_ARCHIVE_OUTPUTS"):
        candidates.append(Path(os.environ["RANG_ARCHIVE_OUTPUTS"]))
    candidates += [ROOT / "outputs", Path.home() / "Github/rang/outputs"]
    for root in candidates:
        if all((root / rel).exists() for rel in NEEDED):
            return root
    return None


def digest(array):
    return sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def solve(problem):
    from rang import core_solver_study as study

    return study.solve(problem, "", max_iterations=50)


def fixture(root):
    from rang import core_solver_study as study

    base = root / FIXTURE
    with np.load(base / "state.npz") as z:
        s = {k: z[k] for k in z.files}
    with np.load(base / "backups/clean-t2-f32-solve.npz") as z:
        flag, flag_row = z["FLAG"], z["FLAG_ROW"]
    with np.load(base / "trials/clean-t2-f32/diagnostics.npz") as z:
        d = {k: z[k] for k in ("gains", "gain_times", "gain_frequencies")}
    integration = np.unique(s["times"], return_inverse=True)[1]
    tb, fb = integration // GRID[0], np.arange(s["data"].shape[1]) // GRID[1]
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
    return digest(solve(problem)["gains"])


def slice_original(root):
    from rang import core_campaign_array as cca
    from rang import core_solver_study as study
    from rang.core_workflow import gain_grid, solve_flags

    roots = (root / SUPPORT, root / SOLVE_INPUTS)
    arrays, rows, _ = cca.decode_inputs(range(4), roots=roots)
    extra = cca.decode_extra(rows, roots=roots)
    state = cca.build_state(arrays, extra, 4)
    counts = {k: int(np.count_nonzero(state[k])) for k in SPLIT}
    if counts != SPLIT:
        raise RuntimeError(f"split counts {counts} differ from the archive {SPLIT}")
    flags, frows = solve_flags(state, np.zeros_like(state["train"]))
    time_map, freq_map, gt, gf = gain_grid(state, *GRID)
    problem = study.problem_from_state(
        state, flags, frows, time_map, freq_map, gt, gf, 4
    )
    return digest(solve(problem)["gains"])


def luno_phase2(root):
    from rang import core

    with np.load(root / LUNO_ARRAYS) as z:
        a = {k: z[k] for k in z.files}
    qc_flagged = np.load(root / LUNO_SOLVE / "gain_flags.npy") != 0
    nt, nf, na = qc_flagged.shape[:3]
    integration = np.unique(a["TIME"], return_inverse=True)[1]
    tb, fb = integration // GRID[0], np.arange(a["DATA"].shape[1]) // GRID[1]
    rust = core.solve_complex(
        a["DATA"],
        a["WEIGHT_SPECTRUM"],
        a["FLAG"],
        a["FLAG_ROW"],
        a["ANTENNA1"],
        a["ANTENNA2"],
        tb,
        fb,
        ntime_bins=nt,
        nfreq_bins=nf,
        nant=na,
        model=a["MODEL_DATA"],
    )
    flags_equal = bool(
        np.array_equal((rust.flags != 0).reshape(qc_flagged.shape), qc_flagged)
    )
    return {
        "iterations": int(rust.iterations),
        "converged_fraction": float(rust.converged_fraction),
        "gain_flags_equal_quartical": flags_equal,
    }


def main(argv):
    started = time.perf_counter()
    root = archive_root()
    if root is None:
        message = "archived inputs absent (set RANG_ARCHIVE_OUTPUTS)"
        if os.environ.get("RANG_GAIN_HASHES") == "optional":
            print(f"gain-hash gate: SKIPPED, {message}")
            return 0
        print(f"gain-hash gate: FAIL, {message}")
        return 1
    got = {"slice_original": slice_original(root), "fixture_D": fixture(root)}
    luno = luno_phase2(root)
    checks = {k: got[k] == EXPECTED[k] for k in EXPECTED}
    checks["luno_iterations"] = luno["iterations"] == LUNO_ITERATIONS
    checks["luno_converged_fraction"] = (
        abs(luno["converged_fraction"] - LUNO_CONVERGED) <= 1e-12
    )
    checks["luno_gain_flags"] = luno["gain_flags_equal_quartical"]
    report = {
        "archive": str(root),
        "hashes": got,
        "luno": luno,
        "checks": checks,
        "pass": all(checks.values()),
        "seconds": round(time.perf_counter() - started, 2),
    }
    if "--json" in argv:
        print(json.dumps(report, indent=1))
    else:
        for name, ok in checks.items():
            print(f"  {'ok  ' if ok else 'FAIL'} {name}")
        print(
            f"gain-hash gate: {'PASS' if report['pass'] else 'FAIL'} "
            f"({report['seconds']} s, archive {root})"
        )
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
