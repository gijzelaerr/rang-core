"""Step 5 of research/e2a-3b-k.md, second part (after k_synth_probe.py showed
that strict stopping changes nothing and that the averaged solutions have the
lower unaveraged chi^2): a NumPy least-squares reference on the prepared,
unaveraged rows (alternating exact per-antenna updates to convergence, per
channel and hand, refant phase 0), against `cal_gain.solve` on the same
arrays with their weights and with unit weights, and the B solves.

    pytest -q -s -p no:cacheprovider research/results/e2a-3b-k/k_synth_probe2.py   (K_OUT=OUT.json)
"""

import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))

from k_synth_probe import chi2
from rang import cal_bandpass, cal_gain, core_ms
from test_e2_average_time import cal_ms, prepared, unit  # noqa: F401
from test_e2a_bandpass_model_divided import exact  # noqa: F401


def np_ls(arr, a1, a2, nant, refant=0, iters=3000):
    """(chan, ant, hand) minimising sum w |V - g_p g_q^* M|^2 per channel."""
    nchan = arr["data"].shape[1]
    out = np.ones((nchan, nant, 2), complex)
    cross = a1 != a2
    for h, c in enumerate((0, 3)):
        v = arr["data"][cross][..., c].astype(complex)
        m = np.broadcast_to(arr["model"], arr["data"].shape)[cross][..., c].astype(
            complex
        )
        w = np.broadcast_to(arr["weights"], arr["data"].shape)[cross][..., c].astype(
            float
        )
        f = np.broadcast_to(arr["flag"], arr["data"].shape)[cross][..., c]
        w = np.where(f, 0, w)
        p, q = a1[cross], a2[cross]
        g = np.ones((nchan, nant), complex)
        for _ in range(iters):
            old = g.copy()
            for a in range(nant):
                # rows where a is p: V ~ g_a g_q^* M ; rows where a is q: V^* ~ g_a g_p^* M^*
                sp, sq = p == a, q == a
                num = (w[sp] * v[sp] * np.conj(g[:, q[sp]].T * m[sp])).sum(0)
                den = (w[sp] * np.abs(g[:, q[sp]].T * m[sp]) ** 2).sum(0)
                num += (w[sq] * np.conj(v[sq]) * g[:, p[sq]].T * m[sq]).sum(0)
                den += (w[sq] * np.abs(g[:, p[sq]].T * m[sq]) ** 2).sum(0)
                g[:, a] = 0.5 * g[:, a] + 0.5 * np.where(
                    den > 0, num / np.where(den > 0, den, 1), g[:, a]
                )
            g *= np.exp(-1j * np.angle(g[:, refant]))[:, None]
            if np.max(np.abs(g - old)) < 1e-13:
                break
        out[..., h] = g
    return out


def test_probe2(exact):  # noqa: F811
    ms, model, tables, _ = exact
    with core_ms.open_table(ms / "ANTENNA") as t:
        positions = t.getcol("POSITION")
    out = {}
    for pre_name, pre in (("none", []), ("KG", tables)):
        fld, arr, _ = prepared(
            ms, 0, "B", model=model, weight_column="WEIGHT", gaintable=pre
        )
        a1, a2 = np.asarray(fld.meta["ANTENNA1"]), np.asarray(fld.meta["ANTENNA2"])
        nchan = arr["data"].shape[1]
        ref = np_ls(arr, a1, a2, 4)
        sols = {"numpy_ls": ref}
        for wname in ("weights", "unit"):
            w = arr["weights"] if wname == "weights" else np.ones_like(arr["weights"])
            s = cal_gain.solve(arr["data"], arr["model"], w, arr["flag"], fld.flag_row,
                               a1, a2, np.zeros(len(a1), np.int64), nant=4,
                               freq_bin=np.arange(nchan), refant=0, minblperant=2,
                               positions=positions, max_iterations=1000,
                               stop_criterion=1e-12, stop_fraction=1.0)  # fmt: skip
            sols[f"solve_{wname}"] = np.asarray(s.gains)[0]
        for vname, var in (
            ("plain", {}),
            ("div", {"average_time": True, "model_divided": True}),
        ):
            _, sol, _ = cal_bandpass.bandpass(ms, field_id=0, refant=0, combine="scan",
                                              minblperant=2, gaintable=pre, model=model,
                                              weight_column="WEIGHT", max_iterations=1000,
                                              stop_criterion=1e-12, stop_fraction=1.0, **var)  # fmt: skip
            sols[f"bandpass_{vname}"] = np.asarray(sol.gains)[0]
        unit_arr = dict(arr, weights=np.ones_like(arr["weights"]))
        res = {}
        for k, g in sols.items():
            res[k] = {"chi2": chi2(arr, a1, a2, g), "chi2_unit_weights": chi2(unit_arr, a1, a2, g),
                      "median_abs_vs_numpy_ls": float(np.median(np.abs(g - ref)))}  # fmt: skip
        out[pre_name] = res
        out[pre_name + "_weights"] = {"min": float(np.min(arr["weights"])), "max": float(np.max(arr["weights"])),
                                      "shape": list(np.shape(arr["weights"]))}  # fmt: skip
    Path(os.environ.get("K_OUT", "k-synth2.json")).write_text(
        json.dumps(out, indent=1) + "\n"
    )
    print(json.dumps(out, indent=1))
