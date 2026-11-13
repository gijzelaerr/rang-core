"""Score one arm on DF5-O's field with DF5-O's own functions (issue #23).

    python measure.py WORKTREE FIELD_DIR ARM_DIR OUT.json [--floor floor.json]
        [--check DF5O_MEASURE.json]

ARM_DIR holds WSClean-named FITS (`<arm>-NNNN-model.fits`, `<arm>-MFS-residual.fits`)
written by WSClean or gemclean; the prefix is the directory name without `-rN`.
Uses examples/compare_df5o.py's score_sources, tolerances, exact_residual and
image_stats unchanged. Adds a pedestal estimate per source (mean model per pixel
in the annulus r < d <= 2r, other apertures excluded, times the aperture's pixels)
and gemclean's per-scale lines. `--check` compares with a DF5-O measure file
(the scorer reproduction of research/multiscale-df5o-a1.md section 2).
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("worktree")
    ap.add_argument("field")
    ap.add_argument("arm_dir")
    ap.add_argument("out")
    ap.add_argument("--floor")
    ap.add_argument("--check")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.worktree) / "examples"))
    import compare_df5o as c

    t0 = time.perf_counter()
    field, truth, arrays = c.load_field(a.field)
    sigma = field["noise"]["sigma_img_mfs_jy"]
    arm_dir = Path(a.arm_dir)
    prefix = re.sub(r"-r\d+$", "", arm_dir.name)
    models, tool_residual, _ = c.wsclean_outputs(arm_dir, prefix)
    truth_cube = arrays["truth_cube"]
    rows, spurious, _ = c.score_sources(models, truth_cube, field, truth)
    totals = {
        "model_mfs_jy": float(models.mean(0).sum()),
        "truth_mfs_jy": float(truth_cube.mean(0).sum()),
    }
    totals["ratio"] = totals["model_mfs_jy"] / totals["truth_mfs_jy"]
    res, q = c.exact_residual(models, arrays)
    res_mfs = res.mean(0)
    rec = {
        "arm": prefix,
        "arm_dir": str(arm_dir),
        "sources": rows,
        "spurious": spurious,
        "totals": totals,
        "exact_residual": c.image_stats(res_mfs, sigma),
        "tool_residual": c.image_stats(tool_residual, sigma),
        "consistency_linf_over_sigma": float(np.abs(tool_residual - res_mfs).max() / sigma),
        "q": float(q.mean()),
        "tolerances": c.tolerances(rows, totals, field),
    }
    if a.floor:
        fl = json.loads(Path(a.floor).read_text())
        rec["reducible_fraction"] = (rec["q"] - fl["q_floor"]) / (fl["q0"] - fl["q_floor"])
        rec["signal_fraction_left"] = (rec["q"] - fl["q_truth"]) / (fl["q0"] - fl["q_truth"])

    # pedestal estimate per source
    mm = models.mean(0)
    masks = {s["name"]: c.disc(s["x"], s["y"], s["radius"] / c.CELL) for s in truth["sources"]}
    any_ap = np.zeros(mm.shape, bool)
    for m in masks.values():
        any_ap |= m
    ped = {}
    for s in truth["sources"]:
        r = s["radius"] / c.CELL
        ring = c.disc(s["x"], s["y"], 2 * r) & ~c.disc(s["x"], s["y"], r) & ~any_ap
        dens = float(mm[ring].mean()) if ring.any() else None
        ped[s["name"]] = {
            "ring_px": int(ring.sum()),
            "ring_mean_jy_per_px": dens,
            "pedestal_jy": None if dens is None else dens * int(masks[s["name"]].sum()),
        }
    for row in rec["sources"]:
        row.update(ped[row["name"]])

    # cost and counts
    run_json = arm_dir / "run.json"
    if run_json.exists():
        rec["run"] = json.loads(run_json.read_text())
    log = arm_dir / "gemclean.log"
    if log.exists():
        text = log.read_text(errors="replace")
        rec["scale_lines"] = re.findall(r"^multiscale: scale .*$", text, re.M)
        rec["log_tail"] = text.splitlines()[-25:]
    rec["seconds"] = time.perf_counter() - t0

    if a.check:
        ref = json.loads(Path(a.check).read_text())
        by = {r["name"]: r for r in ref["sources"]}
        worst = max(
            abs(r["ds_rel"] - by[r["name"]]["ds_rel"]) / max(abs(by[r["name"]]["ds_rel"]), 1e-12)
            for r in rows
        )
        rms_new = rec["exact_residual"]["rms_inner_jy"]
        rms_ref = ref["exact_residual"]["rms_inner_jy"]
        rec["check"] = {
            "against": a.check,
            "worst_rel_ds_rel": worst,
            "ratio_rel": abs(totals["ratio"] - ref["totals"]["ratio"]) / ref["totals"]["ratio"],
            "rms_inner_rel": abs(rms_new - rms_ref) / rms_ref,
            "a1_failures_ref": ref["tolerances"]["A1_failures"],
            "a1_failures_new": rec["tolerances"]["A1_failures"],
        }
        rec["check"]["ok"] = (
            rec["check"]["worst_rel_ds_rel"] <= 1e-9
            and rec["check"]["ratio_rel"] <= 1e-9
            and rec["check"]["rms_inner_rel"] <= 1e-9
            and rec["check"]["a1_failures_ref"] == rec["check"]["a1_failures_new"]
        )
    Path(a.out).write_text(json.dumps(rec, indent=1))
    pick = {r["name"]: round(r["ds_rel"], 4) for r in rows if r["name"] in ("p16", "p23", "p26")}
    print(json.dumps({"arm": prefix, "A1": rec["tolerances"]["A1_failures"],
                      "A2": rec["tolerances"]["A2_failures"], "ratio": totals["ratio"],
                      "rms_inner_uJy": rec["exact_residual"]["rms_inner_jy"] * 1e6,
                      "picked": pick, "check": rec.get("check")}, indent=1))  # fmt: skip


if __name__ == "__main__":
    main()
