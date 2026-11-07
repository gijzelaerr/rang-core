"""score.py OUT SKY CATALOGUE : criteria B, C, D, E and F of research/g9-stokes.md, mechanically.

GeMClean runs are read from OUT/runs/g/<sky>-<cfg>/g-*, WSClean's from OUT/runs/w/<sky>-<cfg>/w-*,
the truth from CATALOGUE (G3's D1.json: Stokes I only; g9_stokes_simulate.py: I, Q, U, V per
channel). Configurations that were not run are skipped. Writes OUT/score-<sky>.json.
"""

import importlib.util
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

# G3's helpers, loaded by path under another name (both files are score.py).
_spec = importlib.util.spec_from_file_location(
    "g3_score", Path(__file__).resolve().parents[1] / "g3-spectral-scripts" / "score.py"
)
_g3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g3)
gaussian_kernel, inner, mad_sigma, restore = (
    _g3.gaussian_kernel,
    _g3.inner,
    _g3.mad_sigma,
    _g3.restore,
)

R_POINT = 6.0
CFG = {  # pols, output channels, cleaned
    "Q0": (["I"], 1, True),
    "Q1": (["I", "Q", "U", "V"], 1, True),
    "Q2": (["I", "Q", "U", "V"], 1, True),
    "Q3": (["I", "Q", "U", "V"], 8, True),
    "Q4": (["XX", "YY"], 1, False),
    "Q5": (["I", "Q", "U", "V"], 4, False),
    "Q6": (["Q", "U"], 4, True),
}


def img(path):
    with fits.open(path) as h:
        return np.asarray(h[0].data, dtype=np.float64).squeeze(), dict(h[0].header)


class Run:
    def __init__(self, out, who, sky, cfg):
        self.dir = Path(out) / "runs" / who / f"{sky}-{cfg}"
        self.p = who
        self.pols, self.n, self.cleaned = CFG[cfg]

    def exists(self):
        return self.dir.is_dir() and any(self.dir.glob(f"{self.p}-*.fits"))

    def path(self, kind, pol=None, part=""):
        chan = f"-{part}" if part != "" else ""
        p = f"-{pol}" if (pol and len(self.pols) > 1 and kind != "psf") else ""
        return self.dir / f"{self.p}{chan}{p}-{kind}.fits"

    def get(self, kind, pol=None, part=""):
        return img(self.path(kind, pol, part))


def parts(n):
    return [""] if n == 1 else [f"{k:04d}" for k in range(n)] + ["MFS"]


def stokes_truth(comp, nchan):
    if "stokes_per_channel" in comp:
        s = comp["stokes_per_channel"]
        return {p: np.asarray(s[p]) for p in "IQUV"}
    i = np.asarray(comp["flux_per_channel"])
    return {"I": i, "Q": 0 * i, "U": 0 * i, "V": 0 * i}


def unpolarised(comp):
    return comp.get("p", 0.0) == 0.0 and comp.get("v", 0.0) == 0.0


def aperture(comp, size):
    yy, xx = np.mgrid[0:size, 0:size]
    return (xx - comp["x"]) ** 2 + (yy - comp["y"]) ** 2 <= R_POINT**2


def nearest(comp):
    return int(round(comp["y"])), int(round(comp["x"]))


# -- B ----------------------------------------------------------------------------------


def crit_b(g, w):
    rows, ok, missing = [], True, []
    for f in sorted(w.dir.glob("w-*.fits")):
        gf = g.dir / ("g" + f.name[1:])
        if not gf.exists():
            missing.append(f.name)
            continue
        a, ha = img(gf)
        b, hb = img(f)
        row = {"file": f.name}
        for key, tol in (("WSCIMGWG", 1e-6), ("CRVAL3", 1e-9), ("CDELT3", 1e-9)):
            if key not in hb:  # WSClean writes no WSCIMGWG in a cleaned MFS image
                row[f"{key}_absent_in_wsclean"] = True
                continue
            rel = abs(float(ha[key]) - float(hb[key])) / abs(float(hb[key]))
            row[f"{key}_rel"] = rel
            ok &= rel <= tol
        row["CRVAL4_equal"] = float(ha["CRVAL4"]) == float(hb["CRVAL4"])
        ok &= row["CRVAL4_equal"]
        kind = f.stem.rsplit("-", 1)[-1]
        if kind in ("dirty", "psf"):
            m = re.match(r"w-(\d{4}-|MFS-)?", f.name)
            part = (m.group(1) or "").rstrip("-")
            ref = w.path("dirty" if kind == "dirty" else "psf", w.pols[0], part)
            scale_first = float(np.abs(img(ref)[0]).max())
            d = float(np.abs(a - b).max())
            row["rel_first"] = d / scale_first
            row["rel_own"] = d / float(np.abs(b).max())
            ok &= row["rel_first"] <= 1e-5 and row["rel_own"] <= 1e-5
        rows.append(row)
    ok &= not missing
    worst = {
        k: max((r.get(k, 0.0) for r in rows), default=0.0)
        for k in ("rel_first", "rel_own", "WSCIMGWG_rel", "CRVAL3_rel", "CDELT3_rel")
    }
    return {"pass": bool(ok), "worst": worst, "missing": missing, "files": len(rows)}


# -- C ----------------------------------------------------------------------------------


def common_beam_image(run, w, p, part):
    """`run`'s model restored with WSClean's beam of the file plus its own residual (C')."""
    model, _ = run.get("model", p, part)
    res, _ = run.get("residual", p, part)
    _, wh = w.get("residual", p, part)
    scale = abs(float(wh["CDELT2"]))
    kern = gaussian_kernel(
        model.shape[0], float(wh["BMAJ"]), float(wh["BMIN"]), float(wh["BPA"]), scale
    )
    return restore(model, kern) + res


def crit_c(g, w, cat, sigma_i, common=False):
    """C as frozen (each imager's own restored image), or C' (post hoc, before the
    held-out sky): both models restored with WSClean's beam, each own residual added."""
    part = "MFS" if g.n > 1 else ""
    size = cat["image"]["size"]
    srcs = []
    for c in cat["components"]:
        t = stokes_truth(c, cat["nchan"])
        if unpolarised(c) and t["I"].mean() >= 200 * sigma_i:
            srcs.append((c, float(t["I"].mean())))
    out, ok = {"sources": len(srcs)}, True
    if not srcs:
        return {"pass": True, "sources": 0}
    for p in [q for q in ("Q", "U", "V") if q in g.pols]:
        r = {}
        for run in (g, w):
            if common:
                image = common_beam_image(run, w, p, part)
            else:
                image, _ = run.get("image", p, part)
            model, _ = run.get("model", p, part)
            rv = np.array([image[nearest(c)] for c, _ in srcs])
            fv = np.array([model[aperture(c, size)].sum() for c, _ in srcs])
            r[run.p] = {
                "median_leak": float(
                    np.median(np.abs(rv) / np.array([i for _, i in srcs]))
                ),
                "max_abs_restored": float(np.abs(rv).max()),
                "sum_abs_model": float(np.abs(fv).sum()),
                "rms": float(np.sqrt(np.mean(inner(image) ** 2))),
            }
        wimage = (
            common_beam_image(w, w, p, part) if common else w.get("image", p, part)[0]
        )
        sigma_p = mad_sigma(inner(wimage))
        gp, wp = r["g"], r["w"]
        r["sigma"] = sigma_p
        r["pass"] = bool(
            gp["median_leak"] <= wp["median_leak"] + 1e-4
            and gp["max_abs_restored"] <= wp["max_abs_restored"] + 3 * sigma_p
            and gp["sum_abs_model"] <= 1.5 * wp["sum_abs_model"] + 1e-3
            and gp["rms"] <= 1.05 * wp["rms"]
        )
        ok &= r["pass"]
        out[p] = r
    out["pass"] = bool(ok)
    return out


# -- D ----------------------------------------------------------------------------------


def crit_d(g, w, cat):
    size = cat["image"]["size"]
    nchan = cat["nchan"]
    groups = [list(range(i * nchan // g.n, (i + 1) * nchan // g.n)) for i in range(g.n)]
    chans = [""] if g.n == 1 else [f"{k:04d}" for k in range(g.n)]
    recs = {"I": [], "lin": [], "V": []}
    for k, part in enumerate(chans):
        sig = {p: mad_sigma(inner(w.get("residual", p, part)[0])) for p in g.pols}
        models = {
            run.p: {p: run.get("model", p, part)[0] for p in g.pols} for run in (g, w)
        }
        for i, c in enumerate(cat["components"]):
            t = {
                p: float(v[groups[k]].mean()) for p, v in stokes_truth(c, nchan).items()
            }
            mask = aperture(c, size)
            flux = {
                who: {p: float(m[p][mask].sum()) for p in g.pols}
                for who, m in models.items()
            }
            if "I" in g.pols and t["I"] >= 200 * sig["I"]:
                snr = t["I"] / sig["I"]
                e = {who: abs(flux[who]["I"] / t["I"] - 1) for who in flux}
                recs["I"].append(
                    {"src": i, "ch": k, "snr": snr, "err": e, "tol": 0.02 + 3 / snr}
                )
            if "Q" in g.pols and "U" in g.pols:
                pt = math.hypot(t["Q"], t["U"])
                s_qu = 0.5 * (sig["Q"] + sig["U"])
                if pt >= 50 * s_qu:
                    snr = pt / s_qu
                    chi_t = 0.5 * math.atan2(t["U"], t["Q"])
                    e, dchi = {}, {}
                    for who in flux:
                        fq, fu = flux[who]["Q"], flux[who]["U"]
                        e[who] = math.hypot(fq - t["Q"], fu - t["U"]) / pt
                        d = 0.5 * math.atan2(fu, fq) - chi_t
                        d = (d + math.pi / 2) % math.pi - math.pi / 2
                        dchi[who] = abs(math.degrees(d))
                    recs["lin"].append(
                        {
                            "src": i,
                            "ch": k,
                            "snr": snr,
                            "err": e,
                            "dchi": dchi,
                            "tol": 0.03 + 3 / snr,
                        }
                    )
            if "V" in g.pols and abs(t["V"]) >= 50 * sig["V"]:
                snr = abs(t["V"]) / sig["V"]
                e = {who: abs(flux[who]["V"] - t["V"]) / abs(t["V"]) for who in flux}
                recs["V"].append(
                    {"src": i, "ch": k, "snr": snr, "err": e, "tol": 0.03 + 3 / snr}
                )
    out, ok, ok_h = {}, True, True
    for kind, rs in recs.items():
        if not rs:
            continue
        v = {}
        for who in ("g", "w"):
            failed = sum(1 for r in rs if r["err"][who] > r["tol"])
            v[who] = {
                "scored": len(rs),
                "failed": failed,
                "fraction": 1 - failed / len(rs),
                "median_err": float(np.median([r["err"][who] for r in rs])),
            }
            if kind == "lin":
                v[who]["median_dchi_deg"] = float(
                    np.median([r["dchi"][who] for r in rs])
                )
        gv, wv = v["g"], v["w"]
        good = (
            gv["fraction"] >= 0.9
            and gv["failed"] <= wv["failed"] + 1
            and gv["median_err"] <= wv["median_err"] + 0.005
        )
        if kind == "lin":
            good &= gv["median_dchi_deg"] <= wv["median_dchi_deg"] + 0.5
        v["pass"] = bool(good)
        v["wsclean_meets_90"] = bool(wv["fraction"] >= 0.9)
        # D' (post hoc, research/g9-stokes.md section 3, amended before the
        # held-out sky): a component also passes for GeMClean when its error
        # is at most WSClean's plus 0.005 (the estimator's own bias is shared).
        failed_h = sum(
            1
            for r in rs
            if r["err"]["g"] > r["tol"] and r["err"]["g"] > r["err"]["w"] + 0.005
        )
        frac_h = 1 - failed_h / len(rs)
        # Paired: the median over components of GeMClean's error minus WSClean's.
        paired = float(np.median([r["err"]["g"] - r["err"]["w"] for r in rs]))
        good_h = frac_h >= 0.9 and failed_h <= wv["failed"] + 1 and paired <= 0.005
        v["posthoc"] = {
            "failed": failed_h,
            "fraction": frac_h,
            "paired_median_err_diff": paired,
        }
        if kind == "lin":
            paired_chi = float(np.median([r["dchi"]["g"] - r["dchi"]["w"] for r in rs]))
            v["posthoc"]["paired_median_dchi_diff_deg"] = paired_chi
            good_h &= paired_chi <= 0.5
        v["posthoc"]["pass"] = bool(good_h)
        ok &= good
        ok_h &= good_h
        out[kind] = v
        out[kind + "_records"] = rs
    out["pass"] = bool(ok)
    out["pass_posthoc"] = bool(ok_h)
    return out


# -- E ----------------------------------------------------------------------------------


def gap(g, w, pol, part):
    wres, wh = w.get("residual", pol, part)
    gres, _ = g.get("residual", pol, part)
    wmod, _ = w.get("model", pol, part)
    gmod, _ = g.get("model", pol, part)
    scale = abs(float(wh["CDELT2"]))
    kern = gaussian_kernel(
        wres.shape[0], float(wh["BMAJ"]), float(wh["BMIN"]), float(wh["BPA"]), scale
    )
    d = inner((restore(gmod, kern) + gres) - (restore(wmod, kern) + wres))
    sigma = mad_sigma(inner(wres))
    return {
        "d_rms": float(np.sqrt(np.mean(d * d)) / sigma),
        "d_max": float(np.abs(d).max()),
        "sigma": sigma,
    }


# -- F ----------------------------------------------------------------------------------


def rss(run):
    t = run.dir / "time.txt"
    if not t.exists():
        return None
    for line in t.read_text().splitlines():
        if "Maximum resident" in line:
            return int(line.split(":")[1]) * 1024
    return None


def main():
    out, sky, catalogue = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    cat = json.loads(catalogue.read_text())
    res = {"sky": sky}
    runs = {}
    for cfg in CFG:
        g, w = Run(out, "g", sky, cfg), Run(out, "w", sky, cfg)
        if g.exists() and w.exists():
            runs[cfg] = (g, w)
    g0, w0 = runs["Q0"]
    sigma_i = mad_sigma(inner(w0.get("residual", "I")[0]))
    base = gap(g0, w0, "I", "")
    res["sigma_I_Q0"] = sigma_i
    res["E_baseline_Q0"] = base
    for cfg, (g, w) in runs.items():
        r = {"B": crit_b(g, w)}
        if g.cleaned and cfg != "Q0":
            if cfg in ("Q1", "Q2", "Q3"):
                r["C"] = crit_c(g, w, cat, sigma_i)
                r["C_posthoc"] = crit_c(g, w, cat, sigma_i, common=True)
            if (
                cfg in ("Q1", "Q2", "Q3", "Q6")
                and "stokes_per_channel" in cat["components"][0]
            ):
                r["D"] = crit_d(g, w, cat)
            part = "MFS" if g.n > 1 else ""
            e = {}
            for p in g.pols:
                m = gap(g, w, p, part)
                m["bound_rms"] = max(1.5 * base["d_rms"], base["d_rms"] + 0.1)
                m["bound_max"] = max(1.5 * base["d_max"], base["d_max"] + 1e-4)
                m["pass"] = bool(
                    m["d_rms"] <= m["bound_rms"] and m["d_max"] <= m["bound_max"]
                )
                e[p] = m
            e["pass"] = all(v["pass"] for v in e.values() if isinstance(v, dict))
            r["E"] = e
        r["F"] = {"gemclean": rss(g), "wsclean": rss(w)}
        r["F"]["pass"] = r["F"]["gemclean"] is None or r["F"]["gemclean"] <= 24e9
        res[cfg] = r
        line = [
            f"{cfg}:",
            f"B {'pass' if r['B']['pass'] else 'FAIL'} {r['B']['worst']} missing {len(r['B']['missing'])}",
        ]
        for k in ("C", "C_posthoc", "D", "E"):
            if k in r:
                line.append(f"{k} {'pass' if r[k]['pass'] else 'FAIL'}")
        if "D" in r:
            line.append(f"D_posthoc {'pass' if r['D']['pass_posthoc'] else 'FAIL'}")
        line.append(f"F {r['F']}")
        print(" | ".join(str(x) for x in line))
        if "D" in r:
            for kind in ("I", "lin", "V"):
                if kind in r["D"]:
                    v = r["D"][kind]
                    print(
                        f"   D {kind}: G {v['g']}  W {v['w']}  posthoc {v['posthoc']}"
                    )
        for ck in ("C", "C_posthoc"):
            if ck not in r:
                continue
            for p in ("Q", "U", "V"):
                if p in r[ck]:
                    print(f"   {ck} {p}: {r[ck][p]}")
        if "E" in r:
            print(
                "   E "
                + ", ".join(
                    f"{p} {v['d_rms']:.3f}/{v['d_max'] * 1e6:.0f}uJy"
                    for p, v in r["E"].items()
                    if isinstance(v, dict)
                )
                + f" (bounds {base['d_rms']:.3f}, {base['d_max'] * 1e6:.0f} uJy)"
            )
    (out / f"score-{sky}.json").write_text(
        json.dumps(res, indent=1, default=float) + "\n"
    )


if __name__ == "__main__":
    main()
