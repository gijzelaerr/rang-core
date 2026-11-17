"""Theoretic beam (GeMClean multiscale::theoretic_beam) under the WSClean 3.7 rule
(u on both axes) and the !1068 rule (u, v) on a Measurement Set's field 0, Stokes I
weights taken as nonzero where no polarisation is flagged and WEIGHT_SPECTRUM > 0.
All channels together (the single-channel path); joined-channel runs take each output
channel's own beam. Run under the main checkout's tools/heavy_lock.py (--slots 2 --mem 10);
the thirteen cases took 69 s. Output: probe.jsonl beside this file."""

import json
import math
import sys

import numpy as np
from rang import core_ms

C = 299_792_458.0


def probe(path, n, pixel_asec, block=20000):
    t = core_ms.open_table(path)
    spw = core_ms.open_table(path + "/SPECTRAL_WINDOW")
    freq = np.asarray(spw.getcol("CHAN_FREQ"))[0]
    nrow = t.nrows
    pixel = math.radians(pixel_asec / 3600.0)
    half = 0.5 * n
    lam = C / freq
    best = {"old": 0.0, "new": 0.0}
    cut_by_v = 0
    for r0 in range(0, nrow, block):
        k = min(block, nrow - r0)
        uvw = np.asarray(t.getcol("UVW", r0, k))
        field = np.asarray(t.getcol("FIELD_ID", r0, k))
        flag = np.asarray(t.getcol("FLAG", r0, k)).any(axis=-1)
        frow = np.asarray(t.getcol("FLAG_ROW", r0, k)).astype(bool)
        ok = ~flag & ~frow[:, None] & (field == 0)[:, None]
        try:
            ws = np.asarray(t.getcol("WEIGHT_SPECTRUM", r0, k)).min(axis=-1)
            ok &= ws > 0
        except (KeyError, ValueError, RuntimeError):
            pass
        u = uvw[:, 0:1] / lam
        v = uvw[:, 1:2] / lam
        length = np.linalg.norm(uvw, axis=1)[:, None] / lam
        x = u * pixel * n
        y = v * pixel * n
        inx = (np.floor(x) > -half) & (np.ceil(x) < half)
        iny = (np.floor(y) > -half) & (np.ceil(y) < half)
        cut_by_v += int((ok & inx & ~iny).sum())
        for key, m in (("old", ok & inx), ("new", ok & inx & iny)):
            if m.any():
                best[key] = max(best[key], float(length[m].max()))
    out = {
        "ms": path,
        "n": n,
        "pixel_asec": pixel_asec,
        "beam_old_rad": 1 / best["old"] if best["old"] else None,
        "beam_new_rad": 1 / best["new"] if best["new"] else None,
    }
    out["identical"] = out["beam_old_rad"] == out["beam_new_rad"]
    # Weighted samples the v test removes: 0 means every channel subset is unchanged too.
    out["samples_cut_by_v"] = cut_by_v
    return out


def main_all():
    B = "D:/rang/outputs/20261102-gemclean/bench/data"
    H = "D:/rang/outputs/20261103-gemclean-heldout"
    cases = [
        (f"{B}/s1.ms", 2048, 1.5),
        (f"{B}/s2.ms", 2048, 1.5),
        (f"{B}/s3.ms", 2048, 1.5),
        (f"{H}/sim/data/h1.ms", 2048, 1.5),
        (f"{H}/sim/data/h2.ms", 2048, 1.5),
        (f"{H}/sim/data/h3.ms", 4096, 1.5),
        (f"{H}/sim/data/h4.ms", 2048, 1.5),
        ("D:/rang/outputs/20261106-g3-spectral/data/D2.ms", 2048, 1.5),
        ("D:/rang/outputs/g5-20261107-03/data/m1.ms", 2048, 1.5),
        ("D:/rang/outputs/g9-20261107-01-probe/probe.ms", 512, 3.0),
        (f"{H}/real/cal.ms", 4096, 3.0),
        (f"{H}/real/cal2.ms", 4096, 3.0),
        (f"{H}/real/cal3.ms", 4096, 3.0),
    ]
    for c in cases:
        print(json.dumps(probe(*c)), flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 4:
        print(
            json.dumps(probe(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]))),
            flush=True,
        )
    else:
        main_all()
