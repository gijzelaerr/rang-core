# SPDX-License-Identifier: MIT
"""Gate E of research/selfcal-mem-34.md: two `rang-core selfcal` run directories compared
file by file (SHA-256 of every file under the run, by relative path). Files that differ are
listed; for `.npz` files the arrays are compared with `np.array_equal` as well, and for JSON
files the keys whose values differ are listed (wall times, paths and memory figures are
expected there).

    compare_runs.py RUN_A RUN_B OUT.json
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def files(root):
    return {
        str(p.relative_to(root)).replace("\\", "/"): p
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "lock"
    }


def json_diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += json_diff(a.get(k), b.get(k), f"{path}/{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += json_diff(x, y, f"{path}[{i}]")
        return out
    return [] if a == b else [path]


def main():
    ra, rb, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    fa, fb = files(ra), files(rb)
    result = {
        "a": str(ra),
        "b": str(rb),
        "only_a": sorted(set(fa) - set(fb)),
        "only_b": sorted(set(fb) - set(fa)),
        "identical": [],
        "differ": {},
    }
    for k in sorted(set(fa) & set(fb)):
        if sha(fa[k]) == sha(fb[k]):
            result["identical"].append(k)
            continue
        note = {}
        if k.endswith(".npz"):
            za, zb = np.load(fa[k]), np.load(fb[k])
            note["arrays_equal"] = sorted(za.files) == sorted(zb.files) and all(
                np.array_equal(za[n], zb[n], equal_nan=True) for n in za.files
            )
        elif k.endswith(".json"):
            try:
                da = json.loads(fa[k].read_text(encoding="utf-8"))
                db = json.loads(fb[k].read_text(encoding="utf-8"))
                note["keys"] = json_diff(da, db)
            except ValueError:
                note["keys"] = None
        result["differ"][k] = note
    result["counts"] = {
        "identical": len(result["identical"]),
        "differ": len(result["differ"]),
        "fits_identical": sum(k.endswith(".fits") for k in result["identical"]),
        "fits_differ": sum(k.endswith(".fits") for k in result["differ"]),
    }
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result["counts"]))
    for k, v in result["differ"].items():
        print("differ", k, json.dumps(v)[:300])


if __name__ == "__main__":
    main()
