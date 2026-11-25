# SPDX-License-Identifier: MIT
"""DD9's runs (research/dd9-solver.md sections 3-6) on the sums of dd9.py."""

import importlib.util
import json
import math
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dd9", HERE / "dd9.py")
dd9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dd9)

DD6_BF = (
    Path(__file__).resolve().parents[3]
    / "research"
    / "results"
    / "dd6-d0"
    / "grid"
    / "B-F-4.json"
)
DD8_SCORE = (
    Path(__file__).resolve().parents[3]
    / "research"
    / "results"
    / "dd8-offaxis"
    / "score"
)
CAPS = [500, 2000]
ARMS_B = ("b0", "bP", "bM", "bR", "bL")


def truth(root):
    return np.load(dd9.DD7_ROOT / "b" / "truth.npz")["gains"]  # (nblock, nant, ndir, 2)


def sol_record(res, tr, S, m, k, dirmap=None):
    """Fractions, e_d (all, converged) and e-hat for one checkpoint result."""
    fr, masks = dd9.perdir(res)
    dirmap = dirmap or list(range(len(res["g"])))
    e_all, e_conv = [], []
    for t in range(1, 4):  # truth directions d1-d3
        d = dirmap[t]
        e_all.append(dd9.e_dir(res["g"][d], res["f"][d], tr[:, :, t], m[d]))
        e_conv.append(
            dd9.e_dir(res["g"][d], res["f"][d], tr[:, :, t], m[d], conv=masks[d])
        )
    blocks = np.arange(S.nblock)
    ehat = [dd9.ehat_dir(S, blocks, m[d], d, k) for d in range(S.ndir)]
    return {"fraction": fr, "iterations": res["iterations"], "global_fraction": res["fraction"],
            "flagged": [int((f != 0).sum()) for f in res["f"]],
            "e_d1_d3": e_all, "e_d1_d3_converged": e_conv, "ehat": ehat}  # fmt: skip


def save(path, res):
    out = {}
    for K in CAPS:
        if K in res:
            for key in ("g", "f", "g2", "f2"):
                for d, x in enumerate(res[K][key]):
                    out[f"{key}{K}_{d}"] = x
    if "history" in res:
        for key, v in res["history"].items():
            out[f"hist_{key}"] = v
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **out)


def load(path, K, D):
    z = np.load(path)
    return {
        key: [z[f"{key}{K}_{d}"] for d in range(D)] for key in ("g", "f", "g2", "f2")
    }


# -- gate GR --------------------------------------------------------------------------


def gate(root):
    root = Path(root)
    t0 = time.perf_counter()
    rec, ok = {}, True
    for name, sums, ref in (("O-F", "O-M0c", "O-F"), ("O-X", "O-skyO", "O-X")):
        S = dd9.Sums(root / "sums" / f"{sums}.npz")
        P = dd9.Problem(S, np.arange(S.nblock), [1] * 4)
        res = dd9.run(P, [500])
        fr, masks = dd9.perdir(res[500])
        g, _ = dd9.stack_sol(res[500]["g"], res[500]["f"])
        rj = json.loads((dd9.DD8_ROOT / "grid" / f"{ref}.json").read_text())
        gr, frr, cr = dd9.from_rust(dd9.DD8_ROOT / "grid" / f"{ref}.npz")
        conv = np.stack(masks, -1)
        pdiff = dd9.product_diff(g[:, 0], gr, conv, cr)
        flagged = [int((x != 0).sum()) for x in res[500]["f"]]
        dfrac = [abs(a - b) for a, b in zip(fr, rj["perdir_converged"], strict=True)]
        dflag = [
            abs(a - b) / max(b, 1)
            for a, b in zip(flagged, rj["flagged_per_direction"], strict=True)
        ]
        pmax = max(x["max"] or 0 for x in pdiff)
        this = bool(max(dfrac) <= 0.005 and max(dflag) <= 0.01 and pmax <= 1e-6)
        # e_d on the Rust gains with this module's truth error, beside DD8's
        tr = truth(root)
        e_rust = [
            dd9.e_dir(gr[:, :, t], frr[:, :, t], tr[:, :, t], 1) for t in range(4)
        ]
        rec[name] = {"fraction_ref": fr, "fraction_rust": rj["perdir_converged"], "fraction_absdiff": dfrac,
                     "flagged_ref": flagged, "flagged_rust": rj["flagged_per_direction"],
                     "product_diff_converged": pdiff, "iterations_ref": res[500]["iterations"],
                     "e_d_this_code_on_rust_gains": e_rust, "e_d_dd8": rj["e_d"], "pass": this}  # fmt: skip
        save(root / "gates" / f"ref-{name}.npz", res)
        ok &= this
    S = dd9.Sums(root / "sums" / "B-M0c.npz")
    P = dd9.Problem(S, np.arange(S.nblock), [1] * 4)
    res = dd9.run(P, [500])
    fr, _ = dd9.perdir(res[500])
    bf = json.loads(DD6_BF.read_text())
    d = [abs(a - b) for a, b in zip(fr, bf["perdir_converged"], strict=True)]
    rec["B-F"] = {"fraction_ref": fr, "fraction_dd6": bf["perdir_converged"], "fraction_absdiff": d,
                  "iterations_ref": res[500]["iterations"], "pass": bool(max(d) <= 0.005)}  # fmt: skip
    ok &= rec["B-F"]["pass"]
    rec["GR_pass_reference_vs_rust"] = bool(ok)
    rec["seconds"] = time.perf_counter() - t0
    dd9.write_json(root / "gates" / "GR.json", rec)
    print(json.dumps(rec, indent=1, default=float))
    if not ok:
        raise SystemExit("GR failed: setup outcome")


# -- part (a) -------------------------------------------------------------------------


def parta(root, base, variants="default,I1,I2,I3,I4"):
    """Section 4 on one base (B-X: B-M0c sums, O-X: O-skyO sums), no global
    stop (amendment A1), checkpoints 500 and 2000."""
    root = Path(root)
    sums = {"B-X": "B-M0c", "O-X": "O-skyO"}[base]
    S = dd9.Sums(root / "sums" / f"{sums}.npz")
    tr = truth(root)
    k = dd9.k_noise()
    m = [1] * 4
    rec = {}
    for v in variants.split(","):
        t0 = time.perf_counter()
        if v == "I4":
            res = {K: warm_sequential(S, K) for K in CAPS}
        else:
            P = dd9.Problem(S, np.arange(S.nblock), m)
            res = dd9.run(
                P, CAPS, variant=v, stop_fraction=2.0, history=(v == "default")
            )
        save(root / "solve" / f"{base}-{v}.npz", res)
        rec[v] = {f"cap{K}": sol_record(res[K], tr, S, m, k) for K in CAPS}
        rec[v]["seconds"] = time.perf_counter() - t0
        if v == "default":
            h = res["history"]
            ratio = h["conv"] / np.maximum(h["unfl"], 1)  # (iters, nint, D)
            ok = (ratio >= 0.99).all(-1)  # every direction 99 % converged
            nconv = np.where(ok.any(0), ok.argmax(0) + 1, 2001)
            rec[v]["N_conv"] = nconv.tolist()
            rec[v]["s0"] = np.median(np.sqrt(h["step"][0]), axis=-1).tolist()
        print(v, json.dumps(rec[v]["cap500"]), flush=True)
        dd9.write_json(root / "solve" / f"{base}-{v}.json", rec[v])


def warm_sequential(S, K):
    """I4: interval j starts from interval j-1's result after K iterations;
    flags fresh; each interval to K (+1 for the second solve)."""
    gs, fs, g2s, f2s = (
        [[] for _ in range(4)],
        [[] for _ in range(4)],
        [[] for _ in range(4)],
        [[] for _ in range(4)],
    )
    init = None
    for j in range(S.nblock):
        P = dd9.Problem(S, np.array([j]), [1] * 4)
        r = dd9.run(P, [K], stop_fraction=2.0, init=init)[K]
        init = [
            np.where((f == 1)[..., None], 1.0, g)
            for g, f in zip(r["g"], r["f"], strict=True)
        ]
        for d in range(4):
            gs[d].append(r["g"][d])
            fs[d].append(r["f"][d])
            g2s[d].append(r["g2"][d])
            f2s[d].append(r["f2"][d])
    cat = lambda x: [np.concatenate(v, 0) for v in x]
    return {
        "g": cat(gs),
        "f": cat(fs),
        "g2": cat(g2s),
        "f2": cat(f2s),
        "iterations": K,
        "fraction": float("nan"),
    }


def fixed_point(root):
    """Section 4's same-fixed-point check and the intervention rule."""
    root = Path(root)
    rec = {}
    for base in ("B-X", "O-X"):
        d0 = load(root / "solve" / f"{base}-default.npz", 2000, 4)
        _, m0 = dd9.perdir(d0)
        g0, _ = dd9.stack_sol(d0["g"], d0["f"])
        rec[base] = {}
        for v in ("I1", "I2", "I3", "I4"):
            dv = load(root / "solve" / f"{base}-{v}.npz", 2000, 4)
            _, mv = dd9.perdir(dv)
            gv, _ = dd9.stack_sol(dv["g"], dv["f"])
            pd = dd9.product_diff(
                g0[:, 0], gv[:, 0], np.stack(m0, -1), np.stack(mv, -1)
            )
            meds = [x["median"] for x in pd if x["median"] is not None]
            p99s = [x["p99"] for x in pd if x["p99"] is not None]
            rec[base][v] = {
                "product_diff": pd,
                "same_fixed_point": bool(
                    meds and max(meds) <= 1e-6 and max(p99s) <= 1e-4
                ),
            }
    ra = {
        b: {
            v: json.loads((root / "solve" / f"{b}-{v}.json").read_text())
            for v in ("default", "I1", "I2", "I3", "I4")
        }
        for b in ("B-X", "O-X")
    }
    mn = lambda r: min(r["cap500"]["fraction"][1:])
    gap = mn(ra["B-X"]["default"]) - mn(ra["O-X"]["default"])
    rec["gap"] = gap
    rec["rule"] = {}
    for v in ("I1", "I2", "I3", "I4"):
        lift = mn(ra["O-X"][v]) - mn(ra["O-X"]["default"])
        reading = (
            "closes" if lift >= 0.5 * gap else "partly" if lift >= 0.2 * gap else "no"
        )
        b_ok = mn(ra["B-X"][v]) >= mn(ra["B-X"]["default"]) - 0.02
        ehat = ra["O-X"][v]["cap500"]["ehat"][1:]
        econv = ra["O-X"][v]["cap500"]["e_d1_d3_converged"]
        acc = all(e <= 2 * eh for e, eh in zip(econv, ehat, strict=True))
        adm = bool(
            b_ok
            and acc
            and rec["O-X"][v]["same_fixed_point"]
            and rec["B-X"][v]["same_fixed_point"]
        )
        rec["rule"][v] = {"lift_O-X": lift, "reading": reading, "B-X_not_worse": bool(b_ok),
                          "O-X_accurate": bool(acc), "admissible": adm,
                          "O-X_e_over_ehat_converged": [e / eh for e, eh in zip(econv, ehat, strict=True)]}  # fmt: skip
    dd9.write_json(root / "solve" / "fixed_point.json", rec)
    print(json.dumps(rec, indent=1, default=float))


def jac(root, base, start=0, stop=None, at="default"):
    """Section 4's linearised rates on one base at the default's cap-2000 gains."""
    root = Path(root)
    sums = {"B-X": "B-M0c", "O-X": "O-skyO"}[base]
    S = dd9.Sums(root / "sums" / f"{sums}.npz")
    P = dd9.Problem(S, np.arange(S.nblock), [1] * 4)
    d0 = load(root / "solve" / f"{base}-{at}.npz", 2000, 4)
    g = np.stack(d0["g"], -1)  # (nint, nant, 2, D)
    f = np.stack(d0["f"], -1)  # (nint, nant, D)
    stop = S.nblock if stop is None else int(stop)
    out = []
    t0 = time.perf_counter()
    for j in range(int(start), stop):
        row = {"interval": j, "hands": []}
        for h in range(2):
            free = f[j] == 0
            if free.sum() < 2:
                row["hands"].append(None)
                continue
            loc = dd9.Local(P, j, h, free)
            g0 = g[j, :, h, :]
            J, fi = dd9.jacobian(loc, g0)
            Pr = dd9.gauge_projector(g0, fi, 4)
            r_full = dd9.spectral_radius(J, Pr)
            nf = len(fi)
            within = []
            for d in range(4):
                sel = np.flatnonzero(fi % 4 == d)
                if len(sel) < 2:
                    within.append(None)
                    continue
                ix = np.concatenate([sel, sel + nf])
                Jd = J[np.ix_(ix, ix)]
                Pd = dd9.gauge_projector(g0, fi[sel], 4)
                within.append(dd9.spectral_radius(Jd, Pd))
            J1 = 2 * J - np.eye(2 * nf)
            r_i1 = math.sqrt(dd9.spectral_radius(J @ J1, Pr))
            J2, _ = dd9.jacobian(loc, g0, "I2")
            J3, _ = dd9.jacobian(loc, g0, "I3")
            H = loc.joint(g0[None])[0]  # (nant, D, D)
            dg = np.sqrt(np.abs(np.einsum("add->ad", H)))
            ov = np.abs(H) / np.maximum(dg[:, :, None] * dg[:, None, :], 1e-300)
            okp = free[:, :, None] & free[:, None, :]
            overlap = {f"{a}{b}": float(np.median(ov[:, a, b][okp[:, a, b]])) if okp[:, a, b].any() else None
                       for a in range(4) for b in range(a + 1, 4)}  # fmt: skip
            row["hands"].append({"rho_full": r_full, "rho_within": within, "rho_I1": r_i1,
                                 "rho_I2": dd9.spectral_radius(J2, Pr), "rho_I3": dd9.spectral_radius(J3, Pr),
                                 "overlap_median": overlap, "nfree": int(nf),
                                 "signal": [float(loc.A[..., d, d].real.sum()) for d in range(4)]})  # fmt: skip
        out.append(row)
        print(j, json.dumps(row["hands"][0] and {k: row["hands"][0][k] for k in ("rho_full", "rho_within", "rho_I1", "rho_I2", "rho_I3")}),
              f"{time.perf_counter() - t0:.0f}s", flush=True)  # fmt: skip
    dd9.write_json(
        (root / "jac" if at == "default" else root / "jac" / f"at-{at}")
        / f"{base}-{start}-{stop}.json",
        {"base": base, "rows": out},
    )


def tau(r):
    return -1.0 / math.log(r) if r is not None and 0 < r < 1 else float("inf")


def spearman(a, b):
    from scipy.stats import spearmanr

    return float(spearmanr(a, b).statistic)


def readings_a(root):
    """Ra1 and Ra2 from the jac files and the default histories."""
    root = Path(root)
    rec = {}
    data = {}
    for base in ("B-X", "O-X"):
        rows = []
        for p in sorted((root / "jac").glob(f"{base}-*.json")):
            rows += json.loads(p.read_text())["rows"]
        rows.sort(key=lambda r: r["interval"])
        sj = json.loads((root / "solve" / f"{base}-default.json").read_text())
        nconv, s0 = np.array(sj["N_conv"]), np.array(sj["s0"])
        rf, tw, wd, npred, r1, r2, r3 = [], [], [], [], [], [], []
        for r in rows:
            hs = [x for x in r["hands"] if x]
            if not hs:
                rf.append(np.nan)
                tw.append(np.nan)
                wd.append(-1)
                npred.append(np.nan)
                r1.append(np.nan)
                r2.append(np.nan)
                r3.append(np.nan)
                continue
            hm = max(hs, key=lambda x: x["rho_full"])
            rf.append(hm["rho_full"])
            wt = [tau(x) for x in hm["rho_within"]]
            tw.append(max(wt))
            wd.append(int(np.argmax(wt)))
            npred.append(
                tau(hm["rho_full"])
                * math.log(max(s0[r["interval"]], 1e-300) / dd9.STOP)
            )
            r1.append(max(x["rho_I1"] for x in hs))
            r2.append(max(x["rho_I2"] for x in hs))
            r3.append(max(x["rho_I3"] for x in hs))
        idx = [r["interval"] for r in rows]
        data[base] = {"interval": idx, "rho_full": rf, "tau_full": [tau(x) for x in rf], "tau_within": tw,
                      "within_dir": wd, "N_pred": npred, "N_conv": nconv[idx].tolist(), "rho_I1": r1,
                      "rho_I2": r2, "rho_I3": r3}  # fmt: skip
    common = [
        i
        for i in data["B-X"]["interval"]
        if data["B-X"]["N_conv"][i] <= 2000 and data["O-X"]["N_conv"][i] <= 2000
    ]
    use = common if len(common) >= 20 else data["B-X"]["interval"]
    rec["intervals_used"] = len(use)
    rec["intervals_converged_at_2000_both"] = len(common)
    nc, npd = [], []
    for base in ("B-X", "O-X"):
        d = data[base]
        for i in use:
            if np.isfinite(d["N_pred"][i]):
                nc.append(d["N_conv"][i])
                npd.append(d["N_pred"][i])
    rho_s = spearman(nc, npd)
    med = {
        b: (
            float(np.nanmedian([data[b]["N_conv"][i] for i in use])),
            float(np.nanmedian([data[b]["N_pred"][i] for i in use])),
        )
        for b in data
    }
    ratio_conv = med["O-X"][0] / med["B-X"][0]
    ratio_pred = med["O-X"][1] / med["B-X"][1]
    f = max(ratio_pred / ratio_conv, ratio_conv / ratio_pred)
    ra1 = (
        "explains"
        if rho_s >= 0.7 and f <= 2
        else "partly"
        if rho_s >= 0.4 or f <= 3
        else "does not explain"
    )
    rec["Ra1"] = {"spearman_Nconv_Npred": rho_s, "median_N_conv": {b: med[b][0] for b in med},
                  "median_N_pred": {b: med[b][1] for b in med}, "ratio_conv": ratio_conv, "ratio_pred": ratio_pred,
                  "factor": f, "reading": ra1}  # fmt: skip
    for base in ("B-X", "O-X"):
        d = data[base]
        kap = [
            1 - d["tau_within"][i] / d["tau_full"][i]
            for i in use
            if np.isfinite(d["tau_full"][i])
        ]
        wdir = np.bincount(
            [d["within_dir"][i] for i in use if d["within_dir"][i] >= 0], minlength=4
        ).tolist()
        mk = float(np.median(kap))
        rec[f"kappa_{base}"] = {"median": mk, "p10": float(np.percentile(kap, 10)), "p90": float(np.percentile(kap, 90)),
                                "within_dir_counts": wdir,
                                "median_tau_full": float(np.median([d["tau_full"][i] for i in use])),
                                "median_tau_within": float(np.median([d["tau_within"][i] for i in use])),
                                "median_rho": {k: float(np.nanmedian([d[k][i] for i in use])) for k in ("rho_full", "rho_I1", "rho_I2", "rho_I3")}}  # fmt: skip
    mk = rec["kappa_O-X"]["median"]
    rec["Ra2"] = ("facet coupling dominates (Ha1)" if mk >= 0.5 else
                  f"within-facet conditioning dominates (Ha2), d{int(np.argmax(rec['kappa_O-X']['within_dir_counts']))}" if mk <= 0.2
                  else "both")  # fmt: skip
    dd9.write_json(
        root / "jac" / "readings.json", {"readings": rec, "per_interval": data}
    )
    print(json.dumps(rec, indent=1, default=float))


# -- part (b) -------------------------------------------------------------------------


def arm_problem(S_path, arm, drop=None):
    lam = dd9.k_noise() / dd9.SIGMA_A**2
    if arm == "bM":
        S = dd9.Sums(S_path, drop=drop, T=dd9.merge_matrix(4, 3, 1))
        return S, dd9.Problem(S, np.arange(S.nblock), [1] * 3), [1] * 3, [0, 1, 2, 1]
    S = dd9.Sums(S_path, drop=drop)
    if arm == "bP":
        return (
            S,
            dd9.Problem(S, np.arange(S.nblock), [1] * 4, pinned=(3,)),
            [1] * 4,
            None,
        )
    if arm == "bR":
        return (
            S,
            dd9.Problem(S, np.arange(S.nblock), [1] * 4, lam=[0, 0, 0, lam]),
            [1] * 4,
            None,
        )
    if arm == "bL":
        return S, dd9.Problem(S, np.arange(S.nblock), [1, 1, 1, 4]), [1, 1, 1, 4], None
    return S, dd9.Problem(S, np.arange(S.nblock), [1] * 4), [1] * 4, None


def as4(res, dirmap):
    """A merged solution in four-direction form (d3's gain = d1's)."""
    if dirmap is None:
        return res
    return {key: [res[key][d] for d in dirmap] for key in ("g", "f", "g2", "f2")} | {
        "iterations": res["iterations"],
        "fraction": res["fraction"],
    }


def partb(root, base="O"):
    """Section 5's arms on O (base O) or O-H (base O-H: held-out dropped)."""
    root = Path(root)
    tr = truth(root)
    k = dd9.k_noise()
    path = root / "sums" / "O-M0c.npz"
    drop = None
    if base == "O-H":
        S0 = dd9.Sums(path)
        drop = S0.mask_of(
            json.loads((dd9.DD8_ROOT / "heldout.json").read_text())["pairs"]
        )
    rec = {}
    for arm in ARMS_B:
        t0 = time.perf_counter()
        S, P, m, dirmap = arm_problem(path, arm, drop)
        res = dd9.run(P, CAPS)
        res4 = {K: as4(res[K], dirmap) for K in CAPS}
        m4 = [m[d] for d in dirmap] if dirmap else m
        save(root / "solve" / f"{base}-{arm}.npz", res4)
        S4 = dd9.Sums(path, drop=drop)
        rec[arm] = {}
        for K in CAPS:
            r = sol_record(res4[K], tr, S4, m4, k)
            if dirmap:
                r["ehat"] = [
                    dd9.ehat_dir(S, np.arange(S.nblock), m[d], d, k)
                    for d in range(S.ndir)
                ]
            r["d3_amp"] = dd9.amp_tail(res4[K]["g"][3], res4[K]["f"][3])
            rec[arm][f"cap{K}"] = r
        rec[arm]["m"] = m4
        rec[arm]["seconds"] = time.perf_counter() - t0
        print(arm, json.dumps(rec[arm]["cap500"], default=float), flush=True)
    rec["lambda"] = k / dd9.SIGMA_A**2
    if base == "O":
        rec["rule"] = rule_b(rec)
    dd9.write_json(root / "solve" / f"partb-{base}.json", rec)


def rule_b(rec):
    e0 = rec["b0"]["cap500"]["e_d1_d3"]
    out = {}
    best, best_v = None, float("inf")
    for arm in ARMS_B[1:]:
        a = rec[arm]
        tames = all(
            a[f"cap{K}"]["d3_amp"]["max"] <= 10 and a[f"cap{K}"]["d3_amp"]["p99"] <= 3
            for K in CAPS
        )
        e = a["cap500"]["e_d1_d3"]
        ratio = [x / y for x, y in zip(e, e0, strict=True)]
        improves = all(r <= 0.8 for r in ratio)
        harms = ratio[0] > 1.2 or ratio[1] > 1.2
        per = [
            "improves" if r <= 0.8 else "harms" if r > 1.2 else "unchanged"
            for r in ratio
        ]
        if not tames:
            reading = "the constraint fails on O"
        elif improves:
            reading = "the constraint works on O"
        elif harms:
            reading = "the constraint moves the error into the neighbours"
        elif per[0] == "unchanged" and per[1] == "unchanged":
            reading = "d3 tamed, d1/d2 truth error unchanged"
        else:
            reading = "tames; mixed (no frozen row)"
        out[arm] = {
            "tames_d3": bool(tames),
            "e_ratio_d1_d3": ratio,
            "per_direction": per,
            "reading": reading,
        }
        if arm != "bP" and tames and not harms and max(ratio) < best_v:
            best, best_v = arm, max(ratio)
    out["best"] = best
    return out


# -- part (c) -------------------------------------------------------------------------


def score_set(S_score, sols, held_bl, k, name):
    blocks = np.arange(S_score.nblock)
    return dd9.robust_score(S_score, blocks, sols, held_bl, k)[0]


def partc_validate(root):
    """Section 6: the robust score on O-H's arms against their truth error."""
    root = Path(root)
    k = dd9.k_noise()
    path = root / "sums" / "O-M0c.npz"
    S = dd9.Sums(path)
    held = np.flatnonzero(
        S.mask_of(json.loads((dd9.DD8_ROOT / "heldout.json").read_text())["pairs"])
    )
    pb = json.loads((root / "solve" / "partb-O-H.json").read_text())
    sols = {}
    for arm in ARMS_B:
        r = load(root / "solve" / f"O-H-{arm}.npz", 500, 4)
        sols[arm] = (r["g"], r["f"], pb[arm]["m"])
    tr = truth(root)
    sols["truth"] = (
        [tr[:, :, d] for d in range(4)],
        [np.zeros(tr.shape[:2], np.int8)] * 4,
        [1] * 4,
    )
    rec = score_set(S, sols, held, k, "O-H")
    four = ["b0", "bM", "bR", "bL"]
    by_score = sorted(four, key=lambda a: rec["solutions"][a]["median"])
    by_truth = sorted(four, key=lambda a: np.mean(pb[a]["cap500"]["e_d1_d3"]))
    tracks = by_score[0] == by_truth[0] and by_score[-1] == by_truth[-1]
    rec["order_by_score"], rec["order_by_truth"] = by_score, by_truth
    rec["tracks_truth_on_O"] = bool(tracks)
    dd9.write_json(root / "score" / "O-H.json", rec)
    print(json.dumps(rec, indent=1, default=float))


def partc_real(root):
    """Section 6's real arms: RM, d0 free, the 145 bad and 169 held-out
    baselines removed; scored on the held-out ones."""
    root = Path(root)
    dd7 = dd9._dd8().dd7
    k = dd9.k_noise()
    path = root / "sums" / "real-RM.npz"
    S0 = dd9.Sums(path)
    held_mask = S0.mask_of(
        json.loads((dd9.DD8_ROOT / "heldout.json").read_text())["pairs"]
    )
    bad_mask = S0.mask_of(dd7.bad_pairs())
    assert not (held_mask & bad_mask).any()
    drop = held_mask | bad_mask
    rule = json.loads((root / "solve" / "partb-O.json").read_text())["rule"]
    best = rule["best"]
    arms = ["b0", best] if best else ["b0", "bM", "bR", "bL"]
    rec = {"best_from_O": best, "dropped_baselines": int(drop.sum()), "bad": int(bad_mask.sum()),
           "heldout": int(held_mask.sum()), "arms": {}}  # fmt: skip
    sols = {}
    for arm in arms:
        t0 = time.perf_counter()
        _, P, m, dirmap = arm_problem(path, arm, drop)
        res = dd9.run(P, [500])
        r4 = as4(res[500], dirmap)
        m4 = [m[d] for d in dirmap] if dirmap else m
        save(root / "solve" / f"real-{arm}.npz", {500: r4})
        fr, _ = dd9.perdir(r4)
        rec["arms"][arm] = {"fraction": fr, "iterations": r4["iterations"], "d3_amp": dd9.amp_tail(r4["g"][3], r4["f"][3]),
                            "seconds": time.perf_counter() - t0}  # fmt: skip
        sols[f"real-{arm}"] = (r4["g"], r4["f"], m4)
    sols["unit"] = (
        [np.ones((1, S0.nant, 2), complex)] * 4,
        [np.zeros((1, S0.nant), np.int8)] * 4,
        [10**9] * 4,
    )
    sc = score_set(S0, sols, np.flatnonzero(held_mask), k, "real")
    rec["score"] = sc
    val = json.loads((root / "score" / "O-H.json").read_text())
    rec["called"] = (
        "accuracy proxy" if val["tracks_truth_on_O"] else "predictive quality only"
    )
    if best:
        pr = sc["pairs"][f"real-b0 - real-{best}"]
        rec["reading"] = ("the constraint predicts better" if pr["significant"] and pr["median"] > 0 else
                          "the constraint predicts worse" if pr["significant"] else "no difference")  # fmt: skip
    dd9.write_json(root / "score" / "real.json", rec)
    print(json.dumps(rec, indent=1, default=float))


def dd8robust(root):
    """Section 6, post hoc: DD8's kept per-baseline sums in the robust form."""
    root = Path(root)
    rec = {}
    for base in ("B-H", "O-H", "real-H"):
        z = np.load(DD8_SCORE / f"{base}.npz")
        names = [str(x) for x in z["names"]]
        N = z["N"]
        ok = N > 0
        Hb = {n: z[f"S_{n}"][ok] / N[ok] for n in names}
        r = {"baselines": int(ok.sum()), "solutions": {}, "pairs": {}, "dH_robust": {}}
        for n in names:
            r["solutions"][n] = {"median": float(np.median(Hb[n])), "trimmed_mean": dd9.trimmed_mean(Hb[n]),
                                 "mean": float(Hb[n].mean())}  # fmt: skip
            SF = z[f"SF_{n}"]
            r["dH_robust"][n] = [
                dd9.bootstrap_median((SF[f][ok] - z[f"S_{n}"][ok]) / N[ok])
                for f in range(SF.shape[0])
            ]
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                r["pairs"][f"{a} - {b}"] = dd9.bootstrap_median(Hb[a] - Hb[b])
        rec[base] = r
    dd9.write_json(root / "score" / "dd8-robust.json", rec)
    print(json.dumps(rec, indent=1, default=float))


# -- the Rust point -------------------------------------------------------------------


def rustbm(root):
    """bM on O in rang's Rust kernel (no solver change): model columns M0c's
    d0, d1 + d3, d2."""
    from rang import cal_gain

    root = Path(root)
    dd8 = dd9._dd8()
    dd4, dd6 = dd8.dd4, dd8.dd6
    t0 = time.perf_counter()
    run = root / "O"
    ctx = dd4.context(run, ti=4)
    c = ctx["c"]
    idx = dd6.facet_idx(run)
    m = np.load(dd9.DD7_ROOT / "b" / "sky.npy")
    models = np.zeros(c["DATA"].shape[:2] + (3, 4), np.complex64)
    for f, col in ((0, 0), (1, 1), (2, 2), (3, 1)):
        v = dd8.facet_vis(c["UVW"], c["freq"], idx, m, f)
        models[:, :, col, 0] += v
        models[:, :, col, 3] += v
        del v
    args = (
        c["DATA"],
        models,
        c["WEIGHT_SPECTRUM"],
        c["FLAG"],
        c["FLAG_ROW"],
        c["ANTENNA1"],
        c["ANTENNA2"],
        ctx["block"],
    )
    kw = {"nant": len(c["ant_names"]), "refant": None, "pinned_directions": [], "calmode": "ap",
          "phase_last_direction_gain": False, "stop_criterion": dd9.STOP}  # fmt: skip
    t1 = time.perf_counter()
    sol = cal_gain.solve_dd(
        *args, **kw, max_iterations=500, stop_fraction=dd9.STOP_FRACTION
    )
    t2 = time.perf_counter()
    sol2 = cal_gain.solve_dd(
        *args, **kw, max_iterations=sol.iterations + 1, stop_fraction=1.0
    )
    t3 = time.perf_counter()
    g, f = np.asarray(sol.gains), np.asarray(sol.flags)
    conv = dd4.per_cell_converged(sol.gains, sol2.gains, sol.flags, sol2.flags)
    per = dd4.per_direction_converged(
        np.asarray(sol.gains), np.asarray(sol2.gains), f, np.asarray(sol2.flags)
    )
    np.savez_compressed(
        root / "gates" / "rust-bM.npz", gains=g, flags=f, converged=conv
    )
    ref = load(root / "solve" / "O-bM.npz", 500, 4)
    rg = [ref["g"][d] for d in (0, 1, 2)]
    rf = [ref["f"][d] for d in (0, 1, 2)]
    fr, masks = dd9.perdir(
        {
            "g": rg,
            "f": rf,
            "g2": [ref["g2"][d] for d in (0, 1, 2)],
            "f2": [ref["f2"][d] for d in (0, 1, 2)],
        }
    )
    gs, _ = dd9.stack_sol(rg, rf)
    pdiff = dd9.product_diff(gs[:, 0], g[:, 0], np.stack(masks, -1), conv[:, 0])
    flagged_r = [int((f[..., d] != 0).sum()) for d in range(3)]
    flagged_ref = [int((x != 0).sum()) for x in rf]
    dfrac = [abs(a - b) for a, b in zip(fr, per, strict=True)]
    dflag = [
        abs(a - b) / max(b, 1) for a, b in zip(flagged_ref, flagged_r, strict=True)
    ]
    pmax = max(x["max"] or 0 for x in pdiff)
    rec = {"fraction_rust": per, "fraction_ref": fr, "iterations_rust": sol.iterations, "flagged_rust": flagged_r,
           "flagged_ref": flagged_ref, "product_diff_converged": pdiff,
           "pass": bool(max(dfrac) <= 0.005 and max(dflag) <= 0.01 and pmax <= 1e-6),
           "seconds_predict": t1 - t0, "seconds_solve": t2 - t1, "seconds_second_solve": t3 - t2}  # fmt: skip
    dd9.write_json(root / "gates" / "rust-bM.json", rec)
    print(json.dumps(rec, indent=1, default=float))
