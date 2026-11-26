# SPDX-License-Identifier: MIT
"""DD11: a start that keeps the solved gains from absorbing the off-axis
model gap, on O (research/dd11-start.md).

    python tools/oracles/dd11/dd11.py reuse ROOT            # copy DD10's reused files, reuse.json
    python tools/oracles/dd11/dd11.py psf ROOT BASE         # DD10's PSF, peak checked against DD10's
    python tools/oracles/dd11/dd11.py gatef ROOT            # gate F: fast Hogbom against DD3's
    python tools/oracles/dd11/dd11.py diag ROOT             # diagnostic D (zero solves)
    python tools/oracles/dd11/dd11.py loop ROOT ARM         # U6 P6 Q6 L6 AT6 ATm ATs, R-<arm>
    python tools/oracles/dd11/dd11.py score ROOT            # section 6 and 7 readings

DD7's to DD10's roots are read only; reused files are copied into ROOT.
"""

import hashlib
import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DD10_ROOT = Path("D:/rang/outputs/dd10-20261126")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd10 = _load("dd10", HERE.parent / "dd10" / "dd10.py")
dd9, dd8, dd7, dd5, dd4, dd3, dd2 = (dd10.dd9, dd10.dd8, dd10.dd7, dd10.dd5,
                                     dd10.dd4, dd10.dd3, dd10.dd2)  # fmt: skip
DD7_ROOT = dd10.DD7_ROOT
TI, TI_LONG, CAP, TRUST = dd10.TI, 16, dd10.CAP, dd10.TRUST
N = 6  # section 3: cycles 0-5, the scored point on M_6
N_CTRL = 3  # ATm, ATs
START = dd10.START


def write_json(path, rec):
    dd10.write_json(path, rec)


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


# -- the fast Hogbom (section 3, gate F) -----------------------------------------------


def hogbom_fast(residual, psf, interior, search=None):
    """DD3's `hogbom` with the residual kept on the search pixels only:
    the same peaks (first maximum in row-major order), the same r - f b per
    pixel, so the same components. Returns (components, residual on the
    search pixels, info)."""
    res = np.array(residual, np.float64)
    sigma = 1.4826 * float(np.median(np.abs(res[interior] - np.median(res[interior]))))
    stop = max(dd3.SIGMAS * sigma, dd3.FLOOR)
    keep = np.asarray(interior if search is None else search, bool)
    ny, nx = res.shape
    stride = psf.shape[1]
    yy, xx = np.nonzero(keep)
    rk = res[yy, xx]
    pf = np.ascontiguousarray(psf, np.float64).ravel()
    off = yy * stride + xx
    comps = {}
    for _ in range(dd3.MAX_COMPONENTS):
        j = int(np.argmax(np.abs(rk)))
        peak = rk[j]
        if abs(peak) < stop:
            break
        y, x = int(yy[j]), int(xx[j])
        f = dd3.GAIN * peak
        comps[(y, x)] = comps.get((y, x), 0.0) + f
        rk -= f * pf[off + ((ny - y) * stride + (nx - x))]
    return comps, rk, {"sigma": sigma, "stop": stop, "n": len(comps)}


def _masks(root):
    """O's d1-d3 clean interior and search masks (DD10's loop)."""
    ctx = masks_ctx(root / "O")
    return ctx["interior"] & (ctx["idx"] > 0), ctx["search"] & (ctx["idx"] > 0)


def masks_ctx(run):
    """dd4.context's image masks without reading the MS."""
    st = json.loads((run / "setup.json").read_text())
    centres = np.array(st["centres"])
    l, m = dd2.pixel_lm()
    idx, margin = dd2.facet_index_and_margin(l, m, centres)
    xg, yg = np.meshgrid(np.arange(dd4.NX), np.arange(dd4.NY))
    e = dd4.EDGE
    interior = (
        (margin >= e) & (xg >= e) & (xg < dd4.NX - e) & (yg >= e) & (yg < dd4.NY - e)
    )
    search = interior.copy()
    for y, x in st["pins"]:
        search[max(y - 2, 0) : y + 3, max(x - 2, 0) : x + 3] = False
    return {"idx": idx, "interior": interior, "search": search}


def gatef(root):
    root = Path(root)
    psf_img = np.load(root / "psf" / "O.npy")
    interior, search = _masks(root)
    rec = {"cases": {}}
    ok_all = True
    for cyc in (0, 1):
        r = np.load(
            DD10_ROOT / "loop" / "ALu" / f"cycle-{cyc}" / "residual.npy"
        ).astype(np.float64)
        t0 = time.perf_counter()
        ca, _, ia = dd3.hogbom(r, psf_img, interior, search)
        t1 = time.perf_counter()
        cb, _, ib = hogbom_fast(r, psf_img, interior, search)
        t2 = time.perf_counter()
        same_keys = list(ca) == list(cb)
        same_flux = same_keys and all(ca[k] == cb[k] for k in ca)
        ok = same_keys and same_flux and ia == ib
        ok_all &= ok
        rec["cases"][f"ALu-cycle-{cyc}"] = {"n_dd3": len(ca), "n_fast": len(cb), "same_pixels_in_order": same_keys,
                                            "fluxes_bitwise": same_flux, "info_dd3": ia, "info_fast": ib,
                                            "seconds_dd3": t1 - t0, "seconds_fast": t2 - t1}  # fmt: skip
    rec["F_pass"] = bool(ok_all)
    write_json(root / "gatef.json", rec)


# -- reuse and PSF ---------------------------------------------------------------------


# (DD10 source, DD11 destination) relative to the roots; a source may have
# several destinations
REUSE = (
    [
        (f"loop/ALu/cycle-{k}/{f}", f"loop/U6/cycle-{k}/{f}")
        for k in (0, 1, 2)
        for f in ("info.json", "gains.npz", "next_model.npy", "residual.npy")
    ]
    + [
        (f"loop/AT/cycle-{k}/{f}", f"loop/AT6/cycle-{k}/{f}")
        for k in (0, 1, 2)
        for f in ("info.json", "next_model.npy", "residual.npy")
    ]
    + [
        (f"loop/AL/cycle-{k}/gains.npz", f"reuse/AL-cycle-{k}-gains.npz")
        for k in (0, 1, 2)
    ]
    + [
        ("loop/ALu/cycle-3/gains.npz", "loop/U6/cycle-3/reuse_gains.npz"),
        ("loop/ALu/cycle-3/info.json", "loop/U6/cycle-3/reuse_info.json"),
        ("loop/AL/cycle-0/gains.npz", "loop/Q6/cycle-0/reuse_gains.npz"),
        ("loop/AL/cycle-0/info.json", "loop/Q6/cycle-0/reuse_info.json"),
        ("loop/AL/cycle-0/gains.npz", "loop/ATs/cycle-0/reuse_gains.npz"),
        ("loop/AL/cycle-0/info.json", "loop/ATs/cycle-0/reuse_info.json"),
        ("loop/RL/cycle-0/gains.npz", "reuse/R0-gains.npz"),
        ("loop/RL/cycle-0/info.json", "reuse/R0-info.json"),
        ("loop/AT/cycle-3/gains.npz", "reuse/AT-final-gains.npz"),
        ("loop/ALu/cycle-3/info.json", "reuse/ALu-final-info.json"),
        ("loop/AT/cycle-3/info.json", "reuse/AT-final-info.json"),
        ("loop/AL/cycle-3/info.json", "reuse/AL-final-info.json"),
        ("loop/RL/cycle-3/info.json", "reuse/RL-final-info.json"),
        ("points/AX-OX-gs.npz", "reuse/AX-gains.npz"),
        ("points/AX-OX-gs.json", "reuse/AX.json"),
        ("score.json", "reuse/dd10-score.json"),
        ("psf/O.json", "reuse/psf-O.json"),
        ("psf/real.json", "reuse/psf-real.json"),
    ]
)


def reuse(root):
    root = Path(root)
    rec = {}
    for src, dst in REUSE:
        s, d = DD10_ROOT / src, root / dst
        d.parent.mkdir(parents=True, exist_ok=True)
        if not d.exists():
            shutil.copy2(s, d)
        rec[dst] = {"from": str(s), "sha256": sha_file(d), "source_sha256": sha_file(s)}
        assert rec[dst]["sha256"] == rec[dst]["source_sha256"]
    write_json(root / "reuse.json", rec)


def psf(root, base):
    """DD10's PSF; its peak against DD10's record (section 2)."""
    root = Path(root)
    dd10.psf(root, base)
    mine = json.loads((root / "psf" / f"{base}.json").read_text())["peak"]
    ref = json.loads((root / "reuse" / f"psf-{base}.json").read_text())["peak"]
    rec = {"peak": mine, "dd10_peak": ref, "pass": abs(mine - ref) <= 1e-9 * abs(ref)}
    write_json(root / "psf" / f"{base}-check.json", rec)
    if not rec["pass"]:
        raise SystemExit("PSF peak differs from DD10's")


def setup_gate(root):
    """Section 2: the rebuilt O against DD10's build record and DD8's sky."""
    root = Path(root)
    mine = json.loads((root / "O" / "build.json").read_text())
    ref = json.loads((DD10_ROOT / "O" / "build.json").read_text())
    bad = []
    for k, v in ref.items():
        if k == "seconds":
            continue
        a, b = np.atleast_1d(mine[k]).astype(float), np.atleast_1d(v).astype(float)
        if not np.allclose(a, b, rtol=1e-9, atol=0):
            bad.append(k)
    sky = sha_file(root / "O" / "sky.npy")
    sky_ref = sha_file(Path("D:/rang/outputs/dd8-20261125") / "O" / "sky.npy")
    rec = {"differing": bad, "sky_sha256": sky, "dd8_sky_sha256": sky_ref,
           "GO_pass": bool(mine.get("GO_pass")), "pass": not bad and sky == sky_ref and bool(mine.get("GO_pass"))}  # fmt: skip
    write_json(root / "setup-gate.json", rec)
    if not rec["pass"]:
        raise SystemExit("setup gate failed")


# -- diagnostic D (section 5) ----------------------------------------------------------


def gain_errors(gains, flags, truth):
    """Per direction d1-d3 on unflagged cells (DD5's products, ti = 4):
    e_d, phase-only e_d, |amp ratio - 1| median, signed amp bias median."""
    g, f = gains[:, 0], flags[:, 0]
    nant = g.shape[1]
    p, q = np.triu_indices(nant, 1)
    P = g[:, p] * np.conj(g[:, q])
    T = truth[:, p] * np.conj(truth[:, q])
    ok = (f[:, p] == 0) & (f[:, q] == 0)
    out = {
        "e": [],
        "e_phase": [],
        "amp_abs_err": [],
        "amp_bias": [],
        "phase_rad_median": [],
    }
    for d in range(1, 4):
        sel = np.broadcast_to(ok[:, :, d, None], P[:, :, d].shape)
        pp, tt = P[:, :, d][sel], T[:, :, d][sel]
        ratio = np.abs(pp) / np.abs(tt)
        out["e"].append(float(np.median(np.abs(pp - tt) / np.abs(tt))))
        out["e_phase"].append(
            float(np.median(np.abs(pp / np.abs(pp) - tt / np.abs(tt))))
        )
        out["amp_abs_err"].append(float(np.median(np.abs(ratio - 1))))
        out["amp_bias"].append(float(np.median(ratio - 1)))
        out["phase_rad_median"].append(
            float(np.median(np.abs(np.angle(pp * np.conj(tt)))))
        )
    return out


def diag(root):
    root = Path(root)
    truth = np.load(root / "O" / "truth.npz")["gains"]
    srcs = {"A0": root / "loop" / "Q6" / "cycle-0" / "reuse_gains.npz",
            "ALu_final": DD10_ROOT / "loop" / "ALu" / "cycle-3" / "gains.npz",
            "AT_final": root / "reuse" / "AT-final-gains.npz",
            "AX": root / "reuse" / "AX-gains.npz"}  # fmt: skip
    rec = {}
    for name, path in srcs.items():
        z = np.load(path)
        rec[name] = gain_errors(z["gains"], z["flags"], truth)
    write_json(root / "diag.json", rec)


# -- the loops (sections 3, 4 and 7) ---------------------------------------------------


# start: rule for cycles 0-1; ncycle; base; images in the cycles
ARMS = {
    "U6": {"base": "O", "n": N, "start": "gs", "images": "U"},
    "P6": {"base": "O", "n": N, "start": "phase", "images": "U"},
    "Q6": {"base": "O", "n": N, "start": "gs-unitamp", "images": "U"},
    "L6": {"base": "O", "n": N, "start": "gs16", "images": "U"},
    "AT6": {"base": "O", "n": N, "start": "truth", "images": "truth"},
    "ATm": {"base": "O", "n": N_CTRL, "start": "truth", "images": "truth-ALmask"},
    "ATs": {"base": "O", "n": N_CTRL, "start": "gs", "images": "truth-untrusted"},
}
for _a in ("U6", "P6", "Q6", "L6"):  # section 7: the real reading of the best arm
    ARMS[f"R-{_a}"] = dict(ARMS[_a], base="real")


def untrusted(gains, flags):
    a = np.abs(gains)
    return (flags != 0) | (a < TRUST[0]).any(-1) | (a > TRUST[1]).any(-1)


def solve_cycle(ctx, models, kind, second):
    """One solve of a cycle: `gs` (DD10's scored solver), `phase` (Jacobi
    phase-only, section 4), `gs16` (GS at 16 x 8 s)."""
    from rang import cal_gain

    c = ctx["c"]
    block = ctx["block16"] if kind == "gs16" else ctx["block"]
    args = (c["DATA"], models, c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"],
            c["ANTENNA1"], c["ANTENNA2"], block)  # fmt: skip
    kw = {"nant": len(c["ant_names"]), "refant": None, "pinned_directions": [], "stop_criterion": 1e-7,
          "phase_last_direction_gain": False, "max_iterations": CAP, "stop_fraction": 0.99}  # fmt: skip
    if kind == "phase":
        kw.update(calmode="p")
    else:
        kw.update(calmode="ap", direction_update="gauss-seidel")
    t0 = time.perf_counter()
    sol = cal_gain.solve_dd(*args, **kw)
    out = {"sol": sol, "seconds_solve": time.perf_counter() - t0}
    if second:
        t1 = time.perf_counter()
        out["sol2"] = cal_gain.solve_dd(
            *args, **{**kw, "max_iterations": sol.iterations + 1, "stop_fraction": 1.0}
        )
        out["seconds_second"] = time.perf_counter() - t1
    return out


def cycle_scores(ctx, models, kind, sol, sol2, k):
    """DD10's scores for a 4 x 8 s `ap` solve; for the start solves of P6
    and L6 the truth errors they allow (not comparable, section 3)."""
    if kind == "gs":
        rec, conv = dd10.scores(ctx, models, sol, sol2, k)
        return rec, conv
    gains, flags = np.asarray(sol.gains), np.asarray(sol.flags)
    rec = {"iterations": sol.iterations, "global_fraction": sol.converged_fraction,
           "flagged": [int((flags[..., f] != 0).sum()) for f in range(4)], "kind": kind}  # fmt: skip
    if (ctx["run"] / "truth.npz").exists():
        ti = TI_LONG if kind == "gs16" else TI
        rec["e_d_not_comparable"] = dd5.truth_error(
            ctx["run"], ctx, gains, flags, ti, False
        )
        rec["e_d_phase_only"] = dd5.truth_error(ctx["run"], ctx, gains, flags, ti, True)
    if kind == "gs16":
        rec["d3_amp"] = dd9.amp_tail(gains[:, 0, :, 3], flags[:, 0, :, 3])
    return rec, None


def loop(root, arm):
    """Resumable per cycle. A cycle directory with info.json is kept; one
    with reuse_gains.npz takes that solve (DD10's, section 2)."""
    root = Path(root)
    spec = ARMS[arm]
    base, n = spec["base"], spec["n"]
    ctx = dd10.base_ctx(root, base)
    c = ctx["c"]
    ctx["block16"] = dd2.interval_axes(c, TI_LONG)[2]
    k = float(json.loads((DD7_ROOT / "b" / "setup.json").read_text())["dd5"]["k"])
    psf_img = np.load(root / "psf" / f"{base}.npy")
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search = ctx["search"] & (ctx["idx"] > 0)
    sky = np.load(root / "O" / "sky.npy") if base == "O" else None
    truth = np.load(root / "O" / "truth.npz")["gains"][:, None] if base == "O" else None
    model = np.load(START[base])
    out = root / "loop" / arm
    for cyc in range(n + 1):
        d = out / f"cycle-{cyc}"
        if (d / "info.json").exists():
            model = np.load(d / "next_model.npy") if cyc < n else model
            print(f"{arm} cycle {cyc}: kept", flush=True)
            continue
        t0 = time.perf_counter()
        models = dd4.facet_models(ctx, model)
        info = {"arm": arm, "cycle": cyc, "seconds_predict": time.perf_counter() - t0}
        if sky is not None:
            info["model_error"] = dd10.model_error(ctx, model, sky)
        final = cyc == n
        start = cyc < 2
        kind = spec["start"] if start else "gs"
        if final:
            kind = "gs"
        kind_solve = "gs" if kind == "gs-unitamp" else kind
        gains = flags = None
        d.mkdir(parents=True, exist_ok=True)
        if kind_solve == "truth" and not final:
            pass  # no solve inside the truth-gain cycles
        elif (d / "reuse_gains.npz").exists():
            z = np.load(d / "reuse_gains.npz")
            gains, flags = z["gains"], z["flags"]
            info["solve"] = json.loads((d / "reuse_info.json").read_text())["solve"]
            info["solve_reused_from"] = str(d / "reuse_gains.npz")
            np.savez_compressed(d / "gains.npz", **{key: z[key] for key in z.files})
        elif base == "real" and cyc == 0 and kind_solve == "gs":
            z = np.load(root / "reuse" / "R0-gains.npz")
            gains, flags = z["gains"], z["flags"]
            info["solve"] = json.loads((root / "reuse" / "R0-info.json").read_text())[
                "solve"
            ]
            info["solve_reused_from"] = str(root / "reuse" / "R0-gains.npz")
            np.savez_compressed(d / "gains.npz", **{key: z[key] for key in z.files})
        else:
            scored = final or cyc == 0
            res = solve_cycle(
                ctx, models, kind_solve, second=scored and kind_solve == "gs"
            )
            sol = res["sol"]
            gains, flags = np.asarray(sol.gains), np.asarray(sol.flags)
            srec, conv = cycle_scores(ctx, models, kind_solve, sol, res.get("sol2"), k)
            info["solve"] = srec
            info["seconds_solve"] = res["seconds_solve"]
            info["seconds_second"] = res.get("seconds_second")
            save = {"gains": gains, "flags": flags}
            if "sol2" in res:
                save.update(gains2=np.asarray(res["sol2"].gains), flags2=np.asarray(res["sol2"].flags),
                            converged=conv)  # fmt: skip
            np.savez_compressed(d / "gains.npz", **save)
            del res
        if not final or base == "real":
            t1 = time.perf_counter()
            w = c["w_I"]
            images = spec["images"]
            info["excluded_weight_share"] = 0.0
            img_ctx = ctx
            if final:  # real only: the final residual for the reported rms, rule U
                images = "U"
            if images == "truth":
                ig = truth
            elif images == "truth-ALmask":
                z = np.load(root / "reuse" / f"AL-cycle-{cyc}-gains.npz")
                rows = dd10.trusted_rows(ctx, z["gains"], z["flags"])
                w = np.where(rows[:, None], c["w_I"], 0.0)
                info["excluded_weight_share"] = float(1 - w.sum() / c["w_I"].sum())
                ig = truth
            else:
                bad = untrusted(gains, flags)
                info["untrusted_gain_share"] = [
                    float(bad[..., f].mean()) for f in range(4)
                ]
                if images == "truth-untrusted":
                    ig = np.where(bad[..., None], truth, gains)
                else:
                    g = (
                        gains / np.abs(gains)
                        if (kind == "gs-unitamp" and not final)
                        else gains
                    )
                    ig = np.where(bad[..., None], 1.0 + 0j, g)
                if kind_solve == "gs16" and not final:
                    img_ctx = dict(ctx, block=ctx["block16"])
            resid = dd10.residual_image(img_ctx, models, ig, w)
            info["image_rule"] = images + (
                " unit-amplitude" if kind == "gs-unitamp" else ""
            )
            info["seconds_image"] = time.perf_counter() - t1
            info["residual_sigma_d1_d3"] = dd10.mad_sigma(resid, clean_interior)
            info["thermal_sigma"] = dd10.thermal_sigma(ctx, w, k)
            np.save(d / "residual.npy", resid.astype(np.float32))
            if not final:
                t2 = time.perf_counter()
                comps, _, hinfo = hogbom_fast(resid, psf_img, clean_interior, search)
                info["hogbom"] = hinfo
                info["components_flux"] = float(sum(comps.values()))
                info["seconds_hogbom"] = time.perf_counter() - t2
                model = dd3.add_components(model, comps)
                np.save(d / "next_model.npy", model)
        del models
        info["seconds"] = time.perf_counter() - t0
        (d / "info.json").write_text(json.dumps(info, indent=1, default=float))
        print(
            f"{arm} cycle {cyc}: {json.dumps(info, default=float)[:1500]}", flush=True
        )


# -- readings (sections 6 and 7) -------------------------------------------------------


def reading(e, e0, ex):
    G = [(e0[d] - e[d]) / (e0[d] - ex[d]) for d in range(1, 4)]
    harm = any(e[d] > 1.2 * e0[d] for d in (2, 3))
    g1 = G[0]
    r = ("closes" if g1 >= 0.5 and not harm else "partly" if g1 >= 0.2 and not harm
         else "moves the error" if g1 >= 0.2 else "no")  # fmt: skip
    return G, harm, r


def score(root):
    root = Path(root)
    rd = lambda p: json.loads(Path(p).read_text())
    d10 = rd(root / "reuse" / "dd10-score.json")
    e0 = d10["A0"]["e_d"]
    ex = d10["AX"]["e_d"]
    eat = d10["AT"]["final"]["e_d"]
    ealu = d10["ALu"]["final"]["e_d"]
    rec = {
        "references": {
            "A0": e0,
            "AX": ex,
            "AT": eat,
            "ALu": ealu,
            "AL": d10["AL"]["final"]["e_d"],
        }
    }
    for arm in ("U6", "P6", "Q6", "L6", "AT6", "ATm", "ATs"):
        n = ARMS[arm]["n"]
        f = root / "loop" / arm / f"cycle-{n}" / "info.json"
        if not f.exists():
            continue
        s = rd(f)["solve"]
        e = s["e_d"]
        G, harm, r = reading(e, e0, ex)
        S = [(e0[d] - e[d]) / (e0[d] - eat[d]) for d in range(1, 4)]
        cycles = []
        for cyc in range(n + 1):
            ci = rd(root / "loop" / arm / f"cycle-{cyc}" / "info.json")
            sv = ci.get("solve") or {}
            cycles.append({kk: ci.get(kk) for kk in ("model_error", "hogbom", "components_flux", "untrusted_gain_share",
                                                     "excluded_weight_share", "residual_sigma_d1_d3", "image_rule")}
                          | {"e_d": sv.get("e_d"), "e_d_not_comparable": sv.get("e_d_not_comparable"),
                             "e_d_phase_only": sv.get("e_d_phase_only"), "perdir_converged": sv.get("perdir_converged"),
                             "global_fraction": sv.get("global_fraction"), "iterations": sv.get("iterations")})  # fmt: skip
        rec[arm] = {"final": s, "e_d1_d3": e[1:], "G_d1_d3": G, "S_AT_d1_d3": S, "harm": harm, "reading": r,
                    "cycles": cycles}  # fmt: skip
    if "AT6" in rec:
        e6 = rec["AT6"]["final"]["e_d"]
        for arm, val in rec.items():
            if arm in ("U6", "P6", "Q6", "L6", "AT6", "ATm", "ATs"):
                e = val["final"]["e_d"]
                val["S_AT6_d1_d3"] = [
                    (e0[d] - e[d]) / (e0[d] - e6[d]) for d in range(1, 4)
                ]
    if "U6" in rec:
        eu = rec["U6"]["final"]["e_d"]
        for arm in ("P6", "Q6", "L6"):
            if arm not in rec:
                continue
            e = rec[arm]["final"]["e_d"]
            worse = any(e[d] > 1.2 * eu[d] for d in (2, 3))
            rec[arm]["start_effect"] = ("hurts" if e[1] >= 1.1 * eu[1] or worse
                                        else "helps" if e[1] <= 0.9 * eu[1] else "no effect")  # fmt: skip
        rec["more_cycles"] = (
            "help"
            if eu[1] <= 0.9 * ealu[1] and not rec["U6"]["harm"]
            else "do not help"
        )
    if "ATm" in rec:
        g = rec["ATm"]["G_d1_d3"][0]
        rec["weight_loss"] = ("weight loss alone does not stop the loop" if g >= 0.5 else
                              "weight loss alone stops it" if g < 0.2 else "both contribute")  # fmt: skip
    if "ATs" in rec:
        s1 = rec["ATs"]["S_AT_d1_d3"][0]
        rec["absorption"] = ("the trusted solved gains do not absorb the gap" if s1 >= 0.8 else
                             "the trusted solved gains absorb the gap" if s1 < 0.5 else "partly")  # fmt: skip
    elig = [a for a in ("U6", "P6", "Q6", "L6") if a in rec]
    if len(elig) == 4:
        starts = [a for a in ("P6", "Q6", "L6") if rec[a]["reading"] == "closes"]
        pool = [a for a in elig if not rec[a]["harm"]] or elig
        pool.sort(key=lambda a: rec[a]["final"]["e_d"][1])
        best = pool[0]
        ties = [
            a
            for a in pool
            if rec[a]["final"]["e_d"][1] - rec[best]["final"]["e_d"][1] <= 0.005
        ]
        best = min(ties, key=lambda a: np.mean(rec[a]["final"]["e_d"][2:4]))
        rec["best_arm"] = best + ("" if not rec[best]["harm"] else " (with harm)")
        if starts:
            rec["answer"] = (
                f"yes: start {starts} keeps the gains from absorbing the gap, and the loop closes on O"
            )
        elif rec["U6"]["reading"] == "closes":
            rec["answer"] = "more cycles close the loop; the start is not needed"
        elif rec[best]["reading"] == "partly":
            rec["answer"] = (
                f"partly: the best start ({best}) closes G_d1 {rec[best]['G_d1_d3'][0]:.3f} of the gap"
            )
        else:
            rec["answer"] = "no: no start tested keeps the gains from absorbing the gap"
    # section 7: the real reading
    for arm in ("U6", "P6", "Q6", "L6"):
        rf = root / "loop" / f"R-{arm}" / f"cycle-{N}" / "info.json"
        if not rf.exists():
            continue
        r0 = rd(root / "reuse" / "R0-info.json")
        rx = rd(rf)
        rl = rd(root / "reuse" / "RL-final-info.json")
        m0 = min(r0["solve"]["perdir_converged"][1:])
        m1 = min(rx["solve"]["perdir_converged"][1:])
        amp = rx["solve"]["d3_amp"]
        cyc = [
            rd(root / "loop" / f"R-{arm}" / f"cycle-{k2}" / "info.json")
            for k2 in range(N + 1)
        ]
        rec[f"R-{arm}"] = {"R0_min_d1_d3": m0, "RX_min_d1_d3": m1, "lifts": m1 >= m0 + 0.20,
                           "tames_d3": amp["p99"] <= 3 and amp["max"] <= 10,
                           "supported_by_O": rec.get(arm, {}).get("reading") in ("closes", "partly"),
                           "RX": rx["solve"], "RL_dd10": rl["solve"],
                           "cycles": [{kk: ci.get(kk) for kk in ("hogbom", "untrusted_gain_share", "residual_sigma_d1_d3",
                                                                 "thermal_sigma", "components_flux")}
                                      | {"perdir_converged": (ci.get("solve") or {}).get("perdir_converged"),
                                         "global_fraction": (ci.get("solve") or {}).get("global_fraction")}
                                      for ci in cyc]}  # fmt: skip
    write_json(root / "score.json", rec)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "reuse":
        reuse(argv[1])
    elif cmd == "psf":
        psf(argv[1], argv[2])
    elif cmd == "setup":
        setup_gate(argv[1])
    elif cmd == "gatef":
        gatef(argv[1])
    elif cmd == "diag":
        diag(argv[1])
    elif cmd == "loop":
        loop(argv[1], argv[2])
    elif cmd == "score":
        score(argv[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
