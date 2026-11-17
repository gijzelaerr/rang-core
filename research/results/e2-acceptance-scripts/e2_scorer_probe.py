"""E2 (post hoc on E1's control, e1-chain.md 8 item 7): where the control
image's channel-flux ratio of 1.03 comes from. Per isolated source and output
channel of an image directory: the frozen fixed-beam fit, the model's summed
components near the source, the residual there, against several truth
conventions (plain mean over input channels; the value at the channel's
centre; the mean weighted by unflagged visibilities per input channel).

    python e2_scorer_probe.py RUN IMAGE_DIR OUT_JSON
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "e1-chain-scripts"))

import e1_score as S
from rang import core_ms


def unflagged_per_channel(ctx):
    rows = ctx.rows(S.TARGET)
    lo, hi = int(rows[0]), int(rows[-1]) + 1
    n = np.zeros(ctx.nchan)
    with core_ms.open_table(ctx.ms) as t:
        for start in range(lo, hi, S.CHUNK):
            m = min(S.CHUNK, hi - start)
            f = t.getcol("FLAG", start, m).any(-1)
            fid = t.getcol("FIELD_ID", start, m)
            n += (~f[fid == ctx.fields[S.TARGET]]).sum(0)
    return n


def main():
    ctx = S.Ctx(sys.argv[1], "full")
    d = Path(sys.argv[2])
    comps = ctx.tj["target_components"]
    rep = json.loads((d / "image-report.json").read_text(encoding="utf-8"))
    nout = len(rep["channels"])
    group = ctx.nchan // nout
    nun = unflagged_per_channel(ctx)
    chans = [S._open(d / f"image-{c:04d}-image.fits") for c in range(nout)]
    models = [S._open(d / f"image-{c:04d}-model.fits")[0] for c in range(nout)]
    resids = [S._open(d / f"image-{c:04d}-residual.fits")[0] for c in range(nout)]
    out = {
        "image_dir": str(d),
        "unflagged_per_input_channel": nun.tolist(),
        "channels": [
            {k: v for k, v in c.items() if k != "input_channels"}
            for c in rep["channels"]
        ],
        "reference_frequency_hz": rep.get("reference_frequency_hz"),
        "sources": [],
    }
    for k in S.ISOLATED:
        c = comps[k]
        s_nu = c["flux"] * (ctx.freq / c["ref_freq_hz"]) ** c["alpha"]
        g = s_nu.reshape(nout, group)
        w = nun.reshape(nout, group)
        plain = g.mean(1)
        weighted = (g * w).sum(1) / np.maximum(w.sum(1), 1)
        centre = np.array(
            [c["flux"] * (ch["central_hz"] / c["ref_freq_hz"]) ** c["alpha"]
             for ch in rep["channels"]]
        )  # fmt: skip
        rec = {"index": k, "flux": c["flux"], "alpha": c["alpha"],
               "plain": plain.tolist(), "fit": [], "model_r3": [], "resid0": []}  # fmt: skip
        rec["weighted_over_plain"] = (weighted / plain).tolist()
        rec["centre_over_plain"] = (centre / plain).tolist()
        for ci in range(nout):
            img, h, wcs = chans[ci]
            x, y = wcs.celestial.world_to_pixel_values(c["ra_deg"], c["dec_deg"])
            ix, iy = round(float(x)), round(float(y))
            yy, xx = np.mgrid[-3:4, -3:4]
            disk = (xx**2 + yy**2) <= 9
            msum = float(models[ci][iy - 3 : iy + 4, ix - 3 : ix + 4][disk].sum())
            rec["fit"].append(S.fit_point(img, h, wcs, c["ra_deg"], c["dec_deg"])[0])
            rec["model_r3"].append(msum)
            rec["resid0"].append(float(resids[ci][iy, ix]))
        out["sources"].append(rec)
    # Summary over the 4.3 selection (truth MFS >= 50 sigma of the control MFS
    # image is applied by the caller; here: sources with flux >= 5 mJy).
    sel = [r for r in out["sources"] if r["flux"] >= 5e-3]
    for key in ("fit", "model_r3"):
        m = np.array([np.array(r[key]) / np.array(r["plain"]) for r in sel])
        out[f"median_{key}_over_plain_per_channel"] = np.median(m, 0).tolist()
        tot = np.array([sum(r[key]) / sum(r["plain"]) for r in sel])
        out[f"median_{key}_ratio_frozen_sum"] = float(np.median(tot))
    S.e1_run.write_json(sys.argv[3], out)
    print(
        json.dumps({k: v for k, v in out.items() if k.startswith("median")}, indent=1)
    )


if __name__ == "__main__":
    main()
