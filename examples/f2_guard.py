"""F2 guards G5 and G6 (research/f2-flagger.md, section 5) on f2sim-t1's variants.

Usage: python examples/f2_guard.py OUT.json LINE_OBS STEP_OBS --net LABEL=W.npz ...

Labels ending in `-target` run on target scans, others on calibrator scans.
G5 (targets, LINE_OBS): flagged fraction of the line's cells (clean of RFI,
outside the shared wrapper), against T's. G6 (STEP_OBS): antenna 0's clean
cells within +-2 dumps of the mid-scan step, against its other clean cells.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from rang import f2flag as ff
from rang import f2flag_sim as fs

sys.path.insert(0, str(Path(__file__).parent))
from f2_measure import load_scan


def frac(f, sel):
    n = int(sel.sum())
    return [float(f[sel].mean()) if n else None, n]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("line", type=Path)
    parser.add_argument("step", type=Path)
    parser.add_argument("--net", action="append", default=[])
    args = parser.parse_args()
    out = args.out
    if out.startswith("RUN/"):
        out = Path(os.environ["RUN_DIR"]) / out[4:]
    nets = dict(item.split("=", 1) for item in args.net)
    result = {"G5": {}, "G6": {}}
    line = json.loads((args.line / "observation.json").read_text())["line"]
    for klass in ("calibrator", "target"):
        labels = [k for k in nets if k.endswith("-target") == (klass == "target")]
        weights = {k: ff.load_net(nets[k]) for k in labels}
        steps_t = ff.strategy(ff.STRATEGIES[klass])
        shared_steps = ff.shared_strategy(klass)
        cases = [("G6", args.step)] + ([("G5", args.line)] if klass == "target" else [])
        for guard, obs in cases:
            acc = {}
            for s in fs.scans_of(obs, klass):
                scan = load_scan(s)
                shared, _ = ff.run_strategy(scan, shared_steps)
                flags = {"T": ff.run_strategy(scan, steps_t)[0]}
                for k, w in weights.items():
                    flags[k] = ff.network_flags(scan, shared, *w)[0]
                clean = ~shared & (scan["amp"] == 0)
                if guard == "G5":
                    sel = np.zeros_like(clean)
                    sel[:, line["chans"]] = True
                    sets = {"line": clean & sel, "background": clean & ~sel}
                else:
                    t = scan["planes"].t
                    mid = scan["planes"].nt // 2
                    ant0 = (scan["antenna1"] == 0) | (scan["antenna2"] == 0)
                    near = (np.abs(t - mid) <= 2) & ant0
                    sets = {
                        "near_step": clean & near[:, None],
                        "background": clean & (ant0 & ~near)[:, None],
                    }
                for k, f in flags.items():
                    for name, sel in sets.items():
                        a = acc.setdefault(k, {}).setdefault(name, [0, 0])
                        a[0] += int((f & sel).sum())
                        a[1] += int(sel.sum())
            res = {
                k: {n: (v[0] / v[1] if v[1] else None) for n, v in d.items()}
                for k, d in acc.items()
            }
            for k in labels:
                r = res[k]
                if guard == "G5":
                    r["pass"] = r["line"] <= res["T"]["line"] + 0.05
                else:
                    r["pass"] = r["near_step"] <= r["background"] + 0.05
            result[guard][klass] = res
            print(guard, klass, json.dumps(res), flush=True)
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
