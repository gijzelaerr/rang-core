# SPDX-License-Identifier: MIT
"""P2 and P2b of research/gate3c-averaging.md (amendment A2): GeMClean's own
averaging predictor against its own images of the noiseless ring sky.

    python p2_measure.py dirty SKY.json BASE_PREFIX AVG_PREFIX OUT.json
    python p2_measure.py clean SKY.json BASE_PREFIX AVG_PREFIX OUT.json

dirty: MFS dirty pixel at each point's true pixel, averaged / unaveraged,
mean per ring, against AVG's report `averaging.imaging_loss` (tolerance 2e-3).
clean: e2_score3c_a's fixed-beam flux summed over the 8 channels, averaged /
unaveraged, mean per ring, against `averaging.restored_loss` (A1's p',
tolerance 3e-3) and, reported, `imaging_loss`.
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "e2-acceptance-scripts"))
from e1b_score import _open  # noqa: E402
from e2_score3c_a import channel_set, flux_at  # noqa: E402

NCH = 8


def main(mode, sky, base, avg, out):
    comps = json.loads(Path(sky).read_text(encoding="utf-8"))
    rep = json.loads(Path(f"{avg}-report.json").read_text(encoding="utf-8"))["averaging"]
    key = "imaging_loss" if mode == "dirty" else "restored_loss"
    pred = [1 - x["loss"] for x in rep[key]][:4]
    pred_dirty = [1 - x["loss"] for x in rep["imaging_loss"]][:4]
    if mode == "dirty":
        b, h = _open(Path(f"{base}-MFS-dirty.fits"))[:2]
        a = _open(Path(f"{avg}-MFS-dirty.fits"))[0]
        n = b.shape[0]
        ratios = [a[n // 2 + c["dy"], n // 2 + c["dx"]] / b[n // 2 + c["dy"], n // 2 + c["dx"]]
                  for c in comps]  # fmt: skip
        tol = 2e-3
    else:
        rb = channel_set(lambda s: f"{base}-{s}", NCH)
        ra = channel_set(lambda s: f"{avg}-{s}", NCH)
        n = rb[0]["model"].shape[0]
        ratios = []
        for c in comps:
            x, y = float(n // 2 + c["dx"]), float(n // 2 + c["dy"])
            fb = sum(flux_at(ch, x, y) for ch in rb)
            fa = sum(flux_at(ch, x, y) for ch in ra)
            ratios.append(fa / fb)
        tol = 3e-3
    rings = sorted({c["ring_arcsec"] for c in comps})
    rows = []
    for i, r in enumerate(rings):
        v = [q for q, c in zip(ratios, comps, strict=True) if c["ring_arcsec"] == r]
        m = float(np.mean(v))
        rows.append({"ring_arcsec": r, "n": len(v), "measured_mean": m,
                     "measured_min": float(np.min(v)), "measured_max": float(np.max(v)),
                     "predicted": pred[i], "predicted_dirty": pred_dirty[i],
                     "diff": m - pred[i], "met": abs(m - pred[i]) <= tol})  # fmt: skip
    res = {"mode": mode, "tolerance": tol, "factor": rep["used"], "met": all(r["met"] for r in rows),
           "rings": rows, "report": rep}  # fmt: skip
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    for r in rows:
        print(f"{r['ring_arcsec']:8.1f}\" meas {r['measured_mean']:.5f} pred {r['predicted']:.5f} "
              f"(dirty {r['predicted_dirty']:.5f}) diff {r['diff']:+.5f} {'met' if r['met'] else 'MISS'}")  # fmt: skip
    print("met" if res["met"] else "not met")


if __name__ == "__main__":
    main(*sys.argv[1:6])
