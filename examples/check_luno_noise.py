"""Test which LUNO column matches the empirical visibility noise (pinned container).

For unflagged cross cells of MAIN_1 row chunk 0, the real and imaginary parts of the
adjacent-channel difference d = V[c+1] - V[c] of DATA are divided by the noise each
hypothesis predicts for d, and the scaled MAD of the result is reported. A
hypothesis that matches the data gives about 1 (1934-638 is a point source at phase
centre, so adjacent channels cancel the sky). Hypotheses, per visibility and per
real/imaginary part:
  sigma_std:    std = SIGMA_SPECTRUM
  sigma_invvar: std = 1/sqrt(SIGMA_SPECTRUM)
  weight_invvar: std = 1/sqrt(WEIGHT_SPECTRUM)
"""

import json
import pathlib
import sys

import numcodecs
import numpy as np

inputs, sigma_dir = (pathlib.Path(x) / "MAIN" / "MAIN_1" for x in sys.argv[1:3])
slice_dir = pathlib.Path(sys.argv[3]) / "MAIN" / "MAIN_1"
TILES = [int(t) for t in sys.argv[4].split(",")]


def load(root, column, key):
    meta = json.loads((root / column / ".zarray").read_text())
    if meta.get("filters") or "O" in meta["dtype"]:
        raise ValueError(f"refusing {column}")
    raw = numcodecs.Blosc().decode((root / column / key).read_bytes())
    full = np.frombuffer(raw, dtype=np.dtype(meta["dtype"])).reshape(meta["chunks"])
    rows = min(meta["chunks"][0], meta["shape"][0])
    return full[:rows]


a1, a2 = load(slice_dir, "ANTENNA1", "0"), load(slice_dir, "ANTENNA2", "0")
cross = (a1 != a2) & ~load(slice_dir, "FLAG_ROW", "0")
result = {"tiles": TILES}
for tile in TILES:
    key = f"0.{tile}.0"
    data = load(inputs, "DATA", key)[cross].astype(np.complex128)
    sigma = load(sigma_dir, "SIGMA_SPECTRUM", key)[cross].astype(np.float64)
    weight = load(slice_dir, "WEIGHT_SPECTRUM", key)[cross].astype(np.float64)
    flag = load(slice_dir, "FLAG", key)[cross]
    pair = ~flag[:, 1:] & ~flag[:, :-1] & (sigma[:, 1:] > 0) & (sigma[:, :-1] > 0)
    pair &= (weight[:, 1:] > 0) & (weight[:, :-1] > 0)
    d = data[:, 1:] - data[:, :-1]
    stds = {
        "sigma_std": (sigma, lambda x: x),
        "sigma_invvar": (sigma, lambda x: 1 / np.sqrt(x)),
        "weight_invvar": (weight, lambda x: 1 / np.sqrt(x)),
    }
    out = {"pairs_per_corr": pair.sum(axis=(0, 1)).tolist()}
    for name, (column, to_std) in stds.items():
        s = to_std(column)
        scale = np.sqrt(s[:, 1:] ** 2 + s[:, :-1] ** 2)
        per_corr = []
        for c in range(4):
            z = (d[..., c] / scale[..., c])[pair[..., c]]
            per_corr.append(
                [
                    float(1.4826 * np.median(np.abs(x - np.median(x))))
                    for x in (z.real, z.imag)
                ]
            )
        out[name + "_scaledMAD_real_imag_by_corr"] = per_corr
    result[f"tile{tile}"] = out
print(json.dumps(result, indent=1))
