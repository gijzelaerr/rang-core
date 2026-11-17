"""Step 5 of research/e2a-3b-k.md (H-C, H-W): the 4-antenna test synthetic
of `tests/test_e2a_bandpass_model_divided.py` (fixture `exact`, unchanged).
B unaveraged, averaged (separate), averaged divided and unaveraged divided,
at the chain's stop rule and strict, with nothing and with K, G
pre-applied; for each, median |g - g_plain| and the unaveraged weighted
chi^2 at the solution. Run as

    pytest -q -s -p no:cacheprovider research/results/e2a-3b-k/k_synth_probe.py   (K_OUT=OUT.json)
"""

import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))

from rang import cal_bandpass  # noqa: E402
from test_e2_average_time import cal_ms, prepared, unit  # noqa: E402,F401
from test_e2a_bandpass_model_divided import exact  # noqa: E402,F401

RULES = {"chain": {}, "strict": {"max_iterations": 1000, "stop_criterion": 1e-12,
                                 "stop_fraction": 1.0}}  # fmt: skip
VARIANTS = {"plain": {}, "sep": {"average_time": True},
            "div": {"average_time": True, "model_divided": True},
            "div_unavg": {"model_divided": True}}  # fmt: skip


def chi2(arr, ant1, ant2, gains):
    """sum w |V - g_p g_q^* M|^2 over unflagged parallel-hand cells of the
    prepared (unaveraged) rows; gains (chan, ant, hand)."""
    total = 0.0
    for h, c in enumerate((0, 3)):
        v = arr["data"][..., c].astype(np.complex128)
        m = np.broadcast_to(arr["model"], arr["data"].shape)[..., c].astype(np.complex128)
        w = np.broadcast_to(arr["weights"], arr["data"].shape)[..., c].astype(float)
        f = np.broadcast_to(arr["flag"], arr["data"].shape)[..., c]
        gp = gains[:, ant1, h].T  # (row, chan)
        gq = gains[:, ant2, h].T
        r = v - gp * np.conj(gq) * m
        ok = ~f & (ant1 != ant2)[:, None] & np.isfinite(r)
        total += float((w * np.abs(r) ** 2)[ok].sum())
    return total


def test_probe(exact, request):  # noqa: F811
    ms, model, tables, _ = exact
    out = {}
    for pre_name, pre in (("none", []), ("KG", tables)):
        fld, arr, _ = prepared(ms, 0, "B", model=model, weight_column="WEIGHT", gaintable=pre)
        a1, a2 = fld.meta["ANTENNA1"], fld.meta["ANTENNA2"]
        sols = {}
        for rname, rule in RULES.items():
            for vname, var in VARIANTS.items():
                _, sol, _ = cal_bandpass.bandpass(ms, field_id=0, refant=0, combine="scan",
                                                  minblperant=2, gaintable=pre, model=model,
                                                  weight_column="WEIGHT", **rule, **var)  # fmt: skip
                sols[(rname, vname)] = (np.asarray(sol.gains)[0, :, :, :],
                                        np.asarray(sol.flags)[0], sol.iterations)  # fmt: skip
        res = {}
        for (rname, vname), (g, f, it) in sols.items():
            gp, fp, _ = sols[(rname, "plain")]
            gs, fs, _ = sols[("strict", "plain")]
            ok = ~f & ~fp & ~fs
            res[f"{rname}/{vname}"] = {
                "iterations": int(np.max(np.asarray(it))),
                "median_abs_vs_plain_same_rule": float(np.median(np.abs(g - gp)[ok])),
                "max_abs_vs_plain_same_rule": float(np.max(np.abs(g - gp)[ok])),
                "median_abs_vs_strict_plain": float(np.median(np.abs(g - gs)[ok])),
                "chi2_unaveraged": chi2(arr, a1, a2, np.where(f, 1, g)),
                "flagged": int(f.sum()),
            }
        out[pre_name] = res
    path = os.environ.get("K_OUT", "k-synth.json")
    Path(path).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
