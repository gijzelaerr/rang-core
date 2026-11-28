# SPDX-License-Identifier: MIT
"""DD15: releasing the pins only where the nominal beam is high
(research/dd15-beam-gate.md).

    python tools/oracles/dd15/dd15.py build ROOT        # DD14's rebuild of OB and gate GB15
    python tools/oracles/dd15/dd15.py gater ROOT        # gate R15 a-c
    python tools/oracles/dd15/dd15.py loop ROOT ARM     # QPG12 ATG12 QPG12-O R-QPG12
    python tools/oracles/dd15/dd15.py score ROOT        # sections 5 and 6
    python tools/oracles/dd15/dd15.py realprep ROOT     # the real PSF and gate R15 d
    python tools/oracles/dd15/dd15.py real ROOT         # section 7's flux reading

DD7's, DD8's and DD11-DD14's roots are read only.
"""

import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DD14_ROOT = Path("D:/rang/outputs/dd14-20261127")
DD13_ROOT = Path("D:/rang/outputs/dd13-20261127")
DD12_ROOT = Path("D:/rang/outputs/dd12-20261126")
DD11_ROOT = Path("D:/rang/outputs/dd11-20261126")

THRESH = 0.5  # section 2 (frozen)
TOL = 0.05  # section 6
N, SCORED = 12, (6, 12)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd14 = _load("dd14", HERE.parent / "dd14" / "dd14.py")
dd13, dd12, dd11, dd10 = dd14.dd13, dd14.dd12, dd14.dd11, dd14.dd10
dd4, dd3, dd2 = dd14.dd4, dd14.dd3, dd14.dd2
DD7_ROOT = dd14.DD7_ROOT


def write_json(path, rec):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    dd10.write_json(path, rec)


def sha_file(path):
    return dd14.sha_file(path)


def _rd(p):
    return json.loads(Path(p).read_text())


# -- the gated rule (sections 2 and 4; unit-tested) -------------------------------------


def high_facets(bnom_geom, thresh=THRESH):
    """True per direction where B_nom >= thresh (d0's B_nom is 1)."""
    return np.asarray(bnom_geom, float) >= thresh


def image_gains_qg(gains, flags, cyc, amp, bnom_geom, thresh=THRESH):
    """QG: sqrt(amp_f) g/|g| in high facets every cycle and in low facets in
    cycles 0-1, the solved g in low facets from cycle 2; untrusted ->
    sqrt(amp_f). `amp` is B_nom on OB and 1 in the real form; the partition
    comes from the geometry's B_nom."""
    bad = dd11.untrusted(gains, flags)
    sb = np.sqrt(np.asarray(amp, float))[None, None, None, :, None]
    g = sb * (gains / np.abs(gains))
    if cyc >= 2:
        low = ~high_facets(bnom_geom, thresh)
        g = np.where(low[None, None, None, :, None], gains, g)
    sub = np.broadcast_to(sb + 0j, gains.shape)
    return np.where(bad[..., None], sub, g), bad


def search_mask(clean_interior, search_pinned, idx, high, release):
    """The Högbom search pixels: pins excluded, except in high facets once released."""
    if not release:
        return search_pinned
    rel = np.isin(idx, np.nonzero(np.asarray(high))[0])
    return search_pinned | (clean_interior & rel)


# -- the readings (section 6; unit-tested) ----------------------------------------------


def effect15(x, q, c):
    """Effect against Q with DD15's d3 clause. x, q, c: dicts with e_sr and e_d
    (index 1-3 = d1-d3); c is the arm's matched truth control."""
    r = x["e_sr"][1] / q["e_sr"][1]
    w2 = x["e_sr"][2] > 1.2 * q["e_sr"][2]
    w3 = x["e_d"][3] > 1.2 * max(q["e_d"][3], c["e_d"][3])
    worse = w2 or w3
    if r >= 1.1 or worse:
        lab = "hurts" + (" (marginal)" if (not worse and r < 1.12) else "")
    elif r <= 0.9:
        lab = "helps" + (" (marginal)" if r > 0.88 else "")
    else:
        lab = "no effect"
    return {"ratio_d1": r, "d2_worse": bool(w2), "d3_worse": bool(w3), "reading": lab}


def criteria(p, q, c, kpin_q3, readable):
    """G, F and the answer row (1 in, 2 in for d1-d2, 0 out) at one N."""
    eff = effect15(p, q, c)
    G = p["reading_sr"] in ("closes", "partly") and eff["reading"].startswith("helps")
    k = p["kappa_pin"]
    f12 = all(abs(p["s"][f] - 1) <= TOL and abs(k[f - 1]) <= TOL and readable[f - 1]
              for f in (1, 2))  # fmt: skip
    f3 = abs(k[2]) <= TOL and readable[2]
    row = 0
    if G and f12 and f3:
        row = 1
    elif G and f12 and readable[2] and abs(k[2]) <= abs(kpin_q3) + TOL:
        row = 2
    return {"effect_vs_Q": eff, "G": bool(G), "F_d1_d2": bool(f12), "F_d3": bool(f3),
            "F": bool(f12 and f3), "row": row}  # fmt: skip


def answer(rows, stopped=False):
    if stopped or not rows or min(rows) == 0:
        return "out: the pinned rule stays in the recipe"
    if all(r == 1 for r in rows):
        return "in: the beam-gated rule goes into the real DD recipe, subject to section 7's real check"
    return "in for d1-d2, d3 a known limitation: the gate holds the high facets; subject to section 7 for d1-d2"


# -- build and gates (section 3) --------------------------------------------------------


def build(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    dd14.beam(root)
    mine, ref = np.load(root / "beam.npz"), np.load(DD14_ROOT / "beam.npz")
    beam_eq = {k: bool(np.array_equal(mine[k], ref[k])) for k in ref.files}
    dd14.apertures(root)
    ap_eq = (
        _rd(root / "apertures.json")["apertures"]
        == _rd(DD14_ROOT / "apertures.json")["apertures"]
    )
    dd14.gateo(root)
    dd14.insert(root)
    dd14.psf(root)
    tr = np.load(root / "O" / "truth.npz")["gains"]
    tr14 = np.load(DD14_ROOT / "O" / "truth.npz")["gains"]
    rec = {"rule": "research/dd15-beam-gate.md section 3",
           "GB1": _rd(root / "gate" / "GB1.json")["pass"],
           "GB23": _rd(root / "gate" / "GB23.json"),
           "GB4": _rd(root / "gate" / "GB4.json")["pass"],
           "beam_arrays_bitwise": beam_eq, "apertures_equal_dd14": bool(ap_eq),
           "truth_bitwise": bool(np.array_equal(tr, tr14)),
           "sky_sha256": sha_file(root / "O" / "sky.npy"),
           "dd14_sky_sha256": sha_file(DD14_ROOT / "O" / "sky.npy"),
           "seconds": time.perf_counter() - t0}  # fmt: skip
    g = rec["GB23"]
    rec["pass"] = bool(rec["GB1"] and g["GB2_pass"] and g["GB3_pass"] and rec["GB4"]
                       and all(beam_eq.values()) and ap_eq and rec["truth_bitwise"]
                       and rec["sky_sha256"] == rec["dd14_sky_sha256"])  # fmt: skip
    write_json(root / "gate" / "GB15.json", rec)
    if not rec["pass"]:
        raise SystemExit("GB15 failed")


def _ctx(root, base):
    root = Path(root)
    if base == "OB":
        return dd10.base_ctx(root, "O")
    if base == "O":
        run = root / "gate" / "O"
        ctx = dd4.context(run, ti=dd10.TI)
        ctx["run"] = run
        return ctx
    return dd10.base_ctx(root, "real")


def _one_cycle(ctx, psf_img, model, gains, flags, cyc, amp, bnom_geom, thresh, release):
    c = ctx["c"]
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search_pinned = ctx["search"] & (ctx["idx"] > 0)
    models = dd4.facet_models(ctx, model)
    ig, _ = image_gains_qg(gains, flags, cyc, amp, bnom_geom, thresh)
    resid = dd10.residual_image(ctx, models, ig, c["w_I"])
    high = high_facets(bnom_geom, thresh)
    search = search_mask(clean_interior, search_pinned, ctx["idx"], high, release)
    comps, _, hinfo = dd11.hogbom_fast(resid, psf_img, clean_interior, search)
    return dd3.add_components(model, comps), hinfo


def _check(root, base, src, cyc, amp, bnom_geom, thresh, release):
    ctx = _ctx(root, base)
    psf_img = np.load(Path(root) / "psf" / ("real.npy" if base == "real" else "O.npy"))
    z = np.load(src / f"cycle-{cyc}" / "gains.npz")
    m = np.load(src / f"cycle-{cyc - 1}" / "next_model.npy")
    ref = np.load(src / f"cycle-{cyc}" / "next_model.npy")
    t0 = time.perf_counter()
    out, hinfo = _one_cycle(ctx, psf_img, m, z["gains"], z["flags"], cyc, amp, bnom_geom,
                            thresh, release)  # fmt: skip
    return {"source": str(src), "cycle": cyc, "threshold": thresh, "bitwise": bool(np.array_equal(out, ref)),
            "max_abs_diff": float(np.abs(out - ref).max()), "hogbom": hinfo,
            "seconds": time.perf_counter() - t0}  # fmt: skip


def gater(root):
    """Gate R15 a-c (section 3)."""
    root = Path(root)
    bnom = np.load(root / "beam.npz")["b_nom"]
    one = np.ones(4)
    rec = {"a": _check(root, "OB", DD14_ROOT / "loop" / "QPN12", 11, bnom, bnom, 0.0, True),
           "b": _check(root, "OB", DD14_ROOT / "loop" / "QPN12", 1, bnom, bnom, THRESH, False),
           "c": _check(root, "O", DD13_ROOT / "loop" / "QP12", 1, one, bnom, THRESH, False)}  # fmt: skip
    rec["R15_pass"] = all(rec[k]["bitwise"] for k in "abc")
    write_json(root / "gate" / "R15.json", rec)
    if not rec["R15_pass"]:
        raise SystemExit("R15 failed")


def realprep(root):
    """The real PSF (peak against DD13's) and gate R15 d."""
    root = Path(root)
    dd10.psf(root, "real")
    peak = _rd(root / "psf" / "real.json")["peak"]
    ref = _rd(DD13_ROOT / "psf" / "real.json")["peak"]
    bnom = np.load(root / "beam.npz")["b_nom"]
    d = _check(
        root, "real", DD13_ROOT / "loop" / "R-QP12", 1, np.ones(4), bnom, THRESH, False
    )
    rec = {"psf_peak": peak, "dd13_psf_peak": ref, "psf_pass": abs(peak - ref) <= 1e-9 * abs(ref),
           "d": d}  # fmt: skip
    rec["pass"] = bool(rec["psf_pass"] and d["bitwise"])
    write_json(root / "gate" / "R15d.json", rec)
    if not rec["pass"]:
        raise SystemExit("R15 d failed")


# -- the loops (section 4) --------------------------------------------------------------

ARMS = {
    "QPG12": {"base": "OB", "images": "QG", "solve": "gs", "prefix": (DD14_ROOT, "QPN12", 2, 2)},
    "ATG12": {"base": "OB", "images": "truth", "solve": "none", "prefix": (DD14_ROOT, "AT12", 2, None)},
    "QPG12-O": {"base": "O", "images": "QG", "solve": "gs", "prefix": (DD13_ROOT, "QP12", 2, 2)},
    "R-QPG12": {"base": "real", "images": "QG", "solve": "gs", "prefix": (DD13_ROOT, "R-QP12", 2, 2)},
}  # fmt: skip


def _prefix(root, arm, spec):
    src_root, src_arm, whole, solve_at = spec["prefix"]
    src, out = src_root / "loop" / src_arm, root / "loop" / arm
    reuse_f = root / "reuse.json"
    reuse = _rd(reuse_f) if reuse_f.exists() else {}
    rec = reuse.setdefault(arm, {})
    for k in range(whole):
        d = out / f"cycle-{k}"
        if (d / "info.json").exists():
            continue
        assert (src / f"cycle-{k}" / "info.json").exists(), f"{src} cycle {k} missing"
        d.mkdir(parents=True, exist_ok=True)
        for fn in ("gains.npz", "next_model.npy", "info.json"):
            if (src / f"cycle-{k}" / fn).exists():
                shutil.copy2(src / f"cycle-{k}" / fn, d / fn)
                rec[f"cycle-{k}/{fn}"] = {"from": str(src / f"cycle-{k}" / fn),
                                          "sha256": sha_file(d / fn)}  # fmt: skip
    if solve_at is not None:
        d = out / f"cycle-{solve_at}"
        if not (d / "info.json").exists() and not (d / "reuse_gains.npz").exists():
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / f"cycle-{solve_at}" / "gains.npz", d / "reuse_gains.npz")
            shutil.copy2(src / f"cycle-{solve_at}" / "info.json", d / "reuse_info.json")
            rec[f"cycle-{solve_at}/reuse_gains.npz"] = {
                "from": str(src / f"cycle-{solve_at}" / "gains.npz"),
                "sha256": sha_file(d / "reuse_gains.npz")}  # fmt: skip
    write_json(reuse_f, reuse)


def _wait_for(paths, poll=60, limit=12 * 3600):
    t0 = time.time()
    while not all(Path(p).exists() for p in paths):
        if time.time() - t0 > limit:
            raise SystemExit(f"waited {limit} s for {paths}")
        time.sleep(poll)


def loop(root, arm):
    """DD13's loop with section 4's arms; resumable per cycle."""
    root = Path(root)
    spec = ARMS[arm]
    base = spec["base"]
    _prefix(root, arm, spec)
    ctx = _ctx(root, base)
    c = ctx["c"]
    k = float(_rd(DD7_ROOT / "b" / "setup.json")["dd5"]["k"])
    psf_img = np.load(root / "psf" / ("real.npy" if base == "real" else "O.npy"))
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search_pinned = ctx["search"] & (ctx["idx"] > 0)
    bnom = np.load(root / "beam.npz")["b_nom"]
    amp = bnom if base == "OB" else np.ones(4)
    high = high_facets(bnom)
    run = {"OB": root / "O", "O": root / "gate" / "O"}.get(base)
    sky = np.load(run / "sky.npy") if run else None
    truth = np.load(run / "truth.npz")["gains"] if run else None
    model = np.load(dd10.START["real" if base == "real" else "O"])
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
        info = {"arm": arm, "cycle": cyc, "seconds_predict": time.perf_counter() - t0}
        if sky is not None:
            info["model_error"] = dd10.model_error(ctx, model, sky)
        final, scored = cyc == N, cyc in SCORED
        gains = flags = None
        d.mkdir(parents=True, exist_ok=True)
        if (d / "reuse_gains.npz").exists():
            z = np.load(d / "reuse_gains.npz")
            gains, flags = z["gains"], z["flags"]
            info["solve"] = _rd(d / "reuse_info.json")["solve"]
            info["solve_reused_from"] = str(d / "reuse_gains.npz")
            np.savez_compressed(d / "gains.npz", **{kk: z[kk] for kk in z.files})
        elif spec["solve"] == "gs" or scored:
            res = dd11.solve_cycle(ctx, models, "gs", second=scored)
            sol = res["sol"]
            srec, conv = dd10.scores(ctx, models, sol, res.get("sol2"), k)
            gains, flags = np.asarray(sol.gains), np.asarray(sol.flags)
            if truth is not None:
                srec.update(dd14.products_err(gains, flags, truth))
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
            if spec["images"] == "truth":
                ig, bad = truth[:, None], None
            elif (
                final
            ):  # real only: the final residual for the reported rms (DD13's rule Q)
                ig, bad = dd13.image_gains("Q", gains, flags, None, 99)
            else:
                ig, bad = image_gains_qg(gains, flags, cyc, amp, bnom)
            if bad is not None:
                info["untrusted_gain_share"] = [
                    float(bad[..., f].mean()) for f in range(4)
                ]
            info["image_rule"] = "Q" if final else spec["images"]
            resid = dd10.residual_image(ctx, models, ig, c["w_I"])
            info["seconds_image"] = time.perf_counter() - t1
            info["residual_sigma_d1_d3"] = dd10.mad_sigma(resid, clean_interior)
            if base == "real":
                info["thermal_sigma"] = dd10.thermal_sigma(ctx, c["w_I"], k)
            if not final:
                release = cyc >= 2
                search = search_mask(
                    clean_interior, search_pinned, ctx["idx"], high, release
                )
                info["pins_released_facets"] = (
                    [int(f) for f in np.nonzero(high)[0] if f > 0] if release else []
                )
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
        # stage stop (section 4): QPG12 only, after M6, on section 6's rows at N = 6
        if arm == "QPG12" and cyc == 6:
            _wait_for([root / "loop" / "ATG12" / "cycle-6" / "info.json",
                       root / "loop" / "QPG12-O" / "cycle-5" / "next_model.npy"])  # fmt: skip
            pt = points(root, only=("QPG12",), ns=(6,))
            cr = pt["QPG12"][6]["criteria"]
            if cr["row"] == 0:
                write_json(out / "stopped.json", {"cycle": 6, "criteria_at_6": cr})
                return


# -- scores (sections 5 and 6) ----------------------------------------------------------

# arm -> (OB root, O-twin root and arm, matched truth control)
REFS = {
    "QPG12": ("dd15", ("dd15", "QPG12-O"), "ATG12"),
    "ATG12": ("dd15", None, None),
    "Q12": ("dd14", (DD12_ROOT, "Q12"), "AT12"),
    "QPN12": ("dd14", (DD13_ROOT, "QP12"), "ATP12"),
    "AT12": ("dd14", (DD12_ROOT, "AT12"), None),
    "ATP12": ("dd14", (DD13_ROOT, "ATP12"), None),
}


def _model_at(root, arm, n):
    f = Path(root) / "loop" / arm / f"cycle-{n - 1}" / "next_model.npy"
    return np.load(f) if f.exists() else None


def points(root, only=None, ns=SCORED):
    """Section 5's quantities and section 6's criteria per arm and N."""
    root = Path(root)
    aps = {int(f): a for f, a in _rd(root / "apertures.json")["apertures"].items()}
    a0 = _rd(DD14_ROOT / "loop" / "Q12" / "cycle-0" / "info.json")["solve"]
    axr = _rd(DD14_ROOT / "loop" / "AX" / "cycle-0" / "info.json")["solve"]
    truth = np.load(root / "O" / "truth.npz")["gains"]
    sky = np.load(root / "O" / "sky.npy")
    rootof = {"dd15": root, "dd14": DD14_ROOT}

    def pin(m):
        return [dd14.facet_flux(m, aps[f], "pin")[0] for f in (1, 2, 3)]

    def allflux(m, which):
        return [dd14.facet_flux(m, aps[f], which)[0] for f in (1, 2, 3)]

    sky_pin = pin(sky)
    out, files = {}, {}
    arms = (
        list(REFS)
        if only is None
        else list(only) + [a for a in ("Q12", "ATG12", "ATP12", "AT12")]
    )
    for arm in dict.fromkeys(arms):
        src, twin, _ = REFS[arm]
        r = rootof[src]
        out[arm] = {}
        for n in ns:
            f = r / "loop" / arm / f"cycle-{n}" / "info.json"
            if not f.exists() or "e_sr" not in (_rd(f).get("solve") or {}):
                continue
            s = _rd(f)["solve"]
            z = np.load(r / "loop" / arm / f"cycle-{n}" / "gains.npz")
            G, harm, rd_ = dd11.reading(s["e_sr"], a0["e_sr"], axr["e_sr"])
            m = _model_at(r, arm, n)
            files[f"{arm}/M{n}"] = sha_file(
                r / "loop" / arm / f"cycle-{n - 1}" / "next_model.npy"
            )
            p = {"e_d": s["e_d"], "e_sr": s["e_sr"], "s": s["s"], "G_sr": G, "harm_sr": harm,
                 "reading_sr": rd_, "perdir_converged": s.get("perdir_converged"),
                 "d3_amp": s.get("d3_amp"), "e_over_ehat": s.get("e_over_ehat"),
                 "diag": dd11.gain_errors(z["gains"], z["flags"], truth),
                 "F_pin": pin(m), "F_pin_sky": sky_pin,
                 "eps_pin_vs_sky": [a / b - 1 for a, b in zip(pin(m), sky_pin, strict=True)],
                 "F_all": allflux(m, "all"), "F_nonpin": allflux(m, "nonpin")}  # fmt: skip
            if twin is not None:
                troot = rootof.get(twin[0], twin[0])
                m0 = _model_at(troot, twin[1], n)
                if m0 is not None:
                    files[f"{twin[1]}@{troot}/M{n}"] = sha_file(
                        Path(troot)
                        / "loop"
                        / twin[1]
                        / f"cycle-{n - 1}"
                        / "next_model.npy"
                    )
                    p["twin"] = f"{troot}/{twin[1]}"
                    p["F_pin_on_O"] = pin(m0)
                    p["kappa_pin"] = [
                        a / b - 1 for a, b in zip(pin(m), pin(m0), strict=True)
                    ]
                    for which in ("all", "nonpin"):
                        p[f"kappa_{which}"] = [a / b - 1 if b else None for a, b in
                                               zip(allflux(m, which), allflux(m0, which), strict=True)]  # fmt: skip
            out[arm][n] = p
    # criteria (section 6), for the solved arms with a twin and a control
    for arm in ("QPG12", "QPN12", "Q12"):
        if arm not in out:
            continue
        ctl = REFS[arm][2]
        for n, p in out[arm].items():
            q, c = out["Q12"].get(n), out.get(ctl, {}).get(n)
            if q is None or c is None or "kappa_pin" not in p:
                continue
            readable = [a > 0.2 * b for a, b in zip(c["F_pin"], sky_pin, strict=True)]
            p["readable"] = readable
            p["criteria"] = criteria(p, q, c, q["kappa_pin"][2], readable)
    out["_files_sha256"] = files
    return out


def score(root):
    root = Path(root)
    pts = points(root)
    files = pts.pop("_files_sha256")
    stopped = (root / "loop" / "QPG12" / "stopped.json").exists()
    rows = [pts["QPG12"][n]["criteria"]["row"] for n in SCORED
            if n in pts["QPG12"] and "criteria" in pts["QPG12"][n]]  # fmt: skip
    done = stopped or len(rows) == len(SCORED)
    rec = {"rule": "research/dd15-beam-gate.md sections 5-6", "threshold": THRESH,
           "points": {a: {str(n): p for n, p in v.items()} for a, v in pts.items()},
           "files_sha256": files, "QPG12_stopped": stopped, "rows": rows}  # fmt: skip
    if done:
        rec["answer"] = answer(rows, stopped)
        rec["real_check_called"] = rec["answer"].startswith("in")
        ans = rec["answer"]
        rec["real_facets_read"] = (
            [1, 2, 3]
            if ans.startswith("in:")
            else [1, 2]
            if ans.startswith("in for")
            else []
        )
    # reference readings under DD15's rules (recorded, not deciding)
    rec["reference_rows"] = {a: {str(n): p["criteria"]["row"] for n, p in pts[a].items() if "criteria" in p}
                             for a in ("QPN12", "Q12") if a in pts}  # fmt: skip
    for arm in ARMS:
        cyc = []
        for kk in range(N + 1):
            f = root / "loop" / arm / f"cycle-{kk}" / "info.json"
            if not f.exists():
                break
            ci = _rd(f)
            sv = ci.get("solve") or {}
            cyc.append({x: ci.get(x) for x in ("model_error", "hogbom", "components_flux", "untrusted_gain_share",
                                               "residual_sigma_d1_d3", "image_rule", "pins_released_facets",
                                               "thermal_sigma")}
                       | {"e_d": sv.get("e_d"), "e_sr": sv.get("e_sr"), "s": sv.get("s"),
                          "global_fraction": sv.get("global_fraction"),
                          "perdir_converged": sv.get("perdir_converged")})  # fmt: skip
        rec[f"cycles_{arm}"] = cyc
    write_json(root / "score.json", rec)


# -- the real-data check (section 7) ----------------------------------------------------


def real(root):
    root = Path(root)
    sc = _rd(root / "score.json")
    if not sc.get("real_check_called"):
        raise SystemExit("section 7: the frozen rule does not read 'in'; no real check")
    read = sc["real_facets_read"]
    st, idx, interior = dd14.geometry()
    sel = json.loads(dd14.CATSEL.read_text())
    comps = []
    for cc in sel["model_components"]:
        x = round(dd4.NX / 2 - cc["l"] / dd2.DELTA)
        y = round(cc["m"] / dd2.DELTA + dd4.NY / 2)
        if 0 <= x < dd4.NX and 0 <= y < dd4.NY:
            comps.append({"id": cc["id"], "y": y, "x": x, "S": float(cc["s_app"])})
    aps = dd14.real_apertures(comps, idx, interior, st["pins"])
    mpaths = {"RM": DD7_ROOT / "models" / "RM.npy",
              "R-Q6": DD11_ROOT / "loop" / "R-Q6" / "cycle-5" / "next_model.npy",
              "R-QP12": DD13_ROOT / "loop" / "R-QP12" / "cycle-11" / "next_model.npy",
              "R-QPG12": root / "loop" / "R-QPG12" / "cycle-11" / "next_model.npy"}  # fmt: skip
    rec = {"rule": "research/dd15-beam-gate.md section 7", "facets_read": read,
           "apertures": {str(f): a for f, a in aps.items()}, "models": {},
           "models_sha256": {k: sha_file(v) for k, v in mpaths.items()}}  # fmt: skip
    for name, pth in mpaths.items():
        m = np.load(pth)
        r_ = {}
        for which in ("nonpin", "pin"):
            eps = []
            for f in (1, 2, 3):
                sel_ = [a for a in aps[f] if a["pin"] == (which == "pin")]
                if not sel_:
                    eps.append(None)
                    continue
                fm = sum(dd14.ap_sum(m, a["y"], a["x"]) for a in sel_)
                eps.append(fm / sum(a["cat"] for a in sel_) - 1)
            r_[which] = eps
        rec["models"][name] = r_
    rm = rec["models"]["RM"]["nonpin"] + rec["models"]["RM"]["pin"]
    rec["RM_code_check_max_abs"] = max(abs(x) for x in rm if x is not None)
    e_x, e_q = rec["models"]["R-QPG12"]["nonpin"], rec["models"]["R-Q6"]["nonpin"]
    rec["agrees_with_catalogue"] = {f"d{f}": abs(e_x[f - 1]) <= 0.10 for f in (1, 2, 3)
                                    if e_x[f - 1] is not None}  # fmt: skip
    rec["agrees_with_pinned_loop"] = {f"d{f}": abs(e_x[f - 1] - e_q[f - 1]) <= 0.05 for f in (1, 2, 3)
                                      if e_x[f - 1] is not None and e_q[f - 1] is not None}  # fmt: skip
    rec["not_readable"] = [f"d{f}" for f in (1, 2, 3) if e_x[f - 1] is None]
    rec["real_check_passes"] = bool(read) and all(
        e_x[f - 1] is not None and abs(e_x[f - 1]) <= 0.10 for f in read
    )
    # DD13 section 7's convergence reading, reported
    r0 = _rd(DD13_ROOT / "reuse" / "R0-info.json")["solve"]
    conv = {}
    for name, f in (("R-QPG12", root / "loop" / "R-QPG12" / "cycle-12" / "info.json"),
                    ("R-QP12", DD13_ROOT / "loop" / "R-QP12" / "cycle-12" / "info.json")):  # fmt: skip
        if f.exists():
            rx = _rd(f)["solve"]
            m0, m1 = min(r0["perdir_converged"][1:]), min(rx["perdir_converged"][1:])
            conv[name] = {"R0_min_d1_d3": m0, "RX_min_d1_d3": m1, "lifts": m1 >= m0 + 0.20,
                          "tames_d3": rx["d3_amp"]["p99"] <= 3 and rx["d3_amp"]["max"] <= 10,
                          "perdir_converged": rx["perdir_converged"], "d3_amp": rx["d3_amp"]}  # fmt: skip
    rec["convergence"] = conv
    write_json(root / "real.json", rec)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    fn = {
        "build": build,
        "gater": gater,
        "score": score,
        "realprep": realprep,
        "real": real,
    }
    if cmd in fn:
        fn[cmd](argv[1])
    elif cmd == "loop":
        loop(argv[1], argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
