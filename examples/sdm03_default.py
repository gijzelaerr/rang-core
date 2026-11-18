# SPDX-License-Identifier: MIT
"""sdm03-default (research/sdm03-default.md): SDm03 against rang-core's shipped image default.

Arms are rang-core `image` sections: the defaults, the required size and scale, `threads: 8` and the
arm's keys, turned into gemclean's argv by `core_pipeline.gemclean_arguments` (W-* arms: WSClean 3.7 at
the same settings). Real data reuse floor-6's `floor6_tests.py` with its MAIN group pointed elsewhere.

    argv ARM --kind eso|sim --ms MS --prefix P [--mask M] [--column C]   print the argv (JSON)
    image ARM --kind ... --ms MS --prefix P [--mask M] [--column C]      run one arm
    fetchms --group MAIN_k --root ZARR --src SRC --phase meta|data         one ms1_target group
    real --group MAIN_k -- STAGE ...                                       a floor6_tests stage
    simprep MS CATALOGUE OUT                                               prepare arrays, truth, T
    simscore OUT ARM=PREFIX ...                                            section 3.2's measures
    summary OUT --real NAME=STATE ... --sim NAME=DIR ... --seen ...        section 7's rule

Every stage skips what it has already written.
"""

import argparse
import concurrent.futures
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ARCSEC = math.pi / (180.0 * 3600.0)
TRACK = "ESO137/ms1_target.zarr"
ROWCOLS = (
    "TIME",
    "TIME_CENTROID",
    "ANTENNA1",
    "ANTENNA2",
    "INTERVAL",
    "EXPOSURE",
    "FLAG_ROW",
    "UVW",
    "WEIGHT",
    "SIGMA",
)
CUBES = ("DATA", "FLAG", "WEIGHT_SPECTRUM")
TILES = range(5, 9)  # channels 640:1152
SPEC = {"channels_out": 8, "join_channels": True, "fit_spectral_pol": 2}
# research/sdm03-default.md section 2 (frozen); CARACal's final image: cleanmask_thr 6,
# clean_cutoff 0.5, img_mgain 0.9 (research/c5b-selfcal-masks.md section 1)
ARMS = {
    "A0": {},
    "SDa": {**SPEC, "auto_mask": 6.0, "auto_threshold": 0.5, "mgain": 0.9},
    "Sa": {**SPEC, "auto_mask": 6.0, "auto_threshold": 3.0, "mgain": 0.9},
    "SDm03": {**SPEC, "fits_mask": "MASK", "auto_threshold": None, "threshold": 0.0003},
    "Sm": {**SPEC, "fits_mask": "MASK", "threshold": None, "auto_threshold": 3.0},
}
BASE = {"eso": ([4096, 4096], "3asec"), "sim": ([2048, 2048], "1.5asec")}
WSCLEAN = "/usr/bin/wsclean"


def wjson(path, value):
    Path(path).write_text(
        json.dumps(value, indent=1, sort_keys=True, default=float) + "\n",
        encoding="utf-8",
    )


def rjson(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- arms


def image_section(arm, kind, mask=None):
    from rang import core_config

    size, scale = BASE[kind]
    keys = dict(ARMS[arm.removeprefix("W-")])
    if keys.get("fits_mask") == "MASK":
        if mask is None:
            raise SystemExit(f"{arm} needs --mask")
        keys["fits_mask"] = str(Path(mask).resolve())
    raw = {
        "schema": "rang-config",
        "version": 1,
        "image": {"size": size, "scale": scale, "threads": 8, **keys},
    }
    config, errors = core_config.resolve(raw)
    if errors:
        raise SystemExit(f"{arm}: config errors {errors}")
    refused = [
        (r.path, r.text)
        for r in core_config.refusals(config, ["image"])
        if r.path.startswith("image")
    ]
    if refused:
        raise SystemExit(f"{arm}: refused {refused}")
    return config["image"], raw["image"]


def gemclean_argv(arm, kind, ms, prefix, column, mask=None):
    from rang import core_pipeline

    img, keys = image_section(arm, kind, mask)
    return core_pipeline.gemclean_arguments(img, column, 0, prefix, ms), keys


def wsclean_argv(arm, kind, ms, prefix, column, mask=None):
    """WSClean 3.7 at the arm's settings (section 6)."""
    img, keys = image_section(arm, kind, mask)
    a = [WSCLEAN, "-gridder", "wgridder", "-no-min-grid-resolution"]
    a += ["-wgridder-accuracy", repr(float(img["wgridder_accuracy"]))]
    a += ["-name", str(prefix), "-size", *[str(v) for v in img["size"]]]
    a += ["-scale", img["scale"], "-weight", img["weight"], repr(float(img["robust"]))]
    a += ["-niter", str(img["niter"]), "-nmiter", str(img["nmiter"] or 20)]
    for key, flag in (
        ("gain", "-gain"),
        ("mgain", "-mgain"),
        ("threshold", "-threshold"),
        ("auto_threshold", "-auto-threshold"),
        ("auto_mask", "-auto-mask"),
        ("fits_mask", "-fits-mask"),
    ):
        if img[key] is not None:
            a += [flag, str(img[key])]
    if img["channels_out"] > 1:
        a += ["-channels-out", str(img["channels_out"])]
    if img["join_channels"]:
        a.append("-join-channels")
    if img["fit_spectral_pol"] is not None:
        a += ["-fit-spectral-pol", str(img["fit_spectral_pol"])]
    a += ["-pol", "I", "-data-column", column, "-field", "0", "-j", "8"]
    tmp = Path(str(prefix) + "-tmp")
    a += ["-no-update-model-required", "-temp-dir", str(tmp), str(ms)]
    return a, keys


def cmd_image(args):
    prefix = Path(args.prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    done = Path(str(prefix) + "-arm.json")
    if done.exists():
        return
    w = args.arm.startswith("W-")
    build = wsclean_argv if w else gemclean_argv
    argv, keys = build(args.arm, args.kind, args.ms, prefix, args.column, args.mask)
    if not w:
        argv = [sys.executable, "-m", "rang.gemclean", *argv]
    else:
        Path(str(prefix) + "-tmp").mkdir(exist_ok=True)
    log = Path(str(prefix) + "-imager.log")
    t0 = time.perf_counter()
    with log.open("w", encoding="utf-8") as fh:
        fh.write(" ".join(argv) + "\n")
        fh.flush()
        rc = subprocess.run(
            argv, check=False, stdout=fh, stderr=subprocess.STDOUT
        ).returncode
    wall = time.perf_counter() - t0
    if w:
        tmp = Path(str(prefix) + "-tmp")
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()
    rec = {"arm": args.arm, "kind": args.kind, "config_keys": keys, "argv": argv}
    rec.update({"rc": rc, "wall_s": wall, "ms": str(args.ms)})
    if rc != 0:
        wjson(str(prefix) + "-arm-failed.json", rec)
        raise SystemExit(f"{args.arm} rc {rc}")
    wjson(done, rec)


# ---------------------------------------------------------------- real data


def cmd_fetchms(args):
    """Channel tiles 5-8 of DATA, FLAG, WEIGHT_SPECTRUM and the row columns of one group.

    `--phase meta` fetches the group's attributes, every column's metadata and the TIME
    column (no visibility); `--phase data` the rest. Subtables are linked from --src."""
    import floor6_tests as f6

    root, src = Path(args.root).expanduser(), Path(args.src).expanduser()
    (root / "MAIN").mkdir(parents=True, exist_ok=True)
    for sub in src.iterdir():
        if sub.name != "MAIN" and not (root / sub.name).exists():
            (root / sub.name).symlink_to(sub)
    g = f"{TRACK}/MAIN/{args.group}"
    gd = root / "MAIN" / args.group
    fn = root / f"manifest-{args.group}-{args.phase}.json"
    if fn.exists():
        return
    rec = {
        "source": f6.BUCKET,
        "licence": "CC BY 4.0; cite Ramatsoku et al. 2020, A&A 636, L1",
        "purpose": f"ms1_target.zarr {args.group}, research/sdm03-default.md",
        "phase": args.phase,
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": [],
    }
    keys = []
    if args.phase == "meta":
        for s in (".zattrs", ".zgroup"):
            keys.append(f"{g}/{s}")
        for col in ROWCOLS + CUBES:
            for s in (".zarray", ".zattrs"):
                keys.append(f"{g}/{col}/{s}")
        keys = [k for k in keys if f6._exists(k) is not None]
        for k in keys:
            f6._get(k, root.parent / k.removeprefix("ESO137/"), rec)
        cols = ("TIME",)
    else:
        cols = [c for c in ROWCOLS if c != "TIME"] + list(CUBES)
    tm = json.loads((gd / "TIME/.zarray").read_text())
    nr = math.ceil(tm["shape"][0] / tm["chunks"][0])
    keys = []
    for col in cols:
        meta = json.loads((gd / col / ".zarray").read_text())
        nd = len(meta["shape"])
        for r in range(nr):
            if col in CUBES:
                keys += [f"{g}/{col}/{r}.{t}.0" for t in TILES]
            else:
                keys.append(f"{g}/{col}/" + ".".join([str(r)] + ["0"] * (nd - 1)))
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        list(
            ex.map(
                lambda k: f6._get(k, root.parent / k.removeprefix("ESO137/"), rec), keys
            )
        )
    rec["bytes"] = sum(x["bytes"] for x in rec["files"])
    rec["objects"] = len(rec["files"])
    wjson(fn, rec)
    print(
        f"fetchms {args.group} {args.phase}: {rec['objects']} objects, {rec['bytes']} bytes"
    )


def cmd_real(args, rest):
    import floor6_tests as f6

    f6.MAIN = args.group
    f6.main(rest)


# ---------------------------------------------------------------- simulated skies


def _bench():
    return _load("gemclean_bench_compare", HERE / "gemclean_bench_compare.py")


def _g3():
    return _load("g3_spectral_simulate", HERE / "g3_spectral_simulate.py")


def cmd_simprep(args):
    out = Path(args.out)
    if (out / "truth.json").exists():
        return
    bc = _bench()
    if not (out / "meta.json").exists():
        bc.prepare(
            argparse.Namespace(
                ms=args.ms,
                catalogue=args.catalogue,
                out_dir=str(out),
                datacol="DATA",
                field=0,
                size=2048,
                scale=1.5,
                epsilon=1e-6,
                wsclean_dirty=[],
                noise=None,
            )
        )
    ex = bc.Exact(out)
    g3 = _g3()
    cat = rjson(args.catalogue)
    arr = g3.arrays(cat["components"])
    truth = g3.predict(ex.uvw, ex.freq, arr)
    np.save(out / "truth.npy", truth)
    wjson(out / "truth.json", {"catalogue": str(Path(args.catalogue).resolve())})
    print(f"simprep {out}: done")


class Scorer:
    """Section 3.2: exact residual floor outside the truth mask, recovery, false flux."""

    def __init__(self, prep):
        self.prep = Path(prep)
        bc = _bench()
        self.ex = bc.Exact(self.prep)
        self.meta = self.ex.meta
        self.size = self.meta["size"]
        self.scale = self.meta["scale_arcsec"]
        self.chan_w = self.ex.wgt.sum(axis=0)  # Briggs weight per channel
        self.cat = rjson(self.meta["catalogue"])
        lo, hi = self.size // 2 - self.size // 3, self.size // 2 + self.size // 3
        self.inner = np.zeros((self.size, self.size), bool)
        self.inner[lo:hi, lo:hi] = True
        self.beam_px = None

    def set_beam(self, beam_arcsec):
        self.beam_px = beam_arcsec / self.scale
        yy, xx = np.mgrid[0 : self.size, 0 : self.size]
        near = np.zeros((self.size, self.size), bool)
        for c in self.cat["components"]:
            r = 3 * self.beam_px + (
                c.get("fwhm_px", 0.0) if c["kind"] == "gaussian" else 0
            )
            near |= (xx - c["x"]) ** 2 + (yy - c["y"]) ** 2 <= r * r
        self.sel = self.inner & ~near
        self.yy, self.xx = yy, xx

    def residual(self, e):
        from rang import core_wgridder

        r = core_wgridder.vis2dirty(
            uvw=self.ex.uvw,
            freq=self.ex.freq,
            vis=e,
            wgt=self.ex.wgt,
            npix_x=self.size,
            npix_y=self.size,
            **self.ex.kw,
        )
        return r.T

    def floor(self, img):
        if self.beam_px is None:
            raise SystemExit("beam not set")
        return float(np.sqrt(np.mean(img[self.sel] ** 2)))

    def groups(self, nout):
        n = self.ex.freq.size
        return [np.arange(k * n // nout, (k + 1) * n // nout) for k in range(nout)]

    def predict(self, planes):
        from rang import core_wgridder

        nout = len(planes)
        M = np.zeros_like(self.ex.vis)
        for k, idx in enumerate(self.groups(nout)):
            m = np.ascontiguousarray(planes[k].T, np.float64)
            M[:, idx] = core_wgridder.dirty2vis(
                uvw=self.ex.uvw, freq=self.ex.freq[idx], dirty=m, **self.ex.kw
            )
        return M

    def measures(self, planes, T):
        nout = len(planes)
        F = self.floor(self.residual(self.ex.vis - self.predict(planes)))
        gw = np.array([self.chan_w[idx].sum() for idx in self.groups(nout)])
        gw = gw / gw.sum()
        far = np.ones((self.size, self.size), bool)
        for c in self.cat["components"]:
            r = 2 * self.beam_px + (
                c.get("fwhm_px", 0.0) if c["kind"] == "gaussian" else 0
            )
            far &= (self.xx - c["x"]) ** 2 + (self.yy - c["y"]) ** 2 > r * r
        false = float(
            sum(w * np.abs(p[far]).sum() for w, p in zip(gw, planes, strict=True))
        )
        ratios = []
        for c in self.cat["components"]:
            if c["kind"] != "point":
                continue
            spec = np.asarray(c["flux_per_channel"])
            if float(np.average(spec, weights=self.chan_w)) < 50 * T:
                continue
            disc = (self.xx - c["x"]) ** 2 + (self.yy - c["y"]) ** 2 <= 36.0
            for k, idx in enumerate(self.groups(nout)):
                want = float(np.average(spec[idx], weights=self.chan_w[idx]))
                ratios.append(float(planes[k][disc].sum()) / want)
        ratios = np.array(ratios)
        return {
            "F": F,
            "P": F * F - T * T,
            "false_flux_jy": false,
            "recovery_n": int(ratios.size),
            "recovery_median": float(np.median(ratios)) if ratios.size else None,
            "recovery_abs_err_median": (
                float(np.median(np.abs(ratios - 1))) if ratios.size else None
            ),
        }


def planes_of(prefix):
    from rang.core_imaging import read_fits

    prefix = Path(prefix)
    one = Path(str(prefix) + "-model.fits")
    files = (
        [one]
        if one.exists()
        else sorted(prefix.parent.glob(prefix.name + "-0*-model.fits"))
    )
    if not files:
        raise SystemExit(f"no model for {prefix}")
    out = []
    for f in files:
        img, _ = read_fits(f)
        out.append(np.asarray(img, np.float64).reshape(img.shape[-2:]))
    return out, files


def restoring_beam_arcsec(prefix):
    """sqrt(BMAJ BMIN) of A0's restored image header (the truth mask's beam)."""
    from astropy.io import fits

    with fits.open(str(prefix) + "-image.fits") as h:
        hd = h[0].header
        return math.sqrt(float(hd["BMAJ"]) * float(hd["BMIN"])) * 3600.0


def cmd_simscore(args):
    out = Path(args.out)
    S = Scorer(out)
    tj = rjson(out / "truth.json")
    specs = dict(s.split("=", 1) for s in args.arms)
    if "beam_arcsec" not in tj:
        tj["beam_arcsec"] = restoring_beam_arcsec(specs["A0"])
        tj["beam_from"] = specs["A0"] + "-image.fits"
        wjson(out / "truth.json", tj)
    S.set_beam(tj["beam_arcsec"])
    if "T" not in tj:
        tj["T"] = S.floor(S.residual(S.ex.vis - np.load(out / "truth.npy")))
        wjson(out / "truth.json", tj)
    T = tj["T"]
    (out / "scores").mkdir(exist_ok=True)
    for arm, prefix in specs.items():
        fn = out / "scores" / f"{arm}.json"
        if fn.exists():
            continue
        planes, files = planes_of(prefix)
        rec = {"arm": arm, "prefix": prefix, "files": [str(f) for f in files], "T": T}
        rec.update(S.measures(planes, T))
        wjson(fn, rec)
        print(f"simscore {out.name} {arm}: F {rec['F'] * 1e6:.3f} uJy T {T * 1e6:.3f}")


# ---------------------------------------------------------------- summary (section 7)


def _time_line(log, name):
    """`TIME name wall s rss KB` from /usr/bin/time in a launch log."""
    if not Path(log).exists():
        return None
    for line in reversed(Path(log).read_text(errors="replace").splitlines()):
        p = line.split()
        if len(p) >= 6 and p[0] == "TIME" and p[1] == name:
            return {"wall_s": float(p[2]), "rss_gib": float(p[4]) / 2**20}
    return None


def real_readings(state, logs, tag):
    st = Path(state)
    if not (st / "pilot.json").exists():
        return {"arms": {}}
    pj = rjson(st / "pilot.json")
    T = pj["T"]
    arms = {}
    for f in sorted((st / "family2").glob("*.json")):
        if f.name.endswith("-mask.json"):
            continue
        r = rjson(f)
        if "F_uJy" in r:
            arms[r["arm"]] = r
    out = {"T": T, "P_ref": pj.get("P_ref"), "arms": {}}
    if "A0" not in arms:
        return out
    PA = (arms["A0"]["F_uJy"] * 1e-6) ** 2 - T * T
    out["P_A0"] = PA
    out["GT_A0"] = T / (arms["A0"]["F_uJy"] * 1e-6)
    for a, r in arms.items():
        F = r["F_uJy"] * 1e-6
        P = F * F - T * T
        x = {"F_uJy": r["F_uJy"], "P": P, "D": (PA - P) / PA, "report": r.get("report")}
        if pj.get("P_ref"):
            x["D_ref"] = (pj["P_ref"] - P) / pj["P_ref"]
        if logs:
            x["cost"] = _time_line(Path(logs) / f"arm-{tag}-{a}.log", f"arm-{tag}-{a}")
        out["arms"][a] = x
    gh = st / "build/GH.json"
    out["gates"] = {
        "GH": rjson(gh)["pass"] if gh.exists() else None,
        "GS1": pj.get("Sp_health", {}).get("pass"),
        "HB": pj.get("HB", {}).get("pass"),
        "GT": out["GT_A0"] <= 0.3,
    }
    return out


def sim_readings(d):
    d = Path(d)
    out = {"arms": {}}
    if not (d / "scores").exists():
        return out
    for f in sorted((d / "scores").glob("*.json")):
        r = rjson(f)
        out["arms"][r["arm"]] = r
    if "A0" in out["arms"]:
        PA = out["arms"]["A0"]["P"]
        for r in out["arms"].values():
            r["D"] = (PA - r["P"]) / PA
    return out


def no_harm(sim, arm):
    a, x = sim["arms"].get("A0"), sim["arms"].get(arm)
    if a is None or x is None:
        return None
    n1 = x["D"] >= -0.05
    n2 = x["false_flux_jy"] <= 1.1 * a["false_flux_jy"] + 1e-4
    n3 = (
        x["recovery_abs_err_median"] is not None
        and x["recovery_abs_err_median"] <= a["recovery_abs_err_median"] + 0.005
        and abs(x["recovery_median"] - 1) <= 0.02
    )
    return {"N1": n1, "N2": n2, "N3": bool(n3), "pass": bool(n1 and n2 and n3)}


def oracle(r, arm):
    g, w = r["arms"].get(arm), r["arms"].get("W-" + arm)
    if g is None or w is None:
        return None
    ok = g["P"] <= 1.25 * w["P"] or abs(g["D"] - w["D"]) <= 0.05
    return {
        "P_ratio": g["P"] / w["P"] if w["P"] else None,
        "dD": g["D"] - w["D"],
        "pass": ok,
    }


def cost(r, arm):
    a, x = r["arms"].get("A0", {}).get("cost"), r["arms"].get(arm, {}).get("cost")
    if not a or not x:
        return None
    c1 = x["wall_s"] <= 6 * a["wall_s"] and x["wall_s"] <= 3600
    c2 = x["rss_gib"] <= 3 * a["rss_gib"] and x["rss_gib"] <= 48
    return {
        "wall_ratio": x["wall_s"] / a["wall_s"],
        "rss_ratio": x["rss_gib"] / a["rss_gib"],
        "C1": c1,
        "C2": c2,
        "near_bound": bool(
            x["wall_s"] / a["wall_s"] > 0.8 * 6
            or x["wall_s"] > 0.8 * 3600
            or x["rss_gib"] / a["rss_gib"] > 0.8 * 3
            or x["rss_gib"] > 0.8 * 48
        ),
    }


def verdict(real, sims):
    """Section 7, in its order of precedence."""
    need_real = ["A0", "SDa", "Sa", "SDm03", "Sm", "W-SDa"]
    ok_scans = {
        k: v
        for k, v in real.items()
        if v.get("gates")
        and all(v["gates"].values())
        and all(a in v["arms"] for a in need_real)
    }
    sims_ok = all(
        all(a in s["arms"] for a in ("A0", "SDa", "Sa", "W-SDa")) for s in sims.values()
    )
    D = lambda arm: [v["arms"][arm]["D"] for v in ok_scans.values()]
    if len(ok_scans) < 2 or len(sims) < 4 or not sims_ok:
        return "incomplete", {"scans_ok": list(ok_scans), "sims_ok": sims_ok}
    dsda, dsa, dlit = D("SDa"), D("Sa"), D("SDm03")
    sa_ship = max(x - y for x, y in zip(dsda, dsa, strict=True)) < 0.05
    nh = {arm: {k: no_harm(s, arm) for k, s in sims.items()} for arm in ("SDa", "Sa")}
    orc = {k: oracle(v, "SDa") for k, v in ok_scans.items()}
    orc.update({k: oracle(s, "SDa") for k, s in sims.items()})
    detail = {
        "D_SDa": dsda,
        "D_Sa": dsa,
        "D_SDm03": dlit,
        "no_harm": nh,
        "oracle_SDa": orc,
    }

    def switch_ok(arm):
        cs = [cost(v, arm) for v in ok_scans.values()]
        return (
            min(D(arm)) >= 0.25
            and all(x["pass"] for x in nh[arm].values())
            and all(c and c["C1"] and c["C2"] for c in cs)
        )

    shipped = "Sa" if (sa_ship and switch_ok("Sa")) else "SDa"
    detail["shipped_form"] = shipped
    detail["cost"] = {
        k: {a: cost(v, a) for a in ("SDa", "Sa")} for k, v in ok_scans.items()
    }
    if shipped == "Sa":
        orc_sa = {k: oracle(v, "Sa") for k, v in ok_scans.items()}
        orc_sa.update({k: oracle(s, "Sa") for k, s in sims.items()})
        detail["oracle_Sa"] = orc_sa
        orc_ship = orc_sa
    else:
        orc_ship = orc
    if any(x is None for x in orc_ship.values()):
        return "incomplete", detail
    if not all(x["pass"] for x in nh[shipped].values()) or not all(
        x["pass"] for x in orc_ship.values()
    ):
        return "not yet", detail
    if (
        min(max(a, b) for a, b in zip(dsda, dsa, strict=True)) < 0.10
        and min(dlit) >= 0.10
    ):
        return "not yet", detail
    if switch_ok(shipped) and all(x["pass"] for x in orc_ship.values()):
        return "switch", detail
    for arm in ("SDa", "Sa"):
        if min(D(arm)) >= 0.10 and all(x["pass"] for x in nh[arm].values()):
            detail["opt_in_form"] = arm
            return "keep opt-in", detail
    return "null", detail


def cmd_summary(args):
    real = {}
    for spec in args.real:
        name, state, tag = spec.split("=")
        real[name] = real_readings(state, args.logs, tag)
    seen = {}
    for spec in args.seen:
        name, state, tag = spec.split("=")
        seen[name] = real_readings(state, args.logs, tag)
    sims = {}
    for spec in args.sim:
        name, d = spec.split("=")
        sims[name] = sim_readings(d)
    seen_sims = {}
    for spec in args.seen_sim:
        name, d = spec.split("=")
        seen_sims[name] = sim_readings(d)
    outcome, detail = verdict(real, sims)
    s = {
        "outcome": outcome,
        "detail": detail,
        "real": real,
        "sims": sims,
        "seen": seen,
        "seen_sims": seen_sims,
    }
    wjson(args.out, s)
    print(
        "SDM03 SUMMARY",
        outcome,
        json.dumps({k: detail.get(k) for k in ("D_SDa", "D_Sa", "D_SDm03")}),
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    rest = []
    if "--" in argv:
        i = argv.index("--")
        argv, rest = argv[:i], argv[i + 1 :]
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="stage", required=True)
    for name in ("argv", "image"):
        q = sub.add_parser(name)
        q.add_argument("arm", choices=[*ARMS, "W-SDa", "W-Sa"])
        q.add_argument("--kind", choices=sorted(BASE), required=True)
        q.add_argument("--ms", required=True)
        q.add_argument("--prefix", required=True)
        q.add_argument("--mask")
        q.add_argument("--column", default="CORRECTED_DATA")
    q = sub.add_parser("fetchms")
    q.add_argument("--group", required=True)
    q.add_argument("--root", required=True)
    q.add_argument("--src", required=True)
    q.add_argument("--phase", choices=["meta", "data"], required=True)
    q = sub.add_parser("real")
    q.add_argument("--group", required=True)
    q = sub.add_parser("simprep")
    q.add_argument("ms")
    q.add_argument("catalogue")
    q.add_argument("out")
    q = sub.add_parser("simscore")
    q.add_argument("out")
    q.add_argument("arms", nargs="+")
    q = sub.add_parser("summary")
    q.add_argument("out")
    q.add_argument("--real", nargs="*", default=[])
    q.add_argument("--seen", nargs="*", default=[])
    q.add_argument("--sim", nargs="*", default=[])
    q.add_argument("--seen-sim", nargs="*", default=[])
    q.add_argument("--logs")
    a = p.parse_args(argv)
    if a.stage == "argv":
        fn = wsclean_argv if a.arm.startswith("W-") else gemclean_argv
        print(json.dumps(fn(a.arm, a.kind, a.ms, a.prefix, a.column, a.mask)[0]))
    elif a.stage == "image":
        cmd_image(a)
    elif a.stage == "fetchms":
        cmd_fetchms(a)
    elif a.stage == "real":
        cmd_real(a, rest)
    elif a.stage == "simprep":
        cmd_simprep(a)
    elif a.stage == "simscore":
        cmd_simscore(a)
    elif a.stage == "summary":
        cmd_summary(a)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
