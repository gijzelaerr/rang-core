# SPDX-License-Identifier: MIT
"""research/k-ambiguity.md section 6 (post hoc, solver-independent): on an MS
copy, per baseline of one antenna (and of control baselines without it), the
median over dumps of the adjacent-channel phase step angle(V[k+1] V[k]^*) per
parallel hand, on unflagged channel pairs; how many dumps show |step| > pi/2;
and the parity of the unflagged channels.

    python ka_raw.py MS ANT OUT.json
"""

import json
import sys

import numpy as np
from rang import core_ms


def main(ms, ant, out_path):
    ant = int(ant)
    with core_ms.open_table(ms) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        time = t.getcol("TIME")
        mine = np.flatnonzero(((a1 == ant) | (a2 == ant)) & (a1 != a2))
        others = np.flatnonzero((a1 != ant) & (a2 != ant) & (a1 != a2))
        rng = np.random.default_rng(0)
        bl_o = sorted({(int(a1[r]), int(a2[r])) for r in others})
        pick = {bl_o[i] for i in rng.choice(len(bl_o), 8, replace=False)}
        ctrl = np.array([r for r in others if (int(a1[r]), int(a2[r])) in pick])
        out = {"ms": ms, "ant": ant, "dumps": int(len(np.unique(time)))}
        for label, rows in (("ant", mine), ("control", ctrl)):
            d = t.getcol_rows("DATA", rows)
            f = t.getcol_rows("FLAG", rows).astype(bool)
            per_bl = {}
            parity = np.zeros(2, np.int64)
            for r_i, r in enumerate(rows):
                key = f"{int(a1[r])}-{int(a2[r])}"
                b = per_bl.setdefault(
                    key, {"steps": [[], []], "flip": [0, 0], "dumps": 0}
                )
                b["dumps"] += 1
                for h, c in ((0, 0), (1, 3)):
                    v = d[r_i, :, c]
                    ok = ~f[r_i, :, c] & (np.abs(v) > 0)
                    if h == 0:
                        idx = np.flatnonzero(ok)
                        parity += np.bincount(idx % 2, minlength=2)
                    pair = ok[1:] & ok[:-1]
                    if pair.sum() < 8:
                        continue
                    s = np.angle(v[1:][pair] * np.conj(v[:-1][pair]))
                    m = float(np.angle(np.mean(np.exp(1j * s))))
                    b["steps"][h].append(m)
                    b["flip"][h] += int(abs(m) > np.pi / 2)
            summ = {}
            for key, b in per_bl.items():
                summ[key] = {
                    "dumps": b["dumps"],
                    "median_abs_step_rad": [float(np.median(np.abs(x))) if x else None
                                            for x in b["steps"]],
                    "dumps_with_step_gt_pi/2": b["flip"],
                    "dumps_with_8_pairs": [len(x) for x in b["steps"]],
                }  # fmt: skip
            out[label] = summ
            out[f"{label}_unflagged_channel_parity_even_odd_X"] = parity.tolist()
            # first and last dump index of a flipped step per baseline (partial-scan event?)
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=1)
    flips = {k: v["dumps_with_step_gt_pi/2"] for k, v in out["ant"].items()}
    print(json.dumps({"dumps": out["dumps"], "ant_flips": flips,
                      "parity": out["ant_unflagged_channel_parity_even_odd_X"],
                      "control_flips": {k: v["dumps_with_step_gt_pi/2"]
                                        for k, v in out["control"].items()}}))  # fmt: skip


if __name__ == "__main__":
    main(*sys.argv[1:])
