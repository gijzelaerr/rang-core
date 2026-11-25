# SPDX-License-Identifier: MIT
"""Attributes of rang-p1 against oracle, key by key (xradio venv): which differ."""
import json, sys
from xradio.measurement_set import open_processing_set
R = sys.argv[1]
out = {}
for case in ["c1","c2","c3","c4","c5","c6x","c8","c10","c11","c11c"]:
    for arm in ("xradio", "xms-auto"):
        a = open_processing_set(f"{R}/ps/{arm}/{case}-rang-p1.ps.zarr")
        b = open_processing_set(f"{R}/ps/{arm}/{case}-oracle.ps.zarr")
        diffs = set()
        for node in a.subtree:
            x, y = dict(node.attrs), dict(b[node.path].attrs)
            def walk(x, y, path=""):
                if isinstance(x, dict) and isinstance(y, dict):
                    for k in sorted(set(x) | set(y)):
                        walk(x.get(k), y.get(k), f"{path}.{k}")
                elif str(x) != str(y):
                    diffs.add(path)
            walk(x, y)
        out[f"{case}/{arm}"] = sorted(diffs)
print(json.dumps(out))
json.dump(out, open(f"{R}/attrs-rang-vs-oracle.json", "w"), indent=1)
