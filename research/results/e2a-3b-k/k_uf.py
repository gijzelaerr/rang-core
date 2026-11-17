"""Section 11 of research/e2a-3b-k.md (post hoc): the UF arm
(`calibrate.average_freq: true`) on the real subset and on S1 seed 1.

    python k_uf.py   -> O/score-uf.json
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "research" / "results" / "e2-average-time"))
sys.path.insert(0, str(HERE))

import e2avg_common as C
from k_score import NAMES1, WIN, Comp, O, tabs


def g1_flag(d, ant=50, rank=7):
    t = C.table(Path(d) / "G1")
    tm = np.round(t.column("TIME"), 3)
    times = np.unique(tm)
    r = np.flatnonzero((t.column("ANTENNA1") == ant) & (tm == times[rank]))[0]
    snr = np.asarray(t.main["SNR"][r]).ravel().tolist()
    return {"flag": np.asarray(t.main["FLAG"][r]).ravel().tolist(), "snr": snr}


def main():
    out = {}
    tt = WIN / "rang-tt.ms.rang-run" / "calibrate"
    uf = O / "rang-uf.ms.rang-run" / "calibrate"
    cp = Comp(O / "src.ms")
    tk3 = [C.table(tt / "K1"), *tabs(O / "casa-ntk3", ("G1", "B1"))]
    ufk = [C.table(tt / "K1"), *tabs(uf, ("G1", "B1"))]
    out["real"] = {
        "uf_G1_id50_interval7": g1_flag(uf),
        "UF vs TK3 (CASA on rang's K)": cp.rel("uf", tabs(uf, NAMES1), "tk3", tk3),
        "UF G1 B1 on TT's K1 vs TK3": cp.rel("ufk", ufk, "tk3", tk3),
        "TT vs TK3": cp.rel("tt", tabs(tt, NAMES1), "tk3", tk3),
        "UF vs TT": cp.rel("uf", tabs(uf, NAMES1), "tt", tabs(tt, NAMES1)),
    }
    tag = "s1-20261171"
    ms = O / f"sim-{tag}-u.ms"
    cs = Comp(ms)
    U = O / f"sim-{tag}-u.ms.rang-run" / "calibrate"
    UF = O / f"sim-{tag}-uf.ms.rang-run" / "calibrate"
    CK = [C.table(U / "K1"), *tabs(O / f"sim-{tag}-casa-ck", ("G1", "B1"))]
    T = tabs(O / f"truth-{tag}", ("K", "G", "B"))
    arms = {"u": tabs(U, NAMES1), "uf": tabs(UF, NAMES1), "ck": CK}
    comps = {a: cs.get(a, t) for a, t in arms.items()}
    b, fb = cs.get("truth", T)
    bad = fb | cs.data_flags()
    for _, f in comps.values():
        bad = bad | f
    out["s1"] = {
        "uf_G1_id50_interval7": g1_flag(UF),
        "against_truth_common_cells": {
            a: C.rel_stats(v, bad, b, bad) for a, (v, _) in comps.items()
        },
        "uf-ck": cs.rel("uf", arms["uf"], "ck", CK, data_cells=True),
        "uf-u": cs.rel("uf", arms["uf"], "u", arms["u"], data_cells=True),
    }
    C.write(O / "score-uf.json", out)
    show = {
        "real": {k: (v if "id50" in k else {"median": v["median"], "p95": v["p95"]})
                 for k, v in out["real"].items()},
        "s1": {"flag": out["s1"]["uf_G1_id50_interval7"],
               "truth": {a: v["median"] for a, v in out["s1"]["against_truth_common_cells"].items()},
               "uf-ck": out["s1"]["uf-ck"]["data_unflagged"]["median"],
               "uf-u": out["s1"]["uf-u"]["data_unflagged"]["median"]},
    }  # fmt: skip
    print(json.dumps(show, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
