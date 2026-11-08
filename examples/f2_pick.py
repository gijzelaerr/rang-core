"""F2: the frozen weights file per class, the median F-SIM seed by validation
loss (research/f2-flagger.md, section 2), and the control arms' files.

Usage: python examples/f2_pick.py OUT.json TRAIN_DIR [TRAIN_DIR ...]
"""

import hashlib
import json
import sys
from pathlib import Path


def main():
    out, *dirs = sys.argv[1:]
    runs = []
    for d in dirs:
        for log in Path(d).glob("*-*-*/log.json"):
            r = json.loads(log.read_text())
            runs.append({**{k: r[k] for k in ("class", "labels", "seed")},
                         "validation_loss": r["validation_loss"],
                         "path": str(log.parent / "weights.npz")})  # fmt: skip
    picks = {}
    for klass in ("calibrator", "target"):
        sim = sorted(
            (r for r in runs if r["class"] == klass and r["labels"] == "sim"),
            key=lambda r: r["validation_loss"],
        )
        if not sim:
            continue
        median = sim[len(sim) // 2]
        picks[f"F-SIM-{klass}"] = median
        for labels, name in (("res", "F-RES"), ("imi", "F-IMI")):
            for r in runs:
                if r["class"] == klass and r["labels"] == labels:
                    picks[f"{name}-{klass}"] = r
        picks[f"seeds-{klass}"] = [[r["seed"], r["validation_loss"]] for r in sim]
    for v in picks.values():
        if isinstance(v, dict):
            v["sha256"] = hashlib.sha256(Path(v["path"]).read_bytes()).hexdigest()
    Path(out).write_text(json.dumps(picks, indent=1), encoding="utf-8")
    print(json.dumps(picks, indent=1))


if __name__ == "__main__":
    main()
