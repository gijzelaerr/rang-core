# SPDX-License-Identifier: MIT
"""DD12: a multi-scale minor cycle in the DD loop, on O
(research/dd12-msclean.md).

    python tools/oracles/dd12/dd12.py reuse ROOT        # copy DD11's reused files, reuse.json
    python tools/oracles/dd12/dd12.py setup ROOT        # DD11's setup gate on the rebuilt O
    python tools/oracles/dd12/dd12.py psf ROOT BASE     # DD10's PSF, peak checked
    python tools/oracles/dd12/dd12.py gater ROOT        # gate R: reproduction of DD11's Q6
    python tools/oracles/dd12/dd12.py gatem ROOT        # gate M1 and pilot T (scale ladder)
    python tools/oracles/dd12/dd12.py loop ROOT ARM     # Q12 MS12 AT12 ATM12 R-MS6 R-MS12
    python tools/oracles/dd12/dd12.py score ROOT        # section 6 and 7 readings

DD7's to DD11's roots are read only; reused files are copied into ROOT.
"""

import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DD11_ROOT = Path("D:/rang/outputs/dd11-20261126")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd11 = _load("dd11", HERE.parent / "dd11" / "dd11.py")
dd10, dd5, dd4, dd3, dd2 = dd11.dd10, dd11.dd5, dd11.dd4, dd11.dd3, dd11.dd2
DD7_ROOT = dd10.DD7_ROOT
START = dd10.START

# section 3, minor cycle S (WSClean 3.7's multi-scale defaults)
MS = {"gain": dd3.GAIN, "sub_minor_gain": 0.2, "scale_bias": 0.6,
      "max_components": dd3.MAX_COMPONENTS, "max_major": 50, "patch": 64}  # fmt: skip
MAX_SCALES = 5
PILOT_LIMIT = 1800.0  # pilot T, seconds


def write_json(path, rec):
    dd10.write_json(path, rec)


# -- minor cycle S ---------------------------------------------------------------------


def theoretic_beam_pixels(ctx):
    from rang import _core

    c = ctx["c"]
    w = np.ascontiguousarray(c["w_I"], np.float64)
    b = _core.multiscale_theoretic_beam(
        np.ascontiguousarray(c["UVW"], np.float64),
        np.ascontiguousarray(c["freq"], np.float64),
        w.reshape(w.shape[0], -1),
        dd4.NX,
        dd2.DELTA,
    )
    return float(b / dd2.DELTA)


def multiscale(residual, psf, interior, search, beam_pixels, nscales):
    """Minor cycle S (section 3): the increment clipped to the search pixels,
    the full model, the binding's residual and the record."""
    from rang import _core

    res = np.ascontiguousarray(residual, np.float64)
    sigma = 1.4826 * float(np.median(np.abs(res[interior] - np.median(res[interior]))))
    stop = max(dd3.SIGMAS * sigma, dd3.FLOOR)
    n = res.shape[0]
    model = np.zeros_like(res)
    out = np.zeros_like(res)
    t0 = time.perf_counter()
    rec = _core.multiscale_image(
        n, res, np.ascontiguousarray(psf, np.float64),
        np.ascontiguousarray(search, np.uint8), stop, MS["gain"], MS["max_components"],
        MS["max_major"], [], nscales, MS["scale_bias"], MS["sub_minor_gain"], beam_pixels,
        MS["patch"], model, out,
    )  # fmt: skip
    rec = dict(rec)
    rec["wall"] = time.perf_counter() - t0
    rec["sigma"], rec["stop_level"], rec["nscales_cap"] = sigma, stop, nscales
    rec["scales"] = [dict(zip(("scale", "kernel_side", "bias", "psf_peak", "gain", "components",
                                "flux"), s, strict=True)) for s in rec["scales"]]  # fmt: skip
    inc = np.where(search, model, 0.0)
    rec["model_flux"] = float(model.sum())
    rec["increment_flux"] = float(inc.sum())
    return inc, model, out, rec


def clipped(ctx, model, inc):
    """Section 3's clip record per facet: net and absolute flux removed."""
    d = model - inc
    idx = ctx["idx"]
    return {"net": [float(d[idx == f].sum()) for f in range(4)],
            "abs": [float(np.abs(d[idx == f]).sum()) for f in range(4)]}  # fmt: skip


# -- reuse, setup, PSF -----------------------------------------------------------------


REUSE = (
    [
        (f"loop/Q6/cycle-{k}/{f}", f"loop/Q12/cycle-{k}/{f}")
        for k in range(6)
        for f in ("info.json", "gains.npz", "next_model.npy", "residual.npy")
    ]
    + [
        (f"loop/AT6/cycle-{k}/{f}", f"loop/AT12/cycle-{k}/{f}")
        for k in range(6)
        for f in ("info.json", "next_model.npy")
    ]
    + [
        ("loop/Q6/cycle-6/gains.npz", "loop/Q12/cycle-6/reuse_gains.npz"),
        ("loop/Q6/cycle-6/info.json", "loop/Q12/cycle-6/reuse_info.json"),
        ("loop/AT6/cycle-6/gains.npz", "loop/AT12/cycle-6/reuse_gains.npz"),
        ("loop/AT6/cycle-6/info.json", "loop/AT12/cycle-6/reuse_info.json"),
        ("loop/Q6/cycle-0/reuse_gains.npz", "loop/MS12/cycle-0/reuse_gains.npz"),
        ("loop/Q6/cycle-0/reuse_info.json", "loop/MS12/cycle-0/reuse_info.json"),
        ("loop/Q6/cycle-1/gains.npz", "gate/Q6-cycle-1-gains.npz"),
        ("score.json", "reuse/dd11-score.json"),
        ("reuse/dd10-score.json", "reuse/dd10-score.json"),
        ("reuse/psf-O.json", "reuse/psf-O.json"),
        ("reuse/psf-real.json", "reuse/psf-real.json"),
        ("reuse/R0-gains.npz", "reuse/R0-gains.npz"),
        ("reuse/R0-info.json", "reuse/R0-info.json"),
        ("reuse/RL-final-info.json", "reuse/RL-final-info.json"),
        ("loop/R-Q6/cycle-6/info.json", "reuse/R-Q6-final-info.json"),
    ]
)


def reuse(root):
    root = Path(root)
    rec = {}
    for src, dst in REUSE:
        s, d = DD11_ROOT / src, root / dst
        d.parent.mkdir(parents=True, exist_ok=True)
        if not d.exists():
            shutil.copy2(s, d)
        rec[dst] = {"from": str(s), "sha256": dd11.sha_file(d),
                    "source_sha256": dd11.sha_file(s)}  # fmt: skip
        assert rec[dst]["sha256"] == rec[dst]["source_sha256"]
    write_json(root / "reuse.json", rec)


# -- gate R (section 5) ----------------------------------------------------------------


def gater(root, part1_only=False):
    root = Path(root)
    ctx = dd10.base_ctx(root, "O")
    c = ctx["c"]
    psf_img = np.load(root / "psf" / "O.npy")
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search = ctx["search"] & (ctx["idx"] > 0)
    q6 = DD11_ROOT / "loop" / "Q6"
    rec = {}
    # (1) cycle 0's residual and Hogbom from A0's gains
    z = np.load(root / "loop" / "MS12" / "cycle-0" / "reuse_gains.npz")
    gains, flags = z["gains"], z["flags"]
    bad = dd11.untrusted(gains, flags)
    ig = np.where(bad[..., None], 1.0 + 0j, gains / np.abs(gains))
    t0 = time.perf_counter()
    models = dd4.facet_models(ctx, np.load(START["O"]))
    full = dd10.residual_image(ctx, models, ig, c["w_I"])
    resid = full.astype(np.float32)  # DD11 saved float32 and cleaned float64 (A1)
    ref = np.load(q6 / "cycle-0" / "residual.npy")
    diff = float(np.abs(resid.astype(np.float64) - ref).max())
    comps, _, _ = dd11.hogbom_fast(full, psf_img, clean_interior, search)
    m1 = dd3.add_components(np.load(START["O"]), comps)
    m1_ref = np.load(q6 / "cycle-0" / "next_model.npy")
    rec["residual_bitwise"] = bool(np.array_equal(resid, ref))
    rec["residual_max_abs_diff"] = diff
    rec["residual_rel"] = diff / float(np.abs(ref).max())
    rec["next_model_bitwise"] = bool(np.array_equal(m1, m1_ref))
    rec["seconds_1"] = time.perf_counter() - t0
    del models
    if part1_only:  # A1: part (1) again, part (2) kept from the first run
        prev = json.loads((root / "gate" / "gater.json").read_text())
        rec["first_run"] = {k: prev[k] for k in prev if k != "first_run"}
        for k in ("cycle1_gains_bitwise", "cycle1_flags_bitwise", "seconds_2"):
            rec[k] = prev[k]
    else:
        _gater_solve(ctx, root, m1_ref, rec)
    ok1 = (rec["residual_bitwise"] or rec["residual_rel"] <= 1e-6) and rec[
        "next_model_bitwise"
    ]
    rec["R_pass"] = bool(
        ok1 and rec["cycle1_gains_bitwise"] and rec["cycle1_flags_bitwise"]
    )
    write_json(root / "gate" / "gater.json", rec)
    print(json.dumps(rec), flush=True)


def _gater_solve(ctx, root, m1_ref, rec):
    # (2) the cycle-1 solve with DD11's M_1
    t1 = time.perf_counter()
    models = dd4.facet_models(ctx, m1_ref)
    sol = dd11.solve_cycle(ctx, models, "gs", second=False)["sol"]
    g1 = np.load(root / "gate" / "Q6-cycle-1-gains.npz")
    rec["cycle1_gains_bitwise"] = bool(
        np.array_equal(np.asarray(sol.gains), g1["gains"])
    )
    rec["cycle1_flags_bitwise"] = bool(
        np.array_equal(np.asarray(sol.flags), g1["flags"])
    )
    rec["seconds_2"] = time.perf_counter() - t1


# -- gate M1 and pilot T (section 5) ---------------------------------------------------


def bm_direct(model, psf2n):
    """B m by a direct FFT convolution with the 2n PSF (SciPy, independent
    of the binding)."""
    from scipy.signal import fftconvolve

    n = model.shape[0]
    full = fftconvolve(model, psf2n, mode="full")
    return full[n : 2 * n, n : 2 * n]


def gatem(root):
    root = Path(root)
    ctx = dd11.masks_ctx(root / "O")
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search = ctx["search"] & (ctx["idx"] > 0)
    psf_img = np.load(root / "psf" / "O.npy")
    assert psf_img.shape == (2 * dd4.NY, 2 * dd4.NX)
    assert np.unravel_index(np.argmax(psf_img), psf_img.shape) == (dd4.NY, dd4.NX)
    bctx = dd10.base_ctx(root, "O")
    b = theoretic_beam_pixels(bctx)
    del bctx
    resid = np.load(DD11_ROOT / "loop" / "Q6" / "cycle-0" / "residual.npy").astype(
        np.float64
    )
    rec = {"beam_pixels": b, "ladder": []}
    chosen = None
    for nscales in (MAX_SCALES, 4, 3):
        _, model, out, info = multiscale(
            resid, psf_img, clean_interior, search, b, nscales
        )
        info.pop("cycles", None)
        rec["ladder"].append(info)
        if chosen is None and "M1" not in rec:
            err = float(np.abs(out - (resid - bm_direct(model, psf_img))).max())
            rec["M1"] = {"max_abs_diff": err, "rel": err / float(np.abs(resid).max()),
                         "pass": err <= 1e-8 * float(np.abs(resid).max())}  # fmt: skip
        print(json.dumps(info, default=float)[:2000], flush=True)
        if info["wall"] <= PILOT_LIMIT:
            chosen = nscales
            break
    rec["nscales"] = chosen
    rec["M_pass"] = bool(rec["M1"]["pass"])
    write_json(root / "gate" / "gatem.json", rec)


def nscales_used(root):
    return int(json.loads((Path(root) / "gate" / "gatem.json").read_text())["nscales"])


# -- the loops (sections 3, 4 and 7) ---------------------------------------------------


# minor: H (hogbom_fast) or S (multi-scale); images: U (rule U, Q6's start) or truth
ARMS = {
    "Q12": {"base": "O", "n": 12, "minor": "H", "images": "U", "scored": (6, 12)},
    "MS12": {"base": "O", "n": 12, "minor": "S", "images": "U", "scored": (6, 12)},
    "AT12": {"base": "O", "n": 12, "minor": "H", "images": "truth", "scored": (6, 12)},
    "ATM12": {"base": "O", "n": 12, "minor": "S", "images": "truth", "scored": (6, 12)},
    "R-MS6": {"base": "real", "n": 6, "minor": "S", "images": "U", "scored": (6,)},
    "R-MS12": {"base": "real", "n": 12, "minor": "S", "images": "U", "scored": (12,)},
}


def loop(root, arm):
    """Resumable per cycle. A cycle directory with info.json is kept; one
    with reuse_gains.npz takes that solve."""
    root = Path(root)
    spec = ARMS[arm]
    base, n = spec["base"], spec["n"]
    ctx = dd10.base_ctx(root, base)
    c = ctx["c"]
    k = float(json.loads((DD7_ROOT / "b" / "setup.json").read_text())["dd5"]["k"])
    psf_img = np.load(root / "psf" / f"{base}.npy")
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search = ctx["search"] & (ctx["idx"] > 0)
    sky = np.load(root / "O" / "sky.npy") if base == "O" else None
    truth = np.load(root / "O" / "truth.npz")["gains"][:, None] if base == "O" else None
    beam_px = nsc = None
    if spec["minor"] == "S":
        beam_px, nsc = theoretic_beam_pixels(ctx), nscales_used(root)
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
        scored = cyc in spec["scored"]
        truth_arm = spec["images"] == "truth"
        unitamp = cyc < 2 and not truth_arm
        gains = flags = None
        d.mkdir(parents=True, exist_ok=True)
        if truth_arm and not scored:
            pass  # truth-gain arms solve only at their scored points
        elif (d / "reuse_gains.npz").exists():
            z = np.load(d / "reuse_gains.npz")
            gains, flags = z["gains"], z["flags"]
            info["solve"] = json.loads((d / "reuse_info.json").read_text())["solve"]
            info["solve_reused_from"] = str(d / "reuse_gains.npz")
            np.savez_compressed(d / "gains.npz", **{key: z[key] for key in z.files})
        elif base == "real" and cyc == 0:
            z = np.load(root / "reuse" / "R0-gains.npz")
            gains, flags = z["gains"], z["flags"]
            info["solve"] = json.loads((root / "reuse" / "R0-info.json").read_text())[
                "solve"
            ]
            info["solve_reused_from"] = str(root / "reuse" / "R0-gains.npz")
            np.savez_compressed(d / "gains.npz", **{key: z[key] for key in z.files})
        else:
            res = dd11.solve_cycle(ctx, models, "gs", second=scored)
            sol = res["sol"]
            gains, flags = np.asarray(sol.gains), np.asarray(sol.flags)
            srec, conv = dd11.cycle_scores(ctx, models, "gs", sol, res.get("sol2"), k)
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
            if truth_arm:
                ig = truth
                info["image_rule"] = "truth"
            else:
                bad = dd11.untrusted(gains, flags)
                info["untrusted_gain_share"] = [
                    float(bad[..., f].mean()) for f in range(4)
                ]
                g = gains / np.abs(gains) if (unitamp and not final) else gains
                ig = np.where(bad[..., None], 1.0 + 0j, g)
                info["image_rule"] = "U" + (
                    " unit-amplitude" if unitamp and not final else ""
                )
            resid = dd10.residual_image(ctx, models, ig, c["w_I"])
            info["seconds_image"] = time.perf_counter() - t1
            info["residual_sigma_d1_d3"] = dd10.mad_sigma(resid, clean_interior)
            info["thermal_sigma"] = dd10.thermal_sigma(ctx, c["w_I"], k)
            np.save(d / "residual.npy", resid.astype(np.float32))
            if not final:
                t2 = time.perf_counter()
                if spec["minor"] == "H":
                    comps, _, hinfo = dd11.hogbom_fast(
                        resid, psf_img, clean_interior, search
                    )
                    info["hogbom"] = hinfo
                    info["components_flux"] = float(sum(comps.values()))
                    model = dd3.add_components(model, comps)
                else:
                    inc, full, _, minfo = multiscale(
                        resid, psf_img, clean_interior, search, beam_px, nsc
                    )
                    minfo["clipped"] = clipped(ctx, full, inc)
                    info["multiscale"] = minfo
                    info["components_flux"] = float(inc.sum())
                    model = model + inc
                    del full
                info["seconds_minor"] = time.perf_counter() - t2
                np.save(d / "next_model.npy", model)
        del models
        info["seconds"] = time.perf_counter() - t0
        (d / "info.json").write_text(json.dumps(info, indent=1, default=float))
        print(
            f"{arm} cycle {cyc}: {json.dumps(info, default=float)[:1500]}", flush=True
        )


# -- readings (sections 6 and 7) -------------------------------------------------------


def effect(e, eh):
    """Section 6's deconvolver rule, MS against the Högbom arm (or ATM
    against AT), with the marginal label."""
    r = e[1] / eh[1]
    worse = any(e[d] > 1.2 * eh[d] for d in (2, 3))
    if r >= 1.1 or worse:
        lab = "hurts" + (" (marginal)" if (not worse and r < 1.12) else "")
    elif r <= 0.9:
        lab = "helps" + (" (marginal)" if r > 0.88 else "")
    else:
        lab = "no effect"
    return {"ratio_d1": r, "reading": lab}


def point(root, arm, cyc):
    f = Path(root) / "loop" / arm / f"cycle-{cyc}" / "info.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def score(root):
    root = Path(root)
    rd = lambda p: json.loads(Path(p).read_text())
    d10 = rd(root / "reuse" / "dd10-score.json")
    d11 = rd(root / "reuse" / "dd11-score.json")
    e0, ex = d10["A0"]["e_d"], d10["AX"]["e_d"]
    rec = {"references": {"A0": e0, "AX": ex, "Q6": d11["Q6"]["final"]["e_d"],
                          "AT6": d11["AT6"]["final"]["e_d"]}}  # fmt: skip
    pts = {}
    for arm, nn in (("Q", 6), ("Q", 12), ("MS", 6), ("MS", 12), ("AT", 6), ("AT", 12),
                    ("ATM", 6), ("ATM", 12)):  # fmt: skip
        name = f"{arm}{nn}"
        loop_arm = {"Q": "Q12", "MS": "MS12", "AT": "AT12", "ATM": "ATM12"}[arm]
        ci = point(root, loop_arm, nn)
        if ci is None or "e_d" not in (ci.get("solve") or {}):
            continue
        s = ci["solve"]
        e = s["e_d"]
        G, harm, r = dd11.reading(e, e0, ex)
        me = ci.get("model_error") or {}
        pts[name] = {"e_d": e, "G_d1_d3": G, "harm": harm, "reading": r, "solve": s,
                     "model_abs_error": me.get("abs_error"), "model_net_flux": me.get("net_flux")}  # fmt: skip
    # per-cycle records
    for loop_arm in ("Q12", "MS12", "AT12", "ATM12"):
        cyc = []
        for k in range(13):
            ci = point(root, loop_arm, k)
            if ci is None:
                break
            sv = ci.get("solve") or {}
            ms = ci.get("multiscale") or {}
            cyc.append({kk: ci.get(kk) for kk in ("model_error", "hogbom", "components_flux", "untrusted_gain_share",
                                                  "residual_sigma_d1_d3", "image_rule", "seconds_minor")}
                       | {"e_d": sv.get("e_d"), "perdir_converged": sv.get("perdir_converged"),
                          "global_fraction": sv.get("global_fraction"),
                          "multiscale": {kk: ms.get(kk) for kk in ("components", "major_cycles", "end", "stop",
                                                                   "sub_minor_loops", "scales", "clipped",
                                                                   "stop_level", "model_flux", "increment_flux",
                                                                   "wall")} if ms else None})  # fmt: skip
        rec[f"cycles_{loop_arm}"] = cyc
    for name, p in pts.items():
        ctrl = {6: ("AT6", "ATM6"), 12: ("AT12", "ATM12")}[
            int(name[-2:] if name.endswith("12") else 6)
        ]
        for cn in ctrl:
            if cn in pts:
                ec = pts[cn]["e_d"]
                p[f"S_{cn}_d1_d3"] = [
                    (e0[d] - p["e_d"][d]) / (e0[d] - ec[d]) for d in range(1, 4)
                ]
    rec["points"] = pts
    eff = {}
    for a, b in (
        ("MS6", "Q6"),
        ("MS12", "Q12"),
        ("ATM6", "AT6"),
        ("ATM12", "AT12"),
        ("MS6", "Q12"),
    ):
        if a in pts and b in pts:
            x = effect(pts[a]["e_d"], pts[b]["e_d"])
            ma, mb = pts[a]["model_abs_error"], pts[b]["model_abs_error"]
            if ma and mb:
                rr = ma[1] / mb[1]
                x["pixel_ratio_d1"] = rr
                x["mechanism"] = ("less pixel error" if rr <= 0.9 else "more pixel error" if rr >= 1.1
                                  else "similar")  # fmt: skip
            eff[f"{a}_vs_{b}"] = x
    rec["effects"] = eff
    if "Q12" in pts:
        rec["more_cycles"] = ("help" if pts["Q12"]["e_d"][1] <= 0.9 * pts["Q6"]["e_d"][1]
                              and not pts["Q12"]["harm"] else "do not help")  # fmt: skip
    if all(x in pts for x in ("Q6", "Q12", "MS6", "MS12")):
        ms_close = [a for a in ("MS6", "MS12") if pts[a]["reading"] == "closes"]
        r6, r12 = eff["MS6_vs_Q6"]["reading"], eff["MS12_vs_Q12"]["reading"]
        if ms_close:
            ans = f"yes: the multi-scale minor cycle closes the loop on O ({ms_close})"
        elif r6.startswith("hurts") and r12.startswith("hurts"):
            ans = "no: multi-scale hurts in this loop"
        elif r6.startswith("helps") or r12.startswith("helps"):
            best = min(
                ("MS6", "MS12"), key=lambda a: eff[f"{a}_vs_Q{a[2:]}"]["ratio_d1"]
            )
            ans = (f"partly: multi-scale helps (d1 {eff[f'{best}_vs_Q{best[2:]}']['ratio_d1']:.3f} x "
                   f"Hogbom's at N {best[2:]}) but does not close")  # fmt: skip
        elif rec["more_cycles"] == "help":
            ans = "the cycle count, not the deconvolver, is the lever"
        else:
            ans = "no: neither the deconvolver nor more cycles moves d1"
        rec["answer"] = ans
        pool = [a for a in ("Q6", "Q12", "MS6", "MS12") if not pts[a]["harm"]] or [
            "Q6",
            "Q12",
            "MS6",
            "MS12",
        ]
        lo = min(pts[a]["e_d"][1] for a in pool)
        ties = [a for a in pool if pts[a]["e_d"][1] - lo <= 0.005]
        best = min(
            ties,
            key=lambda a: (
                np.mean(pts[a]["e_d"][2:4]),
                int(a[-2:] if a.endswith("12") else 6),
            ),
        )
        rec["best_arm"] = best + ("" if not pts[best]["harm"] else " (with harm)")
        bm = {"MS6": "MS6_vs_Q6", "MS12": "MS12_vs_Q12"}.get(best)
        rec["real_arm_warranted"] = bool(
            bm and eff[bm]["reading"].startswith("helps") and not pts[best]["harm"]
        )
    # section 7
    for arm in ("R-MS6", "R-MS12"):
        nn = ARMS[arm]["n"]
        rf = root / "loop" / arm / f"cycle-{nn}" / "info.json"
        if not rf.exists():
            continue
        r0, rx = rd(root / "reuse" / "R0-info.json"), rd(rf)
        m0 = min(r0["solve"]["perdir_converged"][1:])
        m1 = min(rx["solve"]["perdir_converged"][1:])
        amp = rx["solve"]["d3_amp"]
        best = arm[2:]
        rec[arm] = {"R0_min_d1_d3": m0, "RX_min_d1_d3": m1, "lifts": m1 >= m0 + 0.20,
                    "tames_d3": amp["p99"] <= 3 and amp["max"] <= 10,
                    "supported_by_O": pts.get(best, {}).get("reading") in ("closes", "partly"),
                    "RX": rx["solve"], "R-Q6_dd11": rd(root / "reuse" / "R-Q6-final-info.json")["solve"],
                    "cycles": [{kk: ci.get(kk) for kk in ("untrusted_gain_share", "residual_sigma_d1_d3",
                                                          "thermal_sigma", "components_flux")}
                               | {"perdir_converged": (ci.get("solve") or {}).get("perdir_converged")}
                               for ci in (rd(root / "loop" / arm / f"cycle-{j}" / "info.json")
                                          for j in range(nn + 1))]}  # fmt: skip
    write_json(root / "score.json", rec)


# -- post hoc diagnostic A2: where minor cycle S's clipped flux sits ----------------


def spill(root, arms=("ATM12", "MS12"), cycles=(0, 1)):
    """Rerun S on saved residuals (float32 copies, so the record is
    diagnostic only) and locate the clipped flux: in d0, within 16 px of a
    pin box, elsewhere (facet edges)."""
    from scipy import ndimage

    root = Path(root)
    ctx = dd11.masks_ctx(root / "O")
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search = ctx["search"] & (ctx["idx"] > 0)
    psf_img = np.load(root / "psf" / "O.npy")
    b = json.loads((root / "gate" / "gatem.json").read_text())["beam_pixels"]
    pins = np.zeros_like(search)
    st = json.loads((root / "O" / "setup.json").read_text())
    for y, x in st["pins"]:
        pins[max(y - 2, 0) : y + 3, max(x - 2, 0) : x + 3] = True
    near = ndimage.binary_dilation(pins, iterations=16)
    d0 = ctx["idx"] == 0
    rec = {}
    for arm in arms:
        for k in cycles:
            r = np.load(root / "loop" / arm / f"cycle-{k}" / "residual.npy").astype(
                np.float64
            )
            inc, full, _, _ = multiscale(
                r, psf_img, clean_interior, search, b, nscales_used(root)
            )
            out = full - inc
            parts = {"d0": d0, "near_pins": near & ~d0, "other": ~near & ~d0}
            rec[f"{arm}-cycle-{k}"] = {
                "clipped_net": float(out.sum()),
                "clipped_abs": float(np.abs(out).sum()),
                "parts_net": {n: float(out[m].sum()) for n, m in parts.items()},
                "parts_abs": {n: float(np.abs(out[m]).sum()) for n, m in parts.items()},
                "kept_near_pins_net": float(inc[near].sum()),
                "kept_net": float(inc.sum()),
            }
            print(json.dumps(rec[f"{arm}-cycle-{k}"]), flush=True)
    write_json(root / "spill.json", rec)


# -- post hoc diagnostic A3: model flux at the pins, per cycle (zero solves) ---------


def pinflux(root, arms=("MS12", "ATM12", "Q12", "AT12")):
    """Model flux inside each pin box and in the 16 px ring round it, per
    cycle's M_k, against sky O's (no solve, no image)."""
    from scipy import ndimage

    root = Path(root)
    ctx = dd11.masks_ctx(root / "O")
    st = json.loads((root / "O" / "setup.json").read_text())
    sky = np.load(root / "O" / "sky.npy")
    zones = {}
    for i, (y, x) in enumerate(st["pins"]):
        box = np.zeros(sky.shape, bool)
        box[max(y - 2, 0) : y + 3, max(x - 2, 0) : x + 3] = True
        ring = ndimage.binary_dilation(box, iterations=16) & ~box
        zones[f"pin{i}-d{int(ctx['idx'][y, x])}"] = (box, ring)
    rec = {
        "sky": {
            z: [float(sky[b].sum()), float(sky[r].sum())] for z, (b, r) in zones.items()
        }
    }
    for arm in arms:
        rows = []
        models = [np.load(START["O"])]
        for k in range(12):
            f = root / "loop" / arm / f"cycle-{k}" / "next_model.npy"
            if f.exists():
                models.append(np.load(f))
        for k, m in enumerate(models):
            rows.append(
                {
                    z: [float(m[b].sum()), float(m[r].sum())]
                    for z, (b, r) in zones.items()
                }
            )
        rec[arm] = rows
    write_json(root / "pinflux.json", rec)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "reuse":
        reuse(argv[1])
    elif cmd == "setup":
        dd11.setup_gate(argv[1])
    elif cmd == "psf":
        dd11.psf(argv[1], argv[2])
    elif cmd == "gater":
        gater(argv[1], part1_only=len(argv) > 2 and argv[2] == "part1")
    elif cmd == "gatem":
        gatem(argv[1])
    elif cmd == "loop":
        loop(argv[1], argv[2])
    elif cmd == "pinflux":
        pinflux(argv[1])
    elif cmd == "spill":
        spill(argv[1])
    elif cmd == "score":
        score(argv[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
