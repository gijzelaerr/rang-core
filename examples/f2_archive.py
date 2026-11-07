"""F2: the compact archive research/results/f2-flagger.json from the run
directories (research/f2-flagger.md, section 9).

Usage: python examples/f2_archive.py OUT.json STAGE2 STAGE3 AMEND3 STAGE5 REAL COST
"""

import json
import sys
from pathlib import Path


def load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def slim(measure):
    """Pooled Q1, Q2 (with n), by morphology, Q3 and the calls."""
    if measure is None:
        return None
    out = {"q3": measure["q3"], "calls": measure["calls"], "arms": {}}
    for arm, p in measure["pooled"].items():
        out["arms"][arm] = {
            k: p[k] for k in ("q1", "q1_n", "q2", "q2_n", "q1_ge3", "scored")
        }
        out["arms"][arm]["by_morphology"] = p.get("by_morphology")
        out["arms"][arm]["by_decade"] = p.get("by_decade")
    return out


def main():
    out, stage2, stage3, amend3, stage5, real, cost = sys.argv[1:]
    s2, s3, a3, s5, rl, c = map(Path, (stage2, stage3, amend3, stage5, real, cost))
    result = {
        "task": "F2, research/f2-flagger.md",
        "runs": {
            "stage2": str(s2),
            "stage3": str(s3),
            "amendment3": str(a3),
            "stage5": str(s5),
            "real": str(rl),
            "cost": str(c),
        },
        "params": load(s2 / "params.json"),
        "stage2_validation": {
            k: slim(load(s2 / f"{k}.json")) for k in ("calibrator", "target")
        },
        "stage3": {
            "parity_U": load(s3 / "parity-U.json"),
            "c1_U_4t": load(s3 / "c1-U-4t.json"),
        },
        "amendment3": {
            "picks": load(a3 / "picks-tau.json"),
            "curves": {
                k: load(a3 / f"threshold-{k}.json") for k in ("calibrator", "target")
            },
        },
        "stage5": {
            "parity": {
                k: load(s5 / f"parity-{k}.json") for k in ("calibrator", "target")
            },
            "validation": {
                k: slim(load(s5 / f"val-{k}.json")) for k in ("calibrator", "target")
            },
            "test1": {
                k: slim(load(s5 / f"test1-{k}.json")) for k in ("calibrator", "target")
            },
            "test2": {
                k: slim(load(s5 / f"test2-{k}.json")) for k in ("calibrator", "target")
            },
            "test": {
                k: slim(load(s5 / f"test-{k}.json")) for k in ("calibrator", "target")
            },
            "guards": load(s5 / "guards.json"),
        },
        "real": {k: load(rl / f"{k}.json") for k in ("luno1934", "luno1830", "eso137")},
        "cost": {p.stem: load(p) for p in sorted(c.glob("c*.json"))},
    }
    Path(out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
