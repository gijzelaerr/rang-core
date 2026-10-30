"""Summarise the scan 9 solves: iterations, converged %, gain-product distance to the 500-iteration reference.

usage: python analyse.py <solve dir> <rang dir>
Products P_pq = G_p G_q^H (gauge invariant, so referenced and unreferenced runs compare).
"""

import json
import sys

import numpy as np
from daskms.experimental.zarr import xds_from_zarr

sdir, rdir = sys.argv[1], sys.argv[2]


def qc(name):
    ds = xds_from_zarr(f"{sdir}/out/{name}/gains.qc::G")[0]
    g = ds.gains.values[..., 0, :].reshape(ds.gains.shape[:3] + (2, 2))
    f = ds.gain_flags.values[..., 0] != 0
    return (
        g,
        f,
        int(ds.conv_iter.values.ravel()[0]),
        float(ds.conv_perc.values.ravel()[0]),
    )


def rang(name):
    z = np.load(f"{rdir}/{name}.npz")
    return z["gains"], z["flags"] != 0


def products(g):
    p, q = np.triu_indices(g.shape[2], 1)
    return g[:, :, p] @ np.conj(np.swapaxes(g[:, :, q], -1, -2))


def dist(a, b):
    (ga, fa), (gb, fb) = a[:2], b[:2]
    ok = (
        ~(fa.any(-1) | fb.any(-1))
        & np.isfinite(ga).all((-3, -2, -1))
        & np.isfinite(gb).all((-3, -2, -1))
    )
    pa, pb = products(ga)[ok], products(gb)[ok]
    rel = np.linalg.norm(pa - pb, axis=(-2, -1)) / np.linalg.norm(pb, axis=(-2, -1))
    if rel.size == 0:
        return {
            "intervals": 0,
            "fa": int(fa.any(-1).sum()),
            "fb": int(fb.any(-1).sum()),
            "shapes": [list(ga.shape), list(gb.shape)],
        }
    return {
        "intervals": int(ok.sum()),
        "median": float(np.median(rel)),
        "max": float(rel.max()),
    }


rows = []
for w in ("unit", "native", "x4"):
    ref = qc(f"{w}-ref")
    rref = rang(f"{w}-transposed-ref")
    rows.append(
        {
            "arm": f"{w}-ref",
            "iters": ref[2],
            "conv_perc": ref[3],
            "vs_rang_transposed_ref": dist(ref, rref),
        }
    )
    for v in ("027", "pre", "post", "postref"):
        try:
            r = qc(f"{w}-{v}")
        except Exception as e:  # noqa
            rows.append({"arm": f"{w}-{v}", "error": repr(e)})
            continue
        rows.append(
            {
                "arm": f"{w}-{v}",
                "iters": r[2],
                "conv_perc": r[3],
                "vs_ref": dist(r, ref),
            }
        )
    for q in ("archived", "transposed"):
        r = rang(f"{w}-{q}")
        rows.append(
            {
                "arm": f"{w}-rang-{q}",
                "vs_ref": dist(r, ref),
                "vs_qc027": dist(r, qc(f"{w}-027")),
                "vs_rang_ref_same_opt": dist(r, rang(f"{w}-{q}-ref")),
            }
        )
    rows.append(
        {
            "arm": f"{w}-rang-archived-ref",
            "vs_qc_ref": dist(rang(f"{w}-archived-ref"), ref),
        }
    )
for r in rows:
    print(json.dumps(r))


def maxabs(a, b):
    ok = ~(a[1].any(-1) | b[1].any(-1)) if a[1].ndim == 3 else ~(a[1] | b[1])
    d = np.abs(a[0] - b[0])[ok]
    d = d[np.isfinite(d)]
    return {
        "max_abs_gain_diff": float(d.max()) if d.size else None,
        "bit_identical": bool(np.array_equal(a[0][ok], b[0][ok])),
        "intervals": int(ok.sum()),
    }


def qcf(n):
    g, f, *_ = qc(n)
    return g, f.any(-1) if f.ndim == 4 else f


def rf(n):
    g, f = rang(n)
    return g, f


print("--- exact differences")
for w in ("unit", "native", "x4"):
    for a, b in (("027", "pre"), ("027", "post"), ("pre", "post")):
        print(w, a, b, json.dumps(maxabs(qcf(f"{w}-{a}"), qcf(f"{w}-{b}"))))
    print(
        w,
        "post vs postref products",
        json.dumps(dist(qc(f"{w}-post"), qc(f"{w}-postref"))),
    )
    print(
        w,
        "rang archived vs qc027",
        json.dumps(maxabs(rf(f"{w}-archived"), qcf(f"{w}-027"))),
    )
    print(
        w,
        "rang transposed vs qc post",
        json.dumps(maxabs(rf(f"{w}-transposed"), qcf(f"{w}-post"))),
    )
    print(
        w,
        "rang archived vs transposed",
        json.dumps(maxabs(rf(f"{w}-archived"), rf(f"{w}-transposed"))),
    )
print(
    "unit vs native rang archived",
    json.dumps(maxabs(rf("unit-archived"), rf("native-archived"))),
)
z = np.load(f"{rdir}/native.npz")
w, fl = z["weights"], z["flag"]
ok = ~(fl[..., 1] | fl[..., 2]) & (z["a1"] != z["a2"])[:, None] & (w[..., 1] > 0)
ratio = w[..., 2][ok] / w[..., 1][ok]
print(
    "native w_YX/w_XY over unflagged cross-correlation samples: percentiles 1,5,50,95,99 =",
    np.percentile(ratio, [1, 5, 50, 95, 99]).round(4).tolist(),
    "n",
    ratio.size,
)
