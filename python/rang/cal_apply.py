# SPDX-License-Identifier: GPL-3.0-or-later
"""Correct and corrupt visibilities by CASA calibration tables in the Rust
kernel (task C4a, research/c4a-apply.md; C1 step 2).

`apply(...)` takes the arguments of `rang.formats.caltable.correct` and
runs `core/src/cal/apply.rs` in the extension (`rang._core.cal_apply`):
the same model (VisCal order, CASA's time interpolation in float32,
frequency bridging, K pivot, Df's linear approximation, `calflag` flags),
with `direction='corrupt'` as its exact inverse and an `interp` per table.
Python only selects each table's rows per antenna for the field and window
(`caltable._series`) and packs them; interpolation and the apply run in
Rust. Weights are not touched here (`calwt` is `rang.applycal`, task C4b).

`interp` is CASA's string per table: `'linear'` or `'nearest'` (time; the
frequency part is then `linear`, as `applycal`), or `'<time>,<freq>'` with
each `linear` or `nearest`. `'caracal'` gives CARACal's per-term defaults
(`CARACAL_INTERP`). The `flag` suffixes and other modes are refused.
"""

import numpy as np

from .formats import caltable

# The kernel's codes (`apply::Kind`); KCROSS, Xf and P are refused by the
# kernel with the C1 step that adds them.
KINDS = {"B": 0, "K": 1, "Kcross": 2, "G": 3, "T": 4, "Df": 5, "Xf": 6, "P": 7}
INTERP = {"linear": 0, "nearest": 1}
DIRECTIONS = {"correct": 0, "corrupt": 1}

# CARACal 8f7bb363: crosscal_worker.py RULES (K, G, F, B linear) and
# polcal_worker.py (Gpol linear; KCROSS, Xf, Df nearest).
CARACAL_INTERP = {
    "K": "linear",
    "G": "linear",
    "B": "linear",
    "T": "linear",
    "Kcross": "nearest",
    "Xf": "nearest",
    "Df": "nearest",
}


def parse_interp(text):
    """CASA's interp string as (time, frequency) kernel codes."""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) == 1:
        parts.append("linear")
    if len(parts) != 2 or any(p not in INTERP for p in parts):
        raise ValueError(
            f"unsupported interp {text!r}: use 'linear', 'nearest' or '<time>,<freq>' of those"
        )
    return INTERP[parts[0]], INTERP[parts[1]]


def _interps(tables, interp):
    if interp == "caracal":
        return [CARACAL_INTERP[t.kind] for t in tables]
    if isinstance(interp, str):
        return [interp] * len(tables)
    interp = list(interp)
    if len(interp) != len(tables):
        raise ValueError("give one interp per table")
    return interp


POOLED = "pooled"


def _rows(table, antenna, spw, table_field):
    """Rows of one antenna and window sorted by time: of one table field
    (an int), or of every field pooled (`POOLED`, CASA's `gainfield=''`;
    task C4b)."""
    pick = (table.column("ANTENNA1") == antenna) & (
        table.column("SPECTRAL_WINDOW_ID") == spw
    )
    if table_field is not POOLED:
        pick &= table.column("FIELD_ID") == int(table_field)
    rows = np.flatnonzero(pick)
    t = table.column("TIME")[rows]
    order = np.argsort(t, kind="stable")
    return rows[order], t[order]


def pack(tables, nant, spw=0, field_id=0, interp="linear", table_fields=None):
    """The kernel's packed term arrays (`ffi_apply.rs`) for `tables`, the
    rows of each antenna `a < nant` selected as `caltable._series`, or, when
    `table_fields` is given (one per table), of that table field or of
    every field pooled (`POOLED`), as CASA's field maps (task C4b)."""
    interp = _interps(tables, interp)
    if table_fields is not None and len(table_fields) != len(tables):
        raise ValueError("give one table field per table")
    kind, ti, fi, npar, kref = [], [], [], [], []
    starts, slot_time, params, flags, sol_freq = [], [], [], [], []
    so, po, fo, qo = [0], [0], [0], [0]
    for i, (table, mode) in enumerate(zip(tables, interp)):
        if table.kind not in KINDS:
            raise ValueError(f"unsupported calibration type {table.kind!r}")
        t_mode, f_mode = parse_interp(mode)
        all_params = table.params
        all_flags = table.flags
        freqs = table.solution_frequencies(spw)
        kind.append(KINDS[table.kind])
        ti.append(t_mode)
        fi.append(f_mode)
        npar.append(all_params.shape[2])
        kref.append(table.k_reference_frequency(spw))
        start = [0]
        nparams = nflags = 0
        for a in range(nant):
            if table_fields is None:
                rows, t = caltable._series(table, a, spw, field_id)
            else:
                rows, t = _rows(table, a, spw, table_fields[i])
            slot_time.append(np.asarray(t, np.float64))
            p = all_params[rows]
            if table.float_param:
                p = np.ascontiguousarray(p, np.float32).ravel()
            else:
                p = np.ascontiguousarray(p, np.complex64).view(np.float32).ravel()
            f = np.asarray(all_flags[rows], np.uint8).ravel()
            params.append(p)
            flags.append(f)
            nparams += len(p)
            nflags += len(f)
            start.append(start[-1] + len(rows))
        starts.extend(start)
        sol_freq.append(np.asarray(freqs, np.float64))
        so.append(so[-1] + start[-1])
        po.append(po[-1] + nparams)
        fo.append(fo[-1] + nflags)
        qo.append(qo[-1] + len(freqs))

    def cat(parts, dtype):
        return np.ascontiguousarray(
            np.concatenate(parts) if parts else np.zeros(0, dtype), dtype
        )

    return {
        "kind": np.asarray(kind, np.uint32),
        "time_interp": np.asarray(ti, np.uint32),
        "freq_interp": np.asarray(fi, np.uint32),
        "npar": np.asarray(npar, np.uint32),
        "k_ref_freq": np.asarray(kref, np.float64),
        "slot_start": np.asarray(starts, np.uint64),
        "slot_offset": np.asarray(so, np.uint64),
        "slot_time": cat(slot_time, np.float64),
        "param_offset": np.asarray(po, np.uint64),
        "params": cat(params, np.float32),
        "flag_offset": np.asarray(fo, np.uint64),
        "term_flags": cat(flags, np.uint8),
        "freq_offset": np.asarray(qo, np.uint64),
        "sol_freq": cat(sol_freq, np.float64),
    }


def extension():
    """The extension module that runs the kernel (`rang._core`)."""
    from rang import core

    return core.extension()


def apply(
    data,
    flag,
    time,
    antenna1,
    antenna2,
    frequencies,
    tables,
    field_id=0,
    spw=0,
    interp="linear",
    direction="correct",
    threads=0,
    nant=None,
    table_fields=None,
    channels=None,
):
    """Correct (or corrupt) `data` (row, chan, 4) by `tables` (CalTable
    list) in the Rust kernel; returns (complex64 visibilities, bool flags).
    The flags are `flag` OR the tables' flags. `threads` 0 uses the global
    rayon pool. `table_fields` (one per table: a table FIELD_ID or
    `POOLED`) overrides `field_id`'s row choice (task C4b). `channels` (a
    slice of `frequencies`, the window's whole band): `data` holds only
    those channels, corrected exactly as the same channels of the whole
    band (research/sliced-read.md)."""
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {sorted(DIRECTIONS)}")
    data = np.ascontiguousarray(data, np.complex64)
    if data.ndim != 3 or data.shape[2] != 4:
        raise ValueError("data must be (row, chan, 4)")
    flag = np.ascontiguousarray(
        np.broadcast_to(np.asarray(flag, bool), data.shape), np.uint8
    )
    a1 = np.ascontiguousarray(antenna1, np.uint32)
    a2 = np.ascontiguousarray(antenna2, np.uint32)
    if nant is None:
        nant = int(max(a1.max(initial=0), a2.max(initial=0))) + 1
    packed = pack(
        list(tables),
        nant,
        spw=spw,
        field_id=field_id,
        interp=interp,
        table_fields=table_fields,
    )
    first = 0
    if channels is not None:
        first, stop, step = channels.indices(len(frequencies))
        if step != 1 or stop - first != data.shape[1]:
            raise ValueError(
                "channels must be a unit-step slice of the data's channels"
            )
    out = np.empty_like(data)
    out_flag = np.empty(data.shape, np.uint8)
    extension().cal_apply(
        data,
        flag,
        np.ascontiguousarray(time, np.float64),
        a1,
        a2,
        np.ascontiguousarray(frequencies, np.float64),
        int(nant),
        packed["kind"],
        packed["time_interp"],
        packed["freq_interp"],
        packed["npar"],
        packed["k_ref_freq"],
        packed["slot_start"],
        packed["slot_offset"],
        packed["slot_time"],
        packed["param_offset"],
        packed["params"],
        packed["flag_offset"],
        packed["term_flags"],
        packed["freq_offset"],
        packed["sol_freq"],
        DIRECTIONS[direction],
        int(threads),
        out,
        out_flag,
        int(first),
    )
    return out, out_flag.astype(bool)


def apply_jones(
    data,
    flag,
    antenna1,
    antenna2,
    gains,
    valid,
    time_bin,
    freq_bin,
    direction="correct",
    threads=0,
):
    """Correct (or corrupt) `data` (row, chan, 4) by binned general 2x2
    gains `(time_bin, freq_bin, antenna, 2, 2)` (the `complex` term of
    `rang.core.solve_complex`) on their own bins, in the Rust kernel
    (`apply.rs` `apply_jones`, task C4b). `valid` `(time_bin, freq_bin,
    antenna)`; `time_bin` per row, `freq_bin` per channel. Returns (complex64
    visibilities, bool flags): a cell is flagged in all four correlations when
    any of its input flags is set or either antenna's gain is invalid or
    singular (CASA's general-Jones rule); a bad side is the identity."""
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {sorted(DIRECTIONS)}")
    data = np.ascontiguousarray(data, np.complex64)
    if data.ndim != 3 or data.shape[2] != 4:
        raise ValueError("data must be (row, chan, 4)")
    flag = np.ascontiguousarray(
        np.broadcast_to(np.asarray(flag, bool), data.shape), np.uint8
    )
    gains = np.ascontiguousarray(gains, np.complex128)
    if gains.ndim != 5 or gains.shape[3:] != (2, 2):
        raise ValueError("gains must be (time_bin, freq_bin, antenna, 2, 2)")
    valid = np.ascontiguousarray(
        np.broadcast_to(np.asarray(valid, bool), gains.shape[:3]), np.uint8
    )
    out = np.empty_like(data)
    out_flag = np.empty(data.shape, np.uint8)
    extension().cal_apply_jones(
        data,
        flag,
        np.ascontiguousarray(antenna1, np.uint32),
        np.ascontiguousarray(antenna2, np.uint32),
        int(gains.shape[2]),
        gains,
        valid,
        np.ascontiguousarray(time_bin, np.uint32),
        np.ascontiguousarray(freq_bin, np.uint32),
        DIRECTIONS[direction],
        int(threads),
        out,
        out_flag,
    )
    return out, out_flag.astype(bool)


def class_c(got, expected, ok):
    """Class C (research/c4a-apply.md section 2) of `got` against the
    oracle `expected` (row, chan, 4) on correlations `ok`: per correlation
    `|r - c| <= 1e-6 |c|` or `<= 11 eps32 max_k |c_k|` (the oracle's cell).
    Returns a summary with `pass`."""
    got = np.asarray(got, np.complex128)
    expected = np.asarray(expected, np.complex128)
    err = np.abs(got - expected)
    mag = np.abs(expected)
    scale = np.max(mag, axis=-1, keepdims=True) * float(np.finfo(np.float32).eps)
    passed = (err <= 1e-6 * mag) | (err <= 11 * scale)
    ok = np.asarray(ok, bool)
    n = int(ok.sum())
    rel = np.where(
        mag > 0, err / np.where(mag > 0, mag, 1), np.where(err > 0, np.inf, 0)
    )
    eps = err / np.where(scale > 0, scale, 1)
    return {
        "cells": n,
        "max_relative": float(rel[ok].max()) if n else None,
        "max_float32_eps_of_cell": float(eps[ok].max()) if n else None,
        "above_1e-6": int(np.sum((err > 1e-6 * mag) & ok)),
        "failing": int(np.sum(~passed & ok)),
        "pass": bool(n > 0 and np.all(passed[ok])),
    }


__all__ = [
    "CARACAL_INTERP",
    "POOLED",
    "apply",
    "apply_jones",
    "class_c",
    "pack",
    "parse_interp",
]
