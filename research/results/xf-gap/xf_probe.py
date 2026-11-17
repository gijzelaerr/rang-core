# SPDX-License-Identifier: MIT
"""Post hoc probe (research/xf-gap.md section 7): rang's Xf closed form on
the ladder's L3 inputs (CASA's model.ms and CASA's K, G, B, Gpol, Kcross)
with the solve weights varied, against CASA's Xf.

    python xf_probe.py SET OUT.json

Arms: `as_is` (rang's weights: 1/SIGMA^2 with tables pre-applied), `calwt`
(each correlation's weight times |raw / corrected|^2, CASA's calwt scaling
by the applied tables), `unit_nomodel` (arg of the unweighted mean of V/M).
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import xf_gap as X


def load(ms, tables, interp):
    from rang import cal_pol

    return cal_pol.load(
        ms, field_id=1, solved="Xf", solint="inf", combine="scan", uvrange=">150",
        gaintable=tables, interp=interp, parang=True, frame="casa",
        weight_column=None, receptor_angle=math.radians(-90.0),
    )  # fmt: skip


def main(s, dest):
    from rang import cal_pol
    from rang.formats import caltable

    O = X.O
    ms = O / f"casa-{s}-m90" / "model.ms"
    ct = O / f"casa-{s}-m90" / "tables"
    tabs = [caltable.read(ct / t) for t in X.ORDER[:5]]
    ld = load(ms, tabs, ["linear"] * 4 + ["nearest"])
    raw = load(ms, (), "linear")
    assert np.array_equal(ld.rows, raw.rows)
    f = X._freq(s)
    nu0 = float(np.load(O / f"truth-{s}" / "gauge.npz")["nu0"])
    casa = X.xf_of(ct / "Xf")
    L3 = X.xf_of(O / f"ladder-{s}-m90_noavg-L3" / "Xf")

    def run(ldv):
        sol = cal_pol.xf_solve(ldv)
        return (sol.x[0], ~sol.ok[0], 0.0)

    res = {"weights_shape": list(np.shape(ld.weights)),
           "weights_unique": len(np.unique(ld.weights))}  # fmt: skip
    arms = {}
    arms["as_is"] = run(ld)
    with np.errstate(divide="ignore", invalid="ignore"):
        s2 = np.abs(raw.data) ** 2 / np.abs(ld.data) ** 2
    s2 = np.where(np.isfinite(s2), s2, 0.0)
    w0 = np.array(ld.weights, copy=True)
    ld.weights = (w0 * s2).astype(w0.dtype)
    arms["calwt"] = run(ld)
    ld.weights = w0
    # Unit weight per cell on V/M: weights 1/|M|^2 undo the |M|^2 the kernel applies.
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = np.where(np.abs(ld.model) > 0, 1.0 / np.abs(ld.model) ** 2, 0.0)
    ld.weights = (w0 * inv).astype(w0.dtype)
    arms["unit_nomodel"] = run(ld)
    ld.weights = w0
    res["as_is_vs_L3"] = X.summary(X.delta(arms["as_is"], L3), f, nu0)
    for k, v in arms.items():
        res[f"{k}_vs_CASA"] = X.summary(X.delta(v, casa), f, nu0)
    res["s2_range"] = [float(np.percentile(s2[s2 > 0], q)) for q in (1, 50, 99)]
    Path(dest).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
