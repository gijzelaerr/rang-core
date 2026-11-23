"""Task TS-P4: re-verify the unit-weight default (research/ts-p4.md 3).

Usage (worktree venv):
    python examples/ts_p4_verify.py MS TRUTH ROOT WSC_T1 WSC_D2 OUT_JSON

ROOT holds the runs `lc-old`, `lc-new`, `lc-ms` and `lc-unit`. V1 and V2
compare their CSVs byte for byte; V3-V6 score `lc-new` against WSClean 3.7
on the unit-weighted copy (W-T1 snapshots and pixels, W-D2 cell pixels) and
against the NumPy DFT with unit weights (ts_p2_measure.py, which reads the
run's weights); V7 checks that the default changed.
"""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
FILES = ("lightcurve.csv", "dynspec.csv", "candidates.csv")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same(a, b):
    return {f: (Path(a) / f).read_bytes() == (Path(b) / f).read_bytes() for f in FILES}


def main(argv=None):
    ms, truth_path, root, t1, d2, out = (argv or sys.argv[1:])[:6]
    root = Path(root)
    m1, m2 = _load("ts_p1_measure"), _load("ts_p2_measure")
    res = {}
    v1, v2 = (
        same(root / "lc-ms", root / "lc-old"),
        same(root / "lc-new", root / "lc-unit"),
    )
    res["V1"] = {"files": v1, "pass": all(v1.values())}
    res["V2"] = {"files": v2, "pass": all(v2.values())}
    new = json.loads((root / "lc-new/lightcurve.json").read_text(encoding="utf-8"))
    old = json.loads((root / "lc-old/lightcurve.json").read_text(encoding="utf-8"))
    res["settings_weights"] = {"new": new["settings"].get("weights"),
                               "old": old["settings"].get("weights")}  # fmt: skip
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    sig = np.array(truth["sigma_snap_interval_jy"], np.float64)
    flux = np.array(new["flux_jy"], np.float64)
    w = m1.compare_wsclean(t1, ms, root / "lc-new", new, flux, sig, new["intervals"])
    s2 = m2.score(ms, truth_path, root / "lc-new", d2)
    # V4: the band DFT against WSClean's pixel and against NumPy (T2a-type).
    o = m2.oracle(ms, truth, new, new["settings"]["channels_out"])
    dft_band = np.abs(flux - o["dft_band"]) / sig[:, None]
    res["V3"] = w["T1"]
    res["V4"] = {
        "wsclean_max_over_sigma": w["T2c"]["max_over_sigma"],
        "numpy_max_over_sigma": float(dft_band.max()),
        "pass": bool(w["T2c"]["pass"] and dft_band.max() <= 1e-3),
    }
    res["V5"] = {
        "wsclean_max_over_sigma": s2["D2"]["max_over_sigma"],
        "numpy_max_over_sigma": s2["D1"]["max_over_sigma"],
        "crval3_max_offset_hz": s2["D2"]["crval3_max_offset_hz"],
        "pass": bool(s2["D2"]["pass"] and s2["D1"]["pass"]),
    }
    res["V6"] = {"D4": s2["D4"], "D5": s2["D5"],
                 "pass": bool(s2["D4"]["pass"] and s2["D5"]["pass"])}  # fmt: skip
    diff = np.abs(flux - np.array(old["flux_jy"], np.float64))
    res["V7"] = {"max_abs_change_over_sigma": float((diff / sig[:, None]).max()),
                 "pass": bool(diff.max() > 0)}  # fmt: skip
    res["reported"] = {"D3": s2["D3"]["per_source"], "D3b": s2["D3b"]["per_source"]}
    res["gates"] = {
        g: bool(res[g]["pass"]) for g in ("V1", "V2", "V3", "V4", "V5", "V6", "V7")
    }
    res["all_pass"] = all(res["gates"].values())
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"gates": res["gates"], "all_pass": res["all_pass"]}))
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
