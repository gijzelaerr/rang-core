# SPDX-License-Identifier: GPL-3.0-or-later
"""Readout of CASA's tfcrop band template F (research/v8c-tfcrop-poly.md,
section 4, P0; every output is labelled probe, never a gate case).

A group is one average spectrum A shared by many planes. Every plane's rows
are mirrored pairs A(1 + v), A(1 - v) (real, positive values, so the time
mean and the median are A). v carries an alternating background +-e over
all channels, which sets the row sd (below 0.1: one D1 pass), and K test
cells per row whose magnitude V puts the cell near the row threshold for a
predicted misfit m0 = A/F - 1, on a ladder of offsets d. Under D1 a cell of
amplitude a in a row with sd s is flagged where |a/F - 1| > c s, so every
cell bounds F at its channel: flagged above A, F < a/(1 + c s); unflagged,
a/(1 + c s) <= F <= a/(1 - c s); flagged below A, F > a/(1 - c s). The row
sd depends on F at second order only; `invert` iterates.

Usage:
  tfcrop_readout.py design SPEC.json TEMPLATE_INFO.json OUT_DIR NAME
  tfcrop_readout.py invert BATCH_DIR NAME ARM CUTOFF [NCHAN_SEL] > F.json

SPEC.json: {"seed", "planes_per_group", "k_tests", "groups": [{"A": [...],
"m0": [...], "e", "range"}]}; written by the batch scripts.
"""

import json
import sys
from pathlib import Path

import numpy as np


def design(spec, info):
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    half = ntime // 2
    rng = np.random.default_rng(spec["seed"])
    cut = float(spec.get("cutoff", 3.0))
    gp = int(spec["planes_per_group"])
    kt = int(spec["k_tests"])
    data = np.zeros((nbl * ntime, nchan, 4), np.complex64)
    planes = []
    alt = (-1.0) ** np.arange(nchan)
    for gi, g in enumerate(spec["groups"]):
        A = np.asarray(g["A"], float)
        m0 = np.asarray(g.get("m0", np.zeros(nchan)), float)
        e, R = float(g["e"]), float(g["range"])
        # Test slots of the group: (plane, row, channel), spread so that
        # every channel is tested about equally often; offsets d on a
        # shuffled linear ladder in [-R, R] per channel.
        slots = gp * half * kt
        chans = np.resize(rng.permutation(nchan), slots)
        rng.shuffle(chans)
        d = np.empty(slots)
        aim = np.empty(slots)
        for f in range(nchan):
            idx = np.flatnonzero(chans == f)
            d[idx] = rng.permutation(np.linspace(-R, R, len(idx)))
            aim[idx] = rng.permutation(np.resize([1.0, -1.0], len(idx)))
        s = 0
        for p in range(gp):
            k = gi * gp + p
            b, c = divmod(k, 4)
            v = np.empty((half, nchan))
            for t in range(half):
                # one test per channel of a row (a repeated channel's
                # later slot is dropped)
                _, first = np.unique(chans[s : s + kt], return_index=True)
                sl = s + first
                ch, dd, aa = chans[sl], d[sl], aim[sl]
                s += kt
                row = e * alt * (1 if t % 2 == 0 else -1)
                kk = cut * e
                for _ in range(4):
                    mm = m0[ch] + dd
                    vp = (1 + kk) / (1 + mm) - 1  # + reading at m0 + d
                    vm = 1 - (1 - kk) / (1 + mm)  # - reading at m0 + d
                    row[ch] = np.where(aa > 0, vp, vm)
                    u = (1 + m0) * (1 + row) - 1
                    kk = cut * float(np.sqrt(np.mean(u * u)))
                v[t] = row
            v = np.clip(v, -0.9, 0.9)
            vv = np.concatenate([v, -v])
            data[b::nbl, :, c] = (A[None, :] * (1.0 + vv)).astype(np.complex64)
            planes.append([b, c, gi])
    return data, np.zeros(data.shape, bool), {"planes": planes, "ngroups": len(spec["groups"])}


def load_flags(path):
    z = np.load(path)
    s = tuple(int(v) for v in z["shape"])
    return np.unpackbits(z["flag"])[: int(np.prod(s))].astype(bool).reshape(s)


def group_planes(batch, name, arm, nsel=None):
    meta = json.loads((Path(batch) / f"{name}.json").read_text(encoding="utf-8"))
    z = np.load(Path(batch) / f"{name}.npz")
    data = z["data"]
    casa = load_flags(Path(batch) / "out" / f"{name}.{arm}.npz")
    nbl = meta["nbl"]
    groups = {}
    for b, c, gi in meta["planes"]:
        a = np.abs(data[b::nbl, :, c]).astype(np.float64)
        fl = casa[b::nbl, :, c]
        if nsel:
            a, fl = a[:, :nsel], fl[:, :nsel]
        groups.setdefault(gi, ([], []))
        groups[gi][0].append(a)
        groups[gi][1].append(fl)
    return {g: (np.array(a), np.array(f)) for g, (a, f) in groups.items()}


def row_sd(a, F, live=None):
    u = a / F[None, None, :] - 1.0
    if live is None:
        return np.sqrt(np.mean(u * u, axis=2, keepdims=True))
    n = np.maximum(live.sum(axis=2, keepdims=True), 1)
    return np.sqrt(np.where(live, u * u, 0.0).sum(axis=2, keepdims=True) / n)


def invert(a, fl, cut, F0=None, iters=6):
    """Per-channel bounds [lo, hi] on F from one group's planes a (P, T, n)
    and CASA's flags fl; returns (F, lo, hi, nbad) where nbad counts
    channels whose bounds cross."""
    A = a.mean(axis=(0, 1))
    F = A.copy() if F0 is None else np.asarray(F0, float).copy()
    for _ in range(iters):
        sd = row_sd(a, F)
        # rows with sd >= 0.1 take more than one D1 pass: left out
        one = np.broadcast_to(sd < 0.1, a.shape)
        k = cut * sd
        up = a / (1 + k)  # F < up  <=> a/F - 1 > k
        dn = a / (1 - k)  # F > dn  <=> a/F - 1 < -k
        above = a >= F[None, None, :]
        # lower bounds: unflagged -> F >= up; flagged below -> F > dn
        lo_c = np.where(~fl, up, np.where(~above, dn, -np.inf))
        hi_c = np.where(~fl, dn, np.where(above, up, np.inf))
        lo_c = np.where(one, lo_c, -np.inf)
        hi_c = np.where(one, hi_c, np.inf)
        lo = lo_c.max(axis=(0, 1))
        hi = hi_c.min(axis=(0, 1))
        Fn = np.where(np.isfinite(lo) & np.isfinite(hi), 0.5 * (lo + hi), F)
        if np.allclose(Fn, F, rtol=0, atol=1e-12 * np.abs(F).max()):
            F = Fn
            break
        F = Fn
    return F, lo, hi, int((lo > hi).sum())


def main(argv):
    cmd = argv[0]
    if cmd == "design":
        spec = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        info = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        out, name = Path(argv[3]), argv[4]
        data, flag, meta = design(spec, info)
        out.mkdir(parents=True, exist_ok=True)
        np.savez(out / f"{name}.npz", data=data, flag=flag)
        meta |= info
        (out / f"{name}.json").write_text(json.dumps(meta), encoding="utf-8")
    elif cmd == "invert":
        batch, name, arm, cut = argv[1], argv[2], argv[3], float(argv[4])
        nsel = int(argv[5]) if len(argv) > 5 else None
        res = {}
        for g, (a, fl) in sorted(group_planes(batch, name, arm, nsel).items()):
            F, lo, hi, bad = invert(a, fl, cut)
            A = a.mean(axis=(0, 1))
            res[g] = {"A": A.tolist(), "F": F.tolist(), "lo": lo.tolist(),
                      "hi": hi.tolist(), "crossed": bad}  # fmt: skip
        json.dump(res, sys.stdout)
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
