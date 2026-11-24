# SPDX-License-Identifier: MIT
"""DD4: the catalogue-pinned DD loop on ESO 137-006 (research/dd4-eso137.md).

    python tools/oracles/dd4/dd4.py setup SUBMS CATALOGUE.json RUN
    python tools/oracles/dd4/dd4.py rang RUN [--di|--di0] [--cap N --name ARM --model0 NPY]
    python tools/oracles/dd4/dd4.py oracle RUN SCRATCH     # arm O (WSL QuartiCal, WSClean)
    python tools/oracles/dd4/dd4.py control RUN SCRATCH    # C0 (A1, A2)
    python tools/oracles/dd4/dd4.py control1 RUN SCRATCH   # C0', C1 (A4)
    python tools/oracles/dd4/dd4.py control2 RUN SCRATCH   # C2m, C2e, E1 (A5)
    python tools/oracles/dd4/dd4.py score RUN
    python tools/oracles/dd4/dd4.py scoreb RUN             # DD4b (research/dd4b-eso137.md)

The loop and the shared minor cycle are DD3c's (`tools/oracles/dd3/dd3.py`,
arm C); this driver generalises them to the field's directions, real
flags and weights, the pinned direction d0 and the 2880² grid.
"""

import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd3 = _load("dd3", HERE.parent / "dd3" / "dd3.py")
dd2 = dd3.dd2
NX = NY = 2880
for mod in (dd2, dd3):  # DD4's grid (section 4)
    mod.NX = mod.NY = NX
DELTA, EPS, CAP = dd2.DELTA, dd2.EPS, dd2.CAP
NCYCLE, EDGE = dd3.NCYCLE, dd3.EDGE
ANNULUS = (5, 40)  # pixels, section 5
FIELD_EXCLUDE_PX = 40  # 2' at 3"
FIELD_MIN_JY = 0.005


def read_sub(ms):
    from rang import core_ms

    t = core_ms.open_table(str(ms))
    c = {k: t.getcol(k) for k in ("TIME", "ANTENNA1", "ANTENNA2", "UVW", "DATA",
                                   "WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW")}  # fmt: skip
    ant = core_ms.open_table(str(Path(ms) / "ANTENNA"))
    c["ant_names"] = [str(n) for n in ant.getcol("NAME")]
    c["ant_pos"] = np.asarray(ant.getcol("POSITION"), float)
    fld = core_ms.open_table(str(Path(ms) / "FIELD"))
    c["phase_dir"] = np.asarray(fld.getcol("PHASE_DIR"), float).reshape(-1, 2)[0]
    spw = core_ms.open_table(str(Path(ms) / "SPECTRAL_WINDOW"))
    c["freq"] = np.asarray(spw.getcol("CHAN_FREQ"), float).reshape(-1)
    if c["DATA"].shape[-1] == 2:
        # The pilot stores XX and YY only: rang's solver takes four
        # correlations, so the cross hands are zero with zero weight.
        for key, dtype in (
            ("DATA", np.complex64),
            ("WEIGHT_SPECTRUM", np.float32),
            ("FLAG", bool),
        ):
            two = c[key]
            four = np.zeros(two.shape[:2] + (4,), dtype)
            four[..., 0], four[..., 3] = two[..., 0], two[..., 1]
            if key == "FLAG":
                four[..., 1] = four[..., 2] = two[..., 0] | two[..., 1]
            c[key] = four
        c["ncorr_ms"] = 2
    flag = c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]
    w = c["WEIGHT_SPECTRUM"].astype(np.float64)
    wxx = np.where(flag[..., 0], 0.0, w[..., 0])
    wyy = np.where(flag[..., 3], 0.0, w[..., 3])
    # Stokes I gridding weight as WSClean 3.7 forms it from the parallel
    # hands: min(w_xx, w_yy), zero where either is flagged (DD4 amendment A2;
    # its PSF then matches WSClean's to 4.9e-8).
    c["w_I"] = np.where((wxx > 0) & (wyy > 0), np.minimum(wxx, wyy), 0.0)
    return c


def setup(subms, catalogue, run):
    from rang import core_grid, core_wgridder

    run.mkdir(parents=True, exist_ok=False)
    cat = json.loads(Path(catalogue).read_text())
    c = read_sub(subms)
    dirs = cat["directions"]
    centres = np.array([[d["l"], d["m"]] for d in dirs])
    (run / "facets.reg").write_text(
        dd2.region_text(dd2.voronoi_polygons(centres), centres, c["phase_dir"]),
        encoding="utf-8",
    )
    psf = core_wgridder.fits_image(
        c["UVW"], c["freq"], np.ones(c["w_I"].shape, complex), c["w_I"], 2 * NX, 2 * NY,
        dd2.SCALE_ARCSEC, epsilon=EPS,
    )["psf"]  # fmt: skip
    np.save(run / "psf.npy", psf)
    m0 = np.zeros((NY, NX))
    pins = []
    for comp in cat["model_components"]:
        x = round(NX / 2 - comp["l"] / DELTA)
        y = round(NY / 2 + comp["m"] / DELTA)
        if 0 <= x < NX and 0 <= y < NY:
            m0[y, x] += comp["s_app"]
    for d in dirs[1:]:
        pins.append([round(NY / 2 + d["m"] / DELTA), round(NX / 2 - d["l"] / DELTA)])
    np.save(run / "model0.npy", m0)
    hdr = core_grid.wcs_header(c["phase_dir"], NX, NY, dd2.SCALE_ARCSEC, c["freq"])
    hdr["BUNIT"] = "JY/PIXEL"
    (run / "header.json").write_text(json.dumps(hdr))
    (run / "setup.json").write_text(json.dumps({
        "subms": str(subms), "catalogue": str(catalogue), "ndir": len(dirs),
        "centres": centres.tolist(), "pins": pins,
        "model0_flux": float(m0.sum()), "nrow": len(c["TIME"]), "nchan": len(c["freq"]),
        "weights_equal_xx_yy": bool(np.array_equal(c["WEIGHT_SPECTRUM"][..., 0], c["WEIGHT_SPECTRUM"][..., 3])),
    }, indent=1))  # fmt: skip
    print((run / "setup.json").read_text())


def context(run, di=False, di0=False):
    st = json.loads((run / "setup.json").read_text())
    c = read_sub(st["subms"])
    centres = np.array(st["centres"])
    if di:
        centres = centres[:1]
    if di:  # one direction: the whole image is one facet
        idx = np.zeros((NY, NX), int)
        margin = np.full(idx.shape, 1e9)
    else:
        l, m = dd2.pixel_lm()
        idx, margin = dd2.facet_index_and_margin(l, m, centres)
    _, _, block, centres_t = dd2.interval_axes(c)
    xg, yg = np.meshgrid(np.arange(NX), np.arange(NY))
    interior = (margin >= EDGE) & (xg >= EDGE) & (xg < NX - EDGE) & (
        yg >= EDGE) & (yg < NY - EDGE)  # fmt: skip
    search = interior.copy()
    for y, x in st["pins"]:
        search[max(y - 2, 0) : y + 3, max(x - 2, 0) : x + 3] = False
    return {"st": st, "c": c, "centres": centres, "ndir": len(centres), "idx": idx,
            "interior": interior, "search": search, "block": block, "centres_t": centres_t,
            "pinned": [0] if (len(centres) > 1 or di0) else []}  # fmt: skip


def facet_models(ctx, model):
    from rang import core_wgridder

    c, ndir = ctx["c"], ctx["ndir"]
    out = np.zeros(c["DATA"].shape[:2] + (ndir, 4), np.complex64)
    for f in range(ndir):
        v = core_wgridder.dirty2vis(
            uvw=c["UVW"], freq=c["freq"],
            dirty=np.ascontiguousarray(np.where(ctx["idx"] == f, model, 0.0).T),
            pixsize_x=DELTA, pixsize_y=DELTA, epsilon=EPS, flip_v=True, flip_w=True,
        )  # fmt: skip
        out[:, :, f, 0] = v
        out[:, :, f, 3] = v
    return out


def residual_image(ctx, models, gains):
    """The flat-gain facet image (1/c per facet, DD2b's convention) of
    DATA - sum_f G_p,f M_f G_q,f^H."""

    c, block, ndir = ctx["c"], ctx["block"], ctx["ndir"]
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    r = c["DATA"].astype(np.complex128)
    for f in range(ndir):
        gp, gq = gains[block, 0, a1, f], gains[block, 0, a2, f]
        r[..., 0] -= gp[:, None, 0] * models[:, :, f, 0] * np.conj(gq[:, None, 0])
        r[..., 3] -= gp[:, None, 1] * models[:, :, f, 3] * np.conj(gq[:, None, 1])
    return facet_image(ctx, r, gains)


def facet_image(ctx, r, gains):
    """The flat-gain facet image of the four-correlation visibilities r."""
    from rang import core_wgridder

    c, block, ndir = ctx["c"], ctx["block"], ctx["ndir"]
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    w = c["w_I"]
    image = np.zeros((NY, NX))
    for f in range(ndir):
        gp, gq = gains[block, 0, a1, f], gains[block, 0, a2, f]
        vis = 0.5 * (np.conj(gp[:, None, 0]) * r[..., 0] * gq[:, None, 0]
                     + np.conj(gp[:, None, 1]) * r[..., 3] * gq[:, None, 1])  # fmt: skip
        img = core_wgridder.fits_image(c["UVW"], c["freq"], vis, w, NX, NY, dd2.SCALE_ARCSEC,
                                       epsilon=EPS)["dirty"]  # fmt: skip
        cf = dd2.correction(gp, gq, w, "a")
        sel = ctx["idx"] == f
        image[sel] = img[sel] / cf
    return image


def per_direction_converged(g1, g2, f1, f2, stop=CAP["stop_criterion"]):
    """Per direction, the fraction of unflagged solution cells whose relative
    change between two solves one iteration apart is below the solver's own
    test, |dg|^2 / |g|^2 < stop^2 (DD4c section 3)."""
    d2 = (np.abs(g2 - g1) ** 2).sum(-1)
    n2 = (np.abs(g1) ** 2).sum(-1)
    ok = (f1 == 0) & (f2 == 0) & (n2 > 0)
    conv = ok & (d2 < stop * stop * np.where(n2 > 0, n2, 1.0))
    return [
        float(conv[..., f].sum() / max(ok[..., f].sum(), 1)) for f in range(g1.shape[3])
    ]


def arm_r(run, di=False, di0=False, cap=None, name=None, model0=None, calmode="ap",
          own_gain=False, perdir=False):  # fmt: skip
    """Arm R, or DI (one direction, free), or DI0 (one direction, pinned:
    the publisher's DI calibration only; DD4 amendment A3, post hoc).
    `cap`, `name` and `model0` are DD4b's (research/dd4b-eso137.md): the
    iteration cap, the arm's directory name and its start model. `calmode`
    "p", `own_gain` and `perdir` are DD4c's (research/dd4c-eso137.md): the
    phase-only solve, each direction's own gain in its update, and the
    per-direction convergence from a second solve one iteration longer."""
    from rang import cal_gain

    ctx = context(run, di or di0, di0)
    c = ctx["c"]
    psf = np.load(run / "psf.npy")
    model = np.load(model0 if model0 else run / "model0.npy")
    arm = name or ("DI0" if di0 else ("DI" if di else "R"))
    caps = dict(CAP, max_iterations=cap) if cap else CAP
    for k in range(NCYCLE + 1):
        t0 = time.perf_counter()
        models = facet_models(ctx, model)
        args = (c["DATA"], models, c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"],
                c["ANTENNA1"], c["ANTENNA2"], ctx["block"])  # fmt: skip
        kw = {"nant": len(c["ant_names"]), "refant": 0, "pinned_directions": ctx["pinned"],
                  "calmode": calmode, "phase_last_direction_gain": not own_gain}  # fmt: skip
        sol = cal_gain.solve_dd(*args, **kw, **caps)
        t1 = time.perf_counter()
        extra = {}
        if perdir:
            more = dict(caps, max_iterations=sol.iterations + 1, stop_fraction=1.0)
            sol2 = cal_gain.solve_dd(*args, **kw, **more)
            extra = {"perdir_converged": per_direction_converged(
                sol.gains, sol2.gains, sol.flags, sol2.flags), "iterations_second": sol2.iterations,
                "seconds_second_solve": time.perf_counter() - t1}  # fmt: skip
            del sol2
            t1 = time.perf_counter()
        residual = residual_image(ctx, models, sol.gains)
        t2 = time.perf_counter()
        info = {"iterations": sol.iterations, "fraction": sol.converged_fraction,
                "seconds_solve": t1 - t0, "seconds_image": t2 - t1, **extra}  # fmt: skip
        comps, new_model = None, model
        if k < NCYCLE:
            comps, _, hinfo = dd3.hogbom(residual, psf, ctx["interior"], ctx["search"])
            info["hogbom"] = hinfo
            new_model = dd3.add_components(model, comps)
        dd3.save_cycle(
            run / arm / f"cycle-{k}", model, sol.gains, sol.flags, residual, comps, info
        )
        print(f"{arm} cycle {k}: {json.dumps(info)}", flush=True)
        model = new_model
        del models


def arm_o(run, scratch, gtype="diag_complex", cap=150, name="O", model0=None):
    """Arm O; DD4c's Oc with `gtype` "phase", `cap` 500 and its start model.
    Step 3 runs on DD4 A5's matched four-correlation copy."""
    ctx = context(run)
    c, ndir = ctx["c"], ctx["ndir"]
    psf = np.load(run / "psf.npy")
    hdr = json.loads((run / "header.json").read_text())
    model = np.load(model0 if model0 else run / "model0.npy")
    o = run / name
    o.mkdir(exist_ok=True)
    pinned = "[" + ",".join(map(str, ctx["pinned"])) + "]"
    run_wsl("step4_o0.sh", dd3.to_wsl(ctx["st"]["subms"]), scratch, ndir)
    for k in range(NCYCLE + 1):
        d = o / f"cycle-{k}"
        d.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        for f in range(ndir):
            dd3.write_fits(
                d / f"facet{f}-model.fits", np.where(ctx["idx"] == f, model, 0.0), hdr
            )
        dd3.write_fits(d / "full-model.fits", model, hdr)
        dd3.write_fits(d / "full-model-pb.fits", model, hdr)
        log1 = run_wsl("step4_o1.sh", scratch, dd3.to_wsl(d), ndir, pinned, gtype, cap)
        gains, flags, qinfo = dd3.qc_gains(d / "gains")
        ok = dd2.write_h5(
            d / "solved.h5", gains, flags, c, ctx["centres_t"], ctx["centres"]
        )
        t1 = time.perf_counter()
        log2 = run_wsl(
            "step4_o2.sh", scratch, dd3.to_wsl(d), dd3.to_wsl(run / "facets.reg")
        )
        residual = dd2.read_fits(d / "resid-image-pb.fits")
        t2 = time.perf_counter()
        info = {**qinfo, "h5_roundtrip": ok, "seconds_solve": t1 - t0,
                "seconds_image": t2 - t1, "log_tail": (log1 + log2)[-400:]}  # fmt: skip
        comps, new_model = None, model
        if k < NCYCLE:
            comps, _, hinfo = dd3.hogbom(residual, psf, ctx["interior"], ctx["search"])
            info["hogbom"] = hinfo
            new_model = dd3.add_components(model, comps)
        dd3.save_cycle(d, model, gains, flags, residual, comps, info)
        print(f"{name} cycle {k}: {json.dumps({a: b for a, b in info.items() if a != 'log_tail'})}",
              flush=True)  # fmt: skip
        model = new_model


def run_wsl(script, *args):
    import subprocess

    cmd = [
        "wsl",
        "-d",
        "Ubuntu",
        "--",
        "bash",
        dd3.to_wsl(HERE / script),
        *map(str, args),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"{script} failed: {r.stdout[-2000:]} {r.stderr[-2000:]}")
    return r.stdout


# -- scoring --------------------------------------------------------------------------


def restoring_beam(psf):
    """A circular Gaussian fitted to the PSF main lobe: sigma from the
    half-power area of the central lobe (pixels)."""
    cy, cx = NY, NX
    sub = psf[cy - 30 : cy + 31, cx - 30 : cx + 31]
    area = float((sub >= 0.5).sum())  # pixels above half power
    fwhm = 2.0 * math.sqrt(area / math.pi)
    return fwhm / (2 * math.sqrt(2 * math.log(2)))


def measures(run, ctx, arm, psf, sigma):
    from scipy.ndimage import gaussian_filter

    d = run / arm / f"cycle-{NCYCLE}"
    res = np.load(d / "residual.npy").astype(float)
    model = np.load(d / "model.npy")
    yy, xx = np.indices(res.shape)
    out = {"offaxis_rms": {}}
    for k, (y, x) in enumerate(ctx["st"]["pins"]):
        r = np.hypot(yy - y, xx - x)
        sel = (r >= ANNULUS[0]) & (r <= ANNULUS[1]) & ctx["interior"]
        v = res[sel]
        out["offaxis_rms"][f"d{k + 1}"] = float(
            1.4826 * np.median(np.abs(v - np.median(v)))
        )
    # Field rms: interior pixels at least 2' from every model component >= 5 mJy.
    far = np.ones(res.shape, bool)
    for y, x in zip(*np.nonzero(model >= FIELD_MIN_JY), strict=True):
        far[max(y - FIELD_EXCLUDE_PX, 0):y + FIELD_EXCLUDE_PX + 1,
            max(x - FIELD_EXCLUDE_PX, 0):x + FIELD_EXCLUDE_PX + 1] = False  # fmt: skip
    v = res[far & ctx["interior"]]
    rms = float(1.4826 * np.median(np.abs(v - np.median(v))))
    restored = gaussian_filter(model, sigma) * (2 * math.pi * sigma * sigma) + res
    out.update(field_rms=rms, peak=float(restored.max()), dynamic_range=float(restored.max() / rms),
               field_pixels=int(v.size))  # fmt: skip
    return out


def score_b(run):
    """DD4b's measures and rules (research/dd4b-eso137.md, section 3)."""
    ctx = context(run)
    psf = np.load(run / "psf.npy")
    sigma = restoring_beam(psf)
    arms = [a for a in ("R", "DI0", "R500", "R500x", "DI0x")
            if (run / a / f"cycle-{NCYCLE}").exists()]  # fmt: skip
    m = {a: measures(run, ctx, a, psf, sigma) for a in arms}
    rec = {
        "note": "research/dd4b-eso137.md",
        "restoring_sigma_px": sigma,
        "measures": m,
    }
    conv = {}
    for a in ("R", "R500", "R500x"):
        if a not in arms:
            continue
        cyc = [json.loads((run / a / f"cycle-{k}" / "info.json").read_text())
               for k in range(NCYCLE + 1)]  # fmt: skip
        off = [(c["fraction"] - 0.25) / 0.75 for c in cyc]
        its = [c["iterations"] for c in cyc]
        g = np.load(run / a / f"cycle-{NCYCLE}" / "gains.npz")
        amp = np.abs(g["gains"])
        ok = g["flags"] == 0
        per = {f"d{f}": [float(np.median(amp[..., f, :][ok[..., f]])),
                         float(np.std(amp[..., f, :][ok[..., f]]))]
               for f in range(amp.shape[3])}  # fmt: skip
        verdict = ("converges" if all(o >= 0.99 for o in off) and max(its) < 500
                   else "partly" if max(off) > 0.10 else "does not converge")  # fmt: skip
        conv[a] = {"offaxis_fraction": off, "iterations": its, "verdict": verdict,
                   "final_gain_median_abs_and_std": per}  # fmt: skip
    rec["convergence"] = conv

    def versus(a, b):
        r = {
            k: m[a]["offaxis_rms"][k] / m[b]["offaxis_rms"][k]
            for k in m[a]["offaxis_rms"]
        }
        q = float(np.median(list(r.values())))
        dr_ok = m[a]["dynamic_range"] >= m[b]["dynamic_range"]
        v = (
            "DD helps"
            if (q <= 0.90 and dr_ok)
            else ("DD worse" if q >= 1.05 else "null")
        )
        return {"rms_ratio": r, "q": q, "dr_ratio": m[a]["dynamic_range"] / m[b]["dynamic_range"],
                "verdict": v}  # fmt: skip

    if {"R500", "DI0"} <= set(arms):
        rec["R500_vs_DI0"] = versus("R500", "DI0")
    if {"R500x", "DI0x"} <= set(arms):
        rec["R500x_vs_DI0x"] = versus("R500x", "DI0x")
        rho = m["R500x"]["offaxis_rms"]["d1"] / m["DI0x"]["offaxis_rms"]["d1"]
        half = m["R500x"]["offaxis_rms"]["d1"] <= 0.5 * m["R500"]["offaxis_rms"]["d1"]
        v = ("supported" if (rho <= 1.0 and half) else
             "not supported" if rho >= 2.0 else "inconclusive")  # fmt: skip
        rec["d1_test"] = {"rho": rho, "d1_R500x_le_half_R500": bool(half), "verdict": v}
    if {"R", "R500"} <= set(arms):
        nant = len(ctx["c"]["ant_names"])
        p, q = np.triu_indices(nant, 1)
        ga = np.load(run / "R" / "cycle-0" / "gains.npz")["gains"]
        gb = np.load(run / "R500" / "cycle-0" / "gains.npz")["gains"]
        d = np.abs(
            ga[:, :, p] * np.conj(ga[:, :, q]) - gb[:, :, p] * np.conj(gb[:, :, q])
        )
        rec["cycle0_gain_product_change_150_to_500"] = {
            f"d{f}": [float(np.median(d[..., f, :])), float(d[..., f, :].max())]
            for f in range(d.shape[3])
        }
    (run / "scoreb.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(json.dumps(rec, indent=1))


def score_c(run):
    """DD4c's convergence per direction and Rc (and Rq) against DI0c
    (research/dd4c-eso137.md, section 3)."""
    ctx = context(run)
    psf = np.load(run / "psf.npy")
    sigma = restoring_beam(psf)
    arms = [
        a for a in ("Rc", "Rq", "DI0c", "Oc") if (run / a / f"cycle-{NCYCLE}").exists()
    ]
    m = {a: measures(run, ctx, a, psf, sigma) for a in arms}
    rec = {"note": "research/dd4c-eso137.md", "measures": m, "convergence": {}}
    for a in ("Rc", "Rq"):
        if a not in arms:
            continue
        cyc = [json.loads((run / a / f"cycle-{k}" / "info.json").read_text())
               for k in range(NCYCLE + 1)]  # fmt: skip
        per = np.array([c["perdir_converged"] for c in cyc])  # cycles x directions
        verdict = {}
        for f in range(1, per.shape[1]):
            col = per[:, f]
            verdict[f"d{f}"] = ("converges" if (col >= 0.99).all()
                                else "partly" if (col > 0.10).any() else "does not converge")  # fmt: skip
        g = np.load(run / a / f"cycle-{NCYCLE}" / "gains.npz")["gains"]
        rec["convergence"][a] = {
            "perdir_converged": per.tolist(), "verdict": verdict,
            "iterations": [c["iterations"] for c in cyc], "fraction": [c["fraction"] for c in cyc],
            "final_phase_std_rad": [float(np.std(np.angle(g[..., f, :]))) for f in range(g.shape[3])],
        }  # fmt: skip
    for a in ("Rc", "Rq"):
        if a in m and "DI0c" in m:
            r = {
                k: m[a]["offaxis_rms"][k] / m["DI0c"]["offaxis_rms"][k]
                for k in m[a]["offaxis_rms"]
            }
            q = float(np.median(list(r.values())))
            dr_ok = m[a]["dynamic_range"] >= m["DI0c"]["dynamic_range"]
            v = (
                "DD helps"
                if (q <= 0.90 and dr_ok)
                else ("DD worse" if q >= 1.05 else "null")
            )
            rec[f"{a}_vs_DI0c"] = {"rms_ratio": r, "q0": q, "verdict": v,
                                   "dr_ratio": m[a]["dynamic_range"] / m["DI0c"]["dynamic_range"]}  # fmt: skip
    (run / "scorec-convergence.json").write_text(
        json.dumps(rec, indent=1), encoding="utf-8"
    )
    print(json.dumps(rec, indent=1))


def flux_close(a, b):
    """Gate L's component-flux tolerance (section 5)."""
    return abs(a - b) <= 1e-5 + 1e-4 * abs(b)


def up_to_rule(cr, co, stop, rel=1e-4):
    """Whether two component lists {(y, x): flux} differ only through a tie
    or a near-threshold choice of the shared rule (DD3 section 4: two
    components within `rel` of each other, or a component within `rel` of
    the stop level). Lists that do not differ are not this case."""
    only_r = {a: cr[a] for a in set(cr) - set(co)}
    only_o = {a: co[a] for a in set(co) - set(cr)}
    both = [a for a in set(cr) & set(co) if not flux_close(cr[a], co[a])]
    if not (only_r or only_o or both):
        return False
    level = dd3.GAIN * stop

    def near(f):
        return abs(abs(f) - level) <= rel * level

    def tie(f, others):
        return any(abs(f - g) <= rel * abs(g) for g in others)

    ok_r = all(near(f) or tie(f, only_o.values()) for f in only_r.values())
    ok_o = all(near(f) or tie(f, only_r.values()) for f in only_o.values())
    ok_b = all(near(cr[a]) or near(co[a]) for a in both)
    return bool(ok_r and ok_o and ok_b)


def score(run, r="R", o="O", di="DI", out="score.json", ctx=None):
    """Gates L and S (R against O) and the gain over DI, as frozen in
    section 5; DD4c reuses them with its own arm names."""
    ctx = context(run) if ctx is None else ctx
    psf = np.load(run / "psf.npy")
    sigma = restoring_beam(psf)
    rec = {"note": "research/dd4-eso137.md", "restoring_sigma_px": sigma, "L": {}}
    # Gate L, per cycle (R against O), DD3's tolerances.
    first_fail = None
    nant = len(ctx["c"]["ant_names"])
    p, q = np.triu_indices(nant, 1)
    for k in range(NCYCLE + 1):
        dr, do = run / r / f"cycle-{k}", run / o / f"cycle-{k}"
        cr, co = dd3.comps_of(dr), dd3.comps_of(do)
        same = set(cr) == set(co)
        flux_ok = same and all(flux_close(cr[a], co[a]) for a in cr)
        gr, go = np.load(dr / "gains.npz"), np.load(do / "gains.npz")
        pr = gr["gains"][:, :, p] * np.conj(gr["gains"][:, :, q])
        po = go["gains"][:, :, p] * np.conj(go["gains"][:, :, q])
        ok_flags = (gr["flags"][:, :, p] == 0) & (gr["flags"][:, :, q] == 0)
        gdiff = float(
            np.abs(pr - po)[np.broadcast_to(ok_flags[..., None], pr.shape)].max()
        )
        flags_eq = bool(np.array_equal(gr["flags"], go["flags"]))
        rr, ro = np.load(dr / "residual.npy"), np.load(do / "residual.npy")
        rdiff = float(np.abs(rr - ro)[ctx["interior"]].max() / np.abs(ro).max())
        ok = same and flux_ok and gdiff <= 1e-5 and flags_eq and rdiff <= 1e-3
        if not ok and first_fail is None:
            first_fail = k
        rule = False
        if not ok and first_fail == k:
            # Parity up to the rule only when the components alone differ,
            # through a tie or a near-threshold choice (section 5, frozen).
            stop = (
                json.loads((dr / "info.json").read_text()).get("hogbom", {}).get("stop")
            )
            rule = bool(gdiff <= 1e-5 and flags_eq and rdiff <= 1e-3 and stop is not None
                        and up_to_rule(cr, co, stop))  # fmt: skip
            rec["L_parity_up_to_rule"] = rule
        rec["L"][k] = {"components": [len(cr), len(co)], "same_pixels": same, "flux_ok": flux_ok,
                       "gain_product_max_abs_diff": gdiff, "flags_equal": flags_eq,
                       "residual_rel_diff": rdiff, "pass": bool(ok)}  # fmt: skip
    rec["L_first_fail"] = first_fail
    arms = [
        a
        for a in dict.fromkeys((r, o, di, "DI0"))
        if (run / a / f"cycle-{NCYCLE}").exists()
    ]
    m = {arm: measures(run, ctx, arm, psf, sigma) for arm in arms}
    rec["measures"] = m
    ratio_ro = {
        k: m[r]["offaxis_rms"][k] / m[o]["offaxis_rms"][k] for k in m[r]["offaxis_rms"]
    }
    dr_ro = m[r]["dynamic_range"] / m[o]["dynamic_range"]
    # 2 % only with parity up to the rule; any other L failure keeps 0.1 %.
    tol = 0.02 if rec.get("L_parity_up_to_rule") else 0.001
    rec["S"] = {"rms_ratio_R_over_O": ratio_ro, "dr_ratio_R_over_O": dr_ro, "tolerance": tol,
                "pass": bool(all(abs(v - 1) <= tol for v in ratio_ro.values()) and abs(dr_ro - 1) <= tol)}  # fmt: skip
    ratio_di = {
        k: m[r]["offaxis_rms"][k] / m[di]["offaxis_rms"][k] for k in m[r]["offaxis_rms"]
    }
    qv = float(np.median(list(ratio_di.values())))
    dr_ok = m[r]["dynamic_range"] >= m[di]["dynamic_range"]
    verdict = (
        "DD helps" if (qv <= 0.90 and dr_ok) else ("DD worse" if qv >= 1.05 else "null")
    )
    rec["gain_over_DI"] = {"rms_ratio_R_over_DI": ratio_di, "q": qv, "dr_R_ge_DI": bool(dr_ok),
                           "verdict": verdict}  # fmt: skip
    if "DI0" in m and di != "DI0":  # amendment A3, post hoc, reported only
        r0 = {
            k: m[r]["offaxis_rms"][k] / m["DI0"]["offaxis_rms"][k]
            for k in m[r]["offaxis_rms"]
        }
        rec["reported_vs_DI0"] = {"rms_ratio_R_over_DI0": r0, "q": float(np.median(list(r0.values()))),
                                  "dr_R_over_DI0": m[r]["dynamic_range"] / m["DI0"]["dynamic_range"]}  # fmt: skip
    (run / out).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(json.dumps(rec, indent=1))


def control_c0(run, scratch):
    """Amendment A1's control: rang's dirty image of the subset against
    WSClean's (no facets), within 1e-3 of the peak over interior pixels."""
    from rang import core_wgridder

    ctx = context(run, di=True)
    c = ctx["c"]
    out = run / "C0"
    run_wsl("step4_c0.sh", dd3.to_wsl(ctx["st"]["subms"]), scratch, dd3.to_wsl(out))
    vis = 0.5 * (c["DATA"][..., 0].astype(complex) + c["DATA"][..., 3])
    mine = core_wgridder.fits_image(c["UVW"], c["freq"], vis, c["w_I"], NX, NY,
                                    dd2.SCALE_ARCSEC, epsilon=EPS)["dirty"]  # fmt: skip
    theirs = dd2.read_fits(out / "c0-dirty.fits")
    d = np.abs(mine - theirs)[ctx["interior"]].max() / np.abs(theirs).max()
    rec = {
        "rel_diff": float(d),
        "peak": float(np.abs(theirs).max()),
        "pass": bool(d <= 1e-3),
    }
    (out / "c0.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec))


def control_c1(run, scratch):
    """Amendment A4's controls on the four-correlation copy: C0' (WSClean's
    dirty image, no facets) and C1 (its flat-gain facet image of DATA with
    arm O's cycle-0 gains) against rang, each within 1e-3 of the peak over
    interior pixels; c1d, the same facet image with -diagonal-visibilities
    on the two-correlation MS, is reported for contrast (A3)."""
    from rang import core_wgridder

    ctx = context(run)
    c = ctx["c"]
    out = run / "C1"
    d0 = run / "O" / "cycle-0"
    run_wsl("step4_c1.sh", dd3.to_wsl(ctx["st"]["subms"]), scratch, dd3.to_wsl(out),
            dd3.to_wsl(d0 / "solved.h5"), dd3.to_wsl(run / "facets.reg"))  # fmt: skip
    vis = 0.5 * (c["DATA"][..., 0].astype(complex) + c["DATA"][..., 3])
    mine0 = core_wgridder.fits_image(c["UVW"], c["freq"], vis, c["w_I"], NX, NY,
                                     dd2.SCALE_ARCSEC, epsilon=EPS)["dirty"]  # fmt: skip
    g = np.load(d0 / "gains.npz")
    gains = np.array(g["gains"], complex)
    gains[np.broadcast_to(g["flags"][..., None] != 0, gains.shape)] = 1.0  # as write_h5
    mine1 = facet_image(ctx, c["DATA"].astype(np.complex128), gains)
    interior = ctx["interior"]
    rec = {}
    for key, mine, fits in (("C0p", mine0, "c0p-dirty.fits"), ("C1", mine1, "c1-image-pb.fits"),
                            ("C1_diagonal", mine1, "c1d-image-pb.fits")):  # fmt: skip
        theirs = dd2.read_fits(out / fits)
        d = np.abs(mine - theirs)[interior].max() / np.abs(theirs).max()
        scale = []
        for f in range(ctx["ndir"]):
            sel = interior & (ctx["idx"] == f)
            scale.append(
                float((theirs[sel] * mine[sel]).sum() / (mine[sel] ** 2).sum())
            )
        rec[key] = {"rel_diff": float(d), "peak": float(np.abs(theirs).max()),
                    "scale_theirs_over_mine_per_facet": scale, "pass": bool(d <= 1e-3)}  # fmt: skip
    (out / "c1.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


def facet_image_wsclean37(ctx, gains):
    """WSClean 3.7's flat-gain facet image (-image-pb) with facet solutions on
    a four-correlation MS, as its source does it (DD4 amendment A5): each hand
    gridded with its own weight, the correction sum weighted by w_XX only:
    sum(w_X V_X' + w_Y V_Y') / (2 sum w_X S), S the Stokes I Mueller term."""
    from rang import core_wgridder

    c, block, ndir = ctx["c"], ctx["block"], ctx["ndir"]
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    flag = c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]
    w = c["WEIGHT_SPECTRUM"].astype(np.float64)
    wx = np.where(flag[..., 0], 0.0, w[..., 0])
    wy = np.where(flag[..., 3], 0.0, w[..., 3])
    ww = wx + wy
    image = np.zeros((NY, NX))
    for f in range(ndir):
        gp, gq = gains[block, 0, a1, f], gains[block, 0, a2, f]
        num = (wx * np.conj(gp[:, None, 0]) * c["DATA"][..., 0] * gq[:, None, 0]
               + wy * np.conj(gp[:, None, 1]) * c["DATA"][..., 3] * gq[:, None, 1])  # fmt: skip
        vis = np.where(ww > 0, num / np.where(ww > 0, ww, 1.0), 0.0)
        img = core_wgridder.fits_image(c["UVW"], c["freq"], vis, ww, NX, NY, dd2.SCALE_ARCSEC,
                                       epsilon=EPS)["dirty"]  # fmt: skip
        s_i = 0.5 * (np.abs(gp[:, 0]) ** 2 * np.abs(gq[:, 0]) ** 2
                     + np.abs(gp[:, 1]) ** 2 * np.abs(gq[:, 1]) ** 2)  # fmt: skip
        scale = ww.sum() / (2.0 * (wx * s_i[:, None]).sum())
        sel = ctx["idx"] == f
        image[sel] = img[sel] * scale
    return image


def control_c2(run, scratch):
    """Amendment A5's controls: WSClean's facet image with arm O's cycle-0
    gains on the matched copy (C2m) and on the equal-weight unflagged copy
    (C2e) against rang; and rang's emulation of WSClean 3.7's facet weighting
    against A4's C1 image (E1). Each within 1e-3 of the peak."""
    ctx = context(run)
    c = ctx["c"]
    out = run / "C2"
    d0 = run / "O" / "cycle-0"
    if not (out / "c2e-image-pb.fits").exists():
        run_wsl("step4_c2.sh", dd3.to_wsl(ctx["st"]["subms"]), scratch, dd3.to_wsl(out),
                dd3.to_wsl(d0 / "solved.h5"), dd3.to_wsl(run / "facets.reg"))  # fmt: skip
    g = np.load(d0 / "gains.npz")
    gains = np.array(g["gains"], complex)
    gains[np.broadcast_to(g["flags"][..., None] != 0, gains.shape)] = 1.0  # as write_h5
    images = {"C2m": (facet_image(ctx, c["DATA"].astype(np.complex128), gains), out / "c2m-image-pb.fits"),
              "E1": (facet_image_wsclean37(ctx, gains), run / "C1" / "c1-image-pb.fits")}  # fmt: skip
    flag = c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]
    w_i = c["w_I"]
    c["w_I"] = np.ones(w_i.shape)
    images["C2e"] = (facet_image(ctx, np.where(flag, 0, c["DATA"]).astype(np.complex128), gains),
                     out / "c2e-image-pb.fits")  # fmt: skip
    c["w_I"] = w_i
    rec = {}
    for key, (mine, fits) in images.items():
        theirs = dd2.read_fits(fits)
        d = np.abs(mine - theirs)[ctx["interior"]].max() / np.abs(theirs).max()
        scale = []
        for f in range(ctx["ndir"]):
            sel = ctx["interior"] & (ctx["idx"] == f)
            scale.append(
                float((theirs[sel] * mine[sel]).sum() / (mine[sel] ** 2).sum())
            )
        rec[key] = {"rel_diff": float(d), "scale_theirs_over_mine_per_facet": scale,
                    "pass": bool(d <= 1e-3)}  # fmt: skip
    (out / "c2.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0]
    if cmd == "setup":
        setup(Path(argv[1]), Path(argv[2]), Path(argv[3]))
    elif cmd == "rang":
        opt = {
            k: argv[argv.index(k) + 1]
            for k in ("--cap", "--name", "--model0")
            if k in argv
        }
        arm_r(Path(argv[1]), di="--di" in argv, di0="--di0" in argv,
              cap=int(opt["--cap"]) if "--cap" in opt else None, name=opt.get("--name"),
              model0=opt.get("--model0"), calmode="p" if "--phase" in argv else "ap",
              own_gain="--own-gain" in argv, perdir="--perdir" in argv)  # fmt: skip
    elif cmd == "oracle":
        opt = {
            k: argv[argv.index(k) + 1]
            for k in ("--cap", "--name", "--model0")
            if k in argv
        }
        arm_o(Path(argv[1]), argv[2], gtype="phase" if "--phase" in argv else "diag_complex",
              cap=int(opt.get("--cap", 150)), name=opt.get("--name", "O"),
              model0=opt.get("--model0"))  # fmt: skip
    elif cmd == "control":
        control_c0(Path(argv[1]), argv[2])
    elif cmd == "control1":
        control_c1(Path(argv[1]), argv[2])
    elif cmd == "control2":
        control_c2(Path(argv[1]), argv[2])
    elif cmd == "scorec":
        score_c(Path(argv[1]))
    elif cmd == "scoreb":
        score_b(Path(argv[1]))
    elif cmd == "score":
        opt = {
            k[2:]: argv[argv.index(k) + 1]
            for k in ("--r", "--o", "--di", "--out")
            if k in argv
        }
        score(Path(argv[1]), **opt)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
