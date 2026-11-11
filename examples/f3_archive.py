"""F3: the compact result archive research/results/f3-flagger.json from the run
outputs (research/f3-flagger.md).

Usage: python examples/f3_archive.py OUT.json
"""

import hashlib
import json
import sys
from pathlib import Path

D = Path("D:/rang/outputs")


def load(rel):
    return json.loads((D / rel).read_text(encoding="utf-8"))


def sha(p):
    return hashlib.sha256((D / p).read_bytes()).hexdigest()


def main():
    cal = "f3-20261110-17-train-calibrator/seed-3/weights.npz"
    tgt = "f3-20261110-15-train-target/seed-1/weights.npz"
    out = {
        "note": "research/f3-flagger.md",
        "outcome": {
            "calibrator": "F",
            "target": "stopped at the label audit (post hoc arm F)",
        },
        "weights": {
            "calibrator": {"path": cal, "sha256": sha(cal), "tau": -2.5, "seed": 3},
            "target": {"path": tgt, "sha256": sha(tgt), "tau": -4.0, "seed": 1},
        },
        "fetch": {
            k: v
            for k, v in load("f3-20261110-01-fetch/result.json").items()
            if k != "objects"
        },
        "subset": load("f3-20261110-09-subset/subset.json"),
        "stop_z2": {
            "calibrator": load("f3-20261110-10-stage1-cal/summary-z2.json")["gates"],
            "target": load("f3-20261110-05-stage1-target/summary-z2.json")["gates"],
        },
        "parity": {
            "u3_eso10": load("f3-20261110-06-stage2/parity-u3-eso10.json"),
            "u3_fsim": load("f3-20261110-06-stage2/parity-u3-fsim.json"),
            "calibrator_trained": load("f3-20261110-19-parity-cal/parity.json"),
        },
        "c1_u3": {
            k: v
            for k, v in load("f3-20261110-06-stage2-c1u3/c1-u3-4t.json").items()
            if k != "records"
        },
        "audit": {
            "target_frozen": load(
                "f3-20261110-08-shards-target/target/train/audit.json"
            ),
            "target_diagnosis": load("f3-20261110-12-audit-diag/diag.json"),
        },
        "tau": {
            k: {
                x: load(f"f3-20261110-19-tau-{k}/tau.json")[x]
                for x in ("grid", "recall", "added", "T_added", "tau", "rule")
            }
            for k in ("cal", "target")
        },
        "heldout": {
            "calibrator": load(
                "f3-20261110-20-heldout-cal-luno-MAIN_1/summary-cal.json"
            ),
            "target_posthoc": load(
                "f3-20261110-21-heldout-target-eso-0/summary-target.json"
            ),
            "calibrator_injection_widths_posthoc": load(
                "f3-20261110-20-heldout-cal-luno-MAIN_1/posthoc-injection-widths.json"
            ),
        },
        "cost": {},
        "params": load("f3-20261110-18-params/params.json"),
    }
    # S3 has no drifting cells in the calibrator scans (research/f3-flagger.md).
    out["heldout"]["calibrator"]["gates"]["S3"] = "undecidable (0 drifting cells)"
    for c in ("cal", "tgt"):
        for t in ("4", "1"):
            r = load(f"f3-20261110-22-cost-{c}-{t}/c1.json")
            out["cost"][f"{c}-{t}"] = {
                k: r[k]
                for k in ("set", "threads", "median_wall", "c1", "all_clean", "records")
            }
        for a in ("T", "N3"):
            out["cost"][f"{c}-rss-{a}"] = load(
                f"f3-20261110-22-cost-{c}-rss-{a}/c2.json"
            )
    text = json.dumps(out, indent=1)
    Path(sys.argv[1]).write_text(text + "\n", encoding="utf-8")
    print(len(text))


if __name__ == "__main__":
    main()
