# SPDX-License-Identifier: GPL-3.0-or-later
"""The self-calibration terms Sp, Sa and Sd (task C5, research/c5-selfcal.md;
C1's T12, research/c1-calibration-chain.md).

CARACal's selfcal worker solves one CubiCal term per round on the target's
1GC-corrected data against MODEL_DATA and writes the corrected data
(`calibrate_cubical`, `gain_matrix_type` and `gsols_timeslots` per round).
Here each term is solved by the QuartiCal kernels rang already has, without
CASA's rules (`casa_rules=False`, QuartiCal's referencing to the refant):

- `Sp`: a phase per antenna and hand (`GainDiagPhase`; QuartiCal `phase`,
  `rang.cal_gain`, calmode p);
- `Sa`: a complex gain per antenna and hand (`GainDiag`; QuartiCal
  `diag_complex`, calmode ap);
- `Sd`: a phase and a delay per antenna and hand over the band (`Fslope`;
  QuartiCal `delay_and_offset`, `rang.cal_delay`), applied as its
  per-channel gains, offsets included. It starts at zero delay, as CubiCal
  and QuartiCal's default do: the FFT initial estimate of K failed on a
  structured sky model (post hoc, research/c5-selfcal.md section 6).

Layers:

- `time_bins(...)`, `freq_bins(...)`: the solution intervals of a term. An
  integer `solint` is N integrations from each scan start (CARACal's
  timeslots, QuartiCal's `time_interval`), `int` one per integration, `inf`
  one per scan, and seconds (`'60s'`) CASA's bins (`cal_gain.solint_bins`).
  Intervals never cross a scan. `freqint` (Sp, Sa) is `inf` or N channels.
- `solve(...)`: one term on the rows of one field of a single-window MS,
  read and solved in chunks of whole intervals within a
  `core_chunks.ChainBudget` (task W3b), with CARACal's gain clip.
- `apply(...)`: the input column corrected by the solutions on their own
  bins into the output column of a `core_writeback.WriteBack` session, FLAG
  OR'd where a solution is invalid (`rang.cal_apply.apply_jones`).
- `to_store(...)`: the solutions as a QuartiCal gain store (one partition
  per scan, diagonal 2x2 gains), with `read_store` to read them back.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import cal_apply, cal_delay, cal_gain, core_ms
from .formats import quartical_store

TYPES = ("Sp", "Sa", "Sd")
QUARTICAL = {"Sp": "phase", "Sa": "diag_complex", "Sd": "delay_and_offset"}
CARACAL = {"Sp": "GainDiagPhase", "Sa": "GainDiag", "Sd": "Fslope"}

__all__ = [
    "SelfcalSolution",
    "apply",
    "freq_bins",
    "read_store",
    "solve",
    "time_bins",
    "to_store",
]


def _interval(solint):
    """('n', N) for N integrations (an int; 'int' is N = 1; 'inf' N = 0, the
    scan) or ('seconds', text) for CASA's seconds bins."""
    if isinstance(solint, bool):
        raise TypeError(f"solint {solint!r}")
    if isinstance(solint, (int, np.integer)):
        if solint < 1:
            raise ValueError("solint must be at least one integration")
        return "n", int(solint)
    text = str(solint).strip().lower()
    if text == "inf":
        return "n", 0
    if text == "int":
        return "n", 1
    if text.isdigit():
        return _interval(int(text))
    cal_gain.parse_solint(text)  # raises on nonsense
    return "seconds", text


def time_bins(time, scan, field_id, solint):
    """Solution intervals of rows (`time`, `scan`, `field_id` per row):
    `(time_bin per row, scan per bin, gain_time per bin)`, bins numbered in
    time order. `gain_time` is the mean of each bin's integration times
    (QuartiCal's grid, `core_pipeline.solution_grid`)."""
    time = np.asarray(time, np.float64)
    scan = np.asarray(scan)
    kind, value = _interval(solint)
    if kind == "seconds":
        fields = np.broadcast_to(np.asarray(field_id), time.shape)
        raw, _ = cal_gain.solint_bins(time, scan, fields, value, "")
        raw = np.asarray(raw, np.int64)
        first = np.array([time[raw == b].min() for b in range(raw.max() + 1)])
        order = np.argsort(first, kind="stable")
        renumber = np.empty_like(order)
        renumber[order] = np.arange(len(order))
        tb = renumber[raw]
    else:
        tb = np.empty(len(time), np.int64)
        offset = 0
        scans = sorted(np.unique(scan), key=lambda s: time[scan == s].min())
        for s in scans:
            rows = scan == s
            unique, inverse = np.unique(time[rows], return_inverse=True)
            step = len(unique) if value == 0 else value
            local = inverse.reshape(-1) // step
            tb[rows] = local + offset
            offset += int(local.max()) + 1
    nbin = int(tb.max()) + 1
    bin_scan = np.empty(nbin, np.int64)
    gain_time = np.empty(nbin)
    for b in range(nbin):
        rows = tb == b
        values = np.unique(scan[rows])
        if len(values) != 1:  # pragma: no cover - combine is not offered
            raise ValueError(f"solution interval {b} crosses scans {values.tolist()}")
        bin_scan[b] = values[0]
        gain_time[b] = np.unique(time[rows]).mean()
    return tb, bin_scan, gain_time


def freq_bins(chan_freq, freqint):
    """`(freq_bin per channel, gain_freq per bin)` for `freqint` `inf` or N
    channels (the mean frequency of each chunk)."""
    chan_freq = np.asarray(chan_freq, np.float64)
    nchan = len(chan_freq)
    if freqint in ("inf", None, 0):
        step = nchan
    elif freqint == "int":
        step = 1
    else:
        step = int(freqint)
        if step < 1:
            raise ValueError("freqint must be at least one channel")
    fb = np.arange(nchan) // step
    gain_freq = np.array([chan_freq[fb == b].mean() for b in range(fb.max() + 1)])
    return fb, gain_freq


@dataclass
class SelfcalSolution:
    """One self-calibration term on one field: diagonal gains `(time bin,
    freq bin, antenna, hand)` and their flags, the row and channel maps
    (`rows` are MS row numbers, `time_bin` per row, `freq_bin` per
    channel), the grid, and for Sd the delays (ns) and offsets (rad)."""

    name: str
    type: str
    gains: np.ndarray
    flags: np.ndarray
    rows: np.ndarray
    time_bin: np.ndarray
    freq_bin: np.ndarray
    bin_scan: np.ndarray
    gain_time: np.ndarray
    gain_freq: np.ndarray
    field_id: int
    iterations: int
    converged_fraction: float
    clipped: int
    delays: np.ndarray | None = None
    offsets: np.ndarray | None = None
    settings: dict = field(default_factory=dict)

    def valid(self):
        """(time bin, freq bin, antenna): both hands unflagged and finite."""
        return ~self.flags.any(-1) & np.isfinite(self.gains).all(-1)

    def gains_2x2(self):
        """`(time bin, freq bin, antenna, 2, 2)` diagonal gains; an invalid
        antenna gets the identity."""
        nt, nf, na, _ = self.gains.shape
        out = np.zeros((nt, nf, na, 2, 2), np.complex128)
        good = self.valid()
        g = np.where(good[..., None], self.gains, 1.0)
        out[..., 0, 0] = g[..., 0]
        out[..., 1, 1] = g[..., 1]
        return out

    def summary(self):
        """The scalar facts of the solve (for a stage summary)."""
        bins = {
            int(s): int((self.bin_scan == s).sum()) for s in np.unique(self.bin_scan)
        }
        return {
            "name": self.name,
            "type": self.type,
            "quartical_type": QUARTICAL[self.type],
            "caracal_type": CARACAL[self.type],
            "field_id": int(self.field_id),
            "rows": len(self.rows),
            "time_bins": int(self.gains.shape[0]),
            "time_bins_per_scan": bins,
            "freq_bins": int(self.gains.shape[1]),
            "iterations": int(self.iterations),
            "converged_fraction": float(self.converged_fraction),
            "flagged_fraction": float(self.flags.any(-1).mean()),
            "clipped": int(self.clipped),
            "settings": dict(self.settings),
        }


def _clip(gains, flags, gain_clip):
    """CARACal's `g-clip-low`/`g-clip-high`: solutions whose amplitude lies
    outside `gain_clip` (low, high) are flagged; returns (flags, count)."""
    flags = np.array(flags, bool)
    if not gain_clip:
        return flags, 0
    lo, hi = (float(v) for v in gain_clip)
    amp = np.abs(gains)
    bad = ~flags & ((amp < lo) | (amp > hi) | ~np.isfinite(gains))
    return flags | bad, int(bad.sum())


def _window(ms):
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        chan_freq = t.getcol("CHAN_FREQ")
    if len(chan_freq) != 1:
        raise ValueError("self-calibration needs a single-window MS (task W4)")
    return np.asarray(chan_freq[0], np.float64)


def solve(
    ms,
    term,
    *,
    rows,
    field_id,
    input_column="CORRECTED_1GC",
    model_column="MODEL_DATA",
    weight_column="WEIGHT_SPECTRUM",
    refant=0,
    minuvw_m=0.0,
    gain_clip=(0.5, 2.0),
    budget=None,
):
    """Solve self-calibration `term` (a dict with `type` Sp, Sa or Sd,
    `name`, `solint`, and for Sp and Sa `freqint`; `max_iterations`,
    `stop_criterion`, `stop_fraction`) on MS `rows` (one field), the
    `input_column` against `model_column`. `weight_column` None solves with
    unit weights (`data.weights: uniform`). Returns a `SelfcalSolution`."""
    kind = term["type"]
    if kind not in TYPES:
        raise ValueError(f"self-calibration term type must be one of {TYPES}")
    ms = Path(ms)
    rows = np.asarray(rows, np.int64)
    if not len(rows):
        raise ValueError(f"no rows of field {field_id} to self-calibrate")
    with core_ms.open_table(ms / "ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
    nant = len(names)
    refant = names.index(refant) if isinstance(refant, str) else int(refant)
    if not 0 <= refant < nant:
        raise ValueError(f"refant {refant} out of range")
    freq = _window(ms)
    uvrange = f">{float(minuvw_m):g}" if minuvw_m and minuvw_m > 0 else ""
    fld = cal_gain._Field(
        ms, rows, data_column=input_column, model=None, model_column=model_column,
        weight_column=weight_column, sigma_column="SIGMA", tables=[], interp=[],
        nant=nant, field_id=field_id, solved="G", freq=freq, uvrange=uvrange,
    )  # fmt: skip
    m = fld.meta
    tb, bin_scan, gain_time = time_bins(
        m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], term["solint"]
    )
    solver = {
        "max_iterations": int(term.get("max_iterations", 50)),
        "stop_criterion": float(term.get("stop_criterion", 1e-7)),
        "stop_fraction": float(term.get("stop_fraction", 0.99)),
    }
    what = f"selfcal {term.get('name', kind)} field {field_id}"
    delays = offsets = None
    if kind in ("Sp", "Sa"):
        fb, gain_freq = freq_bins(freq, term.get("freqint", "inf"))
        sol, _ = cal_gain._solve_gain_field(
            fld, tb, nchan=len(freq), per_channel=False, budget=budget, what=what,
            freq_bin=fb if fb.max() > 0 else None, nant=nant,
            calmode="p" if kind == "Sp" else "ap", refant=[refant], refantmode="flex",
            minsnr=0.0, minblperant=0, positions=None, casa_rules=False, **solver,
        )  # fmt: skip
        gains, flags = sol.gains, sol.flags
        iterations, fraction = sol.iterations, sol.converged_fraction
    else:
        fb, gain_freq = np.arange(len(freq)), freq.copy()
        sol, _ = cal_delay._solve_field(
            fld, tb, budget=budget, what=what, nant=nant, chan_freq=freq,
            refant=[refant], casa_rules=False, initial_estimate=False,
            return_gains=True, kind="delay_and_offset", offset_start=True, **solver,
        )  # fmt: skip
        gains = sol.gains
        flags = sol.gain_flags[..., None] | sol.flags  # (t, chan, ant, 2)
        flags = np.broadcast_to(flags, gains.shape).copy()
        delays, offsets = sol.delays, sol.offsets
        iterations, fraction = sol.iterations, sol.converged_fraction
    flags, clipped = _clip(gains, flags, gain_clip)
    return SelfcalSolution(
        name=str(term.get("name") or kind),
        type=kind,
        gains=np.asarray(gains, np.complex128),
        flags=flags,
        rows=rows,
        time_bin=tb,
        freq_bin=np.asarray(fb, np.int64),
        bin_scan=bin_scan,
        gain_time=gain_time,
        gain_freq=np.asarray(gain_freq, np.float64),
        field_id=int(field_id),
        iterations=int(iterations),
        converged_fraction=float(fraction),
        clipped=clipped,
        delays=delays,
        offsets=offsets,
        settings={
            "solint": term["solint"],
            "freqint": term.get("freqint", "inf") if kind != "Sd" else "per channel",
            "refant": refant,
            "refant_name": names[refant],
            "input_column": input_column,
            "model_column": model_column,
            "weights": weight_column or "unit",
            "uvrange": uvrange,
            "gain_clip": list(gain_clip) if gain_clip else None,
            "casa_rules": False,
            **solver,
        },
    )


def apply(w, sol, *, input_column, output_column, chunk_rows=None, threads=0):
    """Correct `input_column` of the solution's rows by `sol` on its own
    bins into `output_column` of WriteBack session `w`
    (`S_p^-1 V S_q^-H`), FLAG OR'd where a gain is invalid (all four
    correlations, `rang.cal_apply.apply_jones`). Other rows keep their
    values. Returns counts of cells and flags."""
    w.ensure_column(output_column, init="data")
    nrows = w.layout["nrows"]
    row_bin = np.full(nrows, -1, np.int64)
    row_bin[sol.rows] = sol.time_bin
    gains = sol.gains_2x2()
    valid = sol.valid()
    fb = sol.freq_bin
    flagged_before = flagged_after = cells = 0
    for start, n in w.chunks(chunk_rows):
        rb = row_bin[start : start + n]
        sel = np.flatnonzero(rb >= 0)
        if not len(sel):
            continue
        data = w.read(input_column, start, n)
        flag = np.asarray(w.read("FLAG", start, n), bool)
        out = np.array(w.read(output_column, start, n))
        a1 = w.read("ANTENNA1", start, n)
        a2 = w.read("ANTENNA2", start, n)
        got, gflag = cal_apply.apply_jones(
            data[sel], flag[sel], a1[sel], a2[sel], gains, valid, rb[sel], fb,
            threads=threads,
        )  # fmt: skip
        out[sel] = got
        new = flag.copy()
        new[sel] = gflag | flag[sel]
        flagged_before += int(flag[sel].sum())
        flagged_after += int(new[sel].sum())
        cells += int(np.prod(got.shape))
        w.write(output_column, start, out)
        w.write_flags(start, new)
    return {
        "input_column": input_column,
        "output_column": output_column,
        "rows": len(sol.rows),
        "cells": cells,
        "cells_flagged_before": flagged_before,
        "cells_flagged_after": flagged_after,
    }


def to_store(sol, path, antennas, field_name="", ddid=0):
    """Write `sol` as a QuartiCal gain store at `path` (term `sol.name`, one
    `complex`-type partition per scan holding the diagonal 2x2 gains on its
    bins, attribute `rang_selfcal_type` the rang type); for Sd also
    `<path>.delays.npz` (delays in ns and offsets in rad per bin, antenna,
    hand). Returns the path."""
    path = Path(path)
    gains = sol.gains_2x2()
    raw = np.zeros_like(gains)
    raw[..., 0, 0] = sol.gains[..., 0]
    raw[..., 1, 1] = sol.gains[..., 1]
    parts = []
    for scan in np.unique(sol.bin_scan):
        k = np.flatnonzero(sol.bin_scan == scan)
        part = quartical_store.complex_partition(
            raw[k][:, :, :, None],
            sol.flags[k].any(-1)[:, :, :, None].astype(np.int8),
            sol.gain_time[k],
            sol.gain_freq,
            antennas,
            name=sol.name,
            field_id=sol.field_id,
            field_name=field_name,
            scan=int(scan),
            ddid=ddid,
        )
        part.attrs["rang_selfcal_type"] = sol.type
        parts.append(part)
    quartical_store.write({sol.name: parts}, path)
    if sol.delays is not None:
        np.savez(
            path.with_name(path.name + ".delays.npz"),
            delays_ns=sol.delays,
            offsets_rad=sol.offsets,
            gain_time=sol.gain_time,
            bin_scan=sol.bin_scan,
        )
    return path


def read_store(path, name):
    """The gains of term `name` in a store written by `to_store`: `(gains
    (time, freq, antenna, hand), flags (time, freq, antenna), gain_time,
    gain_freq, scan per bin)`, bins in time order."""
    parts = quartical_store.read_term(Path(path), name)
    parts.sort(key=lambda p: float(np.asarray(p["gain_time"])[0]))
    g, f, t, s = [], [], [], []
    for p in parts:
        full = p.gains_2x2()[:, :, :, 0]
        g.append(np.stack([full[..., 0, 0], full[..., 1, 1]], -1))
        f.append(np.asarray(p["gain_flags"])[:, :, :, 0] != 0)
        times = np.asarray(p["gain_time"], float)
        t.append(times)
        s.append(np.full(len(times), int(p.attrs["SCAN_NUMBER"])))
    gain_freq = np.asarray(parts[0]["gain_freq"], float)
    return (
        np.concatenate(g),
        np.concatenate(f),
        np.concatenate(t),
        gain_freq,
        np.concatenate(s),
    )
