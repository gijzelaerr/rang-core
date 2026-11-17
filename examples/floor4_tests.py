"""floor-4 (research/floor-4.md): H1's specificity under imaging-floor's full criterion, and the XX-YY phase.

Imports floor_tests, floor2_tests and floor3_score unchanged. Paths: RANG_FLOOR_HELD points at the
copy of `D:/rang/outputs/20261103-gemclean-heldout/real` (on nash
`~/rang-data/outputs/20261103-gemclean-heldout/real`). Stages:

    sim      prep (gate R0), truth 8 x 8 and pilot 4 x 4 facets, the arms of section 3 and the
             pilot's T1, T1p, T1L, T1pL (gate GS)
    x        X0-X3 of section 4 on G1's products (`--g1` = floor3_score's --out of G1)
    summary  gates and the frozen readings of sections 4-6
    clean    delete the visibility scratch (prep, skies, hands)

The per-hand helpers (`hands_prep`, `stokes_from_hands`, `row_bins`, `apply_store`) are shared
with examples/selfcal_grid.py.
"""

import argparse
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import floor2_tests as f2
import floor_tests as ft
from rang import cal_selfcal, core_ms, core_weights
from rang.core_imaging import read_fits

REPO = Path(__file__).resolve().parents[1]
IF_ARCH = REPO / "research/results/imaging-floor"
F2_ARCH = REPO / "research/results/floor-2"
T_ARCH = 44.09023909930619e-6
NEW_ARMS = {"H2": 25.144, "H8a": 6.38, "H4b": 50.0}
F3_FIX = {"B": 1073.415606729187, "Fix": 474.83100062889406, "Fin": 379.2621316115341}
F3_D = {"D_Fix": 0.8056811467899708, "D_Fin": 0.8766420601018318}


def setpaths():
    h = os.environ.get("RANG_FLOOR_HELD")
    if not h:
        return
    ft.HELD = Path(h).expanduser()
    ft.MS_A = ft.HELD / "cal2.ms"
    ft.TRUTH = ft.HELD / "run/cal3-003-gem-model.fits"
    ft.PILOT = ft.HELD / "run/cal2-003-gem-model.fits"
    ft.MASK = ft.HELD / "images/source-mask.fits"


setpaths()


# ---------------------------------------------------------------- per-hand helpers


def hands_prep(out, channels, ms=None):
    """XX and YY of `cal2.ms` (DATA, WEIGHT_SPECTRUM, FLAG, FLAG_ROW) on `channels`."""
    fn = out / "hands.npz"
    if fn.exists():
        z = np.load(fn)
        return {k: z[k] for k in z.files}
    ms = ft.MS_A if ms is None else Path(ms)
    channels = np.asarray(channels)
    with core_ms.open_table(str(ms)) as t:
        n = int(t.nrows)
        rows_ok = ~np.asarray(t.getcol("FLAG_ROW", 0, n), bool)
        tm = np.asarray(t.getcol("TIME", 0, n), np.float64)
        scan = np.asarray(t.getcol("SCAN_NUMBER", 0, n))
        fid = np.asarray(t.getcol("FIELD_ID", 0, n))
        nc = channels.size
        d = np.empty((n, nc, 2), np.complex64)
        w = np.empty((n, nc, 2), np.float32)
        f = np.empty((n, nc, 2), bool)
        for r0 in range(0, n, ft.ROWS):
            k = min(ft.ROWS, n - r0)
            x = t.getcol("DATA", r0, k)[:, channels]
            y = t.getcol("WEIGHT_SPECTRUM", r0, k)[:, channels]
            z = t.getcol("FLAG", r0, k)[:, channels]
            sel = [0, -1]  # XX and YY of two or four correlations
            d[r0 : r0 + k] = x[..., sel]
            w[r0 : r0 + k] = y[..., sel]
            f[r0 : r0 + k] = z[..., sel]
    out.mkdir(parents=True, exist_ok=True)
    np.savez(fn, d=d, w=w, f=f, rows_ok=rows_ok, time=tm, scan=scan, field=fid)
    return {
        "d": d,
        "w": w,
        "f": f,
        "rows_ok": rows_ok,
        "time": tm,
        "scan": scan,
        "field": fid,
    }


def stokes_from_hands(xx, yy, w, f, rows_ok):
    """Stokes I as floor_tests.prep builds it from two correlations: [XX, XX, YY, YY]."""
    v = np.empty(xx.shape, np.complex64)
    g = np.empty(xx.shape, np.float32)
    for r0 in range(0, xx.shape[0], ft.ROWS):
        s = slice(r0, r0 + ft.ROWS)
        d4 = np.stack([xx[s], xx[s], yy[s], yy[s]], -1)
        w4 = np.stack([w[s, :, 0], w[s, :, 0], w[s, :, 1], w[s, :, 1]], -1)
        f4 = np.stack([f[s, :, 0], f[s, :, 0], f[s, :, 1], f[s, :, 1]], -1)
        v[s], g[s] = core_weights.stokes_i(d4, w4, f4)
    g *= rows_ok[:, None]
    return v, g


def row_bins(h, solint):
    tb, _bs, _gt = cal_selfcal.time_bins(h["time"], h["scan"], h["field"], solint)
    return tb


def store_gains(store, name):
    g, flags, gt, _gf, _sc = cal_selfcal.read_store(store, name)
    g = g[:, 0]  # (time bin, antenna, hand), frequency independent
    valid = ~flags[:, 0] & np.isfinite(g).all(-1)
    return g, valid, gt


def apply_store(h, g, valid, tb, a1, a2, scalar=False):
    """V / (g_p conj g_q) per hand; cells with an invalid gain flagged (cal_apply's rule)."""
    if scalar:
        px, py = np.angle(g[..., 0]), np.angle(g[..., 1])
        ps = px + np.angle(np.exp(1j * (py - px))) / 2
        g = np.repeat(np.exp(1j * ps)[..., None], 2, axis=-1)
    gp = g[tb, a1]  # (row, hand)
    gq = g[tb, a2]
    ok = valid[tb, a1] & valid[tb, a2]
    den = gp * np.conj(gq)
    den = np.where(ok[:, None], den, 1.0)
    xx = (h["d"][..., 0] / den[:, None, 0]).astype(np.complex64)
    yy = (h["d"][..., 1] / den[:, None, 1]).astype(np.complex64)
    f = h["f"] | ~ok[:, None, None]
    return xx, yy, f, ok


def floor_with(d, vis, model_vis, gw=None):
    return ft.floor(d, ft.grid(d, vis - model_vis, gw))


def model_vis(d, path):
    img, _ = read_fits(path)
    img = np.asarray(img, np.float64).reshape(img.shape[-2:])
    return ft.predict(d, img)


# ---------------------------------------------------------------- simulations (section 3)


def tests4(d, V, Y0):
    """none, T1, T1p, T1L, T1pL against the facet set Y0 (5-min bins, floor-2's StefCal)."""
    res = {}
    M = ft.total(Y0)
    res["none"] = {"F": ft.floor(d, ft.grid(d, V - M))}
    nsb = int(d.bin5.max()) + 1
    longw = d.wnat * (~d.short)[:, None]
    gains = {}
    for name, kw in (
        ("T1", {}),
        ("T1p", {"phase_only": True}),
        ("T1L", {"w": longw}),
        ("T1pL", {"w": longw, "phase_only": True}),
    ):
        f, g = f2.stefcal(d, V, M, d.bin5, nsb, **kw)
        gains[name] = g
        res[name] = {"F": ft.floor(d, ft.grid(d, V - M * f[:, None]))}
    return res, gains


def sim_arm(d, out, name, k, extra=None):
    fn = out / "arms" / f"{name}-{k:g}.json"
    if fn.exists():
        return json.loads(fn.read_text())
    (out / "arms").mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    if name in NEW_ARMS or name == "C":
        V = ft.make_arm(d, out, name, k)
    else:
        V, _ = f2.make(d, out, name, k, extra)
    Y0 = ft.load_set(out, "truth")["facets"]
    r, g = tests4(d, V, Y0)
    np.savez(out / "arms" / f"{name}-{k:g}-gains.npz", **g)
    r["k"] = k
    r["wall_s"] = time.perf_counter() - s0
    ft.wjson(fn, r)
    ft.log(
        "arm",
        name,
        k,
        {t: round(v["F"] * 1e6, 3) for t, v in r.items() if isinstance(v, dict)},
    )
    return r


def cmd_sim(out):
    out.mkdir(parents=True, exist_ok=True)
    ft.prep(out)
    d = ft.Data(out)
    truth, _ = read_fits(ft.TRUTH)
    pilot, _ = read_fits(ft.PILOT)
    ft.sky_set(d, out, "truth", truth, nf=8, alts=False)
    ft.sky_set(d, out, "pilot", pilot, nf=4, alts=False)
    sim_arm(d, out, "C", 1)
    sim_arm(d, out, "H1bP", 6.862)
    for name, k in NEW_ARMS.items():
        sim_arm(d, out, name, k)
    sim_arm(d, out, "H1bP", 5)
    active, _sh, _ = f2.antenna_stats(d)
    r = f2.enu(out)[: d.nant]
    gbar = f2.gauge(np.load(F2_ARCH / "pilot-gains.npz")["T1p"], active, r)["gbar"]
    gp = np.where(active, np.exp(1j * np.angle(gbar)), 1.0)
    sim_arm(d, out, "G3P", 1, {"g": gp})
    fn = out / "pilot.json"
    if not fn.exists():
        Y0 = ft.load_set(out, "pilot")["facets"]
        res, g = tests4(d, d.vis.astype(np.complex64), Y0)
        np.savez(out / "pilot-gains.npz", **g)
        ft.wjson(fn, res)
        ft.log("pilot", {t: round(v["F"] * 1e6, 3) for t, v in res.items()})


# ---------------------------------------------------------------- XX - YY (section 4)


def wrap(x):
    return np.angle(np.exp(1j * x))


def cmd_x(out, g1):
    """X0-X3 on G1 (floor3_score's arm P on nash) and the pilot subset."""
    fn = out / "x.json"
    if fn.exists():
        return
    d = ft.Data(out)
    h = hands_prep(out / "hands", ft.CHANNELS)
    # self-check: the hands give prep's Stokes I exactly
    v0, g0 = stokes_from_hands(
        h["d"][..., 0], h["d"][..., 1], h["w"], h["f"], h["rows_ok"]
    )
    check = {
        "vis_equal": bool(np.array_equal(v0, d.vis)),
        "wnat_equal": bool(np.array_equal(g0, d.wnat)),
    }
    run = Path(g1) / "P" / "run"
    s = json.loads((run / "selfcal/summary.json").read_text())
    rnd = s["fields"][0]["rounds"][0]
    store = rnd["store"]
    g, valid, _gt = store_gains(store, rnd["term"].get("name") or "Sp")
    tb = row_bins(h, rnd["term"]["solint"])
    (m1,) = sorted(Path(store).parent.glob("*-model.fits"))
    M1 = model_vis(d, m1)
    active, _sh, _ = f2.antenna_stats(d)
    act = active & valid.all(0)
    # X0
    delta = np.angle(np.mean(g[..., 0] * np.conj(g[..., 1]), axis=0))
    c = float(np.angle(np.mean(np.exp(1j * delta[act]))))
    sc = wrap(delta - c)
    r = f2.enu(out)[: d.nant]
    X = np.column_stack([np.ones(act.sum()), r[act]])
    coef = np.linalg.lstsq(X, sc[act], rcond=None)[0]
    sg = sc[act] - X @ coef
    nb = g.shape[0]
    per_bin = wrap(np.angle(g[..., 0] * np.conj(g[..., 1])) - delta[None, :])
    x0 = {
        "rms_deg": float(np.degrees(np.sqrt(np.mean(delta[act] ** 2)))),
        "circular_mean_deg": math.degrees(c),
        "scatter_deg": float(np.degrees(np.sqrt(np.mean(sc[act] ** 2)))),
        "scatter_after_gauge_deg": float(np.degrees(np.sqrt(np.mean(sg**2)))),
        "bin_scatter_deg": float(np.degrees(np.sqrt(np.mean(per_bin[:, act] ** 2)))),
        "noise_of_steady_deg": float(
            np.degrees(np.sqrt(np.mean(per_bin[:, act] ** 2)) / math.sqrt(nb))
        ),
        "n_active": int(act.sum()),
        "n_bins": int(nb),
    }
    # X1: bins 1-6 against 7-12
    half = nb // 2
    da = np.angle(np.mean((g[..., 0] * np.conj(g[..., 1]))[:half], axis=0))
    db = np.angle(np.mean((g[..., 0] * np.conj(g[..., 1]))[half:], axis=0))
    da = wrap(da - np.angle(np.mean(np.exp(1j * da[act]))))
    db = wrap(db - np.angle(np.mean(np.exp(1j * db[act]))))
    x1 = {
        "pearson_r": float(np.corrcoef(da[act], db[act])[0, 1]),
        "halves": [half, nb - half],
    }
    # X2: per hand against scalar projection, same solve, against G1's round-1 model
    T = T_ARCH
    PB = json.loads((Path(g1) / "P" / "score.json").read_text())

    def score_apply(scalar):
        xx, yy, f, _ok = apply_store(h, g, valid, tb, d.a1, d.a2, scalar=scalar)
        v, w = stokes_from_hands(xx, yy, h["w"], f, h["rows_ok"])
        gw = np.where(w > 0, d.gw, 0.0).astype(np.float32)
        return floor_with(d, v, M1, gw), float(
            1 - np.count_nonzero(gw) / np.count_nonzero(d.gw)
        )

    FB = floor_with(d, d.vis, M1)
    Fh, newly_h = score_apply(False)
    Fs, newly_s = score_apply(True)

    def D(F0, F):
        return (F0**2 - F**2) / (F0**2 - T**2)

    x2 = {
        "F_B_uJy": FB * 1e6,
        "F_per_hand_uJy": Fh * 1e6,
        "F_scalar_uJy": Fs * 1e6,
        "D_per_hand": D(FB, Fh),
        "D_scalar": D(FB, Fs),
        "dD": D(FB, Fh) - D(FB, Fs),
        "newly_flagged": [newly_h, newly_s],
        "HB1_F_Fix_floor3_score_uJy": PB["F_uJy"]["Fix"],
        "HB1_rel": Fh * 1e6 / PB["F_uJy"]["Fix"] - 1,
    }
    x2["HB1_pass"] = abs(x2["HB1_rel"]) <= 1e-4
    # X3: matched numpy solvers, data-side correction, pilot model facets
    M = ft.total(ft.load_set(out, "pilot")["facets"])
    nsb = int(d.bin5.max()) + 1
    _f, gs = f2.stefcal(d, d.vis, M, d.bin5, nsb, phase_only=True)
    wX = np.where(h["f"][..., 0], 0.0, h["w"][..., 0]) * h["rows_ok"][:, None]
    wY = np.where(h["f"][..., 1], 0.0, h["w"][..., 1]) * h["rows_ok"][:, None]
    hx = np.where(wX > 0, h["d"][..., 0], 0).astype(np.complex64)
    hy = np.where(wY > 0, h["d"][..., 1], 0).astype(np.complex64)
    _fx, gx = f2.stefcal(
        d, hx, M, d.bin5, nsb, w=wX.astype(np.float32), phase_only=True
    )
    _fy, gy = f2.stefcal(
        d, hy, M, d.bin5, nsb, w=wY.astype(np.float32), phase_only=True
    )
    del hx, hy
    allv = np.ones((nsb, d.nant), bool)
    tb5 = d.bin5
    Fx3 = {}
    for name, gg in (
        ("T1p", np.stack([gs, gs], -1)),
        ("T1pH", np.stack([gx, gy], -1)),
    ):
        xx, yy, f, _ok = apply_store(h, gg, allv, tb5, d.a1, d.a2)
        v, _w = stokes_from_hands(xx, yy, h["w"], f, h["rows_ok"])
        Fx3[name] = floor_with(d, v, M)
    F0 = floor_with(d, d.vis, M)
    x3 = {
        "F_none_uJy": F0 * 1e6,
        "F_T1p_uJy": Fx3["T1p"] * 1e6,
        "F_T1pH_uJy": Fx3["T1pH"] * 1e6,
        "D_T1p": D(F0, Fx3["T1p"]),
        "D_T1pH": D(F0, Fx3["T1pH"]),
    }
    x3["dD"] = x3["D_T1pH"] - x3["D_T1p"]
    dT1pH = np.angle(np.mean(gx * np.conj(gy), axis=0))
    x3["T1pH_xx_minus_yy_scatter_deg"] = float(
        np.degrees(
            np.sqrt(
                np.mean(
                    wrap(dT1pH - np.angle(np.mean(np.exp(1j * dT1pH[act]))))[act] ** 2
                )
            )
        )
    )
    x3["T1pH_vs_Sp_delta_pearson_r"] = float(
        np.corrcoef(
            wrap(dT1pH - np.angle(np.mean(np.exp(1j * dT1pH[act]))))[act], sc[act]
        )[0, 1]
    )
    res = {
        "check": check,
        "X0": x0,
        "X1": x1,
        "X2": x2,
        "X3": x3,
        "store": str(store),
        "model": str(m1),
    }
    ft.wjson(fn, res)
    ft.log("x", json.dumps(res, default=float)[:2000])


# ---------------------------------------------------------------- summary (sections 5-6)


def drops(r, T):
    P0 = r["none"]["F"] ** 2 - T**2
    return {
        "P_over_Ppilot": None,
        "P_none": P0,
        **{
            k: (P0 - (v["F"] ** 2 - T**2)) / P0
            for k, v in r.items()
            if isinstance(v, dict) and k != "none"
        },
    }


def cmd_summary(out, g1):
    ifs = json.loads((IF_ARCH / "summary.json").read_text())
    f2s = json.loads((F2_ARCH / "summary.json").read_text())
    f2p = json.loads((F2_ARCH / "pilot.json").read_text())
    Ppil = ifs["P_pilot"]
    res = {"P_pilot": Ppil, "T": T_ARCH}
    # R0
    meta = json.loads((out / "prep/meta.json").read_text())
    am = json.loads((IF_ARCH / "prep-meta.json").read_text())
    res["R0"] = {
        "nrow": meta["nrow"] == am["nrow"],
        "active": meta["active"] == am["active"],
        "noise_c_rel": meta["noise_c"] / am["noise_c"] - 1,
        "gw_sum_rel": meta["gridding_weight_sum"] / am["gridding_weight_sum"] - 1,
    }
    res["R0"]["pass"] = (
        res["R0"]["nrow"]
        and res["R0"]["active"]
        and abs(res["R0"]["noise_c_rel"]) <= 1e-6
        and abs(res["R0"]["gw_sum_rel"]) <= 1e-6
    )
    arms = {}
    for fn in sorted((out / "arms").glob("*.json")):
        if fn.name.endswith("-baselines.json"):
            continue
        r = json.loads(fn.read_text())
        key = fn.stem.replace("-", "@", 1)
        dd = drops(r, T_ARCH)
        dd["P_over_Ppilot"] = dd["P_none"] / Ppil
        dd["F_uJy"] = r["none"]["F"] * 1e6
        arms[key] = dd
    pil = json.loads((out / "pilot.json").read_text())
    pd = drops(pil, T_ARCH)
    res["arms"], res["pilot"] = arms, pd
    res["pilot_F_uJy"] = {k: v["F"] * 1e6 for k, v in pil.items()}
    # GS
    gs = {"C": abs(arms["C@1"]["F_uJy"] / (T_ARCH * 1e6) - 1) <= 0.005}
    for k in ("none", "T1", "T1p", "T1L"):
        gs[f"pilot_{k}"] = abs(pil[k]["F"] / f2p[k]["F"] - 1) <= 0.005
    gs["H1bP_T1p"] = abs(arms["H1bP@6.862"]["T1p"] - 1.0) <= 0.02
    for name, k in NEW_ARMS.items():
        a = ifs["arms"][f"{name}@{k:g}"]
        gs[f"{name}_F"] = abs(arms[f"{name}@{k:g}"]["F_uJy"] / a["F_uJy"] - 1) <= 0.005
        gs[f"{name}_T1"] = abs(arms[f"{name}@{k:g}"]["T1"] - a["T1"]) <= 0.02
    res["GS"] = {"checks": gs, "pass": all(gs.values())}
    # S: specificity of T1p (and T1pL, reported)
    prior = {
        k: f2s["arms"][f"{k}@{f2s['a2'][k]:g}"]
        for k in ("K1", "K3", "K10", "XS2", "XS4", "XG4")
    }
    spec = {}
    for test in ("T1p", "T1pL", "T1L", "T1"):
        own = arms["H1bP@6.862"][test]
        others = {f"{n}@{k:g}": arms[f"{n}@{k:g}"][test] for n, k in NEW_ARMS.items()}
        for n, a in prior.items():
            if test in a:
                others[f"{n} (floor-2 prior)"] = a[test]
        worst = max(others, key=lambda x: others[x])
        spec[test] = {
            "own_H1bP": own,
            "others": others,
            "worst": [worst, others[worst]],
            "specific": own >= 0.7 and all(v <= 0.3 for v in others.values()),
        }
    res["S"] = spec
    D = pd["T1p"]
    Pp = {
        "H1bP@5": arms["H1bP@5"]["P_over_Ppilot"],
        "G3P@1": arms["G3P@1"]["P_over_Ppilot"],
    }
    Pplaus = max(Pp.values())
    res["Q"] = {
        "P_over_Ppilot": Pp,
        "P_plaus": Pplaus,
        "D_T1p_pilot": D,
        "holds": Pplaus >= 0.5 * D,
        "exceeds_by": max(D - Pplaus, 0.0),
    }
    gates_ok = res["R0"]["pass"] and res["GS"]["pass"]
    g1s = None
    if g1:
        p = Path(g1) / "P" / "score.json"
        if p.exists():
            sc = json.loads(p.read_text())
            g0 = json.loads((Path(g1) / "P" / "g0.json").read_text())
            g1s = {
                "G0": g0,
                "F_uJy": sc["F_uJy"],
                "D_Fix": sc["D_Fix"],
                "D_Fin": sc["D_Fin"],
                "F_rel": {k: sc["F_uJy"][k] / F3_FIX[k] - 1 for k in F3_FIX},
                "D_diff": {k: sc[k] - F3_D[k] for k in F3_D},
            }
            g1s["pass"] = (
                g0["pass"]
                and all(abs(v) <= 0.01 for v in g1s["F_rel"].values())
                and all(abs(v) <= 0.02 for v in g1s["D_diff"].values())
            )
            res["G1"] = g1s
    if not gates_ok:
        row = "void: a gate failed"
    elif not spec["T1p"]["specific"]:
        row = f"row 2: T1p not specific (worst {spec['T1p']['worst']}); H1 unresolved under the full criterion"
    elif not res["Q"]["holds"]:
        row = "row 3: plausibility fails; unresolved"
    else:
        row = "row 1: H1 attributed under imaging-floor's full criterion, share D_T1p"
    res["reading"] = row
    xfn = out / "x.json"
    if xfn.exists():
        x = json.loads(xfn.read_text())
        r1 = x["X1"]["pearson_r"]
        rep = "repeatable" if r1 >= 0.7 else ("noise-like" if r1 < 0.3 else "partial")
        dd = [x["X2"]["dD"], x["X3"]["dD"]]
        if any(v >= 0.02 for v in dd):
            st = "reaches"
        elif any(v <= -0.02 for v in dd):
            st = "costs"
        else:
            st = "invisible"
        if rep == "repeatable" and st == "invisible":
            xr = "real steady XX-YY phase, invisible to Stokes I: a polarisation term, outside #13"
        elif rep == "repeatable" and st == "reaches":
            xr = "real differential phase carrying dD of the excess; part of the floor-3 share"
        elif rep == "noise-like":
            xr = "noise-like: the 17.7 deg is the gauge constant plus solve noise"
        else:
            xr = "undecided"
        res["X"] = {"X1": rep, "X2X3": st, "dD": dd, "reading": xr}
    ft.wjson(out / "summary.json", res)
    print(
        json.dumps(
            {k: res.get(k) for k in ("R0", "GS", "G1", "S", "Q", "reading", "X")},
            indent=1,
            default=float,
        )
    )


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["sim", "x", "summary", "clean"])
    p.add_argument("--out", required=True)
    p.add_argument("--g1", default=None, help="floor3_score --out of the G1 run")
    a = p.parse_args(argv)
    out = Path(a.out).expanduser()
    s0 = time.perf_counter()
    if a.stage == "sim":
        cmd_sim(out)
    elif a.stage == "x":
        cmd_x(out, a.g1)
    elif a.stage == "summary":
        cmd_summary(out, a.g1)
    elif a.stage == "clean":
        for sub in ("prep", "skies", "hands"):
            shutil.rmtree(out / sub, ignore_errors=True)
    ft.log("stage", a.stage, "wall_s", round(time.perf_counter() - s0, 1))


if __name__ == "__main__":
    sys.exit(main())
