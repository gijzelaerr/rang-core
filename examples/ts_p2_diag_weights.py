"""TS-P2 real track, post hoc diagnostic (research/ts-p2.md 10.3, not a gate):
the uninjected residual's DFT time-mean at the positions and the snapshot
sigma of a few intervals, with the MS's weights and with every nonzero
Stokes I weight set to one (E2-A imaged with -unit-weights).

    python examples/ts_p2_diag_weights.py MS TRUTH OUT_JSON
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
from rang import core_model, core_ms
from rang import lightcurve as lc


def main(argv=None):
    ms, truth_path, out = (argv or sys.argv[1:])[:3]
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    freq, _, centre = core_model.band(ms, 0)
    lm = np.array(
        [lc.lm_from_radec(math.radians(s["ra_deg"]), math.radians(s["dec_deg"]), *centre)
         for s in truth["sources"]])  # fmt: skip
    rows = core_model.selected_rows(ms, 0)
    flux = {"ms": [], "unit": []}
    sig = {"ms": [], "unit": []}
    with core_ms.open_table(ms) as t:
        times = t.getcol_rows("TIME", rows)
        unique = np.unique(times)
        for k, when in enumerate(unique):
            sel = np.sort(rows[times == when])
            uvw, vis, w = lc._residual(
                t, sel, "DATA", "MODEL_DATA", "WEIGHT_SPECTRUM", len(freq)
            )
            u = (w > 0).astype(np.float32)
            for key, wt in (("ms", w), ("unit", u)):
                flux[key].append(lc.dft(uvw, freq, vis, wt, lm)[0])
                if k % 90 == 0:
                    sig[key].append(
                        lc.robust_sigma(lc.snapshot(uvw, freq, vis, wt, 2048, 2.0))
                    )
    names = [s["name"] for s in truth["sources"]]
    res = {
        key: {
            "mean_mjd": dict(
                zip(names, (np.mean(flux[key], 0) * 1e3).round(4).tolist(), strict=True)
            ),
            "sigma_snapshot_mjy_intervals_0_90_180_270_360": (np.array(sig[key]) * 1e3)
            .round(4)
            .tolist(),
        }
        for key in flux
    }
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res))


if __name__ == "__main__":
    main()
