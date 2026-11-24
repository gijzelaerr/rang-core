# SPDX-License-Identifier: MIT
"""DD5: ESO 137-006's DD setup simulated factor by factor (research/dd5-sim.md).

    python tools/oracles/dd5/dd5.py noise OUT.json            # section 2's k
    python tools/oracles/dd5/dd5.py sim SKY OUTDIR [--nonoise] [--d0err]
    python tools/oracles/dd5/dd5.py grid RUN KIND TI MODEL OUT.json
    python tools/oracles/dd5/dd5.py looptruth RUN ARM          # stage 5, e_d per cycle
    python tools/oracles/dd5/dd5.py score RUN R O OUT.json     # stage 5, gates L and S

SKY is a (S_a, catalogue), b (S_b, M0c), p (S_p, S_b with the d2 and d3
pins halved), e (S_e, DI0c's cycle-4 model; amendment A1), or e0 / e1
(S_e in facet d0 / d1 only, M0c elsewhere; amendment A2). Each OUTDIR is a DD4 run directory (setup.json, psf.npy,
header.json, facets.reg, model0.npy) whose subset MS is the simulated copy,
so `tools/oracles/dd4/dd4.py rang|oracle` run on it unchanged.
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
REAL_RUN = Path("D:/rang/outputs/dd4-20261123/run-02")
M0C = REAL_RUN / "DI0" / "cycle-4" / "model.npy"
M0C_SHA = "619891d38b8d7508d6c3d95ee8fb2dfc6ec9ba9eb6d589379bd5ea1e30f4914a"
SEEDS = {"gains": 1502, "noise": 5501, "d0": 5504}  # section 2 and 3
GAIN_SCALE = (0.1, 0.5)  # DD1's AMP_SCALE, PHASE_SCALE
D0_SCALE = (0.01, 0.02)  # arm D
PIN_SCALE = 0.5  # S_p: d2 and d3 pins
BLOCK = 4  # truth gains are constant on 4 integrations


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd4 = _load("dd4", HERE.parent / "dd4" / "dd4.py")
dd2 = dd4.dd2


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def truth_gains(nant, ndir, nblock, seed, amp_scale, phase_scale):
    """DD1's `truth_gains` (tools/oracles/dd1/sim.py) with its seed and
    scales as arguments: (nblock, nant, ndir, 2) complex."""
    rng = np.random.default_rng(seed)
    t = (np.arange(nblock) + 0.5) / nblock
    shape = (nant, ndir, 2)

    def smooth():
        offset = rng.normal(0, 1, shape)
        amp = rng.uniform(0.2, 1.0, shape)
        period = rng.uniform(0.5, 2.0, shape)
        phase = rng.uniform(0, 2 * math.pi, shape)
        return offset[None] + amp[None] * np.sin(
            2 * math.pi * t[:, None, None, None] / period[None] + phase[None]
        )

    a, b = smooth(), smooth()
    return np.exp(amp_scale * a + 1j * phase_scale * b)


def sky(name):
    st = json.loads((REAL_RUN / "setup.json").read_text())
    if name == "a":
        return np.load(REAL_RUN / "model0.npy")
    m = np.load(M0C)
    if name == "b":
        return m
    if name == "e":  # amendment A1: DI0c's cycle-4 model as the sky
        return np.load(REAL_RUN / "DI0c" / "cycle-4" / "model.npy")
    if name in ("e0", "e1"):  # amendment A2: S_e in one facet only, M0c elsewhere
        e = np.load(REAL_RUN / "DI0c" / "cycle-4" / "model.npy")
        l, mm = dd2.pixel_lm()
        idx, _ = dd2.facet_index_and_margin(l, mm, np.array(st["centres"]))
        sel = idx == int(name[1])
        m = m.copy()
        m[sel] = e[sel]
        return m
    if name == "p":
        m = m.copy()
        for y, x in st["pins"][1:]:  # d2, d3
            m[y, x] *= PIN_SCALE
        return m
    raise SystemExit(f"unknown sky {name}")


def noise_scale(out):
    """Section 2: k from adjacent-channel differences of the real residual
    DATA - (unit-gain predict of M0c), against WEIGHT_SPECTRUM."""
    t0 = time.perf_counter()
    assert sha256(M0C) == M0C_SHA
    ctx = dd4.context(REAL_RUN)
    c = ctx["c"]
    models = dd4.facet_models(ctx, np.load(M0C))
    r = c["DATA"].astype(np.complex64) - models.sum(axis=2)
    del models
    flag = c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]
    w = c["WEIGHT_SPECTRUM"].astype(np.float64)
    parts = []
    for h in (0, 3):
        ok = ~flag[:, :-1, h] & ~flag[:, 1:, h] & (w[:, :-1, h] > 0) & (w[:, 1:, h] > 0)
        d = (r[:, :-1, h] - r[:, 1:, h])[ok]
        s = 1.0 / np.sqrt(1.0 / w[:, :-1, h][ok] + 1.0 / w[:, 1:, h][ok])
        parts += [d.real * s, d.imag * s]
    v = np.concatenate(parts)
    k = float((1.4826 * np.median(np.abs(v - np.median(v)))) ** 2)
    # The thermal Stokes I image noise this implies, with rang's w_I weights:
    # Var Re V_I = (k/w_xx + k/w_yy) / 4 per cell.
    wxx = np.where(flag[..., 0], 0, w[..., 0])
    wyy = np.where(flag[..., 3], 0, w[..., 3])
    wi = c["w_I"]
    sel = wi > 0
    var = 0.25 * k * (1 / wxx[sel] + 1 / wyy[sel])
    sigma_img = float(np.sqrt((wi[sel] ** 2 * var).sum()) / wi[sel].sum())
    rec = {"note": "research/dd5-sim.md section 2", "k": k, "n_samples": int(v.size),
           "median_weight": float(np.median(w[..., 0][~flag[..., 0]])),
           "sigma_vis_per_part_at_median_weight_jy": float(math.sqrt(k / np.median(w[..., 0][~flag[..., 0]]))),
           "implied_stokes_i_image_sigma_jy": sigma_img, "m0c_sha256": M0C_SHA,
           "seconds": time.perf_counter() - t0}  # fmt: skip
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


def simulate(name, outdir, nonoise=False, d0err=False, k=None):
    """Section 2: the simulated copy of the subset and its run directory."""
    from rang import core_ms_write

    t0 = time.perf_counter()
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=False)
    st = json.loads((REAL_RUN / "setup.json").read_text())
    ctx = dd4.context(REAL_RUN)
    c = ctx["c"]
    nant, ndir = len(c["ant_names"]), ctx["ndir"]
    block4 = dd2.interval_axes(c, BLOCK)[2]
    nblock = int(block4.max()) + 1
    g = truth_gains(nant, ndir, nblock, SEEDS["gains"], *GAIN_SCALE)
    g[:, :, 0, :] = 1.0
    if d0err:
        g[:, :, 0, :] = truth_gains(nant, 1, nblock, SEEDS["d0"], *D0_SCALE)[:, :, 0, :]
    s = sky(name)
    np.save(outdir / "sky.npy", s)
    models = dd4.facet_models(ctx, s)
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    data = np.zeros(c["DATA"].shape[:2] + (2,), np.complex64)
    for f in range(ndir):
        for h, (hh, corr) in enumerate(((0, 0), (1, 3))):
            gp, gq = g[block4, a1, f, hh], g[block4, a2, f, hh]
            data[..., h] += (
                gp[:, None] * models[:, :, f, corr] * np.conj(gq[:, None])
            ).astype(np.complex64)
    del models
    if not nonoise:
        w = c["WEIGHT_SPECTRUM"][..., [0, 3]].astype(np.float64)
        sd = np.where(w > 0, np.sqrt(k / np.where(w > 0, w, 1.0)), 0.0)
        rng = np.random.default_rng(SEEDS["noise"])
        n = rng.standard_normal(data.shape + (2,))
        data += (sd * (n[..., 0] + 1j * n[..., 1])).astype(np.complex64)
        del n
    ms = outdir / "sim.ms"
    shutil.copytree(st["subms"], ms)
    t = core_ms_write.open_table(str(ms), readonly=False)
    t.putcol("DATA", data)
    t.close()
    del data
    for f in ("psf.npy", "header.json", "facets.reg", "model0.npy"):
        shutil.copy(REAL_RUN / f, outdir / f)
    st2 = dict(st, subms=str(ms), dd5={"sky": name, "nonoise": nonoise, "d0err": d0err,
                                       "k": k, "seeds": SEEDS, "pin_scale": PIN_SCALE})  # fmt: skip
    (outdir / "setup.json").write_text(json.dumps(st2, indent=1))
    np.savez(
        outdir / "truth.npz", gains=g, block=BLOCK, k=k if k is not None else np.nan
    )
    rec = {"sky": name, "sky_flux": float(s.sum()), "sky_sha256": hashlib.sha256(s.tobytes()).hexdigest(),
           "nblock": nblock, "nonoise": nonoise, "d0err": d0err, "k": k,
           "seconds": time.perf_counter() - t0}  # fmt: skip
    (outdir / "sim.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec), flush=True)


def products(g, p, q):
    return g[..., p, :, :] * np.conj(g[..., q, :, :])


def truth_error(run, ctx, gains, flags, ti, phase_only):
    """Section 4's e_d per direction: median |P - Pbar| / |Pbar| over
    unflagged cells, pairs and hands; Pbar the truth product averaged over
    the truth blocks inside each solution interval."""
    tr = np.load(run / "truth.npz")
    gt = tr["gains"]  # (nblock, nant, ndir, 2)
    c = ctx["c"]
    nant = len(c["ant_names"])
    p, q = np.triu_indices(nant, 1)
    block4 = dd2.interval_axes(c, BLOCK)[2]
    block_t = dd2.interval_axes(c, ti)[2]
    nint = int(block_t.max()) + 1
    pt = products(gt, p, q)  # (nblock, npair, ndir, 2)
    pbar = np.zeros((nint,) + pt.shape[1:], complex)
    for j in range(nint):
        blocks = np.unique(block4[block_t == j])
        pbar[j] = pt[blocks].mean(axis=0)
    ps = products(gains[:, 0], p, q)  # (nint, npair, ndir, 2)
    if phase_only:
        ps, pbar = ps / np.abs(ps), pbar / np.abs(pbar)
    rel = np.abs(ps - pbar) / np.abs(pbar)
    ok = (flags[:, 0][:, p] == 0) & (flags[:, 0][:, q] == 0)  # (nint, npair, ndir)
    out = []
    for f in range(gt.shape[2]):
        v = rel[:, :, f, :][np.broadcast_to(ok[:, :, f, None], rel[:, :, f, :].shape)]
        out.append(float(np.median(v)) if v.size else float("nan"))
    return out


def predicted_error(ctx, models, k, ti):
    """Section 4's noise prediction e^_d: Var g_p = 1 / sum (w/2k)|V_d|^2 over
    p's unflagged visibilities in the interval; 0.83 x median over pairs of
    sqrt(Var g_p + Var g_q)."""
    c = ctx["c"]
    nant = len(c["ant_names"])
    flag = c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]
    w = c["WEIGHT_SPECTRUM"].astype(np.float64)
    block_t = dd2.interval_axes(c, ti)[2]
    nint = int(block_t.max()) + 1
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    p, q = np.triu_indices(nant, 1)
    out = []
    for f in range(models.shape[2]):
        info = np.zeros((nint, nant, 2))
        for h, corr in enumerate((0, 3)):
            ww = np.where(flag[..., corr], 0.0, w[..., corr])
            row = (ww * np.abs(models[:, :, f, corr]) ** 2).sum(axis=1) / (2 * k)
            for ant in (a1, a2):
                np.add.at(info[:, :, h], (block_t, ant), row)
        var = np.where(info > 0, 1.0 / np.where(info > 0, info, 1.0), np.inf)
        e = np.sqrt(var[:, p, :] + var[:, q, :])
        e = e[np.isfinite(e)]
        out.append(float(0.83 * np.median(e)) if e.size else float("nan"))
    return out


def step_stats(g1, g2, f1, f2):
    """Per direction: median and 90th percentile of |dg|^2/|g|^2 between the
    two solves over cells unflagged in both, and the cells whose flag
    changed (DD5 amendment A1)."""
    d2 = (np.abs(g2 - g1) ** 2).sum(-1)
    n2 = (np.abs(g1) ** 2).sum(-1)
    ok = (f1 == 0) & (f2 == 0) & (n2 > 0)
    rel = d2 / np.where(n2 > 0, n2, 1.0)
    out = []
    for f in range(g1.shape[3]):
        v = rel[..., f][ok[..., f]]
        out.append({"median": float(np.median(v)) if v.size else None,
                    "p90": float(np.percentile(v, 90)) if v.size else None,
                    "flag_changes": int(((f1[..., f] == 0) != (f2[..., f] == 0)).sum())})  # fmt: skip
    return out


def empty_cells(ctx, ti):
    """Per direction-independent cell (interval, antenna): how many have no
    unflagged parallel-hand visibility (DD5 amendment A1)."""
    c = ctx["c"]
    nant = len(c["ant_names"])
    flag = c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]
    good = (~flag[..., 0] | ~flag[..., 3]).sum(axis=1)
    block_t = dd2.interval_axes(c, ti)[2]
    nint = int(block_t.max()) + 1
    n = np.zeros((nint, nant))
    for ant in (c["ANTENNA1"], c["ANTENNA2"]):
        np.add.at(n, (block_t, ant), good)
    return n == 0


def grid_point(run, kind, ti, model, out, cap=500, stop_fraction=None):
    """Section 3: DD4d's grid solve (and the one-longer solve for the
    per-direction measure) on a simulated run, with section 4's measures."""
    from rang import cal_gain

    run = Path(run)
    ctx = dd4.context(run, ti=ti)
    c = ctx["c"]
    t0 = time.perf_counter()
    models = dd4.facet_models(ctx, np.load(model))
    args = (c["DATA"], models, c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"],
            c["ANTENNA1"], c["ANTENNA2"], ctx["block"])  # fmt: skip
    kw = {"nant": len(c["ant_names"]), "refant": None, "pinned_directions": ctx["pinned"],
          "calmode": "p" if kind == "phase" else "ap", "phase_last_direction_gain": False}  # fmt: skip
    caps = dict(dd4.CAP, max_iterations=cap)
    if stop_fraction is not None:
        caps["stop_fraction"] = stop_fraction
    t1 = time.perf_counter()
    sol = cal_gain.solve_dd(*args, **kw, **caps)
    t2 = time.perf_counter()
    sol2 = cal_gain.solve_dd(*args, **kw, **dict(caps, max_iterations=sol.iterations + 1,
                                                  stop_fraction=1.0))  # fmt: skip
    t3 = time.perf_counter()
    per = dd4.per_direction_converged(sol.gains, sol2.gains, sol.flags, sol2.flags)
    steps = step_stats(np.asarray(sol.gains), np.asarray(sol2.gains), np.asarray(sol.flags),
                       np.asarray(sol2.flags))  # fmt: skip
    empty = empty_cells(ctx, ti)
    k = float(json.loads((run / "setup.json").read_text())["dd5"]["k"] or 0.0)
    gains, flags = np.asarray(sol.gains), np.asarray(sol.flags)
    e = truth_error(run, ctx, gains, flags, ti, kind == "phase")
    ehat = (
        predicted_error(ctx, models, k, ti) if k > 0 else [float("nan")] * ctx["ndir"]
    )
    conv = [x >= 0.99 for x in per]
    level = [
        "converges" if x >= 0.99 else "partly" if x > 0.10 else "does not converge"
        for x in per
    ]
    flagged_empty = [
        int(((flags[..., f] != 0) & empty[:, None, :]).sum())
        for f in range(ctx["ndir"])
    ]
    rec = {"run": str(run), "model": str(model), "kind": kind, "ti": ti, "seconds_per_solution": 8 * ti,
           "cap": cap, "stop_fraction": caps["stop_fraction"], "level": level, "step_stats": steps,
           "stopped_before_cap": bool(sol.iterations < cap), "empty_cells": int(empty.sum()),
           "flagged_per_direction": [int((flags[..., f] != 0).sum()) for f in range(ctx["ndir"])],
           "flagged_on_empty_cells": flagged_empty,
           "nint": int(ctx["block"].max()) + 1, "iterations": sol.iterations,
           "iterations_second": sol2.iterations, "fraction": sol.converged_fraction,
           "perdir_converged": per, "converges": bool(all(conv[1:])),
           "e_d": e, "ehat_d": ehat,
           "e_over_ehat": [a / b if b and not math.isnan(b) else float("nan") for a, b in zip(e, ehat, strict=True)],
           "accurate": [bool(conv[f] and e[f] <= 2 * ehat[f]) for f in range(len(e))],
           "flagged_offaxis": int((flags[..., 1:] != 0).sum()),
           "phase_std_rad": [float(np.std(np.angle(gains[..., f, :]))) for f in range(ctx["ndir"])],
           "amp_median": [float(np.median(np.abs(gains[..., f, :]))) for f in range(ctx["ndir"])],
           "seconds_predict": t1 - t0, "seconds_solve": t2 - t1, "seconds_second_solve": t3 - t2}  # fmt: skip
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1))
    np.savez_compressed(out.with_suffix(".npz"), gains=gains, flags=flags)
    print(json.dumps(rec), flush=True)


def loop_truth(run, arm, ti):
    """Stage 5: e_d per cycle of a loop arm against the truth gains."""
    run = Path(run)
    ctx = dd4.context(run, ti=ti)
    rec = {}
    for k in range(dd4.NCYCLE + 1):
        g = np.load(run / arm / f"cycle-{k}" / "gains.npz")
        rec[k] = truth_error(run, ctx, g["gains"], g["flags"], ti, False)
    (run / f"{arm}-truth.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0]
    if cmd == "noise":
        noise_scale(argv[1])
    elif cmd == "sim":
        k = None
        if "--nonoise" not in argv:
            k = json.loads(Path(argv[argv.index("--k") + 1]).read_text())["k"]
        simulate(
            argv[1], argv[2], nonoise="--nonoise" in argv, d0err="--d0err" in argv, k=k
        )
    elif cmd == "grid":
        opt = {
            k: argv[argv.index(k) + 1]
            for k in ("--cap", "--stop-fraction")
            if k in argv
        }
        grid_point(argv[1], argv[2], int(argv[3]), argv[4], argv[5], cap=int(opt.get("--cap", 500)),
                   stop_fraction=float(opt["--stop-fraction"]) if "--stop-fraction" in opt else None)  # fmt: skip
    elif cmd == "looptruth":
        loop_truth(argv[1], argv[2], int(argv[3]))
    elif cmd == "score":
        run = Path(argv[1])
        dd4.score(run, r=argv[2], o=argv[3], di=argv[2], out=argv[4],
                  ctx=dd4.context(run, ti=int(argv[5]) if len(argv) > 5 else 4))  # fmt: skip
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
