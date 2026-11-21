# SPDX-License-Identifier: MIT
"""Residual flagging, `flag.residual` (issue #51, research/flag-residual.md).

`flag_fields(w, fields, cfg, ...)` adds flags on calibrator fields from
their residual: the corrected data minus the field's per-channel,
per-correlation complex median over each scan (model-free; parallactic angle
applied by the caller's apply, so a polarised calibrator is constant in the
sky frame). The statistics unit is one (field, scan) block (amendment 2).
Rules (`rang._core.flag_residual_rang`, `flag_residual_quartical`):

- `method: rang`: antenna-factorised noise per 16-channel block, a cell
  where any correlation has z > `sigma`, a baseline's channel or dump whose
  mean z^2 exceeds `persist` x the block's median, a guard keeping each
  calibrator baseline at or below `guard` flagged;
- `method: quartical`: QuartiCal 0.2.7's `mad_flags` on the same residual,
  diagonal correlations, `threshold_bl` = `sigma`, `threshold_global` =
  `global_sigma`, one chunk per scan.

New flags are OR-ed into FLAG in every correlation, through the caller's
`WriteBack` session.
"""

import numpy as np

from . import core

BLOCK = 16
DIAGONAL = (0, 3)  # XX, YY


def _ext():
    return core.extension()


def _rows_by_scan(w, fields, scans=None):
    """{(field, scan): sorted row indices} over the whole MS."""
    n = w.layout["nrows"] if w.layout else None
    if n is None:
        n = sum(k for _, k in w.chunks())
    fid = w.read("FIELD_ID", 0, n)
    scan = w.read("SCAN_NUMBER", 0, n)
    out = {}
    for f in fields:
        sel = np.flatnonzero(fid == f)
        for s in np.unique(scan[sel]):
            if scans is not None and int(s) not in scans:
                continue
            out[(int(f), int(s))] = sel[scan[sel] == s]
    return out


def _block(w, rows):
    """Read the contiguous span holding `rows`: (start, n, index into span)."""
    start, stop = int(rows.min()), int(rows.max()) + 1
    return start, stop - start, rows - start


def flag_block(w, rows, cfg, nant, column="CORRECTED_DATA", write=True):
    """Flags for one (field, scan) block against the flags now in the MS;
    writes them (or not) and returns (record, new (row, chan) bool)."""
    start, n, idx = _block(w, rows)
    data = w.read(column, start, n)[idx]
    flag = w.read("FLAG", start, n)
    sub = flag[idx]
    a1 = w.read("ANTENNA1", start, n)[idx].astype(np.uint32)
    a2 = w.read("ANTENNA2", start, n)[idx].astype(np.uint32)
    times = w.read("TIME", start, n)[idx]
    nrow, nchan, ncorr = data.shape
    flag8 = np.ascontiguousarray(sub, np.uint8)
    pairs = np.ascontiguousarray(data, np.complex64).view(np.float32)
    model = _ext().flag_residual_median_model(pairs, flag8, nrow, nchan, ncorr)
    model = model.reshape(nchan, ncorr, 2).view(np.complex64)[..., 0]
    res = np.ascontiguousarray(data - model[None], np.complex64)
    res[~np.isfinite(res)] = 0
    resf = res.view(np.float32)
    if cfg["method"] == "rang":
        dump = np.unique(times, return_inverse=True)[1].astype(np.uint32)
        new, counts = _ext().flag_residual_rang(
            resf, flag8, nrow, nchan, ncorr, a1, a2, dump, nant,
            float(cfg["sigma"]), float(cfg["persist"]), BLOCK, float(cfg["guard"]),
        )  # fmt: skip
        counts = dict(counts)
    else:
        rowflag = np.ascontiguousarray(sub.any(-1), np.uint8)
        new = _ext().flag_residual_quartical(
            resf, rowflag, nrow, nchan, ncorr, a1, a2, nant, list(DIAGONAL),
            float(cfg["sigma"]), float(cfg["global_sigma"]), 0.0,
        )  # fmt: skip
        counts = {"added": int(new.sum())}
    new = new.reshape(nrow, nchan).astype(bool)
    before = sub.any(-1)
    added = new & ~before
    cross = a1 != a2
    if write:
        flag[idx] = sub | new[..., None]
        w.write_flags(start, flag)
    v = np.abs(0.5 * (res[..., 1] - res[..., 2]))
    rec = {
        "rows": int(nrow),
        "flagged_before": float(before[cross].mean()) if cross.any() else 0.0,
        "flagged_after": float((before | new)[cross].mean()) if cross.any() else 0.0,
        "added": int(added[cross].sum()),
        "counts": counts,
        "v_rms_kept": float(np.sqrt(np.mean(v[cross][~(before | new)[cross]] ** 2)))
        if (~(before | new)[cross]).any()
        else None,
    }
    return rec, added


def or_flags(w, rows, new):
    """OR `new` ((row, chan) bool, rows as `rows`) into FLAG in every correlation."""
    start, n, idx = _block(w, rows)
    flag = w.read("FLAG", start, n)
    flag[idx] |= new[..., None]
    w.write_flags(start, flag)


def flag_fields(w, fields, cfg, nant, names, scans=None, write=True):
    """Flags for every (field, scan) block of `fields`: (summary per block,
    {(field, scan): (rows, new flags)}). With `write`, they are OR-ed into
    FLAG at once; otherwise the caller writes them (`or_flags`)."""
    out, new = [], {}
    for (f, s), rows in sorted(_rows_by_scan(w, fields, scans).items()):
        rec, added = flag_block(w, rows, cfg, nant, write=write)
        rec.update({"field": names[f], "field_id": f, "scan": s})
        out.append(rec)
        new[(f, s)] = (rows, added)
    return out, new


TRIPWIRE_TYPES = ("K", "G", "B", "F")


def solution_flag_fractions(steps, types=None):
    """{table name: flagged fraction of its solutions} from each step's CASA
    table (FLAG of the main table), for the step types `types` (all with a
    table when None)."""
    from .formats import caltable

    out = {}
    for step in steps:
        if not step.get("path") or (types and step.get("type") not in types):
            continue
        flag = caltable.read(step["path"]).flags
        out[step["name"]] = float(flag.mean()) if flag.size else 0.0
    return out


def tripwire(steps, limit):
    """(fired, {table: flagged solution fraction}) over K, G (G, Gsec), B and F."""
    frac = solution_flag_fractions(steps, TRIPWIRE_TYPES)
    return any(v > limit for v in frac.values()), frac


__all__ = [
    "BLOCK",
    "flag_block",
    "flag_fields",
    "or_flags",
    "solution_flag_fractions",
    "tripwire",
]
