"""#48 measures on real data, held out (research/weights-48.md sections 3-5).

    python w48_real.py weights CAL_MS RAW_MS FIELD ARM OUT.json [CHANBIN]
    python w48_real.py n CAL_MS FIELD OUT.json [CHANBIN]
    python w48_real.py image CAL_MS FIELD OUTDIR [THREADS]
    python w48_real.py sources DIRTY_I.fits CAL_MS FIELD OUT.csv
    python w48_real.py lc CAL_MS FIELD SOURCES.csv OUTDIR

`weights` sets WEIGHT_SPECTRUM and WEIGHT of FIELD's rows in CAL_MS (a calibrated own copy) for
one arm: raw (RAW_MS's WEIGHT_SPECTRUM, as `calwt: false` leaves it), unity (1), rmad and rclip
(`rang.reweight` stokes_v with statistic mad or clipped at the stage defaults, CHANBIN channels
per block, estimated from the dumps of even dump pairs only), calwt (CAL_MS's own after an apply
with `calwt: true`). Every arm then gets weight 0 on the dumps of even pairs, so only held-out
dumps (odd pairs) are scored. Dump pairs: per scan, the sorted unique times 2k and 2k+1 are pair k.

`n` is apply-calwt's measure N on CAL_MS's current weights (held-out pairs only): Stokes V of
CORRECTED_DATA, d = (V_2k - V_2k+1)/sqrt(2); sigma^2 per (baseline, CHANBIN block, scan) =
median |d|^2 / ln 2 over the even pairs; e(w) = sqrt(S(w)/S(1/sigma^2)) over the odd pairs, with
w the mean of the two dumps' V weights. Quintiles of w|d|^2 over its mean.

`image`: GeMClean Stokes V dirty images (-niter 0), 2048 x 2048 at 3 arcsec, natural and Briggs
-0.5; per image the robust rms (1.4826 MAD) of the 16 tiles of a 4 x 4 grid over the inner
1536 x 1536 pixels, and each tile's peak |V|.

`sources`: the 20 brightest peaks (separated by 30 arcsec) within 0.5 deg of the phase centre of
the raw arm's natural Stokes I dirty image, and 20 control positions (seed w48-ctrl) at least
30 arcsec from any pixel above 5 robust sigma. `lc`: rang-core lightcurve --weights ms --no-model
--no-images at those positions (one point per dump; weight-0 dumps come out empty).
"""

import json
import math
import subprocess
import sys
import time
import zlib
from pathlib import Path

import numpy as np

XY, YX = 1, 2
STEP = 4000


def _field_id(ms, field):
    from rang import core_ms

    with core_ms.open_table(f"{ms}/FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    return names.index(field) if field in names else int(field)


def _rows(t, fid):
    f = t.getcol("FIELD_ID")
    return np.flatnonzero(f == fid)


def pairs_of(times, scans):
    """Per row: (pair index k within its scan, whether the dump is in an even pair)."""
    k = np.zeros(len(times), np.int64)
    for s in np.unique(scans):
        m = scans == s
        _, dump = np.unique(times[m], return_inverse=True)
        k[m] = dump.reshape(-1) // 2
    return k, k % 2 == 0


def _runs(rows):
    breaks = np.flatnonzero(np.diff(rows) != 1) + 1
    for run in np.split(rows, breaks):
        for s in range(0, len(run), STEP):
            yield int(run[s]), int(min(STEP, len(run) - s))


def cmd_weights(cal_ms, raw_ms, field, arm, out, chanbin="16"):
    from rang import core_ms, core_ms_write, reweight

    t0 = time.perf_counter()
    fid = _field_id(cal_ms, field)
    rec = {"cal_ms": cal_ms, "field": field, "arm": arm, "chanbin": int(chanbin)}
    with core_ms.open_table(cal_ms) as t:
        rows = _rows(t, fid)
        times, scans = t.getcol("TIME")[rows], t.getcol("SCAN_NUMBER")[rows]
        nchan = t.getcol("FLAG", 0, 1).shape[1]
        _, even = pairs_of(times, scans)
        var = gid = None
        if arm in ("rmad", "rclip"):
            settings = reweight.Settings(mode="stokes_v", chanbin=int(chanbin),
                                         statistic="mad" if arm == "rmad" else "clipped")  # fmt: skip
            settings.check()
            rec["settings"] = settings.__dict__

            def read(name, r, chans):
                return t.getcol_rows(name, r, chans=chans)

            gid, var, filled = reweight.estimate_rows(read, rows, settings, nchan, fit=even,
                                                      chans_for_scan=lambda n: 128)  # fmt: skip
            rec["filled_blocks"] = filled
            rec["blocks_finite"] = float(np.isfinite(var).mean())
    pos = np.full(int(rows.max()) + 1, -1, np.int64)
    pos[rows] = np.arange(len(rows))
    zero_unflagged = cells = 0
    raw = core_ms.open_table(raw_ms) if arm == "raw" else None
    w = core_ms_write.open_table(cal_ms, readonly=False)
    try:
        for start, n in _runs(rows):
            idx = pos[start : start + n]
            flag = w.getcol("FLAG", start, n).astype(bool)
            if arm == "raw":
                ws = raw.getcol("WEIGHT_SPECTRUM", start, n).astype(np.float32)
            elif arm == "unity":
                ws = np.ones(flag.shape, np.float32)
            elif arm == "calwt":
                ws = w.getcol("WEIGHT_SPECTRUM", start, n).astype(np.float32)
            else:
                ws = reweight.weights_of(
                    var, gid[idx], nchan, int(chanbin), flag.shape[2]
                )
            ws[even[idx]] = 0.0
            keep = ~even[idx]
            zero_unflagged += int(np.count_nonzero((ws[keep] == 0) & ~flag[keep]))
            cells += int(np.count_nonzero(~flag[keep]))
            w.putcol("WEIGHT_SPECTRUM", ws, start)
            w.putcol("WEIGHT", reweight.row_weight(ws, flag), start)
            w.flush()
    finally:
        w.close()
        if raw is not None:
            raw.close()
    rec.update(rows=len(rows), heldout_unflagged_cells=cells,
               heldout_unflagged_cells_at_weight_0=zero_unflagged,
               seconds=time.perf_counter() - t0)  # fmt: skip
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec, indent=1))


def v_weight(ws):
    a, b = ws[..., XY].astype(np.float64), ws[..., YX].astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        w = 4.0 / (1.0 / a + 1.0 / b)
    return np.where((a > 0) & (b > 0), w, 0.0)


def cmd_n(cal_ms, field, out, chanbin="16"):
    from rang import core_ms

    t0 = time.perf_counter()
    cb = int(chanbin)
    fid = _field_id(cal_ms, field)
    with core_ms.open_table(f"{cal_ms}/ANTENNA") as t:
        nant = t.nrows
    nbl = nant * (nant - 1) // 2
    sums = {"arm": [0, 0.0, 0.0], "ideal": [0, 0.0, 0.0]}
    q = []
    with core_ms.open_table(cal_ms) as t:
        rows_all = _rows(t, fid)
        scan = t.getcol("SCAN_NUMBER")[rows_all]
        times = t.getcol("TIME")[rows_all]
        a1all, a2all = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        nchan = t.getcol("FLAG", 0, 1).shape[1]
        blk = np.arange(nchan) // cb
        for sc in np.unique(scan):
            rows = rows_all[scan == sc]
            rows = rows[np.argsort(times[scan == sc], kind="stable")]
            ut, dump = np.unique(t.getcol("TIME")[rows], return_inverse=True)
            dump = dump.reshape(-1)
            lo, hi = (
                np.minimum(a1all[rows], a2all[rows]),
                np.maximum(a1all[rows], a2all[rows]),
            )
            cross = lo != hi
            b = lo * nant - lo * (lo + 1) // 2 + (hi - lo - 1)

            def dense(idx, values, fill, cross=cross, b=b):
                o = np.full((nbl, *values.shape[1:]), fill, values.dtype)
                keep = cross[idx]
                o[b[idx][keep]] = values[keep]
                return o

            est, ev, evw = [], [], []
            for k in range(len(ut) // 2):
                ia, ib = (
                    np.flatnonzero(dump == 2 * k),
                    np.flatnonzero(dump == 2 * k + 1),
                )
                da = t.getcol_rows("CORRECTED_DATA", rows[ia])
                db = t.getcol_rows("CORRECTED_DATA", rows[ib])
                fa, fb = (
                    t.getcol_rows("FLAG", rows[ia]),
                    t.getcol_rows("FLAG", rows[ib]),
                )
                va = dense(
                    ia,
                    ((da[..., XY] - da[..., YX]) / 2j).astype(np.complex64),
                    np.nan + 0j,
                )
                vb = dense(
                    ib,
                    ((db[..., XY] - db[..., YX]) / 2j).astype(np.complex64),
                    np.nan + 0j,
                )
                ok = dense(ia, ~(fa[..., XY] | fa[..., YX]), False) & dense(
                    ib, ~(fb[..., XY] | fb[..., YX]), False)  # fmt: skip
                d2 = (np.abs(va - vb) ** 2 / 2.0).astype(np.float32)
                d2[~ok] = np.nan
                if k % 2 == 0:
                    est.append(d2)
                    continue
                ev.append(d2)
                wa = dense(
                    ia, v_weight(t.getcol_rows("WEIGHT_SPECTRUM", rows[ia])), 0.0
                )
                wb = dense(
                    ib, v_weight(t.getcol_rows("WEIGHT_SPECTRUM", rows[ib])), 0.0
                )
                evw.append((0.5 * (wa + wb)).astype(np.float32))
            if not est or not ev:
                continue
            nb = -(-nchan // cb)
            e = np.stack(est)  # (pairs, nbl, nchan)
            sig = np.full((nbl, nb), np.nan)
            for j in range(nb):
                with np.errstate(all="ignore"):
                    import warnings

                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", RuntimeWarning)
                        sig[:, j] = np.nanmedian(
                            np.moveaxis(e[:, :, j * cb : (j + 1) * cb], 0, 1).reshape(
                                nbl, -1
                            ),
                            1,
                        )
            sig_c = (sig / math.log(2))[:, blk]
            for d2, w in zip(ev, evw):
                good = np.isfinite(d2) & np.isfinite(sig_c) & (sig_c > 0)
                dd = d2[good].astype(np.float64)
                wi = 1.0 / sig_c[good]
                s = sums["ideal"]
                s[0] += dd.size
                s[1] += wi.sum()
                s[2] += (wi * wi * dd).sum()
                ww = w[good].astype(np.float64)
                g = ww > 0
                s = sums["arm"]
                s[0] += int(g.sum())
                s[1] += ww[g].sum()
                s[2] += (ww[g] ** 2 * dd[g]).sum()
                q.append(np.stack([ww[g], ww[g] * dd[g]]).astype(np.float32))
    S = {a: v[2] / v[1] ** 2 if v[1] > 0 else math.nan for a, v in sums.items()}
    rec = {"cal_ms": cal_ms, "field": field, "cells_ideal": sums["ideal"][0],
           "cells_arm": sums["arm"][0], "e": math.sqrt(S["arm"] / S["ideal"])}  # fmt: skip
    if q:
        qq = np.concatenate(q, 1)
        edges = np.quantile(qq[0], [0.2, 0.4, 0.6, 0.8])
        which = np.searchsorted(edges, qq[0], side="right")
        overall = float(qq[1].mean())
        rec["quintiles"] = [float(qq[1][which == j].mean() / overall) for j in range(5)]
    rec["seconds"] = time.perf_counter() - t0
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec, indent=1))


def _fits(path):
    from astropy.io import fits

    with fits.open(path) as h:
        return np.asarray(h[0].data, np.float64).squeeze(), h[0].header


def tile_rms(img, inner=1536, grid=4):
    n = img.shape[0]
    a = (n - inner) // 2
    sub = img[a : a + inner, a : a + inner]
    s = inner // grid
    out = []
    for i in range(grid):
        for j in range(grid):
            x = sub[i * s : (i + 1) * s, j * s : (j + 1) * s]
            x = x[np.isfinite(x)]
            med = np.median(x)
            out.append({"rms": float(1.4826 * np.median(np.abs(x - med))),
                        "peak_abs": float(np.abs(x).max())})  # fmt: skip
    return out


def cmd_image(cal_ms, field, outdir, threads="8"):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    fid = _field_id(cal_ms, field)
    rec = {"cal_ms": cal_ms, "field": field, "images": {}}
    for tag, weight in (("natural", ["-weight", "natural"]),
                        ("briggs-0.5", ["-weight", "briggs", "-0.5"])):  # fmt: skip
        name = out / f"v-{tag}"
        t0 = time.perf_counter()
        cmd = [sys.executable, "-m", "rang.gemclean", "-name", str(name), "-field", str(fid),
               "-pol", "V", *weight, "-niter", "0", "-size", "2048", "2048", "-scale", "3asec",
               "-no-update-model-required", "-j", str(threads), cal_ms]  # fmt: skip
        rc = subprocess.run(
            cmd, stdout=open(f"{name}.log", "w"), stderr=subprocess.STDOUT
        ).returncode
        dirty = Path(f"{name}-dirty.fits")
        r = {"rc": rc, "seconds": time.perf_counter() - t0}
        if rc == 0 and dirty.exists():
            img, _ = _fits(dirty)
            r["tiles"] = tile_rms(img)
        rec["images"][tag] = r
    Path(out / "image.json").write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec, indent=1))


def cmd_sources(fits_i, cal_ms, field, out_csv):
    from astropy.wcs import WCS

    img, hdr = _fits(fits_i)
    wcs = WCS(hdr).celestial
    n = img.shape[0]
    med = np.median(img)
    sigma = 1.4826 * np.median(np.abs(img - med))
    scale = abs(hdr["CDELT1"]) * 3600.0
    sep = int(math.ceil(30.0 / scale))
    yy, xx = np.mgrid[0:n, 0:n]
    cy, cx = n // 2, n // 2
    within = np.hypot(yy - cy, xx - cx) * scale <= 0.5 * 3600.0
    work = np.where(within, img, -np.inf)
    picks = []
    while len(picks) < 20:
        i = int(np.argmax(work))
        y, x = divmod(i, n)
        if not np.isfinite(work[y, x]):
            break
        picks.append((y, x, float(img[y, x])))
        work[max(0, y - sep) : y + sep + 1, max(0, x - sep) : x + sep + 1] = -np.inf
    bright = img > 5 * sigma
    from scipy.ndimage import binary_dilation

    near = binary_dilation(bright, iterations=sep)
    rng = np.random.default_rng(zlib.crc32(b"w48-ctrl"))
    ctrl = []
    while len(ctrl) < 20:
        y, x = rng.integers(0, n, 2)
        if within[y, x] and not near[y, x]:
            ctrl.append((int(y), int(x), float(img[y, x])))
    with open(out_csv, "w") as fh:
        fh.write("name,ra_deg,dec_deg\n")
        for tag, pts in (("src", picks), ("ctrl", ctrl)):
            for j, (y, x, _) in enumerate(pts):
                sky = wcs.pixel_to_world(x, y)
                fh.write(f"{tag}{j:02d},{sky.ra.deg:.7f},{sky.dec.deg:.7f}\n")
    meta = {
        "sigma": float(sigma),
        "src_peaks": [p[2] for p in picks],
        "scale_arcsec": scale,
    }
    Path(out_csv).with_suffix(".json").write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps(meta, indent=1))


def cmd_lc(cal_ms, field, sources, outdir):
    t0 = time.perf_counter()
    cmd = [
        sys.executable,
        "-m",
        "rang.core_cli",
        "lightcurve",
        cal_ms,
        "--positions",
        sources,
        "--out",
        outdir,
        "--field",
        str(field),
        "--no-model",
        "--no-images",
        "--weights",
        "ms",
    ]
    rc = subprocess.run(cmd).returncode
    print(json.dumps({"rc": rc, "seconds": time.perf_counter() - t0}))
    sys.exit(rc)


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"weights": cmd_weights, "n": cmd_n, "image": cmd_image, "sources": cmd_sources,
     "lc": cmd_lc}[cmd](*sys.argv[2:])  # fmt: skip
