# SPDX-License-Identifier: MIT
"""Where the present MSv4 read path spends its time (a probe for a Rust
reader, research/msv4-weights.md section 8). Reported only, no rule.

    read_probe.py ROOT OUT.json

For each store copy under ROOT/inputs/ps: the seconds to open the processing
set, to build every partition, to read `Partition.rows()` once, and the
share of that read spent decoding the chunk files (zarr's own array read of
each variable `rows()` touches, without xarray), best of 3.
"""

import json
import sys
import time
from pathlib import Path


def _best(fn, n=3):
    best = None
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return best


def probe(store):
    import zarr
    from rang import msv4

    out = {}
    out["open_s"] = _best(lambda: msv4.open_processing_set(store))
    ps = msv4.open_processing_set(store)
    out["partitions_s"] = _best(lambda: ps.partitions())
    parts = ps.partitions()
    out["rows_s"] = _best(lambda: [p.rows() for p in parts])
    group = zarr.open_group(str(store), mode="r")
    names = []
    for p in parts:
        for var in (
            p.variables["correlated_data"],
            p.variables["flag"],
            p.variables["uvw"],
            p.weight_variable,
        ):
            if var:
                names.append(f"{p.name}/{var}")
    nbytes = sum(group[n].nbytes for n in names)
    out["decode_s"] = _best(lambda: [group[n][...] for n in names])
    out["bytes"] = int(nbytes)
    out["decode_share"] = out["decode_s"] / out["rows_s"] if out["rows_s"] else None
    return out


def main(argv):
    root, out = Path(argv[0]), Path(argv[1])
    res = {}
    for arm_dir in sorted((root / "inputs" / "ps").iterdir()):
        for store in sorted(arm_dir.iterdir()):
            key = f"{arm_dir.name}/{store.name}"
            res[key] = probe(store)
            print(key, {k: round(v, 4) for k, v in res[key].items() if v is not None})
    out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
