"""seeds.py COMMIT BINARY_SHA256: the held-out sky H's seeds (research/g4-masks.md, section 3).

The first 8 and the next 8 hex digits of sha256("<commit> <binary sha256> G4H") as integers,
moving on by 8 digits on a collision with rang.simtruth.SEEDS or the simulator's seed tables.
"""

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def taken():
    used = set()
    for f in (
        ROOT / "python/rang/simtruth.py",
        ROOT / "examples/gemclean_bench_simulate.py",
    ):
        used |= {
            int(x) for x in re.findall(r"\b(\d{6,})\b", f.read_text(encoding="utf-8"))
        }
    return used


def main():
    commit, binary = sys.argv[1:3]
    h = hashlib.sha256(f"{commit} {binary} G4H".encode()).hexdigest()
    used = taken()
    seeds, i = [], 0
    while len(seeds) < 2:
        v = int(h[i : i + 8], 16)
        i += 8
        if v not in used:
            seeds.append(v)
    print(f"sky {seeds[0]} noise {seeds[1]} (digest {h})")


if __name__ == "__main__":
    main()
