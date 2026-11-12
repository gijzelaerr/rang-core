# SPDX-License-Identifier: GPL-3.0-or-later
"""W1 oracles inside the containers (research/w1-writeback.md). Imports no
rang code. Each mode writes a JSON file.

    python3 oracle.py casacore <ms> <writes.npz> <pristine.ms> <out.json>
    /opt/casa/bin/python oracle.py casa-list <ms> <out.json>
    /opt/casa/bin/python oracle.py casa-flagmanager <ms> <restore|save> <name> <out.json>
    /opt/casa/bin/python oracle.py casa-split <ms> <corrected|model> <outvis> <out.json>
    /opt/casa/bin/python oracle.py casa-applycal <ms> <out.json>
    python3 oracle.py split-compare <ms> <splitvis> <column> <out.json>
    python3 oracle.py applycal-compare <ms> <out.json>
    /opt/qc/bin/python oracle.py daskms <ms> <writes.npz> <out.json>
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

COLUMNS = (
    "MODEL_DATA",
    "CORRECTED_DATA",
    "WEIGHT_SPECTRUM",
    "WEIGHT",
    "FLAG",
    "FLAG_ROW",
)
EPS32 = float(np.finfo(np.float32).eps)


def dump(out, record):
    Path(out).write_text(json.dumps(record, indent=1, default=str))


def sha_chunks(get, nrow, chunk=1024):
    """SHA-256 of a column's values, read in chunks of 1024 rows (the same
    bytes as rang's `examples/w1_writeback.py sha`)."""
    h = hashlib.sha256()
    for s in range(0, nrow, chunk):
        h.update(np.ascontiguousarray(get(s, min(chunk, nrow - s))).tobytes())
    return h.hexdigest()


def casacore_check(ms, npz, pristine, out):
    from casacore import tables as pt

    w = np.load(npz)
    t = pt.table(ms, ack=False)
    nrow = t.nrows()
    rec = {"casacore": pt.__name__, "nrows": nrow, "hashes": {}, "columns": {}}
    try:
        import casacore

        rec["casacore_version"] = casacore.__version__
    except AttributeError:
        pass
    for c in t.colnames():
        try:
            rec["hashes"][c] = sha_chunks(lambda s, n, c=c: t.getcol(c, s, n), nrow)
        except RuntimeError as e:
            rec["hashes"][c] = f"unreadable: {e}"
    for c in COLUMNS:
        if c in t.colnames():
            rec["columns"][c] = {
                "desc": t.getcoldesc(c),
                "dminfo": t.getdminfo(c),
                "keywords": t.getcolkeywords(c),
            }
    data = t.getcol("DATA")
    checks = {
        "MODEL_DATA == 2 DATA": bool(np.array_equal(t.getcol("MODEL_DATA"), 2 * data)),
        "CORRECTED_DATA == DATA": bool(
            np.array_equal(t.getcol("CORRECTED_DATA"), data)
        ),
        "FLAG == written": bool(np.array_equal(t.getcol("FLAG"), w["flag"])),
        "FLAG_ROW == written": bool(
            np.array_equal(t.getcol("FLAG_ROW"), w["flag_row"])
        ),
    }
    if "weight" in w.files:
        checks["WEIGHT_SPECTRUM == written"] = bool(
            np.array_equal(t.getcol("WEIGHT_SPECTRUM"), w["weight_spectrum"])
        )
        checks["WEIGHT == written"] = bool(
            np.array_equal(t.getcol("WEIGHT"), w["weight"])
        )
    elif bool(w["added_WEIGHT_SPECTRUM"]):
        ws, wt = t.getcol("WEIGHT_SPECTRUM"), t.getcol("WEIGHT")
        checks["WEIGHT_SPECTRUM == WEIGHT over channels"] = bool(
            np.array_equal(ws, np.repeat(wt[:, None, :], ws.shape[1], axis=1))
        )
    p = pt.table(pristine, ack=False)
    v = pt.table(ms + ".flagversions/flags.rang_original", ack=False)
    checks["backup FLAG == pristine FLAG"] = bool(
        np.array_equal(v.getcol("FLAG"), p.getcol("FLAG"))
    )
    checks["backup FLAG_ROW == pristine FLAG_ROW"] = bool(
        np.array_equal(v.getcol("FLAG_ROW"), p.getcol("FLAG_ROW"))
    )
    rec["backup"] = {
        "desc": {c: v.getcoldesc(c) for c in v.colnames()},
        "info": v.info(),
        "nrows": v.nrows(),
    }
    rec["pristine_hashes"] = {
        c: sha_chunks(lambda s, n, c=c: p.getcol(c, s, n), p.nrows())
        for c in ("FLAG", "FLAG_ROW")
    }
    rec["checks"] = checks
    dump(out, rec)


def casa_list(ms, out):
    from casatasks import flagmanager, listobs

    t0 = time.perf_counter()
    summary = listobs(vis=ms, listfile=out + ".listobs.txt", overwrite=True)
    versions = flagmanager(vis=ms, mode="list")
    dump(
        out,
        {
            "wall_s": time.perf_counter() - t0,
            "listobs_nrows": summary.get("nrows")
            if isinstance(summary, dict)
            else None,
            "flagmanager_list": versions,
        },
    )


def casa_flagmanager(ms, mode, name, out):
    from casatasks import flagmanager

    t0 = time.perf_counter()
    result = flagmanager(vis=ms, mode=mode, versionname=name, comment="CASA oracle")
    dump(out, {"wall_s": time.perf_counter() - t0, "result": result})


def casa_split(ms, column, outvis, out):
    from casatasks import split

    t0 = time.perf_counter()
    result = split(vis=ms, outputvis=outvis, datacolumn=column, keepflags=True)
    dump(out, {"wall_s": time.perf_counter() - t0, "result": result})


def casa_applycal(ms, out):
    from casatasks import applycal, gencal

    t0 = time.perf_counter()
    table = ms + ".amp2"
    gencal(vis=ms, caltable=table, caltype="amp", parameter=[2.0])
    applycal(vis=ms, gaintable=[table], calwt=False, flagbackup=False)
    dump(out, {"wall_s": time.perf_counter() - t0})


def _sorted(t, cols):
    key = np.lexsort((t.getcol("ANTENNA2"), t.getcol("ANTENNA1"), t.getcol("TIME")))
    return {c: t.getcol(c)[key] for c in cols}


def split_compare(ms, splitvis, column, out):
    from casacore import tables as pt

    a = _sorted(pt.table(ms, ack=False), [column, "FLAG", "FLAG_ROW"])
    b = _sorted(pt.table(splitvis, ack=False), ["DATA", "FLAG", "FLAG_ROW"])
    dump(
        out,
        {
            "rows": [len(a[column]), len(b["DATA"])],
            f"split DATA == {column}": bool(np.array_equal(a[column], b["DATA"])),
            "FLAG equal": bool(np.array_equal(a["FLAG"], b["FLAG"])),
            "FLAG_ROW equal": bool(np.array_equal(a["FLAG_ROW"], b["FLAG_ROW"])),
        },
    )


def applycal_compare(ms, out):
    from casacore import tables as pt

    t = pt.table(ms, ack=False)
    got, data = t.getcol("CORRECTED_DATA"), t.getcol("DATA")
    want = data / np.float32(4)
    diff = np.abs(got - want)
    rel = diff / np.maximum(np.abs(want), np.finfo(np.float32).tiny)
    scale = np.abs(want).max(axis=-1, keepdims=True)
    ok = (rel <= 1e-6) | (diff <= 11 * EPS32 * scale)
    flag = t.getcol("FLAG")
    dump(
        out,
        {
            "cells": int(diff.size),
            "max_abs": float(diff.max()),
            "max_rel": float(rel.max()),
            "cells_failing_class_C": int((~ok).sum()),
            "cells_failing_unflagged": int((~ok & ~flag).sum()),
            "exactly_equal": bool(np.array_equal(got, want)),
        },
    )


def daskms_check(ms, npz, out):
    import daskms
    from daskms import xds_from_ms

    w = np.load(npz)
    cols = ["DATA", *COLUMNS]
    parts = xds_from_ms(ms, columns=cols)
    nrow = sum(ds.sizes["row"] for ds in parts)
    arrays = {}
    for c in cols:
        first = parts[0][c]
        full = np.empty((nrow, *first.shape[1:]), first.dtype)
        for ds in parts:
            full[ds.ROWID.values] = ds[c].values
        arrays[c] = full
    data = arrays["DATA"]
    checks = {
        "MODEL_DATA == 2 DATA": bool(np.array_equal(arrays["MODEL_DATA"], 2 * data)),
        "CORRECTED_DATA == DATA": bool(np.array_equal(arrays["CORRECTED_DATA"], data)),
        "FLAG == written": bool(np.array_equal(arrays["FLAG"], w["flag"])),
        "FLAG_ROW == written": bool(np.array_equal(arrays["FLAG_ROW"], w["flag_row"])),
    }
    if "weight" in w.files:
        checks["WEIGHT_SPECTRUM == written"] = bool(
            np.array_equal(arrays["WEIGHT_SPECTRUM"], w["weight_spectrum"])
        )
        checks["WEIGHT == written"] = bool(
            np.array_equal(arrays["WEIGHT"], w["weight"])
        )
    elif bool(w["added_WEIGHT_SPECTRUM"]):
        ws, wt = arrays["WEIGHT_SPECTRUM"], arrays["WEIGHT"]
        checks["WEIGHT_SPECTRUM == WEIGHT over channels"] = bool(
            np.array_equal(ws, np.repeat(wt[:, None, :], ws.shape[1], axis=1))
        )
    hashes = {c: sha_chunks(lambda s, n, a=arrays[c]: a[s : s + n], nrow) for c in cols}
    dump(
        out,
        {
            "daskms": daskms.__version__,
            "partitions": len(parts),
            "nrows": nrow,
            "checks": checks,
            "hashes": hashes,
            "dtypes": {c: str(a.dtype) for c, a in arrays.items()},
        },
    )


def qc_gains(store, out):
    """Median |gain| on the parallel hands of a QuartiCal G solve (reported,
    not gated)."""
    from daskms.experimental.zarr import xds_from_zarr

    amps, flagged, total = [], 0, 0
    for ds in xds_from_zarr(f"{store}::G"):
        g = ds.gains.values  # (time, freq, antenna, direction, correlation)
        f = ds.gain_flags.values.astype(bool)  # (time, freq, antenna, direction)
        a = np.abs(g[..., [0, -1]])[~f]
        amps.append(a.reshape(-1))
        flagged += int(f.sum())
        total += int(f.size)
    a = np.concatenate(amps)
    dump(
        out,
        {
            "median_abs_gain_parallel": float(np.median(a)),
            "expected": float(1 / np.sqrt(2)),
            "max_abs_deviation": float(np.abs(a - 1 / np.sqrt(2)).max()),
            "n": int(a.size),
            "flagged_solutions": [flagged, total],
        },
    )


MODES = {
    "qc-gains": qc_gains,
    "casacore": casacore_check,
    "casa-list": casa_list,
    "casa-flagmanager": casa_flagmanager,
    "casa-split": casa_split,
    "casa-applycal": casa_applycal,
    "split-compare": split_compare,
    "applycal-compare": applycal_compare,
    "daskms": daskms_check,
}

if __name__ == "__main__":
    MODES[sys.argv[1]](*sys.argv[2:])
