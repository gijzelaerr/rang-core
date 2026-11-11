"""E1b's m32 arms against E1's frozen gates (e1-chain.md 4): the gate
numbers of result-e1b.json of each arm, as JSON (e2-acceptance.md 3).
    python e1b_table.py RUN_AUTO RUN_M000 OUT.json"""

import json
import sys


def row(d):
    t, f, im, pol, sc = d["terms"], d["flags"], d["image"], d["polarisation"], d["selfcal"]
    ch = t["crosshand"]
    out = {
        "K_med_e_over_s": t["K"]["median_abs_over_s"], "K_pass": t["K"]["pass"],
        "target_1gc_med_e_over_s": t["composite"]["target_1gc"]["median_abs_over_s"],
        "target_1gc_med_abs": t["composite"]["target_1gc"]["abs_e"]["median"],
        "target_1gc_pass": t["composite"]["target_1gc"]["pass"],
        "crosshand": {k: {kk: v[kk] for kk in ("median_abs_over_s", "pass") if kk in v}
                      for k, v in ch.items() if isinstance(v, dict)},
        "Df_med_e_over_s": t["Df"].get("median_abs_over_s"), "Df_pass": t["Df"]["pass"],
        "recall": f["recall"], "recall_pass": f["recall_pass"],
        "fp": f["false_positives"], "fp_tricolour": f["tricolour"]["false_positives"],
        "cells_differ": f["tricolour"]["cells_differ"], "fp_pass": f["fp_pass"],
        "image_chain": im["chain"].get("summary", {k: im["chain"][k] for k in im["chain"] if k not in ("beams", "sources", "fits")}),
        "image_chain_pass": im["chain"]["pass"], "image_control_pass": im["control"]["pass"],
        "residual_ratio": im["residual"]["ratio"], "residual_pass": im["residual"]["pass"],
        "pol_pass": pol["pass"], "gcal_leak": pol.get("gcal_leak"),
        "selfcal_r1": sc["round1_Sp"]["median_abs_over_s"], "selfcal_r2": sc["round2_Sa"]["median_abs_over_s"],
        "selfcal_r1_phase": sc["round1_Sp"]["phase_deg"], "selfcal_r2_phase": sc["round2_Sa"]["phase_deg"],
        "selfcal_r2_amp": sc["round2_Sa"]["amp_rel"], "selfcal_pass": sc["pass"],
    }
    return out


def main(a, b, out):
    res = {}
    for name, path in (("auto", a), ("m000", b)):
        with open(path + "/result-e1b.json", encoding="utf-8") as fh:
            res[name] = row(json.load(fh))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(json.dumps(res, indent=1, default=str)[:12000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
