# SPDX-License-Identifier: MIT
"""Post hoc (labelled, after the held-out read; research/calwt-terms.md
section 12): how far each key moves rang's own keyed tables in the full
chain (arm against `off`, section 7's table measure), next to the truth
floor (the `off` arm's composite errors), on H1-H4.

    python posthoc.py OUT.json
"""

import json
import sys

import calwt_terms as c
import numpy as np

ARM_OF = {"K2": "k", "Kg": "k", "G2": "g", "Gg": "g", "Gpol": "gpol",
          "Kcross": "kcross", "Df": "df"}  # fmt: skip


def main(argv):
    out = {"moved": {}, "rang_vs_casa_off": {}}
    for name, arm in ARM_OF.items():
        mv, gap = [], []
        for s in ("H1", "H2", "H3", "H4"):
            off = c.rang_tables(c.O / f"rang-{s}-off")
            on = c.rang_tables(c.O / f"rang-{s}-{arm}")
            mv.append(
                c.table_diff(name, c._tab(on / name), c._tab(off / name))["median"]
            )
            gap.append(c.table_diff(name, c._tab(off / name),
                                    c._tab(c.O / f"casa-{s}" / "tables" / name))["median"])  # fmt: skip
        out["moved"][name] = {"per_set": mv, "mean": float(np.mean(mv))}
        out["rang_vs_casa_off"][name] = {"per_set": gap, "mean": float(np.mean(gap))}
    with open(argv[0], "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    for n in ARM_OF:
        moved, gap = out["moved"][n]["mean"], out["rang_vs_casa_off"][n]["mean"]
        print(f"{n} moved {moved:.3g} rang-casa {gap:.3g}")


if __name__ == "__main__":
    main(sys.argv[1:])
