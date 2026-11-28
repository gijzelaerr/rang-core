# SPDX-License-Identifier: MIT
"""DD14: QP12's facet flux scale when the true facet amplitudes are not 1
(research/dd14-flux-scale.md).

    python tools/oracles/dd14/dd14.py beam ROOT        # B_true by section 2's rule, beam.npz/json
    python tools/oracles/dd14/dd14.py gateo ROOT       # gate GB 1: DD8's O rebuilt in ROOT/gate/O
    python tools/oracles/dd14/dd14.py insert ROOT      # OB in ROOT/O; gate GB 2-3
    python tools/oracles/dd14/dd14.py psf ROOT         # OB's PSF; gate GB 4
    python tools/oracles/dd14/dd14.py gater ROOT       # gate R14 on ROOT/gate/O
    python tools/oracles/dd14/dd14.py apertures ROOT   # the frozen apertures from sky O
    python tools/oracles/dd14/dd14.py loop ROOT ARM    # Q12 QP12 QPN12 AT12 ATP12
    python tools/oracles/dd14/dd14.py ax ROOT          # AX: one scored solve on sky O
    python tools/oracles/dd14/dd14.py score ROOT       # sections 4 and 5
    python tools/oracles/dd14/dd14.py real ROOT        # section 6 (read only, zero solves)

DD7's to DD13's roots are read only.
"""

import hashlib
import importlib.util
import json
import math
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DD13_ROOT = Path("D:/rang/outputs/dd13-20261127")
DD11_ROOT = Path("D:/rang/outputs/dd11-20261126")
DD8_ROOT = Path("D:/rang/outputs/dd8-20261125")
CATSEL = REPO / "research" / "results" / "dd4-eso137" / "catalogue-selection.json"

# section 2: the true beam (frozen)
THETA_B = 57.5 * (1.5e9 / 1043.15e6)  # arcmin, catalogue.py's
ELL = 0.04  # Stokes I elongated along elevation
SIGMA_POINT = 0.64 / math.sqrt(2)  # arcmin per axis (0.64' radial)
SEED_POINT = 1401
LAT, LON = -30.7130, 21.4430  # degrees, the MeerKAT site
PHASE_DIR = (4.25503999, -1.06300733)  # radians, catalogue.py's
# section 4: apertures (frozen)
AP_R, AP_SEP, AP_MIN = 16, 33, 0.020
# section 3: QPC
COMPACT = 0.8
# section 5
FLUX_TOL = 0.05
REAL_TOL, REAL_PIN_TOL = 0.10, 0.05


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd13 = _load("dd13", HERE.parent / "dd13" / "dd13.py")
dd12, dd11, dd10 = dd13.dd12, dd13.dd11, dd13.dd10
dd5, dd4, dd3 = dd13.dd5, dd13.dd4, dd13.dd3
dd2 = dd4.dd2
DD7_ROOT = dd10.DD7_ROOT


def _dd8():
    return _load("dd8", HERE.parent / "dd8" / "dd8.py")


def write_json(path, rec):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    dd10.write_json(path, rec)


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -- the beam (section 2; unit-tested) -------------------------------------------------


def mauch(rho_arcmin, theta=THETA_B):
    """Mauch et al. 2020 cosine-squared power beam (catalogue.py's, vectorised)."""
    x = 1.189 * np.asarray(rho_arcmin, float) / theta
    den = 1.0 - 4.0 * x * x
    safe = np.where(np.abs(den) < 1e-12, 1.0, den)
    return np.where(
        np.abs(den) < 1e-12, (math.pi / 4) ** 2, (np.cos(np.pi * x) / safe) ** 2
    )


def facet_geometry(centres):
    """(rho arcmin, position angle rad east of north) of each (l, m)."""
    c = np.asarray(centres, float)
    rho = np.degrees(np.hypot(c[:, 0], c[:, 1])) * 60.0  # catalogue.py's rho (A1)
    return rho, np.arctan2(c[:, 0], c[:, 1])


def b_nominal(centres):
    return mauch(facet_geometry(centres)[0])


def parallactic(time_s, ra=PHASE_DIR[0], dec=PHASE_DIR[1], lat=LAT, lon=LON):
    """Parallactic angle (rad) at MJD seconds `time_s` (UTC)."""
    jd = np.asarray(time_s, float) / 86400.0 + 2400000.5
    gmst = np.radians((280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360.0)
    h = gmst + math.radians(lon) - ra
    phi = math.radians(lat)
    return np.arctan2(
        np.sin(h), math.tan(phi) * math.cos(dec) - math.sin(dec) * np.cos(h)
    )


def pointing_offsets(nant, sigma=SIGMA_POINT, seed=SEED_POINT):
    """(nant, 2) static offsets (elevation, azimuth) in arcmin."""
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, sigma, (nant, 2))


def beam_true(centres, q, point, ell=ELL, theta=THETA_B):
    """B_true (nblock, nant, ndir) by section 2's rule."""
    rho, psi = facet_geometry(centres)
    ang = psi[None, None, :] - np.asarray(q, float)[:, None, None]
    d_el = rho * np.cos(ang) - point[None, :, 0, None]
    d_az = rho * np.sin(ang) - point[None, :, 1, None]
    r_eff = np.hypot(d_el / (1 + ell / 2), d_az / (1 - ell / 2))
    return mauch(r_eff, theta)


def block_times(time_col, block=None):
    block = dd5.BLOCK if block is None else block
    ut, inv = np.unique(time_col, return_inverse=True)
    b = np.arange(len(ut)) // block
    return np.array([ut[b == k].mean() for k in range(b.max() + 1)]), inv // block


def beam(root):
    """section 2: B_true and B_nom, written before the MS is generated."""
    from rang import core_ms

    root = Path(root)
    st = json.loads((DD7_ROOT / "b" / "setup.json").read_text())
    t = core_ms.open_table(st["subms"])
    tcol = np.asarray(t.getcol("TIME"), float)
    t.close()
    tb, _ = block_times(tcol)
    g = np.load(DD7_ROOT / "b" / "truth.npz")["gains"]
    nblock, nant = g.shape[:2]
    assert len(tb) == nblock, (len(tb), nblock)
    q = parallactic(tb)
    pt = pointing_offsets(nant)
    bt = beam_true(st["centres"], q, pt)
    bn = b_nominal(st["centres"])
    np.savez(root / "beam.npz", b_true=bt, b_nom=bn, q=q, pointing=pt, block_time=tb)
    rec = {"rule": "research/dd14-flux-scale.md section 2", "theta_b_arcmin": THETA_B,
           "ellipticity": ELL, "sigma_point_arcmin_per_axis": SIGMA_POINT, "seed": SEED_POINT,
           "rho_arcmin": facet_geometry(st["centres"])[0].tolist(),
           "q_deg_first_last": [float(np.degrees(q[0])), float(np.degrees(q[-1]))],
           "b_nom": bn.tolist(), "b_true_mean": bt.mean((0, 1)).tolist(),
           "b_true_over_nom_mean": (bt.mean((0, 1)) / bn).tolist(),
           "b_true_over_nom_p5_p95": [np.percentile(bt[..., f] / bn[f], [5, 95]).tolist() for f in range(4)],
           "sqrt_b_true_mean": np.sqrt(bt).mean((0, 1)).tolist()}  # fmt: skip
    write_json(root / "beam.json", rec)


# -- gates GB and the build (section 2) ------------------------------------------------


def gateo(root):
    """GB 1: DD8's insert, unchanged, into ROOT/gate; DD13's setup gate."""
    root = Path(root)
    dd8 = _dd8()
    if not (root / "gate" / "O" / "build.json").exists():
        dd8.insert(root / "gate")
    mine = json.loads((root / "gate" / "O" / "build.json").read_text())
    ref = json.loads((DD13_ROOT / "O" / "build.json").read_text())
    bad = [k for k, v in ref.items() if k != "seconds" and not np.allclose(
        np.atleast_1d(mine[k]).astype(float), np.atleast_1d(v).astype(float), rtol=1e-9, atol=0)]  # fmt: skip
    sky, sky_ref = (
        sha_file(root / "gate" / "O" / "sky.npy"),
        sha_file(DD8_ROOT / "O" / "sky.npy"),
    )
    rec = {"differing": bad, "sky_sha256": sky, "dd8_sky_sha256": sky_ref,
           "GO_pass": bool(mine.get("GO_pass")),
           "pass": not bad and sky == sky_ref and bool(mine.get("GO_pass"))}  # fmt: skip
    write_json(root / "gate" / "GB1.json", rec)
    if not rec["pass"]:
        raise SystemExit("GB 1 failed")


def insert(root):
    """OB = n + sum_f G'_f predict(sky O|f) G'_f^H; GB 2 (B = 1 against gate/O) and 3."""
    root = Path(root)
    dd8 = _dd8()
    dd7, dd6 = dd8.dd7, dd8.dd6
    t0 = time.perf_counter()
    base = DD7_ROOT / "b"
    st = json.loads((base / "setup.json").read_text())
    run = root / "O"
    ms = dd7.copy_run(base, run, st["subms"], ("truth.npz", "sky.npy"))
    idx = dd6.facet_idx(run)
    sky_o = np.load(root / "gate" / "O" / "sky.npy")
    np.save(run / "sky.npy", sky_o)
    c = dd7.read2(
        ms,
        ("WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2", "TIME", "UVW"),
    )
    freq = dd8.freqs(ms)
    g = np.load(base / "truth.npz")["gains"]  # (nblock, nant, ndir, 2)
    bt = np.load(root / "beam.npz")["b_true"]
    gb = g * np.sqrt(bt)[..., None]
    block4 = np.unique(c["TIME"], return_inverse=True)[1] // dd5.BLOCK
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    shape = c["WEIGHT_SPECTRUM"].shape
    pred1 = np.zeros(shape, np.complex64)
    predb = np.zeros(shape, np.complex64)
    for f in range(4):
        vo = dd8.facet_vis(c["UVW"], freq, idx, sky_o, f)
        for h in (0, 1):
            g1 = (g[block4, a1, f, h] * np.conj(g[block4, a2, f, h]))[:, None]
            gg = (gb[block4, a1, f, h] * np.conj(gb[block4, a2, f, h]))[:, None]
            pred1[..., h] += (g1 * vo).astype(np.complex64)
            predb[..., h] += (gg * vo).astype(np.complex64)
        del vo
    n = dd7.regen_noise(c["WEIGHT_SPECTRUM"], st["dd5"]["k"])
    ok = ~(c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]) & (
        c["WEIGHT_SPECTRUM"] > 0
    )
    data_o = dd7.read2(root / "gate" / "O" / "sim.ms", ("DATA",))["DATA"]
    gb2 = float(np.abs(np.where(ok, (n + pred1) - data_o, 0)).max())
    del data_o, pred1
    data = (n + predb).astype(np.complex64)
    dd7.put(ms, DATA=data)
    back = dd7.read2(ms, ("DATA",))["DATA"]
    gb3 = float(np.abs(np.where(ok, back - n - predb, 0)).max())
    np.savez(run / "truth.npz", gains=gb, block=dd5.BLOCK, k=st["dd5"]["k"])
    rec = {"rule": "research/dd14-flux-scale.md section 2", "beam_sha256": sha_file(root / "beam.npz"),
           "GB2_max_abs_B1_minus_gateO": gb2, "GB3_max_abs_OB_minus_n_minus_predict": gb3,
           "GB2_pass": gb2 <= 1e-3, "GB3_pass": gb3 <= 1e-3,
           "truth_amp_geomean_per_dir": [float(np.exp(np.log(np.abs(gb[:, :, f])).mean())) for f in range(4)],
           "sky_sha256": sha_file(run / "sky.npy"), "seconds": time.perf_counter() - t0}  # fmt: skip
    write_json(run / "build.json", rec)
    write_json(root / "gate" / "GB23.json", rec)
    if not (rec["GB2_pass"] and rec["GB3_pass"]):
        raise SystemExit("GB 2/3 failed")


def psf(root):
    root = Path(root)
    dd10.psf(root, "O")
    mine = json.loads((root / "psf" / "O.json").read_text())["peak"]
    ref = json.loads((DD13_ROOT / "psf" / "O.json").read_text())["peak"]
    rec = {"peak": mine, "dd13_peak": ref, "pass": abs(mine - ref) <= 1e-9 * abs(ref)}
    write_json(root / "gate" / "GB4.json", rec)
    if not rec["pass"]:
        raise SystemExit("GB 4 failed")


# -- image rules (section 3; unit-tested) ----------------------------------------------


def image_gains(rule, gains, flags, truth, cyc, bnom=None):
    """DD13's rules plus QN: sqrt(B_nom,f) g/|g| every cycle, untrusted -> sqrt(B_nom,f)."""
    if rule != "QN":
        return dd13.image_gains(rule, gains, flags, truth, cyc)
    bad = dd11.untrusted(gains, flags)
    sb = np.sqrt(np.asarray(bnom, float))[None, None, None, :, None]
    g = sb * (gains / np.abs(gains))
    sub = np.broadcast_to(sb + 0j, gains.shape)
    return np.where(bad[..., None], sub, g), bad


def gater(root):
    """Gate R14: DD13's QP12 cycle 11 on gate/O with DD14's QP12 and QN(B=1) rules."""
    root = Path(root)
    run = root / "gate" / "O"
    ctx = dd4.context(run, ti=dd10.TI)
    ctx["run"] = run
    c = ctx["c"]
    psf_img = np.load(root / "psf" / "O.npy")
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    q = DD13_ROOT / "loop" / "QP12"
    z = np.load(q / "cycle-11" / "gains.npz")
    m11 = np.load(q / "cycle-10" / "next_model.npy")
    ref = np.load(q / "cycle-11" / "next_model.npy")
    t0 = time.perf_counter()
    models = dd4.facet_models(ctx, m11)
    ig, _ = image_gains("QA", z["gains"], z["flags"], None, 11)
    ign, _ = image_gains("QN", z["gains"], z["flags"], None, 11, bnom=np.ones(4))
    resid = dd10.residual_image(ctx, models, ig, c["w_I"])
    comps, _, hinfo = dd11.hogbom_fast(resid, psf_img, clean_interior, clean_interior)
    m12 = dd3.add_components(m11, comps)
    rec = {"QN_B1_equals_QA_bitwise": bool(np.array_equal(ig, ign)),
           "next_model_bitwise": bool(np.array_equal(m12, ref)),
           "max_abs_diff": float(np.abs(m12 - ref).max()), "hogbom": hinfo,
           "seconds": time.perf_counter() - t0}  # fmt: skip
    rec["R14_pass"] = rec["QN_B1_equals_QA_bitwise"] and rec["next_model_bitwise"]
    write_json(root / "gate" / "R14.json", rec)
    if not rec["R14_pass"]:
        raise SystemExit("R14 failed")


# -- apertures (section 4; unit-tested) ------------------------------------------------


def disc(r=AP_R):
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    return xx * xx + yy * yy <= r * r


def ap_sum(img, y, x, r=AP_R):
    d = disc(r)
    return float(img[y - r : y + r + 1, x - r : x + r + 1][d].sum())


def select_apertures(
    sky, idx, interior, pins, r=AP_R, sep=AP_SEP, smin=AP_MIN, facets=(1, 2, 3)
):
    """section 4's rule: {facet: [{"y","x","sky","pin"}...]} from sky O only."""
    from scipy import ndimage, signal

    d = disc(r)
    apmap = signal.fftconvolve(sky, d.astype(float), mode="same")
    mx = ndimage.maximum_filter(apmap, size=2 * r + 1)
    out = {}
    for f in facets:
        inside = ndimage.binary_erosion(interior & (idx == f), structure=d)
        cand = (apmap == mx) & inside & (apmap >= smin - 1e-6)
        ys, xs = np.nonzero(cand)
        sums = np.array([ap_sum(sky, y, x, r) for y, x in zip(ys, xs, strict=True)])
        keep = sums >= smin
        ys, xs, sums = ys[keep], xs[keep], sums[keep]
        taken = []
        for k in np.argsort(-sums, kind="stable"):
            y, x = int(ys[k]), int(xs[k])
            if all((y - a["y"]) ** 2 + (x - a["x"]) ** 2 >= sep * sep for a in taken):
                taken.append({"y": y, "x": x, "sky": float(sums[k]), "pin": False})
        py, px = pins[f - 1]
        near = [a for a in taken if (a["y"] - py) ** 2 + (a["x"] - px) ** 2 <= r * r]
        if near:
            min(near, key=lambda a: (a["y"] - py) ** 2 + (a["x"] - px) ** 2)["pin"] = (
                True
            )
        out[f] = taken
    return out


def facet_flux(model, aps, which="all"):
    sel = [a for a in aps if which == "all" or (which == "pin") == a["pin"]]
    return float(sum(ap_sum(model, a["y"], a["x"]) for a in sel)), float(
        sum(a["sky"] for a in sel)
    )


def geometry():
    st = json.loads((DD7_ROOT / "b" / "setup.json").read_text())
    l, m = dd2.pixel_lm()
    idx, margin = dd2.facet_index_and_margin(l, m, np.array(st["centres"]))
    xg, yg = np.meshgrid(np.arange(dd4.NX), np.arange(dd4.NY))
    e = dd4.EDGE
    interior = (
        (margin >= e) & (xg >= e) & (xg < dd4.NX - e) & (yg >= e) & (yg < dd4.NY - e)
    )
    return st, idx, interior


def apertures(root):
    root = Path(root)
    st, idx, interior = geometry()
    sky = np.load(DD8_ROOT / "O" / "sky.npy")
    aps = select_apertures(sky, idx, interior, st["pins"])
    rec = {"rule": "research/dd14-flux-scale.md section 4", "r": AP_R, "sep": AP_SEP,
           "min_jy": AP_MIN, "sky_sha256": sha_file(DD8_ROOT / "O" / "sky.npy"),
           "apertures": {str(f): a for f, a in aps.items()}}  # fmt: skip
    write_json(root / "apertures.json", rec)


def qpc_factors(model, pins, cat_flux, r=AP_R, compact=COMPACT):
    """section 3: r_f per facet d1-d3 (1 where the pin source is not compact)."""
    out = []
    for (y, x), s in zip(pins, cat_flux, strict=True):
        box = float(model[y - 2 : y + 3, x - 2 : x + 3].sum())
        ring = ap_sum(model, y, x, r)
        ok = ring > 0 and box >= compact * ring and box > 0
        out.append(
            {"box": box, "disc": ring, "compact": bool(ok), "r": s / box if ok else 1.0}
        )
    return out


# -- the loops (section 3) -------------------------------------------------------------

ARMS = {
    "Q12": {"images": "Q", "solve": "gs", "release": None, "prefix": None},
    "QP12": {"images": "QA", "solve": "gs", "release": 2, "prefix": ("Q12", 2, 2)},
    "QPN12": {"images": "QN", "solve": "gs", "release": 2, "prefix": ("Q12", 0, 0)},
    "AT12": {"images": "truth", "solve": "none", "release": None, "prefix": None},
    "ATP12": {"images": "truth", "solve": "none", "release": 2, "prefix": ("AT12", 2, None)},
}  # fmt: skip
N, SCORED = 12, (6, 12)


def products_err(gains, flags, truth):
    """Raw e_d, s_d and scale-removed e_d per direction (section 4); ti = block."""
    g, f = gains[:, 0], flags[:, 0]
    nint, nant = g.shape[:2]
    assert truth.shape[0] == nint
    p, q = np.triu_indices(nant, 1)
    out = {"e": [], "s": [], "e_sr": []}
    for d in range(g.shape[2]):
        P = g[:, p, d] * np.conj(g[:, q, d])
        T = truth[:, p, d] * np.conj(truth[:, q, d])
        ok = (f[:, p, d] == 0) & (f[:, q, d] == 0)
        sel = np.broadcast_to(ok[..., None], P.shape)
        pp, tt = P[sel], T[sel]
        s = float(np.median(np.abs(pp) / np.abs(tt)))
        out["e"].append(float(np.median(np.abs(pp - tt) / np.abs(tt))))
        out["s"].append(s)
        out["e_sr"].append(float(np.median(np.abs(pp / s - tt) / np.abs(tt))))
    return out


def _prefix(root, arm, spec):
    if spec["prefix"] is None:
        return
    src_arm, whole, solve_at = spec["prefix"]
    src, out = root / "loop" / src_arm, root / "loop" / arm
    for k in range(whole):
        d = out / f"cycle-{k}"
        if (d / "info.json").exists():
            continue
        assert (src / f"cycle-{k}" / "info.json").exists(), (
            f"{src_arm} cycle {k} missing"
        )
        d.mkdir(parents=True, exist_ok=True)
        for fn in ("gains.npz", "next_model.npy", "info.json"):
            if (src / f"cycle-{k}" / fn).exists():
                shutil.copy2(src / f"cycle-{k}" / fn, d / fn)
    if solve_at is not None:
        d = out / f"cycle-{solve_at}"
        if not (d / "info.json").exists():
            assert (src / f"cycle-{solve_at}" / "info.json").exists()
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / f"cycle-{solve_at}" / "gains.npz", d / "reuse_gains.npz")
            shutil.copy2(src / f"cycle-{solve_at}" / "info.json", d / "reuse_info.json")


def loop(root, arm):
    """DD13's loop on OB with section 3's arms; resumable per cycle."""
    root = Path(root)
    spec = ARMS[arm]
    _prefix(root, arm, spec)
    ctx = dd10.base_ctx(root, "O")
    c = ctx["c"]
    k = float(json.loads((DD7_ROOT / "b" / "setup.json").read_text())["dd5"]["k"])
    psf_img = np.load(root / "psf" / "O.npy")
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search_pinned = ctx["search"] & (ctx["idx"] > 0)
    sky = np.load(root / "O" / "sky.npy")
    truth = np.load(root / "O" / "truth.npz")["gains"]
    truth5 = truth[:, None]
    bnom = np.load(root / "beam.npz")["b_nom"]
    model = np.load(dd10.START["O"])
    out = root / "loop" / arm
    for cyc in range(N + 1):
        d = out / f"cycle-{cyc}"
        if (out / "stopped.json").exists():
            print(f"{arm}: stopped at the stage rule", flush=True)
            return
        if (d / "info.json").exists():
            model = np.load(d / "next_model.npy") if cyc < N else model
            print(f"{arm} cycle {cyc}: kept", flush=True)
            continue
        t0 = time.perf_counter()
        models = dd4.facet_models(ctx, model)
        info = {"arm": arm, "cycle": cyc, "seconds_predict": time.perf_counter() - t0,
                "model_error": dd10.model_error(ctx, model, sky)}  # fmt: skip
        final, scored = cyc == N, cyc in SCORED
        gains = flags = None
        d.mkdir(parents=True, exist_ok=True)
        if (d / "reuse_gains.npz").exists():
            z = np.load(d / "reuse_gains.npz")
            gains, flags = z["gains"], z["flags"]
            info["solve"] = json.loads((d / "reuse_info.json").read_text())["solve"]
            info["solve_reused_from"] = str(d / "reuse_gains.npz")
            np.savez_compressed(d / "gains.npz", **{kk: z[kk] for kk in z.files})
        elif spec["solve"] == "gs" or scored:
            res = dd11.solve_cycle(ctx, models, "gs", second=scored)
            sol = res["sol"]
            srec, conv = dd10.scores(ctx, models, sol, res.get("sol2"), k)
            gains, flags = np.asarray(sol.gains), np.asarray(sol.flags)
            srec.update(products_err(gains, flags, truth))
            info["solve"] = srec
            info["seconds_solve"] = res["seconds_solve"]
            info["seconds_second"] = res.get("seconds_second")
            save = {"gains": gains, "flags": flags}
            if "sol2" in res:
                save.update(gains2=np.asarray(res["sol2"].gains), flags2=np.asarray(res["sol2"].flags),
                            converged=conv)  # fmt: skip
            np.savez_compressed(d / "gains.npz", **save)
            del res
        if not final:
            t1 = time.perf_counter()
            rule = spec["images"]
            ig, bad = image_gains(rule, gains, flags, truth5, cyc, bnom=bnom)
            if bad is not None:
                info["untrusted_gain_share"] = [
                    float(bad[..., f].mean()) for f in range(4)
                ]
            info["image_rule"] = rule
            resid = dd10.residual_image(ctx, models, ig, c["w_I"])
            info["seconds_image"] = time.perf_counter() - t1
            info["residual_sigma_d1_d3"] = dd10.mad_sigma(resid, clean_interior)
            release = spec["release"] is not None and cyc >= spec["release"]
            search = clean_interior if release else search_pinned
            info["pins_released"] = bool(release)
            t2 = time.perf_counter()
            comps, _, hinfo = dd11.hogbom_fast(resid, psf_img, clean_interior, search)
            info["hogbom"] = hinfo
            info["components_flux"] = float(sum(comps.values()))
            info["seconds_minor"] = time.perf_counter() - t2
            model = dd3.add_components(model, comps)
            np.save(d / "next_model.npy", model)
            del resid
        del models
        info["seconds"] = time.perf_counter() - t0
        (d / "info.json").write_text(json.dumps(info, indent=1, default=float))
        print(
            f"{arm} cycle {cyc}: {json.dumps(info, default=float)[:1500]}", flush=True
        )
        # stage stop (DD13's, on e_sr; amendment A1): loop arms with solves only
        if cyc == 6 and spec["solve"] == "gs" and arm != "Q12":
            q6 = json.loads(
                (root / "loop" / "Q12" / "cycle-6" / "info.json").read_text()
            )
            eff = dd12.effect(info["solve"]["e_sr"], q6["solve"]["e_sr"])
            if eff["reading"].startswith("hurts"):
                write_json(out / "stopped.json", {"cycle": 6, "effect_vs_Q6_sr": eff})
                return


def ax(root):
    """AX: one scored solve with sky O as the model."""
    root = Path(root)
    ctx = dd10.base_ctx(root, "O")
    k = float(json.loads((DD7_ROOT / "b" / "setup.json").read_text())["dd5"]["k"])
    truth = np.load(root / "O" / "truth.npz")["gains"]
    sky = np.load(root / "O" / "sky.npy")
    models = dd4.facet_models(ctx, sky)
    res = dd11.solve_cycle(ctx, models, "gs", second=False)
    srec, _ = dd10.scores(ctx, models, res["sol"], None, k)
    g, f = np.asarray(res["sol"].gains), np.asarray(res["sol"].flags)
    srec.update(products_err(g, f, truth))
    d = root / "loop" / "AX" / "cycle-0"
    d.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(d / "gains.npz", gains=g, flags=f)
    (d / "info.json").write_text(json.dumps({"solve": srec, "seconds_solve": res["seconds_solve"]},
                                            indent=1, default=float))  # fmt: skip


# -- readings (sections 4 and 5) -------------------------------------------------------


def _info(root, arm, cyc):
    f = Path(root) / "loop" / arm / f"cycle-{cyc}" / "info.json"
    return json.loads(f.read_text()) if f.exists() else None


def _final_n(root, arm):
    if (Path(root) / "loop" / arm / "stopped.json").exists():
        return 6
    return 12 if _info(root, arm, 12) else None


def _model_at(root, arm, n):
    """M_n: cycle n-1's next_model."""
    f = Path(root) / "loop" / arm / f"cycle-{n - 1}" / "next_model.npy"
    return np.load(f) if f.exists() else None


def score(root):
    root = Path(root)
    rd = lambda p: json.loads(Path(p).read_text())
    st = json.loads((DD7_ROOT / "b" / "setup.json").read_text())
    aps = {int(f): a for f, a in rd(root / "apertures.json")["apertures"].items()}
    truth = np.load(root / "O" / "truth.npz")["gains"]
    m0c = np.load(dd10.START["O"])
    cat = [float(m0c[y - 2 : y + 3, x - 2 : x + 3].sum()) for y, x in st["pins"]]
    a0, axr = _info(root, "Q12", 0)["solve"], _info(root, "AX", 0)["solve"]
    rec = {"references": {"A0": {k: a0[k] for k in ("e_d", "e_sr", "s")},
                          "AX": {k: axr[k] for k in ("e_d", "e_sr", "s")}}, "points": {}}  # fmt: skip
    pts = rec["points"]

    def flux_block(model, model0):
        fb = {}
        for which in ("all", "nonpin", "pin"):
            fx, fs, f0 = [], [], []
            for f in (1, 2, 3):
                a, s = facet_flux(model, aps[f], which)
                a0_ = (
                    facet_flux(model0, aps[f], which)[0] if model0 is not None else None
                )
                fx.append(a)
                fs.append(s)
                f0.append(a0_)
            fb[which] = {"F": fx, "F_sky": fs, "F_on_O": f0,
                         "eps": [a / s - 1 if s else None for a, s in zip(fx, fs, strict=True)],
                         "kappa": [a / b - 1 if b else None for a, b in zip(fx, f0, strict=True)]}  # fmt: skip
        return fb

    # the arms on O (A2: DD13 kept no copies of DD12's Q12 and AT12 models)
    dd12_root = Path("D:/rang/outputs/dd12-20261126")
    o_ref = {
        "Q12": (dd12_root, "Q12"),
        "QP12": (DD13_ROOT, "QP12"),
        "QPN12": (DD13_ROOT, "QP12"),
        "AT12": (dd12_root, "AT12"),
        "ATP12": (DD13_ROOT, "ATP12"),
    }
    for arm in ARMS:
        for n in SCORED:
            inf = _info(root, arm, n)
            if not inf or "e_sr" not in (inf.get("solve") or {}):
                continue
            s = inf["solve"]
            z = np.load(root / "loop" / arm / f"cycle-{n}" / "gains.npz")
            G, harm, r = dd11.reading(s["e_sr"], a0["e_sr"], axr["e_sr"])
            Graw, _harm_raw, rraw = dd11.reading(s["e_d"], a0["e_d"], axr["e_d"])
            p = {"e_d": s["e_d"], "e_sr": s["e_sr"], "s": s["s"], "G_sr": G, "harm_sr": harm,
                 "reading_sr": r, "G_raw": Graw, "reading_raw": rraw,
                 "perdir_converged": s.get("perdir_converged"), "d3_amp": s.get("d3_amp"),
                 "e_over_ehat": s.get("e_over_ehat"),
                 "diag": dd11.gain_errors(z["gains"], z["flags"], truth)}  # fmt: skip
            m = _model_at(root, arm, n)
            m0 = _model_at(*o_ref[arm], n)
            p["flux"] = flux_block(m, m0)
            pts[f"{arm[:-2]}{n}"] = p
            # QPC from QP12 (section 3)
            if arm == "QP12":
                fac = qpc_factors(m, st["pins"], cat)
                fac0 = qpc_factors(m0, st["pins"], cat)
                mq, mq0 = m.copy(), m0.copy()
                _, idx, _ = geometry()
                gq = z["gains"].copy()
                for f in (1, 2, 3):
                    mq[idx == f] *= fac[f - 1]["r"]
                    mq0[idx == f] *= fac0[f - 1]["r"]
                    gq[..., f, :] /= math.sqrt(fac[f - 1]["r"])
                pe = products_err(gq, z["flags"], truth)
                Gq, hq, rq = dd11.reading(pe["e_sr"], a0["e_sr"], axr["e_sr"])
                pts[f"QPC{n}"] = {"e_d": pe["e"], "e_sr": pe["e_sr"], "s": pe["s"],
                                  "G_sr": Gq, "harm_sr": hq, "reading_sr": rq, "qpc_factors": fac,
                                  "qpc_factors_on_O": fac0, "flux": flux_block(mq, mq0)}  # fmt: skip
            p["e_check_vs_dd5"] = float(
                max(abs(a - b) for a, b in zip(s["e"], s["e_d"], strict=True))
            )
    # effects and Gamma on e_sr
    for name, p in pts.items():
        n = 12 if name.endswith("12") else 6
        if f"Q{n}" in pts and name != f"Q{n}":
            p["effect_vs_Q_sr"] = dd12.effect(p["e_sr"], pts[f"Q{n}"]["e_sr"])
        for ctl in ("AT", "ATP"):
            if f"Q{n}" in pts and f"{ctl}{n}" in pts:
                eq, ec = pts[f"Q{n}"]["e_sr"][1], pts[f"{ctl}{n}"]["e_sr"][1]
                p[f"Gamma_sr_vs_{ctl}"] = (
                    (eq - p["e_sr"][1]) / (eq - ec) if eq != ec else None
                )
        ctl = "AT" if name.startswith("Q") and not name.startswith("QP") else "ATP"
        if name.startswith("Q") and f"{ctl}{n}" in pts:
            kx = p["flux"]["all"]["kappa"]
            kc = pts[f"{ctl}{n}"]["flux"]["all"]["kappa"]
            p["phi"] = [a - b for a, b in zip(kx, kc, strict=True)]
            kxn = p["flux"]["nonpin"]["kappa"]
            kcn = pts[f"{ctl}{n}"]["flux"]["nonpin"]["kappa"]
            p["phi_nonpin"] = [a - b if a is not None and b is not None else None
                               for a, b in zip(kxn, kcn, strict=True)]  # fmt: skip
            fc = pts[f"{ctl}{n}"]["flux"]["all"]
            p["flux_readable"] = [
                a > 0.2 * s for a, s in zip(fc["F"], fc["F_sky"], strict=True)
            ]
            p["criterion_F"] = bool(
                all(abs(x) <= FLUX_TOL for x in p["phi"]) and all(p["flux_readable"])
            )
        if "effect_vs_Q_sr" in p:
            p["criterion_G"] = bool(p["reading_sr"] in ("closes", "partly")
                                    and p["effect_vs_Q_sr"]["reading"].startswith("helps"))  # fmt: skip
    # final N and the answer
    fin = {"QP": _final_n(root, "QP12"), "QPN": _final_n(root, "QPN12")}
    fin["QPC"] = fin["QP"]
    rec["final_N"] = fin
    meets = {a: bool(n and f"{a}{n}" in pts and pts[f"{a}{n}"].get("criterion_G")
                     and pts[f"{a}{n}"].get("criterion_F")) for a, n in fin.items()}  # fmt: skip
    rec["meets_G_and_F"] = meets
    if all(n for n in fin.values()):
        if meets["QPN"]:
            ans, arm_in = (
                "in, with the beam in the model: QP12's rules go into the real DD recipe whose catalogue model is apparent through the nominal beam",
                "QPN",
            )
        elif meets["QPC"]:
            ans, arm_in = "in, with the catalogue renormalisation (QPC)", "QPC"
        else:
            ans, arm_in = (
                "out: QP12's convention moves the facet flux scale or breaks the loop under the offset; the pinned rule stays in the recipe",
                None,
            )
        rec["answer"] = ans
        rec["arm_in"] = arm_in
        rec["QP12_survives_without_beam"] = meets["QP"]
    for arm in list(ARMS):
        cyc = []
        for k in range(N + 1):
            ci = _info(root, arm, k)
            if not ci:
                break
            sv = ci.get("solve") or {}
            cyc.append({kk: ci.get(kk) for kk in ("model_error", "hogbom", "components_flux", "untrusted_gain_share",
                                                  "residual_sigma_d1_d3", "image_rule", "pins_released")}
                       | {"e_d": sv.get("e_d"), "e_sr": sv.get("e_sr"), "s": sv.get("s"),
                          "global_fraction": sv.get("global_fraction")})  # fmt: skip
        rec[f"cycles_{arm}"] = cyc
    write_json(root / "score.json", rec)


# -- the real-data flux check (section 6) ----------------------------------------------


def real_apertures(
    comps, idx, interior, pins, r=AP_R, sep=AP_SEP, smin=AP_MIN, facets=(1, 2, 3)
):
    """Section 6 (with A1): centres at components >= smin, brightest first,
    merged within sep; catalogue flux = every component's S_app inside the disc."""
    from scipy import ndimage

    d = disc(r)
    out = {}
    for f in facets:
        inside = ndimage.binary_erosion(interior & (idx == f), structure=d)
        mine = sorted((cc for cc in comps if cc["S"] >= smin and inside[cc["y"], cc["x"]]
                       and idx[cc["y"], cc["x"]] == f), key=lambda cc: -cc["S"])  # fmt: skip
        taken = []
        for cc in mine:
            if all(
                (cc["y"] - a["y"]) ** 2 + (cc["x"] - a["x"]) ** 2 >= sep * sep
                for a in taken
            ):
                taken.append({"y": cc["y"], "x": cc["x"], "id": cc["id"], "pin": False})
        for a in taken:
            a["cat"] = float(sum(cc["S"] for cc in comps
                                 if (cc["y"] - a["y"]) ** 2 + (cc["x"] - a["x"]) ** 2 <= r * r))  # fmt: skip
            py, px = pins[f - 1]
            a["pin"] = abs(a["y"] - py) <= 2 and abs(a["x"] - px) <= 2
        out[f] = taken
    return out


def real(root):
    root = Path(root)
    score_rec = json.loads((root / "score.json").read_text())
    arm_in = score_rec.get("arm_in")
    if arm_in is None:
        raise SystemExit("section 6: the frozen rule does not read 'in'; no real check")
    st, idx, interior = geometry()
    sel = json.loads(CATSEL.read_text())
    comps = []
    for cc in sel["model_components"]:
        x = round(dd4.NX / 2 - cc["l"] / dd2.DELTA)
        y = round(cc["m"] / dd2.DELTA + dd4.NY / 2)
        if 0 <= x < dd4.NX and 0 <= y < dd4.NY:
            comps.append({"id": cc["id"], "y": y, "x": x, "S": float(cc["s_app"])})
    aps = real_apertures(comps, idx, interior, st["pins"])
    models = {"RM": np.load(DD7_ROOT / "models" / "RM.npy"),
              "R-Q6": np.load(DD11_ROOT / "loop" / "R-Q6" / "cycle-5" / "next_model.npy"),
              "R-QP12": np.load(DD13_ROOT / "loop" / "R-QP12" / "cycle-11" / "next_model.npy")}  # fmt: skip
    if arm_in == "QPC":
        cat = [
            float(models["RM"][y - 2 : y + 3, x - 2 : x + 3].sum())
            for y, x in st["pins"]
        ]
        fac = qpc_factors(models["R-QP12"], st["pins"], cat)
        mq = models["R-QP12"].copy()
        for f in (1, 2, 3):
            mq[idx == f] *= fac[f - 1]["r"]
        models["R-QPC12"] = mq
    rec = {"rule": "research/dd14-flux-scale.md section 6 (A1)", "arm_in": arm_in,
           "apertures": {str(f): a for f, a in aps.items()}, "models": {}}  # fmt: skip
    for name, m in models.items():
        r_ = {}
        for which in ("nonpin", "pin"):
            eps = []
            for f in (1, 2, 3):
                sel_ = [a for a in aps[f] if a["pin"] == (which == "pin")]
                if not sel_:
                    eps.append(None)
                    continue
                fm = sum(ap_sum(m, a["y"], a["x"]) for a in sel_)
                fc = sum(a["cat"] for a in sel_)
                eps.append(fm / fc - 1)
            r_[which] = eps
        rec["models"][name] = r_
    rm = rec["models"]["RM"]["nonpin"] + rec["models"]["RM"]["pin"]
    rec["RM_code_check_max_abs"] = max(abs(x) for x in rm if x is not None)
    x = "R-QPC12" if arm_in == "QPC" else "R-QP12"
    e_x, e_q = rec["models"][x]["nonpin"], rec["models"]["R-Q6"]["nonpin"]
    readable = [f for f in range(3) if e_x[f] is not None]
    rec["reading_arm"] = x
    rec["agrees_with_catalogue"] = {
        f"d{f + 1}": abs(e_x[f]) <= REAL_TOL for f in readable
    }
    rec["agrees_with_pinned_loop"] = {f"d{f + 1}": abs(e_x[f] - e_q[f]) <= REAL_PIN_TOL
                                      for f in readable if e_q[f] is not None}  # fmt: skip
    rec["not_readable"] = [f"d{f + 1}" for f in range(3) if e_x[f] is None]
    rec["real_check_passes"] = bool(readable) and all(
        rec["agrees_with_catalogue"].values()
    )
    write_json(root / "real.json", rec)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    fn = {"beam": beam, "gateo": gateo, "insert": insert, "psf": psf, "gater": gater,
          "apertures": apertures, "ax": ax, "score": score, "real": real}  # fmt: skip
    if cmd in fn:
        fn[cmd](argv[1])
    elif cmd == "loop":
        loop(argv[1], argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
