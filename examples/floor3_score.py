"""floor-3 (research/floor-3.md): score `rang-core selfcal` Sp on the pilot with imaging-floor's metric.

Stages (ARM is P or PL; OUT/ARM holds the MS copy, the run directory and the scores):

    copy ARM     a fresh copy of cal2.ms into OUT/ARM/pilot.ms
    g0           gate G0 on OUT/P's copy before the stage: DATA against the archived pilot model
    score ARM    after `rang-core selfcal`: B, Fix and Fin, flags, and the solve's health
    summary      gates and the frozen readings of section 6
    clean ARM    delete the MS copy and the prep scratch of ARM

Uses floor_tests (unchanged) for the prep, the gridder and the floor.
"""

import argparse
import json
import math
import shutil
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import floor2_tests as f2
import floor_tests as ft
from rang import cal_selfcal, core_ms, core_weights
from rang.core_imaging import read_fits

REPO = Path(__file__).resolve().parents[1]
F_ARCH = 1073.42e-6  # floor-2 pilot F(none) = imaging-floor's, Jy
T = 44.09023909930619e-6
F2_GAINS = REPO / "research/results/floor-2/pilot-gains.npz"


def prep_arm(out, ms):
    """floor_tests.prep on `ms` (DATA), then the Stokes I CORRECTED_DATA on the same cells."""
    ft.MS_A = Path(ms)
    ft.prep(out)
    p = out / "prep"
    fn = p / "vis_corr.npy"
    if fn.exists() or not has_column(ms, "CORRECTED_DATA"):
        return
    n = json.loads((p / "meta.json").read_text())["nrow"]
    vis = np.empty((n, ft.CHANNELS.size), np.complex64)
    with core_ms.open_table(str(ms)) as t:
        rows_ok = ~np.asarray(t.getcol("FLAG_ROW", 0, n), bool)
        for r0 in range(0, n, ft.ROWS):
            k = min(ft.ROWS, n - r0)
            sel = np.sort(np.concatenate([ft.CHANNELS, ft.CHANNELS + 1]))
            d = t.getcol("CORRECTED_DATA", r0, k)[:, sel]
            w = t.getcol("WEIGHT_SPECTRUM", r0, k)[:, sel]
            f = t.getcol("FLAG", r0, k)[:, sel]
            if d.shape[-1] == 2:

                def full(x):
                    return np.stack(
                        [x[..., 0], x[..., 0], x[..., 1], x[..., 1]], axis=-1
                    )

                d, w, f = full(d), full(w), full(f)
            v, _g = core_weights.stokes_i(d, w, f)
            vis[r0 : r0 + k] = v[:, 0::2]
    del rows_ok
    np.save(fn, vis)


def has_column(ms, name):
    with core_ms.open_table(str(ms)) as t:
        return name in t.colnames()


def score_model(d, vis, model_path):
    img, _ = read_fits(model_path)
    img = np.asarray(img, np.float64).reshape(img.shape[-2:])
    return ft.floor(d, ft.grid(d, vis - ft.predict(d, img)))


def excess(F):
    return F**2 - T**2


def cmd_copy(out, arm):
    dst = out / arm / "pilot.ms"
    if dst.exists():
        return
    (out / arm).mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    shutil.copytree(ft.HELD / "cal2.ms", dst)
    ft.log("copy", arm, round(time.perf_counter() - s0, 1), "s")


def cmd_g0(out):
    q = out / "P"
    fn = q / "g0.json"
    if fn.exists():
        return
    if has_column(q / "pilot.ms", "CORRECTED_DATA"):
        raise SystemExit("G0 must run before the stage")
    prep_arm(q / "g0", q / "pilot.ms")
    d = ft.Data(q / "g0")
    F = score_model(d, d.vis.astype(np.complex64), ft.PILOT)
    r = {
        "F": F,
        "ratio": F / F_ARCH,
        "pass": abs(F / F_ARCH - 1) <= 0.001,
        "active": d.meta["active"],
    }
    ft.wjson(fn, r)
    ft.log("g0", r)


def field_dir(run):
    s = json.loads((run / "selfcal/summary.json").read_text())
    f = s["fields"][0]
    return s, f


def cmd_score(out, arm):
    q = out / arm
    fn = q / "score.json"
    if fn.exists():
        return
    ms = q / "pilot.ms"
    run = q / "run"
    s, fld = field_dir(run)
    rdir = Path(fld["rounds"][0]["store"]).parent
    (m1,) = sorted(rdir.glob("*-model.fits"))
    (mf,) = sorted((rdir.parent / "final").glob("*-model.fits"))
    prep_arm(q / "score", ms)
    d = ft.Data(q / "score")
    corr = np.load(q / "score/prep/vis_corr.npy")
    data = d.vis.astype(np.complex64)
    F = {
        "B": score_model(d, data, m1),
        "Fix": score_model(d, corr, m1),
        "Fin": score_model(d, corr, mf),
    }
    P = {k: excess(v) for k, v in F.items()}
    drops = {
        "D_Fix": (P["B"] - P["Fix"]) / P["B"],
        "D_Fin": (P["B"] - P["Fin"]) / P["B"],
    }
    g0 = json.loads((out / "P/g0.json").read_text())
    act_before = g0["active"]
    act_after = d.meta["active"]
    newly = 1 - act_after / act_before
    res = {
        "F_uJy": {k: v * 1e6 for k, v in F.items()},
        **drops,
        "active_before": act_before,
        "active_after": act_after,
        "newly_flagged_fraction": newly,
    }
    if newly > 0.01:
        Tr = T * math.sqrt(act_before / act_after)
        Pr = {k: v**2 - Tr**2 for k, v in F.items()}
        res["rescaled_T"] = {
            "T": Tr,
            "D_Fix": (Pr["B"] - Pr["Fix"]) / Pr["B"],
            "D_Fin": (Pr["B"] - Pr["Fin"]) / Pr["B"],
        }
    # health
    rnd = fld["rounds"][0]
    solve = rnd["solve"]
    g, flags, _gt, _gf, _scans = cal_selfcal.read_store(
        rnd["store"], rnd["term"].get("name") or "Sp"
    )
    res["solve"] = {
        k: solve.get(k)
        for k in ("iterations", "converged_fraction", "clipped", "wall_seconds")
    }
    res["solve_summary_keys"] = sorted(solve)
    res["flagged_solution_fraction"] = float(np.mean(flags))
    gi = np.exp(1j * np.angle(g[:, 0])).mean(
        axis=-1
    )  # (time, ant): mean of the two hands' phasors
    active, _sh, _ = f2.antenna_stats(d)
    r = f2.enu(q / "score")[: d.nant]
    mine = f2.gauge(gi[:, : d.nant], active, r)
    ref = f2.gauge(np.load(F2_GAINS)["T1p"], active, r)
    a, b = np.angle(mine["gbar"])[active], np.angle(ref["gbar"])[active]
    res["phase_vs_floor2_T1p"] = {
        "pearson_r": float(np.corrcoef(a, b)[0, 1]),
        "rms_diff_deg": float(np.degrees(np.sqrt(np.mean((a - b) ** 2)))),
        "sigma_phi_deg_selfcal": mine["sigma_phi_deg"],
        "sigma_phi_deg_floor2": ref["sigma_phi_deg"],
        "n_bins": int(g.shape[0]),
    }
    res["XX_minus_YY_steady_deg_rms"] = float(
        np.degrees(
            np.sqrt(
                np.mean(
                    np.angle(np.mean(g[:, 0, :, 0] * np.conj(g[:, 0, :, 1]), axis=0))[
                        active
                    ]
                    ** 2
                )
            )
        )
    )
    res["round1_clean"] = rnd["image"]["clean"]
    res["final_clean"] = fld["final_image"]["clean"]
    res["image_wall_s"] = [
        rnd["image"]["wall_seconds"],
        fld["final_image"]["wall_seconds"],
    ]
    res["gemclean_sha256"] = s["gemclean_sha256"]
    res["models"] = [str(m1), str(mf)]
    ft.wjson(fn, res)
    ft.log("score", arm, json.dumps(res, default=float)[:1500])


def healthy(x):
    return (
        (x["solve"]["converged_fraction"] or 0) >= 0.9
        and x["flagged_solution_fraction"] <= 0.05
        and x["phase_vs_floor2_T1p"]["pearson_r"] >= 0.7
    )


def cmd_summary(out):
    g0 = json.loads((out / "P/g0.json").read_text())
    arms = {
        a: json.loads((out / a / "score.json").read_text())
        for a in ("P", "PL")
        if (out / a / "score.json").exists()
    }
    res = {"G0": g0, "arms": arms}
    p = arms["P"]
    res["G1"] = {"F_B_uJy": p["F_uJy"]["B"], "ratio": p["F_uJy"]["B"] / (F_ARCH * 1e6)}
    res["G1"]["within_10pct"] = abs(res["G1"]["ratio"] - 1) <= 0.10
    hp = healthy(p)
    res["health"] = {a: healthy(x) for a, x in arms.items()}

    def band(x, hi=0.75, lo=0.40):
        return "high" if x >= hi else ("low" if x < lo else "partial")

    if not hp:
        r1 = r2 = "void"
    else:
        r1 = {"high": "replicates", "low": "refutes", "partial": "partial"}[
            band(p["D_Fix"])
        ]
        r2 = {"high": "lowers", "low": "fails", "partial": "partial"}[band(p["D_Fin"])]
    notes = []
    if r1 == "replicates" and p["D_Fin"] < 0.40:
        notes.append(
            "gains right, re-imaging brings the floor back (H9 / deconvolution)"
        )
    if p["D_Fin"] >= p["D_Fix"] + 0.10:
        notes.append("re-imaging adds to the drop")
    r3 = "void"
    if "PL" in arms and res["health"]["PL"] and hp:
        q = arms["PL"]["D_Fix"] / p["D_Fix"]
        r3 = "long" if q >= 0.7 else ("short" if q < 0.3 else "partial")
        res["R3_ratio"] = q
    if r1 == "replicates" and r2 == "lowers" and r3 == "long":
        j = "row 1: H1 attributed under floor-3's standard, share D_Fin"
    elif r1 == "replicates" and r2 == "lowers":
        j = "row 2: H1 supported, not attributed"
    elif r1 == "replicates":
        j = "row 3: H1 supported for the data; the image floor needs more than gains"
    elif r1 == "refutes":
        j = "row 5: floor-2's lead withdrawn"
    else:
        j = "row 4: H1 unresolved, bound 0.854"
    res.update({"R1": r1, "R2": r2, "R3": r3, "notes": notes, "joint": j})
    ft.wjson(out / "summary.json", res)
    print(
        json.dumps(
            {
                k: res[k]
                for k in ("G0", "G1", "health", "R1", "R2", "R3", "notes", "joint")
            },
            indent=1,
            default=float,
        )
    )


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["copy", "g0", "score", "summary", "clean"])
    p.add_argument("arm", nargs="?", choices=["P", "PL"])
    p.add_argument("--out", default="D:/rang/outputs/floor-3-20261116")
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    if a.stage == "copy":
        cmd_copy(out, a.arm)
    elif a.stage == "g0":
        cmd_g0(out)
    elif a.stage == "score":
        cmd_score(out, a.arm)
    elif a.stage == "summary":
        cmd_summary(out)
    elif a.stage == "clean":
        shutil.rmtree(out / a.arm / "pilot.ms", ignore_errors=True)
        for sub in ("score/prep", "g0/prep"):
            shutil.rmtree(out / a.arm / sub, ignore_errors=True)
    ft.log("stage", a.stage, a.arm, "wall_s", round(time.perf_counter() - s0, 1))


if __name__ == "__main__":
    sys.exit(main())
