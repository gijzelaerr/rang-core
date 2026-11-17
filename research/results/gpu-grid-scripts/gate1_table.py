"""Gate 1 table (research/gpu-grid.md section 4 and amendment 9.3) from the gpu_grid_parity JSONs."""
import json
import sys
from pathlib import Path

G = Path("D:/rang/outputs/20261116-gpu-grid/gate1")
B = sys.argv[1] if len(sys.argv) > 1 else "4096"
rows = []
for sky in ["s1", "s2", "s3", "h1", "h2", "h3", "h4", "pilot"]:
    for form in ["coarse", "fine"]:
        f = G / f"{sky}-{form}-b{B}.json"
        if not f.exists():
            continue
        r = json.loads(f.read_text())["result"]
        tol = 1e-5 if form == "coarse" else 1e-9
        d = G / f"{sky}-coarse-dirty-b{B}.json"
        try:
            dirty_peak = json.loads(d.read_text())["result"]["residual_peak_ujy"]
        except (OSError, ValueError, KeyError):
            dirty_peak = None
        ref = r.get("double_reference")
        a = r["residual_abs_ujy"] / dirty_peak if dirty_peak else None
        b = ref["gpu_abs_ujy"] / ref["cpu_abs_ujy"] if ref else None
        frozen = r["residual_rel"] <= tol and r["misfit_rel"] <= tol and r["dirty2vis_rel"] <= tol
        rows.append(dict(sky=sky, form=form, plan=r["plan"], residual_rel=r["residual_rel"],
            residual_abs_ujy=r["residual_abs_ujy"], residual_peak_ujy=r["residual_peak_ujy"],
            misfit_rel=r["misfit_rel"], dirty2vis_rel=r["dirty2vis_rel"], frozen_pass=frozen,
            dirty_peak_ujy=dirty_peak, amended_a=a, amended_b=b,
            amended_pass=(None if form == "fine" else (a is not None and a <= 1e-5 and b is not None and b <= 2)),
            repeat_identical=r["gpu_repeat_identical"], double_reference=ref,
            cpu_residual_s=r["cpu_residual_s"], gpu_residual_warm_s=r["gpu_residual_warm_s"],
            cpu_dirty2vis_s=r["cpu_dirty2vis_s"], gpu_dirty2vis_s=r["gpu_dirty2vis_s"], gpu_plan_s=r["gpu_plan_s"]))
print("| sky | form | grid, supp, planes | res. diff / res. peak | µJy | misfit | dirty2vis | frozen | / dirty peak | GPU/CPU err vs f64 | amended |")
print("| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |")
for x in rows:
    p = x["plan"]
    fa = lambda v: "–" if v is None else f"{v:.1e}"
    print(f"| {x['sky'].upper()} | {x['form']} | {p['nu']}, {p['supp']}, {p['nplanes']} | {x['residual_rel']:.1e} | {x['residual_abs_ujy']:.2e} | {x['misfit_rel']:.1e} | {x['dirty2vis_rel']:.1e} | {'pass' if x['frozen_pass'] else 'FAIL'} | {fa(x['amended_a'])} | {fa(x['amended_b'])} | {'–' if x['amended_pass'] is None else ('pass' if x['amended_pass'] else 'FAIL')} |")
Path(sys.argv[2] if len(sys.argv) > 2 else "gate1.json").write_text(json.dumps(rows, indent=1))
