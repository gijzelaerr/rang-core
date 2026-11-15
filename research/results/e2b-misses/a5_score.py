"""Arm A5 (research/e2b-misses.md 9.18): gate 3c's cleaned measures, by
e2_score3c.py's score_field unchanged, per field, pooled as its main pools.

    a5_score.py a5|control OUT_JSON

a5:      GeMClean -auto-mask 5 ($P/rang-mask/TAG) against WSClean -auto-mask 5
         -no-small-inversion ($P/wsclean-mask/TAG)
control: E2-B's unmasked GeMClean (R/rang-run-moved/image/FIELD) against
         WSClean unmasked -no-small-inversion ($P/wsclean-nomask/TAG)
Also reads both arms' noise per major iteration from their logs.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "e2-acceptance-scripts"))
from e2_score3c import mad, score_field

R = Path("D:/rang/outputs/e2-20261111-20-e2b")
P = Path("D:/rang/outputs/gemclean-iquv-mask-20261115")
FIELDS = ["J1331+3030", "J1939-6342", "J1833-2103"]  # field ids 0, 1, 2
NCH = 8


def tag(n):
    return n.replace("+", "p").replace("-", "m")


def sigmas_rang(path):
    if not path.exists():
        return None
    t = path.read_text(errors="replace")
    sig = [
        float(x)
        for x in re.findall(r"auto-mask: major iteration \d+, sigma (\S+) Jy", t)
    ]
    fin = re.findall(r"auto-mask: threshold reached in major iteration (\d+)", t)
    return {"sigma": sig, "finishing": int(fin[0]) if fin else None}


UNIT = {"Jy": 1.0, "mJy": 1e-3, "µJy": 1e-6, "uJy": 1e-6, "nJy": 1e-9}


def sigmas_wsclean(path):
    if not path.exists():
        return None
    t = path.read_text(errors="replace")
    sig = [
        float(v) * UNIT[u]
        for v, u in re.findall(
            r"Estimated standard deviation of background noise: (\S+) (\S+)", t
        )
    ]
    blocks = re.split(r" == Deconvolving \((\d+)\) ==", t)
    fin = None
    for i in range(1, len(blocks) - 1, 2):
        if "Auto-masking threshold reached" in blocks[i + 1]:
            fin = int(blocks[i])
            break
    return {"sigma": sig, "finishing": fin, "majors": len(sig)}


def main(mode, out):
    res = {"mode": mode, "fields": {}}
    for n in FIELDS:
        t = tag(n)
        if mode == "a5":
            rdir, odir = P / "rang-mask" / t, P / "wsclean-mask" / t
            logs = {
                "rang": sigmas_rang(P / "rang-mask" / f"{t}.out"),
                "wsclean": sigmas_wsclean(P / "wsclean-mask" / f"{t}.out"),
            }
        else:
            rdir = R / "rang-run-moved" / "image" / n.replace("+", "_")
            odir = P / "wsclean-nomask" / t
            logs = {"wsclean": sigmas_wsclean(P / "wsclean-nomask" / f"{t}.out")}
        f = score_field(n, rdir, odir, t, NCH)
        f["logs"] = logs
        res["fields"][n] = f
    allsrc = [s for f in res["fields"].values() for s in f["sources"]]
    ratios = np.array([s["ratio"] for s in allsrc])
    da = np.array([abs(s["dalpha"]) for s in allsrc if "dalpha" in s])
    comp = {"n": len(allsrc)}
    if len(ratios):
        comp.update(median=float(np.median(ratios)), robust_scatter=mad(ratios))
    comp["met"] = (
        bool(abs(comp["median"] - 1) <= 0.005 and comp["robust_scatter"] <= 0.01)
        if len(ratios) >= 3
        else None
    )
    spec = {
        "n": len(da),
        "median_abs_dalpha": float(np.median(da)) if len(da) else None,
    }
    spec["met"] = bool(spec["median_abs_dalpha"] <= 0.05) if len(da) else None
    res.update(
        compact=comp,
        spectral_index=spec,
        offsource={n: f["offsource_ratio"] for n, f in res["fields"].items()},
        gates={
            "compact_ratio": comp["met"],
            "offsource_model": all(f["offsource_met"] for f in res["fields"].values()),
            "spectral_index (reported)": spec["met"],
            "unpolarised_quv (reported)": res["fields"]["J1939-6342"].get(
                "unpolarised_met"
            ),
        },
    )
    res["hypothesis_met"] = bool(comp["met"]) and res["gates"]["offsource_model"]
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: res[k] for k in ("compact", "offsource", "gates", "hypothesis_met")},
            indent=1,
        )
    )


if __name__ == "__main__":
    main(*sys.argv[1:3])
