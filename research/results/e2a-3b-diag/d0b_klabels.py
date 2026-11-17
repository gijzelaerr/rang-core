"""D0b of research/e2a-3b-diag.md (added after D0 was read, post hoc): the
K solution TIME labels. D0 found rang's K1 TIMEs equal to its G1 TIMEs
(and to CASA's G1 TIMEs within 0.01 s), while CASA's K1 TIMEs are 19-49 s
earlier (K0: 204 and 233 s). The composite interpolates each table
linearly in TIME, so the labels alone move it. Here the KGB1 (and KGB0)
composite is recomputed with one side's K TIMEs replaced by the other's
(rows matched by time rank), nothing else changed.

    python d0b_klabels.py RUN OUT.json
"""

import copy
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-average-time"))

import e2avg_common as C
from rang import cal_apply

FCAL = "J1939-6342"
POOLED = [cal_apply.POOLED] * 3


def relabel(t, times_from):
    """`t` with each row's TIME replaced by `times_from`'s TIME of the same
    time rank."""
    src = np.unique(np.round(times_from.column("TIME"), 3))
    exact = np.unique(times_from.column("TIME"))
    if len(src) != len(exact):
        raise ValueError("ambiguous times")
    own = np.unique(np.round(t.column("TIME"), 3))
    if len(own) != len(src):
        raise ValueError("interval counts differ")
    rank = np.searchsorted(own, np.round(t.column("TIME"), 3))
    out = copy.deepcopy(t)
    new = exact[rank].astype(np.float64)
    out.main["TIME"] = new if isinstance(t.main["TIME"], np.ndarray) else list(new)
    return out


def main(run, out_path):
    run = Path(run)
    ms = run / "e2a.ms"
    r = {n: C.table(run / "rang-run" / "calibrate" / n) for n in ("K0", "G0", "B0", "K1", "G1", "B1")}
    c = {n: C.table(run / "casa" / "tables" / n) for n in r}
    fid = C.field_id(ms, FCAL)
    out = {}
    for tag in ("1", "0"):
        K, G, B = f"K{tag}", f"G{tag}", f"B{tag}"
        b, fb = C.composite(ms, fid, [c[K], c[G], c[B]], POOLED, step=8)
        cases = {
            "rang_K_on_casa_K_times": ([relabel(r[K], c[K]), r[G], r[B]], None),
            "casa_K_on_casa_G_times": (None, [relabel(c[K], c[G]), c[G], c[B]]),
        }
        res = {}
        for label, (ra, cb) in cases.items():
            if ra is not None:
                a, fa = C.composite(ms, fid, ra, POOLED, step=8)
                res[label] = C.rel_stats(a, fa, b, fb)
            else:
                a, fa = C.composite(ms, fid, [r[K], r[G], r[B]], POOLED, step=8)
                b2, fb2 = C.composite(ms, fid, cb, POOLED, step=8)
                res[label] = C.rel_stats(a, fa, b2, fb2)
                res["casa_relabel_vs_casa (CASA-CASA)"] = C.rel_stats(b2, fb2, b, fb)
                del b2, fb2
            del a, fa
        out[f"KGB{tag}"] = res
        del b, fb
    C.write(out_path, out)
    print(json.dumps({k: {kk: [vv["median"], vv["p95"], vv["class_b"]] for kk, vv in v.items()}
                      for k, v in out.items()}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
