"""F2: pool `f2_measure.py` results of one class over observations (counts and
Q3 sums added), and recompute the calls of section 5.

Usage: python examples/f2_combine.py OUT.json IN.json [IN.json ...]
"""

import json
import sys
from pathlib import Path

import numpy as np
from rang import f2flag as ff

sys.path.insert(0, str(Path(__file__).parent))
from f2_measure import calls


def main():
    out, *ins = sys.argv[1:]
    counts, q3 = {}, {}
    klass = None
    for path in ins:
        r = json.loads(Path(path).read_text())
        klass = r["class"]
        for label, c in r["counts"].items():
            ff.add_counts(counts.setdefault(label, {}), c)
        for label, v in r["q3_sums"].items():
            t = q3.setdefault(label, {"num": 0.0, "den": 0.0})
            t["num"] += v["num"]
            t["den"] += v["den"]
    result = {
        "class": klass,
        "inputs": ins,
        "pooled": {k: ff.pooled(v) for k, v in counts.items()},
        "q3": {k: float(np.sqrt(v["num"] / v["den"])) for k, v in q3.items()},
        "q3_sums": q3,
        "counts": counts,
    }
    result["calls"] = calls(result)
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result["calls"], indent=1))


if __name__ == "__main__":
    main()
