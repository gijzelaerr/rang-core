"""Task TS-P3: score the real track's weighting and control-referenced gates
(research/ts-p3.md, section 4).

Usage (worktree venv):
    python examples/ts_p3_measure.py MS TRUTH LC_INJ LC_CONTROL OUT_JSON
        [--wsclean-t1 DIR --wsclean-d2 DIR]

LC_INJ and LC_CONTROL are `rang-core lightcurve --channels-out M` runs of the
injected and the uninjected residual with the same `--weights`. The script
reuses ts_p2_measure.py (independent NumPy DFT per group and over the band,
expected dirty values from the truth, WSClean pixels) and ts_p1_measure.py
(WSClean snapshot comparison), and adds the control-referenced residual

    R = flux(injected) - flux(control) - expected

per interval and position (band) and per cell (C1-C4), plus T3d on the
injected run (C5). With `--wsclean-*`: U1 (snapshots), U2c (band pixel) and
U4 (cell pixel). Every gate's bound is in ts-p3.md 4.
"""

import argparse
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m2 = _load("ts_p2_measure")
m1 = _load("ts_p1_measure")
BOUND = 1e-3


def _lc(d):
    return json.loads((Path(d) / "lightcurve.json").read_text(encoding="utf-8"))


def _cells(lcj):
    return np.array(
        [[[math.nan if v is None else v for v in g] for g in k]
         for k in lcj["dynspec_flux_jy"]], np.float64)  # fmt: skip


def control_referenced(ms, truth, inj, ctl):
    """C1-C4: R over the band (in sigma_meas) and per cell (in sigma_dyn)."""
    if inj["settings"].get("weights") != ctl["settings"].get("weights"):
        raise SystemExit("injected and control runs use different weights")
    groups = inj["settings"]["channels_out"]
    o = m2.oracle(ms, truth, inj, groups)
    names = [p["name"] for p in inj["positions"]]
    sm = float(np.median(inj["sigma_meas_jy"]))
    f = names.index("F")
    cc = _cells(ctl)
    sig_g = np.array([m2.robust(cc[:, f, g]) for g in range(groups)])
    band = np.array(inj["flux_jy"]) - np.array(ctl["flux_jy"]) - o["exp_band"]
    cell = (_cells(inj) - cc - o["exp"]) / sig_g[None, None, :]
    per = {}
    for s, n in enumerate(names):
        per[n] = {
            "C1_mean_band": float(abs(band[:, s].mean()) / sm),
            "C2_max_band": float(np.abs(band[:, s]).max() / sm),
            "C3_mean_cell": float(abs(np.nanmean(cell[:, s, :]))),
            "C4_max_cell": float(np.nanmax(np.abs(cell[:, s, :]))),
        }
    gated = [n for n in names if n != "F"]
    out = {"per_source": per, "gated_sources": gated, "sigma_meas_jy": sm,
           "sigma_dyn_jy": sig_g.tolist()}  # fmt: skip
    for key in ("C1_mean_band", "C2_max_band", "C3_mean_cell", "C4_max_cell"):
        out[key[:2]] = {
            "max": max(per[n][key] for n in gated),
            "pass": all(per[n][key] <= BOUND for n in gated),
        }
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for k in ("ms", "truth", "lc_inj", "lc_ctl", "out"):
        p.add_argument(k)
    p.add_argument("--wsclean-t1")
    p.add_argument("--wsclean-d2")
    a = p.parse_args(argv)
    started = time.perf_counter()
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8"))
    inj, ctl = _lc(a.lc_inj), _lc(a.lc_ctl)
    res = {"weights": inj["settings"].get("weights", "ms")}
    s2 = m2.score(a.ms, a.truth, a.lc_inj, a.wsclean_d2, real=True, control=a.lc_ctl)
    res["p2_score"] = s2
    res["U2a"] = s2["T2a"]
    res["U2b"] = s2["T2b"]
    res["U3"] = s2["D1"]
    res["C5"] = s2["T3d"]
    res["uncontrolled_T3a"] = s2["T3a"]
    res["uncontrolled_D3"] = s2["D3"]
    if a.wsclean_d2:
        res["U4"] = s2["D2"]
    res.update(control_referenced(a.ms, truth, inj, ctl))
    if a.wsclean_t1:
        n = inj["intervals"]
        flux = np.array(inj["flux_jy"], np.float64)
        sig = np.array(inj["sigma_meas_jy"], np.float64)
        w = m1.compare_wsclean(a.wsclean_t1, a.ms, a.lc_inj, inj, flux, sig, n)
        res["U1"], res["U2c"] = w["T1"], w["T2c"]
    gates = ["U2a", "U2b", "U3", "C1", "C2", "C3", "C4", "C5"]
    gates += [g for g in ("U1", "U2c", "U4") if g in res]
    res["gates"] = {g: bool(res[g]["pass"]) for g in gates}
    res["all_pass"] = all(res["gates"].values())
    res["seconds"] = time.perf_counter() - started
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"gates": res["gates"], "all_pass": res["all_pass"]}))
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
