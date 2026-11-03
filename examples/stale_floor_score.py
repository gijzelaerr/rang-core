"""One row for a run: the report's cycles and stop, and the model and residual with the added source removed.

Usage: stale_floor_score.py PREFIX ADDED_JY OUT_JSONL
"""

import json
import sys

import numpy as np
from astropy.io import fits

prefix, added, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
model = fits.getdata(prefix + "-model.fits").squeeze()
resid = fits.getdata(prefix + "-residual.fits").squeeze()
with open(prefix + "-report.json", encoding="utf-8") as f:
    run = json.load(f)["run"]
n = model.shape[0]
rest = model.copy()
source = None
if added > 0:
    at = np.unravel_index(np.abs(model).argmax(), model.shape)
    source = {
        "pixel_from_centre": [int(at[0]) - n // 2, int(at[1]) - n // 2],
        "jy": float(model[at]),
    }
    rest[at] = 0
inner = resid[n // 4 : 3 * n // 4, n // 4 : 3 * n // 4]
row = {
    "name": prefix.rsplit("/", 1)[-1],
    "added_jy": added,
    "major_cycles": run["major_cycles"],
    "components": run["components"],
    "stop": run["stop"],
    "cycle_peaks_jy": [c["peak_start"] for c in run["cycles"]],
    "cycle_stops": [c["stop"] for c in run["cycles"]],
    "model_pixels": int(np.count_nonzero(model)),
    "source": source,
    "off_source_abs_jy": float(np.abs(rest).sum()),
    "off_source_flux_jy": float(rest.sum()),
    "residual_inner_peak_ujy": float(np.abs(inner).max() * 1e6),
    "residual_inner_rms_ujy": float(inner.std() * 1e6),
}
print(
    json.dumps(
        {k: v for k, v in row.items() if k not in ("cycle_peaks_jy", "cycle_stops")}
    ),
    flush=True,
)
with open(out, "a", encoding="utf-8") as f:
    f.write(json.dumps(row) + "\n")
