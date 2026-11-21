"""Cross-host parity (glacier docker WSClean 3.7 against nash native 3.7).

Runs ladder seed 5 (all arms) and grid-PSF seeds 0, 1 on this host and writes
OUT/parity-<host>.npz (models, G) and .json (scores). `compare A B` prints the
differences. Usage: python parity.py run DATA OUT HOST | compare A.npz B.npz
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "examples"))
import dl4b_step0 as S

if sys.argv[1] == "run":
    data, out, host = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
    out.mkdir(parents=True, exist_ok=True)
    z = np.load(data / "shard-000.npz")
    bm = S.beams(data)
    recs, models = S.ladder_seed(5, z, 5, bm, out)
    arr = {
        f"{k}_{p}": v[i]
        for k, v in models.items()
        for i, p in enumerate(("idx", "val"))
    }
    for s in (0, 1):
        G, rec = S.psfg_seed(s, z["dirty"][3 * s])
        arr[f"G{s}"] = G
        recs.append(rec)
    np.savez(out / f"parity-{host}.npz", **arr)
    (out / f"parity-{host}.json").write_text(json.dumps(recs, indent=1))
else:
    a, b = np.load(sys.argv[2]), np.load(sys.argv[3])
    res = {}
    for k in sorted(a.files):
        if k.endswith("_idx"):
            continue
        if k.startswith("G"):
            res[k] = float(np.abs(a[k] - b[k]).max())
            continue
        base = k[:-4]
        ia, ib = a[base + "_idx"], b[base + "_idx"]
        ma, mb = np.zeros(65536), np.zeros(65536)
        ma[ia], mb[ib] = a[k], b[k]
        res[base] = {
            "same_pixels": bool(np.array_equal(ia, ib)),
            "max_abs": float(np.abs(ma - mb).max()),
            "rel_flux": float(abs(ma.sum() - mb.sum()) / max(abs(mb.sum()), 1e-30)),
        }
    print(json.dumps(res, indent=1))
