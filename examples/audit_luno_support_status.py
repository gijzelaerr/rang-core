"""Post-hoc reporting audit for the LUNO processed-support survey.

Re-evaluates the same extraction and tabulates the native anchored_response status
for every supported bin by rank label, per field and gain point. The frozen survey
only compared status 3 with the underidentified label, and it passed drop_h=H, which
makes the kernel's kept curvature zero. This records every status for that frozen
call and for the original survey's anchored_response(H, 0, 0, 0) call.
"""

import collections
import json
import pathlib
import sys

import numpy as np
from rangtoy.core_influence import anchored_response, training_normals

source = pathlib.Path(sys.argv[1])
GRID, CUTOFF, SEED = (2, 32), 1e-10, 20261029  # as frozen in survey_luno_support.py


def gain_points(nbins):
    identity = np.broadcast_to(np.eye(2), (nbins, 4, 2, 2)).astype(np.complex128)
    rng = np.random.default_rng(SEED)
    noise = rng.standard_normal((nbins, 4, 2, 2, 2))
    return {
        "identity": np.ascontiguousarray(identity),
        "random_seed20261029": identity + 0.1 * (noise[..., 0] + 1j * noise[..., 1]),
    }


result = {}
for group in ("1", "2"):
    directory = source / f"group{group}"
    a1, a2, time, flag, weight, model = (
        np.load(directory / f"{n}.npy")
        for n in ("antenna1", "antenna2", "time", "flag", "weight", "model")
    )
    integration = np.searchsorted(np.unique(time), time)
    nchan_bins = flag.shape[1] // GRID[1]
    nbins = (int(integration.max()) // GRID[0] + 1) * nchan_bins
    train = ~flag.any(-1) & (weight > 0).all(-1) & np.isfinite(model).all(-1)
    rows, channels = np.nonzero(train)
    bins = (integration[rows] // GRID[0]) * nchan_bins + channels // GRID[1]
    p, q = a1[rows], a2[rows]
    models = model[rows, channels].astype(np.complex128).reshape(-1, 2, 2)
    weights = weight[rows, channels].astype(np.float64)
    result[group] = {}
    for name, gains in gain_points(nbins).items():
        h, _, counts = training_normals(
            gains, models, np.zeros_like(models), weights, p, q, bins
        )
        table = collections.Counter()
        for b in np.flatnonzero(counts):
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
                else "over_rank"
            )
            zero = np.zeros(32)
            for call, drop in (
                ("frozen(H,0,H,0)", h[b]),
                ("original(H,0,0,0)", 0 * h[b]),
            ):
                status = anchored_response(h[b], zero, drop, zero, gains[b], active)
                table[f"{call} {label} status{status['native_status']}"] += 1
        result[group][name] = dict(sorted(table.items()))
print(json.dumps(result, indent=1))
