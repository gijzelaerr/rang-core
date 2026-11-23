# SPDX-License-Identifier: MIT
"""DD3: the direction-dependent self-calibration loop (research/dd3-selfcal-loop.md).

    python tools/oracles/dd3/dd3.py setup SIMDIR RUN        # PSF, facets, start model
    python tools/oracles/dd3/dd3.py rang RUN                # arm R, all cycles
    python tools/oracles/dd3/dd3.py oracle RUN SCRATCH      # arm O (WSL QuartiCal, WSClean)
    python tools/oracles/dd3/dd3.py compare RUN             # gates L and T

Each arm writes RUN/<arm>/cycle-<k>/{model.npy, gains.npz, residual.npy,
components.npz} for k = 0..4 (cycle 4: the final solve and residual, no
minor cycle). Arm O's WSL steps are `step_o1.sh` (model columns and
QuartiCal) and `step_o2.sh` (corrupted predict, residual column, image).
"""

import importlib.util
import json
import subprocess
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


dd2 = _load("dd2", HERE.parent / "dd2" / "dd2.py")
NX, NY, DELTA, EPS, CAP = dd2.NX, dd2.NY, dd2.DELTA, dd2.EPS, dd2.CAP
NDIR = 4
NCYCLE = 4
GAIN = 0.1
MAX_COMPONENTS = 5000
SIGMAS = 5.0
FLOOR = 1e-3
EDGE = dd2.EDGE_PX
REF_T1 = 3.10e-3  # DD2 prepare.json P1_under_cap_truth median (section 3)


# -- shared pieces ------------------------------------------------------------------


def setup(sim, run):
    from rang import core_grid, core_wgridder

    run.mkdir(parents=True, exist_ok=False)
    c = dd2.read_ms(Path(sim) / "dd1.ms")
    truth = dict(np.load(Path(sim) / "truth.npz"))
    centres = dd2.centres_lm(truth)
    (run / "facets.reg").write_text(
        dd2.region_text(dd2.voronoi_polygons(centres), centres, c["phase_dir"]),
        encoding="utf-8",
    )
    w = c["WEIGHT_SPECTRUM"][..., 0].astype(np.float64)
    # The unit-gain PSF on a grid twice the image, centre at (NY, NX).
    psf = core_wgridder.fits_image(
        c["UVW"], c["freq"], np.ones(w.shape, complex), w, 2 * NX, 2 * NY,
        dd2.SCALE_ARCSEC, epsilon=EPS,
    )["psf"]  # fmt: skip
    np.save(run / "psf.npy", psf.astype(np.float64))
    lm, flux = truth["lm"], truth["flux"]
    x = np.rint(NX / 2 - lm[:, 0] / DELTA).astype(int)
    y = np.rint(NY / 2 + lm[:, 1] / DELTA).astype(int)
    m0 = np.zeros((NY, NX))
    for k in range(NDIR):  # the four facet-centre sources are components 0-3
        m0[y[k], x[k]] += flux[k]
    np.save(run / "model0.npy", m0)
    np.savez(run / "truth_pixels.npz", x=x, y=y, flux=flux)
    hdr = core_grid.wcs_header(c["phase_dir"], NX, NY, dd2.SCALE_ARCSEC, c["freq"])
    hdr["BUNIT"] = "JY/PIXEL"
    (run / "header.json").write_text(json.dumps(hdr))
    (run / "sim.json").write_text(json.dumps({"sim": str(Path(sim))}))


def context(run):
    sim = Path(json.loads((run / "sim.json").read_text())["sim"])
    c = dd2.read_ms(sim / "dd1.ms")
    truth = dict(np.load(sim / "truth.npz"))
    centres = dd2.centres_lm(truth)
    idx, margin = dd2.facet_masks(centres)
    _, _, block, centres_t = dd2.interval_axes(c)
    xg, yg = np.meshgrid(np.arange(NX), np.arange(NY))
    interior = (margin >= EDGE) & (xg >= EDGE) & (xg < NX - EDGE) & (
        yg >= EDGE) & (yg < NY - EDGE)  # fmt: skip
    return {
        "sim": sim, "c": c, "truth": truth, "centres": centres, "idx": idx,
        "interior": interior, "block": block, "centres_t": centres_t,
    }  # fmt: skip


def hogbom(residual, psf, interior):
    """The shared minor cycle (section 2, step 4): components {(y, x): flux}
    and the residual after them."""
    res = np.array(residual, np.float64)
    sigma = 1.4826 * float(np.median(np.abs(res[interior] - np.median(res[interior]))))
    stop = max(SIGMAS * sigma, FLOOR)
    comps = {}
    keep = np.asarray(interior, bool)
    for _ in range(MAX_COMPONENTS):
        k = int(np.argmax(np.where(keep, np.abs(res), 0.0)))
        y, x = divmod(k, NX)
        peak = res[y, x]
        if abs(peak) < stop:
            break
        f = GAIN * peak
        comps[(y, x)] = comps.get((y, x), 0.0) + f
        res -= f * psf[NY - y : 2 * NY - y, NX - x : 2 * NX - x]
    return comps, res, {"sigma": sigma, "stop": stop, "n": len(comps)}


def add_components(model, comps):
    out = model.copy()
    for (y, x), f in comps.items():
        out[y, x] += f
    return out


def save_cycle(d, model, gains, flags, residual, comps, info):
    d.mkdir(parents=True, exist_ok=True)
    np.save(d / "model.npy", model)
    np.savez(d / "gains.npz", gains=gains, flags=flags)
    np.save(d / "residual.npy", residual.astype(np.float32))
    if comps is not None:
        keys = sorted(comps)
        np.savez(
            d / "components.npz",
            y=np.array([k[0] for k in keys], int),
            x=np.array([k[1] for k in keys], int),
            flux=np.array([comps[k] for k in keys]),
        )
    (d / "info.json").write_text(json.dumps(info, indent=1))


# -- arm R ------------------------------------------------------------------------------


def facet_models(c, model, idx):
    from rang import core_wgridder

    out = np.zeros(c["DATA"].shape[:2] + (NDIR, 4), np.complex64)
    for f in range(NDIR):
        v = core_wgridder.dirty2vis(
            uvw=c["UVW"], freq=c["freq"],
            dirty=np.ascontiguousarray(np.where(idx == f, model, 0.0).T),
            pixsize_x=DELTA, pixsize_y=DELTA, epsilon=EPS, flip_v=True, flip_w=True,
        )  # fmt: skip
        out[:, :, f, 0] = v
        out[:, :, f, 3] = v
    return out


def corrupt(c, models, gains, block):
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    out = np.zeros(c["DATA"].shape, complex)
    for f in range(NDIR):
        gp, gq = gains[block, 0, a1, f], gains[block, 0, a2, f]
        out[..., 0] += gp[:, None, 0] * models[:, :, f, 0] * np.conj(gq[:, None, 0])
        out[..., 3] += gp[:, None, 1] * models[:, :, f, 3] * np.conj(gq[:, None, 1])
    return out


def flat_gain_image(c, data, gains, block, idx):
    from rang import core_wgridder

    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    w = c["WEIGHT_SPECTRUM"][..., 0].astype(np.float64)
    image = np.zeros((NY, NX))
    for f in range(NDIR):
        gp, gq = gains[block, 0, a1, f], gains[block, 0, a2, f]
        xx = np.conj(gp[:, None, 0]) * data[..., 0] * gq[:, None, 0]
        yy = np.conj(gp[:, None, 1]) * data[..., 3] * gq[:, None, 1]
        img = core_wgridder.fits_image(
            c["UVW"],
            c["freq"],
            0.5 * (xx + yy),
            w,
            NX,
            NY,
            dd2.SCALE_ARCSEC,
            epsilon=EPS,
        )["dirty"]
        cf = dd2.correction(gp, gq, w, "a")
        sel = idx == f
        image[sel] = img[sel] / cf
    return image


def arm_r(run):
    from rang import cal_gain

    ctx = context(run)
    c, idx, block = ctx["c"], ctx["idx"], ctx["block"]
    psf = np.load(run / "psf.npy")
    model = np.load(run / "model0.npy")
    nant = len(c["ant_names"])
    data = c["DATA"].astype(np.complex128)
    for k in range(NCYCLE + 1):
        t0 = time.perf_counter()
        models = facet_models(c, model, idx)
        sol = cal_gain.solve_dd(
            c["DATA"], models, c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"],
            c["ANTENNA1"], c["ANTENNA2"], block, nant=nant, refant=0, **CAP,
        )  # fmt: skip
        t1 = time.perf_counter()
        residual = flat_gain_image(c, data - corrupt(c, models, sol.gains, block), sol.gains,
                                   block, idx)  # fmt: skip
        t2 = time.perf_counter()
        info = {"iterations": sol.iterations, "fraction": sol.converged_fraction,
                "seconds_solve": t1 - t0, "seconds_image": t2 - t1}  # fmt: skip
        comps = None
        new_model = model
        if k < NCYCLE:
            comps, _, hinfo = hogbom(residual, psf, ctx["interior"])
            info["hogbom"] = hinfo
            new_model = add_components(model, comps)
        save_cycle(
            run / "R" / f"cycle-{k}", model, sol.gains, sol.flags, residual, comps, info
        )
        print(f"R cycle {k}: {json.dumps(info)}", flush=True)
        model = new_model


# -- arm O ------------------------------------------------------------------------------


def wsl(script, *args):
    cmd = ["wsl", "-d", "Ubuntu", "--", "bash", to_wsl(HERE / script), *map(str, args)]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"{script} failed: {r.stdout[-2000:]} {r.stderr[-2000:]}")
    return r.stdout


def to_wsl(p):
    p = str(Path(p).resolve()).replace("\\", "/")
    return f"/mnt/{p[0].lower()}{p[2:]}"


def write_fits(path, image, hdr):
    from rang import core_grid

    if path.exists():
        path.unlink()
    core_grid.write_fits(path, image, hdr)


def qc_gains(store):
    from rang.formats import quartical_store as qs

    parts = qs.read_term(store, "G")
    v = parts[0].variables
    g = np.asarray(v["gains"].data)
    if g.shape[-1] == 4:
        g = g[..., [0, 3]]
    return (
        g,
        np.asarray(v["gain_flags"].data),
        {
            "iterations": int(np.asarray(v["conv_iter"].data).ravel()[0]),
            "fraction": float(np.asarray(v["conv_perc"].data).ravel()[0]),
        },
    )


def arm_o(run, scratch):
    from rang.formats import h5parm  # noqa: F401  (needs h5py)

    ctx = context(run)
    c, idx = ctx["c"], ctx["idx"]
    psf = np.load(run / "psf.npy")
    hdr = json.loads((run / "header.json").read_text())
    model = np.load(run / "model0.npy")
    o = run / "O"
    o.mkdir(exist_ok=True)
    wsl("step_o0.sh", to_wsl(ctx["sim"]), scratch)
    for k in range(NCYCLE + 1):
        d = o / f"cycle-{k}"
        d.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        for f in range(NDIR):
            write_fits(d / f"facet{f}-model.fits", np.where(idx == f, model, 0.0), hdr)
        write_fits(d / "full-model.fits", model, hdr)
        write_fits(d / "full-model-pb.fits", model, hdr)
        log1 = wsl("step_o1.sh", scratch, to_wsl(d))
        gains, flags, qinfo = qc_gains(d / "gains")
        ok = dd2.write_h5(
            d / "solved.h5", gains, flags, c, ctx["centres_t"], ctx["centres"]
        )
        t1 = time.perf_counter()
        log2 = wsl("step_o2.sh", scratch, to_wsl(d), to_wsl(run / "facets.reg"))
        residual = dd2.read_fits(d / "resid-image-pb.fits")
        t2 = time.perf_counter()
        info = {**qinfo, "h5_roundtrip": ok, "seconds_solve": t1 - t0, "seconds_image": t2 - t1,
                "log_tail": (log1 + log2)[-400:]}  # fmt: skip
        comps = None
        new_model = model
        if k < NCYCLE:
            comps, _, hinfo = hogbom(residual, psf, ctx["interior"])
            info["hogbom"] = hinfo
            new_model = add_components(model, comps)
        save_cycle(d, model, gains, flags, residual, comps, info)
        print(f"O cycle {k}: {json.dumps({x: y for x, y in info.items() if x != 'log_tail'})}",
              flush=True)  # fmt: skip
        model = new_model


# -- comparison -------------------------------------------------------------------------


def comps_of(d):
    p = d / "components.npz"
    if not p.exists():
        return {}
    z = np.load(p)
    return {
        (int(y), int(x)): float(f)
        for y, x, f in zip(z["y"], z["x"], z["flux"], strict=True)
    }


def truth_scores(run, ctx, d):
    tp = np.load(run / "truth_pixels.npz")
    x, y, flux = tp["x"], tp["y"], tp["flux"]
    model = np.load(d / "model.npy")
    g = np.load(d / "gains.npz")
    dd1 = dd2._dd1()
    t1 = dd1.truth_stat(
        {"gains": g["gains"], "flags": g["flags"]},
        ctx["truth"],
        "P1",
        len(ctx["c"]["ant_names"]),
    )
    yy, xx = np.indices(model.shape)
    near = np.zeros(model.shape, bool)
    ratios = []
    for k in range(len(flux)):
        box = (np.abs(yy - y[k]) <= 2) & (np.abs(xx - x[k]) <= 2)
        near |= box
        ratios.append(float(model[box].sum() / flux[k]))
    ratios = np.array(ratios)
    bright = ratios[:NDIR]
    faint = ratios[NDIR:][flux[NDIR:] >= 0.03]
    false = float(np.abs(model[~near]).sum() / flux.sum())
    return {
        "T1_median": t1["median"], "T1_per_direction": t1["per_direction"],
        "T1_pass": bool(t1["median"] <= 1.2 * REF_T1),
        "T2_bright_ratios": bright.tolist(), "T2_faint_ratios": faint.tolist(),
        "T2_pass": bool(np.all(np.abs(bright - 1) <= 0.02) and np.all(np.abs(faint - 1) <= 0.10)),
        "T3_false_fraction": false, "T3_pass": bool(false <= 0.01),
    }  # fmt: skip


def compare(run):
    ctx = context(run)
    rec = {"note": "research/dd3-selfcal-loop.md", "cycles": {}}
    p, q = np.triu_indices(len(ctx["c"]["ant_names"]), 1)
    first_fail = None
    for k in range(NCYCLE + 1):
        dr, do = run / "R" / f"cycle-{k}", run / "O" / f"cycle-{k}"
        cr, co = comps_of(dr), comps_of(do)
        same_pix = set(cr) == set(co)
        flux_ok = same_pix and all(
            abs(cr[key] - co[key]) <= 1e-5 + 1e-4 * abs(co[key]) for key in cr
        )
        gr, go = np.load(dr / "gains.npz"), np.load(do / "gains.npz")
        pr = gr["gains"][:, :, p] * np.conj(gr["gains"][:, :, q])
        po = go["gains"][:, :, p] * np.conj(go["gains"][:, :, q])
        gdiff = float(np.abs(pr - po).max())
        flags_eq = bool(np.array_equal(gr["flags"], go["flags"]))
        rr, ro = np.load(dr / "residual.npy"), np.load(do / "residual.npy")
        sel = ctx["interior"]
        rdiff = float(np.abs(rr - ro)[sel].max() / np.abs(ro).max())
        ok = same_pix and flux_ok and gdiff <= 1e-5 and flags_eq and rdiff <= 1e-3
        if not ok and first_fail is None:
            first_fail = k
        rec["cycles"][k] = {
            "components": [len(cr), len(co)], "same_pixels": same_pix, "flux_ok": flux_ok,
            "only_R": sorted(map(list, set(cr) - set(co)))[:5],
            "only_O": sorted(map(list, set(co) - set(cr)))[:5],
            "gain_product_max_abs_diff": gdiff, "flags_equal": flags_eq,
            "residual_rel_diff": rdiff, "L_pass": bool(ok),
        }  # fmt: skip
    rec["L_first_fail"] = first_fail
    final = NCYCLE
    rec["T"] = {
        arm: truth_scores(run, ctx, run / arm / f"cycle-{final}") for arm in ("R", "O")
    }
    rec["T_start_model"] = {
        arm: truth_scores(run, ctx, run / arm / "cycle-0") for arm in ("R", "O")
    }
    (run / "compare.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(json.dumps(rec, indent=1))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0]
    if cmd == "setup":
        setup(Path(argv[1]), Path(argv[2]))
    elif cmd == "rang":
        arm_r(Path(argv[1]))
    elif cmd == "oracle":
        arm_o(Path(argv[1]), argv[2])
    elif cmd == "compare":
        compare(Path(argv[1]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
