# SPDX-License-Identifier: GPL-3.0-or-later
"""V8b's comparison (research/v8b-flagdata.md, section 5): rang's flags and
returns against CASA's, case by case.

Usage: compare_flagdata.py CASA_DIR RANG_DIR PLAN.json OUT.json [NAME ...]

tfcrop cases (arm `T*`): G1 cell agreement >= 99.9 %, G2 per-baseline flag
fraction within 1e-3, G3 precision and recall of the added flags >= 0.98,
G4 FLAG_ROW equal; informative when CASA adds >= 0.01 % of the cells. Other
cases: FLAG and FLAG_ROW equal (differences listed with the values that
attribute them, section 5.2), and every count of CASA's `summary` returns
equal in rang's.
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rang_flagdata import local  # noqa: E402


def load(path):
    z = np.load(path)
    shape = tuple(int(v) for v in z["shape"])
    flag = np.unpackbits(z["flag"])[: int(np.prod(shape))].astype(bool).reshape(shape)
    return flag, z["flag_row"].astype(bool)


def input_flags(path):
    from rang import core_ms

    with core_ms.open_table(path) as t:
        flag = np.asarray(t.getcol("FLAG"), bool)
        row = np.asarray(t.getcol("FLAG_ROW"), bool) if "FLAG_ROW" in t.columns else None
        a1 = np.asarray(t.getcol("ANTENNA1")) if "ANTENNA1" in t.columns else None
        a2 = np.asarray(t.getcol("ANTENNA2")) if "ANTENNA2" in t.columns else None
    return flag, row, a1, a2


def counts_diff(casa, rang, path=""):
    """Differences between CASA's summary record and rang's: every number
    in CASA's present and equal in rang's."""
    out = []
    if isinstance(casa, dict):
        if not isinstance(rang, dict):
            return [f"{path}: rang has no record"]
        for k, v in casa.items():
            if k in ("name", "type"):
                continue
            if k not in rang:
                out.append(f"{path}/{k}: missing in rang")
                continue
            out += counts_diff(v, rang[k], f"{path}/{k}")
    elif isinstance(casa, (int, float)):
        if not isinstance(rang, (int, float)) or float(casa) != float(rang):
            out.append(f"{path}: CASA {casa}, rang {rang}")
    return out


def tfcrop_verdict(casa, rang, before, a1, a2):
    n = casa.size
    agree = float((casa == rang).sum()) / n
    add_c, add_r = casa & ~before, rang & ~before
    tp = int((add_c & add_r).sum())
    precision = tp / max(int(add_r.sum()), 1) if add_r.any() else (1.0 if not add_c.any() else 0.0)
    recall = tp / max(int(add_c.sum()), 1) if add_c.any() else 1.0
    worst = 0.0
    key = a1.astype(np.int64) * 100000 + a2
    for k in np.unique(key):
        pick = key == k
        fc = casa[pick].mean()
        fr = rang[pick].mean()
        worst = max(worst, abs(float(fc) - float(fr)))
    informative = int(add_c.sum()) >= 1e-4 * n
    return {
        "agreement": agree,
        "casa_added": int(add_c.sum()),
        "rang_added": int(add_r.sum()),
        "precision": precision,
        "recall": recall,
        "worst_baseline_fraction": worst,
        "informative": bool(informative),
        "G1": agree >= 0.999,
        "G2": worst <= 1e-3,
        "G3": precision >= 0.98 and recall >= 0.98,
    }


def main(argv):
    casa_dir, rang_dir = Path(argv[0]), Path(argv[1])
    plan = {c["name"]: c for c in json.loads(Path(argv[2]).read_text(encoding="utf-8"))}
    out_path = Path(argv[3])
    only = set(argv[4:])
    verdicts = {}
    for name, case in plan.items():
        if only and not any(name == o or name.startswith(o) for o in only):
            continue
        cp, rp = casa_dir / f"{name}.npz", rang_dir / f"{name}.npz"
        if not cp.exists() or not rp.exists():
            verdicts[name] = {"missing": [str(p) for p in (cp, rp) if not p.exists()]}
            continue
        casa, casa_row = load(cp)
        rang, rang_row = load(rp)
        before, _, a1, a2 = input_flags(local(case["input"]))
        cj = json.loads((casa_dir / f"{name}.json").read_text(encoding="utf-8"))
        rj = json.loads((rang_dir / f"{name}.json").read_text(encoding="utf-8"))
        v = {"cells": int(casa.size)}
        errors = [c["error"] for c in cj["calls"] if c["error"]] + [
            c["error"] for c in rj["calls"] if c["error"]
        ]
        if errors:
            v["errors"] = {"casa": [c["error"] for c in cj["calls"]],
                           "rang": [c["error"] for c in rj["calls"]]}  # fmt: skip
        if casa.shape != rang.shape:
            v["shape"] = [list(casa.shape), list(rang.shape)]
            v["pass"] = False
            verdicts[name] = v
            continue
        rows_equal = casa_row.shape == rang_row.shape and bool(np.array_equal(casa_row, rang_row))
        v["flag_row_equal"] = rows_equal
        v["flag_row_diff"] = (int((casa_row != rang_row).sum())
                              if casa_row.shape == rang_row.shape else None)  # fmt: skip
        arm = name.split(".", 1)[1]
        if arm.startswith("T"):
            v |= tfcrop_verdict(casa, rang, before, a1, a2)
            v["G4"] = rows_equal
            v["pass"] = bool(v["G1"] and v["G2"] and v["G3"] and v["G4"])
        else:
            diff = casa != rang
            v["flag_diff"] = int(diff.sum())
            v["casa_changed"] = int((casa != before).sum())
            v["informative"] = v["casa_changed"] > 0
            if diff.any():
                r, c, p = np.nonzero(diff)
                v["first_diffs"] = [[int(a), int(b), int(d), bool(casa[a, b, d])]
                                    for a, b, d in zip(r[:20], c[:20], p[:20])]  # fmt: skip
                v["diff_rows"] = sorted({int(a) for a in r})[:50]
            sdiff = []
            for k, (cc, rc) in enumerate(zip(cj["calls"], rj["calls"])):
                if cc["params"].get("mode") == "summary":
                    sdiff += [f"call {k}{d}" for d in counts_diff(cc["return"], rc["return"])]
            v["summary_diff"] = sdiff[:50]
            v["summary_ndiff"] = len(sdiff)
            v["pass"] = bool(not diff.any() and rows_equal and not sdiff)
        verdicts[name] = v
    out_path.write_text(json.dumps(verdicts, indent=1), encoding="utf-8", newline="\n")
    npass = sum(1 for v in verdicts.values() if v.get("pass"))
    print(f"{npass}/{len(verdicts)} cases pass")
    for name, v in verdicts.items():
        if not v.get("pass"):
            brief = {k: v[k] for k in ("flag_diff", "flag_row_diff", "summary_ndiff",
                                       "agreement", "precision", "recall", "errors",
                                       "missing", "shape", "informative") if k in v}  # fmt: skip
            print(f"  FAIL {name}: {brief}")


if __name__ == "__main__":
    main(sys.argv[1:])
