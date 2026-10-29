"""Offline numeric decode of the bounded LUNO calibrator probe (run in the pinned container).

Refuses object dtypes and any filter; only Blosc/None compressors. Prints a JSON summary.
"""

import json
import pathlib
import sys

import numcodecs
import numpy as np

root = pathlib.Path(sys.argv[1])


def load(array_dir, chunk):
    meta = json.loads((root / array_dir / ".zarray").read_text())
    if meta.get("filters") or "O" in meta["dtype"]:
        raise ValueError(f"refusing {array_dir}: filters/object dtype")
    comp = meta.get("compressor")
    raw = (root / array_dir / chunk).read_bytes()
    if comp:
        if comp["id"] != "blosc":
            raise ValueError(f"unexpected compressor {comp}")
        raw = numcodecs.Blosc().decode(raw)
    arr = np.frombuffer(raw, dtype=np.dtype(meta["dtype"])).reshape(
        meta["chunks"], order=meta["order"]
    )
    # Trim zarr edge padding to the real array extent.
    idx = [int(i) for i in chunk.split(".")]
    sl = tuple(
        slice(0, min(c, s - i * c))
        for c, s, i in zip(meta["chunks"], meta["shape"], idx)
    )
    return arr[sl], meta


groups = []
for g in range(20):
    a = json.loads((root / f"MAIN/MAIN_{g}/.zattrs").read_text())
    groups.append(
        {
            "group": g,
            "field": a.get("FIELD_ID"),
            "scan": a.get("SCAN_NUMBER"),
            "ddid": a.get("DATA_DESC_ID"),
        }
    )

corr, _ = load("POLARIZATION/POLARIZATION_0/CORR_TYPE", "0.0")
phase, _ = load("FIELD/FIELD_0/PHASE_DIR", "0.0.0")
freq, _ = load("SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ", "0.0")
aflag, _ = load("ANTENNA/ANTENNA_0/FLAG_ROW", "0")
pos, _ = load("ANTENNA/ANTENNA_0/POSITION", "0.0")
trange, _ = load("OBSERVATION/OBSERVATION_0/TIME_RANGE", "0.0")
a1, m1 = load("MAIN/MAIN_0/ANTENNA1", "0")
a2, _ = load("MAIN/MAIN_0/ANTENNA2", "0")
t, _ = load("MAIN/MAIN_0/TIME", "0")
frow, _ = load("MAIN/MAIN_0/FLAG_ROW", "0")
w, _ = load("MAIN/MAIN_0/WEIGHT", "0.0")
s, _ = load("MAIN/MAIN_0/SIGMA", "0.0")
ws, _ = load("MAIN/MAIN_0/WEIGHT_SPECTRUM", "0.8.0")
ss, _ = load("MAIN/MAIN_0/SIGMA_SPECTRUM", "0.8.0")
fl, _ = load("MAIN/MAIN_0/FLAG", "0.8.0")

cross = a1 != a2
ants = np.union1d(a1[cross], a2[cross])
unflagged = ~fl & ~frow[:, None, None] & cross[:, None, None]
supported = unflagged & (ws > 0)
per_ant = {}
for ant in ants:
    rows = cross & ((a1 == ant) | (a2 == ant))
    per_ant[int(ant)] = int(supported[rows].all(axis=-1).sum())
all_four = supported.all(axis=-1)
ra = np.degrees(phase[:, 0, 0]) % 360
dec = np.degrees(phase[:, 0, 1])
lengths = np.sqrt(((pos[:, None, :] - pos[None, :, :]) ** 2).sum(-1))
summary = {
    "groups": groups,
    "corr_type": corr.tolist(),
    "field_ra_dec_deg": [
        [round(float(r), 5), round(float(d), 5)] for r, d in zip(ra, dec)
    ],
    "chan_freq_mhz": [
        float(freq[0, 0] / 1e6),
        float(freq[0, -1] / 1e6),
        freq.shape[-1],
    ],
    "tile_freq_mhz": [float(freq[0, 1024] / 1e6), float(freq[0, 1151] / 1e6)],
    "antenna_rows": int(aflag.size),
    "antenna_flag_rows": int(aflag.sum()),
    "max_baseline_m": float(lengths.max()),
    "observation_time_range_s": float(trange[0, 1] - trange[0, 0]),
    "chunk_rows": int(a1.size),
    "chunk_unique_times": int(np.unique(t).size),
    "chunk_time_span_s": float(t.max() - t.min()),
    "cross_participating_antennas": int(ants.size),
    "flag_row_fraction": float(frow.mean()),
    "flag_fraction_cross": float(fl[cross].mean()),
    "weight_row_unique_first": np.unique(w)[:5].tolist(),
    "sigma_row_unique_first": np.unique(s)[:5].tolist(),
    "weight_spectrum_positive_per_corr": [
        int((ws[cross][..., c] > 0).sum()) for c in range(4)
    ],
    "sigma_spectrum_positive_per_corr": [
        int((ss[cross][..., c] > 0).sum()) for c in range(4)
    ],
    "weight_spectrum_quantiles_per_corr": [
        np.quantile(ws[cross][..., c], [0, 0.5, 1]).tolist() for c in range(4)
    ],
    "all_four_supported_cells": int(all_four.sum()),
    "cross_cells": int(cross.sum() * ws.shape[1]),
    "antennas_with_zero_all_four_support": [a for a, n in per_ant.items() if n == 0],
    "min_max_per_antenna_all_four_support": [
        min(per_ant.values()),
        max(per_ant.values()),
    ],
}
print(json.dumps(summary, indent=1))
