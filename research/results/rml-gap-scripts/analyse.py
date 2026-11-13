"""analyse.py SKY [SKY ...]: section 4 of research/rml-gap.md on one bench sky.

Reads $O/prep/SKY (gemclean_bench_compare.py prepare), the catalogue, and the runs
$O/runs/{G,W,U-*}/SKY; writes $O/scores/SKY.json: the common beam, the scorer control, the
preconditions, every arm's measures (U: every major cycle's MFS model, the exact residual for the
last cycle and for the last within 5 x G's wall), parity, and the per-sky ratios of section 5.
"""

import json
import math
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "examples"))
import rml_gap_score as rs  # noqa: E402
from gemclean_bench_compare import Exact, inner_box, truth_image  # noqa: E402
from rang.core_imaging import read_fits  # noqa: E402

O = Path("D:/rang/outputs/rml-gap-20261113")
CATS = {
    "S1": "D:/rang/outputs/20261102-gemclean/bench/data/s1.json",
    "S2": "D:/rang/outputs/20261102-gemclean/bench/data/s2.json",
    "S3": "D:/rang/outputs/20261102-gemclean/bench/data/s3.json",
    "H1": "D:/rang/outputs/20261103-gemclean-heldout/sim/data/h1.json",
    "H2": "D:/rang/outputs/20261103-gemclean-heldout/sim/data/h2.json",
    "H3": "D:/rang/outputs/20261103-gemclean-heldout/sim/data/h3.json",
    "H4": "D:/rang/outputs/20261103-gemclean-heldout/sim/data/h4.json",
    "M1": "D:/rang/outputs/g5-20261107-03/data/m1.json",
    "N1": str(O / "data/n1.json"),
    "N2": str(O / "data/n2.json"),
}


def mad_sigma(img, mask):
    v = img[mask]
    return float(1.4826 * np.median(np.abs(v - np.median(v))))


class Sky:
    def __init__(self, sky):
        self.sky = sky
        self.prep = O / "prep" / sky
        self.meta = json.loads((self.prep / "meta.json").read_text(encoding="utf-8"))
        self.cat = json.loads(Path(CATS[sky]).read_text(encoding="utf-8"))
        self.size = self.meta["size"]
        self.comps = rs.components(self.cat)
        w = O / "runs" / "W" / sky
        psf, _ = read_fits(w / "w-psf.fits")
        self.beam = rs.halfmax_major_px(psf)
        self.bt = rs.truth_on_beam(self.comps, self.size, self.beam)
        self.label, self.groups = rs.groups(self.comps, self.size, self.beam)
        if self.meta.get("noise"):
            self.sigma, self.sigma_source = self.meta["noise"]["briggs_image_rms"], "noise file"
        else:
            res, _ = read_fits(w / "w-residual.fits")
            ib = np.zeros_like(self.label, bool)
            ib[inner_box(self.size)] = True
            self.sigma = mad_sigma(res, ib & (self.label == 0))
            self.sigma_source = "1.4826 MAD of W's residual outside every group"
        self.core_dirty = np.load(self.prep / "core-dirty-fits-order.npy").astype(np.float64)
        self._exact = None

    @property
    def exact(self):
        if self._exact is None:
            self._exact = Exact(self.prep)
        return self._exact

    def measure(self, model, exact):
        model = np.nan_to_num(model)
        rec = rs.measures(rs.model_on_beam(model, self.beam), self.bt, model, self.label,
                          self.groups, self.beam, self.sigma)  # fmt: skip
        if exact:
            q, r = self.exact.score(model)
            ib = inner_box(self.size)
            rec["q_over_q0"] = q / self.meta["q0"]
            if self.meta.get("noise"):
                rec["q_over_q_truth"] = q / self.meta["noise"]["q_truth"]
            rec["exact_residual_inner_rms_sigma"] = float(np.sqrt(np.mean(r[ib] ** 2)) / self.sigma)
            rec["exact_residual_inner_peak_sigma"] = float(np.abs(r[ib]).max() / self.sigma)
        return rec

    def control(self):
        out = {}
        for name, model in (("bandlimited", rs.bandlimited_truth(self.comps, self.size)),
                            ("nearest_pixel", truth_image(self.cat, self.size))):  # fmt: skip
            rec = self.measure(model, exact=False)
            ratios = [g["F_M"] / g["F_T"] for g in rec.pop("groups")]
            rec["group_ratio_min"], rec["group_ratio_max"] = min(ratios), max(ratios)
            out[name] = rec
        b = out["bandlimited"]
        out["pass"] = bool(b["relative_l2"] <= 0.002 and abs(b["group_ratio_min"] - 1) <= 0.002
                           and abs(b["group_ratio_max"] - 1) <= 0.002)  # fmt: skip
        return out

    def dirty_check(self, path, orient=0):
        d, _ = read_fits(path)
        d = rs.ORIENT[orient](d)
        peak = np.abs(self.core_dirty).max()
        return float(np.abs(d - self.core_dirty).max() / peak)


def wall(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def time_v(path):
    p = Path(path)
    if not p.exists():
        return None
    m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", p.read_text(encoding="utf-8"))
    return int(m.group(1)) / 1e6 if m else None


def u_run(s, d, g_wall, out):
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    rec = {"rc": run["rc"], "wall_s": run["wall_s"], "steps": [
        {k: st[k] for k in ("step", "rc", "wall_s", "wall_cap_hit")} for st in run["steps"]]}  # fmt: skip
    rec["peak_rss_gb"] = {n: time_v(d / f"time-{n}.txt") for n in ("init", "grid", "sara")}
    dirty = d / "pfb_I_main_dirty_time0000_mfs.fits"
    if not dirty.exists():
        rec["precondition"] = "no dirty image"
        return rec
    pfb, _ = read_fits(dirty)
    best = None
    for k, f in rs.ORIENT.items():
        c = f(pfb)
        if c.shape != s.core_dirty.shape:
            continue
        sc = float(np.sum(c * s.core_dirty) / np.sum(c * c))
        e = float(np.abs(sc * c - s.core_dirty).max() / np.abs(s.core_dirty).max())
        best = (best or []) + [(e, k, sc)]
    best.sort()
    rec["orientation"] = best[0][1]
    rec["dirty_linf_over_peak_scaled"] = best[0][0]
    rec["dirty_scale"] = best[0][2]
    rec["orientation_margin"] = best[1][0] - best[0][0]
    rec["dirty_linf_over_peak"] = s.dirty_check(dirty, rec["orientation"])
    rec["precondition_pass"] = rec["orientation_margin"] >= 0.5
    log = (d / "sara.log").read_text(encoding="utf-8", errors="replace") if (d / "sara.log").exists() else ""
    eps = [float(x) for x in re.findall(r"eps = ([0-9.eE+-]+)", log)]
    rec["eps"] = eps
    rec["converged"] = bool(eps) and eps[-1] < 5e-4
    rec["diverged"] = "diverg" in log.lower()
    secs = run["file_seconds_since_start"]
    its = sorted(
        (int(m.group(1)), secs[f])
        for f in secs
        if (m := re.fullmatch(r"pfb_I_main_model_(\d+)\.fits", f))
    )
    rec["iterates"] = []
    for k, t in its:
        model, _ = read_fits(d / f"pfb_I_main_model_{k}.fits")
        m = s.measure(rs.ORIENT[rec["orientation"]](model), exact=False)
        m.pop("groups")
        rec["iterates"].append({"cycle": k, "seconds": t, **m})
    if not its:
        return rec
    last = its[-1][0]
    within = [k for k, t in its if g_wall and t <= 5 * g_wall]
    for key, k in (("last", last), ("within_5g", within[-1] if within else None)):
        if k is None:
            rec[key] = None
            continue
        model, _ = read_fits(d / f"pfb_I_main_model_{k}.fits")
        m = s.measure(rs.ORIENT[rec["orientation"]](model), exact=True)
        m["cycle"] = k
        m["seconds"] = dict(its)[k]
        rec[key] = m
    if rec["converged"] and g_wall:
        rec["converged_within_5g"] = its[-1][1] <= 5 * g_wall
    return rec


def analyse(sky):
    s = Sky(sky)
    out = {"sky": sky, "beam_px": s.beam, "sigma": s.sigma, "sigma_source": s.sigma_source,
           "groups": len(s.groups), "extended_groups": sum(g["extended"] for g in s.groups)}  # fmt: skip
    out["control"] = s.control()
    arms = {}
    g_wall = None
    for arm, prefix in (("G", "g"), ("W", "w")):
        d = O / "runs" / arm / sky
        if not (d / f"{prefix}-model.fits").exists():
            continue
        model, _ = read_fits(d / f"{prefix}-model.fits")
        rec = s.measure(model, exact=True)
        rec.update(wall(d / "wall.json"))
        rec["peak_rss_gb"] = time_v(d / "time.txt")
        rec["dirty_linf_over_peak"] = s.dirty_check(d / f"{prefix}-dirty.fits")
        rec["precondition_pass"] = rec["dirty_linf_over_peak"] <= 1e-5
        log = (d / "log.txt").read_text(encoding="utf-8", errors="replace")
        rec["major_cycles_log"] = len(re.findall(r"Major iteration|major cycle \d+|== Major", log, re.I))
        arms[arm] = rec
        if arm == "G":
            g_wall = rec["wall_s"]
    for d in sorted((O / "runs").glob(f"U-*/{sky}")):
        if (d / "run.json").exists():
            arms[d.parent.name] = u_run(s, d, g_wall, out)
    out["arms"] = arms
    if "G" in arms and "W" in arms:
        G, W = arms["G"], arms["W"]
        omega = 2 * math.pi * (s.beam * rs.FWHM_TO_SIGMA) ** 2
        par = []
        for gg, ww in zip(G["groups"], W["groups"], strict=True):
            if not gg["extended"]:
                continue
            ok = abs(gg["F_M"] - ww["F_M"]) <= 0.02 * gg["F_T"] + math.sqrt(2) * gg["eps"]
            par.append({"id": gg["id"], "F_G": gg["F_M"], "F_W": ww["F_M"], "F_T": gg["F_T"],
                        "pass": ok})  # fmt: skip
        ratio = W["relative_l2"] / G["relative_l2"]
        out["parity"] = {"groups": par, "l2_ratio_w_over_g": ratio, "omega_px": omega,
                         "pass": all(p["pass"] for p in par) and 0.8 <= ratio <= 1.25}  # fmt: skip
        for name, u in arms.items():
            if not name.startswith("U-") or not u.get("last"):
                continue
            u["r"] = u["last"]["relative_l2"] / G["relative_l2"]
            u["r5"] = u["within_5g"]["relative_l2"] / G["relative_l2"] if u.get("within_5g") else None
            u["cost_ratio_last"] = u["last"]["seconds"] / G["wall_s"]
    for a in arms.values():
        for k in ("last", "within_5g"):
            if isinstance(a.get(k), dict):
                a[k].pop("groups", None)
    (O / "scores").mkdir(exist_ok=True)
    (O / "scores" / f"{sky}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    brief = {"sky": sky, "beam_px": round(s.beam, 3), "control": out["control"]["pass"],
             "parity": out.get("parity", {}).get("pass")}  # fmt: skip
    for n, a in arms.items():
        if n in ("G", "W"):
            brief[n] = (round(a["relative_l2"], 4), round(a["wall_s"], 1))
        elif a.get("last"):
            brief[n] = (round(a["last"]["relative_l2"], 4), a["last"]["cycle"],
                        round(a["last"]["seconds"], 1), a.get("converged"), a.get("r"), a.get("r5"))  # fmt: skip
    print(json.dumps(brief))


if __name__ == "__main__":
    for sky in sys.argv[1:]:
        analyse(sky)
