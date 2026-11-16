"""Gate 2 of research/gpu-grid.md: GeMClean -gpu against the CPU path, G1's bounds on the
inner field (central 2N/3). Usage: gate2_analyse.py OUT_JSON (reads D:/rang/outputs/20261116-gpu-grid/gate2)."""
import json
import re
import sys
from pathlib import Path

import numpy as np
from rang.core_imaging import read_fits

G = Path("D:/rang/outputs/20261116-gpu-grid/gate2")
THRESHOLD_JY = 1e-4
BOUNDS = {
    "image_rms_over_sigma": 0.1,
    "image_linf_jy": THRESHOLD_JY,
    "q_over_q_truth": 1e-3,
    "false_flux_abs_jy": 1e-3,
    "recovery_flux_weighted": 1e-3,
    "exact_residual_inner_peak_jy": 0.1 * THRESHOLD_JY,
}


def inner(a):
    n = a.shape[-1]
    lo, hi = n // 6, n - n // 6
    return a[..., lo:hi, lo:hi]


def summary(log):
    t = log.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(\d+) components, (\d+) major cycles", t)
    return int(m.group(1)), int(m.group(2))


rows = []
for sky in ["s1", "s2", "s3", "h1", "h2", "h3", "h4"]:
    if not (G / "score" / f"{sky}.json").exists():
        continue
    sc = json.loads((G / "score" / f"{sky}.json").read_text(encoding="utf-8"))
    sigma = sc["briggs_noise"]
    for form in ["coarse", "fine"]:
        c, g = sc["jobs"][f"{sky}-{form}-cpu"], sc["jobs"][f"{sky}-{form}-gpu"]
        row = {"sky": sky, "form": form, "sigma_jy": sigma}
        for kind in ("image", "residual", "model"):
            a, _ = read_fits(G / "score" / sky / f"{sky}-{form}-cpu-{kind}.fits")
            b, _ = read_fits(G / "score" / sky / f"{sky}-{form}-gpu-{kind}.fits")
            d = inner(np.asarray(b, dtype=float) - np.asarray(a, dtype=float))
            row[f"{kind}_rms_jy"] = float(np.sqrt(np.mean(d**2)))
            row[f"{kind}_linf_jy"] = float(np.abs(d).max())
            if kind == "residual":
                row["residual_linf_over_peak"] = row["residual_linf_jy"] / float(np.abs(inner(np.asarray(a, dtype=float))).max())
        row["deltas"] = {
            "image_rms_over_sigma": row["image_rms_jy"] / sigma,
            "image_linf_jy": row["image_linf_jy"],
            "q_over_q_truth": abs(g["q_over_q_truth"] - c["q_over_q_truth"]),
            "false_flux_abs_jy": abs(g["false_flux_abs"] - c["false_flux_abs"]),
            "recovery_flux_weighted": abs(g["recovery_all"]["flux_weighted"] - c["recovery_all"]["flux_weighted"]),
            "exact_residual_inner_peak_jy": abs(g["exact_residual_inner_peak_abs"] - c["exact_residual_inner_peak_abs"]),
        }
        row["cpu"] = {k: c[k] for k in ("q_over_q_truth", "false_flux_abs", "exact_residual_inner_peak_abs")}
        row["gpu"] = {k: g[k] for k in ("q_over_q_truth", "false_flux_abs", "exact_residual_inner_peak_abs")}
        row["components_cycles"] = {"cpu": summary(G / "score" / sky / f"{sky}-{form}-cpu.log"),
                                    "gpu": summary(G / "score" / sky / f"{sky}-{form}-gpu.log")}
        row["model_identical"] = row["model_linf_jy"] == 0.0
        row["passes"] = all(row["deltas"][k] <= v for k, v in BOUNDS.items())
        rows.append(row)

print("| Sky | form | comp. CPU / GPU | img rms/σ | img L∞ µJy | ΔQ/Qt | Δfalse mJy | Δrecov | Δpeak µJy | Q/Qt CPU / GPU | pass |")
print("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |")
for r in rows:
    d = r["deltas"]
    cc = r["components_cycles"]
    print(f"| {r['sky'].upper()} | {r['form']} | {cc['cpu'][0]} / {cc['gpu'][0]} ({cc['cpu'][1]}/{cc['gpu'][1]} cyc) | {d['image_rms_over_sigma']:.2e} | {1e6*d['image_linf_jy']:.3g} | "
          f"{d['q_over_q_truth']:.1e} | {1e3*d['false_flux_abs_jy']:.3g} | {d['recovery_flux_weighted']:.1e} | {1e6*d['exact_residual_inner_peak_jy']:.3g} | "
          f"{r['cpu']['q_over_q_truth']:.5f} / {r['gpu']['q_over_q_truth']:.5f} | {'pass' if r['passes'] else 'FAIL'} |")
Path(sys.argv[1]).write_text(json.dumps({"bounds": BOUNDS, "rows": rows}, indent=1))
