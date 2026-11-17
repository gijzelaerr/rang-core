"""floor-5 (research/floor-5.md): what is left of the pilot's floor after one Sp round.

Imports floor_tests, floor2_tests and floor3_score unchanged. Paths: RANG_FLOOR_HELD points at
the copy of `D:/rang/outputs/20261103-gemclean-heldout/real` (on nash
`~/rang-data/outputs/floor-5-20261117/inputs/20261103-gemclean-heldout/real`). Stages:

    gates    R0 (prep) and G0 (DATA against the archived pilot model)
    skies    floor-2's sky sets (truth, pilot, K1, K3, K10 4 x 4; extended) and m1 with its
             rescoring alternatives
    pilot    S1 (numpy per-hand apply of the G1 store), gate HB, Family I on S1 against m1, E5
    arm X    one simulated arm's chain a1 -> a2 -> a_max with Family I's tests
    score    Family II: every GeMClean model in --models scored on the subset
    twobytwo T_A then T_B | A against m1 and against Dm03's model
    summary  gates and the frozen readings of section 6
    clean    delete the visibility scratch

The per-hand helpers re-implement floor-4's (`origin/floor-4:examples/floor4_tests.py`), which is
not on main.
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
T = 44.09023909930619e-6
F_ARCH = 1073.42e-6
G1_REF = {"B": 1073.415606729187, "Fix": 474.83100062889406, "Fin": 379.2621316115341}
CENTRAL4 = ft.CENTRAL4
# arm -> (builder, a1 multiple, a_max multiple or None)
ARMS = {
    "C": ("ft", 1, None),
    "H1a": ("ft", 1, 5),
    "H1bA": ("f2", 1, 5),
    "H2": ("ft", 1, 10),
    "H8a": ("ft", 1, 1 / 0.7),
    "H3c": ("f5", 1, 5),
    "K1": ("f2", 1, None),
    "K3": ("f2", 1, None),
    "XS2": ("f2", 1, None),
    "XS4": ("f2", 1, None),
    "XG4": ("f2", 1, None),
}
OWN = {"T_A": "H1bA", "T_Af": "H1a", "T_B|A": "H2", "T8": "H8a", "T_D|A": "H3c"}
HYP = {"T_A": "H1r", "T_Af": "H1a", "T_B|A": "H2", "T8": "H8", "T_D|A": "H3c"}
GS_ARMS = {"H2": 25.144, "H8a": 6.38}
RERUN = Path(os.environ.get("RANG_FLOOR5_G1RERUN", "/nonexistent"))


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


def P(F):
    return F**2 - T**2


def fits2d(path):
    img, _ = read_fits(path)
    return np.asarray(img, np.float64).reshape(img.shape[-2:])


# ---------------------------------------------------------------- per-hand helpers (floor-4's)


def hands_prep(out, channels, ms=None):
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
            sel = [0, -1]
            d[r0 : r0 + k] = t.getcol("DATA", r0, k)[:, channels][..., sel]
            w[r0 : r0 + k] = t.getcol("WEIGHT_SPECTRUM", r0, k)[:, channels][..., sel]
            f[r0 : r0 + k] = t.getcol("FLAG", r0, k)[:, channels][..., sel]
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


def apply_store(h, store, a1, a2):
    """V / (g_p conj g_q) per hand with the Sp store; invalid gains flag the cell."""
    g, flags, _gt, _gf, _sc = cal_selfcal.read_store(store, "Sp")
    g = g[:, 0]
    valid = ~flags[:, 0] & np.isfinite(g).all(-1)
    tb, _bs, _gt2 = cal_selfcal.time_bins(h["time"], h["scan"], h["field"], "300s")
    gp, gq = g[tb, a1], g[tb, a2]
    ok = valid[tb, a1] & valid[tb, a2]
    den = np.where(ok[:, None], gp * np.conj(gq), 1.0)
    xx = (h["d"][..., 0] / den[:, None, 0]).astype(np.complex64)
    yy = (h["d"][..., 1] / den[:, None, 1]).astype(np.complex64)
    f = h["f"] | ~ok[:, None, None]
    return stokes_from_hands(xx, yy, h["w"], f, h["rows_ok"])


def g1_products(g1):
    run = Path(g1) / "P" / "run"
    s = json.loads((run / "selfcal/summary.json").read_text())
    rnd = s["fields"][0]["rounds"][0]
    # the store under this `g1` (a copied run directory keeps the layout, not the absolute path)
    store = run / Path(rnd["store"]).as_posix().split("/run/", 1)[1]
    rdir = store.parent
    (m0,) = sorted(rdir.glob("*-model.fits"))
    (m1,) = sorted((rdir.parent / "final").glob("*-model.fits"))
    return store, m0, m1


# ---------------------------------------------------------------- Family I tests


def t_d(d, V, Y):
    """Steady per-antenna complex gains per cluster: the four central facets and the rest."""
    cl = {k: v for k, v in Y.items() if k in CENTRAL4}
    rest = [v for k, v in Y.items() if k not in CENTRAL4]
    if rest:
        acc = rest[0].copy()
        for v in rest[1:]:
            acc += v
        cl["rest"] = acc
    base = {k: v.copy() for k, v in cl.items()}
    cur = {k: v.copy() for k, v in cl.items()}
    tot = ft.total(cur)
    zero = np.zeros(d.n, np.int32)
    gains = {k: None for k in cl}
    for _sweep in range(2):
        for k in cl:
            tot -= cur[k]
            f, gains[k] = ft.stefcal(d, V - tot, base[k], zero, 1, iters=8, g0=gains[k])
            cur[k] = base[k] * f[:, None]
            tot += cur[k]
    return tot


def tests5(d, V, Y0, stats=False):
    """Family I on data V against the facet set Y0: floors of every test (section 4.1)."""
    res = {}
    t0 = time.perf_counter()
    M = ft.total(Y0)

    def rec(name, e):
        img = ft.grid(d, e)
        res[name] = {"F": ft.floor(d, img)}
        if stats and name == "none":
            res[name]["shape"] = ft.shape_stats(d, img)
            res[name]["E5"] = e5(d, img, Y0)
        return img

    rec("none", V - M)
    nsb = int(d.bin5.max()) + 1
    fA, _g = f2.stefcal(d, V, M, d.bin5, nsb)
    rec("T_A", V - M * fA[:, None])
    fp, _g = f2.stefcal(d, V, M, d.bin5, nsb, phase_only=True)
    rec("T_Ap", V - M * fp[:, None])
    del fp
    ff, _g = f2.stefcal(d, V, M, d.ti, int(d.ti.max()) + 1)
    rec("T_Af", V - M * ff[:, None])
    del ff
    YA = {k: v * fA[:, None] for k, v in Y0.items()}
    del fA
    YB, _s = ft.t2(d, V, YA)
    rec("T_B|A", V - ft.total(YB))
    del YB
    YB, _s = ft.t2(d, V, Y0)
    rec("T_B", V - ft.total(YB))
    del YB
    rec("T8", V - ft.total(ft.t8(d, V, Y0)))
    rec("T_D|A", V - t_d(d, V, YA))
    del YA
    res["seconds"] = time.perf_counter() - t0
    return res


def drops5(r):
    """Fractions of the arm's own excess; '| A' tests as increments over T_A."""
    p0 = P(r["none"]["F"])
    out = {"P_none": p0}
    pa = P(r["T_A"]["F"])
    for k, v in r.items():
        if not isinstance(v, dict) or k == "none" or "F" not in v:
            continue
        p = P(v["F"])
        out[k] = ((pa - p) if k.endswith(("| A", "|A")) else (p0 - p)) / p0
    return out


def e5(d, img, Y0):
    """rms over F's pixels in each 4 x 4 facet, with the facet's model flux (from Y0 keys)."""
    f = ft.SIZE // 4
    rows = []
    for iy in range(4):
        for ix in range(4):
            s = np.zeros_like(d.sel)
            s[iy * f : (iy + 1) * f, ix * f : (ix + 1) * f] = True
            s &= d.sel
            rows.append(
                {
                    "facet": [iy, ix],
                    "rms": float(np.sqrt(np.mean(img[s] ** 2))) if s.any() else None,
                    "npix": int(s.sum()),
                }
            )
    return rows


# ---------------------------------------------------------------- arms


def make_h3c(d, out, k):
    Tv = np.load(out / "skies/truth/full.npy")
    V = d.noise(ft.NOISE_SEED) + Tv
    rng = np.random.default_rng(1503)
    for key in sorted(CENTRAL4):
        v = np.load(out / "skies/truth" / f"facet4_{key[0]}_{key[1]}.npy")
        if not v.size:
            continue
        g = ft.gains(rng, (1, d.nant), 0.02 * k, 2.0 * k)[0]
        f = g[d.a1] * np.conj(g[d.a2])
        V += v * (f[:, None] - 1).astype(np.complex64)
    return V


def build(d, out, name, k):
    kind = ARMS[name][0]
    if kind == "f5":
        return make_h3c(d, out, k), "truth"
    if kind == "f2":
        return f2.make(d, out, name, k)
    return ft.make_arm(d, out, name, k), "truth"


def run_arm(d, out, name, k, stats=False):
    fn = out / "arms" / f"{name}-{k:g}.json"
    if fn.exists():
        return json.loads(fn.read_text())
    (out / "arms").mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    V, model = build(d, out, name, k)
    Y0 = ft.load_set(out, model)["facets"]
    r = tests5(d, V, Y0, stats=stats)
    r["k"] = k
    r["model"] = model
    r["drops"] = drops5(r)
    r["wall_s"] = time.perf_counter() - s0
    ft.wjson(fn, r)
    ft.log(
        "arm",
        name,
        k,
        {
            t: round(v["F"] * 1e6, 3)
            for t, v in r.items()
            if isinstance(v, dict) and "F" in v
        },
    )
    return r


def p_ref(out):
    return P(json.loads((out / "pilot.json").read_text())["none"]["F"])


def cmd_arm(out, name):
    d = ft.Data(out)
    Pref = p_ref(out)
    _kind, a1, amax = ARMS[name]
    r1 = run_arm(d, out, name, a1)
    if name == "C":
        return
    p1 = max(P(r1["none"]["F"]), 1e-30)
    a2 = round(min(a1 * math.sqrt(Pref / p1), 50.0 * a1), 3)
    run_arm(d, out, name, a2, stats=True)
    if amax is not None:
        run_arm(d, out, name, round(amax, 4))
    if name in GS_ARMS:
        fn = out / "arms" / f"GS-{name}.json"
        if not fn.exists():
            V, model = build(d, out, name, GS_ARMS[name])
            F = ft.floor(d, ft.grid(d, V - ft.load_set(out, model)["full"]))
            ft.wjson(fn, {"k": GS_ARMS[name], "F": F})
    ft.wjson(out / "arms" / f"{name}-a2.json", {"a1": a1, "a2": a2, "a_max": amax})


# ---------------------------------------------------------------- stages


def cmd_gates(out):
    out.mkdir(parents=True, exist_ok=True)
    ft.prep(out)
    meta = json.loads((out / "prep/meta.json").read_text())
    am = json.loads((IF_ARCH / "prep-meta.json").read_text())
    d = ft.Data(out)
    F0 = ft.floor(d, ft.grid(d, d.vis - ft.predict(d, fits2d(ft.PILOT))))
    r = {
        "R0": {
            "nrow": meta["nrow"] == am["nrow"],
            "active": meta["active"] == am["active"],
            "noise_c_rel": meta["noise_c"] / am["noise_c"] - 1,
            "gw_sum_rel": meta["gridding_weight_sum"] / am["gridding_weight_sum"] - 1,
        },
        "G0": {"F_uJy": F0 * 1e6, "ratio": F0 / F_ARCH},
    }
    r["R0"]["pass"] = bool(
        r["R0"]["nrow"]
        and r["R0"]["active"]
        and abs(r["R0"]["noise_c_rel"]) <= 1e-6
        and abs(r["R0"]["gw_sum_rel"]) <= 1e-6
    )
    r["G0"]["pass"] = abs(F0 / F_ARCH - 1) <= 1e-3
    ft.wjson(out / "gates.json", r)
    ft.log("gates", r)


def cmd_skies(out, g1):
    f2.skies(out)
    _store, _m0, m1 = g1_products(g1)
    d = ft.Data(out)
    ft.sky_set(d, out, "m1", fits2d(m1), nf=4, alts=True)


def cmd_pilot(out, g1):
    fn = out / "pilot.json"
    if fn.exists():
        return
    d = ft.Data(out)
    store, m0, m1 = g1_products(g1)
    h = hands_prep(out / "hands", ft.CHANNELS)
    v0, g0 = stokes_from_hands(
        h["d"][..., 0], h["d"][..., 1], h["w"], h["f"], h["rows_ok"]
    )
    check = {
        "vis_equal": bool(np.array_equal(v0, d.vis)),
        "wnat_equal": bool(np.array_equal(g0, d.wnat)),
    }
    del v0, g0
    s1, w1 = apply_store(h, store, d.a1, d.a2)
    newly = float(1 - np.count_nonzero(w1) / np.count_nonzero(d.wnat))
    np.save(out / "s1.npy", s1)
    M0 = ft.predict(d, fits2d(m0))
    F_B = ft.floor(d, ft.grid(d, d.vis - M0))
    F_Fix = ft.floor(d, ft.grid(d, s1 - M0))
    del M0
    sky = ft.load_set(out, "m1")
    r = tests5(d, s1, sky["facets"], stats=True)
    q = sky["dir"]
    for k in ("flipw", "now", "eps7", "smear"):
        name = "T5" + k if k != "smear" else "T10"
        r[name] = {"F": ft.floor(d, ft.grid(d, s1 - np.load(q / f"{k}.npy")))}
    r["drops"] = drops5(r)
    r["HB"] = {
        "check": check,
        "F_B_uJy": F_B * 1e6,
        "F_Fix_uJy": F_Fix * 1e6,
        "F_ref_uJy": r["none"]["F"] * 1e6,
        "rel_Fix": F_Fix * 1e6 / G1_REF["Fix"] - 1,
        "rel_Fin": r["none"]["F"] * 1e6 / G1_REF["Fin"] - 1,
        "newly_flagged": newly,
    }
    r["HB"]["pass"] = bool(
        abs(r["HB"]["rel_Fix"]) <= 1e-4 and abs(r["HB"]["rel_Fin"]) <= 1e-4
    )
    r["P_ref"] = P(r["none"]["F"])
    r["P_B"] = P(F_B)
    r["store"], r["m0"], r["m1"] = str(store), str(m0), str(m1)
    ft.wjson(fn, r)
    ft.log(
        "pilot",
        json.dumps(r["HB"]),
        {
            t: round(v["F"] * 1e6, 3)
            for t, v in r.items()
            if isinstance(v, dict) and "F" in v
        },
    )


def model_on_subset(d, name):
    """Predict a GeMClean model (one plane, or -channels-out 8 planes) on the 32 subset channels."""
    name = Path(name)
    one = Path(str(name) + "-model.fits")
    if one.exists():
        return ft.predict(d, fits2d(one)), [one]
    files = sorted(name.parent.glob(name.name + "-0*-model.fits"))
    nout = len(files)
    if nout == 0:
        raise SystemExit(f"no model for {name}")
    M = np.zeros((d.n, d.freq.size), np.complex64)
    group = ft.CHANNELS // (256 // nout)
    for k, fnk in enumerate(files):
        idx = np.nonzero(group == k)[0]
        if idx.size:
            M[:, idx] = ft.predict(d, fits2d(fnk), freq=d.freq[idx])
    return M, files


def model_stats(files, mask):
    out = []
    for fnm in files:
        m = fits2d(fnm)
        out.append(
            {
                "file": str(fnm),
                "flux_jy": float(m.sum()),
                "negative_jy": float(m[m < 0].sum()),
                "outside_mask_jy": float(m[~mask].sum()),
                "outside_mask_pixels": int(np.count_nonzero(m[~mask])),
                "pixels": int(np.count_nonzero(m)),
            }
        )
    return out


def cmd_score(out, models):
    d = ft.Data(out)
    s1 = np.load(out / "s1.npy")
    pil = json.loads((out / "pilot.json").read_text())
    mask = fits2d(ft.MASK) > 0.5
    (out / "family2").mkdir(exist_ok=True)
    for spec in models:
        arm, prefix, state = spec.split("=")[0], spec.split("=")[1], "S1"
        if arm.startswith("C0"):
            state = "S0"
        fn = out / "family2" / f"{arm}.json"
        if fn.exists():
            continue
        M, files = model_on_subset(d, prefix)
        V = s1 if state == "S1" else d.vis
        F = ft.floor(d, ft.grid(d, V - M))
        Pr = pil["P_ref"] if state == "S1" else pil["P_B"]
        rep = {}
        rj = Path(prefix + "-report.json")
        if not rj.exists():
            alt = sorted(Path(prefix).parent.glob(Path(prefix).name + "*report.json"))
            rj = alt[0] if alt else rj
        if rj.exists():
            x = json.loads(rj.read_text())["run"]
            rep = {
                k: x.get(k)
                for k in (
                    "components",
                    "major_cycles",
                    "stop",
                    "model_flux",
                    "residual_mad_sigma",
                    "residual_peak_abs",
                )
            }
        res = {
            "arm": arm,
            "state": state,
            "F_uJy": F * 1e6,
            "D": (Pr - P(F)) / Pr,
            "dP": Pr - P(F),
            "model": model_stats(files, mask),
            "report": rep,
        }
        ft.wjson(fn, res)
        ft.log("score", arm, res["F_uJy"], res["D"])


def cmd_twobytwo(out, deep):
    fn = out / "twobytwo.json"
    if fn.exists():
        return
    d = ft.Data(out)
    s1 = np.load(out / "s1.npy")
    nsb = int(d.bin5.max()) + 1
    res = {}
    for name, M in (
        ("m1", ft.load_set(out, "m1")["full"]),
        ("Dm03", model_on_subset(d, deep)[0]),
    ):
        fA, _g = f2.stefcal(d, s1, M, d.bin5, nsb)
        YA = {"all": M * fA[:, None]}
        YB, _s = ft.t2(d, s1, YA)
        F0 = ft.floor(d, ft.grid(d, s1 - M))
        FA = ft.floor(d, ft.grid(d, s1 - YA["all"]))
        FB = ft.floor(d, ft.grid(d, s1 - YB["all"]))
        res[name] = {
            "F_none": F0,
            "F_A": FA,
            "F_BA": FB,
            "dP_B": P(FA) - P(FB),
            "dP_A": P(F0) - P(FA),
        }
    res["rho_B"] = res["Dm03"]["dP_B"] / res["m1"]["dP_B"]
    ft.wjson(fn, res)
    ft.log("2x2", res)


# ---------------------------------------------------------------- summary


def verdict_family1(pil, arms, Pref):
    out = {}
    a2 = {}
    for name in ARMS:
        fa = arms.get(f"{name}-a2")
        if fa:
            a2[name] = fa
    for test, own in OWN.items():
        row = {"hypothesis": HYP[test], "own_arm": own}
        Dp = pil["drops"][test]
        row["D_pilot"] = Dp
        cross = {}
        for name, a in a2.items():
            r = arms.get(f"{name}-{a['a2']:g}")
            if r is None or name == "C":
                continue
            usable = r["drops"]["P_none"] >= 0.1 * Pref
            cross[name] = {
                "D": r["drops"][test],
                "P_over_Pref": r["drops"]["P_none"] / Pref,
                "usable": bool(usable),
            }
        row["arms"] = cross
        own_D = cross.get(own, {}).get("D")
        others = {k: v["D"] for k, v in cross.items() if k != own and v["usable"]}
        row["specific"] = bool(
            own_D is not None
            and own_D >= 0.7
            and all(x <= 0.3 for x in others.values())
        )
        row["fires_on"] = sorted(k for k, x in others.items() if x > 0.3)
        amx = a2.get(own, {}).get("a_max")
        rmax = arms.get(f"{own}-{round(amx, 4):g}") if amx else None
        pmax = rmax["drops"]["P_none"] / Pref if rmax else None
        row["P_amax_over_Pref"] = pmax
        if pmax is not None and pmax < 0.05:
            v = "rejected (no plausible amplitude carries 0.05 P_ref)"
        elif row["specific"] and Dp >= 0.10 and pmax is not None and pmax >= 0.5 * Dp:
            v = f"attributed, share {Dp:.3f}"
        elif row["specific"] and Dp < 0.05:
            v = "rejected"
        elif not row["specific"]:
            v = f"unresolved, upper bound {Dp:.3f} shared with {row['fires_on'] or ['own arm below 0.7']}"
        elif pmax is not None and pmax < 0.5 * Dp:
            v = f"unresolved: the pilot drop {Dp:.3f} exceeds what a plausible amplitude carries ({pmax:.3f})"
        else:
            v = f"unresolved, 0.05 <= D = {Dp:.3f} < 0.10"
        row["verdict"] = v
        out[test] = row
    # H5, H10
    F0 = pil["none"]["F"]
    best = max(P(F0) - P(pil[k]["F"]) for k in ("T5flipw", "T5now", "T10"))
    eps = abs(pil["T5eps7"]["F"] / F0 - 1)
    out["T5_T10"] = {
        "best_dP_over_Pref": best / Pref,
        "eps7_rel": eps,
        "verdict": "rejected"
        if best < 0.05 * Pref and eps < 0.02
        else f"attributed {best / Pref:.3f}",
    }
    return out


def cmd_summary(out):
    pil = json.loads((out / "pilot.json").read_text())
    Pref = pil["P_ref"]
    arms = {p.stem: json.loads(p.read_text()) for p in (out / "arms").glob("*.json")}
    res = {
        "P_ref": Pref,
        "P_ref_over_P_pilot": Pref / 1.150e-6,
        "gates": json.loads((out / "gates.json").read_text()),
        "HB": pil["HB"],
    }
    am = json.loads((IF_ARCH / "summary.json").read_text())
    gs = {"C": arms["C-1"]["none"]["F"] / T - 1}
    for name, k in GS_ARMS.items():
        g = arms.get(f"GS-{name}")
        ref = am["arms"][f"{name}@{k:g}"]["F_uJy"] * 1e-6
        gs[name] = {
            "F": g["F"] if g else None,
            "ref": ref,
            "rel": (g["F"] / ref - 1) if g else None,
        }
    gs["pass"] = bool(
        abs(gs["C"]) <= 5e-3 and all(abs(gs[n]["rel"] or 1) <= 5e-3 for n in GS_ARMS)
    )
    res["GS"] = gs
    res["family1"] = verdict_family1(pil, arms, Pref)
    if RERUN.exists():
        sa, _m0a, m1a = g1_products(RERUN)
        sb, _m0b, m1b = Path(pil["store"]), None, Path(pil["m1"])
        ga, fa = cal_selfcal.read_store(sa, "Sp")[:2]
        gb, fb = cal_selfcal.read_store(sb, "Sp")[:2]
        res["g1_rerun_equal"] = {
            "store": bool(np.array_equal(ga, gb) and np.array_equal(fa, fb)),
            "final_model": bool(np.array_equal(fits2d(m1a), fits2d(m1b))),
        }
    f2d = out / "family2"
    fam2 = (
        {p.stem: json.loads(p.read_text()) for p in f2d.glob("*.json")}
        if f2d.exists()
        else {}
    )
    res["family2"] = fam2
    if "Dm03" in fam2 and "C0" in fam2:
        kappa = (fam2["C0"]["dP"] - fam2["Dm03"]["dP"]) / (pil["P_B"] - Pref)
        D = fam2["Dm03"]["D"]
        if D < 0.05:
            v = "rejected"
        elif D >= 0.10 and kappa <= 0.3:
            v = f"attributed under floor-5's depth standard, share {D:.3f}"
        else:
            v = f"unresolved (D {D:.3f}, kappa {kappa:.3f}); upper bound {D:.3f}"
        res["H9"] = {"D_Dm03": D, "kappa": kappa, "verdict": v}
        notes = []
        if "Dms03" in fam2 and fam2["Dms03"]["D"] >= D + 0.10:
            notes.append("extended emission CLEAN misses")
        if (
            "Du1" in fam2
            and "Dm1" in fam2
            and fam2["Du1"]["D"] >= fam2["Dm1"]["D"] + 0.10
        ):
            notes.append("unmasked depth cleans artefacts")
        res["H9"]["notes"] = notes
    if "S" in fam2:
        Ds = fam2["S"]["D"]
        res["H8_direct"] = {
            "D_S": Ds,
            "reading": "supported"
            if Ds >= 0.10
            else ("not supported as tested" if Ds < 0.05 else "unresolved"),
        }
    tb = out / "twobytwo.json"
    if tb.exists():
        x = json.loads(tb.read_text())
        rho = x["rho_B"]
        res["twobytwo"] = {
            **x,
            "reading": "H2 supported"
            if rho >= 0.7
            else ("H2 absorbed" if rho <= 0.3 else "partial"),
        }
    ft.wjson(out / "summary.json", res)
    ft.log("summary", json.dumps(res, default=float)[:3000])


def cmd_clean(out):
    for p in ("prep", "skies", "hands", "s1.npy"):
        q = out / p
        if q.is_dir():
            shutil.rmtree(q, ignore_errors=True)
        elif q.exists():
            q.unlink()


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "stage",
        choices=[
            "gates",
            "skies",
            "pilot",
            "arm",
            "score",
            "twobytwo",
            "summary",
            "clean",
        ],
    )
    p.add_argument("name", nargs="*")
    p.add_argument("--out", default="D:/rang/outputs/floor-5-20261117/floor-5")
    p.add_argument("--g1", default="D:/rang/outputs/floor-5-20261117/g1")
    a = p.parse_args(argv)
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    if a.stage == "gates":
        cmd_gates(out)
    elif a.stage == "skies":
        cmd_skies(out, a.g1)
    elif a.stage == "pilot":
        cmd_pilot(out, a.g1)
    elif a.stage == "arm":
        for n in a.name:
            cmd_arm(out, n)
    elif a.stage == "score":
        cmd_score(out, a.name)
    elif a.stage == "twobytwo":
        cmd_twobytwo(out, a.name[0])
    elif a.stage == "summary":
        cmd_summary(out)
    elif a.stage == "clean":
        cmd_clean(out)
    ft.log("stage", a.stage, a.name, f"{time.perf_counter() - s0:.1f} s")


if __name__ == "__main__":
    main()
