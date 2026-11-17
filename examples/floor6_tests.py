# SPDX-License-Identifier: MIT
"""floor-6 (research/floor-6.md): held-out checks of floor-5's H9 (Dm03) and H8 (S).

The held-out set is ms1_target.zarr MAIN_4 (scan 10), built by the pilot's recipe. Imports
floor_tests, floor3_score, floor5_tests and gemclean_heldout_real unchanged; set A's mask and the
pilot's model (for the peak) stay on the pilot folder (--held). Stages:

    meta      section 2's conditions from metadata only (field, phase centre, time span)
    fetch     the publisher's GKB-net gains for MAIN_4 (metadata first, then the chosen group)
    build     convert, verify, gainload, gaincheck, calibrate, average (MAIN_4 in place of MAIN_0)
    copy      floor3_score's four-correlation copy into OUT/P/pilot.ms
    state     prep, T (noise only, seed 1301), S1, F_B, F_Fix, F_ref, HB, Sp health
    score     floor5_tests.cmd_score on the state, T passed explicitly
    summary   gates and the frozen readings of section 7

Every stage skips what it has already written, so the driver can be rerun.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import floor3_score as f3
import floor5_tests as f5
import floor_tests as ft
from rang import cal_selfcal, core_ms
from rang.core_imaging import read_fits

_spec = importlib.util.spec_from_file_location("ghr", HERE / "gemclean_heldout_real.py")
ghr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ghr)

MAIN = "MAIN_4"
BUCKET = "https://ratt-public-data.s3.af-south-1.amazonaws.com"
GROOT = "ESO137/ms1_gains.qc/GKB-net"
T_PILOT = 44.09023909930619e-6  # floor-5's T
PILOT_F5 = {  # floor-5 results/floor-5: pilot.json HB, family2/*.json
    "F_ref": 379.2615718666121,
    "F_B": 1073.415606729187,
    "F_Fix": 474.83100062889406,
    "fR3": 379.2621316115116,
    "fDm03": 334.8257705983144,
    "fS": 342.63664582758616,
}
D_PILOT = {"H9": 0.224, "H8": 0.186}  # floor-5 10.1 (rounded as frozen)
KAPPA_MIN_SPAN = 0.5  # clarification 1: kappa is read only if P_B - P_ref >= 0.5 P_ref


def main_group(root):
    return Path(root) / "MAIN" / MAIN


ghr.main_group = main_group


def wjson(path, value):
    ft.wjson(path, value)


def held_paths(held):
    """Mask and pilot model from the pilot folder (never the held-out build)."""
    held = Path(held).expanduser()
    ft.HELD = held
    ft.MASK = held / "images/source-mask.fits"
    ft.PILOT = held / "run/cal2-003-gem-model.fits"
    ft.TRUTH = held / "run/cal3-003-gem-model.fits"


def fits2d(p):
    img, _ = read_fits(p)
    return np.asarray(img, np.float64).reshape(img.shape[-2:])


# ---------------------------------------------------------------- meta and fetch


def cmd_meta(out, zarr, pilot_ms):
    fn = out / "meta.json"
    if fn.exists():
        return json.loads(fn.read_text())
    root = Path(zarr)
    main = main_group(root)
    nrow, nchunks = ghr.row_chunks(root)
    fid = np.unique(
        np.concatenate([ghr.row_column(main, "FIELD_ID", r) for r in range(nchunks)])
    )
    times = np.unique(
        np.concatenate([ghr.row_column(main, "TIME", r) for r in range(nchunks)])
    )
    try:
        scans = np.unique(
            np.concatenate(
                [ghr.row_column(main, "SCAN_NUMBER", r) for r in range(nchunks)]
            )
        )
    except (OSError, KeyError, ValueError):  # a store without the column
        scans = np.array([])
    pd = ghr.whole(root / "FIELD/FIELD_0/PHASE_DIR").reshape(-1, 2)
    with core_ms.open_table(str(Path(pilot_ms) / "FIELD")) as f:
        ppd = np.asarray(f.getcol("PHASE_DIR", 0, 1), np.float64).reshape(-1)[:2]
    sep = [float(np.hypot(*(pd[int(i)] - ppd)) / ft.ARC) for i in fid]
    span = float(times[-1] - times[0])
    r = {
        "zarr": str(root),
        "main": MAIN,
        "rows": int(nrow),
        "row_chunks": int(nchunks),
        "field_ids": fid.tolist(),
        "scans": scans.tolist(),
        "phase_dir_sep_arcsec": sep,
        "ntime": int(times.size),
        "time_first": float(times[0]),
        "time_last": float(times[-1]),
        "span_s": span,
        "nfield_rows": int(pd.shape[0]),
    }
    r["one_field"] = len(fid) == 1
    r["phase_ok"] = bool(r["one_field"] and sep[0] <= 0.01)
    r["span_ok"] = span >= 15 * 60
    wjson(fn, r)
    ft.log("meta", r)
    return r


def _get(key, path, rec):
    path.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with (
        urllib.request.urlopen(f"{BUCKET}/{key}", timeout=300) as f,
        open(path, "wb") as o,
    ):
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
            o.write(b)
    rec["files"].append(
        {"key": key, "bytes": path.stat().st_size, "sha256": h.hexdigest()}
    )


def _exists(key):
    q = urllib.request.Request(f"{BUCKET}/{key}", method="HEAD")
    try:
        with urllib.request.urlopen(q, timeout=60) as f:
            return int(f.headers["Content-Length"])
    except OSError:  # HTTPError and URLError are OSError
        return None


def cmd_fetch(out, zarr, gains_dir):
    gd = Path(gains_dir)
    fn = gd / "manifest.json"
    if fn.exists():
        return
    meta = json.loads((out / "meta.json").read_text())
    rec = {
        "source": BUCKET,
        "licence": "CC BY 4.0; cite Ramatsoku et al. 2020, A&A 636, L1",
        "purpose": "GKB-net gains for ms1_target.zarr MAIN_4, research/floor-6.md",
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": [],
        "groups": {},
    }
    rows_t = np.unique(
        np.concatenate(
            [
                ghr.row_column(main_group(zarr), "TIME", r)
                for r in range(meta["row_chunks"])
            ]
        )
    )
    chosen = None
    for k in range(16):
        g = f"{GROOT}/GKB-net_{k}"
        if _exists(f"{g}/gain_time/.zarray") is None:
            rec["groups"][k] = None
            continue
        for a in ("gain_time", "gain_freq", "gains", "gain_flags"):
            for s in (".zarray", ".zattrs"):
                if _exists(f"{g}/{a}/{s}") is not None:
                    _get(f"{g}/{a}/{s}", gd / g / a / s, rec)
        for s in (".zattrs", ".zgroup"):
            if _exists(f"{g}/{s}") is not None:
                _get(f"{g}/{s}", gd / g / s, rec)
        tm = ghr.meta_of(gd / g / "gain_time")
        nt = math.ceil(tm["shape"][0] / tm["chunks"][0])
        for i in range(nt):
            _get(f"{g}/gain_time/{i}", gd / g / "gain_time" / str(i), rec)
        gt = np.concatenate(
            [ghr.decode(gd / g / "gain_time", str(i))[0] for i in range(nt)]
        )[: tm["shape"][0]]
        i = np.clip(np.searchsorted(gt, rows_t), 0, len(gt) - 1)
        j = np.clip(i - 1, 0, len(gt) - 1)
        dt = np.minimum(np.abs(gt[i] - rows_t), np.abs(gt[j] - rows_t)).max()
        rec["groups"][k] = {"ntime": int(gt.size), "max_row_gap_s": float(dt)}
        if dt <= 1.0 and chosen is None:
            chosen = k
    rec["chosen"] = chosen
    if chosen is None:
        wjson(gd / "manifest-nochoice.json", rec)
        raise SystemExit("no GKB-net group covers MAIN_4 within 1 s")
    g = f"{GROOT}/GKB-net_{chosen}"
    gm = ghr.meta_of(gd / g / "gains")
    fm = ghr.meta_of(gd / g / "gain_freq")
    nt = math.ceil(gm["shape"][0] / gm["chunks"][0])
    cf = gm["chunks"][1]
    fch = list(range(ghr.CHAN0 // cf, (ghr.CHAN1 - 1) // cf + 1))
    for f in fch:
        _get(f"{g}/gain_freq/{f}", gd / g / "gain_freq" / str(f), rec)
        for t in range(nt):
            _get(f"{g}/gains/{t}.{f}.0.0.0", gd / g / "gains" / f"{t}.{f}.0.0.0", rec)
            _get(
                f"{g}/gain_flags/{t}.{f}.0.0",
                gd / g / "gain_flags" / f"{t}.{f}.0.0",
                rec,
            )
    rec["freq_chunks"] = fch
    rec["time_chunks"] = nt
    rec["gain_freq_chunk"] = fm["chunks"][0]
    rec["bytes"] = sum(x["bytes"] for x in rec["files"])
    wjson(fn, rec)
    ft.log("fetch", chosen, rec["bytes"], "bytes")


def gainload(gains_dir, zarr, out_npz):
    """gemclean_heldout_real.gainload for the chosen group, all its time chunks."""
    gd = Path(gains_dir)
    man = json.loads((gd / "manifest.json").read_text())
    root = gd / f"{GROOT}/GKB-net_{man['chosen']}"
    gm = ghr.meta_of(root / "gains")
    fm = ghr.meta_of(root / "gain_flags")
    tm = ghr.meta_of(root / "gain_time")
    if gm["dtype"] != "<c16" or fm["dtype"] != "|i1":
        raise SystemExit("unexpected gain dtype")
    nt_chunks = math.ceil(tm["shape"][0] / tm["chunks"][0])
    gtime = np.concatenate(
        [ghr.decode(root / "gain_time", str(i))[0] for i in range(nt_chunks)]
    )[: tm["shape"][0]]
    cf = gm["chunks"][1]
    fch = man["freq_chunks"]
    gfm = ghr.meta_of(root / "gain_freq")
    gfreq = {}
    for f in fch:
        a = ghr.decode(root / "gain_freq", str(f))[0]
        gfreq[f] = a
    nt, nf, na = gm["shape"][0], ghr.CHAN1 - ghr.CHAN0, gm["shape"][2]
    gains = np.zeros((nt, nf, na, 2), np.complex128)
    flags = np.zeros((nt, nf, na), bool)
    freq = np.zeros(nf)
    for ti, t0 in enumerate(range(0, nt, gm["chunks"][0])):
        n = min(gm["chunks"][0], nt - t0)
        for f in fch:
            f0 = f * cf
            g, _ = ghr.decode(root / "gains", f"{ti}.{f}.0.0.0")
            g = g.reshape(gm["chunks"][0], cf, na, 1, 2)[:n, :, :, 0]
            fl, _ = ghr.decode(root / "gain_flags", f"{ti}.{f}.0.0")
            fl = fl.reshape(fm["chunks"][0], cf, na, 1)[:n, :, :, 0]
            lo, hi = max(f0, ghr.CHAN0), min(f0 + cf, ghr.CHAN1)
            gains[t0 : t0 + n, lo - ghr.CHAN0 : hi - ghr.CHAN0] = g[
                :, lo - f0 : hi - f0
            ]
            flags[t0 : t0 + n, lo - ghr.CHAN0 : hi - ghr.CHAN0] = (
                fl[:, lo - f0 : hi - f0] != 0
            )
            if ti == 0:
                gf = gfreq[f][: gfm["chunks"][0]]
                freq[lo - ghr.CHAN0 : hi - ghr.CHAN0] = gf[lo - f0 : hi - f0]
    sub = ghr.subtable_arrays(zarr)
    rec = {
        "group": man["chosen"],
        "gain_freq_vs_chan_freq_max_hz": float(np.abs(freq - sub["freq"]).max()),
        "gain_times": len(gtime),
        "gain_flag_fraction": float(flags.mean()),
        "gain_nonfinite": int((~np.isfinite(gains)).sum()),
        "amp_median": float(np.median(np.abs(gains[~flags]))),
    }
    ft.log("gainload", rec)
    np.savez(out_npz, gains=gains, flags=flags, gain_time=gtime, freq=sub["freq"])
    wjson(str(out_npz) + ".json", rec)


def gaincheck(zarr, gains_npz, out_json, nchunks):
    """gemclean_heldout_real.gaincheck's Stokes I band coherence on chunks 0 and middle."""
    main = main_group(zarr)
    g = np.load(gains_npz)
    gains, gflags, gtime = g["gains"], g["flags"], g["gain_time"]
    rec = {}
    for r in sorted({0, nchunks // 2}):
        data = ghr.cube(main, "DATA", r)
        flag = ghr.cube(main, "FLAG", r)
        weight = ghr.cube(main, "WEIGHT_SPECTRUM", r)
        a1, a2 = (
            ghr.row_column(main, "ANTENNA1", r),
            ghr.row_column(main, "ANTENNA2", r),
        )
        times = ghr.row_column(main, "TIME", r)
        keep = a1 != a2
        data, flag, weight = data[keep], flag[keep], weight[keep]
        a1, a2, times = a1[keep], a2[keep], times[keep]
        ti = ghr.time_index(gtime, times)
        out = {}
        for name, corr in (
            ("raw", None),
            ("vis_over_gp_gqH", "qc"),
            ("other", "conjugate"),
        ):
            xx, fx, wx = data[..., 0], flag[..., 0], weight[..., 0]
            yy, fy, wy = data[..., 3], flag[..., 3], weight[..., 3]
            if corr:
                xx, fx, wx = ghr.correct(xx, fx, wx, gains, gflags, ti, a1, a2, 0, corr)
                yy, fy, wy = ghr.correct(yy, fy, wy, gains, gflags, ti, a1, a2, 1, corr)
            good = ~(fx | fy) & (wx > 0) & (wy > 0)
            i_ = np.where(good, 0.5 * (xx + yy), 0)
            n = good.reshape(len(good), -1, 32).sum(axis=2)
            s = i_.reshape(len(good), -1, 32).sum(axis=2)
            m = np.abs(i_).reshape(len(good), -1, 32).sum(axis=2)
            coh = np.abs(s) / np.maximum(m, 1e-30)
            a = np.where(good, xx * np.conj(yy), 0).sum(axis=1)
            out[name] = {
                "stokes_i_32chan_coherence_median": float(np.median(coh[n >= 16])),
                "xx_yy_phase_abs_median_rad": float(np.median(np.abs(np.angle(a)))),
                "good_fraction": float(good.mean()),
            }
        rec[f"row_chunk_{r}"] = out
    c = list(rec.values())
    rec["pass"] = bool(
        all(
            x["vis_over_gp_gqH"]["stokes_i_32chan_coherence_median"]
            > max(
                x["raw"]["stokes_i_32chan_coherence_median"],
                x["other"]["stokes_i_32chan_coherence_median"],
            )
            for x in c
        )
    )
    wjson(out_json, rec)
    ft.log("gaincheck", rec)


def cmd_build(out, zarr, gains_dir):
    b = out / "build"
    b.mkdir(parents=True, exist_ok=True)
    meta = json.loads((out / "meta.json").read_text())

    def step(name, fn, done):
        if Path(done).exists():
            return
        s0 = time.perf_counter()
        fn()
        ft.log("build", name, f"{time.perf_counter() - s0:.1f} s")

    ns = argparse.Namespace
    step(
        "convert",
        lambda: ghr.convert(ns(zarr=zarr, ms=str(b / "raw.ms"))),
        b / "convert.done",
    )
    (b / "convert.done").touch()
    step(
        "verify",
        lambda: ghr.verify(
            ns(zarr=zarr, ms=str(b / "raw.ms"), out=str(b / "verify.json"))
        ),
        b / "verify.json",
    )
    step(
        "gainload",
        lambda: gainload(gains_dir, zarr, b / "gains.npz"),
        b / "gains.npz.json",
    )
    step(
        "gaincheck",
        lambda: gaincheck(
            zarr, b / "gains.npz", b / "gaincheck.json", meta["row_chunks"]
        ),
        b / "gaincheck.json",
    )
    step(
        "calibrate",
        lambda: ghr.calibrate(
            ns(
                zarr=zarr,
                gains=str(b / "gains.npz"),
                ms=str(b / "cal.ms"),
                raw=False,
                extra_flags=None,
            )
        ),
        b / "cal.ms.json",
    )
    step(
        "average",
        lambda: ghr.average(
            ns(
                ms_in=str(b / "cal.ms"),
                ms_out=str(b / "cal2.ms"),
                factor=2,
                flag_baselines=None,
            )
        ),
        b / "cal2.ms.json",
    )
    v = json.loads((b / "verify.json").read_text())
    gl = json.loads((b / "gains.npz.json").read_text())
    gc = json.loads((b / "gaincheck.json").read_text())
    gh = {
        "verify_identical": all(v["identical"].values()) and v["rows_equal"],
        "gain_freq_ok": gl["gain_freq_vs_chan_freq_max_hz"] <= 1.0,
        "gaincheck": gc["pass"],
    }
    gh["pass"] = bool(all(gh.values()))
    wjson(b / "GH.json", gh)
    ft.log("GH", gh)


def cmd_copy(out):
    ft.HELD = (
        out / "build"
    )  # cmd_copy reads HELD/cal2.ms; mask/pilot stay set by held_paths
    f3.cmd_copy(out, "P")


# ---------------------------------------------------------------- state


def g1_products(g1):
    return f5.g1_products(g1)


def cmd_state(out, cal2, g1, ms4, T_fixed=None):
    """The scoring state on `out`: prep of cal2, T, S1, F's, HB; out/pilot.json for cmd_score."""
    fn = out / "pilot.json"
    if fn.exists():
        return json.loads(fn.read_text())
    ft.MS_A = Path(cal2)
    ft.prep(out)
    d = ft.Data(out)
    T_noise = ft.floor(d, ft.grid(d, d.noise(ft.NOISE_SEED)))
    T = T_noise if T_fixed is None else T_fixed
    store, m0, m1 = g1_products(g1)
    h = f5.hands_prep(out / "hands", ft.CHANNELS, ms=cal2)
    v0, g0 = f5.stokes_from_hands(
        h["d"][..., 0], h["d"][..., 1], h["w"], h["f"], h["rows_ok"]
    )
    check = {
        "vis_equal": bool(np.array_equal(v0, d.vis)),
        "wnat_equal": bool(np.array_equal(g0, d.wnat)),
    }
    del v0, g0
    s1, w1 = f5.apply_store(h, store, d.a1, d.a2)
    newly = float(1 - np.count_nonzero(w1) / np.count_nonzero(d.wnat))
    np.save(out / "s1.npy", s1)
    M0 = ft.predict(d, fits2d(m0))
    F_B = ft.floor(d, ft.grid(d, d.vis - M0))
    F_Fix = ft.floor(d, ft.grid(d, s1 - M0))
    M1 = ft.predict(d, fits2d(m1))
    F_ref = ft.floor(d, ft.grid(d, s1 - M1))
    del M1
    # HB: the MS's own CORRECTED_DATA (floor3_score.prep_arm) on the same cells
    f3.prep_arm(out / "hb", ms4)
    ft.MS_A = Path(cal2)
    vc = np.load(out / "hb/prep/vis_corr.npy")
    F_Fix_ms = ft.floor(d, ft.grid(d, vc - M0))
    del M0, vc
    s = json.loads((Path(g1) / "P/run/selfcal/summary.json").read_text())
    rnd = s["fields"][0]["rounds"][0]
    _g, flags, _gt, _gf, _sc = cal_selfcal.read_store(store, "Sp")
    health = {
        "converged_fraction": rnd["solve"].get("converged_fraction"),
        "flagged_solution_fraction": float(np.mean(flags)),
        "round1_clean": rnd["image"]["clean"],
        "final_clean": s["fields"][0]["final_image"]["clean"],
        "gemclean_sha256": s.get("gemclean_sha256"),
    }
    health["pass"] = bool(
        (health["converged_fraction"] or 0) >= 0.9
        and health["flagged_solution_fraction"] <= 0.05
    )
    P = lambda F: F**2 - T**2
    r = {
        "none": {"F": F_ref},
        "T": T,
        "T_noise": T_noise,
        "F_B": F_B,
        "F_Fix": F_Fix,
        "F_Fix_ms": F_Fix_ms,
        "HB": {
            "check": check,
            "rel_Fix_ms": F_Fix / F_Fix_ms - 1,
            "newly_flagged": newly,
            "pass": bool(abs(F_Fix / F_Fix_ms - 1) <= 1e-4 and all(check.values())),
        },
        "GT": {"T_over_Fref": T / F_ref, "pass": bool(T / F_ref <= 0.3)},
        "Sp_health": health,
        "P_ref": P(F_ref),
        "P_B": P(F_B),
        "store": str(store),
        "m0": str(m0),
        "m1": str(m1),
        "active": d.meta["active"],
        "nrow": d.meta["nrow"],
        "noise_c": d.meta["noise_c"],
    }
    wjson(fn, r)
    ft.log(
        "state",
        out,
        {k: r[k] for k in ("T", "F_B", "F_Fix", "F_Fix_ms", "P_ref", "P_B")},
    )
    ft.log("state", out, "F_ref_uJy", F_ref * 1e6)
    return r


def cmd_score(out, specs):
    pil = json.loads((out / "pilot.json").read_text())
    f5.T = pil["T"]  # floor5_tests.P reads its module T: the state's own T
    f3.T = pil["T"]
    f5.cmd_score(out, specs)


# ---------------------------------------------------------------- summary


def _arm(dirp, name):
    p = dirp / "family2" / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def cmd_summary(out, pilot_out, fam_ho):
    ho = json.loads((out / "pilot.json").read_text())
    pi = json.loads((pilot_out / "pilot.json").read_text())
    res = {"held_out": {}, "pilot": {}, "gates": {}}
    meta = json.loads((out / "meta.json").read_text())
    gh = json.loads((out / "build/GH.json").read_text())
    res["gates"]["conditions"] = {
        k: meta[k] for k in ("one_field", "phase_ok", "span_ok")
    }
    res["gates"]["GH"] = gh
    res["gates"]["GS1"] = ho["Sp_health"]
    res["gates"]["HB"] = ho["HB"]
    res["gates"]["GT"] = ho["GT"]
    # GM: R3 against m1, pixel for pixel
    r3 = Path(fam_ho) / "R3/image-model.fits"
    gm = None
    if r3.exists():
        a, b = fits2d(r3), fits2d(ho["m1"])
        gm = {
            "pixel_identical": bool(np.array_equal(a, b)),
            "max_abs_diff": float(np.abs(a - b).max()),
        }
    res["gates"]["GM"] = gm
    # GP: the pin, on the pilot
    gp = {
        "F_ref_rel": pi["none"]["F"] * 1e6 / PILOT_F5["F_ref"] - 1,
        "F_B_rel": pi["F_B"] * 1e6 / PILOT_F5["F_B"] - 1,
        "F_Fix_rel": pi["F_Fix"] * 1e6 / PILOT_F5["F_Fix"] - 1,
        "T_noise_rel": pi["T_noise"] / T_PILOT - 1,
    }
    for k in ("fR3", "fDm03", "fS"):
        a = _arm(pilot_out, k)
        gp[f"{k}_rel"] = (a["F_uJy"] / PILOT_F5[k] - 1) if a else None
    gp["pass"] = bool(
        all(
            v is not None and abs(v) <= 1e-6
            for k, v in gp.items()
            if k not in ("T_noise_rel",)
        )
        and abs(gp["T_noise_rel"]) <= 5e-3
    )
    res["gates"]["GP"] = gp
    # every arm
    for side, dirp in (("held_out", out), ("pilot", pilot_out)):
        for p in sorted((dirp / "family2").glob("*.json")):
            a = json.loads(p.read_text())
            res[side][p.stem] = {
                "F_uJy": a["F_uJy"],
                "D": a["D"],
                "dP": a["dP"],
                "components": a["report"].get("components"),
                "major_cycles": a["report"].get("major_cycles"),
                "stop": a["report"].get("stop"),
                "outside_mask_jy": sum(m["outside_mask_jy"] for m in a["model"]),
                "outside_mask_pixels": sum(
                    m["outside_mask_pixels"] for m in a["model"]
                ),
                "flux_jy": sum(m["flux_jy"] for m in a["model"]),
                "negative_jy": sum(m["negative_jy"] for m in a["model"]),
            }
    H = res["held_out"]
    base_ok = bool(
        meta["phase_ok"]
        and meta["span_ok"]
        and gh["pass"]
        and ho["Sp_health"]["pass"]
        and ho["HB"]["pass"]
        and ho["GT"]["pass"]
        and gp["pass"]
    )
    # GM failing: drops against R3's own score
    shift = 0.0
    if gm is not None and not gm["pixel_identical"] and "R3" in H:
        shift = H["R3"]["D"]
        res["gm_rebase"] = "drops taken against R3's own score"

    def rebased(name):
        if name not in H:
            return None
        if shift == 0.0:
            return H[name]["D"]
        Pr = ho["P_ref"] * (1 - shift)
        return (Pr - (ho["P_ref"] - H[name]["dP"])) / Pr

    out_v = {}
    kappa = None
    if "Dm03" in H and "C0" in H:
        span = ho["P_B"] - ho["P_ref"]
        kappa = (H["C0"]["dP"] - H["Dm03"]["dP"]) / span if span > 0 else None
    kappa_read = bool(
        kappa is not None and (ho["P_B"] - ho["P_ref"]) >= KAPPA_MIN_SPAN * ho["P_ref"]
    )
    for cause, arm in (("H9", "Dm03"), ("H8", "S")):
        Dp = D_PILOT[cause]
        delta = max(0.05, 0.25 * Dp)
        Dh = rebased(arm)
        row = {"arm": arm, "D_pilot": Dp, "delta": delta, "D_ho": Dh}
        if not base_ok or gm is None or Dh is None:
            v = "void"
        elif cause == "H9" and Dh >= 0.05 and kappa_read and kappa > 0.3:
            v = "not separated"
        elif Dh < 0.05:
            v = "not reproduced"
        elif Dh >= 0.10 and Dh >= Dp - delta:
            v = "confirmed" + (", larger" if Dh > Dp + delta else "")
        else:
            v = "smaller"
        row["outcome"] = v
        if cause == "H9":
            row["kappa"] = kappa
            row["kappa_read"] = kappa_read
            row["P_B_minus_P_ref_over_P_ref"] = (ho["P_B"] - ho["P_ref"]) / ho["P_ref"]
        out_v[cause] = row
    res["outcomes"] = out_v
    # secondary
    sec = {}
    for side, S in (("held_out", H), ("pilot", res["pilot"])):
        rm3 = S.get("Rm3" if side == "held_out" else "pRm3")
        sm3 = S.get("Sm3" if side == "held_out" else "pSm3")
        sd = S.get("SDm03" if side == "held_out" else "pSDm03")
        dm = S.get("Dm03" if side == "held_out" else "fDm03")
        ss = S.get("S" if side == "held_out" else "fS")
        x = {}
        if rm3 and sm3:
            x["dS_matched"] = sm3["D"] - rm3["D"]
        if sd and dm and ss:
            x["D_SDm03"] = sd["D"]
            x["additivity"] = sd["D"] / (dm["D"] + ss["D"])
        if side == "held_out" and "Dm1" in S:
            x["D_Dm1"] = S["Dm1"]["D"]
        sec[side] = x
    notes = []
    dsh = sec["held_out"].get("dS_matched")
    if dsh is not None and out_v["H8"]["D_ho"] is not None:
        if out_v["H8"]["D_ho"] >= 0.10 and dsh < 0.05:
            notes.append("S's drop is mostly unmasked flux, not spectral")
        if dsh >= 0.10:
            notes.append("spectral gain survives masking")
    sec["notes"] = notes
    res["secondary"] = sec
    res["sigma_ho"] = sum(
        r["D_ho"] for r in out_v.values() if r["outcome"].startswith("confirmed")
    )
    res["T_ho"] = ho["T"]
    res["F_ref_ho_uJy"] = ho["none"]["F"] * 1e6
    res["F_B_ho_uJy"] = ho["F_B"] * 1e6
    res["P_ref_ho"] = ho["P_ref"]
    res["base_gates_pass"] = base_ok
    wjson(out / "summary.json", res)
    ft.log(
        "FLOOR6 SUMMARY",
        json.dumps({k: v["outcome"] for k, v in out_v.items()}),
        json.dumps({k: v["D_ho"] for k, v in out_v.items()}, default=float),
        "kappa",
        kappa,
        "gates",
        base_ok,
    )


# ---------------------------------------------------------------- main


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "stage", choices=["meta", "fetch", "build", "copy", "state", "score", "summary"]
    )
    p.add_argument("name", nargs="*")
    p.add_argument("--out", required=True, help="state directory (held-out or pilot)")
    p.add_argument("--held", required=True, help="the pilot folder: mask, pilot model")
    p.add_argument("--zarr", default="~/rang-data/e2-a/ESO137/ms1_target.zarr")
    p.add_argument("--gains", help="gains directory (fetch, build)")
    p.add_argument("--cal2", help="state: the 2-correlation MS scored")
    p.add_argument("--g1", help="state: the directory holding P/run (selfcal)")
    p.add_argument("--ms4", help="state: the four-correlation MS with CORRECTED_DATA")
    p.add_argument(
        "--pilot-T", action="store_true", help="state: floor-5's T, not T_noise"
    )
    p.add_argument("--pilot-out", help="summary: the pilot state directory")
    p.add_argument("--fam", help="summary: the held-out GeMClean arm directory")
    a = p.parse_args(argv)
    held_paths(a.held)
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    zarr = str(Path(a.zarr).expanduser())
    s0 = time.perf_counter()
    if a.stage == "meta":
        r = cmd_meta(out, zarr, ft.HELD / "cal2.ms")
        if not (r["phase_ok"] and r["span_ok"]):
            raise SystemExit("candidate 2 fails section 2's conditions")
    elif a.stage == "fetch":
        cmd_fetch(out, zarr, a.gains)
    elif a.stage == "build":
        cmd_build(out, zarr, a.gains)
        if not json.loads((out / "build/GH.json").read_text())["pass"]:
            raise SystemExit("gate GH fails")
    elif a.stage == "copy":
        cmd_copy(out)
    elif a.stage == "state":
        cmd_state(out, a.cal2, a.g1, a.ms4, T_PILOT if a.pilot_T else None)
    elif a.stage == "score":
        cmd_score(out, a.name)
    elif a.stage == "summary":
        cmd_summary(out, Path(a.pilot_out).expanduser(), a.fam)
    ft.log("stage", a.stage, a.name, f"{time.perf_counter() - s0:.1f} s")


if __name__ == "__main__":
    main()
