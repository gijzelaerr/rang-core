"""e2b-misses 9.28's scorer and rule (frozen with the section, before any run).

    python c3_score.py g2b OUT_JSON     pool the three fields' 2b comparisons
    python c3_score.py dirty-field NAME     one field's gate 3c dirty L-inf / peak
                                            (a4_score.linf) -> $P/score/dirty-TAG.json
    python c3_score.py clean-field NAME     one field's e2_score3c.score_field
                                            -> $P/score/clean-TAG.json
    python c3_score.py dirty OUT_JSON       the three fields' dirty records, the rule
    python c3_score.py clean OUT_JSON       pooled as e2_score3c.main; every checked
                                            gate decides
Per field, so that a field's FITS files can be deleted once it is scored.
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "a5-mask"))
sys.path.insert(0, str(HERE.parents[1] / "e2-acceptance-scripts"))
from a4_score import TOL, linf
from a5_score import sigmas_rang, sigmas_wsclean
from e2_score3c import mad, score_field

P = Path("D:/rang/outputs/e2b-confirm-20261116")
FIELDS = [("J1331+3030", 0), ("J1939-6342", 1), ("J1833-2103", 2)]
NCH = 8


def tag(n):
    return n.replace("+", "p").replace("-", "m")


def write(out, res, keys):
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in keys}, indent=1))


def g2b(out):
    per = {n: json.loads((P / f"g2b-f{f}.json").read_text()) for n, f in FIELDS}
    tot = {k: sum(v[k] for v in per.values())
           for k in ("rows", "cells", "compared_cells", "flag_elements_differ",
                     "cells_over_class_c", "nonfinite_compared", "casa_flag_ne_frozen",
                     "rang_flag_ne_frozen")}  # fmt: skip
    tot["max_eps_of_cell_max"] = max(v["max_eps_of_cell_max"] for v in per.values())
    tot["max_rel"] = max(v["max_rel"] for v in per.values())
    tot["met"] = tot["cells_over_class_c"] == 0 and tot["flag_elements_differ"] == 0
    res = {"pooled": tot, "fields": per}
    write(out, res, ["pooled"])


def dirty_field(name):
    t = tag(name)
    r, w = P / "rang-dirty" / t, P / "wsclean-dirty" / t
    f = linf(
        lambda c, p: r / f"image-{c}-{p}-dirty.fits",
        lambda c, p: w / f"{t}-dirty-{c}-{p}-dirty.fits",
        lambda c: w / f"{t}-dirty-{c}-I-dirty.fits",
    )
    f["met"] = f["max"] <= TOL
    (P / "score").mkdir(exist_ok=True)
    (P / "score" / f"dirty-{t}.json").write_text(json.dumps(f, indent=1) + "\n")
    print(json.dumps({k: v for k, v in f.items() if k != "per_image"}))


def clean_field(name):
    t = tag(name)
    rdir, odir = P / "rang-clean" / t, P / "wsclean-clean" / t
    f = score_field(name, rdir, odir, t, NCH)
    f["logs"] = {"rang": sigmas_rang(P / "rang-clean" / f"{t}.out"),
                 "wsclean": sigmas_wsclean(P / "wsclean-clean" / f"{t}.out")}  # fmt: skip
    (P / "score").mkdir(exist_ok=True)
    (P / "score" / f"clean-{t}.json").write_text(json.dumps(f, indent=1) + "\n")
    print(json.dumps({k: v for k, v in f.items() if k not in ("sources", "logs")}))


def dirty(out):
    res = {"tolerance": TOL, "eps": "1e-06", "fields": {}}
    for name, _ in FIELDS:
        f = json.loads((P / "score" / f"dirty-{tag(name)}.json").read_text())
        f.pop("per_image")
        res["fields"][name] = f
    res["met_all"] = all(v["met"] for v in res["fields"].values())
    write(out, res, ["fields", "met_all"])


def clean(out):
    res = {"fields": {}}
    for name, _ in FIELDS:
        res["fields"][name] = json.loads(
            (P / "score" / f"clean-{tag(name)}.json").read_text()
        )
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
    gates = {
        "compact_ratio": comp["met"],
        "spectral_index": spec["met"],
        "offsource_model": all(f["offsource_met"] for f in res["fields"].values()),
        "unpolarised_quv": res["fields"]["J1939-6342"].get("unpolarised_met"),
    }
    checked = [v for v in gates.values() if v is not None]
    res.update(
        compact=comp,
        spectral_index=spec,
        offsource={n: f["offsource_ratio"] for n, f in res["fields"].items()},
        gates=gates,
        not_checked=[k for k, v in gates.items() if v is None] + ["q_over_q0"],
        met_where_checked=bool(checked) and all(checked),
    )
    write(
        out,
        res,
        ["compact", "spectral_index", "offsource", "gates", "met_where_checked"],
    )


if __name__ == "__main__":
    {"g2b": g2b, "dirty": dirty, "clean": clean, "dirty-field": dirty_field,
     "clean-field": clean_field}[sys.argv[1]](sys.argv[2])  # fmt: skip
