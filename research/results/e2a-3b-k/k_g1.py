"""Step 3 follow-up (research/e2a-3b-k.md, post hoc after TT-TKG was read): rang's
and CASA's G1 (both on rang's K1) and B1 on the real subset, row by row:
flags, relative differences per interval, and the B1 difference per antenna.

    python k_g1.py   -> O/score-g1.json
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "research" / "results" / "e2-average-time"))

import e2avg_common as C

O = Path.home() / "rang-data" / "outputs" / "e2a-3b-k-20261117"
TT = O / "win" / "rang-tt.ms.rang-run" / "calibrate"
TK3 = O / "casa-ntk3"


def flags(t):
    return np.stack([np.asarray(x) for x in t.main["FLAG"]])


def main():
    out = {}
    for n in ("G1", "B1", "G0", "B0"):
        a, b = C.table(TT / n), C.table(TK3 / n)
        pa, fa, pb, fb, na, nb = C.matched(a, b)
        ok = ~fa & ~fb
        rel = np.abs(pa - pb) / np.abs(pb)
        out[n] = {"rows": [na, nb], "flagged_rang": int(fa.sum()), "flagged_casa": int(fb.sum()),
                  "flags_differ": int((fa != fb).sum()), "rel": C.stats(rel[ok]),
                  "rang_only_flagged": int((fa & ~fb).sum()), "casa_only_flagged": int((fb & ~fa).sum())}  # fmt: skip
        if n in ("G1", "G0"):
            ta = np.round(a.column("TIME"), 3)
            out[n]["times_rang"] = np.unique(ta).tolist()
            out[n]["times_casa"] = np.unique(np.round(b.column("TIME"), 3)).tolist()
            ka = C.keyed(a)
            kb = C.keyed(b)
            per = {}
            for (ti, ant), ra in ka.items():
                rb = kb.get((ti, ant))
                if rb is None:
                    continue
                f1, f2 = flags(a)[ra], flags(b)[rb]
                if (f1 != f2).any():
                    per.setdefault(int(ant), []).append(
                        {
                            "interval": ti,
                            "rang": f1.ravel().tolist(),
                            "casa": f2.ravel().tolist(),
                        }
                    )
            out[n]["flag_differences_by_antenna"] = per
        if n in ("B1", "B0"):
            ant = a.column("ANTENNA1")
            ia = {int(x): i for i, x in enumerate(ant)}
            ib = {int(x): i for i, x in enumerate(b.column("ANTENNA1"))}
            per = {}
            for x in sorted(set(ia) & set(ib)):
                p1, p2 = a.params[ia[x]], b.params[ib[x]]
                f1, f2 = flags(a)[ia[x]], flags(b)[ib[x]]
                g = ~f1 & ~f2
                per[x] = (
                    float(np.median((np.abs(p1 - p2) / np.abs(p2))[g]))
                    if g.any()
                    else None
                )
            out[n]["median_rel_by_antenna"] = per
    (O / "score-g1.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("times_rang", "times_casa")}
                      for k, v in out.items()}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
