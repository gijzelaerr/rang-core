"""DD9 A2 (post hoc): the default map's rates at its own and at I2's fixed
point, split by when the default converges, and the default's extra flags.
Writes D:/rang/outputs/dd9-20261126/jac/posthoc_a2.json.

    python research/results/dd9-solver/scripts/posthoc_a2.py
"""

import glob
import importlib.util
import json
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[4]
R = "D:/rang/outputs/dd9-20261126"
spec = importlib.util.spec_from_file_location(
    "runs", W / "tools" / "oracles" / "dd9" / "runs.py"
)
runs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runs)
dd9 = runs.dd9


def rows(pattern):
    out = []
    for p in sorted(glob.glob(pattern)):
        out += json.loads(Path(p).read_text())["rows"]
    return sorted(out, key=lambda r: r["interval"])


def split(rs, nc):
    classes = {"<=500": lambda i: nc[i] <= 500, "500-2000": lambda i: 500 < nc[i] <= 2000,
               ">2000": lambda i: nc[i] > 2000, "all": lambda i: True}  # fmt: skip
    out = {}
    for lab, sel in classes.items():
        rf, rw, r2, r3, r1 = [], [], [], [], []
        for r in rs:
            hs = [h for h in r["hands"] if h]
            if not sel(r["interval"]) or not hs:
                continue
            h = max(hs, key=lambda x: x["rho_full"])
            rf.append(h["rho_full"])
            rw.append([x if x is not None else np.nan for x in h["rho_within"]])
            r1.append(h["rho_I1"]), r2.append(h["rho_I2"]), r3.append(h["rho_I3"])
        rf, rw = np.array(rf), np.array(rw)
        out[lab] = {"intervals": len(rf), "rho_full_median": float(np.median(rf)), "rho_full_max": float(rf.max()),
                    "rho_full_gt1": int((rf > 1).sum()), "rho_within_median": np.nanmedian(rw, 0).tolist(),
                    "rho_within_gt1": (rw > 1).sum(0).tolist(), "rho_I1_median": float(np.median(r1)),
                    "rho_I2_median": float(np.median(r2)), "rho_I2_max": float(max(r2)),
                    "rho_I3_median": float(np.median(r3))}  # fmt: skip
    return out


rec = {}
for base in ("B-X", "O-X"):
    nc = np.array(
        json.loads(Path(f"{R}/solve/{base}-default.json").read_text())["N_conv"]
    )
    rec[f"{base} N_conv classes"] = {"<=500": int((nc <= 500).sum()), "500-2000": int(((nc > 500) & (nc <= 2000)).sum()),
                                     ">2000": int((nc > 2000).sum()), "median": float(np.median(nc))}  # fmt: skip
    rec[f"{base} at default cap 2000"] = split(rows(f"{R}/jac/{base}-*.json"), nc)
nc = np.array(json.loads(Path(f"{R}/solve/O-X-default.json").read_text())["N_conv"])
rec["O-X at I2 cap 2000"] = split(rows(f"{R}/jac/at-I2/O-X-*.json"), nc)
a = runs.load(f"{R}/solve/O-X-default.npz", 2000, 4)
b = runs.load(f"{R}/solve/O-X-I2.npz", 2000, 4)
fa, fb = np.stack(a["f"], -1), np.stack(b["f"], -1)
extra = ((fa != 0) & (fb == 0)).sum((1, 2))
rec["O-X default extra flags against I2"] = {
    lab: {
        "intervals": int(sel.sum()),
        "with_extra": int((extra[sel] > 0).sum()),
        "extra_total": int(extra[sel].sum()),
    }
    for lab, sel in (
        ("<=500", nc <= 500),
        ("500-2000", (nc > 500) & (nc <= 2000)),
        (">2000", nc > 2000),
    )
}
Path(f"{R}/jac/posthoc_a2.json").write_text(json.dumps(rec, indent=1))
print(json.dumps(rec, indent=1))
