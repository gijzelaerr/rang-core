"""E2-N's DATA-state check (research/e2n-native.md section 2): A0 2.2's probe
on the converted MS. Run in the WSL katdal venv (python-casacore).

    python e2n_datastate.py MS OUT.json

Per field (J1939-6342, J1331+3030, and for context J1744-5144): the first
800 rows of the field in MS order, the channels whose centres lie in A0's
tile 20, 1391.0-1417.5 MHz; `stats` is A0's (fp_a0_probe_state.py, copied
unchanged): cross-correlation rows, cells with no flagged correlation;
median |XX-YY phase| and its coherence over cells; per row (A0's
"baseline") the phase of the mean XX, |XY|/|XX|, the phase of the mean XY.
Prints the verdict of section 2's rule from J1939-6342's coherence.
"""

import json
import sys

import numpy as np
from casacore.tables import table

TILE = (1391.0e6, 1417.5e6)
NROWS = 800


def stats(cols, a1, a2, fl):
    out = {}
    cross = a1 != a2
    good = ~fl[cross].any(axis=2)
    for name, v in cols.items():
        V = v[cross]
        if good.sum() == 0:
            out[name] = dict(ngood=0)
            continue
        XX, XY, YX, YY = [V[..., i][good] for i in range(4)]
        I = (XX + YY) / 2
        Q = (XX - YY) / 2
        U = (XY + YX) / 2
        S = (XY - YX) / 2j
        d = dict(
            ngood=int(good.sum()),
            nonzero_rows=int(np.count_nonzero(np.abs(V).sum(axis=(1, 2)))),
            med_abs_XX=float(np.median(np.abs(XX))),
            med_abs_YY=float(np.median(np.abs(YY))),
            med_abs_XY=float(np.median(np.abs(XY))),
            mean_I=[float(I.mean().real), float(I.mean().imag)],
            mean_Q=[float(Q.mean().real), float(Q.mean().imag)],
            mean_U=[float(U.mean().real), float(U.mean().imag)],
            mean_V=[float(S.mean().real), float(S.mean().imag)],
            coh_I=float(np.abs(I.mean()) / np.abs(I).mean()),
            xxyy_phase_med_rad=float(np.median(np.abs(np.angle(XX * np.conj(YY))))),
            xxyy_coh=float(np.abs(np.mean(np.exp(1j * np.angle(XX * np.conj(YY)))))),
        )
        phs = []
        for b in range(V.shape[0]):
            gb = good[b]
            if gb.sum() > 10:
                m = V[b, gb].mean(axis=0)
                phs.append(
                    (
                        np.angle(m[0]),
                        np.angle(m[3]),
                        abs(m[1]) / max(abs(m[0]), 1e-20),
                        abs(m[2]) / max(abs(m[3]), 1e-20),
                        np.angle(m[1]),
                        np.angle(m[0] * np.conj(m[3])),
                    )
                )
        if phs:
            p = np.array(phs)
            d.update(
                n_baselines=len(phs),
                bl_XX_phase_std_deg=float(np.degrees(np.std(p[:, 0]))),
                bl_XXYY_phase_std_deg=float(np.degrees(np.std(p[:, 5]))),
                bl_XY_over_XX_med=float(np.median(p[:, 2])),
                bl_YX_over_YY_med=float(np.median(p[:, 3])),
                bl_XY_phase_coh=float(np.abs(np.mean(np.exp(1j * p[:, 4])))),
                bl_XY_phase_mean_deg=float(
                    np.degrees(np.angle(np.mean(np.exp(1j * p[:, 4]))))
                ),
            )
        out[name] = d
    return out


def main(ms, out):
    freq = table(f"{ms}/SPECTRAL_WINDOW", ack=False).getcol("CHAN_FREQ")[0]
    chans = np.flatnonzero((freq >= TILE[0]) & (freq <= TILE[1]))
    names = list(table(f"{ms}/FIELD", ack=False).getcol("NAME"))
    t = table(ms, ack=False)
    fid = t.getcol("FIELD_ID")
    res = {"ms": ms, "channels": [int(chans[0]), int(chans[-1])],
           "freq_hz": [float(freq[chans[0]]), float(freq[chans[-1]])], "fields": {}}  # fmt: skip
    for name in ("J1939-6342", "J1331+3030", "J1744-5144"):
        if name not in names:
            continue
        rows = np.flatnonzero(fid == names.index(name))[:NROWS]
        r0, n = int(rows[0]), int(rows[-1] - rows[0] + 1)
        blc, trc = [int(chans[0]), 0], [int(chans[-1]), 3]
        data = t.getcolslice("DATA", blc, trc, startrow=r0, nrow=n)[rows - r0]
        flag = t.getcolslice("FLAG", blc, trc, startrow=r0, nrow=n)[rows - r0]
        a1 = t.getcol("ANTENNA1", startrow=r0, nrow=n)[rows - r0]
        a2 = t.getcol("ANTENNA2", startrow=r0, nrow=n)[rows - r0]
        res["fields"][name] = {"first_row": r0, "rows": len(rows),
                               "DATA": stats({"DATA": data}, a1, a2, flag)["DATA"]}  # fmt: skip
    coh = res["fields"]["J1939-6342"]["DATA"].get("xxyy_coh")
    res["verdict"] = (None if coh is None else "native, unphased" if coh < 0.5
                      else "observatory-phased" if coh >= 0.9 else "partly phased")  # fmt: skip
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "fields"}))
    for k, v in res["fields"].items():
        d = v["DATA"]
        print(k, {x: d.get(x) for x in ("ngood", "xxyy_phase_med_rad", "xxyy_coh",
              "bl_XX_phase_std_deg", "bl_XY_over_XX_med", "bl_XY_phase_coh",
              "bl_XY_phase_mean_deg")})  # fmt: skip


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
