"""Print DD9's records compactly for the note."""

import json
from pathlib import Path

R = Path("D:/rang/outputs/dd9-20261126")


def r3(x):
    return [round(v, 3) if isinstance(v, float) else v for v in x]


def part_a():
    for b in ("B-X", "O-X"):
        for v in ("default", "I1", "I2", "I3", "I4"):
            p = R / "solve" / f"{b}-{v}.json"
            if not p.exists():
                print(b, v, "missing")
                continue
            r = json.loads(p.read_text())
            for K in (500, 2000):
                x = r[f"cap{K}"]
                eh = x["ehat"][1:]
                print(b, v, K, "frac", r3(x["fraction"]), "e/eh conv",
                      r3([e / h for e, h in zip(x["e_d1_d3_converged"], eh)]),
                      "e/eh all", r3([e / h for e, h in zip(x["e_d1_d3"], eh)]),
                      "flagged", x["flagged"], "s", round(r["seconds"]))


def part_b():
    for base in ("O", "O-H"):
        p = R / "solve" / f"partb-{base}.json"
        if not p.exists():
            print(base, "missing")
            continue
        r = json.loads(p.read_text())
        for arm in ("b0", "bP", "bM", "bR", "bL"):
            for K in (500, 2000):
                x = r[arm][f"cap{K}"]
                print(base, arm, K, "frac", r3(x["fraction"]), "it", x["iterations"], "e", r3(x["e_d1_d3"]),
                      "e conv", r3(x["e_d1_d3_converged"]), "ehat", r3(x["ehat"]), "d3amp",
                      {k: round(v, 2) for k, v in x["d3_amp"].items()})
        if "rule" in r:
            print(json.dumps(r["rule"], indent=1))


if __name__ == "__main__":
    part_a()
    part_b()
