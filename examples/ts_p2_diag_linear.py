"""TS-P2 real track, post hoc diagnostic (research/ts-p2.md 10.3, not a gate):
the injected run minus the uninjected run against the expected dirty value of
the injections alone, per source over the band (T3a's quantity) and per cell
(D3's), in sigma_meas and sigma_dyn. It separates the product's recovery from
the residual sky's mean at each position.

    python examples/ts_p2_diag_linear.py MS TRUTH LC_INJ LC_CONTROL OUT_JSON
"""

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "ts_p2_measure", Path(__file__).with_name("ts_p2_measure.py")
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def load(d):
    return json.loads((Path(d) / "lightcurve.json").read_text(encoding="utf-8"))


def cells(lcj):
    return np.array(
        [[[math.nan if v is None else v for v in g] for g in k]
         for k in lcj["dynspec_flux_jy"]], np.float64)  # fmt: skip


def main(argv=None):
    ms, truth_path, inj_dir, ctl_dir, out = (argv or sys.argv[1:])[:5]
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    inj, ctl = load(inj_dir), load(ctl_dir)
    groups = inj["settings"]["channels_out"]
    o = m.oracle(ms, truth, inj, groups)
    names = [p["name"] for p in inj["positions"]]
    sm = float(np.median(inj["sigma_meas_jy"]))
    band = np.array(inj["flux_jy"]) - np.array(ctl["flux_jy"]) - o["exp_band"]
    f = names.index("F")
    sig_g = np.array([m.robust(cells(ctl)[:, f, g]) for g in range(groups)])
    dyn = (cells(inj) - cells(ctl) - o["exp"]) / sig_g[None, None, :]
    res = {
        "band_bias_over_sigma_meas": {
            n: float(band[:, s].mean() / sm) for s, n in enumerate(names)
        },
        "band_max_abs_over_sigma_meas": float(np.abs(band).max() / sm),
        "cell_bias_over_sigma_dyn": {
            n: float(np.nanmean(dyn[:, s, :])) for s, n in enumerate(names)
        },
        "cell_max_abs_over_sigma_dyn": float(np.nanmax(np.abs(dyn))),
        "control_mean_over_sigma_meas": {
            n: float(np.mean(ctl["flux_jy"], axis=0)[s] / sm)
            for s, n in enumerate(names)
        },
    }
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res))


if __name__ == "__main__":
    main()
