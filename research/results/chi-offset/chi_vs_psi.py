"""Chi against parallactic angle per integration (research/chi-offset.md 4.2),
read-only on any MS.

    python chi_vs_psi.py MS DATA_COL FLAG_COL FIELD SCAN RECEPTOR_DEG OUT.json [LO_HZ HI_HZ]

Per integration of FIELD/SCAN, over LO-HI (default 1.3-1.5 GHz): the
unit-weight mean of each correlation over cells whose four correlations are
unflagged (e2_rows_b.py's estimator), Stokes I, Q, U, V (real parts), chi;
psi at the array (mean over the antennas of rang's CASA-frame parallactic
angle); and the feed-frame q_f, u_f with P undone at a = psi + RECEPTOR_DEG:
(q_f + i u_f) = (q + i u) exp(-2 i a). q_f is the parallel hands' Q after
K, G, B, which no cross-hand term touches.
"""

import json
import sys
from pathlib import Path

import numpy as np
from rang import cal_pol, core_ms

BLOCK = 2000


def main(argv):
    ms, col, fcol, field, scan, rdeg, out = argv[:7]
    lo, hi = (float(argv[7]), float(argv[8])) if len(argv) > 8 else (1.3e9, 1.5e9)
    scan, rdeg = int(scan), float(rdeg)
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ"))[0]
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        fid = [str(n) for n in t.getcol("NAME")].index(field)
    cb = (freq >= lo) & (freq <= hi)
    acc = {}
    ants = set()
    with core_ms.open_table(ms) as t:
        nrow = t.nrows
        for r0 in range(0, nrow, BLOCK):
            k = min(BLOCK, nrow - r0)
            sel = (np.asarray(t.getcol("SCAN_NUMBER", r0, k)) == scan) & (
                np.asarray(t.getcol("FIELD_ID", r0, k)) == fid
            )
            a1 = np.asarray(t.getcol("ANTENNA1", r0, k))
            a2 = np.asarray(t.getcol("ANTENNA2", r0, k))
            sel &= a1 != a2
            if not sel.any():
                continue
            tm = np.asarray(t.getcol("TIME", r0, k))[sel]
            ants.update(a1[sel].tolist())
            ants.update(a2[sel].tolist())
            d = np.asarray(t.getcol(col, r0, k))[sel][:, cb]
            f = np.asarray(t.getcol(fcol, r0, k), bool)[sel][:, cb]
            fr = np.asarray(t.getcol("FLAG_ROW", r0, k), bool)[sel]
            good = ~f.any(-1) & ~fr[:, None]
            for tt in np.unique(tm):
                m = tm == tt
                g = good[m]
                s = (d[m] * g[..., None]).sum((0, 1))
                e = acc.setdefault(float(tt), [np.zeros(4, complex), 0, 0])
                e[0] += s
                e[1] += int(g.sum())
                e[2] += int(g.size)
    times = np.array(sorted(acc))
    used = np.array(sorted(ants))
    _, q = cal_pol.angle_table_at(ms, times, used, fid, "casa", receptor_angle=0.0)
    psi = np.degrees(np.angle(np.exp(1j * q[:, used]).mean(1)))
    rows = []
    for i, tt in enumerate(times):
        s, n, tot = acc[tt]
        if n == 0:
            continue
        v = s / n
        ii = ((v[0] + v[3]) / 2).real
        qq = ((v[0] - v[3]) / 2).real / ii
        uu = ((v[1] + v[2]) / 2).real / ii
        vv = ((v[1] - v[2]) / 2j).real / ii
        a = np.radians(psi[i] + rdeg)
        zf = (qq + 1j * uu) * np.exp(-2j * a)
        rows.append({"time": tt, "psi_deg": float(psi[i]), "frac": n / tot, "I": float(ii),
                     "q": float(qq), "u": float(uu), "v": float(vv),
                     "p": float(np.hypot(qq, uu)),
                     "chi_deg": float(np.degrees(0.5 * np.arctan2(uu, qq))),
                     "q_f": float(zf.real), "u_f": float(zf.imag),
                     "chi_f_deg": float(np.degrees(0.5 * np.angle(zf)))})  # fmt: skip
    res = {"ms": ms, "column": col, "flag": fcol, "field": field, "scan": scan,
           "receptor_deg": rdeg, "band_hz": [lo, hi], "integrations": rows}  # fmt: skip
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    for r in rows:
        print(
            f"{r['psi_deg']:8.2f} p {r['p']:.4f} chi {r['chi_deg']:7.2f} "
            f"q_f {r['q_f']:+.4f} u_f {r['u_f']:+.4f} frac {r['frac']:.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
