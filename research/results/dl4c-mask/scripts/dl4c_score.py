"""DL4c (#43), research/dl4c-mask.md sections 2-4 (with amendments 2-3): scores and rule.

    python dl4c_score.py RUN_ROOT OUT.json

Per case: arm A against arm P (R1-R3, real) or T (T1-T3, simulated), from GeMClean's
image reports and products in RUN_ROOT/img/<case>-<arm>.
Cost: convolutions (primary), sub-minor loops, major cycles, minor, resync and wall seconds.
Quality, R: P's final MFS residual MAD-sigma within 1.02 x A's; P's MFS model flux within 2 %
of A's; rms of (restored P - restored A) over A's 5-sigma region at most 0.1 x A's sigma.
Quality, T: the bench scorer (examples/gemclean_bench_compare.py score, job image-MFS, against
RUN_ROOT/prep/<case>/out and the catalogue): false |flux| of T at most 1.1 x A's; flux-weighted
recovery within 0.005 of A's; Q/Q_truth within 0.2 % of A's.
A case counts if its arm meets every quality bound and neither image ended on the component
budget (amendment 3). h = 1 - conv(arm)/conv(A). Rule (section 4): null if median h over the six
cases < 0.20 or fewer than four count; headroom if median h >= 0.20 with at least two counting
R and two counting T cases; mixed otherwise.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

CASES = {"R1": "P", "R2": "P", "R3": "P", "T1": "T", "T2": "T", "T3": "T"}
K = 5.0


def mad_sigma(x):
    x = x[np.isfinite(x)]
    return 1.4826 * float(np.median(np.abs(x - np.median(x))))


def fdata(path):
    with fits.open(path) as h:
        return np.squeeze(h[0].data).astype(float)


def cost(d):
    rep = json.loads((d / "image-report.json").read_text())
    run, ms = rep["run"], rep["multiscale"][0]
    return {
        "convolutions": ms["convolutions"],
        "sub_minor_loops": ms["sub_minor_loops"],
        "major_cycles": run["major_cycles"],
        "components": run["components"],
        "budget": any(c["stop"] == "Budget" for c in run["cycles"]),
        "minor_s": run["seconds"]["minor"],
        "resync_s": run["seconds"]["resync"],
        "wall_s": rep["seconds"]["wall"],
        "threads": rep.get("threads"),
    }


def real_quality(a, p):
    sa = mad_sigma(fdata(a / "image-MFS-residual.fits"))
    sp = mad_sigma(fdata(p / "image-MFS-residual.fits"))
    fa = float(np.nansum(fdata(a / "image-MFS-model.fits")))
    fp = float(np.nansum(fdata(p / "image-MFS-model.fits")))
    ia, ip = fdata(a / "image-MFS-image.fits"), fdata(p / "image-MFS-image.fits")
    region = ia > K * sa
    diff = float(np.sqrt(np.mean((ip - ia)[region] ** 2)))
    q = {
        "sigma_a": sa,
        "sigma_arm": sp,
        "sigma_ratio": sp / sa,
        "flux_a": fa,
        "flux_arm": fp,
        "flux_ratio": fp / fa,
        "restored_diff_rms_over_sigma_a": diff / sa,
        "region_pixels": int(region.sum()),
    }
    q["pass"] = bool(
        q["sigma_ratio"] <= 1.02
        and abs(q["flux_ratio"] - 1) <= 0.02
        and q["restored_diff_rms_over_sigma_a"] <= 0.1
    )
    return q


def bench(root, case, d, py, script):
    out = d / "bench-score.json"
    if not out.is_file():
        subprocess.run(
            [py, "-I", script, "score", str(root / "prep" / case / "out"),
             str(root / "sim" / case / "catalogue.json"), str(d), str(out),
             "--jobs", "image-MFS"],
            check=True,
        )  # fmt: skip
    return json.loads(out.read_text())["jobs"]["image-MFS"]


def sim_quality(root, case, a, t, py, script):
    ba, bt = bench(root, case, a, py, script), bench(root, case, t, py, script)
    ra = (ba.get("recovery_all") or {}).get("flux_weighted")
    rt = (bt.get("recovery_all") or {}).get("flux_weighted")
    q = {
        "false_flux_abs_a": ba["false_flux_abs"],
        "false_flux_abs_arm": bt["false_flux_abs"],
        "recovery_a": ra,
        "recovery_arm": rt,
        "q_over_q_truth_a": ba.get("q_over_q_truth"),
        "q_over_q_truth_arm": bt.get("q_over_q_truth"),
    }
    q["pass"] = bool(
        q["false_flux_abs_arm"] <= 1.1 * q["false_flux_abs_a"]
        and abs(rt - ra) <= 0.005
        and abs(q["q_over_q_truth_arm"] / q["q_over_q_truth_a"] - 1) <= 0.002
    )
    return q


def main(root, out, stopped=()):
    """`stopped`: cases stopped under a rule (amendment 4): recorded as not
    converged, not counting, and left out of the median."""
    root = Path(root)
    wt = Path(__file__).resolve().parents[4]
    py = sys.executable
    script = str(wt / "examples" / "gemclean_bench_compare.py")
    cases = {}
    for case, arm in CASES.items():
        a, m = root / "img" / f"{case}-A", root / "img" / f"{case}-{arm}"
        if case in stopped:
            cases[case] = {"stopped": True, "counts": False}
            continue
        if not ((a / "done").exists() and (m / "done").exists()):
            cases[case] = {"missing": True}
            continue
        ca, cm = cost(a), cost(m)
        q = real_quality(a, m) if case.startswith("R") else sim_quality(root, case, a, m, py, script)
        h = 1 - cm["convolutions"] / ca["convolutions"]
        counts = q["pass"] and not ca["budget"] and not cm["budget"]
        cases[case] = {"arm": arm, "cost_a": ca, "cost_arm": cm, "quality": q, "h": h, "counts": counts}
    done = [c for c in cases.values() if not c.get("missing") and not c.get("stopped")]
    hs = [c["h"] for c in done]
    med = float(np.median(hs)) if hs else None
    n_r = sum(1 for k, c in cases.items() if k[0] == "R" and c.get("counts"))
    n_t = sum(1 for k, c in cases.items() if k[0] == "T" and c.get("counts"))
    n = n_r + n_t
    if len(done) < len(CASES) - len(stopped):
        outcome = "incomplete"
    elif med < 0.20 or n < 4:
        outcome = "null"
    elif n_r >= 2 and n_t >= 2:
        outcome = "headroom"
    else:
        outcome = "mixed"
    res = {"cases": cases, "median_h": med, "counting_R": n_r, "counting_T": n_t, "outcome": outcome}
    Path(out).write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: v for k, v in res.items() if k != "cases"}, indent=1))
    for k, c in cases.items():
        if c.get("stopped"):
            print(k, "stopped (amendment 4): does not count")
        elif not c.get("missing"):
            print(k, "h=%.3f" % c["h"], "counts" if c["counts"] else "does not count")


if __name__ == "__main__":
    stop = sys.argv[sys.argv.index("--stopped") + 1].split(",") if "--stopped" in sys.argv else []
    main(sys.argv[1], sys.argv[2], tuple(stop))
