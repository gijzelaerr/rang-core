"""Issue #55 gate G3 (research/apply-reweight.md section 4): E2-N, held out.

    python rw_g3.py CAL_MS RAW_MS OUT.json

CAL_MS is a calibrated E2-N (read only: CORRECTED_DATA, FLAG); RAW_MS the
original e2n.ms (read only: its WEIGHT_SPECTRUM, which `calwt: false` leaves
as it is); both hold the same rows. apply-calwt's measure N: per scored field
(the target ASKAPJ1745, J1744-5144) and scan, Stokes V = (XY - YX)/(2i) of
CORRECTED_DATA; dumps 2k and 2k+1 of a baseline form pair k, d = (V_2k -
V_2k+1)/sqrt(2); estimation pairs are even k, evaluation pairs odd k. sigma^2
per (baseline, 16-channel block, scan) = median |d|^2 / ln 2 over the
estimation cells; on the evaluation cells S(w) = sum w^2 |d|^2 / (sum w)^2 and
e(w) = sqrt(S(w)/S(1/sigma^2)). Arms: F raw, U unity, R the stage's weights
(`rang.reweight.estimate`, stokes_v, mad, the defaults), estimated on the
dumps of the estimation pairs only (`fit`), so no evaluation dump enters R.
"""

import json
import math
import sys
import time

import numpy as np
from rang import core_ms, reweight

FIELDS = ("ASKAPJ1745", "J1744-5144")
BLOCK = 16
XY, YX = 1, 2
CHANS_PER_READ = 128


def v_weight(ws):
    a, b = ws[..., XY].astype(np.float64), ws[..., YX].astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        w = 4.0 / (1.0 / a + 1.0 / b)
    return np.where((a > 0) & (b > 0), w, 0.0)


def main(cal_ms, raw_ms, out):
    t0 = time.perf_counter()
    settings = reweight.Settings(mode="stokes_v")
    arms = ("F", "U", "R")
    result = {
        "cal_ms": cal_ms,
        "raw_ms": raw_ms,
        "settings": settings.__dict__,
        "fields": {},
    }
    with core_ms.open_table(f"{cal_ms}/FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    with core_ms.open_table(f"{cal_ms}/ANTENNA") as t:
        nant = t.nrows
    nbl = nant * (nant - 1) // 2
    with core_ms.open_table(cal_ms) as t, core_ms.open_table(raw_ms) as r:
        if t.nrows != r.nrows:
            raise SystemExit("CAL_MS and RAW_MS differ in rows")
        fid, scan, times = (
            t.getcol("FIELD_ID"),
            t.getcol("SCAN_NUMBER"),
            t.getcol("TIME"),
        )
        if not np.array_equal(times, r.getcol("TIME")):
            raise SystemExit("CAL_MS and RAW_MS differ in TIME")
        nchan = t.getcol("FLAG", 0, 1).shape[1]
        blk = np.arange(nchan) // BLOCK
        a1all, a2all = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")

        def read(name, rows, chans):
            return t.getcol_rows(name, rows, chans=chans)

        for name in FIELDS:
            f = names.index(name)
            sel = np.flatnonzero(fid == f)
            sums = {a: [0, 0.0, 0.0] for a in (*arms, "ideal")}
            qw = {a: [] for a in arms}
            for sc in np.unique(scan[sel]):
                rows = sel[scan[sel] == sc]
                rows = rows[np.argsort(times[rows], kind="stable")]
                ut, dump = np.unique(times[rows], return_inverse=True)
                fit = (dump // 2) % 2 == 0  # the dumps of estimation pairs (even k)
                group, var = reweight.estimate(read, rows, settings, nchan, fit=fit,
                                               chans_per_read=CHANS_PER_READ)  # fmt: skip
                wr = reweight.weights_of(
                    var, group, nchan, settings.chanbin
                )  # (row, chan, 4)
                lo = np.minimum(a1all[rows], a2all[rows])
                hi = np.maximum(a1all[rows], a2all[rows])
                cross = lo != hi
                b = lo * nant - lo * (lo + 1) // 2 + (hi - lo - 1)

                def dense(idx, values, fill, cross=cross, b=b):
                    out = np.full((nbl, *values.shape[1:]), fill, values.dtype)
                    keep = cross[idx]
                    out[b[idx][keep]] = values[keep]
                    return out

                est, ev, evw = [], [], {a: [] for a in arms}
                for k in range(len(ut) // 2):
                    ia, ib = (
                        np.flatnonzero(dump == 2 * k),
                        np.flatnonzero(dump == 2 * k + 1),
                    )
                    da, db = (
                        t.getcol_rows("CORRECTED_DATA", rows[ia]),
                        t.getcol_rows("CORRECTED_DATA", rows[ib]),
                    )
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
                    oka = dense(ia, ~(fa[..., XY] | fa[..., YX]), False)
                    okb = dense(ib, ~(fb[..., XY] | fb[..., YX]), False)
                    ok = oka & okb
                    d2 = (np.abs(va - vb) ** 2 / 2.0).astype(np.float32)
                    d2[~ok] = np.nan
                    if k % 2 == 0:
                        est.append(d2)
                        continue
                    ev.append(d2)
                    wfa = dense(
                        ia, v_weight(r.getcol_rows("WEIGHT_SPECTRUM", rows[ia])), 0.0
                    )
                    wfb = dense(
                        ib, v_weight(r.getcol_rows("WEIGHT_SPECTRUM", rows[ib])), 0.0
                    )
                    wra = dense(ia, v_weight(wr[ia]), 0.0)
                    wrb = dense(ib, v_weight(wr[ib]), 0.0)
                    evw["F"].append((0.5 * (wfa + wfb)).astype(np.float32))
                    evw["U"].append(np.ones_like(d2))
                    evw["R"].append((0.5 * (wra + wrb)).astype(np.float32))
                if not est or not ev:
                    continue
                e = np.stack(est).reshape(len(est), nbl, nchan // BLOCK, BLOCK)
                sig = np.nanmedian(
                    np.moveaxis(e, 0, 2).reshape(nbl, nchan // BLOCK, -1), axis=2
                )
                sig_c = (sig / math.log(2))[:, blk]
                for i, d2 in enumerate(ev):
                    good = np.isfinite(d2) & np.isfinite(sig_c) & (sig_c > 0)
                    dd = d2[good].astype(np.float64)
                    wi = 1.0 / sig_c[good]
                    s = sums["ideal"]
                    s[0] += dd.size
                    s[1] += wi.sum()
                    s[2] += (wi * wi * dd).sum()
                    for a in arms:
                        w = evw[a][i][good].astype(np.float64)
                        g = w > 0
                        s = sums[a]
                        s[0] += int(g.sum())
                        s[1] += w[g].sum()
                        s[2] += (w[g] ** 2 * dd[g]).sum()
                        if a != "U":
                            qw[a].append(
                                np.stack([w[g], w[g] * dd[g]]).astype(np.float32)
                            )
            S = {a: v[2] / v[1] ** 2 if v[1] > 0 else math.nan for a, v in sums.items()}
            fr = {"cells_evaluated": sums["ideal"][0], "S_ideal": S["ideal"]}
            for a in arms:
                fr[a] = {
                    "cells": sums[a][0],
                    "S": S[a],
                    "e": math.sqrt(S[a] / S["ideal"]),
                }
                if a != "U" and qw[a]:
                    q = np.concatenate(qw[a], axis=1)
                    edges = np.quantile(q[0], [0.2, 0.4, 0.6, 0.8])
                    which = np.searchsorted(edges, q[0], side="right")
                    overall = float(q[1].mean())
                    fr[a]["quintiles"] = [
                        float(q[1][which == j].mean() / overall) for j in range(5)
                    ]
            fr["R_vs_F"] = fr["R"]["e"] / fr["F"]["e"] - 1
            result["fields"][name] = fr
    result["seconds"] = time.perf_counter() - t0
    with open(out, "w") as fh:
        json.dump(result, fh, indent=1)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
