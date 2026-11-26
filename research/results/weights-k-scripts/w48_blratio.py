"""#48 diagnostic (post hoc, after the I gate's first read; research/weights-48.md section 9 A2): does
the R estimate (stokes_v clipped, variance over a scan) take up slowly varying V sky as noise?

    python w48_blratio.py CAL_MS FIELD OUT.json [CHANBIN]

On the dumps of even dump pairs only, per baseline and CHANBIN block: R's variance
(`rang.reweight.estimate_rows`, the stage defaults with `statistic: clipped`, `fit` = even-pair
dumps) against the dump-difference variance (median |d|^2 / ln 2 of d = (V_2k - V_2k+1)/sqrt(2) over
the even pairs k, which cancels anything constant over 8 s). R reports 2 var(V) with var the per-part
variance, which is E|V - <V>|^2, the same quantity as E|d|^2, so the ratio is R / sigma_d^2. (The
first run divided by 2 sigma_d^2 and read 0.51-0.52; corrected before the outcome was worded.) Reported per baseline-length bin: median ratio and count of baselines.
Flat near 1 means R tracks the thermal noise; rising on short baselines means it takes up sky.
"""

import json
import math
import sys
import time
import warnings
from pathlib import Path

import numpy as np

XY, YX = 1, 2
EDGES = (0, 150, 500, 1000, 2000, 4000, 8000, 1e9)


def main(cal_ms, field, out, chanbin="16"):
    from rang import core_ms, reweight

    t0 = time.perf_counter()
    cb = int(chanbin)
    sys.path.insert(0, str(Path(__file__).parent))
    import w48_real

    fid = w48_real._field_id(cal_ms, field)
    with core_ms.open_table(f"{cal_ms}/ANTENNA") as t:
        nant = t.nrows
    nbl = nant * (nant - 1) // 2
    with core_ms.open_table(cal_ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == fid)
        times, scans = t.getcol("TIME")[rows], t.getcol("SCAN_NUMBER")[rows]
        a1, a2 = t.getcol("ANTENNA1")[rows], t.getcol("ANTENNA2")[rows]
        uvw = t.getcol("UVW")[rows]
        nchan = t.getcol("FLAG", 0, 1).shape[1]
        nb = -(-nchan // cb)
        _, even = w48_real.pairs_of(times, scans)
        settings = reweight.Settings(mode="stokes_v", chanbin=cb, statistic="clipped")

        def read(name, r, chans):
            return t.getcol_rows(name, r, chans=chans)

        gid, var, _ = reweight.estimate_rows(read, rows, settings, nchan, fit=even,
                                             chans_for_scan=lambda n: 128)  # fmt: skip
        lo, hi = np.minimum(a1, a2), np.maximum(a1, a2)
        b = lo * nant - lo * (lo + 1) // 2 + (hi - lo - 1)
        cross = lo != hi
        r_var = np.full((nbl, nb), np.nan)
        sums = {}
        for s in np.unique(scans):
            m = np.flatnonzero((scans == s) & cross)
            g = gid[m]
            # one group per (scan, baseline): take each baseline's group of this scan
            r_var_s = np.full((nbl, nb), np.nan)
            r_var_s[b[m]] = var[g]
            ut, dump = np.unique(times[m], return_inverse=True)
            dump = dump.reshape(-1)
            d2s = []
            for k in range(0, len(ut) // 2, 2):  # even pairs only
                ia, ib = m[dump == 2 * k], m[dump == 2 * k + 1]
                da, db = t.getcol_rows("CORRECTED_DATA", rows[ia]), t.getcol_rows("CORRECTED_DATA", rows[ib])
                fa, fb = t.getcol_rows("FLAG", rows[ia]), t.getcol_rows("FLAG", rows[ib])
                va = np.full((nbl, nchan), np.nan + 0j, np.complex64)
                vb = va.copy()
                va[b[ia]] = (da[..., XY] - da[..., YX]) / 2j
                vb[b[ib]] = (db[..., XY] - db[..., YX]) / 2j
                bad = np.ones((nbl, nchan), bool)
                bad2 = bad.copy()
                bad[b[ia]] = fa[..., XY] | fa[..., YX]
                bad2[b[ib]] = fb[..., XY] | fb[..., YX]
                d2 = (np.abs(va - vb) ** 2 / 2.0).astype(np.float32)
                d2[bad | bad2] = np.nan
                d2s.append(d2)
            if not d2s:
                continue
            e = np.stack(d2s)  # (pairs, nbl, nchan)
            sig = np.full((nbl, nb), np.nan)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                for j in range(nb):
                    x = np.moveaxis(e[:, :, j * cb : (j + 1) * cb], 0, 1).reshape(nbl, -1)
                    sig[:, j] = np.nanmedian(x, 1) / math.log(2)
            ratio = r_var_s / sig
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                per_bl = np.nanmedian(ratio, 1)
            sums[int(s)] = per_bl
            r_var = np.where(np.isfinite(r_var), r_var, r_var_s)
        length = np.full(nbl, np.nan)
        length[b[cross]] = np.hypot(uvw[cross, 0], uvw[cross, 1])
    per_bl = np.nanmedian(np.stack(list(sums.values())), 0)
    bins = []
    for x0, x1 in zip(EDGES[:-1], EDGES[1:], strict=True):
        m = (length >= x0) & (length < x1) & np.isfinite(per_bl)
        if m.any():
            bins.append({"from_m": x0, "to_m": x1 if x1 < 1e9 else None, "baselines": int(m.sum()),
                         "median_ratio": float(np.median(per_bl[m])),
                         "p16": float(np.percentile(per_bl[m], 16)),
                         "p84": float(np.percentile(per_bl[m], 84))})  # fmt: skip
    rec = {"cal_ms": cal_ms, "field": field, "chanbin": cb, "bins": bins,
           "all_median": float(np.nanmedian(per_bl)), "seconds": time.perf_counter() - t0}  # fmt: skip
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
