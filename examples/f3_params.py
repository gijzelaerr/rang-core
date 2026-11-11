"""F3: count tunable parameters (P, research/f3-flagger.md section 6) with
F2's counter (`examples/f2_params.py`), W3 against the full YAML.

Usage: python examples/f3_params.py OUT.json
"""

import importlib.util
import json
import sys
from pathlib import Path

from rang import f2flag as ff
from rang import f3flag as f3

spec = importlib.util.spec_from_file_location(
    "f2_params", Path(__file__).resolve().parent / "f2_params.py"
)
f2p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f2p)


def main():
    out = {}
    for klass in ("calibrator", "target"):
        out[f"{klass}_T"] = f2p.count(ff.strategy(ff.STRATEGIES[klass]))
        w = f2p.count(f3.w3_strategy(klass))
        w["t1_kinds_with_weights_and_tau"] = w["distinct_kinds"] + 2
        out[f"{klass}_W3"] = w
    out["t2_retraining"] = [
        "label threshold A >= 3 and ignore band",
        "consensus strength bar max(u) >= 3 (Amendment 1)",
        "injection mix (morphologies, counts, strengths 3-300, decay, coupling, fringe)",
        "augmentation occupancy and shapes",
        "realisations per scan",
        "baselines per shard (256)",
        "Adam rate",
        "steps",
        "batch",
        "window width",
        "seed selection rule",
        "tau grid and rule",
    ]
    out["t3_architecture"] = [
        "inputs (15 planes; running median 33; MIN_AGG 3; noise MIN_PAIRS 16)",
        "depth 5",
        "filters 8",
        "kernel 3x3",
        "dilations 1-16",
    ]
    text = json.dumps(out, indent=1)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
