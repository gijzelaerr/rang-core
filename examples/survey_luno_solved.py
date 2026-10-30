"""LUNO 1934-638 support at solved QuartiCal gains (research/flagging-luno-solved.md).

Same TRAIN cells, grid, native normals, rank cutoff and requirement as
examples/survey_luno_support.py, but each bin's four-station gains come from the
solve. Supported bins whose active-station gains QuartiCal flagged are reported as
"no_solved_gain" and not classified. Crosscheck uses anchored_response(H, 0, 0, 0).
"""

import json
import pathlib
import sys
from hashlib import sha256

import numpy as np
from rangtoy.core_influence import anchored_response, training_normals

extract, solve, out = (pathlib.Path(x) for x in sys.argv[1:4])
GRID, CUTOFF = (2, 32), 1e-10
out.mkdir(parents=False, exist_ok=False)
directory = extract / "group1"
a1, a2, time, flag, weight, model = (
    np.load(directory / f"{n}.npy")
    for n in ("antenna1", "antenna2", "time", "flag", "weight", "model")
)
solved = np.load(solve / "gains.npy")
solved_flags = np.load(solve / "gain_flags.npy") != 0
integration = np.searchsorted(np.unique(time), time)
ntime, nchan_bins = int(integration.max()) // GRID[0] + 1, flag.shape[1] // GRID[1]
if solved.shape[:3] != (ntime, nchan_bins, 4):
    raise ValueError(f"solved gain grid {solved.shape} does not match the survey")
nbins = ntime * nchan_bins
gains = np.ascontiguousarray(solved.reshape(nbins, 4, 2, 2).astype(np.complex128))
gain_flags = solved_flags.reshape(nbins, 4)
train = ~flag.any(-1) & (weight > 0).all(-1) & np.isfinite(model).all(-1)
rows, channels = np.nonzero(train)
bins = (integration[rows] // GRID[0]) * nchan_bins + channels // GRID[1]
p, q = a1[rows], a2[rows]
models = model[rows, channels].astype(np.complex128).reshape(-1, 2, 2)
weights = weight[rows, channels].astype(np.float64)
safe = np.where(np.isfinite(gains), gains, 0)
h, _, counts = training_normals(
    safe, models, np.zeros_like(models), weights, p, q, bins
)
summary = {
    "bins": nbins,
    "train_cells": int(train.sum()),
    "bins_with_train": 0,
    "no_solved_gain_bins": 0,
    "fully_identified_bins": 0,
    "underidentified_bins": 0,
    "over_rank_anomalies": 0,
    "no_train_bins": 0,
    "fully_identified_cells": 0,
    "underidentified_cells": 0,
    "no_solved_gain_cells": 0,
    "native_status_by_label": {},
    "failures": [],
}
for b in range(nbins):
    if not counts[b]:
        summary["no_train_bins"] += 1
        continue
    summary["bins_with_train"] += 1
    selected = bins == b
    active = np.zeros(4, dtype=bool)
    active[p[selected]] = True
    active[q[selected]] = True
    if gain_flags[b, active].any() or not np.isfinite(gains[b, active]).all():
        summary["no_solved_gain_bins"] += 1
        summary["no_solved_gain_cells"] += int(counts[b])
        summary["failures"].append({"bin": b, "label": "no_solved_gain"})
        continue
    eig = np.linalg.eigvalsh(h[b])
    rank = int(np.sum(eig > CUTOFF * eig[-1])) if eig[-1] > 0 else 0
    required = 8 * int(active.sum()) - 4
    label = (
        "fully_identified"
        if rank == required
        else "underidentified"
        if rank < required
        else "over_rank_anomalies"
    )
    if label == "over_rank_anomalies":
        summary[label] += 1
    else:
        summary[label + "_bins"] += 1
        summary[label + "_cells"] += int(counts[b])
    zero = np.zeros(32)
    status = anchored_response(h[b], zero, 0 * h[b], zero, gains[b], active)
    key = f"{label} status{status['native_status']}"
    summary["native_status_by_label"][key] = (
        summary["native_status_by_label"].get(key, 0) + 1
    )
    if label != "fully_identified":
        edges = sorted({(int(x), int(y)) for x, y in zip(p[selected], q[selected])})
        summary["failures"].append(
            {
                "bin": b,
                "label": label,
                "cells": int(counts[b]),
                "active": np.flatnonzero(active).tolist(),
                "edges": edges,
                "rank": rank,
                "required": required,
            }
        )
summary["solve_summary"] = json.loads((solve / "summary.json").read_text())
summary["input_sha256"] = {
    str(path): sha256(path.read_bytes()).hexdigest()
    for path in (solve / "gains.npy", solve / "gain_flags.npy")
}
(out / "result.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
print(
    json.dumps(
        {
            k: v
            for k, v in summary.items()
            if k not in ("failures", "solve_summary", "input_sha256")
        }
    )
)
