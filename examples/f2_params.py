"""F2: count tunable parameters (P, research/f2-flagger.md section 5), as F1's
probe P1 (`outputs/f1-20261102-00-probes/count.py`), with `core_flag.parse_strategy`.

Usage: python examples/f2_params.py OUT.json
"""

import json
import sys

from rang import f2flag as ff


def count(steps):
    keys = scalars = 0
    kinds, triples = {}, set()
    for s in steps:
        for k, v in (s.get("kwargs") or {}).items():
            keys += 1
            vv = v if isinstance(v, list) else [v]
            scalars += len(vv)
            kinds.setdefault(f"{s['task']}.{k}", set()).add(json.dumps(v))
            triples.add((s["task"], k, json.dumps(v)))
    return {
        "steps": len(steps),
        "tasks": [s["task"] for s in steps],
        "kwarg_keys": keys,
        "scalar_values": scalars,
        "distinct_kinds": len(kinds),
        "kinds": sorted(kinds),
        "distinct_task_key_value": len(triples),
    }


def main():
    out = {}
    for label, name in (
        ("calibrator_firstpass", ff.STRATEGIES["calibrator"]),
        ("target_firstpass", ff.STRATEGIES["target"]),
        ("calibrator_mild", ff.MILD),
    ):
        out[label] = count(ff.strategy(name))
    for klass in ("calibrator", "target"):
        w = count(ff.shared_strategy(klass))
        # The network arm's T1: the wrapper's kinds plus the weights file.
        w["t1_kinds_with_weights_file"] = w["distinct_kinds"] + 1
        out[f"{klass}_network_wrapper"] = w
    out["t2_retraining"] = [
        "label threshold A >= 3",
        "ignore band 0 < A < 3",
        "augmentation occupancy and shapes",
        "Adam rate",
        "steps",
        "batch",
        "window width",
        "training seed selection rule",
    ]
    out["t3_architecture"] = [
        "inputs (6 planes, profile window 33)",
        "depth 5",
        "filters 8",
        "kernel 3x3",
        "dilations 1-16",
    ]
    text = json.dumps(out, indent=1)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
