"""Step 5 of research/e2a-3b-k.md, second part (after k_synth_probe.py showed
that strict stopping changes nothing and that the averaged solutions have the
lower unaveraged chi^2): a SciPy least-squares reference on the prepared,
unaveraged rows (per channel and hand, refant phase 0, started from both B solutions), against `cal_gain.solve` on the same
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


def scipy_ls(arr, a1, a2, skip, nant, starts, refant=0):
    """(chan, ant, hand) minimising sum w |V - g_p g_q^* M|^2 per channel and
    hand (scipy least_squares, refant imaginary part 0), from each start in
    `starts` (chan, ant, hand); the lowest cost kept."""
    from scipy.optimize import least_squares

    nchan = arr["data"].shape[1]
    out = np.ones((nchan, nant, 2), complex)
    use = (a1 != a2) & ~skip
    p, q = a1[use], a2[use]
    for h, c in enumerate((0, 3)):
        shape = arr["data"].shape
        v = arr["data"][use][..., c].astype(complex)
        m = np.broadcast_to(arr["model"], shape)[use][..., c].astype(complex)
        w = np.broadcast_to(arr["weights"], shape)[use][..., c].astype(float)
        f = np.broadcast_to(arr["flag"], shape)[use][..., c]
        sw = np.sqrt(np.where(f, 0, w))
        for ch in range(nchan):

            def res(x, sw=sw, ch=ch, v=v, m=m):
                g = x[:nant] + 1j * np.insert(x[nant:], refant, 0.0)
                r = sw[:, ch] * (v[:, ch] - g[p] * np.conj(g[q]) * m[:, ch])
                return np.concatenate([r.real, r.imag])

            best = None
            for st in starts:
                g0 = st[ch, :, h] * np.exp(-1j * np.angle(st[ch, refant, h]))
                x0 = np.concatenate([g0.real, np.delete(g0.imag, refant)])
                r = least_squares(
                    res, x0, xtol=1e-15, ftol=1e-15, gtol=1e-15, max_nfev=20000
                )
                if best is None or r.cost < best.cost:
                    best = r
            x = best.x
            out[ch, :, h] = x[:nant] + 1j * np.insert(x[nant:], refant, 0.0)
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
        skip = np.asarray(fld.flag_row | fld.auto, bool)
        sols = {}
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
        ref = scipy_ls(
            arr, a1, a2, skip, 4, [sols["bandpass_plain"], sols["bandpass_div"]]
        )
        sols["scipy_ls"] = ref
        unit_arr = dict(arr, weights=np.ones_like(arr["weights"]))
        res = {}
        for k, g in sols.items():
            res[k] = {"chi2": chi2(arr, a1, a2, g, skip),
                      "chi2_unit_weights": chi2(unit_arr, a1, a2, g, skip),
                      "median_abs_vs_scipy_ls": float(np.median(np.abs(g - ref)))}  # fmt: skip
        out[pre_name] = res
        out[pre_name + "_weights"] = {"min": float(np.min(arr["weights"])), "max": float(np.max(arr["weights"])),
                                      "shape": list(np.shape(arr["weights"]))}  # fmt: skip
    Path(os.environ.get("K_OUT", "k-synth2.json")).write_text(
        json.dumps(out, indent=1) + "\n"
    )
    print(json.dumps(out, indent=1))
