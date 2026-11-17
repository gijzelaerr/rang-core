"""E2-A gate 3c (research/e2-acceptance.md 6.5, 9.10 and the coordinator's
decisions on it; A0 6.1 row 3c and E2-A's field limit, appendix A): rang's
image-stage images (GeMClean, Stokes I) against WSClean 3.7's of rang's apply
output (`e2_post.py wsclean3c-a-dirty` and `-clean`). Written before any E2-A
image existed; E2-B's scorer (e2_score3c.py) is IQUV and three fields.

    python e2_score3c_a.py R ORACLE_DIR OUT.json [--dirty-only]

R holds rang-run-moved/ (after `restore`) or rang-run/ (`archive`'s copy);
ORACLE_DIR is R/wsclean3c-a (the frozen primary reading) or
R/wsclean3c-a-nosi (`-no-small-inversion`: the second, seen reading, dirty
only, after the primary is scored). Measures, as 6.5 names them for E2-A,
with A0 6.1's 3c tolerances:

1. Dirty L-inf (gated): per output channel and MFS, max |rang dirty -
   WSClean dirty| over the full image, over the peak |I| of WSClean's dirty
   image of that channel; met when <= 1e-6. Reported beside, not gated: the
   same over the inner two-thirds (the coordinator's decision: channel
   smearing towards the edge shows there), with a 5 % border excluded, within
   E2-A's 0.7 deg radius, and the largest per-image median.
2. Compact sources (gated, within the 0.7 deg radius of the image centre,
   E2-A's field limit): candidates are local maxima (box of 2 beams) of the
   mean of both arms' MFS images, >= 10 sigma (1.4826 MAD of WSClean's MFS
   residual over the inner two-thirds), with no other candidate within 5
   beams. Per arm and output channel: the beam fitted to that channel's PSF
   (E1b's convention), residual + model (*) beam, and the Gaussian fixed to
   that beam fitted at the candidate (amplitude and centre free). Flux = sum
   over channels; ratio rang / WSClean; met when the median is within 0.5 %
   of 1 and the robust scatter (1.4826 MAD) <= 1 %; not checked with fewer
   than 3 sources. Reported beside, not gated: the same over the inner
   two-thirds and over the full image (sources too near the edge for the fit
   are counted, not fitted), and the median ratio per radial bin.
3. Reported, not gated (6.5 names only 1 and 2 for E2-A): the spectral index
   of sources >= 50 sigma within 0.7 deg (median |d alpha|, A0's 0.05 shown),
   and off-source |model| over the full image (A0's 1.6 x shown).
Not checked: Q/Q0 and MODEL_DATA against WSClean -predict (not in E2-A's 6.5
row). Not applicable: the unpolarised-source Q, U, V measure (Stokes I).

Stated before reading (9.10): WSClean grids 4,096 channels, GeMClean 512
averaged ones, so rang's image carries more bandwidth smearing towards the
edge; dirty L-inf includes WSClean's small-inversion edge term (A4b).
"""

import itertools
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from e1b_score import _open, fit_cut, fit_psf_beam, restored_cut

RADIUS_DEG = 0.7  # appendix A, E2-A's field limit
DIRTY_TOL = 1e-6
COMPACT = {"median": 0.005, "scatter": 0.01}
RADIAL_BINS_DEG = (0.0, 0.35, 0.7, 1.0, 1.4, 2.5)


def mad(x):
    x = np.asarray(x, float)
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def inner(shape):
    ny, nx = shape
    m = np.zeros(shape, bool)
    m[ny // 6 : ny - ny // 6, nx // 6 : nx - nx // 6] = True
    return m


def radius_deg(h, shape):
    """Distance of every pixel from the reference pixel (the phase centre)."""
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    dx = (xx - (h["CRPIX1"] - 1)) * abs(h["CDELT1"])
    dy = (yy - (h["CRPIX2"] - 1)) * abs(h["CDELT2"])
    return np.hypot(dx, dy)


def rang_images(r):
    """(rang's image directory for the target, its oracle tag, channels_out)."""
    base = r / "rang-run-moved"
    if not base.is_dir():
        base = r / "rang-run"
    summ = json.loads((base / "image" / "summary.json").read_text(encoding="utf-8"))
    cfg = json.loads((base / "config.resolved.json").read_text(encoding="utf-8"))
    (entry,) = summ["images"]
    a = entry["argv"]
    sub = re.split(r"[\\/]", a[a.index("-name") + 1])[-2]
    tag = entry["field"].replace("+", "p").replace("-", "m")
    return base / "image" / sub, tag, int(cfg["image"]["channels_out"])


def same_grid(a, b, what):
    if a[0].shape != b[0].shape:
        raise SystemExit(f"shape differs: {what}")
    for k in ("CRVAL1", "CRVAL2", "CDELT1", "CDELT2", "CRPIX1", "CRPIX2"):
        if not math.isclose(a[1][k], b[1][k], rel_tol=1e-9, abs_tol=1e-12):
            raise SystemExit(f"header {k} differs: {what}")


def dirty_linf(rdir, odir, tag, nch):
    per, worst = {}, 0.0
    prof = {"inner_two_thirds": 0.0, "border5": 0.0, "within_0p7deg": 0.0, "median_max": 0.0}
    for c in [f"{i:04d}" for i in range(nch)] + ["MFS"]:
        r_img = _open(rdir / f"image-{c}-dirty.fits")
        o_img = _open(odir / f"{tag}-dirty-{c}-dirty.fits")
        same_grid(r_img, o_img, c)
        d = np.abs(r_img[0] - o_img[0]) / float(np.max(np.abs(o_img[0])))
        per[c] = float(d.max())
        worst = max(worst, per[c])
        n = d.shape[0]
        b = n // 20
        rad = radius_deg(o_img[1], d.shape)
        for key, v in (("inner_two_thirds", d[inner(d.shape)].max()),
                       ("border5", d[b : n - b, b : n - b].max()),
                       ("within_0p7deg", d[rad <= RADIUS_DEG].max()),
                       ("median_max", np.median(d))):  # fmt: skip
            prof[key] = max(prof[key], float(v))
    return {"max_over_peak": worst, "per_image": per, "tolerance": DIRTY_TOL,
            "met": worst <= DIRTY_TOL, "reported": prof}  # fmt: skip


def channel_set(stem_of, nch):
    out = []
    for i in range(nch):
        stem = stem_of(f"{i:04d}")
        img = _open(Path(f"{stem}-image.fits"))
        out.append({"model": _open(Path(f"{stem}-model.fits"))[0],
                    "resid": _open(Path(f"{stem}-residual.fits"))[0],
                    "beam": fit_psf_beam(_open(Path(f"{stem}-psf.fits"))[0]),
                    "freq": float(img[1]["CRVAL3"])})  # fmt: skip
    return out


def flux_at(ch, x0, y0):
    ix, iy = round(x0), round(y0)
    cut = restored_cut(ch["model"], ch["resid"], ix, iy, ch["beam"])
    yy, xx = np.mgrid[iy - 4 : iy + 5, ix - 4 : ix + 5]
    return float(fit_cut(cut, xx, yy, ch["beam"], float(cut[4, 4]), x0, y0)[0])


def ratio_stats(ratios):
    rec = {"n": len(ratios)}
    if len(ratios):
        rec.update(median=float(np.median(ratios)), robust_scatter=mad(ratios))
    if len(ratios) >= 3:
        rec["met"] = bool(abs(rec["median"] - 1) <= COMPACT["median"]
                          and rec["robust_scatter"] <= COMPACT["scatter"])  # fmt: skip
    else:
        rec["met"] = None  # scatter undefined below 3 sources: not checked
    return rec


def compact(rdir, odir, tag, nch):
    from scipy import ndimage

    r_mfs = _open(rdir / "image-MFS-image.fits")
    o_mfs = _open(odir / f"{tag}-clean-MFS-image.fits")
    o_res = _open(odir / f"{tag}-clean-MFS-residual.fits")[0]
    same_grid(r_mfs, o_mfs, "MFS image")
    h = o_mfs[1]
    bmaj = h["BMAJ"] / abs(h["CDELT2"])
    shape = o_res.shape
    inn = inner(shape)
    rad = radius_deg(h, shape)
    sigma = mad(o_res[inn])
    mean = 0.5 * (r_mfs[0] + o_mfs[0])
    size = max(3, int(2 * bmaj) | 1)
    peaks = (mean == ndimage.maximum_filter(mean, size=size)) & (mean >= 10 * sigma)
    ys, xs = np.nonzero(peaks)
    cand = list(zip(xs.tolist(), ys.tolist(), mean[ys, xs].tolist(), strict=True))
    iso = [(x, y, v) for x, y, v in cand
           if not any((x2, y2) != (x, y) and math.hypot(x2 - x, y2 - y) < 5 * bmaj
                      for x2, y2, _ in cand)]  # fmt: skip
    r_ch = channel_set(lambda c: rdir / f"image-{c}", nch)
    o_ch = channel_set(lambda c: odir / f"{tag}-clean-{c}", nch)
    margin = 4 + max(math.ceil(5 * ch["beam"][0]) for ch in r_ch + o_ch)
    src, edge = [], 0
    for x, y, v in iso:
        if not (margin <= x < shape[1] - margin and margin <= y < shape[0] - margin):
            edge += 1
            continue
        fr = [flux_at(c, float(x), float(y)) for c in r_ch]
        fo = [flux_at(c, float(x), float(y)) for c in o_ch]
        rec = {"x": x, "y": y, "radius_deg": float(rad[y, x]), "snr": v / sigma,
               "in_0p7deg": bool(rad[y, x] <= RADIUS_DEG), "in_inner_two_thirds": bool(inn[y, x]),
               "ratio": sum(fr) / sum(fo), "rang_jy": fr, "wsclean_jy": fo}  # fmt: skip
        if v >= 50 * sigma and min(fr) > 0 and min(fo) > 0:
            lnu = np.log([c["freq"] for c in o_ch])
            ar = float(np.polyfit(lnu, np.log(fr), 1)[0])
            ao = float(np.polyfit(lnu, np.log(fo), 1)[0])
            rec.update(alpha_rang=ar, alpha_wsclean=ao, dalpha=ar - ao)
        src.append(rec)
    sets = {
        "within_0p7deg": [s["ratio"] for s in src if s["in_0p7deg"]],
        "inner_two_thirds": [s["ratio"] for s in src if s["in_inner_two_thirds"]],
        "full_image": [s["ratio"] for s in src],
    }
    radial = []
    for lo, hi in itertools.pairwise(RADIAL_BINS_DEG):
        x = [s["ratio"] for s in src if lo <= s["radius_deg"] < hi]
        radial.append({"deg": [lo, hi], "n": len(x),
                       "median": float(np.median(x)) if x else None})  # fmt: skip
    da = [abs(s["dalpha"]) for s in src if "dalpha" in s and s["in_0p7deg"]]
    mask = ndimage.binary_dilation(mean > 5 * sigma, iterations=max(1, math.ceil(2 * bmaj)))
    off = {arm: float(sum(np.abs(c["model"][~mask]).sum() for c in chs))
           for arm, chs in (("rang", r_ch), ("wsclean", o_ch))}  # fmt: skip
    return {
        "sigma_jy": sigma, "beam_major_pix": bmaj, "candidates": len(cand),
        "isolated": len(iso), "too_near_edge": edge, "sources": src,
        "gated": ratio_stats(sets["within_0p7deg"]),
        "reported": {k: ratio_stats(v) for k, v in sets.items() if k != "within_0p7deg"},
        "radial": radial,
        "spectral_index_reported": {"n": len(da), "tolerance_a0": 0.05,
                                    "median_abs_dalpha": float(np.median(da)) if da else None},
        "offsource_reported": {**off, "tolerance_a0": 1.6,
                               "ratio": off["rang"] / off["wsclean"] if off["wsclean"] > 0 else None},
    }  # fmt: skip


def main(r, odir, out_path, *flags):
    r, odir = Path(r), Path(odir)
    dirty_only = "--dirty-only" in flags
    rdir, tag, nch = rang_images(r)
    res = {"oracle": str(odir), "rang_images": str(rdir), "channels_out": nch,
           "dirty_only": dirty_only, "dirty": dirty_linf(rdir, odir, tag, nch),
           "caveat": "WSClean grids 4,096 channels, GeMClean 512 averaged (9.10)"}  # fmt: skip
    gates = {"dirty_linf": res["dirty"]["met"]}
    if not dirty_only:
        res["compact"] = compact(rdir, odir, tag, nch)
        gates["compact_ratio"] = res["compact"]["gated"]["met"]
    gates["q_over_q0"] = "not checked"
    gates["model_data_predict"] = "not checked"
    checked = [v for v in gates.values() if isinstance(v, bool)]
    res.update(gates=gates, met_where_checked=bool(checked) and all(checked),
               not_checked=[k for k, v in gates.items() if not isinstance(v, bool)])  # fmt: skip
    Path(out_path).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("gates", "met_where_checked", "not_checked")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
