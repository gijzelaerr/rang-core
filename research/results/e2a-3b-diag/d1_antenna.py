"""D1 post hoc reading (research/e2a-3b-diag.md, added after d1-score.json
was read): the KGB1 composite of each D1 pair per antenna, and with the
baselines of one antenna (m053, ID 50: K near 2,300 ns) left out.

    python d1_antenna.py D           -> D/d1-antenna.json
    python d1_antenna.py RUN --full  -> E2-A's archived tables, every 8th time
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d1_score as S

C = S.C


def per_antenna(ms, fid, A, B, drop):
    a, fa = C.composite(ms, fid, A, S.POOLED, step=S.STEP)
    b, fb = C.composite(ms, fid, B, S.POOLED, step=S.STEP)
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        c = {
            n: np.asarray(t.getcol(n))
            for n in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID")
        }
    rows = (c["FIELD_ID"] == fid) & (c["ANTENNA1"] != c["ANTENNA2"])
    times = np.unique(c["TIME"][rows])[:: S.STEP]
    rows &= np.isin(c["TIME"], times)
    a1, a2 = c["ANTENNA1"][rows], c["ANTENNA2"][rows]
    ok = ~fa & ~fb & (np.abs(b) > 0)
    r = np.abs(a - b) / np.where(np.abs(b) > 0, np.abs(b), 1)
    out = {"all": C.stats(r[ok])}
    keep = ~np.isin(a1, drop) & ~np.isin(a2, drop)
    out[f"without_{drop}"] = C.stats(r[keep][ok[keep]])
    out["antenna_median"] = {}
    for ant in sorted(set(a1.tolist()) | set(a2.tolist())):
        sel = (a1 == ant) | (a2 == ant)
        x = r[sel][ok[sel]]
        out["antenna_median"][int(ant)] = float(np.median(x)) if x.size else None
    return out


def main(argv):
    if "--full" in argv:
        run = Path(argv[0])
        ms = run / "e2a.ms"
        r = [C.table(run / "rang-run" / "calibrate" / n) for n in ("K1", "G1", "B1")]
        c = [C.table(run / "casa" / "tables" / n) for n in ("K1", "G1", "B1")]
        res = {"full R-C": per_antenna(ms, C.field_id(ms, S.FCAL), r, c, [50])}
        Path(argv[2]).write_text(json.dumps(res, indent=1))
        print(
            json.dumps(
                {
                    k: {kk: vv for kk, vv in v.items() if kk != "antenna_median"}
                    for k, v in res.items()
                },
                indent=1,
            )
        )
        return 0
    d = Path(argv[0])
    ms = d / "rang-r0.ms"
    fid = C.field_id(ms, S.FCAL)
    arms = {a: S.load(d, a) for a in ("r0", "c0", "tf", "tt", "tk")}
    res = {}
    for label, x, y in (("R0-C0", "r0", "c0"), ("R0-TF", "r0", "tf"), ("TT-TF", "tt", "tf"),
                        ("R0-TT", "r0", "tt"), ("R0-TK", "r0", "tk")):  # fmt: skip
        A = [arms[x][n] for n in ("K1", "G1", "B1")]
        B = [arms[y][n] for n in ("K1", "G1", "B1")]
        res[label] = per_antenna(ms, fid, A, B, [50])
    C.write(d / "d1-antenna.json", res)
    print(
        json.dumps(
            {
                k: {kk: vv for kk, vv in v.items() if kk != "antenna_median"}
                for k, v in res.items()
            },
            indent=1,
        )
    )
    print(
        json.dumps(
            {
                k: {a: round(m, 4) if m else m for a, m in v["antenna_median"].items()}
                for k, v in res.items()
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
