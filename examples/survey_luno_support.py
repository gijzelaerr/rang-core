"""LUNO processed-support survey (research/flagging-luno-support.md), host stage.

Reads the extraction from examples/extract_luno_support.py and evaluates the frozen
four-station native TRAIN normals on the 2-integration x 32-channel grid at identity
and at a fixed-seed random gain point. Descriptive only: no solve, no data writes.
"""

import json
import pathlib
import sys
from hashlib import sha256

import numpy as np
from rangtoy.flagging_influence import anchored_response, training_normals

source, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
GRID = (2, 32)
CUTOFF = 1e-10
SEED = 20261029
out.mkdir(parents=False, exist_ok=False)
receipts = {
    p.relative_to(source).as_posix(): sha256(p.read_bytes()).hexdigest()
    for p in sorted(source.rglob("*"))
    if p.is_file()
}


def gain_points(nbins):
    identity = np.broadcast_to(np.eye(2), (nbins, 4, 2, 2)).astype(np.complex128)
    rng = np.random.default_rng(SEED)
    noise = rng.standard_normal((nbins, 4, 2, 2, 2))
    return {
        "identity": np.ascontiguousarray(identity),
        "random_seed20261029": identity + 0.1 * (noise[..., 0] + 1j * noise[..., 1]),
    }


def survey(directory):
    a1, a2, time, flag, weight, model = (
        np.load(directory / f"{n}.npy")
        for n in ("antenna1", "antenna2", "time", "flag", "weight", "model")
    )
    integration = np.searchsorted(np.unique(time), time)
    nchan = flag.shape[1]
    ntime_bins = int(integration.max()) // GRID[0] + 1
    nchan_bins = nchan // GRID[1]
    nbins = ntime_bins * nchan_bins
    train = ~flag.any(-1) & (weight > 0).all(-1) & np.isfinite(model).all(-1)
    rows, channels = np.nonzero(train)
    bins = (integration[rows] // GRID[0]) * nchan_bins + channels // GRID[1]
    p, q = a1[rows], a2[rows]
    models = model[rows, channels].astype(np.complex128).reshape(-1, 2, 2)
    weights = weight[rows, channels].astype(np.float64)
    nonzero = (np.abs(models.reshape(-1, 4)) > 0).mean(0).tolist() if len(rows) else []
    result = {
        "integrations": int(integration.max()) + 1,
        "channels": int(nchan),
        "bins": nbins,
        "train_cells": int(train.sum()),
        "train_model_nonzero_fraction_per_corr": nonzero,
        "points": {},
    }
    if not len(rows) or not np.any(np.abs(models) > 0):
        result["status"] = "no TRAIN data or no model; bins not classified"
        return result
    for name, gains in gain_points(nbins).items():
        h, _, counts = training_normals(
            gains, models, np.zeros_like(models), weights, p, q, bins
        )
        summary = {
            "bins_with_train": 0,
            "fully_identified_bins": 0,
            "underidentified_bins": 0,
            "over_rank_anomalies": 0,
            "no_train_bins": 0,
            "fully_identified_cells": 0,
            "underidentified_cells": 0,
            "native_crosscheck_agree": 0,
            "native_crosscheck_disagree": [],
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
            native = anchored_response(
                h[b], np.zeros(32), h[b], np.zeros(32), gains[b], active
            )["native_status"]
            if (native == 3) == (label == "underidentified"):
                summary["native_crosscheck_agree"] += 1
            else:
                summary["native_crosscheck_disagree"].append([b, native, label])
            if label != "fully_identified":
                edges = sorted(
                    {(int(x), int(y)) for x, y in zip(p[selected], q[selected])}
                )
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
        result["points"][name] = summary
    return result


extract = json.loads((source / "extract.json").read_text())
result = {
    "protocol": "research/flagging-luno-support.md",
    "provisional": "licence and native weights unconfirmed; processed support only",
    "grid": list(GRID),
    "rank_relative_cutoff": CUTOFF,
    "random_seed": SEED,
    "stations": extract["stations"],
    "station_names": [extract["antenna_names"][i] for i in extract["stations"]],
    "extract": extract,
    "input_receipts": receipts,
    "groups": {g: survey(source / f"group{g}") for g in ("1", "2")},
}
(out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
for g, r in result["groups"].items():
    print(g, json.dumps({k: v for k, v in r.items() if k != "points"}))
    for name, s in r.get("points", {}).items():
        print(" ", name, json.dumps({k: v for k, v in s.items() if k != "failures"}))
