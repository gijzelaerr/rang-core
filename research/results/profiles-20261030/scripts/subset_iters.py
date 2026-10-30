"""Iterations and converged fraction of the original-arm solve on the probe subsets."""

import json
import sys
from pathlib import Path

import numpy as np

from rangtoy import core_campaign, core_fetch
from rangtoy.core_workflow import core_solve

fetched = sys.argv[1]
arrays0, _ = core_fetch.decode_slice(fetched)
rows = np.asarray(json.loads((Path(fetched) / "result.json").read_text())["rows"])
extra0 = core_campaign.decode_extra(fetched, rows)
pairs = sorted({(int(p), int(q)) for p, q in zip(arrays0["ANTENNA1"], arrays0["ANTENNA2"])})
out = []
for nb, nc in [(1, 2048), (2, 2048), (3, 2048), (6, 512), (6, 1024), (6, 2048)]:
    keep = set(pairs[:nb])
    sel = np.array([(int(p), int(q)) in keep for p, q in zip(arrays0["ANTENNA1"], arrays0["ANTENNA2"])])
    arrays = {k: (v[sel][:, :nc] if v.ndim == 3 else v[sel]) for k, v in arrays0.items()}
    extra = dict(extra0, uvw=extra0["uvw"][sel], chan_freq=extra0["chan_freq"][:nc], chan_width=extra0["chan_width"][:nc])
    state = core_campaign.build_state(arrays, extra)
    m, *_ = core_solve(state, np.zeros_like(state["train"]), 2, 32, 50)
    rec = {"baselines": nb, "channels": nc, "train_cells": int(state["train"].sum()),
           "iterations": m["solver"]["iterations"], "converged_fraction": m["solver"]["converged_fraction"],
           "solve_seconds": m["seconds"]}
    out.append(rec)
    print(json.dumps(rec))
