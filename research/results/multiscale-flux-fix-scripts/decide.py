"""Issue #23 step 4: the frozen decision rule (research/multiscale-flux-fix.md, section 6).

    python decide.py OUT.json D_MEASURES_DIR H_MEASURES_DIR

Reads every `<tag>-<arm>-r<N>.json` measure file (measure.py) in the two
directories (tag `D` or `H`), computes per arm and field the five clauses and
the pass, the WSClean baselines' RMS bound per field, and writes one archive. The
WSClean baselines are `<tag>-ws-multiscale-r1` and `-r2` (on D: DF5-O's FITS
rescored by measure.py, the scorer reproduction).
"""

import argparse
import json
import re
from pathlib import Path
from statistics import median


def summary(rec):
    rows = rec["sources"]
    bright = [r for r in rows if r["snr_truth"] >= 20]
    tol = {r["name"]: 0.05 * r["s_truth_jy"] + 3 * r["sigma_ap_jy"] for r in bright}
    ratios = {r["name"]: abs(r["ds_jy"]) / tol[r["name"]] for r in bright}
    worst = max(ratios, key=ratios.get)
    points = [r["ds_jy"] for r in bright if r["kind"] == "point"]
    out = {
        "A1_failures": rec["tolerances"]["A1_failures"],
        "A1_total": rec["tolerances"]["A1_total"],
        "A1": rec["tolerances"]["A1"],
        "A2_failures": rec["tolerances"]["A2_failures"],
        "A2": rec["tolerances"]["A2"],
        "worst_ratio": ratios[worst],
        "worst_source": worst,
        "median_point_ds_jy": median(points),
        "points_tested": len(points),
        "positive_points": sum(1 for d in points if d > 0),
        "total_ratio": rec["totals"]["ratio"],
        "rms_inner_jy": rec["exact_residual"]["rms_inner_jy"],
        "rms_jy": rec["exact_residual"]["rms_jy"],
        "spurious": rec["spurious"],
        "median_point_pedestal_jy": median(
            [
                r["pedestal_jy"]
                for r in bright
                if r["kind"] == "point" and r.get("pedestal_jy") is not None
            ]
            or [float("nan")]
        ),
        "picked": {
            r["name"]: round(r["ds_rel"], 4)
            for r in rows
            if r["name"] in ("p16", "p23", "p26")
        },
        "extended_ds_rel": {
            r["name"]: round(r["ds_rel"], 4) for r in rows if r["kind"] != "point"
        },
    }
    run = rec.get("run")
    if run:
        out["wall_s"] = run.get("wall_s")
        out["peak_rss_mb"] = run.get("peak_rss_mb")
        out["binary_sha256"] = run.get("binary_sha256")
    if rec.get("scale_lines"):
        out["scale_lines"] = rec["scale_lines"]
    return out


def load(d, tag):
    arms = {}
    for p in sorted(Path(d).glob(f"{tag}-*-r*.json")):
        m = re.fullmatch(rf"{tag}-(.+)-r(\d+)\.json", p.name)
        arms[f"{m.group(1)}-r{m.group(2)}"] = summary(json.loads(p.read_text()))
    return arms


def bound(rms):
    lo = min(rms)
    spread = max(rms) - lo
    return lo + max(0.02 * lo, 2 * spread)


def clauses(s, rms_bound, base_median):
    c = {
        "1_A1": s["A1"],
        "2_A2": s["A2"],
        "3_rms": s["rms_inner_jy"] <= rms_bound,
        "4_margin": s["worst_ratio"] <= 0.9,
        "5_offset": True
        if base_median <= 0
        else s["median_point_ds_jy"] <= 0.5 * base_median,
    }
    return c, all(c.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("d_dir")
    ap.add_argument("h_dir")
    a = ap.parse_args()
    fields = {"D": load(a.d_dir, "D"), "H": load(a.h_dir, "H")}
    result = {"rule": "research/multiscale-flux-fix.md section 6", "fields": {}}
    for tag, arms in fields.items():
        base_rms = [
            arms[k]["rms_inner_jy"]
            for k in ("ws-multiscale-r1", "ws-multiscale-r2")
            if k in arms
        ]
        rms_bound = bound(base_rms) if len(base_rms) == 2 else None
        base_median = arms.get("gc-multiscale-r1", {}).get("median_point_ds_jy")
        per = {}
        for name, s in arms.items():
            entry = dict(s)
            if rms_bound is not None and base_median is not None:
                entry["clauses"], entry["pass"] = clauses(s, rms_bound, base_median)
            per[name] = entry
        result["fields"][tag] = {
            "rms_bound_jy": rms_bound,
            "baseline_median_point_ds_jy": base_median,
            "arms": per,
        }
    names = {
        re.sub(r"-r\d+$", "", n) for f in result["fields"].values() for n in f["arms"]
    }
    both = {}
    for n in sorted(names):
        got = [result["fields"][t]["arms"].get(f"{n}-r1", {}).get("pass") for t in "DH"]
        both[n] = {"D": got[0], "H": got[1], "fix": got[0] is True and got[1] is True}
    result["both_fields"] = both
    Path(a.out).write_text(json.dumps(result, indent=1))
    for n, v in both.items():
        line = [n, f"D {v['D']}", f"H {v['H']}"]
        for t in "DH":
            s = result["fields"][t]["arms"].get(f"{n}-r1")
            if s:
                line.append(
                    f"{t}: A1 {','.join(s['A1_failures']) or '-'} worst {s['worst_ratio']:.2f} "
                    f"med {s['median_point_ds_jy'] * 1e6:+.1f} rms {s['rms_inner_jy'] * 1e6:.4f}"
                )
        print(" | ".join(line))
    for t in "DH":
        print(t, "bound", result["fields"][t]["rms_bound_jy"])


if __name__ == "__main__":
    main()
