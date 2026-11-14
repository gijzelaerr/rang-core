"""Arm A1's rang side and comparison (research/e2b-misses.md 9.2).

    python a1_rang.py spec OUT_DIR          CASA's applycal list -> OUT_DIR/a1-spec.json
    python a1_rang.py rang MINI_MS OUT_DIR  C3, and rang's M1 and M2 values -> OUT_DIR/rang/
    python a1_rang.py compare OUT_DIR       C2, C3, M1, M2 and the rule  -> OUT_DIR/a1.json

Terms in rang's `cal_gain.TYPE_ORDER` (CASA's order of correction): field
J1939-6342 B, K, Kcross, G, Gpol, Df, Xf, then P; field J1833-2103 the same
with F for G and Gpol. Interp and gainfield are 2b's (`R/applycal-spec.json`,
`R/rang-run/apply/summary.json`).

- M1: each term alone on DATA = 1 (all four correlations), FLAG false:
  rang `cal_apply.apply(direction='correct')` (P: `cal_pol.rotate`,
  inverse) against CASA `applycal`; d in float32 ulps of rang's value.
- M2: cumulative sets on the real DATA and after-calibrate FLAG: rang's
  apply (one rounding after the tables; P by `cal_pol.rotate`) and the
  float32 emulation (one term at a time, complex64 between terms, P last).
"""

import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "python"))

R = Path(r"D:\rang\outputs\e2-20261111-20-e2b")
EPS = float(np.finfo(np.float32).eps)
FIELDS = {
    "J1939-6342": {"id": 1, "terms": [("B", "B", "linear", ""), ("K", "K", "linear", ""),
                   ("Kcross", "Kcross", "nearest", ""), ("G", "G", "linear", ""),
                   ("Gpol", "Gpol", "linear", ""), ("Df", "Df", "nearest", ""),
                   ("Xf", "Xf", "nearest", "")]},
    "J1833-2103": {"id": 2, "terms": [("B", "B", "linear", "J1939-6342"),
                   ("K", "K", "linear", "J1939-6342"), ("Kcross", "Kcross", "nearest", ""),
                   ("F", "F", "linear", "J1833-2103"), ("Df", "Df", "nearest", ""),
                   ("Xf", "Xf", "nearest", "")]},
}  # fmt: skip
TAB_IN = "/w/a1/tables"  # rang's frozen tables inside the container
RECEPTOR = -np.pi / 2


def short(f):
    return "f1" if f.startswith("J1939") else "f2"


def spec(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    calls = []
    for c in json.loads((R / "applycal-spec.json").read_text()):
        if c["field"] not in FIELDS:
            continue
        calls.append({"name": f"c2_{short(c['field'])}", "field": c["field"],
                      "gaintable": [g.replace("/p/rang-run/calibrate", TAB_IN) for g in c["gaintable"]],
                      "interp": c["interp"], "gainfield": c["gainfield"],
                      "parang": c["parang"], "unit": False})  # fmt: skip
    for f, d in FIELDS.items():
        terms = d["terms"]
        for i in range(1, len(terms) + 1):
            sub = terms[:i]
            calls.append({"name": f"cum_{short(f)}_{i}", "field": f,
                          "gaintable": [f"{TAB_IN}/{t[1]}" for t in sub],
                          "interp": [t[2] for t in sub], "gainfield": [t[3] for t in sub],
                          "parang": False, "unit": False})  # fmt: skip
        calls.append({"name": f"cum_{short(f)}_{len(terms) + 1}", "field": f,
                      "gaintable": [f"{TAB_IN}/{t[1]}" for t in terms],
                      "interp": [t[2] for t in terms], "gainfield": [t[3] for t in terms],
                      "parang": True, "unit": False})  # fmt: skip
        for t in terms:
            calls.append({"name": f"term_{short(f)}_{t[0]}", "field": f,
                          "gaintable": [f"{TAB_IN}/{t[1]}"], "interp": [t[2]],
                          "gainfield": [t[3]], "parang": False, "unit": True})  # fmt: skip
        calls.append({"name": f"term_{short(f)}_P", "field": f, "gaintable": [],
                      "interp": [], "gainfield": [], "parang": True, "unit": True})  # fmt: skip
    (out / "a1-spec.json").write_text(json.dumps(calls, indent=1) + "\n")
    print(len(calls), "calls")
    return 0


def rang_side(mini, out):
    from rang import applycal, cal_apply, cal_pol, core_ms
    from rang.formats import caltable

    mini, out = Path(mini), Path(out)
    rd = out / "rang"
    rd.mkdir(parents=True, exist_ok=True)
    # C3: rang's library apply with the frozen apply's arguments on a copy.
    c3 = out / "c3.ms"
    if c3.exists():
        shutil.rmtree(c3)
    shutil.copytree(mini, c3)
    s = json.loads((R / "rang-run" / "apply" / "summary.json").read_text())
    for e in s["applied"]:
        applycal.applycal(
            c3, [R / "rang-run" / "calibrate" / n for n in e["tables_applied"]],
            interp=[t["interp"] for t in e["tables"]],
            gainfield=[t["gainfield"] for t in e["tables"]],
            calwt=[t["calwt"] for t in e["tables"]], field=e["fields"],
            applymode=e["applymode"], scan=e["scans"], parang=e["parang"],
            frame=e["frame"], receptor_angle=e["receptor_angle"], parang_flags="none",
        )  # fmt: skip
    with core_ms.open_table(c3) as t:
        got = {k: t.getcol(k) for k in ("CORRECTED_DATA", "FLAG", "RANG_CORRECTED_DATA",
                                         "RANG_FLAG", "FIELD_ID")}  # fmt: skip
    np.savez(rd / "c3.npz", **got)
    # M1 and M2 inputs.
    with core_ms.open_table(mini) as t:
        col = {k: t.getcol(k) for k in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID",
                                         "DATA", "FLAG")}  # fmt: skip
    info = applycal.ms_info(mini)
    freqs = info["chan_freq"][0]
    for f, d in FIELDS.items():
        fid = d["id"]
        rows = col["FIELD_ID"] == fid
        tm, a1, a2 = col["TIME"][rows], col["ANTENNA1"][rows], col["ANTENNA2"][rows]
        tabs = [caltable.read(R / "rang-run" / "calibrate" / t[1]) for t in d["terms"]]
        tfs = [
            applycal.field_map(tb, t[3], info)[fid] for tb, t in zip(tabs, d["terms"])
        ]
        interps = [t[2] for t in d["terms"]]
        ap, aq = cal_pol.row_angles(mini, tm, a1, a2, fid, "casa", RECEPTOR)

        def run(
            data, flag, idx, tm=tm, a1=a1, a2=a2, tabs=tabs, interps=interps, tfs=tfs
        ):
            return cal_apply.apply(data, flag, tm, a1, a2, freqs, [tabs[i] for i in idx],
                                   interp=[interps[i] for i in idx], nant=info["nant"],
                                   table_fields=[tfs[i] for i in idx])  # fmt: skip

        unit = np.ones(col["DATA"][rows].shape, np.complex64)
        noflag = np.zeros(unit.shape, bool)
        res = {}
        for i, t in enumerate(d["terms"]):
            res[f"term_{t[0]}"], res[f"term_{t[0]}_flag"] = run(unit, noflag, [i])
        res["term_P"] = cal_pol.rotate(unit, ap, aq, inverse=True)
        res["term_P_flag"] = noflag
        data, flag = col["DATA"][rows], col["FLAG"][rows]
        n = len(d["terms"])
        emu, eflag = data.astype(np.complex64), flag.copy()
        for i in range(n):
            res[f"cum_{i + 1}"], res[f"cum_{i + 1}_flag"] = run(
                data, flag, list(range(i + 1))
            )
            emu, eflag = run(emu, eflag, [i])
            emu = emu.astype(np.complex64)
            res[f"emu_{i + 1}"], res[f"emu_{i + 1}_flag"] = emu, eflag
        res[f"cum_{n + 1}"] = cal_pol.rotate(res[f"cum_{n}"], ap, aq, inverse=True)
        res[f"cum_{n + 1}_flag"] = res[f"cum_{n}_flag"]
        res[f"emu_{n + 1}"] = cal_pol.rotate(emu, ap, aq, inverse=True).astype(
            np.complex64
        )
        res[f"emu_{n + 1}_flag"] = eflag
        res["rows"] = np.flatnonzero(rows)
        np.savez(rd / f"{short(f)}.npz", **res)
    print("rang side written to", rd)
    return 0


def ulps(c, r):
    """d of M1: |c - r| in float32 ulps of rang's value; structural
    near-zeros (|r| < 1e-3 max_k |r_k|) in ulps of the cell's largest."""
    c = c.astype(np.complex128)
    r64 = r.astype(np.complex128)
    mag = np.abs(r64)
    cmax = mag.max(-1, keepdims=True)
    comp = np.maximum(np.abs(r64.real), np.abs(r64.imag)).astype(np.float32)
    u = np.spacing(comp).astype(np.float64)
    u_cell = np.broadcast_to(
        np.spacing(cmax.astype(np.float32)).astype(np.float64), u.shape
    )
    u = np.where(mag >= 1e-3 * cmax, u, u_cell)
    return np.abs(c - r64) / np.where(u > 0, u, np.finfo(np.float32).tiny)


def eps_cell(c, x):
    c, x = c.astype(np.complex128), x.astype(np.complex128)
    cmax = np.abs(x).max(-1, keepdims=True)
    return np.abs(c - x) / (EPS * np.where(cmax > 0, cmax, 1))


def stats(v):
    v = np.asarray(v, float).ravel()
    if not v.size:
        return {"n": 0}
    return {"n": int(v.size), "median": float(np.median(v)), "p99": float(np.percentile(v, 99)),
            "max": float(v.max())}  # fmt: skip


def compare(out):
    out = Path(out)
    cdir, rd = out / "casa", out / "rang"
    cells = json.loads((R / "g2b-applycal-cells.json").read_text())
    mini = json.loads((out / "mini.json").read_text())
    rows = mini["rows"]
    res = {"cells": len(cells)}
    # C3
    c3 = np.load(rd / "c3.npz")
    use = ~c3["RANG_FLAG"]
    res["c3"] = {
        "values_bit_identical": bool(np.array_equal(c3["CORRECTED_DATA"][use],
                                                    c3["RANG_CORRECTED_DATA"][use])),
        "flags_equal": bool(np.array_equal(c3["FLAG"], c3["RANG_FLAG"])),
        "compared": int(use.sum()),
    }  # fmt: skip
    res["c3"]["met"] = res["c3"]["values_bit_identical"]
    # C2: archived per-correlation eps (rang's cell max, 2b's compare)
    worst = 0.0
    per = []
    for c in cells:
        i = rows.index(int(c["row"]))
        f = "f1" if c["field"] == 1 else "f2"
        z = np.load(cdir / f"c2_{f}.npz")
        cv = z["CORRECTED_DATA"][i, c["chan"]].astype(np.complex128)
        g = c3["RANG_CORRECTED_DATA"][i, c["chan"]].astype(np.complex128)
        use = ~(z["FLAG"][i, c["chan"]] | c3["RANG_FLAG"][i, c["chan"]])
        e = np.where(use, np.abs(cv - g) / (EPS * np.abs(g).max()), 0.0)
        dev = float(np.max(np.abs(np.round(e, 2) - np.asarray(c["eps"]))))
        per.append(dev)
        worst = max(worst, dev)
    res["c2"] = {"max_abs_eps_deviation": worst, "met": bool(worst <= 0.01 + 1e-9)}
    # M1 and M2 per field
    m1, m2 = {}, {}
    for f, d in FIELDS.items():
        s = short(f)
        z = np.load(rd / f"{s}.npz")
        frows = list(z["rows"])
        mine = [c for c in cells if (c["field"] == 1) == (s == "f1")]
        idx = [(frows.index(rows.index(int(c["row"]))), int(c["chan"])) for c in mine]
        names = [t[0] for t in d["terms"]] + ["P"]
        m1[s] = {}
        for name in names:
            cz = np.load(cdir / f"term_{s}_{name}.npz")
            cv = cz["CORRECTED_DATA"][z["rows"]]
            cf = cz["FLAG"][z["rows"]]
            rv, rf = z[f"term_{name}"], z[f"term_{name}_flag"]
            ok = ~cf & ~rf
            d_all = ulps(cv, rv)
            at = np.array([d_all[i, ch] for i, ch in idx]) if idx else np.zeros((0, 4))
            okc = (
                np.array([ok[i, ch] for i, ch in idx])
                if idx
                else np.zeros((0, 4), bool)
            )
            m1[s][name] = {
                "cells42_max_ulp": float(at[okc].max()) if okc.any() else None,
                "cells42_over_2": int((at[okc] > 2).sum()),
                "cells42_compared": int(okc.sum()),
                "all_rows": stats(d_all[ok]),
                "all_rows_over_2": int((d_all[ok] > 2).sum()),
                "flags_differ": int((cf != rf).sum()),
            }  # fmt: skip
        n = len(d["terms"]) + 1
        m2[s] = {}
        for k in range(1, n + 1):
            cz = np.load(cdir / f"cum_{s}_{k}.npz")
            cv, cf = cz["CORRECTED_DATA"][z["rows"]], cz["FLAG"][z["rows"]]
            entry = {"set": names[:k] if k < n else names}
            for side in ("cum", "emu"):
                x, xf = z[f"{side}_{k}"], z[f"{side}_{k}_flag"]
                ok = ~cf & ~xf
                e = eps_cell(cv, x)
                at = np.array([e[i, ch] for i, ch in idx])
                okc = np.array([ok[i, ch] for i, ch in idx])
                entry[side] = {"cells42_max_eps": float(at[okc].max()) if okc.any() else None,
                               "cells42_over_2": int((at[okc] > 2).sum()),
                               "cells42_over_11": int((at[okc] > 11).sum()),
                               "all_rows": stats(e[ok]),
                               "all_rows_over_11": int((e[ok] > 11).sum())}  # fmt: skip
            m2[s][str(k)] = entry
    res["m1"], res["m2"] = m1, m2
    # The rule (9.2), in TYPE_ORDER.
    order = ["B", "K", "Kcross", "G", "Gpol", "F", "Df", "Xf", "P"]
    over = [
        (order.index(n), s, n)
        for s in m1
        for n, v in m1[s].items()
        if v["cells42_over_2"]
    ]
    first = min(over)[1:] if over else None
    emu_ok = all(m2[s][str(len(FIELDS[f]["terms"]) + 1)]["emu"]["cells42_over_2"] == 0
                 for f in FIELDS for s in [short(f)])  # fmt: skip
    if not (res["c2"]["met"] and res["c3"]["met"]):
        outcome = "void: a harness control failed"
    elif first is None and emu_ok:
        outcome = "rounding"
    elif first is not None:
        outcome = f"rang difference: first term {first[1]} (field {first[0]})"
    else:
        outcome = "not shown"
    res["first_term_over_2_ulps"] = first
    res["emulation_within_2_eps_all42"] = emu_ok
    res["outcome"] = outcome
    (out / "a1.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("c2", "c3", "first_term_over_2_ulps",
                      "emulation_within_2_eps_all42", "outcome")}, indent=1))  # fmt: skip
    return 0


def main(argv):
    if argv[0] == "spec":
        return spec(argv[1])
    if argv[0] == "rang":
        return rang_side(argv[1], argv[2])
    return compare(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
