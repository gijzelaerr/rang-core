"""F3 Stage 1: W3's flags are a subset of T's on one validation scan per class
and source (research/f3-flagger.md, section 2).

Usage: python examples/f3_subset.py OUT.json
"""

import json
import os
import sys
from pathlib import Path

from rang import f2flag_sim as fs
from rang import f3flag as f3


def check(scan):
    w3 = f3.w3_flags(scan)
    t = f3.t_flags(scan)
    extra = w3 & ~t
    return {
        "field": scan["field"],
        "class": scan["klass"],
        "w3_fraction": float(w3.mean()),
        "t_fraction": float(t.mean()),
        "w3_not_t": int(extra.sum()),
        "subset": bool(not extra.any()),
    }


def main():
    out = sys.argv[1]
    out = Path(os.environ["RUN_DIR"]) / out[4:] if out.startswith("RUN/") else Path(out)
    res = []
    for scan in (
        f3.load_luno("MAIN_7"),
        f3.load_eso(10),
        f3.load_fsim(fs.scans_of(f3.F2_VAL, "calibrator")[0]),
        f3.load_fsim(fs.scans_of(f3.F2_VAL, "target")[0]),
    ):
        res.append(check(scan))
        print(json.dumps(res[-1]), flush=True)
    out.write_text(
        json.dumps(
            {"checks": res, "all_subset": all(r["subset"] for r in res)}, indent=1
        )
    )


if __name__ == "__main__":
    main()
