"""E2-N's reported-only readings (e2n-native.md section 6, "native size of
the terms"; no tolerance): the size of K, KCROSS and Xf in rang's and CASA's
tables, and which antennas each arm's K leaves flagged. Committed before it
read an E2-N table; run once on the dry run's tables first.

    python e2n_native_size.py RANG_CAL_DIR CASA_TABLE_DIR OUT.json

K: |delay| in ns over unflagged antenna-polarisation entries. KCROSS: the
cross-hand delay in ns (pol 0). Xf: the cross-hand phase in degrees over
unflagged channels (pol 0), its circular mean and the spread about it.
"""

import json
import sys
from pathlib import Path

import numpy as np
from rang import core_ms


def table(d, name):
    with core_ms.open_table(Path(d) / name) as t:
        cols = t.colnames()
        p = np.asarray(t.getcol("FPARAM" if "FPARAM" in cols else "CPARAM"))
        f = np.asarray(t.getcol("FLAG"), bool)
        a = np.asarray(t.getcol("ANTENNA1"))
    return p, f, a


def stats(x):
    x = np.asarray(x, float)
    if x.size == 0:
        return {"n": 0}
    return {"n": int(x.size), "median": float(np.median(x)),
            "p95": float(np.percentile(x, 95)), "max": float(np.max(x))}  # fmt: skip


def arm(d):
    out = {}
    p, f, a = table(d, "K")
    out["K_abs_ns"] = stats(np.abs(p[~f]))
    allf = f.reshape(len(a), -1).all(1)
    out["K_flagged_antennas"] = sorted({int(x) for x in a[allf]})
    p, f, a = table(d, "Kcross")
    v = p[..., 0].real[~f[..., 0]]
    out["Kcross_ns"] = stats(v)
    out["Kcross_abs_ns"] = stats(np.abs(v))
    p, f, a = table(d, "Xf")
    z = p[..., 0][~f[..., 0]]
    z = z[np.abs(z) > 0]
    if z.size:
        u = z / np.abs(z)
        mean = np.angle(np.mean(u))
        dev = np.degrees(np.abs(np.angle(u * np.exp(-1j * mean))))
        out["Xf"] = {"n": int(z.size), "circular_mean_deg": float(np.degrees(mean)),
                     "coherence": float(np.abs(np.mean(u))),
                     "abs_dev_from_mean_deg": stats(dev)}  # fmt: skip
    else:
        out["Xf"] = {"n": 0}
    return out


def main(rang_dir, casa_dir, out_json):
    rec = {"label": "reported, not gated (e2n-native.md section 6)",
           "rang": arm(rang_dir), "casa": arm(casa_dir),
           "rang_dir": str(rang_dir), "casa_dir": str(casa_dir)}  # fmt: skip
    Path(out_json).write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(rec, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
