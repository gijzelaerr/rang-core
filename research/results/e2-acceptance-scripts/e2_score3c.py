"""E2-B gate 3c (research/e2-acceptance.md 6.5; A0 6.1, appendix A): rang's
image-stage images (GeMClean) against WSClean 3.7's of rang's CORRECTED_DATA
at the same settings, per imaged field. Written and run on the development
dry run before it read an E2-B image.

    python e2_score3c.py R ORACLE_DIR OUT.json

R holds rang-run-moved/ (the rang run directory moved by `restore`);
ORACLE_DIR is R/wsclean3c (as committed: MS weights) or R/wsclean3c-unit
(matched: unit weights, as rang's -unit-weights). Measures, fixed here:

1. Dirty L-inf: per output channel and MFS, per Stokes I, Q, U, V,
   max |rang dirty - WSClean dirty| over the image, over the peak |I| of
   WSClean's dirty image of that channel. Gate: max <= 1e-6. Reported
   beside (not gated): the same max with a 5 % border excluded, over the
   inner two-thirds, and the largest per-image median.
2. Compact sources: candidates are local maxima (box of 2 beams) of the mean
   of both arms' MFS I images, at least 10 sigma (sigma: 1.4826 MAD of
   WSClean's MFS I residual over the inner two-thirds), inside the inner
   two-thirds, with no other candidate within 5 beams. Per arm and output
   channel: the restoring beam fitted to that channel's PSF (E1b's
   convention, WSClean 3.7's method), residual + model (*) beam, and the
   Gaussian fixed to that beam fitted at the candidate (amplitude and centre
   free). Flux = sum over channels; ratio rang / WSClean. Gate: median within
   0.5 % of 1, robust scatter (1.4826 MAD) <= 1 %, pooled over the fields;
   not checked with fewer than 3 sources (the scatter is then undefined).
3. Spectral index: sources >= 50 sigma; alpha per arm from a straight line
   in log S against log nu over the output channels; gate median |d alpha|
   <= 0.05 (pooled).
4. Off-source |model|: sum over output channels of |model I| outside the
   source mask (mean MFS I of both arms > 5 sigma, dilated by 2 beams); gate
   rang <= 1.6 x WSClean's, per field.
5. Unpolarised source (J1939-6342): per Stokes Q, U, V, the rms of the MFS
   image over the inner two-thirds and max |P| within 3 beams of the I peak;
   gate rang <= 1.2 x WSClean's, both measures, every Stokes.
6. Q/Q0 (A0's visibility-domain objective): not checked here (it needs both
   models predicted through one gridder on the MS); reported as not checked.

Met = every checked gate met; with 6 unchecked the gate is reported as
"met where checked", never as met.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from e1b_score import _open, fit_cut, fit_psf_beam, restored_cut

STOKES = ("I", "Q", "U", "V")
UNPOLARISED = "J1939-6342"


def mad(x):
    x = np.asarray(x, float)
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def fields(r):
    """[(field name, rang image prefix dir, oracle tag)] from the image summary."""
    summ = json.loads((r / "rang-run-moved" / "image" / "summary.json").read_text())
    cfg = json.loads((r / "rang-run-moved" / "config.resolved.json").read_text())
    im = cfg["image"]
    names = list(dict.fromkeys(n for role in im["fields"] for n in cfg["fields"][role]))
    dirs = {}
    for e in summ["images"]:
        a = e["argv"]
        dirs[Path(a[a.index("-name") + 1]).parent.name] = True
    out = []
    for n in names:
        d = n.replace("+", "_")
        if d not in dirs:
            raise SystemExit(f"no rang image directory for {n}: {sorted(dirs)}")
        out.append(
            (
                n,
                r / "rang-run-moved" / "image" / d,
                n.replace("+", "p").replace("-", "m"),
            )
        )
    return out, int(im["channels_out"])


def inner(shape):
    ny, nx = shape
    m = np.zeros(shape, bool)
    m[ny // 6 : ny - ny // 6, nx // 6 : nx - nx // 6] = True
    return m


def dirty_linf(rdir, odir, tag, nch):
    worst, rec = 0.0, {}
    prof = {"border5": 0.0, "inner": 0.0, "median_max": 0.0}
    for c in [f"{i:04d}" for i in range(nch)] + ["MFS"]:
        wi = _open(odir / f"{tag}-dirty-{c}-I-dirty.fits")
        peak = float(np.max(np.abs(wi[0])))
        for p in STOKES:
            r_img = _open(rdir / f"image-{c}-{p}-dirty.fits")
            o_img = _open(odir / f"{tag}-dirty-{c}-{p}-dirty.fits")
            if r_img[0].shape != o_img[0].shape:
                raise SystemExit(f"shape differs: {c} {p}")
            for k in ("CRVAL1", "CRVAL2", "CDELT1", "CDELT2", "CRPIX1", "CRPIX2"):
                if not math.isclose(
                    r_img[1][k], o_img[1][k], rel_tol=1e-9, abs_tol=1e-12
                ):
                    raise SystemExit(f"header {k} differs: {c} {p}")
            d = np.abs(r_img[0] - o_img[0]) / peak
            v = float(d.max())
            rec[f"{c}-{p}"] = v
            worst = max(worst, v)
            n = d.shape[0]
            for key, m in (("border5", n // 20), ("inner", n // 6)):
                prof[key] = max(prof[key], float(d[m : n - m, m : n - m].max()))
            prof["median_max"] = max(prof["median_max"], float(np.median(d)))
    return {"max_over_peak": worst, "per_image": rec, "met": worst <= 1e-6,
            "reported_profile": prof}  # fmt: skip


def channel_set(where, stem_fmt, nch):
    out = []
    for i in range(nch):
        stem = where / stem_fmt.format(c=f"{i:04d}")
        img = _open(Path(f"{stem}-I-image.fits"))
        out.append({
            "model": _open(Path(f"{stem}-I-model.fits"))[0],
            "resid": _open(Path(f"{stem}-I-residual.fits"))[0],
            "beam": fit_psf_beam(_open(Path(f"{stem}-psf.fits"))[0]),
            "freq": float(img[1]["CRVAL3"]),
        })  # fmt: skip
    return out


def flux_at(ch, x0, y0):
    ix, iy = round(x0), round(y0)
    cut = restored_cut(ch["model"], ch["resid"], ix, iy, ch["beam"])
    yy, xx = np.mgrid[iy - 4 : iy + 5, ix - 4 : ix + 5]
    return float(fit_cut(cut, xx, yy, ch["beam"], float(cut[4, 4]), x0, y0)[0])


def score_field(name, rdir, odir, tag, nch):
    from scipy import ndimage

    r_mfs = _open(rdir / "image-MFS-I-image.fits")
    o_mfs = _open(odir / f"{tag}-clean-MFS-I-image.fits")
    o_res = _open(odir / f"{tag}-clean-MFS-I-residual.fits")[0]
    h = o_mfs[1]
    bmaj = h["BMAJ"] / abs(h["CDELT2"])
    inn = inner(o_res.shape)
    sigma = mad(o_res[inn])
    mean = 0.5 * (r_mfs[0] + o_mfs[0])
    size = max(3, int(2 * bmaj) | 1)
    peaks = (
        (mean == ndimage.maximum_filter(mean, size=size)) & (mean >= 10 * sigma) & inn
    )
    ys, xs = np.nonzero(peaks)
    cand = list(zip(xs.tolist(), ys.tolist(), mean[ys, xs].tolist(), strict=True))
    iso = []
    for x, y, v in cand:
        near = [1 for x2, y2, _ in cand
                if (x2, y2) != (x, y) and math.hypot(x2 - x, y2 - y) < 5 * bmaj]  # fmt: skip
        if not near:
            iso.append((x, y, v))
    r_ch = channel_set(rdir, "image-{c}", nch)
    o_ch = channel_set(odir, tag + "-clean-{c}", nch)
    src = []
    for x, y, v in iso:
        fr = [flux_at(c, float(x), float(y)) for c in r_ch]
        fo = [flux_at(c, float(x), float(y)) for c in o_ch]
        rec = {"x": x, "y": y, "snr": v / sigma, "ratio": sum(fr) / sum(fo),
               "rang_jy": fr, "wsclean_jy": fo}  # fmt: skip
        if v >= 50 * sigma and min(fr) > 0 and min(fo) > 0:
            lnu = np.log([c["freq"] for c in o_ch])
            ar = float(np.polyfit(lnu, np.log(fr), 1)[0])
            ao = float(np.polyfit(lnu, np.log(fo), 1)[0])
            rec.update(alpha_rang=ar, alpha_wsclean=ao, dalpha=ar - ao)
        src.append(rec)
    mask = mean > 5 * sigma
    rr = math.ceil(2 * bmaj)
    yy, xx = np.mgrid[-rr : rr + 1, -rr : rr + 1]
    mask = ndimage.binary_dilation(mask, structure=(xx**2 + yy**2) <= rr * rr)
    off = {arm: float(sum(np.abs(c["model"][~mask]).sum() for c in chs))
           for arm, chs in (("rang", r_ch), ("wsclean", o_ch))}  # fmt: skip
    out = {"sigma_jy": sigma, "beam_major_pix": bmaj, "candidates": len(cand),
           "isolated": len(iso), "sources": src, "offsource_abs_model_jy": off,
           "offsource_ratio": off["rang"] / off["wsclean"] if off["wsclean"] > 0 else None}  # fmt: skip
    out["offsource_met"] = (
        out["offsource_ratio"] is not None and out["offsource_ratio"] <= 1.6
    )
    if name == UNPOLARISED:
        py, px = np.unravel_index(int(np.argmax(o_mfs[0])), o_mfs[0].shape)
        yy, xx = np.mgrid[: o_mfs[0].shape[0], : o_mfs[0].shape[1]]
        near = np.hypot(xx - px, yy - py) <= 3 * bmaj
        pol = {}
        for p in ("Q", "U", "V"):
            a = _open(rdir / f"image-MFS-{p}-image.fits")[0]
            b = _open(odir / f"{tag}-clean-MFS-{p}-image.fits")[0]
            m = {"rms_inner": [float(np.sqrt(np.mean(a[inn] ** 2))),
                               float(np.sqrt(np.mean(b[inn] ** 2)))],
                 "peak_near_source": [float(np.max(np.abs(a[near]))),
                                      float(np.max(np.abs(b[near])))]}  # fmt: skip
            m["met"] = all(v[0] <= 1.2 * v[1] for v in m.values())
            pol[p] = m
        out["unpolarised"] = pol
        out["unpolarised_met"] = all(v["met"] for v in pol.values())
    return out


def main(r, odir, out_path):
    r, odir = Path(r), Path(odir)
    flist, nch = fields(r)
    res = {"oracle": str(odir), "fields": {}}
    for name, rdir, tag in flist:
        f = score_field(name, rdir, odir, tag, nch)
        f["dirty"] = dirty_linf(rdir, odir, tag, nch)
        res["fields"][name] = f
    allsrc = [s for f in res["fields"].values() for s in f["sources"]]
    ratios = np.array([s["ratio"] for s in allsrc])
    da = np.array([abs(s["dalpha"]) for s in allsrc if "dalpha" in s])
    comp = {"n": len(allsrc)}
    if len(ratios):
        comp.update(median=float(np.median(ratios)), robust_scatter=mad(ratios))
    if len(ratios) >= 3:  # scatter undefined below 3 sources: not checked
        comp["met"] = bool(
            abs(comp["median"] - 1) <= 0.005 and comp["robust_scatter"] <= 0.01
        )
    else:
        comp["met"] = None
    spec = {
        "n": len(da),
        "median_abs_dalpha": float(np.median(da)) if len(da) else None,
    }
    spec["met"] = bool(spec["median_abs_dalpha"] <= 0.05) if len(da) else None
    gates = {
        "dirty_linf": all(f["dirty"]["met"] for f in res["fields"].values()),
        "compact_ratio": comp["met"],
        "spectral_index": spec["met"],
        "offsource_model": all(f["offsource_met"] for f in res["fields"].values()),
        "unpolarised_quv": res["fields"].get(UNPOLARISED, {}).get("unpolarised_met"),
        "q_over_q0": "not checked",
    }
    checked = [v for k, v in gates.items() if k != "q_over_q0" and v is not None]
    res.update(compact=comp, spectral_index=spec, gates=gates,
               met_where_checked=bool(checked) and all(checked),
               not_checked=[k for k, v in gates.items() if v is None or v == "not checked"])  # fmt: skip
    Path(out_path).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("compact", "spectral_index", "gates",
                                          "met_where_checked", "not_checked")}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
