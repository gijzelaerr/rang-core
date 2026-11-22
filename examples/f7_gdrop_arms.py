"""F7 D5 (research/f7-flagger.md), validation only: G-drop split by arm (N5, W4, method).

Usage: python examples/f7_gdrop_arms.py OUT.json --method M.json --set eso:10 [--data-root R]

G-drop as examples/f5_heldout.py: for k = 1, 4, 8 and seeds 20265301-03, the live antennas
f5.drop_draw removes; per arm, the symmetric difference of its added cells on the remaining
baselines against the full-array run, over the full-array added cells there.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from rang import f3flag as f3
from rang import f5flag as f5

SEEDS = (20265301, 20265302, 20265303)


def arms(scan, w3, m, w):
    logit, anom = f5.rust_logits_anomaly(scan, w3, w, m["level"], m["degree"])
    n5 = logit > m["tau"]
    with np.errstate(invalid="ignore"):
        w4 = anom > m["kappa"] if m.get("kappa") is not None else np.zeros_like(n5)
    return {"N5": n5, "W4": w4, "method": n5 | w4}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--method", type=Path, required=True)
    p.add_argument("--set", default="eso:10")
    p.add_argument("--data-root")
    a = p.parse_args()
    if a.data_root:
        f5.use_data_root(a.data_root)
    m = json.loads(a.method.read_text())
    w = np.asarray(np.load(m["weights"])["flat"], np.float32)
    full = f5.load(a.set)
    w3 = f3.w3_flags(full)
    a0 = arms(full, w3, m, w)
    out = {"method_file": str(a.method), "set": a.set, "cases": []}
    for k in (1, 4, 8):
        for s in SEEDS:
            keep = f5.drop_draw(full, k, s)
            sc, rows = f5.subarray(full, keep)
            ws = f3.w3_flags(sc)
            a1 = arms(sc, ws, m, w)
            el = ~ws
            c = {"k": k, "seed": s}
            for name in ("N5", "W4", "method"):
                fa = a0[name][rows] & el
                sa = a1[name] & el
                c[name] = {
                    "full_added": int(fa.sum()),
                    "change": int((fa ^ sa).sum()),
                    "change_frac": int((fa ^ sa).sum()) / max(int(fa.sum()), 1),
                }
            out["cases"].append(c)
            print(
                json.dumps(
                    {
                        "k": k,
                        "seed": s,
                        **{
                            n: round(c[n]["change_frac"], 3)
                            for n in ("N5", "W4", "method")
                        },
                    }
                ),
                flush=True,
            )
    a.out.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
