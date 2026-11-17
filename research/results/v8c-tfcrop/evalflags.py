# evalflags.py: score template variants by wrong cells on readout planes (CASA flags)
import json, sys, itertools
import numpy as np
sys.path.insert(0, "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly/tools/oracles/casa")
import tfcrop_readout as ro, tfcrop_template as tt
B = "D:/rang/outputs/v8c-tfcrop-20261116/probes"
ARMS = {"p1": ("poly", 1), "p2": ("poly", 2), "p3": ("poly", 3), "p7": ("poly", 7), "line": ("line", 1), "M8": ("poly", 1), "M32": ("poly", 1)}
def load(sets):
    items = []
    for b, design, arm in sets:
        spec = json.load(open(f"{B}/{b}/spec-{design[3:]}.json")) if design.startswith("RO-") else None
        for gi, (a, fl) in sorted(ro.group_planes(f"{B}/{b}", design, arm).items()):
            items.append((f"{b}.{arm}.{spec['groups'][gi]['name']}", ARMS[arm], a, fl))
    return items
sys.path.insert(0, "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly/python")
from rang import tfcrop as _tf
def wrong(a, fl, F):
    u = (a / F[None, None] - 1).reshape(-1, a.shape[2])
    got = _tf.row_flags(u, np.ones(u.shape, bool), 3.0).reshape(a.shape)
    return int((got != fl).sum())
def score(items, opts):
    per = {}
    for name, (kind, mp), a, fl in items:
        A = a.mean(axis=(0, 1))
        per[name] = wrong(a, fl, tt.template(A, np.ones(len(A), bool), kind, mp, **opts))
    return sum(per.values()), per
