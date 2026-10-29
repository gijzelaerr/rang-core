"""Compare SIGMA_SPECTRUM with WEIGHT_SPECTRUM on one LUNO probe tile (pinned container).

Read-only check of the observer's statement that SIGMA_SPECTRUM keeps the original
noise while QuartiCal modified WEIGHT_SPECTRUM. Uses the tile fetched by
tools/flagging/fetch-luno-probe.sh (MAIN_0, row chunk 0, channels 1024:1152).
"""

import json
import pathlib
import sys

import numcodecs
import numpy as np

root = pathlib.Path(sys.argv[1]) / "MAIN" / "MAIN_0"


def load(column, key):
    meta = json.loads((root / column / ".zarray").read_text())
    if meta.get("filters") or "O" in meta["dtype"]:
        raise ValueError(f"refusing {column}")
    raw = numcodecs.Blosc().decode((root / column / key).read_bytes())
    return np.frombuffer(raw, dtype=np.dtype(meta["dtype"])).reshape(meta["chunks"])


a1, a2 = load("ANTENNA1", "0"), load("ANTENNA2", "0")
frow = load("FLAG_ROW", "0")
flag = load("FLAG", "0.8.0")
w = load("WEIGHT_SPECTRUM", "0.8.0").astype(np.float64)
s = load("SIGMA_SPECTRUM", "0.8.0").astype(np.float64)
row_w, row_s = load("WEIGHT", "0.0"), load("SIGMA", "0.0")
cross = (a1 != a2) & ~frow
good = cross[:, None, None] & ~flag
names = ("XX", "XY", "YX", "YY")


def q(x):
    return np.quantile(x, [0, 0.05, 0.5, 0.95, 1]).round(6).tolist() if x.size else []


result = {
    "cells_unflagged_cross": int(good[..., 0].sum()),
    "row_WEIGHT_unique_first": np.unique(row_w)[:5].tolist(),
    "row_SIGMA_unique_first": np.unique(row_s)[:5].tolist(),
}
for c, name in enumerate(names):
    wc, sc = w[..., c][good[..., c]], s[..., c][good[..., c]]
    positive = sc > 0
    result[name] = {
        "sigma_spectrum_quantiles": q(sc),
        "weight_spectrum_quantiles": q(wc),
        "sigma_positive_fraction": float(positive.mean()) if sc.size else None,
        # If SIGMA_SPECTRUM is a standard deviation, 1/sigma^2 is the original weight.
        "w_times_sigma2_quantiles": q(wc[positive] * sc[positive] ** 2),
        # If it is an inverse variance (observer's wording), w/sigma is the ratio.
        "w_over_sigma_quantiles": q(wc[positive] / sc[positive]),
        "sigma_unique_count": int(np.unique(sc).size),
    }
print(json.dumps(result, indent=1))
