"""E3 visibility-domain measures on CARACal's calibrated calibrator split
(research/e3-caracal.md section 5). Runs in WSL with the CARACal venv
(python-casacore, numpy):

    python e3_vis_measures.py MS OUT.json [--column CORRECTED_DATA]

Per field and scan: Stokes I, Q, U, V per channel as the mean over unflagged
rows of CORRECTED_DATA, with E2's convention (e1b_score._stokes4: I=(XX+YY)/2,
Q=(XX-YY)/2, U=(XY+YX)/2, V=(XY-YX)/2j, real parts), then per 100 MHz bin
1.0-1.65 GHz (bins with >= 10 % of cells unflagged): I, p = |Q+iU|/I,
chi = arg(Q+iU)/2 in degrees, leakage sqrt(Q^2+U^2+V^2)/I, and for J1939-6342
the ratio of I to SR2016 (rang.fluxstd, the same model rang uses).
CASA applycal with parang=True leaves CORRECTED_DATA in the sky frame.
"""

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
from casacore.tables import table

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("fluxstd", ROOT / "python" / "rang" / "fluxstd.py")
fluxstd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fluxstd)

# 100 MHz bins 1.0-1.6 GHz and the 50 MHz bin 1.6-1.65 GHz (section 5: "1.0-1.65 GHz")
EDGES = np.append(np.arange(1.0e9, 1.6e9 + 1, 1.0e8), 1.65e9)
CHUNK = 2000


def field_scan_stokes(ms, fid, scan, column):
    t = table(ms, ack=False)
    sel = t.query(f"FIELD_ID=={fid} && SCAN_NUMBER=={scan} && ANTENNA1!=ANTENNA2")
    n = sel.nrows()
    acc = None
    cnt = None
    for r0 in range(0, n, CHUNK):
        nr = min(CHUNK, n - r0)
        v = sel.getcol(column, r0, nr).astype(np.complex128)
        f = sel.getcol("FLAG", r0, nr) | sel.getcol("FLAG_ROW", r0, nr)[:, None, None]
        ok = ~f.any(-1)  # a cell counts if all four correlations are unflagged
        st = np.stack([(v[..., 0] + v[..., 3]) / 2, (v[..., 0] - v[..., 3]) / 2,
                       (v[..., 1] + v[..., 2]) / 2, (v[..., 1] - v[..., 2]) / 2j], -1)
        s = np.where(ok[..., None], st, 0).sum(0)
        c = ok.sum(0)
        acc = s if acc is None else acc + s
        cnt = c if cnt is None else cnt + c
    sel.close()
    t.close()
    return acc, cnt, n


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ms")
    p.add_argument("out")
    p.add_argument("--column", default="CORRECTED_DATA")
    a = p.parse_args()
    names = list(table(a.ms + "/FIELD", ack=False).getcol("NAME"))
    freq = table(a.ms + "/SPECTRAL_WINDOW", ack=False).getcol("CHAN_FREQ")[0]
    m = table(a.ms, ack=False)
    pairs = sorted(set(zip(m.getcol("FIELD_ID").tolist(), m.getcol("SCAN_NUMBER").tolist())))
    m.close()
    res = {"ms": a.ms, "column": a.column, "fields": names, "per_scan": []}
    for fid, scan in pairs:
        acc, cnt, nrows = field_scan_stokes(a.ms, fid, scan, a.column)
        bins = []
        for lo, hi in zip(EDGES[:-1], EDGES[1:]):
            ch = (freq >= lo) & (freq < hi)
            frac = cnt[ch].sum() / (nrows * ch.sum())
            rec = {"lo_hz": lo, "hi_hz": hi, "unflagged": float(frac)}
            if frac >= 0.10:
                i, q, u, v = (acc[ch, k].sum() / cnt[ch].sum() for k in range(4))
                i, q, u, v = i.real, q.real, u.real, v.real
                rec.update(I=i, Q=q, U=u, V=v, p=float(np.hypot(q, u) / i),
                           chi_deg=float(np.degrees(np.arctan2(u, q)) / 2),
                           leak=float(np.sqrt(q * q + u * u + v * v) / i))
                if names[fid] == "J1939-6342":
                    nu = freq[ch][cnt[ch] > 0]
                    w = cnt[ch][cnt[ch] > 0]
                    model = fluxstd.flux("J1939-6342", nu, "Stevens-Reynolds 2016")[:, 0]
                    rec["I_over_SR2016"] = float(i / ((w * model).sum() / w.sum()))
            bins.append(rec)
        res["per_scan"].append({"field": names[fid], "scan": scan, "rows": nrows, "bins": bins})
        print(names[fid], scan, nrows, flush=True)
    Path(a.out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
