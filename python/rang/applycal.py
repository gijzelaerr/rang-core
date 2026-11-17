# SPDX-License-Identifier: GPL-3.0-or-later
# Follows CASA's C++ source in part (Copyright (C) Associated
# Universities, Inc. Washington DC, USA; (L)GPL version 2 or later):
# notices in THIRD-PARTY-NOTICES.txt.
"""CASA `applycal` on a Measurement Set (task C4b, research/c4b-apply-ms.md;
C1 step 7). For example::

    from rang import applycal
    summary = applycal.applycal("my.ms", ["cal.K", "cal.G", "cal.B"],
                                interp=["linear"], gainfield=["", "nearest", ""],
                                calwt=[False], field=["SIM-TARGET"])

Rows are read in chunks through W1's `rang.core_writeback.WriteBack` (a CASA
flag version is saved before the first write), corrected in the Rust kernel
(`rang.cal_apply.apply`, C4a) per field and data description, and written:
CORRECTED_DATA (added and initialised to DATA when absent, as CASA's
`calibrater.open(addcorr=True)`) for the selected rows, FLAG as the input OR
the tables' flags (`applymode='calflag'`), and, when a G, T or B table has
`calwt` true, WEIGHT and WEIGHT_SPECTRUM reset from SIGMA (SIGMA_SPECTRUM)
and scaled as CASA's `VisJones::updateWt2`. K, Df and general Jones terms do
not scale weights, as in CASA. Rows of fields not selected are left as they
are. CASA's argument rules are kept: a one-element `interp`, `gainfield` or
`calwt` list is broadcast; a missing `interp` is `linear`, a missing
`gainfield` is `''`.

Field maps (`gainfield`, CASA's `CTPatchedInterp`): `''` pools every field
of the table into one time series per antenna; a field name or id uses that
table field's rows; `nearest` uses, for each MS field, the table field
nearest on the sky (the only one when the table has one; a tie is an error).

`apply_complex` applies the `complex` gains of a QuartiCal gain store (W2's
`rang-core calibrate`) to the fields and scans they were solved on, on
their own solution bins (`rang.cal_apply.apply_jones`).
"""

import numpy as np

from . import cal_apply, core_ms, core_tasks, core_writeback
from .formats import caltable, quartical_store

MODES = ("calflag", "calflagstrict")
WEIGHT_KINDS = ("G", "T", "B")  # diagonal and scalar Jones (`updateWt2`)
LINEAR = (9, 10, 11, 12)


class ApplyError(ValueError):
    """An apply that cannot run as asked."""


# -- the Measurement Set's subtables -------------------------------------------


def ms_info(ms):
    """FIELD names and phase centres, the window of each data description and
    its CHAN_FREQ, and the antenna count of `ms`."""
    with core_ms.open_table(ms / "FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
        try:
            phase = np.asarray(t.getcol("PHASE_DIR"), np.float64)
        except OSError:  # undefined cells; only gainfield 'nearest' needs them
            phase = np.full((len(names), 1, 2), np.nan)
    with core_ms.open_table(ms / "DATA_DESCRIPTION") as t:
        spw_of = [int(s) for s in t.getcol("SPECTRAL_WINDOW_ID")]
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freqs = [
            np.asarray(t.getcol("CHAN_FREQ", i, 1)[0], float) for i in range(t.nrows)
        ]
    with core_ms.open_table(ms / "ANTENNA") as t:
        nant = t.nrows
    return {
        "fields": names,
        "phase_dir": phase.reshape(len(names), -1, 2)[:, 0, :],
        "spw_of_ddid": spw_of,
        "chan_freq": freqs,
        "nant": nant,
    }


def _unit(lon_lat):
    lon, lat = lon_lat[..., 0], lon_lat[..., 1]
    return np.stack(
        [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=-1
    )


def separation(a, b):
    """Great-circle separation (radians) of (lon, lat) pairs."""
    ua, ub = _unit(np.asarray(a, float)), _unit(np.asarray(b, float))
    cross = np.linalg.norm(np.cross(ua, ub), axis=-1)
    return np.arctan2(cross, np.sum(ua * ub, axis=-1))


def field_map(table, gainfield, info):
    """{MS field id: table FIELD_ID or `cal_apply.POOLED`} for one table and
    its `gainfield`, as CASA's `CTPatchedInterp` (module docstring)."""
    present = sorted({int(f) for f in table.column("FIELD_ID")})
    nfield = len(info["fields"])
    text = "" if gainfield is None else str(gainfield).strip()
    if text == "":
        return dict.fromkeys(range(nfield), cal_apply.POOLED)
    ct_field = table.subtables.get("FIELD", {})
    ct_names = [str(n) for n in ct_field.get("NAME", [])]
    if text == "nearest":
        if len(present) == 1:
            return dict.fromkeys(range(nfield), present[0])
        dirs = np.array(
            [
                np.asarray(ct_field["PHASE_DIR"][f], float).reshape(-1, 2)[0]
                for f in present
            ]
        )
        out = {}
        for f in range(nfield):
            sep = separation(dirs, info["phase_dir"][f])
            order = np.argsort(sep, kind="stable")
            if len(order) > 1 and sep[order[1]] == sep[order[0]]:
                raise ApplyError(
                    f"gainfield nearest: two table fields are equally near MS field "
                    f"{info['fields'][f]!r}, as CASA refuses"
                )
            out[f] = present[int(order[0])]
        return out
    if text.isdigit():
        chosen = int(text)
    elif text in ct_names:
        chosen = ct_names.index(text)
    else:
        raise ApplyError(
            f"gainfield {text!r}: not a field of the table (fields {ct_names}); give one "
            "name or id, nearest, or an empty string"
        )
    if chosen not in present:
        raise ApplyError(f"gainfield {text!r}: the table has no solutions for it")
    return dict.fromkeys(range(nfield), chosen)


def _broadcast(values, n, default, name):
    if values is None:
        values = []
    if isinstance(values, (str, bool)):
        values = [values]
    values = list(values)
    if len(values) == 1:
        return values * n
    if len(values) > n:
        raise ApplyError(f"{name}: {len(values)} values for {n} tables")
    return values + [default] * (n - len(values))


def _field_ids(field, info):
    if field is None:
        return list(range(len(info["fields"])))
    if isinstance(field, (str, int)):
        field = [field]
    out = []
    for f in field:
        if isinstance(f, (int, np.integer)) and 0 <= int(f) < len(info["fields"]):
            out.append(int(f))
        elif isinstance(f, str) and f in info["fields"]:
            out.extend(i for i, n in enumerate(info["fields"]) if n == f)
        elif isinstance(f, str) and f.isdigit() and int(f) < len(info["fields"]):
            out.append(int(f))
        else:
            raise ApplyError(f"field {f!r}: not a field of the MS ({info['fields']})")
    return sorted(set(out))


# -- weights -------------------------------------------------------------------


def _reset_weights(sigma, sigma_spectrum, nchan, spectrum):
    """CASA's weights from sigma: 1/sigma^2 (0 where sigma is not positive),
    per channel from SIGMA_SPECTRUM when it exists, else SIGMA repeated."""

    def inv2(s):
        s = np.asarray(s, np.float32)
        out = np.zeros_like(s)
        good = s > 0
        out[good] = np.float32(1) / (s[good] * s[good])
        return out

    if not spectrum:
        return inv2(sigma), None
    if sigma_spectrum is not None:
        ws = inv2(sigma_spectrum)
    else:
        ws = np.repeat(inv2(sigma)[:, None, :], nchan, axis=1)
    return None, ws


def _median_over_channels(ws):
    """casacore `partialMedians(ws, axis 1)` as CASA writes WEIGHT: the
    element at index (n - 1) // 2 of the sorted channel values, so the lower
    of the two middle values for an even n (measured after run -02 of
    research/c4b-apply-ms.md: CASA's WEIGHT equals it on every value; the
    upper one missed by up to 9.5e-3)."""
    n = ws.shape[1]
    return np.sort(ws, axis=1)[:, (n - 1) // 2, :]


def _b_scale(table, interp, spw, table_field, nant, times):
    """BJones::calcWtScale: per (antenna, time, receptor) the mean of |B|^2
    over the solution channels unflagged after time interpolation; 1 where
    none is. Returns (nant, len(times), 2) float32."""
    t_mode = interp.split(",")[0].strip()
    out = np.ones((nant, len(times), 2), np.float32)
    params, flags = table.params, table.flags
    for a in range(nant):
        rows, t = cal_apply._rows(table, a, spw, table_field)
        if not len(rows):
            continue
        amp = np.abs(params[rows]).astype(np.float32)  # (slot, chan, 2)
        val, flg = caltable._interpolate(t, amp, flags[rows], times, t_mode)
        a2 = np.where(flg, np.float32(0), val * val)
        n = (~flg).sum(axis=1).astype(np.float32)  # (time, 2)
        mean = np.where(n > 0, a2.sum(axis=1, dtype=np.float32) / np.maximum(n, 1), 1)
        norm = np.sqrt(mean.astype(np.float32))
        out[a] = (norm * norm).astype(np.float32)
    return out


def _weight_scale(kind, table, interp, spw, table_field, chunk, freqs, nant):
    """(rows, chan or 1, 4) float32 weight scale of one table on one group."""
    a1, a2, time = chunk["ANTENNA1"], chunk["ANTENNA2"], chunk["TIME"]
    if kind == "B":
        uniq, inv = np.unique(time, return_inverse=True)
        s = _b_scale(table, interp, spw, table_field, nant, uniq)
        sp, sq = s[a1, inv.reshape(-1)], s[a2, inv.reshape(-1)]
        out = np.stack(
            [
                sp[:, 0] * sq[:, 0],
                sp[:, 0] * sq[:, 1],
                sp[:, 1] * sq[:, 0],
                sp[:, 1] * sq[:, 1],
            ],
            axis=-1,
        )
        return out[:, None, :].astype(np.float32)
    ones = np.ones((len(time), len(freqs), 4), np.complex64)
    g, _ = cal_apply.apply(
        ones,
        False,
        time,
        a1,
        a2,
        freqs,
        [table],
        spw=spw,
        interp=[interp],
        direction="corrupt",
        nant=nant,
        table_fields=[table_field],
    )
    return (np.abs(g.astype(np.complex128)) ** 2).astype(np.float32)


# -- applycal ------------------------------------------------------------------


def _field_angles(w, chunk_rows, fields, frame, receptor_angle):
    """P's angle table (`rang.cal_pol.angle_table`) of each of `fields`, over
    all of its rows: the field's unique times and antennas are collected
    chunk by chunk, so no per-row array of the MS is held (task W3b,
    research/w3b-chainchunks.md); the angles equal `row_angles`'."""
    from . import cal_pol

    times = {int(f): [] for f in fields}
    used = {int(f): [] for f in fields}
    for s, n in w.chunks(chunk_rows):
        fid = w.read("FIELD_ID", s, n)
        if not np.isin(fid, list(times)).any():
            continue
        t, a1, a2 = (w.read(k, s, n) for k in ("TIME", "ANTENNA1", "ANTENNA2"))
        for f, seen in times.items():
            sel = fid == f
            if sel.any():
                seen[:] = [np.unique(np.concatenate([*seen, t[sel]]))]
                used[f] = [np.unique(np.concatenate([*used[f], a1[sel], a2[sel]]))]
    return {
        f: cal_pol.angle_table_at(
            w.ms, times[f][0], used[f][0].astype(np.int64), f, frame, receptor_angle
        )
        for f in times
        if times[f]
    }


def _load(t):
    return t if isinstance(t, caltable.CalTable) else caltable.read(t)


def applycal(
    ms,
    gaintable,
    interp=None,
    gainfield=None,
    calwt=(False,),
    field=None,
    applymode="calflag",
    column="CORRECTED_DATA",
    chunk_rows=None,
    session=None,
    flag_backup=core_writeback.DEFAULT_BACKUP,
    stage="apply",
    threads=0,
    scan=None,
    parang=False,
    frame="casa",
    receptor_angle=None,
    parang_flags="spread",
):
    """Apply CASA calibration tables (paths or `CalTable`s) to `ms` as CASA
    `applycal` (module docstring). `session` lets a caller pass an open
    `WriteBack`. `scan` (a list of SCAN_NUMBERs, CASA's `scan`; task C2e)
    restricts the rows corrected. `parang` (task C6w) corrects by the
    parallactic angle P after the tables, as CASA's `parang=True` and
    `rang.cal_pol.apply`, in `frame` (`rang.cal_pol.row_angles`, with
    `receptor_angle` replacing FEED's); the angles of each field are
    computed once over all of the field's rows, so they do not depend on
    the chunking. `parang_flags` is P's flag rule
    (`rang.cal_pol.spread_flags`): `spread`, CASA's, flags all four
    correlations of a cell with any one flagged after the tables; `none`
    keeps the tables' flags (rang before task df-flag-rule). Returns a
    summary."""
    from pathlib import Path

    ms = Path(ms)
    if applymode not in MODES:
        raise ApplyError(f"applymode {applymode!r}: rang applies {list(MODES)}")
    from . import cal_pol

    if parang_flags not in cal_pol.P_FLAG_RULES:
        raise ApplyError(
            f"parang_flags {parang_flags!r}: use one of {list(cal_pol.P_FLAG_RULES)}"
        )
    tables = [_load(t) for t in gaintable]
    if not tables and not parang:
        raise ApplyError("no gaintable given")
    n = len(tables)
    interp = [m or "linear" for m in _broadcast(interp, n, "linear", "interp")]
    gainfield = _broadcast(gainfield, n, "", "gainfield")
    calwt = [bool(c) for c in _broadcast(calwt, n, False, "calwt")]
    for m in interp:
        cal_apply.parse_interp(m)
    lay = core_writeback.layout(ms)
    if tuple(int(c) for c in lay["corr_type"]) != LINEAR:
        raise ApplyError(
            f"{ms}: correlations {list(lay['corr_type'])}; apply needs XX, XY, YX, YY (W4)"
        )
    info = ms_info(ms)
    fields = _field_ids(field, info)
    maps = [field_map(t, g, info) for t, g in zip(tables, gainfield)]
    weighted = [c and t.kind in WEIGHT_KINDS for t, c in zip(tables, calwt)]
    write_weights = any(weighted)
    has = lay["columns"]
    spectrum = "WEIGHT_SPECTRUM" in has
    nchan = lay["cell"][0]
    summary = {
        "ms": str(ms),
        "tables": [
            {
                "kind": t.kind,
                "interp": m,
                "gainfield": g,
                "calwt": c,
                "calwt_effective": w,
                "field_map": {
                    info["fields"][f]: (v if v is not cal_apply.POOLED else "pooled")
                    for f, v in mp.items()
                    if f in fields
                },
            }
            for t, m, g, c, w, mp in zip(
                tables, interp, gainfield, calwt, weighted, maps
            )
        ],
        "fields": [info["fields"][f] for f in fields],
        "scans": None if scan is None else [int(s) for s in np.atleast_1d(scan)],
        "applymode": applymode,
        "column": column,
        "weights_written": write_weights,
        "parang": bool(parang),
        "parang_flags": parang_flags if parang else None,
        "rows": 0,
        "cells_flagged_before": 0,
        "cells_flagged_after": 0,
        "uncovered": [],
    }
    own = session is None
    w = session or core_writeback.WriteBack(
        ms, flag_backup=flag_backup, stage=stage, chunk_rows=chunk_rows
    )
    if own:
        w.begin()
    try:
        added = w.ensure_column(column, init="data")
        summary["column_added"] = bool(added)
        if parang:
            angle_tables = _field_angles(w, chunk_rows, fields, frame, receptor_angle)
            summary["frame"] = frame
            if receptor_angle is not None:
                summary["receptor_angle"] = float(receptor_angle)
        uncovered = set()
        for start, nrow in w.chunks(chunk_rows):
            c = {
                k: w.read(k, start, nrow)
                for k in ("FIELD_ID", "DATA_DESC_ID", "TIME", "ANTENNA1", "ANTENNA2")
            }
            sel = np.isin(c["FIELD_ID"], fields)
            if scan is not None:
                sel &= np.isin(
                    w.read("SCAN_NUMBER", start, nrow),
                    [int(s) for s in np.atleast_1d(scan)],
                )
            if not sel.any():
                continue
            data = w.read("DATA", start, nrow)
            flag = w.read("FLAG", start, nrow)
            out = w.read(column, start, nrow)
            new_flag = flag.copy()
            if write_weights:
                sigma = w.read("SIGMA", start, nrow)
                sigsp = (
                    w.read("SIGMA_SPECTRUM", start, nrow)
                    if "SIGMA_SPECTRUM" in has
                    else None
                )
                weight = w.read("WEIGHT", start, nrow)
                wspec = w.read("WEIGHT_SPECTRUM", start, nrow) if spectrum else None
            keys = np.stack([c["FIELD_ID"], c["DATA_DESC_ID"]], axis=1)[sel]
            rows_sel = np.flatnonzero(sel)
            for fid, ddid in np.unique(keys, axis=0):
                idx = rows_sel[(keys[:, 0] == fid) & (keys[:, 1] == ddid)]
                spw = info["spw_of_ddid"][int(ddid)]
                freqs = info["chan_freq"][spw]
                use, strict_flag = [], False
                for i, t in enumerate(tables):
                    tf = maps[i][int(fid)]
                    rows_t = t.column("SPECTRAL_WINDOW_ID") == spw
                    if tf is not cal_apply.POOLED:
                        rows_t &= t.column("FIELD_ID") == tf
                    if rows_t.any():
                        use.append(i)
                    else:
                        uncovered.add((i, int(fid), spw))
                        strict_flag |= applymode == "calflagstrict"
                group = {k: v[idx] for k, v in c.items()}
                if len(use) < len(tables):
                    # `VisEquation::VBOKforCalApply` fails when any term has
                    # no calibration for the buffer: `Calibrater::correct2`
                    # then neither initialises CORRECTED_DATA nor resets the
                    # weights there; `calflagstrict` flags every cell.
                    if strict_flag:
                        new_flag[idx] = True
                    continue
                if tables:
                    got, gflag = cal_apply.apply(
                        data[idx],
                        flag[idx],
                        group["TIME"],
                        group["ANTENNA1"],
                        group["ANTENNA2"],
                        freqs,
                        tables,
                        spw=spw,
                        interp=interp,
                        threads=threads,
                        nant=info["nant"],
                        table_fields=[maps[i][int(fid)] for i in use],
                    )
                else:
                    got, gflag = data[idx], flag[idx]
                if parang:
                    angles = cal_pol.table_angles(
                        angle_tables[int(fid)],
                        group["TIME"],
                        group["ANTENNA1"],
                        group["ANTENNA2"],
                    )
                    got = cal_pol.rotate(got, *angles, inverse=True)
                    gflag = cal_pol.spread_flags(gflag, parang_flags)
                out[idx] = got
                new_flag[idx] = gflag
                if write_weights:
                    if spectrum:
                        _, ws = _reset_weights(
                            sigma[idx],
                            None if sigsp is None else sigsp[idx],
                            nchan,
                            True,
                        )
                    else:
                        ws, _ = _reset_weights(sigma[idx], None, nchan, False)
                        ws = ws[:, None, :]
                    for i in use:
                        if not weighted[i]:
                            continue
                        s = _weight_scale(
                            tables[i].kind,
                            tables[i],
                            interp[i],
                            spw,
                            maps[i][int(fid)],
                            group,
                            freqs,
                            info["nant"],
                        )
                        if not spectrum:
                            s = s[:, :1, :]
                        ws = (ws * s).astype(np.float32)
                    if spectrum:
                        wspec[idx] = ws
                        weight[idx] = _median_over_channels(ws)
                    else:
                        weight[idx] = ws[:, 0, :]
            summary["rows"] += int(sel.sum())
            summary["cells_flagged_before"] += int(flag[sel].sum())
            summary["cells_flagged_after"] += int(new_flag[sel].sum())
            w.write(column, start, out)
            w.write_flags(start, new_flag)
            if write_weights:
                w.write("WEIGHT", start, weight)
                if spectrum:
                    w.write("WEIGHT_SPECTRUM", start, wspec)
        summary["uncovered"] = [
            {"table": i, "field": info["fields"][f], "spw": s}
            for i, f, s in sorted(uncovered)
        ]
    except BaseException as exc:
        if own:
            w.close(error=exc)
        raise
    if own:
        w.close()
    return summary


# -- the complex term ------------------------------------------------------------


def apply_complex(
    ms,
    store,
    term,
    solints,
    fields=None,
    column="CORRECTED_DATA",
    chunk_rows=None,
    session=None,
    flag_backup=core_writeback.DEFAULT_BACKUP,
    stage="apply",
    threads=0,
    input_column="DATA",
    executor=None,
):
    """Apply the `complex` gains of `term` in a QuartiCal gain store to the
    rows of the fields and scans they were solved on, on their own bins
    (`solints`: the term's `(solint, freqint)` as W2's calibrate used them),
    reading `input_column` (DATA; `column` itself to chain a second term)
    and writing `column`, FLAG OR'd. `fields`: MS field ids to apply to
    (default: every solved field); a field without its own partition is
    refused (transfer is not implemented: CASA G tables, C2a). Row chunks
    are chunk tasks run by `executor` (default: inline;
    research/chunk-task-api.md), written here in row order. Returns a
    summary."""
    from pathlib import Path

    from .core_pipeline import solution_grid

    ms = Path(ms)
    parts = quartical_store.read_term(store, term)
    by_key = {}
    for p in parts:
        if p.type != "complex":
            raise ApplyError(f"{store}: partition {p.name} is {p.type}, not complex")
        key = (
            int(p.attrs["FIELD_ID"]),
            int(p.attrs["SCAN_NUMBER"]),
            int(p.attrs["DATA_DESC_ID"]),
        )
        by_key[key] = p
    solved = sorted({k[0] for k in by_key})
    info = ms_info(ms)
    fields = solved if fields is None else _field_ids(fields, info)
    missing = [info["fields"][f] for f in fields if f not in solved]
    if missing:
        raise ApplyError(
            f"term {term!r} was not solved on {missing}; a complex term is applied "
            "only where it was solved (research/c4b-apply-ms.md, owner decision 2): "
            "solve G and F terms to transfer gains"
        )
    lay = core_writeback.layout(ms)
    nchan = lay["cell"][0]
    solint, freqint = solints
    own = session is None
    w = session or core_writeback.WriteBack(
        ms, flag_backup=flag_backup, stage=stage, chunk_rows=chunk_rows
    )
    if own:
        w.begin()
    summary = {
        "term": term,
        "store": str(store),
        "fields": [info["fields"][f] for f in fields],
        "partitions": [],
    }
    try:
        added = w.ensure_column(column, init="data")
        summary["column_added"] = bool(added)
        # The bins of each partition need all its rows' times, so the row
        # columns are read whole (small); data columns go chunk by chunk.
        nrows = lay["nrows"]
        meta = {
            k: np.concatenate([w.read(k, s, m) for s, m in w.chunks(chunk_rows)])
            for k in ("FIELD_ID", "SCAN_NUMBER", "DATA_DESC_ID", "TIME")
        }
        row_bin = np.full(nrows, -1, np.int64)
        row_part = np.full(nrows, -1, np.int64)
        grids = []
        for key, p in by_key.items():
            fid, scan, ddid = key
            if fid not in fields:
                continue
            rows = np.flatnonzero(
                (meta["FIELD_ID"] == fid)
                & (meta["SCAN_NUMBER"] == scan)
                & (meta["DATA_DESC_ID"] == ddid)
            )
            if not len(rows):
                continue
            order = rows[np.argsort(meta["TIME"][rows], kind="stable")]
            spw = info["spw_of_ddid"][ddid]
            tb, fb, gt, gf = solution_grid(
                meta["TIME"][order], nchan, info["chan_freq"][spw], solint, freqint
            )
            stored_t, stored_f = (
                np.asarray(p["gain_time"], float),
                np.asarray(p["gain_freq"], float),
            )
            if (
                len(gt) != len(stored_t)
                or len(gf) != len(stored_f)
                or not (np.array_equal(gt, stored_t) and np.array_equal(gf, stored_f))
            ):
                raise ApplyError(
                    f"{term} partition {p.name}: its bins ({len(stored_t)} x {len(stored_f)}) "
                    f"are not those of solint {solint}, freqint {freqint} on these rows"
                )
            row_bin[order] = tb
            row_part[order] = len(grids)
            gains = p.gains_2x2()[:, :, :, 0]
            valid = (np.asarray(p["gain_flags"])[:, :, :, 0] == 0) & np.isfinite(
                gains
            ).all(axis=(-1, -2))
            grids.append((gains, valid, fb))
            summary["partitions"].append(
                {
                    "partition": p.name,
                    "field": info["fields"][fid],
                    "scan": scan,
                    "rows": len(rows),
                    "valid_fraction": float(valid.mean()),
                }
            )
        flagged_before = flagged_after = 0
        specs = core_tasks.plan_apply(
            ms, w.chunks(chunk_rows), row_part, row_bin, grids, input_column,
            column, threads,
        )  # fmt: skip
        executor = executor or core_tasks.INLINE
        for part in executor.map(specs, w):
            w.write(column, part["start"], part["out"])
            w.write_flags(part["start"], part["flag"])
            flagged_before += part["before"]
            flagged_after += part["after"]
            del part
        summary["cells_flagged_before"] = flagged_before
        summary["cells_flagged_after"] = flagged_after
    except BaseException as exc:
        if own:
            w.close(error=exc)
        raise
    if own:
        w.close()
    return summary


__all__ = [
    "MODES",
    "ApplyError",
    "apply_complex",
    "applycal",
    "field_map",
    "ms_info",
    "separation",
]
