"""Post hoc checks after section 10 of research/e2a-3b-k.md was drafted:

    python k_hb.py   -> O/score-hb.json

1. H-B on a common cell set: U, C and CK against truth on cells unflagged in
   all three arms and in the data; flag differences of U-CK; G1 and B1 of U
   against CK (rows, flags) on one S1 seed.
2. The real D arm against U: per-term differences and FLAG cells that
   differ between `rang-d.ms` and `rang-u.ms` (A0's flags).
3. S0f's floor: |DATA - M J_U| / |M J_U| on data-unflagged cells at rang
   U's pass-0 and pass-1 solutions, and the solves' converged fractions.
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "research" / "results" / "e2-average-time"))
sys.path.insert(0, str(HERE))

import e2avg_common as C
from k_score import NAMES0, NAMES1, Comp, O, tabs
from rang import cal_apply, core_ms


def flags(t):
    return np.stack([np.asarray(x) for x in t.main["FLAG"]])


def common_truth(tag):
    ms = O / f"sim-{tag}-u.ms"
    cp = Comp(ms)
    U = O / f"sim-{tag}-u.ms.rang-run" / "calibrate"
    CK = O / f"sim-{tag}-casa-ck"
    Cc = O / f"sim-{tag}-casa-c"
    T = tabs(O / f"truth-{tag}", ("K", "G", "B"))
    out = {}
    for tg, names in (("KGB1", NAMES1), ("KGB0", NAMES0)):
        arms = {
            "u": tabs(U, names),
            "c": tabs(Cc, names),
            "ck": [C.table(U / names[0]), *tabs(CK, names[1:])],
        }
        comps = {a: cp.get(f"{a}{tg}", t) for a, t in arms.items()}
        b, fb = cp.get("truth", T)
        bad = fb | cp.data_flags()
        for _, f in comps.values():
            bad = bad | f
        out[tg] = {a: C.rel_stats(v, bad, b, bad) for a, (v, _) in comps.items()}
        out[tg]["cells"] = int((~bad).sum())
        out[tg]["flags_differ_u_ck"] = int((comps["u"][1] != comps["ck"][1]).sum())
        out[tg]["flags_differ_u_c"] = int((comps["u"][1] != comps["c"][1]).sum())
    return out


def tables_u_ck(tag):
    U = O / f"sim-{tag}-u.ms.rang-run" / "calibrate"
    CK = O / f"sim-{tag}-casa-ck"
    out = {}
    for n in ("G1", "B1", "G0", "B0"):
        a, b = C.table(U / n), C.table(CK / n)
        pa, fa, pb, fb, na, nb = C.matched(a, b)
        ok = ~fa & ~fb
        out[n] = {
            "rows": [na, nb],
            "rang_only_flagged": int((fa & ~fb).sum()),
            "casa_only_flagged": int((fb & ~fa).sum()),
            "rel": C.stats((np.abs(pa - pb) / np.abs(pb))[ok]),
        }
        if n[0] == "G":
            ka, kb = C.keyed(a), C.keyed(b)
            diffs = []
            for key, ra in ka.items():
                rb = kb.get(key)
                if rb is not None and (flags(a)[ra] != flags(b)[rb]).any():
                    diffs.append({"interval": key[0], "antenna": key[1],
                                  "rang": flags(a)[ra].ravel().tolist(),
                                  "casa": flags(b)[rb].ravel().tolist()})  # fmt: skip
            out[n]["flag_differences"] = diffs
    return out


def real_d():
    U = O / "rang-u.ms.rang-run" / "calibrate"
    D = O / "rang-d.ms.rang-run" / "calibrate"
    out = {"terms": {}}
    for n in ("K0", "G0", "B0", "K1", "G1", "B1"):
        d = C.term_diff(
            C.table(D / n), C.table(U / n), "delay" if n[0] == "K" else "complex"
        )
        out["terms"][n] = {k: v for k, v in d.items() if k != "rows"}
    with core_ms.open_table(O / "rang-u.ms") as t:
        fu = np.asarray(t.getcol("FLAG"))
    with core_ms.open_table(O / "rang-d.ms") as t:
        fd = np.asarray(t.getcol("FLAG"))
    out["flag_cells_differ"] = int((fu != fd).sum())
    out["flagged_u"], out["flagged_d"] = int(fu.sum()), int(fd.sum())
    for arm, d in (("u", U), ("d", D)):
        summ = d / "summary.json"
        if summ.exists():
            out[f"summary_{arm}"] = json.loads(summ.read_text())
    return out


def floor(tag):
    ms = O / f"sim-{tag}-u.ms"
    U = O / f"sim-{tag}-u.ms.rang-run" / "calibrate"
    with core_ms.open_table(ms) as t:
        n = t.nrows
        sel = np.arange(0, n, 7)
        c = {
            k: np.asarray(t.getcol(k))[sel]
            for k in ("TIME", "ANTENNA1", "ANTENNA2", "DATA")
        }
    with core_ms.open_table(O / "src.ms") as t:
        flag = np.asarray(t.getcol("FLAG"))[sel]
    with core_ms.open_table(O / "rang-u.ms") as t:
        m = np.asarray(t.getcol("MODEL_DATA"))[sel]
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0])
    cross = c["ANTENNA1"] != c["ANTENNA2"]
    out = {}
    for tg, names in (("KGB0", NAMES0), ("KGB1", NAMES1)):
        v, f = cal_apply.apply(m[cross], flag[cross], c["TIME"][cross], c["ANTENNA1"][cross],
                               c["ANTENNA2"][cross], freq, tabs(U, names), interp="linear",
                               direction="corrupt", table_fields=[cal_apply.POOLED] * 3)  # fmt: skip
        d = c["DATA"][cross]
        r = []
        for h in (0, 3):
            ok = ~f[..., h] & (np.abs(v[..., h]) > 0)
            r.append(np.abs(d[..., h] - v[..., h])[ok] / np.abs(v[..., h])[ok])
        out[tg] = C.stats(np.concatenate(r))
    summ = U / "summary.json"
    if summ.exists():
        out["summary"] = json.loads(summ.read_text())
    return out


def main():
    out = {"common_cells": {}, "tables_u_ck": {}}
    for tag in (
        "s0",
        "s0f",
        "s1-20261171",
        "s1-20261172",
        "s2-20261171",
        "s2-20261172",
    ):
        out["common_cells"][tag] = common_truth(tag)
    out["tables_u_ck"]["s1-20261171"] = tables_u_ck("s1-20261171")
    out["real_d"] = real_d()
    out["floor_s0f"] = floor("s0f")
    C.write(O / "score-hb.json", out)
    brief = {t: {g: {a: (v["median"] if isinstance(v, dict) else v) for a, v in x.items()}
                 for g, x in y.items()} for t, y in out["common_cells"].items()}  # fmt: skip
    print(json.dumps(brief, indent=1))
    print(json.dumps({n: {k: v for k, v in x.items() if k != "flag_differences"}
                      | {"n_flag_differences": len(x.get("flag_differences", []))}
                      for n, x in out["tables_u_ck"]["s1-20261171"].items()}, indent=1))  # fmt: skip
    print(
        json.dumps(
            {k: v for k, v in out["real_d"].items() if not k.startswith("summary")},
            indent=1,
        )
    )
    print(
        json.dumps(
            {k: v for k, v in out["floor_s0f"].items() if k != "summary"}, indent=1
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
