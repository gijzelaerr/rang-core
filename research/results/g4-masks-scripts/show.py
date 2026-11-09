"""show.py TAG RUN...: a compact print of score.py's JSON (research/g4-masks.md)."""

import json
import os
import sys
from pathlib import Path

O = Path(os.environ.get("G4_OUT", "D:/rang/outputs/g4-20261109-01"))


def short(v):
    return f"{v:.3g}" if isinstance(v, float) else v


def main():
    tag = sys.argv[1]
    for run in sys.argv[2:]:
        r = json.loads((O / "runs" / tag / f"score-{run}.json").read_text())
        print(f"== {run}")
        s = r["S"]
        if s["missing"]:
            print("  S missing", s["missing"])
        for row in s["rows"]:
            bad = [k for k in row if k.endswith("_ok") and not row[k]]
            print(
                "  S",
                {k: short(v) for k, v in row.items() if not k.endswith("_ok")},
                bad,
            )
        if "B" in r:
            print("  B", {k: short(v) for k, v in r["B"].items() if k != "rows"})
        if "M" in r:
            m = r["M"]
            keys = [k for k in m if k not in ("apertures", "mask_json")]
            print("  M", {k: short(m[k]) for k in keys})
            for a in m["apertures"]:
                if not (a["M2"] and a["M3"]):
                    print("   ap", {k: short(v) for k, v in a.items()})
        if "X" in r:
            x = r["X"]
            print("  X", {k: short(v) for k, v in x.items() if k != "rows"})
            for row in x["rows"]:
                print("   ", {k: short(v) for k, v in row.items()})


if __name__ == "__main__":
    main()
