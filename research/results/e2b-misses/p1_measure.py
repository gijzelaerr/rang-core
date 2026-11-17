"""P1-a and P1-b (research/e2b-misses.md 9.15): the new
`cal_pol.parallactic_angle_casa` on A1's field rows against casacore's K
(A1c) and A1b's CASA applycal probe.

    python p1_measure.py MINI_MS A1B_CASA_DIR A1C_CASA_DIR OUT_JSON
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "python"))
sys.path.insert(0, str(HERE))
from a1c_rang import RECEPTOR, extract, wrap  # noqa: E402

TOL = 2e-7


def main(mini, a1b_dir, a1c_dir, out_json):
    from rang import cal_pol, core_ms

    mini = Path(mini)
    with core_ms.open_table(mini) as t:
        c = {k: t.getcol(k) for k in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID")}
    with core_ms.open_table(mini / "ANTENNA") as t:
        xyz = np.asarray(t.getcol("POSITION"), float)
    with core_ms.open_table(mini / "FIELD") as t:
        phase = np.asarray(t.getcol("PHASE_DIR"), float)
    k = np.load(Path(a1c_dir) / "a1c-casa.npz")
    res = {"tolerance_rad": TOL, "fields": {}}
    worst_k = 0.0
    for fid in (1, 2):
        rows = c["FIELD_ID"] == fid
        a1, a2, tm = c["ANTENNA1"][rows], c["ANTENNA2"][rows], c["TIME"][rows]
        ra, dec = phase[fid].reshape(-1)[:2]
        ts, ants = k[f"f{fid}_times"], k[f"f{fid}_ants"]
        q = np.stack([cal_pol.parallactic_angle_casa(ts, ra, dec, xyz[a]) for a in ants], 1)
        old = np.stack([cal_pol.parallactic_angle_tete(ts, ra, dec, xyz[a]) for a in ants], 1)
        ti = np.searchsorted(ts, tm)
        ja, jb = np.searchsorted(ants, a1), np.searchsorted(ants, a2)

        def rows_of(m, ti=ti, ja=ja, jb=jb):
            return np.concatenate([m[ti, ja], m[ti, jb]])

        K = rows_of(k[f"f{fid}_K"])
        z = np.load(Path(a1b_dir) / f"probe_{fid}.npz")
        cp, cq = extract(z["CORRECTED_DATA"][rows][:, 0].astype(np.complex128))
        chi = np.concatenate([cp, cq]) - RECEPTOR
        new_k = wrap(rows_of(q) - K)
        res["fields"][str(fid)] = {
            "new_minus_K_max_rad": float(np.abs(new_k).max()),
            "new_minus_K_median_rad": float(np.median(new_k)),
            "old_minus_K_max_rad": float(np.abs(wrap(rows_of(old) - K)).max()),
            "new_minus_casa_probe_max_rad": float(np.abs(wrap(chi - rows_of(q), np.pi)).max()),
            "old_minus_casa_probe_max_rad": float(np.abs(wrap(chi - rows_of(old), np.pi)).max()),
            "K_minus_casa_probe_max_rad": float(np.abs(wrap(chi - K, np.pi)).max()),
        }
        worst_k = max(worst_k, res["fields"][str(fid)]["new_minus_K_max_rad"])
    res["p1a_max_rad"] = worst_k
    res["p1a_met"] = worst_k <= TOL
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
