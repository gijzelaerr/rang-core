"""apply-calwt (#48), research/apply-calwt.md section 5: weight scores on E2-N.

    python calwt_score.py MS F OUT.json                  # arms F (WEIGHT_SPECTRUM now) and U (unity)
    python calwt_score.py MS T OUT.json --save-weights W.npz
    python calwt_score.py MS O OUT.json --compare-weights W.npz   # CASA's weights against T's

Per scored field (the target ASKAPJ1745 and J1744-5144) and scan: Stokes
V = (XY - YX)/(2i) of CORRECTED_DATA; consecutive dumps 2k and 2k+1 of a
baseline form pair k, d = (V_2k - V_2k+1)/sqrt(2), on cells unflagged in XY
and YX at both dumps; pair k is an estimation pair for even k, an evaluation
pair for odd k. sigma^2 per (baseline, 16-channel block, scan) = median |d|^2
/ ln 2 over its estimation cells (|d|^2 of a complex Gaussian is
exponential). On the evaluation cells, for each arm's weights w (V's weight
4 / (1/w_XY + 1/w_YX), the mean over the pair's two dumps),
S(w) = sum w^2 |d|^2 / (sum w)^2, and the ideal arm w = 1/sigma^2;
e(w) = sqrt(S(w) / S(ideal)). Quintiles: mean of |d|^2 w per quintile of w,
over the overall mean.
"""

import argparse
import json
import math
import time

import numpy as np

from rang import core_ms

FIELDS = ("ASKAPJ1745", "J1744-5144")
BLOCK = 16
XY, YX = 1, 2
SAVE_EVERY = 50  # pairs of the target whose first dump's weights are kept for the oracle


def field_ids(ms):
    with core_ms.open_table(f"{ms}/FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    return {n: names.index(n) for n in FIELDS}


def v_weight(ws):
    a, b = ws[..., XY].astype(np.float64), ws[..., YX].astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        w = 4.0 / (1.0 / a + 1.0 / b)
    return np.where((a > 0) & (b > 0), w, 0.0)


def dumps_of(t, rows):
    times = t.getcol_rows("TIME", rows)
    order = np.argsort(times, kind="stable")
    rows, times = rows[order], times[order]
    return np.split(rows, np.flatnonzero(np.diff(times) > 0) + 1)


def read_dump(t, rows, nant, nbl, nchan, want_w):
    """Dense (nbl, nchan) V, ok and (optionally) the four weights, cross baselines only."""
    a1, a2 = t.getcol_rows("ANTENNA1", rows), t.getcol_rows("ANTENNA2", rows)
    cross = a1 != a2
    rows, a1, a2 = rows[cross], a1[cross], a2[cross]
    lo, hi = np.minimum(a1, a2), np.maximum(a1, a2)
    b = lo * nant - lo * (lo + 1) // 2 + (hi - lo - 1)  # index of (lo, hi) among nbl
    data = t.getcol_rows("CORRECTED_DATA", rows)
    flag = t.getcol_rows("FLAG", rows)
    v = np.full((nbl, nchan), np.nan + 0j, np.complex64)
    ok = np.zeros((nbl, nchan), bool)
    v[b] = (data[..., XY] - data[..., YX]) / 2j
    ok[b] = ~(flag[..., XY] | flag[..., YX])
    w = None
    raw = None
    if want_w:
        ws = t.getcol_rows("WEIGHT_SPECTRUM", rows)
        w = np.zeros((nbl, nchan))
        w[b] = v_weight(ws)
        raw = (rows, ws)
    return v, ok, w, raw


def score(ms, mode, out, save=None, compare=None):
    t0 = time.perf_counter()
    result = {"ms": ms, "mode": mode, "fields": {}}
    if mode == "O":
        ref = np.load(compare)
        rows = ref["rows"]
        with core_ms.open_table(ms) as t:
            casa = t.getcol_rows("WEIGHT_SPECTRUM", rows).astype(np.float64)
            flag = t.getcol_rows("FLAG", rows)
        mine = ref["ws"].astype(np.float64)
        ok = ~flag & (mine > 0)
        rel = np.abs(casa - mine)[ok] / mine[ok]
        result["oracle"] = {
            "rows": int(len(rows)),
            "cells": int(ok.sum()),
            "max_rel": float(rel.max()),
            "p99_rel": float(np.percentile(rel, 99)),
            "median_rel": float(np.median(rel)),
        }
        json.dump(result, open(out, "w"), indent=1)
        print(json.dumps(result, indent=1))
        return
    arms = ("F", "U") if mode == "F" else ("T",)
    ids = field_ids(ms)
    saved = {"rows": [], "ws": []}
    with core_ms.open_table(f"{ms}/ANTENNA") as t:
        nant = t.nrows
    nbl = nant * (nant - 1) // 2
    with core_ms.open_table(ms) as t:
        fid = t.getcol("FIELD_ID")
        scan = t.getcol("SCAN_NUMBER")
        nchan = t.getcol("FLAG", 0, 1).shape[1]
        if nchan % BLOCK:
            raise SystemExit(f"{nchan} channels: not a multiple of {BLOCK}")
        nblk = nchan // BLOCK
        blk = np.arange(nchan) // BLOCK
        for name, f in ids.items():
            sel = np.flatnonzero(fid == f)
            sums = {a: [0, 0.0, 0.0] for a in (*arms, "ideal")}
            qw = {a: [] for a in arms}
            for sc in np.unique(scan[sel]):
                dumps = dumps_of(t, sel[scan[sel] == sc])
                est, ev, evw = [], [], {a: [] for a in arms}
                for k in range(len(dumps) // 2):
                    want = True
                    va, oka, wa, rawa = read_dump(t, dumps[2 * k], nant, nbl, nchan, want)
                    vb, okb, wb, _ = read_dump(t, dumps[2 * k + 1], nant, nbl, nchan, want)
                    ok = oka & okb
                    d2 = (np.abs(va - vb) ** 2 / 2.0).astype(np.float32)
                    d2[~ok] = np.nan
                    if save and name == FIELDS[0] and k % SAVE_EVERY == 0:
                        saved["rows"].append(rawa[0])
                        saved["ws"].append(rawa[1])
                    if k % 2 == 0:
                        est.append(d2)
                    else:
                        ev.append(d2)
                        w = 0.5 * (wa + wb)
                        for a in arms:
                            evw[a].append(np.ones_like(d2) if a == "U" else w.astype(np.float32))
                if not est or not ev:
                    continue
                e = np.stack(est)  # (P, nbl, nchan)
                pe = e.shape[0]
                e = e.reshape(pe, nbl, nblk, BLOCK)
                sig = np.nanmedian(np.moveaxis(e, 0, 2).reshape(nbl, nblk, -1), axis=2) / math.log(2)
                sig_c = sig[:, blk]  # (nbl, nchan)
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
                        qw[a].append(np.stack([w[g], w[g] * dd[g]]).astype(np.float32))
            S = {a: v[2] / v[1] ** 2 if v[1] > 0 else math.nan for a, v in sums.items()}
            fr = {"cells_evaluated": sums["ideal"][0], "S_ideal": S["ideal"]}
            for a in arms:
                q = np.concatenate(qw[a], axis=1)
                edges = np.quantile(q[0], [0.2, 0.4, 0.6, 0.8])
                which = np.searchsorted(edges, q[0], side="right")
                overall = float(q[1].mean())
                fr[a] = {
                    "cells": sums[a][0],
                    "S": S[a],
                    "e": math.sqrt(S[a] / S["ideal"]),
                    "quintiles": [float(q[1][which == j].mean() / overall) for j in range(5)],
                }
            result["fields"][name] = fr
    if save and saved["rows"]:
        np.savez(save, rows=np.concatenate(saved["rows"]), ws=np.concatenate(saved["ws"]))
        result["saved_rows"] = int(sum(len(r) for r in saved["rows"]))
    result["seconds"] = time.perf_counter() - t0
    json.dump(result, open(out, "w"), indent=1)
    print(json.dumps(result, indent=1))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ms")
    p.add_argument("mode", choices=("F", "T", "O"))
    p.add_argument("out")
    p.add_argument("--save-weights")
    p.add_argument("--compare-weights")
    a = p.parse_args()
    score(a.ms, a.mode, a.out, save=a.save_weights, compare=a.compare_weights)


if __name__ == "__main__":
    main()
