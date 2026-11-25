# SPDX-License-Identifier: MIT
"""One line per DD7 grid record: fractions, step medians, e/ê, flags."""

import json
import math
import sys


def fmt(xs):
    return ", ".join("nan" if math.isnan(x) else f"{x:.3g}" for x in xs)


for p in sys.argv[1:]:
    with open(p) as fh:
        r = json.load(fh)
    steps = [s["median"] or 0 for s in r["step_stats"]]
    print(
        p.split("/")[-1][:-5],
        "| frac",
        fmt(r["perdir_converged"]),
        "| step med",
        fmt(steps),
        "| e/ehat",
        fmt(r["e_over_ehat"]),
        "| flag",
        r["flagged_per_direction"],
        "| d0 ph",
        round(r["phase_std_rad"][0], 3),
        "| it",
        r["iterations"],
    )
