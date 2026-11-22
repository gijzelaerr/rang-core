"""apply-calwt (#48), research/apply-calwt.md sections 4-5 (S): A1 small with
known gains and bandpass.

    python calwt_a1.py flags A1_DIR             # FLAG := the truth RFI mask ('any'), every row
    python calwt_a1.py score A1_DIR OUT.json    # rang's calwt weights against truth

The flags come from the simulation's own RFI mask, so the calibration sees
no RFI and the test is about the weights only (a deviation from E1, which
ran a flagger; stated in the note's result). Score, on the target
(SIM-TARGET, field 3), XX and YY, unflagged cells: the true corrected weight
is |g_p g_q|^2 / SIGMA^2 with g = raw_gain(time) * raw_bandpass(channel) of
truth.npz for each hand (K, Kcross, Xf and Df change no amplitude; the
target's scalar S is not corrected by 1GC and is left out, as in the data).
Reported: the ratio rang / truth, median and p95 of |ratio - 1|.
"""

import json
import sys
from pathlib import Path

import numpy as np

from rang import core_ms, core_writeback

TARGET_FIELD = 3


def flags(a1):
    a1 = Path(a1)
    ms = a1 / "a1-small.ms"
    m = np.load(a1 / "a1-small.rfi_mask.npz")
    nchan = int(m["nchan"])
    bits = np.unpackbits(m["any"], axis=1)[:, :nchan].astype(bool)
    with core_writeback.WriteBack(ms, stage="calwt-a1-flags") as w:
        for start, nrow in w.chunks(None):
            f = w.read("FLAG", start, nrow)
            f[:] = bits[start : start + nrow, :, None]
            w.write_flags(start, f)
    print(json.dumps({"rows": int(bits.shape[0]), "flagged_fraction": float(bits.mean())}))


def score(a1, out):
    a1 = Path(a1)
    ms = a1 / "a1-small.ms"
    z = np.load(a1 / "truth.npz")
    g, b, times = z["raw_gain"], z["raw_bandpass"], z["time"]
    with core_ms.open_table(ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == TARGET_FIELD)
        a1i, a2i = t.getcol_rows("ANTENNA1", rows), t.getcol_rows("ANTENNA2", rows)
        tm = t.getcol_rows("TIME", rows)
        ws = t.getcol_rows("WEIGHT_SPECTRUM", rows).astype(np.float64)
        sigma = t.getcol_rows("SIGMA", rows).astype(np.float64)
        flag = t.getcol_rows("FLAG", rows)
    ti = np.searchsorted(times, tm)
    if not np.allclose(times[np.clip(ti, 0, len(times) - 1)], tm):
        raise SystemExit("MS times are not the truth's integrations")
    cross = a1i != a2i
    res = {}
    for name, corr, hand in (("XX", 0, 0), ("YY", 3, 1)):
        gp = g[ti, a1i, hand][:, None] * b[a1i, :, hand]
        gq = g[ti, a2i, hand][:, None] * b[a2i, :, hand]
        truth = np.abs(gp * gq) ** 2 / sigma[:, corr, None] ** 2
        ok = cross[:, None] & ~flag[..., corr] & (ws[..., corr] > 0)
        ratio = ws[..., corr][ok] / truth[ok]
        dev = np.abs(ratio - 1)
        res[name] = {
            "cells": int(ok.sum()),
            "ratio_median": float(np.median(ratio)),
            "dev_median": float(np.median(dev)),
            "dev_p95": float(np.percentile(dev, 95)),
            "dev_max": float(dev.max()),
        }
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "flags":
        flags(sys.argv[2])
    elif cmd == "score":
        score(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(f"unknown {cmd}")
