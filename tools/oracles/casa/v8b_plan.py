# SPDX-License-Identifier: GPL-3.0-or-later
"""The V8b case list (research/v8b-flagdata.md, section 4) as `flagdata.py`
plans: every (input, arm) pair, one CASA call list each.

Usage: v8b_plan.py dev|heldout OUT.json

Arms take the input paths of `flagdata.sh` (`/in/...`). `rang`'s side reads
the same list through `rang.oracles.casa_flagdata.cases`.
"""

import json
import sys

DEV_INPUTS = {
    "syn-noise": "/in/cases/syn-noise.ms",
    "syn-rfi": "/in/cases/syn-rfi.ms",
    "syn-edges": "/in/cases/syn-edges.ms",
    "luno": "/in/luno.ms",
    "a1": "/in/a1.ms",
}
FIXTURE = {f"fixture-scan{s}": f"/in/fixture/1672727931_sdp_l0_scan_{s}.ms"
           for s in (1, 4, 5, 8, 9)}  # fmt: skip
HELDOUT_INPUTS = FIXTURE | {"eso137-ho": "/in/heldout/eso137-ho.ms"}

TFCROP = {
    "T1": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False}],
    "T2": [{"mode": "tfcrop", "flagdimension": "time", "extendflags": False}],
    "T3": [{"mode": "tfcrop", "extendflags": False}],
    "T4": [{"mode": "tfcrop"}],
    "T5": [{"mode": "tfcrop", "usewindowstats": "std", "combinescans": False,
            "flagdimension": "freqtime", "timecutoff": 4.0, "freqcutoff": 3.0,
            "correlation": "", "datacolumn": "data"}],
    "T6": [{"mode": "tfcrop", "usewindowstats": "both", "halfwin": 2}],
    "T7": [{"mode": "tfcrop", "timefit": "poly", "freqfit": "line", "maxnpieces": 4,
            "flagdimension": "timefreq"}],
    "T8": [{"mode": "tfcrop", "ntime": "60s", "combinescans": True,
            "correlation": "ABS_XX,YY"}],
}  # fmt: skip
TFCROP_CASES = {
    "T1": ("syn-noise", "syn-rfi", "a1", "luno"),
    "T2": ("syn-noise", "syn-rfi", "a1", "luno"),
    "T3": ("syn-noise", "syn-rfi", "a1", "luno"),
    "T4": ("syn-noise", "syn-rfi", "a1", "luno"),
    "T5": ("syn-noise", "syn-rfi", "a1", "luno"),
    "T6": ("syn-rfi", "luno"),
    "T7": ("syn-rfi", "luno"),
    "T8": ("luno", "a1"),
}
CARACAL_SPW = "*:856~880MHz , *:1658~1800MHz, *:1419.8~1421.3MHz"
EXTEND_E0 = {"mode": "extend", "ntime": "60s", "combinescans": True, "growtime": 80.0,
             "growfreq": 80.0, "growaround": True, "flagneartime": True,
             "flagnearfreq": True}  # fmt: skip
SUMMARIES = [
    {"mode": "summary"},
    {"mode": "summary", "basecnt": True},
    {"mode": "summary", "spwchan": True, "spwcorr": True},
]


def fixed_arms(edges):
    """The fixed-rule arms; `edges` adds the arms that need syn-edges'
    names, times and values."""
    arms = {
        "M1": [{"mode": "unflag"}],
        "M2": [{"mode": "manual", "autocorr": True}],
        "M3": [{"mode": "quack", "quackinterval": 8.0, "quackmode": "beg"}],
        "M4a": [{"mode": "quack", "quackinterval": 8.0, "quackmode": "endb"}],
        "M4b": [{"mode": "quack", "quackinterval": 8.0, "quackmode": "tail"}],
        "M4c": [{"mode": "quack", "quackinterval": 8.0, "quackmode": "end"}],
        "M4d": [{"mode": "quack", "quackinterval": 8.0, "quackmode": "beg",
                 "quackincrement": True}],
        "M5a": [{"mode": "elevation", "lowerlimit": 0.0, "upperlimit": 90.0}],
        "M5b": [{"mode": "elevation", "lowerlimit": 20.0, "upperlimit": 60.0}],
        "M6a": [{"mode": "shadow", "tolerance": 0.0}],
        "M6b": [{"mode": "shadow", "tolerance": 2.0}],
        "M7": [{"mode": "manual", "spw": CARACAL_SPW}],
        "M14a": [{"mode": "clip", "clipminmax": [0.0, 50.0]}],
        "M14b": [{"mode": "clip", "clipminmax": [0.0, 50.0], "clipoutside": False}],
        "M14c": [{"mode": "clip", "clipzeros": True}],
        "M14d": [{"mode": "clip", "clipminmax": [-50.0, 50.0], "correlation": "REAL_XX"}],
        "M14e": [{"mode": "clip"}],
        "M15a": [EXTEND_E0],
        "M15b": [{"mode": "extend"}],
        "M16a": [{"mode": "quack", "quackinterval": 8.0}, {"mode": "shadow"},
                 {"mode": "manual", "spw": CARACAL_SPW}] + SUMMARIES,
    }  # fmt: skip
    if edges:
        arms |= {
            "M8a": [{"mode": "manual", "spw": "0:0~9;20~29"}],
            "M8b": [{"mode": "manual", "spw": "*:5~7"}],
            "M8c": [{"mode": "manual", "spw": "1"}],
            "M9": [{"mode": "manual", "timerange": "2026/01/01/03:00:40~03:01:20"}],
            "M10a": [{"mode": "manual", "scan": "1,3"}],
            "M10b": [{"mode": "manual", "field": "EDGES"}],
            "M10c": [{"mode": "manual", "field": "0", "scan": "4"}],
            "M11a": [{"mode": "manual", "antenna": "m001"}],
            "M11b": [{"mode": "manual", "antenna": "m001&m002"}],
            "M11c": [{"mode": "manual", "antenna": "!m000"}],
            "M11d": [{"mode": "manual", "antenna": "m003",
                      "timerange": "2026/01/01/03:40:00~03:42:00"}],
            "M12a": [{"mode": "manual", "uvrange": "<100m"}],
            "M12b": [{"mode": "manual", "uvrange": "1~3km"}],
            "M13": [{"mode": "manual", "correlation": "XY,YX"}],
        }  # fmt: skip
    return arms


def dev_plan():
    plan = []
    for arm, calls in TFCROP.items():
        for case in TFCROP_CASES[arm]:
            plan.append({"name": f"{case}.{arm}", "input": DEV_INPUTS[case], "calls": calls})
    for case in ("syn-edges", "luno", "a1"):
        for arm, calls in fixed_arms(case == "syn-edges").items():
            plan.append({"name": f"{case}.{arm}", "input": DEV_INPUTS[case], "calls": calls})
    for df in ("B-poldx", "B-twin", "B-poldx-uv"):
        plan.append({"name": f"df-{df}.M17", "input": f"/in/df/{df}.Df",
                     "calls": [{"mode": "clip", "clipminmax": [-0.6, 0.6],
                                "datacolumn": "CPARAM"}]})  # fmt: skip
    return plan


def heldout_plan():
    plan = []
    for arm in ("T4", "T5"):
        plan.append({"name": f"eso137-ho.{arm}", "input": HELDOUT_INPUTS["eso137-ho"],
                     "calls": TFCROP[arm]})  # fmt: skip
    fixed = fixed_arms(False)
    for case, path in HELDOUT_INPUTS.items():
        for arm in ("M1", "M2", "M3", "M5a", "M5b", "M6a", "M7", "M14a", "M16a"):
            plan.append({"name": f"{case}.{arm}", "input": path, "calls": fixed[arm]})
    return plan


if __name__ == "__main__":
    which, out = sys.argv[1], sys.argv[2]
    plan = dev_plan() if which == "dev" else heldout_plan()
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan, f, indent=1)
    print(len(plan), "cases")
