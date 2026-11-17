"""floor-2 (research/floor-2.md): gains against short-spacing incompleteness on the pilot.

Reuses examples/floor_tests.py (imported, unchanged) for the prep, the gridder, the facets, StefCal
and the tests T1, T4, T8. Stages, each resumable:

    prep     floor_tests' prep (set A, 32 channels), then gate R0's prep check
    skies    truth, pilot, K1/K3/K10 as 4 x 4 facets; the extended images XS2, XS4, XG4
    arms     the simulated arms of section 3 at a1 and a2
    pilot    gate R0 on the pilot, then the new tests
    g3       item 3a: the pilot's steady T1 gains injected, and its two controls
    summary  the frozen readings of sections 5-8
    cleanup  delete prep and skies (the visibility scratch)
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import floor_tests as ft
from rang import core_ms
from rang.core_imaging import read_fits

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "research/results/imaging-floor"
GAINS = ft.HELD / "gains.npz"
P_PILOT = 1.150e-6  # replaced by the archive's exact value below
T_ARCH = None
SEED_GAINS = 1312
SEED_PERM = 1333
KH = 5.616


def archive():
    s = json.loads((ARCHIVE / "summary.json").read_text())
    return s, json.loads((ARCHIVE / "pilot.json").read_text())


SUMMARY_ARCH, PILOT_ARCH = archive()
P_PILOT = SUMMARY_ARCH["P_pilot"]
T_ARCH = SUMMARY_ARCH["T_thermal_subset_jy"]


# ---------------------------------------------------------------- StefCal variants


def stefcal(d, V, Y, sb, nsb, iters=30, w=None, phase_only=False):
    """floor_tests.stefcal with an optional projection onto unit amplitude after each update."""
    w = d.wnat if w is None else w
    A = np.einsum("rc,rc->r", w * V, np.conj(Y)).astype(np.complex128)
    B = np.einsum("rc,rc->r", w, np.abs(Y) ** 2).astype(np.float64)
    na = d.nant
    g = np.ones((nsb, na), np.complex128)
    i1 = sb * na + d.a1
    i2 = sb * na + d.a2
    n = nsb * na
    for it in range(iters):
        gq2 = g.reshape(-1)[i2]
        gq1 = g.reshape(-1)[i1]
        num = np.bincount(i1, (A * gq2).real, n) + 1j * np.bincount(
            i1, (A * gq2).imag, n
        )
        num += np.bincount(i2, (np.conj(A) * gq1).real, n) + 1j * np.bincount(
            i2, (np.conj(A) * gq1).imag, n
        )
        den = np.bincount(i1, np.abs(gq2) ** 2 * B, n) + np.bincount(
            i2, np.abs(gq1) ** 2 * B, n
        )
        gn = np.where(den > 0, num / np.maximum(den, 1e-300), g.reshape(-1)).reshape(
            nsb, na
        )
        g = 0.5 * (g + gn) if it % 2 else gn
        if phase_only:
            g = np.where(np.abs(g) > 0, g / np.maximum(np.abs(g), 1e-300), 1.0)
    f = g.reshape(-1)[i1] * np.conj(g.reshape(-1)[i2])
    return f.astype(np.complex64), g


def tests(d, V, Y0, gains_path):
    """none, T1, T4, T8, T1p, T1L; floors and the three gain solutions."""
    res = {}
    t0 = time.perf_counter()
    M = ft.total(Y0)

    def rec(name, e):
        img = ft.grid(d, e)
        res[name] = {"F": ft.floor(d, img)}
        if name == "none":
            res[name]["shape"] = ft.shape_stats(d, img)

    rec("none", V - M)
    nsb = int(d.bin5.max()) + 1
    sol = {}
    longw = d.wnat * (~d.short)[:, None]
    for name, kw in (
        ("T1", {}),
        ("T1p", {"phase_only": True}),
        ("T1L", {"w": longw}),
    ):
        f, g = stefcal(d, V, M, d.bin5, nsb, **kw)
        sol[name] = g
        rec(name, V - M * f[:, None])
        del f
    rec("T4", V - ft.total(ft.t4(d, V, Y0)))
    rec("T8", V - ft.total(ft.t8(d, V, Y0)))
    np.savez(gains_path, **sol)
    res["seconds"] = time.perf_counter() - t0
    return res


def drops(r, T):
    P = {
        k: v["F"] ** 2 - T**2 for k, v in r.items() if isinstance(v, dict) and "F" in v
    }
    p0 = P["none"]
    out = {"P_none": p0, "P_over_Ppilot": p0 / P_PILOT}
    for k, v in P.items():
        if k != "none":
            out[k] = (p0 - v) / p0 if p0 > 0 else None
    return out


# ---------------------------------------------------------------- skies


def gaussian_image(shape, cy, cx, fwhm_px):
    yy, xx = np.indices(shape)
    s = fwhm_px / (2 * math.sqrt(2 * math.log(2)))
    return np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * s * s))


def extended(d, truth):
    """E images, 1 Jy each: the truth's positive pixels smoothed to 2' and 4'; a 4' halo."""
    from scipy.ndimage import gaussian_filter

    pos = np.where(truth > 0, truth, 0.0)
    out = {}
    for name, fw in (("XS2", 120.0), ("XS4", 240.0)):
        s = fw / ft.SCALE / (2 * math.sqrt(2 * math.log(2)))
        e = gaussian_filter(pos, s, mode="constant")
        out[name] = e / e.sum()
    g = gaussian_image(truth.shape, d.peak[0], d.peak[1], 240.0 / ft.SCALE)
    out["XG4"] = g / g.sum()
    return out


def skies(out):
    d = ft.Data(out)
    truth, _ = read_fits(ft.TRUTH)
    pilot, _ = read_fits(ft.PILOT)
    ft.sky_set(d, out, "pilot", pilot, nf=4, alts=False)
    ft.sky_set(d, out, "truth", truth, nf=4, alts=False)
    flux = {}
    for thr, name in ((1e-3, "K1"), (3e-3, "K3"), (1e-2, "K10")):
        kept = np.where(np.abs(truth) >= thr, truth, 0.0)
        flux[name] = {
            "kept_jy": float(kept.sum()),
            "missing_jy": float((truth - kept).sum()),
        }
        ft.sky_set(d, out, name, kept, nf=4, alts=False)
    for name, e in extended(d, truth).items():
        fn = out / "skies" / f"E_{name}.npy"
        if not fn.exists():
            np.save(fn, ft.predict(d, e))
        v = np.load(fn)
        flux[name] = {
            "flux_jy": float(e.sum()),
            "short_amp_share": float(
                np.sum(d.gw * np.abs(v) * d.short[:, None]) / np.sum(d.gw * np.abs(v))
            ),
        }
    ft.wjson(out / "skies/floor2-skies.json", flux)
    ft.log("skies", flux)


# ---------------------------------------------------------------- arms


def h1_gains(d, k, mode):
    rng = np.random.default_rng(SEED_GAINS)
    za = rng.standard_normal((1, d.nant))
    zp = rng.standard_normal((1, d.nant))
    amp = 1 + 0.01 * k * za if mode in ("H1b", "H1bA") else np.ones_like(za)
    ph = math.radians(1.0 * k) * zp if mode in ("H1b", "H1bP") else np.zeros_like(zp)
    return (amp * np.exp(1j * ph))[0]


def apply_gains(d, X, g):
    return X * (g[d.a1] * np.conj(g[d.a2]))[:, None].astype(np.complex64)


def make(d, out, name, k, extra=None):
    T = np.load(out / "skies/truth/full.npy")
    V = d.noise(ft.NOISE_SEED)
    model = "truth"
    if name == "C":
        V += T
    elif name in ("H1b", "H1bA", "H1bP"):
        V += apply_gains(d, T, h1_gains(d, k, name))
    elif name in ("K1", "K3", "K10"):
        kept = np.load(out / "skies" / name / "full.npy")
        V += kept + k * (T - kept)
        model = name
    elif name in ("XS2", "XS4", "XG4"):
        V += T + k * np.load(out / "skies" / f"E_{name}.npy")
    elif name == "MIX":
        kx = extra["kx"]
        V += apply_gains(
            d,
            T + kx * np.load(out / "skies/E_XS2.npy"),
            h1_gains(d, KH / math.sqrt(2), "H1b"),
        )
    elif name.startswith("G3"):
        V += apply_gains(d, T, extra["g"])
    else:
        raise ValueError(name)
    return V, model


def arm(d, out, name, k, extra=None):
    fn = out / "arms" / f"{name}-{k:g}.json"
    if fn.exists():
        return json.loads(fn.read_text())
    (out / "arms").mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    V, model = make(d, out, name, k, extra)
    Y0 = ft.load_set(out, model)["facets"]
    r = tests(d, V, Y0, out / "arms" / f"{name}-{k:g}-gains.npz")
    r["k"] = k
    r["model"] = model
    if extra and "kx" in extra:
        r["kx"] = extra["kx"]
    r["wall_s"] = time.perf_counter() - s0
    ft.wjson(fn, r)
    ft.log(
        "arm",
        name,
        k,
        {
            t: round(v["F"] * 1e6, 2)
            for t, v in r.items()
            if isinstance(v, dict) and "F" in v
        },
    )
    return r


def a2_of(r):
    P1 = max(r["none"]["F"] ** 2 - T_ARCH**2, 1e-30)
    return round(min(math.sqrt(P_PILOT / P1), 50.0), 3)


def smoke(out):
    """Declared smoke run (section 10): simulated arms only, on a row subset; not results."""
    d = ft.Data(out)
    for nm in ("C", "H1b", "K10", "XS2"):
        arm(d, out, nm, 1)
    active, sh, _longsh = antenna_stats(d)
    r = enu(out)[: d.nant]
    rep = gain_report(d, out, out / "arms/H1b-1-gains.npz", active, sh, r)
    pub = publisher_stats(d, d.nant)
    ft.log(
        "smoke",
        {k: rep[k]["sigma_a"] for k in rep},
        {k: float(np.nanmedian(v)) for k, v in pub.items()},
    )


def arms(out):
    d = ft.Data(out)
    arm(d, out, "C", 1)
    r = arm(d, out, "H1b", 1)
    k = a2_of(r)
    arm(d, out, "H1b", k)
    arm(d, out, "H1b", 5.616)  # gate R0 (the archive's a2)
    arm(d, out, "H1b", 5)
    a2 = {"H1b": k}
    for nm in ("H1bA", "H1bP", "K10", "K1", "K3", "XS2", "XS4", "XG4"):
        r = arm(d, out, nm, 1)
        a2[nm] = a2_of(r)
        arm(d, out, nm, a2[nm])
    kx = round(a2["XS2"] / math.sqrt(2), 3)
    arm(d, out, "MIX", 1, {"kx": kx})
    ft.wjson(out / "arms/a2.json", a2)


def pilot(out):
    fn = out / "pilot.json"
    if fn.exists():
        return
    d = ft.Data(out)
    Y0 = ft.load_set(out, "pilot")["facets"]
    r = tests(d, d.vis.astype(np.complex64), Y0, out / "pilot-gains.npz")
    ft.wjson(fn, r)
    ft.log(
        "pilot",
        {
            t: round(v["F"] * 1e6, 2)
            for t, v in r.items()
            if isinstance(v, dict) and "F" in v
        },
    )


# ---------------------------------------------------------------- gains (item 3)


def enu(out):
    p = out / "antpos.npy"
    if p.exists():
        return np.load(p)
    with core_ms.open_table(str(ft.MS_A / "ANTENNA")) as t:
        xyz = np.asarray(t.getcol("POSITION", 0, int(t.nrows)), np.float64)
    dx = xyz - xyz.mean(axis=0)
    lat, lon = ft.LAT, ft.LON
    sl, cl, so, co = math.sin(lat), math.cos(lat), math.sin(lon), math.cos(lon)
    e = -so * dx[:, 0] + co * dx[:, 1]
    n = -sl * co * dx[:, 0] - sl * so * dx[:, 1] + cl * dx[:, 2]
    u = cl * co * dx[:, 0] + cl * so * dx[:, 1] + sl * dx[:, 2]
    r = np.stack([e, n, u], axis=1)
    np.save(p, r)
    return r


def antenna_stats(d):
    w = d.gw.sum(axis=1, dtype=np.float64)
    tot = np.bincount(d.a1, w, d.nant) + np.bincount(d.a2, w, d.nant)
    sh = np.bincount(d.a1, w * d.short, d.nant) + np.bincount(d.a2, w * d.short, d.nant)
    wl = d.wnat.sum(axis=1, dtype=np.float64) * (~d.short)
    wn = d.wnat.sum(axis=1, dtype=np.float64)
    longsh = (
        np.bincount(d.a1, wl, d.nant) + np.bincount(d.a2, wl, d.nant)
    ) / np.maximum(
        np.bincount(d.a1, wn, d.nant) + np.bincount(d.a2, wn, d.nant), 1e-300
    )
    active = tot > 0
    return active, np.where(active, sh / np.maximum(tot, 1e-300), np.nan), longsh


def gauge(g, active, r):
    """Section 4's gauge: amplitude over its median, phase less c_b + k_b . r_p per bin."""
    g = np.asarray(g, np.complex128)
    a = np.abs(g)
    scale = float(np.median(a[:, active]))
    a = a / scale
    ref = np.exp(-1j * np.angle(np.sum(g[:, active] / np.abs(g[:, active]), axis=1)))
    ph = np.angle(g * ref[:, None])
    X = np.column_stack([np.ones(active.sum()), r[active]])
    for b in range(g.shape[0]):
        c = np.linalg.lstsq(X, ph[b, active], rcond=None)[0]
        ph[b] -= np.column_stack([np.ones(r.shape[0]), r]) @ c
    G = a * np.exp(1j * ph)
    gbar = G.mean(axis=0)
    e = np.abs(gbar - 1)
    return {
        "G": G,
        "gbar": gbar,
        "e": e,
        "scale": scale,
        "sigma_a": float(np.sqrt(np.mean((np.abs(gbar[active]) - 1) ** 2))),
        "sigma_phi_deg": float(
            np.degrees(np.sqrt(np.mean(np.angle(gbar[active]) ** 2)))
        ),
        "variable": float(
            np.sqrt(np.mean(np.abs(G[:, active] / gbar[active] - 1) ** 2))
        ),
    }


def spearman_perm(x, y, seed=SEED_PERM, n=10_000):
    from scipy.stats import rankdata

    ok = np.isfinite(x) & np.isfinite(y)
    rx, ry = rankdata(x[ok]), rankdata(y[ok])
    rx, ry = (rx - rx.mean()) / rx.std(), (ry - ry.mean()) / ry.std()
    rho = float(np.mean(rx * ry))
    rng = np.random.default_rng(seed)
    perm = np.array([np.mean(rng.permutation(rx) * ry) for _ in range(n)])
    return {
        "rho": rho,
        "p": float((np.sum(np.abs(perm) >= abs(rho)) + 1) / (n + 1)),
        "n": int(ok.sum()),
    }


def publisher_stats(d, nant):
    z = np.load(GAINS)
    g, fl = z["gains"], z["flags"]
    ch = ft.CHANNELS
    gs = 0.5 * (g[:, 2 * ch] + g[:, 2 * ch + 1])  # (t, 32, ant, hand)
    fs = fl[:, 2 * ch] | fl[:, 2 * ch + 1]  # (t, 32, ant)
    out = {
        k: np.full(nant, np.nan)
        for k in ("amp_var", "phase_var", "amp_mean", "flag_frac", "xy_log")
    }
    for p in range(min(nant, gs.shape[2])):
        ok = ~fs[:, :, p]
        out["flag_frac"][p] = 1 - ok.mean()
        av, pv, _am = [], [], []
        for c in range(ch.size):
            m = ok[:, c]
            if m.sum() < 3:
                continue
            for h in range(2):
                x = gs[m, c, p, h]
                amp = np.abs(x)
                av.append(np.sqrt(np.mean((amp / amp.mean() - 1) ** 2)))
                cm = np.angle(np.sum(x / np.maximum(amp, 1e-300)))
                pv.append(np.sqrt(np.mean(np.angle(x * np.exp(-1j * cm)) ** 2)))
        if av:
            out["amp_var"][p] = np.median(av)
            out["phase_var"][p] = np.median(pv)
        sel = ok[:, :, None] & np.ones((1, 1, 2), bool)
        ax = np.abs(gs[:, :, p, 0])[ok]
        ay = np.abs(gs[:, :, p, 1])[ok]
        if ax.size:
            out["amp_mean"][p] = float(np.mean(np.abs(gs[:, :, p, :])[sel]))
            out["xy_log"][p] = abs(math.log(ax.mean() / ay.mean()))
    return out


def gain_report(d, out, path, active, sh, r):
    z = np.load(path)
    rep = {}
    for name in ("T1", "T1p", "T1L"):
        gg = gauge(z[name], active, r)
        e = np.where(active, gg["e"], np.nan)
        order = np.argsort(-np.nan_to_num(e, nan=-1))
        rep[name] = {
            "scale": gg["scale"],
            "sigma_a": gg["sigma_a"],
            "sigma_phi_deg": gg["sigma_phi_deg"],
            "variable": gg["variable"],
            "core_spearman": spearman_perm(e, sh),
            "rank_ant1": int(np.nonzero(order == 1)[0][0]) + 1,
            "worst10": order[:10].tolist(),
            "e": e.tolist(),
            "gbar_re": gg["gbar"].real.tolist(),
            "gbar_im": gg["gbar"].imag.tolist(),
        }
    return rep


def g3(out):
    d = ft.Data(out)
    active, _sh, _ = antenna_stats(d)
    r = enu(out)[: d.nant]
    for name, src in (
        ("G3", out / "pilot-gains.npz"),
        ("G3K10", None),
        ("G3XS2", None),
    ):
        if src is None:
            a2 = json.loads((out / "arms/a2.json").read_text())
            arm_name = name[2:]
            src = out / "arms" / f"{arm_name}-{a2[arm_name]:g}-gains.npz"
        gbar = gauge(np.load(src)["T1"], active, r)["gbar"]
        gbar = np.where(active, gbar, 1.0)
        arm(d, out, name, 1, {"g": gbar})


# ---------------------------------------------------------------- summary


def summary(out):
    d = ft.Data(out)
    active, sh, longsh = antenna_stats(d)
    r = enu(out)[: d.nant]
    T = T_ARCH
    res = {"P_pilot": P_PILOT, "T": T, "n_active": int(active.sum())}
    # gate R0
    meta = json.loads((out / "prep/meta.json").read_text())
    am = json.loads((ARCHIVE / "prep-meta.json").read_text())
    r0 = {
        "prep": meta["nrow"] == am["nrow"]
        and meta["active"] == am["active"]
        and abs(meta["noise_c"] / am["noise_c"] - 1) < 1e-6
        and abs(meta["gridding_weight_sum"] / am["gridding_weight_sum"] - 1) < 1e-6
    }
    pil = json.loads((out / "pilot.json").read_text())
    r0["pilot"] = {
        t: pil[t]["F"] / PILOT_ARCH[t]["F"] for t in ("none", "T1", "T4", "T8")
    }
    r0["pilot_ok"] = all(abs(v - 1) <= 0.005 for v in r0["pilot"].values())
    arms_ = {}
    for fn in sorted((out / "arms").glob("*.json")):
        if fn.name == "a2.json":
            continue
        nm, k = fn.stem.rsplit("-", 1)
        rr = json.loads(fn.read_text())
        arms_[f"{nm}@{k}"] = {"F_uJy": rr["none"]["F"] * 1e6, **drops(rr, T)}
    chk = {}
    for mine, theirs in (("C@1", "C@1"), ("H1b@5.616", "H1b@5.616"), ("K10@1", "M@1")):
        a, b = arms_[mine], SUMMARY_ARCH["arms"][theirs]
        row = {"F_ratio": a["F_uJy"] / b["F_uJy"]}
        ok = abs(row["F_ratio"] - 1) <= 0.005
        if mine != "C@1":
            for t in ("T1", "T4", "T8"):
                row[t] = [a[t], b[t]]
                ok = ok and abs(a[t] - b[t]) <= 0.02
        row["ok"] = ok
        chk[mine] = row
    r0["arms"] = chk
    r0["pass"] = r0["prep"] and r0["pilot_ok"] and all(v["ok"] for v in chk.values())
    res["R0"] = r0
    pd = drops(pil, T)
    res["pilot"] = {
        "F_uJy": pil["none"]["F"] * 1e6,
        **pd,
        "floors_uJy": {
            t: v["F"] * 1e6 for t, v in pil.items() if isinstance(v, dict) and "F" in v
        },
    }
    res["arms"] = arms_
    a2 = json.loads((out / "arms/a2.json").read_text())
    res["a2"] = a2
    at2 = {nm: arms_[f"{nm}@{a2[nm]:g}"] for nm in a2}

    def usable(x):
        return x["P_over_Ppilot"] >= 0.1 and x["T1"] >= 0.1

    def rpm(x):
        f = max(x["T4"], x["T8"])
        return (
            (f + 0.02) / max(x["T1"] - 0.02, 0.01),
            max(f - 0.02, 0) / (x["T1"] + 0.02),
            f / x["T1"],
        )

    # item 1
    G = ["H1b", "H1bA", "H1bP"]
    I = ["K1", "K3", "K10", "XS2", "XS4", "XG4"]
    RG = max(rpm(at2[g])[0] for g in G)
    Rp_plus, Rp_minus, Rp = rpm(pd)
    kinds = {}
    for j in I:
        x = at2[j]
        if not usable(x):
            kinds[j] = {"usable": False}
            continue
        _, Rjm, Rj = rpm(x)
        sep = Rjm >= 2 * RG
        row = {"usable": True, "R": Rj, "R_minus": Rjm, "separates": sep}
        if sep:
            tau = math.sqrt(RG * Rjm)
            row["tau"] = tau
            row["pilot"] = (
                "unlike"
                if Rp_plus < tau
                else ("like" if Rp_minus > tau else "undecided")
            )
        kinds[j] = row
    use = [j for j in I if kinds[j]["usable"]]
    valid = (
        bool(use)
        and all(kinds[j]["separates"] for j in use)
        and any(j.startswith("X") for j in use)
    )
    if valid and all(kinds[j]["pilot"] == "unlike" for j in use):
        r1 = "gain-like"
    elif valid and any(kinds[j]["pilot"] == "like" for j in use):
        r1 = (
            "incompleteness-like ("
            + ", ".join(j for j in use if kinds[j]["pilot"] == "like")
            + ")"
        )
    else:
        r1 = "not discriminating"
    res["item1"] = {
        "R_G_plus": RG,
        "R_gain": {g: rpm(at2[g])[2] for g in G},
        "pilot_R": Rp,
        "pilot_R_plus": Rp_plus,
        "pilot_R_minus": Rp_minus,
        "kinds": kinds,
        "valid": valid,
        "non_separating": [j for j in use if not kinds[j]["separates"]],
        "reading": r1,
        "MIX_R": rpm(arms_[next(k for k in arms_ if k.startswith("MIX@"))])[2],
    }
    # item 5
    rho = {
        nm: {
            "rho_p": x["T1p"] / x["T1"],
            "rho_L": x["T1L"] / x["T1"],
            "usable": usable(x),
        }
        for nm, x in at2.items()
    }
    rho["pilot"] = {"rho_p": pd["T1p"] / pd["T1"], "rho_L": pd["T1L"] / pd["T1"]}
    L_valid = rho["H1b"]["rho_L"] >= 0.7
    p_valid = rho["H1bP"]["rho_p"] >= 0.7
    Xu = [j for j in ("XS2", "XS4", "XG4") if rho[j]["usable"]]
    KXu = [j for j in I if rho[j]["usable"]]
    maxL = max((rho[j]["rho_L"] for j in Xu), default=None)
    sepL = L_valid and maxL is not None and maxL <= rho["H1b"]["rho_L"] - 0.3
    if sepL:
        mL = 0.5 * (rho["H1b"]["rho_L"] + maxL)
        pl = rho["pilot"]["rho_L"]
        survL = (
            "survives"
            if pl >= max(0.5, mL + 0.05)
            else ("not survived" if pl <= mL - 0.05 else "undecided")
        )
    else:
        mL, survL = None, "void (not separating or invalid)"
    infP = p_valid and all(rho[j]["rho_p"] <= 0.3 for j in KXu)
    if infP:
        survP = (
            "survives"
            if rho["pilot"]["rho_p"] >= 0.5
            else "amplitude-like (does not decide)"
        )
    else:
        survP = "void (not informative or invalid)"
    if survL == "survives" and survP == "survives":
        r5 = "gains more likely"
    elif sepL and survL == "not survived":
        r5 = "short-spacing cause more likely"
    else:
        r5 = "undecided"
    weak = [int(p) for p in np.nonzero(active & (longsh < 0.01))[0]]
    res["item5"] = {
        "rho": rho,
        "T1L_valid": L_valid,
        "T1p_valid": p_valid,
        "T1L_separates": sepL,
        "m_L": mL,
        "T1L": survL,
        "T1p_informative": infP,
        "T1p": survP,
        "reading": r5,
        "antennas_under_1pct_long_weight": weak,
        "min_long_weight_share": float(np.nanmin(np.where(active, longsh, np.nan))),
    }
    # item 3
    g3r = {nm: arms_[f"{nm}@1"]["P_over_Ppilot"] for nm in ("G3", "G3K10", "G3XS2")}
    pg = g3r["G3"]
    size = "exist" if pg >= 0.5 else ("absent" if pg < 0.1 else "partial")
    sep3a = all(g3r[c] < 0.5 * pg for c in ("G3K10", "G3XS2"))
    reps = {"pilot": gain_report(d, out, out / "pilot-gains.npz", active, sh, r)}
    for nm in a2:
        reps[nm] = gain_report(
            d, out, out / "arms" / f"{nm}-{a2[nm]:g}-gains.npz", active, sh, r
        )

    def core(rep):
        c = rep["T1"]["core_spearman"]
        return c["rho"] >= 0.4 and c["p"] < 0.01

    cc = {nm: core(v) for nm, v in reps.items()}
    usKX = [j for j in I if usable(at2[j])]
    if cc["pilot"] and all(cc[j] for j in usKX) and not cc["H1b"]:
        r3b = "like incompleteness's spurious gains"
    elif not cc["pilot"] and not cc["H1b"]:
        r3b = "like gain errors"
    else:
        r3b = "not discriminating"
    e = np.array(reps["pilot"]["T1"]["e"])
    pub = publisher_stats(d, d.nant)
    assoc = {}
    for k, v in pub.items():
        s = spearman_perm(e, v)
        s["associated"] = abs(s["rho"]) >= 0.3 and s["p"] < 0.002
        assoc[k] = s
    rank1 = reps["pilot"]["T1"]["rank_ant1"]
    res["item3"] = {
        "3a": {
            "P_over_Ppilot": g3r,
            "reading": size,
            "controls_separate": sep3a,
            "pilot_sigma_a": reps["pilot"]["T1"]["sigma_a"],
            "pilot_sigma_phi_deg": reps["pilot"]["T1"]["sigma_phi_deg"],
            "pilot_variable": reps["pilot"]["T1"]["variable"],
            "pilot_scale": reps["pilot"]["T1"]["scale"],
        },
        "3b": {
            "core_concentrated": cc,
            "spearman": {nm: v["T1"]["core_spearman"] for nm, v in reps.items()},
            "reading": r3b,
        },
        "3c": assoc,
        "3d": {
            "rank_ant1_pilot": rank1,
            "n_active": int(active.sum()),
            "among_worst": rank1 <= 6,
            "chance": 6 / int(active.sum()),
            "rank_ant1_K10": reps["K10"]["T1"]["rank_ant1"],
            "rank_ant1_XS2": reps["XS2"]["T1"]["rank_ant1"],
            "rank_ant1_H1b": reps["H1b"]["T1"]["rank_ant1"],
            "pilot_worst10": reps["pilot"]["T1"]["worst10"],
        },
        "gain_stats": {
            nm: {
                t: {
                    k: v[t][k]
                    for k in (
                        "scale",
                        "sigma_a",
                        "sigma_phi_deg",
                        "variable",
                        "rank_ant1",
                    )
                }
                for t in ("T1", "T1p", "T1L")
            }
            for nm, v in reps.items()
        },
    }
    res["antennas"] = {
        "short_share": np.nan_to_num(sh, nan=-1).tolist(),
        "pilot_e_T1": reps["pilot"]["T1"]["e"],
        "pilot_gbar_re": reps["pilot"]["T1"]["gbar_re"],
        "pilot_gbar_im": reps["pilot"]["T1"]["gbar_im"],
        "publisher": {k: np.nan_to_num(v, nan=-1).tolist() for k, v in pub.items()},
    }
    # joint (section 8)
    if r1 == "gain-like" and r5 == "gains more likely" and size == "exist":
        j = "row 1: H1 attributed, share D_T1"
    elif (
        r1 in ("gain-like", "not discriminating")
        and r5 == "gains more likely"
        and size == "partial"
    ):
        j = "row 2: H1 favoured, not attributed"
    elif (
        r1.startswith("incompleteness") or r1 == "not discriminating"
    ) and r5 == "short-spacing cause more likely":
        j = "row 3: H9 (short-spacing incompleteness) favoured"
    else:
        j = "row 4: H1 and H9 stay unresolved"
    res["joint"] = j
    ft.wjson(out / "summary.json", res)
    print(json.dumps({k: res[k] for k in ("R0", "joint")}, indent=1, default=float))
    print("item1", r1, "item5", r5, "3a", size, "3b", r3b, "ant1 rank", rank1)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument(
        "stage",
        choices=[
            "prep",
            "skies",
            "smoke",
            "arms",
            "pilot",
            "g3",
            "summary",
            "all",
            "cleanup",
        ],
    )
    p.add_argument("--out", default="D:/rang/outputs/floor-2-20261116")
    p.add_argument("--rows-limit", type=int)
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    if a.stage in ("prep", "all"):
        ft.prep(out, a.rows_limit)
    if a.stage in ("skies", "all"):
        skies(out)
    if a.stage == "smoke":
        ft.prep(out, a.rows_limit)
        skies(out)
        smoke(out)
    if a.stage in ("arms", "all"):
        arms(out)
    if a.stage in ("pilot", "all"):
        pilot(out)
    if a.stage in ("g3", "all"):
        g3(out)
    if a.stage in ("summary", "all"):
        summary(out)
    if a.stage == "cleanup":
        import shutil

        for sub in ("prep", "skies"):
            shutil.rmtree(out / sub, ignore_errors=True)
    ft.log("stage", a.stage, "wall_s", round(time.perf_counter() - s0, 1))


if __name__ == "__main__":
    sys.exit(main())
