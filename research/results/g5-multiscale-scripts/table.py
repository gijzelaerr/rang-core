"""table.py TAG RUN... : the note's summary rows from $O/runs/TAG/score-RUN.json."""

import json
import os
import sys
from pathlib import Path

O = Path(os.environ.get("G5_OUT", "/mnt/d/rang/outputs/g5-20261107-01"))
tag = sys.argv[1]
for run in sys.argv[2:]:
    d = json.loads((O / "runs" / tag / f"score-{run}.json").read_text())
    f = d["F"]
    verdicts = " ".join(
        f"{k}:{'pass' if v['pass'] else 'FAIL'}"
        for k, v in d.items()
        if isinstance(v, dict) and "pass" in v
    )
    print(f"## {run} {verdicts}")
    c = d.get("C") or (d.get("E") or {}).get("mfs")
    if c:
        print(f"  sigma {c['sigma'] * 1e6:.1f} uJy, points {c['points_scored']}: median err G {c['median_point_err_g']:.4f} W {c['median_point_err_w']:.4f}")
        for g in c["groups"]:
            print(
                f"  group {g['gaussians']} G at ({g['centre'][0]:.0f},{g['centre'][1]:.0f}): T {g['truth']:.4f} Jy, "
                f"G {g['rel_err_g'] * 100:+.2f}% W {g['rel_err_w'] * 100:+.2f}%, eps {g['eps'] * 1e3:.2f} mJy, "
                f"res rms G {g['res_rms_g'] * 1e6:.1f} W {g['res_rms_w'] * 1e6:.1f} uJy"
            )
        print(
            f"  false flux G {c['false_flux_g'] * 1e3:.1f} W {c['false_flux_w'] * 1e3:.1f} mJy; "
            f"|false| G {c['false_abs_flux_g'] * 1e3:.1f} W {c['false_abs_flux_w'] * 1e3:.1f} mJy"
        )
    if "E" in d:
        for g in d["E"]["gaussians"]:
            print(
                f"  E gauss fwhm {g['fwhm_px']:.1f}: dS G {g['g'].get('dS', float('nan')):+.4f} W {g['w'].get('dS', float('nan')):+.4f}, "
                f"dalpha G {g['g'].get('dalpha', float('nan')):+.4f} W {g['w'].get('dalpha', float('nan')):+.4f} {g['pass']}"
            )
    if "D" in d:
        dd = d["D"]
        for name, r in dd["regions"].items():
            print(
                f"  D {name}: {r['pixels']} px, G {r['flux_g']:.4f} W {r['flux_w']:.4f} Jy ({r['rel_diff'] * 100:+.2f}%), "
                f"eps {r['eps']:.4f}, res rms G {r['res_rms_g'] * 1e3:.3f} W {r['res_rms_w'] * 1e3:.3f} mJy {r['flux_ok']} {r['rms_ok']}"
            )
        print(
            f"  off-mask flux G {dd['off_flux_g']:.3f} W {dd['off_flux_w']:.3f} Jy; |off| G {dd['off_abs_flux_g']:.3f} W {dd['off_abs_flux_w']:.3f}; "
            f"off sigma G {dd['off_res_sigma_g'] * 1e3:.3f} W {dd['off_res_sigma_w'] * 1e3:.3f} mJy; model G {dd['model_flux_g']:.3f} W {dd['model_flux_w']:.3f}"
        )
    print(
        f"  majors G {f['g_major_cycles']} W {f['w_major_cycles']}; components G {f['g_components']} W {f['w_components_logged']}; "
        f"sub-minor {f['g_sub_minor_loops']}; RSS/wall G {f['g_rss_bytes, wall']} W {f['w_rss_bytes, wall']}"
    )
    per = f["g_per_scale"][0]
    print("  per scale: " + ", ".join(f"{s:.0f}px {n} ({fl:.3f} Jy)" for s, n, fl in per))
