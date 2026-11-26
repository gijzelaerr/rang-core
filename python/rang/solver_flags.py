# SPDX-License-Identifier: MIT
"""Residual flags at the gain solve, `calibrate.solver_flags` (issue #58,
research/solver-flags.md section 3.1).

After a G or B term has solved on a field, `flag_pass(fld, tb, sol, cfg,
write)` forms the residual `d - g_p m g_q^*` on the field's unaveraged
cells, in the frame of the solve (`rang.cal_gain._Field.prepare`: data with
the lower types corrected, model with the higher types corrupted), and per
solution interval (one statistics chunk: the interval's rows times every
channel) runs `rang._core.flag_residual_solver`:

- `mode: quartical`: QuartiCal 0.2.7's `mad_flags` rule (diagonal
  correlations, unwhitened, `threshold_bl` = `sigma`, `threshold_global` =
  `global_sigma`, `max_deviation` 0);
- `mode: rang`: the antenna-factorised rule of `flag.residual`;

then `min_cells` and `guard` per baseline. Cells that take no part: flagged
in any correlation, FLAG_ROW, outside the solve's `uvrange`, an
autocorrelation, a zero or non-finite parallel hand of data or model, a zero
parallel-hand weight, or a flagged gain of either antenna. `write(rows, new)`
OR-s the new flags into FLAG (all correlations).

`rounds(...)` runs passes and re-solves: pass, write, re-solve, up to
`cfg["rounds"]` times or until a pass adds nothing, and checks the tripwire.
QuartiCal's own `mad_flags` is one pass after its solve, without a re-solve.
"""

import numpy as np

from . import core, core_chunks

# Field rows read per block for the residual (about 270 MB of cells at 1,024
# channels); results do not depend on it.
BLOCK_CELLS = 2**28 // 100
NOISE_BLOCK = 16  # the rang rule's channels per noise block (flag.residual)


class TripwireFired(RuntimeError):
    """A re-solve flagged more of a term's solutions than the tripwire allows."""


def _ext():
    return core.extension()


def settings(cfg):
    """The flag pass's settings from `calibrate.solver_flags`."""
    return {
        "quartical": cfg["mode"] == "quartical",
        "sigma": float(cfg["sigma"]),
        "global_sigma": float(cfg["global_sigma"]),
        "persist": float(cfg["persist"]),
        "block": NOISE_BLOCK,
        "guard": float(cfg["guard"]),
        "min_cells": int(cfg["min_cells"]),
    }


def selects(terms, kind, name):
    """True when `calibrate.solver_flags.terms` flags the term of type `kind`
    named `name`: G and B terms only, by type (G, B) or by name, such as
    Gsec (research/solver-flags-2.md section 3)."""
    return kind in ("G", "B") and (kind in terms or name in terms)


def _freq_bins(sol, nchan):
    nfreq = sol.gains.shape[1]
    if nfreq == 1:
        return np.zeros(nchan, np.uint32)
    if nfreq == nchan:
        return np.arange(nchan, dtype=np.uint32)
    raise ValueError(f"solver_flags: {nfreq} frequency bins over {nchan} channels")


def _excluded(arr, fld, pos):
    """(row, chan) cells that take no part in the statistics."""
    flag = np.asarray(arr["flag"], bool).any(-1)
    flag |= (fld.flag_row[pos] | fld.auto[pos])[:, None]
    for key in ("data", "model"):
        v = np.asarray(arr[key])[..., (0, 3)]
        flag |= ~np.isfinite(v).all(-1) | (v == 0).any(-1)
    w = np.asarray(arr["weights"])[..., (0, 3)]
    flag |= (w == 0).any(-1)
    return flag


def _interval_residual(reader, fld, pos, sol, t, fb, block_rows):
    """The residual `(n, nchan, 2)` complex64 and the excluded cells of the
    field rows `pos` (one interval `t`)."""
    nant = fld.nant
    gains = np.ascontiguousarray(sol.gains[t : t + 1], np.complex128)
    gflags = np.ascontiguousarray(sol.flags[t : t + 1], np.uint8)
    nfreq = gains.shape[1]
    res_parts, flag_parts = [], []
    divided = fld.model_divided
    fld.model_divided = False  # the residual of the undivided data
    try:
        for s in range(0, len(pos), block_rows):
            p = pos[s : s + block_rows]
            cols = {n: core_chunks.read_rows(reader, n, fld.rows[p]) for n in fld.cells}
            arr = fld.prepare(p, cols)
            del cols
            data = np.ascontiguousarray(arr["data"], np.complex64)
            nrow, nchan = data.shape[:2]
            model = np.ascontiguousarray(
                np.broadcast_to(arr["model"], data.shape), np.complex64
            )
            res, bad = _ext().flag_residual_diag(
                data.view(np.float32).reshape(-1),
                model.view(np.float32).reshape(-1),
                nrow,
                nchan,
                np.ascontiguousarray(fld.meta["ANTENNA1"][p], np.uint32),
                np.ascontiguousarray(fld.meta["ANTENNA2"][p], np.uint32),
                np.zeros(nrow, np.uint32),
                fb,
                gains.reshape(-1).view(np.float64),
                gflags.reshape(-1),
                1,
                nfreq,
                nant,
            )
            res_parts.append(res.view(np.complex64).reshape(nrow, nchan, 2))
            flag_parts.append(
                _excluded(arr, fld, p) | bad.reshape(nrow, nchan).astype(bool)
            )
            del arr, data, model
    finally:
        fld.model_divided = divided
    return np.concatenate(res_parts), np.concatenate(flag_parts)


def flag_pass(fld, tb, sol, cfg, write=None):
    """One pass over every solution interval of `sol` on field `fld` (rows'
    interval index `tb`). `cfg` is `calibrate.solver_flags`; `write(rows, new)`
    (MS row indices, `(row, chan)` bool) is called per interval with flags to
    add, after the pass has read everything. Returns the pass's record:
    totals and the per-interval counts."""
    s = settings(cfg)
    nchan = len(fld.freq)
    fb = _freq_bins(sol, nchan)
    block_rows = max(1, BLOCK_CELLS // max(1, nchan * 4))
    tb = np.asarray(tb, np.int64)
    m = fld.meta
    intervals = []
    totals = {"cells": 0, "input_flagged": 0, "added": 0}
    pending = []
    from . import core_ms

    with core_ms.open_table(fld.ms) as reader:
        for t in range(sol.gains.shape[0]):
            pos = np.flatnonzero(tb == t)
            if not len(pos):
                continue
            res, excl = _interval_residual(reader, fld, pos, sol, t, fb, block_rows)
            _, dump = np.unique(m["TIME"][pos], return_inverse=True)
            new, counts = _ext().flag_residual_solver(
                np.ascontiguousarray(res).view(np.float32).reshape(-1),
                np.ascontiguousarray(excl, np.uint8).reshape(-1),
                len(pos),
                nchan,
                np.ascontiguousarray(m["ANTENNA1"][pos], np.uint32),
                np.ascontiguousarray(m["ANTENNA2"][pos], np.uint32),
                np.ascontiguousarray(dump, np.uint32),
                fld.nant,
                s["quartical"],
                s["sigma"],
                s["global_sigma"],
                s["persist"],
                s["block"],
                s["guard"],
                s["min_cells"],
            )
            del res
            new = new.reshape(len(pos), nchan).astype(bool)
            counts = {k: int(v) for k, v in counts.items()}
            if counts["added"]:
                pending.append((fld.rows[pos], new))
            intervals.append({"interval": int(t), **counts})
            for k in totals:
                totals[k] += counts[k]
    # Written after the reader is closed: a second table object in this
    # process would drop the writer's lock (`core_writeback.WriteBack.read`).
    if write is not None:
        for rows, new in pending:
            write(rows, new)
    return {**totals, "intervals": intervals}


def solution_flag_fraction(sol):
    return float(np.mean(sol.flags)) if sol.flags.size else 0.0


def rounds(fld, tb, sol, cfg, write, resolve):
    """Flag passes and re-solves on one field: `(sol, extra, record)`, the
    last solve's solution, whatever else `resolve()` returned with it, and
    the record. `resolve()` solves the term again on the MS's flags and
    returns `(solution, extra)`. Raises `TripwireFired` (after writing the
    record into the exception's `record`) when the solutions' flagged
    fraction rises by more than `cfg["tripwire"]`."""
    first = solution_flag_fraction(sol)
    passes, extra = [], None
    for _ in range(int(cfg["rounds"])):
        rec = flag_pass(fld, tb, sol, cfg, write)
        passes.append({k: v for k, v in rec.items()})
        if not rec["added"]:
            break
        sol, extra = resolve()
    last = solution_flag_fraction(sol)
    record = {
        "mode": cfg["mode"],
        "passes": passes,
        "added": int(sum(p["added"] for p in passes)),
        "solutions_flagged_first": first,
        "solutions_flagged_last": last,
        "resolved": sum(1 for p in passes if p["added"]),
    }
    if last - first > float(cfg["tripwire"]):
        err = TripwireFired(
            f"solver_flags: the flagged fraction of the solutions rose from "
            f"{first:.4f} to {last:.4f} (tripwire {cfg['tripwire']})"
        )
        err.record = record
        raise err
    return sol, extra, record


def or_writer(ms, *, flag_backup, stage, chunk_rows=None):
    """`write(rows, new)` that ORs `new` into FLAG through one
    `core_writeback.WriteBack` session per call, contiguous row runs at a
    time."""
    from . import core_writeback

    def write(rows, new):
        rows = np.asarray(rows, np.int64)
        order = np.argsort(rows, kind="stable")
        rows, new = rows[order], new[order]
        cuts = np.flatnonzero(np.diff(rows) != 1) + 1
        with core_writeback.WriteBack(
            ms, flag_backup=flag_backup, stage=stage, chunk_rows=chunk_rows
        ) as w:
            for r, n in zip(np.split(rows, cuts), np.split(new, cuts)):
                start = int(r[0])
                flag = w.read("FLAG", start, len(r))
                flag |= n[..., None]
                w.write_flags(start, flag)

    return write
