"""Gate 1 of research/xf-avg-fix.md: chi per 3C286-SIM scan of the rang arms
run with the fix (sim_chi.py of claude/chi-offset-80cb6a at b12d2c3), against
33 deg and against chi-offset's arms (rang before the fix, CASA), and the Xf
tables against the unaveraged arm's.

    python gate1.py NEW_ROOT OLD_ROOT OUT.json
"""

import json
import sys
from pathlib import Path

import numpy as np
from rang.formats import caltable

TOL = 1.11  # deg, C6w's tolerance (frozen in section 2)


def chi(d):
    return {r["scan"]: r for r in json.loads((Path(d) / "chi.json").read_text())}


def xf(d):
    t = caltable.read(Path(d) / "sim.ms.rang-run" / "calibrate" / "Xf")
    c = np.array(t.main["CPARAM"])
    f = np.array(t.main["FLAG"])
    return c, f


def main(new, old, out):
    new, old = Path(new), Path(old)
    res = {"tolerance_deg": TOL, "arms": {}}
    arms = [
        ("control", "m90", "m90_noavg", "casa-control-m90"),
        ("feed0", "null", "null_noavg", "casa-feed0-feedms"),
    ]
    for truth, avg_arm, noavg_arm, casa in arms:
        fixed = chi(new / f"rang-{truth}-{avg_arm}")
        fixed_noavg = chi(new / f"rang-{truth}-{noavg_arm}")
        before = chi(old / f"rang-{truth}-{avg_arm}")
        before_noavg = chi(old / f"rang-{truth}-{noavg_arm}")
        cas = chi(old / casa)
        a, fa = xf(new / f"rang-{truth}-{avg_arm}")
        b, fb = xf(new / f"rang-{truth}-{noavg_arm}")
        a0, _ = xf(old / f"rang-{truth}-{avg_arm}")
        ok = ~fa & ~fb
        dx = np.degrees(np.abs(np.angle(a[ok] / b[ok])))
        dx0 = np.degrees(np.abs(np.angle(a0[ok] / b[ok])))
        rows = []
        for s in sorted(fixed):
            rows.append({
                "scan": s, "psi_deg": fixed[s]["psi_deg"],
                "chi_fixed_avg": fixed[s]["chi_deg"], "p_fixed_avg": fixed[s]["p"],
                "chi_noavg": fixed_noavg[s]["chi_deg"],
                "chi_noavg_before": before_noavg[s]["chi_deg"],
                "chi_avg_before": before[s]["chi_deg"], "chi_casa": cas[s]["chi_deg"],
            })  # fmt: skip
        err = max(abs(r["chi_fixed_avg"] - 33.0) for r in rows)
        res["arms"][f"{truth}-{avg_arm}"] = {
            "scans": rows,
            "max_abs_chi_minus_33": err,
            "max_abs_fixed_minus_noavg": max(
                abs(r["chi_fixed_avg"] - r["chi_noavg"]) for r in rows
            ),
            "max_abs_fixed_minus_casa": max(
                abs(r["chi_fixed_avg"] - r["chi_casa"]) for r in rows
            ),
            "xf_vs_noavg_deg": {"median": float(np.median(dx)), "max": float(dx.max()),
                                "n": int(ok.sum())},
            "xf_before_vs_noavg_deg": {"median": float(np.median(dx0)),
                                       "max": float(dx0.max())},
            "noavg_unchanged": all(r["chi_noavg"] == r["chi_noavg_before"] for r in rows),
            "pass": bool(err <= TOL),
        }  # fmt: skip
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
