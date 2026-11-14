"""E2-B's 1830-211 row read as a polarisation vector (post hoc,
research/e2b-misses.md section 5): per bin, |delta (Q, U)| / I between rang
and CASA, p, and the |delta chi| bound |delta P| / (2 p) that the vector
difference allows. Reads the archived row only.

    python j1830_vector.py ROWS.json [ROWS.json ...] > OUT.json

ROWS.json: fp-e2-acceptance research/results/e2-acceptance/e2b/{frozen,
amended}/rows-j1830.json.
"""

import json
import math
import sys


def bins(path):
    out = []
    with open(path) as fh:
        rows = json.load(fh)["bins"]
    for b in rows:
        if not b.get("scored"):
            continue
        i = b["I_rang"]
        dq = (b["Q_rang"] - b["Q_casa"]) / i
        du = (b["U_rang"] - b["U_casa"]) / i
        dp_vec = math.hypot(dq, du)
        p = 0.5 * (b["p_rang"] + b["p_casa"])
        out.append(
            {
                "lo_ghz": b["lo_hz"] / 1e9,
                "frac_unflagged": b["frac_unflagged"][0],
                "p_percent": 100 * p,
                "dP_over_I": dp_vec,
                "dchi_bound_deg": math.degrees(min(dp_vec / (2 * p), math.pi / 2)),
                "dchi_deg": b["dchi_deg"],
                "dI_rel": b["dI_rel"],
            }
        )
    return out


if __name__ == "__main__":
    json.dump({p: bins(p) for p in sys.argv[1:]}, sys.stdout, indent=1)
