# SPDX-License-Identifier: MIT
"""DD13: stopping the trusted gains' absorption of the off-axis model gap,
on O (research/dd13-absorb.md).

    python tools/oracles/dd13/dd13.py reuse ROOT        # copy DD12's Q12, AT12 and scores, reuse.json
    python tools/oracles/dd13/dd13.py gater ROOT        # gate R13: Q12's cycle 11 and scored solve
    python tools/oracles/dd13/dd13.py gateuv ROOT       # gate UV: the 1,074 lambda cut
    python tools/oracles/dd13/dd13.py loop ROOT ARM     # QA12 SA12 UV12 QP12 ATP12 ATa3 ATp3 R-<arm>
    python tools/oracles/dd13/dd13.py diag ROOT         # diagnostic D on every scored point
    python tools/oracles/dd13/dd13.py score ROOT        # section 6 and 7 readings

DD7's to DD12's roots are read only; reused files are copied into ROOT.
O (dd8.insert), the setup gate and the PSF are DD12's commands (`dd12.py
setup`, `dd12.py psf`).
"""

import importlib.util
import itertools
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DD12_ROOT = Path("D:/rang/outputs/dd12-20261126")
C_LIGHT = 299792458.0
UV_MIN = 1.0 / (64 * 3.0 * np.pi / (180 * 3600))  # section 5: 1 / (64 px x 3"), lambda
UV_GATE = (0.05, 0.60)  # gate UV: share of the solve weight removed


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd12 = _load("dd12", HERE.parent / "dd12" / "dd12.py")
dd11, dd10 = dd12.dd11, dd12.dd10
dd5, dd4, dd3 = dd12.dd5, dd12.dd4, dd12.dd3
DD7_ROOT = dd10.DD7_ROOT
START = dd10.START


def write_json(path, rec):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    dd10.write_json(path, rec)


# -- the arms (section 5) --------------------------------------------------------------

# images: Q (unit amplitude in cycles 0-1, then g), QA (unit amplitude always),
# SA (cycles 0-1 unit amplitude, then the time-constant amplitude), truth,
# ATa / ATp (one factor of the trusted gains replaced by the truth's).
# solve: gs (the scored solver), uv (the scored solver with the cut), none.
# release: the first cycle whose Hogbom searches the pin boxes (None: never).
# prefix: (DD12 arm, cycles copied whole, the cycle whose solve is reused).
ARMS = {
    "QA12": {"base": "O", "n": 12, "images": "QA", "solve": "gs", "release": None,
             "scored": (6, 12), "prefix": ("Q12", 2, 2)},
    "SA12": {"base": "O", "n": 12, "images": "SA", "solve": "gs", "release": None,
             "scored": (6, 12), "prefix": ("Q12", 2, 2)},
    "QP12": {"base": "O", "n": 12, "images": "QA", "solve": "gs", "release": 2,
             "scored": (6, 12), "prefix": ("Q12", 2, 2)},
    "UV12": {"base": "O", "n": 12, "images": "Q", "solve": "uv", "release": None,
             "scored": (6, 12), "prefix": None},
    "ATP12": {"base": "O", "n": 12, "images": "truth", "solve": "none", "release": 2,
              "scored": (6, 12), "prefix": ("AT12", 2, None)},
    "ATa3": {"base": "O", "n": 3, "images": "ATa", "solve": "gs", "release": None,
             "scored": (3,), "prefix": ("Q12", 0, 0)},
    "ATp3": {"base": "O", "n": 3, "images": "ATp", "solve": "gs", "release": None,
             "scored": (3,), "prefix": ("Q12", 0, 0)},
}  # fmt: skip
for _a in ("QA12", "SA12", "QP12", "UV12"):  # section 7
    ARMS[f"R-{_a}"] = dict(ARMS[_a], base="real", prefix=None)


def time_constant_amplitude(gains, bad):
    """SA12's A-bar: per antenna, direction and hand the median over all
    intervals of the trusted |g|; 1 where no interval is trusted. Returns
    an array broadcastable to `gains` (nint, nfreq, nant, ndir, 2)."""
    a = np.where(bad[..., None], np.nan, np.abs(gains))
    with np.errstate(all="ignore"):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(a, axis=0, keepdims=True)
    return np.where(np.isfinite(med), med, 1.0)


def image_gains(rule, gains, flags, truth, cyc):
    """The image gains of one cycle (section 5) and the untrusted mask."""
    if rule == "truth":
        return truth, None
    bad = dd11.untrusted(gains, flags)
    unit = gains / np.abs(gains)
    if rule == "QA" or (rule in ("Q", "SA") and cyc < 2):
        g = unit
    elif rule == "Q":
        g = gains
    elif rule == "SA":
        g = time_constant_amplitude(gains, bad) * unit
    elif rule == "ATa":
        g = np.abs(truth) * unit
    elif rule == "ATp":
        g = np.abs(gains) * truth / np.abs(truth)
    else:
        raise ValueError(rule)
    sub = truth if rule in ("ATa", "ATp") else 1.0 + 0j
    return np.where(bad[..., None], sub, g), bad


def uv_cut(c, uv_min=UV_MIN):
    """(rows, chans) True where |uv| x nu / c < uv_min (UV12's cut)."""
    uvd = np.hypot(c["UVW"][:, 0], c["UVW"][:, 1])
    return uvd[:, None] * (np.asarray(c["freq"])[None, :] / C_LIGHT) < uv_min


def cut_ctx(ctx, cut):
    c = dict(ctx["c"], FLAG=np.asarray(ctx["c"]["FLAG"], bool) | cut[:, :, None])
    return dict(ctx, c=c)


def unflagged(c):
    return ~(
        np.asarray(c["FLAG"], bool).any(-1) | np.asarray(c["FLAG_ROW"], bool)[:, None]
    )


# -- reuse (section 3) -----------------------------------------------------------------


def reuse(root):
    root = Path(root)
    pairs = []
    for k in range(13):
        for f in ("info.json", "gains.npz", "next_model.npy"):
            pairs.append((f"loop/Q12/cycle-{k}/{f}", f"loop/Q12/cycle-{k}/{f}"))
            pairs.append((f"loop/AT12/cycle-{k}/{f}", f"loop/AT12/cycle-{k}/{f}"))
    pairs += [("score.json", "reuse/dd12-score.json"),
              ("reuse/dd11-score.json", "reuse/dd11-score.json"),
              ("reuse/dd10-score.json", "reuse/dd10-score.json"),
              ("reuse/psf-O.json", "reuse/psf-O.json"),
              ("reuse/psf-real.json", "reuse/psf-real.json"),
              ("reuse/R0-gains.npz", "reuse/R0-gains.npz"),
              ("reuse/R0-info.json", "reuse/R0-info.json"),
              ("reuse/R-Q6-final-info.json", "reuse/R-Q6-final-info.json")]  # fmt: skip
    rec = {}
    for src, dst in pairs:
        s, d = DD12_ROOT / src, root / dst
        if not s.exists():
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        if not d.exists():
            shutil.copy2(s, d)
        rec[dst] = {
            "from": str(s),
            "sha256": dd11.sha_file(d),
            "source_sha256": dd11.sha_file(s),
        }
        assert rec[dst]["sha256"] == rec[dst]["source_sha256"]
    write_json(root / "reuse.json", rec)


# -- gates (section 5) -----------------------------------------------------------------


def gater(root):
    root = Path(root)
    ctx = dd10.base_ctx(root, "O")
    c = ctx["c"]
    psf_img = np.load(root / "psf" / "O.npy")
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search = ctx["search"] & (ctx["idx"] > 0)
    q = root / "loop" / "Q12"
    rec = {}
    t0 = time.perf_counter()
    z = np.load(q / "cycle-11" / "gains.npz")
    m11 = np.load(q / "cycle-10" / "next_model.npy")
    models = dd4.facet_models(ctx, m11)
    ig, _ = image_gains("Q", z["gains"], z["flags"], None, 11)
    resid = dd10.residual_image(ctx, models, ig, c["w_I"])
    comps, _, hinfo = dd11.hogbom_fast(resid, psf_img, clean_interior, search)
    m12 = dd3.add_components(m11, comps)
    m12_ref = np.load(q / "cycle-11" / "next_model.npy")
    rec["cycle11_next_model_bitwise"] = bool(np.array_equal(m12, m12_ref))
    rec["cycle11_max_abs_diff"] = float(np.abs(m12 - m12_ref).max())
    rec["cycle11_hogbom"] = hinfo
    rec["seconds_1"] = time.perf_counter() - t0
    del models
    t1 = time.perf_counter()
    models = dd4.facet_models(ctx, m12_ref)
    sol = dd11.solve_cycle(ctx, models, "gs", second=False)["sol"]
    g12 = np.load(q / "cycle-12" / "gains.npz")
    rec["cycle12_gains_bitwise"] = bool(
        np.array_equal(np.asarray(sol.gains), g12["gains"])
    )
    rec["cycle12_flags_bitwise"] = bool(
        np.array_equal(np.asarray(sol.flags), g12["flags"])
    )
    rec["cycle12_iterations"] = sol.iterations
    rec["seconds_2"] = time.perf_counter() - t1
    rec["R13_pass"] = bool(
        rec["cycle11_next_model_bitwise"]
        and rec["cycle12_gains_bitwise"]
        and rec["cycle12_flags_bitwise"]
    )
    write_json(root / "gate" / "gater.json", rec)


def gateuv(root):
    root = Path(root)
    ctx = dd10.base_ctx(root, "O")
    c = ctx["c"]
    cut = uv_cut(c)
    ok = unflagged(c)
    w = np.asarray(c["WEIGHT_SPECTRUM"], np.float64)[..., [0, 3]].sum(-1)
    w = np.where(ok, w, 0.0)
    share = float(w[cut].sum() / w.sum())
    keep = (ok & ~cut).any(1)  # rows with an unflagged cell after the cut
    block, a1, a2 = ctx["block"], c["ANTENNA1"], c["ANTENNA2"]
    nint, nant = int(block.max()) + 1, len(c["ant_names"])
    has = np.zeros((nint, nant), bool)
    has[block[keep], a1[keep]] = True
    has[block[keep], a2[keep]] = True
    had = np.zeros((nint, nant), bool)
    rows = ok.any(1)
    had[block[rows], a1[rows]] = True
    had[block[rows], a2[rows]] = True
    lost = int((had & ~has).sum())
    rec = {"uv_min_lambda": UV_MIN, "weight_share_removed": share,
           "cells_cut": int((cut & ok).sum()), "cells_unflagged": int(ok.sum()),
           "antenna_intervals_losing_all_data": lost,
           "pass": bool(UV_GATE[0] <= share <= UV_GATE[1] and lost == 0)}  # fmt: skip
    write_json(root / "gate" / "gateuv.json", rec)


# -- the loops (sections 4 and 5) ------------------------------------------------------


def _prefix(root, arm, spec):
    """Copy the shared prefix (section 3) into the arm's directory."""
    if spec["prefix"] is None:
        return
    src_arm, whole, solve_at = spec["prefix"]
    src = root / "loop" / src_arm
    out = root / "loop" / arm
    for k in range(whole):
        d = out / f"cycle-{k}"
        if (d / "info.json").exists():
            continue
        d.mkdir(parents=True, exist_ok=True)
        for f in ("gains.npz", "next_model.npy", "info.json"):
            if (src / f"cycle-{k}" / f).exists():
                shutil.copy2(src / f"cycle-{k}" / f, d / f)
    if solve_at is not None:
        d = out / f"cycle-{solve_at}"
        if not (d / "info.json").exists():
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / f"cycle-{solve_at}" / "gains.npz", d / "reuse_gains.npz")
            shutil.copy2(src / f"cycle-{solve_at}" / "info.json", d / "reuse_info.json")


def _effect_vs(root, e, n):
    """Section 4's stage stop: the arm's M_6 point against Q6."""
    q = json.loads((root / "loop" / "Q12" / f"cycle-{n}" / "info.json").read_text())
    return dd12.effect(e, q["solve"]["e_d"])


def loop(root, arm):
    """Resumable per cycle. A cycle directory with info.json is kept; one
    with reuse_gains.npz takes that solve."""
    root = Path(root)
    spec = ARMS[arm]
    base, n = spec["base"], spec["n"]
    _prefix(root, arm, spec)
    ctx = dd10.base_ctx(root, base)
    c = ctx["c"]
    k = float(json.loads((DD7_ROOT / "b" / "setup.json").read_text())["dd5"]["k"])
    psf_img = np.load(root / "psf" / f"{base}.npy")
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search_pinned = ctx["search"] & (ctx["idx"] > 0)
    sky = np.load(root / "O" / "sky.npy") if base == "O" else None
    truth = np.load(root / "O" / "truth.npz")["gains"][:, None] if base == "O" else None
    cctx = None
    if spec["solve"] == "uv":
        cut = uv_cut(c)
        cctx = cut_ctx(ctx, cut)
    model = np.load(START[base])
    out = root / "loop" / arm
    for cyc in range(n + 1):
        d = out / f"cycle-{cyc}"
        if (out / "stopped.json").exists():
            print(f"{arm}: stopped at the stage rule", flush=True)
            return
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
        gains = flags = None
        d.mkdir(parents=True, exist_ok=True)
        if (d / "reuse_gains.npz").exists():
            z = np.load(d / "reuse_gains.npz")
            gains, flags = z["gains"], z["flags"]
            info["solve"] = json.loads((d / "reuse_info.json").read_text())["solve"]
            info["solve_reused_from"] = str(d / "reuse_gains.npz")
            np.savez_compressed(d / "gains.npz", **{key: z[key] for key in z.files})
        elif base == "real" and cyc == 0 and spec["solve"] == "gs":
            z = np.load(root / "reuse" / "R0-gains.npz")
            gains, flags = z["gains"], z["flags"]
            info["solve"] = json.loads((root / "reuse" / "R0-info.json").read_text())[
                "solve"
            ]
            info["solve_reused_from"] = str(root / "reuse" / "R0-gains.npz")
            np.savez_compressed(d / "gains.npz", **{key: z[key] for key in z.files})
        else:
            save = {}
            # the loop's own solve: the cut solve (UV, non-final), else the scored solver
            if spec["solve"] == "uv" and not final:
                res = dd11.solve_cycle(cctx, models, "gs", second=False)
                sol = res["sol"]
                gains, flags = np.asarray(sol.gains), np.asarray(sol.flags)
                srec, _ = dd10.scores(ctx, models, sol, None, k)
                info["cut_solve"] = srec
                info["seconds_cut_solve"] = res["seconds_solve"]
                save.update(gains=gains, flags=flags)
                del res
            if spec["solve"] == "gs" or scored:
                res = dd11.solve_cycle(ctx, models, "gs", second=scored)
                sol = res["sol"]
                srec, conv = dd10.scores(ctx, models, sol, res.get("sol2"), k)
                info["solve"] = srec
                info["seconds_solve"] = res["seconds_solve"]
                info["seconds_second"] = res.get("seconds_second")
                sg, sf = np.asarray(sol.gains), np.asarray(sol.flags)
                if spec["solve"] == "uv":
                    save.update(scored_gains=sg, scored_flags=sf)
                    pre = "scored_"
                else:
                    gains, flags = sg, sf
                    save.update(gains=sg, flags=sf)
                    pre = ""
                if "sol2" in res:
                    save[pre + "gains2"] = np.asarray(res["sol2"].gains)
                    save[pre + "flags2"] = np.asarray(res["sol2"].flags)
                    save[pre + "converged"] = conv
                del res
            if save:
                np.savez_compressed(d / "gains.npz", **save)
            if gains is None and "scored_gains" in save:  # real UV12's final residual
                gains, flags = save["scored_gains"], save["scored_flags"]
        if not final or base == "real":
            t1 = time.perf_counter()
            rule = spec["images"]
            if final:  # real only: the final residual for the reported rms, rule U
                rule = "Q"
            ig, bad = image_gains(rule, gains, flags, truth, cyc if not final else 99)
            if bad is not None:
                info["untrusted_gain_share"] = [
                    float(bad[..., f].mean()) for f in range(4)
                ]
            info["image_rule"] = rule
            resid = dd10.residual_image(ctx, models, ig, c["w_I"])
            info["seconds_image"] = time.perf_counter() - t1
            info["residual_sigma_d1_d3"] = dd10.mad_sigma(resid, clean_interior)
            info["thermal_sigma"] = dd10.thermal_sigma(ctx, c["w_I"], k)
            if not final:
                release = spec["release"] is not None and cyc >= spec["release"]
                search = clean_interior if release else search_pinned
                info["pins_released"] = bool(release)
                t2 = time.perf_counter()
                comps, _, hinfo = dd11.hogbom_fast(
                    resid, psf_img, clean_interior, search
                )
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
        if base == "O" and cyc == 6 and n == 12 and not final and arm != "ATP12":
            eff = _effect_vs(root, info["solve"]["e_d"], 6)
            if eff["reading"].startswith("hurts"):
                write_json(out / "stopped.json", {"cycle": 6, "effect_vs_Q6": eff})
                return


# -- diagnostic D (section 6) ----------------------------------------------------------


def pair_lengths(ctx):
    """Mean projected baseline length (m) per antenna pair, triu order."""
    c = ctx["c"]
    nant = len(c["ant_names"])
    p, q = np.triu_indices(nant, 1)
    a1, a2 = (
        np.minimum(c["ANTENNA1"], c["ANTENNA2"]),
        np.maximum(c["ANTENNA1"], c["ANTENNA2"]),
    )
    key = a1 * nant + a2
    L = np.hypot(c["UVW"][:, 0], c["UVW"][:, 1])
    s = np.bincount(key, L, nant * nant)
    m = np.bincount(key, None, nant * nant)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = s / m
    return mean[p * nant + q]


def bias_by_length(gains, flags, truth, lengths, d=1, bins=(0, 500, 2000, np.inf)):
    g, f = gains[:, 0], flags[:, 0]
    nant = g.shape[1]
    p, q = np.triu_indices(nant, 1)
    P = g[:, p, d] * np.conj(g[:, q, d])
    T = truth[:, p, d] * np.conj(truth[:, q, d])
    ok = (f[:, p, d] == 0) & (f[:, q, d] == 0)
    out = []
    for lo, hi in itertools.pairwise(bins):
        sel = ok & ((lengths >= lo) & (lengths < hi))[None]
        r = (np.abs(P) / np.abs(T))[sel] - 1
        out.append({"from_m": lo, "to_m": None if np.isinf(hi) else hi, "cells": int(r.size),
                    "amp_bias": float(np.median(r)) if r.size else None})  # fmt: skip
    return out


def _scored_gains(path):
    z = np.load(path)
    if "scored_gains" in z.files:
        return z["scored_gains"], z["scored_flags"]
    return z["gains"], z["flags"]


def diag(root):
    root = Path(root)
    ctx = dd10.base_ctx(root, "O")
    lengths = pair_lengths(ctx)
    truth = np.load(root / "O" / "truth.npz")["gains"]
    srcs = {"A0": ("Q12", 0), "Q6": ("Q12", 6), "Q12": ("Q12", 12), "AT6": ("AT12", 6),
            "AT12": ("AT12", 12)}  # fmt: skip
    for arm, spec in ARMS.items():
        if spec["base"] != "O":
            continue
        for s in spec["scored"]:
            srcs[f"{arm[:-2] if arm.endswith('12') else arm[:-1]}{s}"] = (arm, s)
    rec = {}
    for name, (arm, cyc) in srcs.items():
        f = root / "loop" / arm / f"cycle-{cyc}" / "gains.npz"
        if not f.exists():
            continue
        g, fl = _scored_gains(f)
        rec[name] = dd11.gain_errors(g, fl, truth)
        rec[name]["d1_bias_by_length"] = bias_by_length(g, fl, truth, lengths)
        rec[name]["source"] = str(f)
    write_json(root / "diag.json", rec)


# -- readings (sections 6 and 7) -------------------------------------------------------


def _point(root, arm, cyc):
    f = Path(root) / "loop" / arm / f"cycle-{cyc}" / "info.json"
    if not f.exists():
        return None
    s = json.loads(f.read_text()).get("solve") or {}
    return s if "e_d" in s and "perdir_converged" in s else None


def score(root):
    root = Path(root)
    rd = lambda p: json.loads(Path(p).read_text())
    d10 = rd(root / "reuse" / "dd10-score.json")
    d11 = rd(root / "reuse" / "dd11-score.json")
    e0, ex = d10["A0"]["e_d"], d10["AX"]["e_d"]
    e_at3, e_ats3 = d10["AT"]["final"]["e_d"], d11["ATs"]["final"]["e_d"]
    diag_rec = rd(root / "diag.json") if (root / "diag.json").exists() else {}
    rec = {"references": {"A0": e0, "AX": ex, "AT3": e_at3, "ATs3": e_ats3}}
    pts = {}
    names = {"Q": "Q12", "AT": "AT12", "QA": "QA12", "SA": "SA12", "QP": "QP12", "UV": "UV12",
             "ATP": "ATP12"}  # fmt: skip
    for short, arm in names.items():
        for nn in (6, 12):
            s = _point(root, arm, nn)
            if s is not None:
                pts[f"{short}{nn}"] = s
    for arm in ("ATa3", "ATp3"):
        s = _point(root, arm, 3)
        if s is not None:
            pts[arm] = s
    for name, s in pts.items():
        G, harm, r = dd11.reading(s["e_d"], e0, ex)
        s.update(G_d1_d3=G, harm=harm, reading=r)
        dg = diag_rec.get(name)
        if dg:
            s["diag"] = dg
        nn = 12 if name.endswith("12") else 6 if name.endswith("6") else None
        if nn and f"Q{nn}" in pts and f"AT{nn}" in pts:
            eq, ea = pts[f"Q{nn}"]["e_d"][1], pts[f"AT{nn}"]["e_d"][1]
            s["Gamma"] = (eq - s["e_d"][1]) / (eq - ea)
    rec["points"] = {k: {kk: v.get(kk) for kk in ("e_d", "e_d_converged", "G_d1_d3", "harm", "reading", "Gamma",
                                                   "e_over_ehat", "perdir_converged", "d3_amp", "diag")}
                     for k, v in pts.items()}  # fmt: skip
    eff = {}
    for a in ("QA", "SA", "QP", "UV"):
        for nn in (6, 12):
            if f"{a}{nn}" in pts and f"Q{nn}" in pts:
                eff[f"{a}{nn}_vs_Q{nn}"] = dd12.effect(
                    pts[f"{a}{nn}"]["e_d"], pts[f"Q{nn}"]["e_d"]
                )
    for nn in (6, 12):
        if f"QP{nn}" in pts and f"QA{nn}" in pts:
            eff[f"QP{nn}_vs_QA{nn}"] = dd12.effect(
                pts[f"QP{nn}"]["e_d"], pts[f"QA{nn}"]["e_d"]
            )
        if f"ATP{nn}" in pts and f"AT{nn}" in pts:
            eff[f"ATP{nn}_vs_AT{nn}"] = dd12.effect(
                pts[f"ATP{nn}"]["e_d"], pts[f"AT{nn}"]["e_d"]
            )
    rec["effects"] = eff
    # final N per arm (a stopped arm is read at 6)
    final = {}
    for a in ("QA", "SA", "QP", "UV"):
        if f"{a}12" in pts:
            final[a] = 12
        elif f"{a}6" in pts and (root / "loop" / f"{a}12" / "stopped.json").exists():
            final[a] = 6
    rec["final_N"] = final

    def bias(name):
        dg = diag_rec.get(name)
        return dg["amp_bias"][0] if dg else None

    absorb = {}
    for a, nn in final.items():
        b, bq = bias(f"{a}{nn}"), bias(f"Q{nn}")
        if b is not None and bq is not None:
            absorb[a] = {"b_d1": b, "b_d1_Q": bq, "reduced": abs(b) <= 0.5 * abs(bq)}
    rec["absorption"] = absorb
    # split controls
    split = {}
    for arm, lab in (("ATa3", "amplitudes"), ("ATp3", "phases")):
        if arm in pts:
            S = (e_ats3[1] - pts[arm]["e_d"][1]) / (e_ats3[1] - e_at3[1])
            r = (f"the absorption sits in the trusted {lab}" if S >= 0.8 else f"not mainly in the {lab}"
                 if S < 0.5 else f"partly in the {lab}")  # fmt: skip
            split[arm] = {"S": S, "reading": r}
    rec["split"] = split
    # pin
    if "QP" in final:
        nn = final["QP"]
        k1 = eff.get(f"QP{nn}_vs_QA{nn}", {}).get("reading", "")
        k2 = eff.get("ATP12_vs_AT12", {}).get("reading", "")
        rec["pin"] = ("the pin limits the loop" if k1.startswith("helps") or k2.startswith("helps") else
                      "releasing the pin hurts" if k1.startswith("hurts") or k2.startswith("hurts") else
                      "the pin does not limit")  # fmt: skip
    # answer
    if len(final) == 4:
        fin = {a: pts[f"{a}{nn}"] for a, nn in final.items()}
        closes = [a for a, s in fin.items() if s["reading"] == "closes"]
        helps = [a for a, nn in final.items() if eff[f"{a}{nn}_vs_Q{nn}"]["reading"].startswith("helps")
                 and not fin[a]["harm"]]  # fmt: skip
        reduced = [a for a, x in absorb.items() if x["reduced"]]
        pool = [a for a in fin if not fin[a]["harm"]]
        cand = {"Q": pts["Q12"]} | {a: fin[a] for a in pool if final[a] == 12}
        lo = min(s["e_d"][1] for s in cand.values())
        ties = [a for a, s in cand.items() if s["e_d"][1] - lo <= 0.005]
        best = min(ties, key=lambda a: (np.mean(cand[a]["e_d"][2:4]), a != "Q"))
        rec["best_arm"] = "Q12" if best == "Q" else f"{best}12"
        if closes:
            x = min(closes, key=lambda a: fin[a]["e_d"][1])
            ans = f"yes: {x}{final[x]} stops the absorption and the loop from solved gains closes on O"
        elif helps:
            x = min(helps, key=lambda a: fin[a]["e_d"][1])
            ans = (f"partly: {x}{final[x]} closes Gamma {fin[x].get('Gamma', float('nan')):.3f} of the "
                   f"Q-to-AT gap (absorption {'reduced' if absorb.get(x, {}).get('reduced') else 'not reduced'})")  # fmt: skip
        elif reduced:
            ans = "absorption reduced, gap not closed: the amplitude bias is not what holds d1"
        else:
            ans = "no: none of the tested constraints stops the absorption"
        rec["answer"] = ans
        rec["real_arm_warranted"] = bool(
            best != "Q"
            and eff[f"{best}12_vs_Q12"]["reading"].startswith("helps")
            and not cand[best]["harm"]
        )
    # section 7
    for arm in ("R-QA12", "R-SA12", "R-QP12", "R-UV12"):
        rf = root / "loop" / arm / "cycle-12" / "info.json"
        if not rf.exists():
            continue
        r0, rx = rd(root / "reuse" / "R0-info.json"), rd(rf)
        m0 = min(r0["solve"]["perdir_converged"][1:])
        m1 = min(rx["solve"]["perdir_converged"][1:])
        amp = rx["solve"]["d3_amp"]
        rec[arm] = {"R0_min_d1_d3": m0, "RX_min_d1_d3": m1, "lifts": m1 >= m0 + 0.20,
                    "tames_d3": amp["p99"] <= 3 and amp["max"] <= 10,
                    "supported_by_O": pts.get(arm[2:-2] + "12", {}).get("reading") in ("closes", "partly"),
                    "RX": rx["solve"]}  # fmt: skip
    # per-cycle records
    for arm in list(names.values()) + ["ATa3", "ATp3"]:
        cyc = []
        for k in range(13):
            f = root / "loop" / arm / f"cycle-{k}" / "info.json"
            if not f.exists():
                break
            ci = json.loads(f.read_text())
            sv, cs = ci.get("solve") or {}, ci.get("cut_solve") or {}
            cyc.append({kk: ci.get(kk) for kk in ("model_error", "hogbom", "components_flux", "untrusted_gain_share",
                                                  "residual_sigma_d1_d3", "image_rule", "pins_released")}
                       | {"e_d": sv.get("e_d"), "e_d_cut_solve": cs.get("e_d"),
                          "global_fraction": sv.get("global_fraction")})  # fmt: skip
        rec[f"cycles_{arm}"] = cyc
    write_json(root / "score.json", rec)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    fn = {
        "reuse": reuse,
        "gater": gater,
        "gateuv": gateuv,
        "diag": diag,
        "score": score,
    }
    if cmd in fn:
        fn[cmd](argv[1])
    elif cmd == "loop":
        loop(argv[1], argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
