"""Exact pixel comparison of the native pass: repeats, and -j1 against -j16.

Usage: native_repeats.py NATIVE_DIR. Writes NATIVE_DIR/scores/repeats.json.
"""

import json
import sys
from pathlib import Path

import numpy as np


def read(path):
    raw = path.read_bytes()
    pos = 0
    bitpix = None
    while True:
        block = raw[pos : pos + 2880]
        pos += 2880
        cards = [block[i : i + 80] for i in range(0, 2880, 80)]
        for c in cards:
            if c.startswith(b"BITPIX"):
                bitpix = int(c[10:30])
        if any(c.startswith(b"END ") or c.rstrip() == b"END" for c in cards):
            break
    dtype = {-32: ">f4", -64: ">f8"}[bitpix]
    return np.frombuffer(raw, dtype=dtype, offset=pos)


def diff(a, b):
    a, b = read(a), read(b)
    n = min(a.size, b.size)
    a, b = a[:n], b[:n]
    d = a != b
    return int(d.sum()), float(
        np.abs(a[d].astype(float) - b[d].astype(float)).max()
    ) if d.any() else 0.0


root = Path(sys.argv[1])
out = {}
for im in ("wsclean", "gemclean"):
    for f in sorted((root / "rep1" / im).glob("*-model.fits")):
        name = f.name[: -len("-model.fits")]
        for kind in ("model", "residual"):
            first = root / "rep1" / im / f"{name}-{kind}.fits"
            for rep in (2, 3):
                out[f"{im}/{name}/{kind}/rep{rep}"] = diff(
                    first, root / f"rep{rep}" / im / first.name
                )
            if name.endswith("-j16"):
                other = root / "rep1" / im / f"{name[:-3]}j1-{kind}.fits"
                if other.exists():
                    out[f"{im}/{name}/{kind}/j1"] = diff(first, other)
(root / "scores" / "repeats.json").write_text(json.dumps(out, indent=0) + "\n")
same = sum(1 for v in out.values() if v[0] == 0)
print(f"{same} of {len(out)} comparisons identical")
for k, v in out.items():
    if v[0]:
        print(k, v)
