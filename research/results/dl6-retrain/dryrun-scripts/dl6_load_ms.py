# SPDX-License-Identifier: MIT
"""DL6 dry run, step R2's loader (research/dl6-retrain.md section 8): one
DL2 Measurement Set scan to the scan form of F3/F4/F5's loaders
(`rang.f3flag.read_luno`): cross rows with FLAG_ROW rows dropped, DATA
complex64 (row, chan, corr), FLAG bool (row, chan, corr), antennas, times,
antenna positions, channel frequencies and widths, correlation types.

    python dl6_load_ms.py OUT_DIR MS [MS ...]

Runs in a python-casacore venv (DL2's `.venv-dl2`); writes OUT_DIR/<scan>.npz
with `keep` (the MS rows kept, for the teachers' labels) and a receipt
OUT_DIR/<scan>.json (MS path, its DL2 hash file's sha256, shapes, wall).
Opens every table read-only. Refuses DL6's held-out scans (23, 25).
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from casacore.tables import table

HELDOUT = {"scan023.ms", "scan025.ms"}


def sub(ms, name, col):
    t = table(f"{ms}/{name}", ack=False, readonly=True)
    try:
        return t.getcol(col)
    finally:
        t.close()


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for ms in map(Path, sys.argv[2:]):
        if ms.name in HELDOUT:
            raise SystemExit(f"{ms}: held out for DL6's agent test (section 8)")
        t0 = time.perf_counter()
        t = table(str(ms), ack=False, readonly=True)
        try:
            a1 = t.getcol("ANTENNA1").astype(np.int32)
            a2 = t.getcol("ANTENNA2").astype(np.int32)
            frow = t.getcol("FLAG_ROW").astype(bool)
            keep = np.flatnonzero((a1 != a2) & ~frow)
            data = t.getcol("DATA")[keep].astype(np.complex64)
            flag = t.getcol("FLAG")[keep].astype(bool)
            times = t.getcol("TIME")[keep].astype(np.float64)
        finally:
            t.close()
        name = ms.stem
        np.savez(
            out / f"{name}.npz",
            data=np.ascontiguousarray(data),
            input_flags=np.ascontiguousarray(flag),
            antenna1=np.ascontiguousarray(a1[keep]),
            antenna2=np.ascontiguousarray(a2[keep]),
            times=times,
            antenna_position=sub(ms, "ANTENNA", "POSITION").astype(np.float64),
            chan_freq=sub(ms, "SPECTRAL_WINDOW", "CHAN_FREQ")[0].astype(np.float64),
            chan_width=sub(ms, "SPECTRAL_WINDOW", "CHAN_WIDTH")[0].astype(np.float64),
            corr_type=sub(ms, "POLARIZATION", "CORR_TYPE")[0].astype(np.int32),
            keep=keep,
        )
        hashfile = ms.parent.parent.parent / "manifests" / ms.parent.name / f"{name}.sha256"
        rec = {
            "ms": str(ms),
            "ms_hash": hashlib.sha256(hashfile.read_bytes()).hexdigest()
            if hashfile.exists()
            else None,
            "rows_ms": int(len(a1)),
            "rows_kept": int(len(keep)),
            "shape": list(data.shape),
            "flagged_input": float(flag.mean()),
            "wall_s": round(time.perf_counter() - t0, 1),
        }
        (out / f"{name}.json").write_text(json.dumps(rec, indent=1) + "\n")
        print(json.dumps(rec), flush=True)


if __name__ == "__main__":
    main()
