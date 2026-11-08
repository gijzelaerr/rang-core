"""The delay term K in the Rust core, with its FFT initial estimate (the
owner's estimator: FFT, then Gauss-Newton) and CASA's
`gaincal(gaintype='K')` conventions (task C2b, research/c2b-delay.md; C1
step 4, research/c1-calibration-chain.md).

The term's form, `kind` (task C2c, research/c2c-bandpass.md part 1): by
default QuartiCal 0.2.7's `delay_and_offset` (a delay and a free phase per
antenna and hand, `core/src/cal/delay_offset.rs`), the coordinator's
provisional K model since CARACal solves K before any G; `kind="delay"` is C2b's
QuartiCal `delay` (`core/src/cal/delay.rs`), which matches CASA only with a
G pre-applied (C2b section 6). The K table holds the delays only; the
offsets are returned in `DelaySolution.offsets` and G, solved next, absorbs
them.

Layers, each usable alone:

- `solve(...)`: one term on arrays.
  With `casa_rules=True` (the default) the delays are referenced as CASA's
  `KJones` does: per interval and hand to the first refant (`tau_p -
  tau_r`), an antenna without an unflagged cell on a baseline to the refant
  flagged, the refant itself unflagged at 0; no `minsnr`, `minblperant`,
  flex or strict (CASA's K applies none of them). With `casa_rules=False`
  the kernel is QuartiCal's alone, referenced as QuartiCal references it.
- `gaincal(...)`: the Measurement Set route, as CASA `gaincal(gaintype='K')`:
  the field, `solint` and `combine` through `rang.cal_gain.solint_bins`,
  earlier tables pre-applied through `rang.cal_apply` (lower VisCal types
  correct the data, equal or higher types corrupt the model), SIGMA weights
  when tables are pre-applied (as `rang.cal_gain`); returns a
  `formats.caltable.CalTable` (`K Jones`, delays in ns) that
  `caltable.write` writes and `rang.cal_apply` applies.

Not here: KCROSS (`rang.cal_pol.kcross`, task C6), several windows or fields in one call,
`combine='spw'`, and CASA's FFT-only estimator.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import cal_gain, core_ms
from .formats import caltable

KINDS = ("delay_and_offset", "delay")


@dataclass
class DelaySolution:
    """One solved delay term over (interval, frequency bin, antenna, hand);
    delays and errors in ns, offsets (`delay_and_offset`; zeros for
    `delay`) in radians."""

    delays: np.ndarray
    flags: np.ndarray
    err: np.ndarray
    iterations: int
    converged_fraction: float
    refant_used: np.ndarray
    kernel_flags: np.ndarray
    gain_flags: np.ndarray
    gains: np.ndarray | None = None
    settings: dict = field(default_factory=dict)
    offsets: np.ndarray | None = None


def _cell_flags(data, weights, flag, flag_row):
    """The kernel's data flags per cell (`solve::data_flags`): any flagged
    correlation, a flagged row, a zero parallel-hand datum or weight."""
    missing = (data[..., (0, 3)] == 0).any(-1)
    no_weight = (weights[..., (0, 3)] == 0).any(-1)
    return flag.any(-1) | flag_row[:, None] | missing | no_weight


def solve(
    data,
    model,
    weights,
    flag,
    flag_row,
    antenna1,
    antenna2,
    time_bin,
    *,
    nant,
    chan_freq,
    freq_bin=None,
    refant=0,
    casa_rules=True,
    initial_estimate=True,
    return_gains=False,
    max_iterations=50,
    stop_criterion=1e-7,
    stop_fraction=0.99,
    kind="delay_and_offset",
    offset_start=True,
    trace=False,
):
    """Solve one delay term on arrays (rows, chans, 4 correlations).

    `chan_freq` holds the channel frequencies (Hz), `time_bin` maps rows to
    intervals (`cal_gain.solint_bins`), `freq_bin` channels to delay bins
    (default one per window). `refant` is an index or a list; K uses the
    first. `kind` is `delay_and_offset` (default) or `delay`.
    `offset_start` (`delay_and_offset` with the initial estimate only;
    post hoc, research/c2c-bandpass.md section 6): start the offsets at the
    phase of the FFT peak derotated by the estimated delay, not at 0
    (QuartiCal's start, which on large antenna phases can walk to the delay
    response's first sidelobe, 1.43 / bandwidth away); `False` is
    QuartiCal's estimator exactly. Autocorrelations are not used. `trace`
    (task W3b, `rang.cal_chunks.replayed`): return only `(counts, error,
    ngains)` of the counted kernel."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    refants = [int(r) for r in np.atleast_1d(refant)]
    if not refants or any(r < 0 or r >= nant for r in refants):
        raise ValueError("refant out of range")
    r0 = refants[0]
    data = np.ascontiguousarray(data, np.complex64)
    nrow, nchan = data.shape[:2]
    freq = np.ascontiguousarray(chan_freq, np.float64)
    if freq.shape != (nchan,):
        raise ValueError("chan_freq must hold one frequency per channel")
    model = np.ascontiguousarray(np.broadcast_to(model, data.shape), np.complex64)
    weights = np.ascontiguousarray(np.broadcast_to(weights, data.shape), np.float32)
    flag = np.ascontiguousarray(np.broadcast_to(flag, data.shape), np.uint8)
    a1 = np.ascontiguousarray(antenna1, np.uint32)
    a2 = np.ascontiguousarray(antenna2, np.uint32)
    flag_row = np.asarray(flag_row, bool) | (a1 == a2)
    time_bin = np.asarray(time_bin, np.int64)
    freq_bin = (
        np.zeros(nchan, np.int64)
        if freq_bin is None
        else np.asarray(freq_bin, np.int64)
    )
    ntime, nfreq = int(time_bin.max()) + 1, int(freq_bin.max()) + 1
    order = np.argsort(time_bin, kind="stable")

    def sorted_rows(x):
        return np.ascontiguousarray(x[order])

    data, model, weights, flag = (sorted_rows(x) for x in (data, model, weights, flag))
    a1, a2, flag_row, tb = (sorted_rows(x) for x in (a1, a2, flag_row, time_bin))
    fb = np.ascontiguousarray(freq_bin, np.uint32)
    nparam = ntime * nfreq * nant
    ngain = ntime * nchan * nant
    delays = np.zeros(2 * nparam, np.float64)
    pflags = np.zeros(nparam, np.int8)
    err = np.zeros(2 * nparam, np.float64)
    gflags = np.zeros(ngain, np.int8)
    gains = np.zeros(4 * ngain if return_gains else 0, np.float64)
    offsets = np.zeros(2 * nparam, np.float64)
    from rang import core

    ext = core.extension()
    common = (
        nrow, nchan, ntime, nfreq, int(nant), cal_gain._floats(data), weights,
        cal_gain._floats(model), flag, flag_row.astype(np.uint8), a1, a2,
        tb.astype(np.uint32), fb, freq, int(max_iterations), float(stop_criterion),
        float(stop_fraction), -1 if casa_rules else r0, r0 if initial_estimate else -1,
    )  # fmt: skip
    if trace:  # task W3b: the counts of the stop test only
        counts = np.zeros(2 * max(int(max_iterations), 1), np.uint64)
        if kind == "delay":
            n, error = ext.cal_delay_trace(*common, counts)
        else:
            n, error = ext.cal_delay_offset_trace(*common, bool(offset_start), counts)
        return counts[: 2 * n].reshape(-1, 2), error, ngain
    if kind == "delay":
        iterations, fraction = ext.cal_delay_solve(
            *common, delays, pflags, err, gflags, gains
        )
    else:
        iterations, fraction = ext.cal_delay_offset_solve(
            *common, bool(offset_start), delays, offsets, pflags, err, gflags, gains
        )
    shape = (ntime, nfreq, nant)
    tau = delays.reshape(*shape, 2) * 1e9
    phi = offsets.reshape(*shape, 2)
    kernel_flags = pflags.reshape(shape) != 0
    flags = np.repeat(kernel_flags[..., None], 2, axis=-1)
    err = err.reshape(*shape, 2) * 1e9
    if casa_rules:
        # CASA's KJones: an antenna needs an unflagged cell on its baseline to
        # the refant; delays referenced to the refant, which is unflagged at 0.
        cells = ~_cell_flags(data, weights, flag.astype(bool), flag_row)
        to_ref = ((a1 == r0) | (a2 == r0)) & (a1 != a2)
        other = np.where(a1 == r0, a2, a1).astype(np.int64)
        linked = np.zeros(shape, bool)
        for f in range(nfreq):
            rows = to_ref & cells[:, fb == f].any(1)
            linked[tb[rows].astype(np.int64), f, other[rows]] = True
        ref_ok = ~flags[:, :, r0, :]
        flags |= ~linked[..., None]
        tau = np.where(ref_ok[:, :, None, :], tau - tau[:, :, r0 : r0 + 1, :], tau)
        phi = np.where(ref_ok[:, :, None, :], phi - phi[:, :, r0 : r0 + 1, :], phi)
        flags |= ~ref_ok[:, :, None, :]
        flags[:, :, r0, :] = False
        tau[:, :, r0, :] = 0.0
        phi[:, :, r0, :] = 0.0
        tau[flags] = 0.0
        phi[flags] = 0.0
        err[flags] = 0.0
    out_gains = None
    if return_gains:
        out_gains = gains.view(np.complex128).reshape(ntime, nchan, nant, 2)
    return DelaySolution(
        delays=tau,
        flags=flags,
        err=err,
        iterations=int(iterations),
        converged_fraction=float(fraction),
        refant_used=np.full(ntime, r0, np.int32),
        kernel_flags=kernel_flags,
        gain_flags=gflags.reshape(ntime, nchan, nant) != 0,
        gains=out_gains,
        offsets=phi,
        settings={
            "kind": kind,
            "offset_start": bool(offset_start) and kind == "delay_and_offset",
            "refant": refants,
            "casa_rules": bool(casa_rules),
            "initial_estimate": bool(initial_estimate),
            "max_iterations": int(max_iterations),
            "stop_criterion": float(stop_criterion),
            "stop_fraction": float(stop_fraction),
        },
    )


def gaincal(
    ms,
    *,
    field_id=0,
    solint="inf",
    combine="",
    refant=0,
    refantmode="flex",
    minsnr=3.0,
    minblperant=4,
    uvrange="",
    gaintable=(),
    interp="linear",
    data_column="DATA",
    model_column="MODEL_DATA",
    model=None,
    weight_column="WEIGHT_SPECTRUM",
    casa_rules=True,
    initial_estimate=True,
    max_iterations=50,
    stop_criterion=1e-7,
    stop_fraction=0.99,
    kind="delay_and_offset",
    offset_start=True,
    scan=None,
    budget=None,
):
    """`gaincal(gaintype='K')` on one field of a single-window MS: returns
    `(CalTable, DelaySolution, info)`; `kind` and `offset_start` as `solve`, recorded in
    `sol.settings`, with the offsets left out of the table (G absorbs them).
    `refant` is an antenna index or name
    (or a list, of which K uses the first); `refantmode`, `minsnr` and
    `minblperant` are accepted and not applied, as CASA's K does not apply
    them. `gaintable` CalTables or paths; `model` an array `(row, chan, 4)`
    for the field's rows instead of `model_column`. With tables to
    pre-apply the solve uses SIGMA weights (as `rang.cal_gain.gaincal`),
    otherwise `weight_column`. Raises when no solution is written.
    `weight_column=None` and `scan` as `rang.cal_gain.gaincal` (task C2e),
    and `budget` (task W3b): chunks of whole intervals, the same result."""
    ms = Path(ms)
    with core_ms.open_table(ms / "ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        chan_freq = t.getcol("CHAN_FREQ")
    if len(chan_freq) != 1:
        raise ValueError(
            "one spectral window only (several are refused by rang-core, task W4)"
        )
    freq = np.asarray(chan_freq[0], float)
    nant = len(names)
    refants = [
        names.index(r) if isinstance(r, str) else int(r) for r in np.atleast_1d(refant)
    ]
    with core_ms.open_table(ms) as t:
        fields = t.getcol("FIELD_ID")
        colnames = t.colnames()
    rows = np.flatnonzero(cal_gain._scan_keep(ms, scan, fields == field_id))
    if not len(rows):
        raise ValueError(f"no rows of field {field_id}")
    sigma_column = "SIGMA_SPECTRUM" if "SIGMA_SPECTRUM" in colnames else "SIGMA"
    tables = [
        t if isinstance(t, caltable.CalTable) else caltable.read(t) for t in gaintable
    ]
    fld = cal_gain._Field(
        ms, rows, data_column=data_column, model=model, model_column=model_column,
        weight_column=weight_column, sigma_column=sigma_column, tables=tables,
        interp=interp, nant=nant, field_id=field_id, solved="K", freq=freq,
        uvrange=uvrange,
    )  # fmt: skip
    m = fld.meta
    tb, keys = cal_gain.solint_bins(
        m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], solint, combine
    )
    sol, row_w = _solve_field(
        fld, tb, budget=budget, what=f"gaincal K field {field_id}", nant=nant,
        chan_freq=freq, refant=refants, casa_rules=casa_rules,
        initial_estimate=initial_estimate, max_iterations=max_iterations,
        stop_criterion=stop_criterion, stop_fraction=stop_fraction, kind=kind,
        offset_start=offset_start,
    )  # fmt: skip
    sol.settings.update(
        {
            "refantmode": refantmode,
            "minsnr": float(minsnr),
            "minblperant": int(minblperant),
            "applied_casa_k_rules_only": True,
            "weights": sigma_column if tables else weight_column,
        }
    )
    if sol.flags.all():
        raise RuntimeError(
            f"gaincal K wrote no solutions for field {field_id} (every delay flagged)"
        )
    times, _ = fld.solution_times(tb, row_w, len(keys))
    scans = fld.scans(tb, len(keys))
    table = to_caltable(sol, times, scans, field_id=field_id, ms=ms)
    info = {"rows": len(rows), "intervals": keys, "time_bin": tb, "frequency": freq}
    return table, sol, info


_PER_INTERVAL = ("delays", "flags", "err", "kernel_flags", "gain_flags", "gains", "offsets",
                 "refant_used")  # fmt: skip


def _solve_field(fld, tb, *, budget, what, **opts):
    """`solve` on the rows of `fld` (`rang.cal_gain._Field`) in chunks of
    whole intervals under `budget` (task W3b; None: one call), the stop test
    replayed (`rang.cal_chunks.replayed`); K's referencing is per interval,
    so every chunk is a whole `solve`. Returns `(DelaySolution, row
    weights)`."""
    from . import cal_chunks

    nchan = len(opts["chan_freq"])
    chunks, block = cal_chunks.plan(tb, nchan, 4, budget, per_channel=False, what=what)
    row_w = np.zeros(len(tb))
    m = fld.meta
    with core_ms.open_table(fld.ms) as reader:

        def run(chunk, max_iterations, stop_fraction, trace):
            arr = cal_chunks.load(
                reader, fld.rows, chunk, fld.cells, fld.prepare, block
            )
            pos = chunk.pos
            if not trace:
                row_w[pos] = arr.pop("row_w")
            kw = dict(opts, max_iterations=max_iterations, stop_fraction=stop_fraction)
            return solve(
                arr["data"], arr["model"], arr["weights"], arr["flag"],
                fld.flag_row[pos], m["ANTENNA1"][pos], m["ANTENNA2"][pos],
                tb[pos] - chunk.t0, trace=trace, **kw,
            )  # fmt: skip

        results, replay = cal_chunks.replayed(
            chunks,
            run,
            max_iterations=opts["max_iterations"],
            stop_fraction=opts["stop_fraction"],
        )
    sol = results[0]
    if replay is not None:
        for key in _PER_INTERVAL:
            parts = [getattr(r, key) for r in results]
            if parts[0] is not None:
                setattr(sol, key, np.concatenate(parts, axis=0))
        sol.iterations, sol.converged_fraction = replay
        sol.settings["max_iterations"] = int(opts["max_iterations"])
        sol.settings["stop_fraction"] = float(opts["stop_fraction"])
    return sol, row_w


def to_caltable(sol, times, scans, *, field_id, ms, spw=0):
    """The CASA `K Jones` table of `sol` (one delay bin): one row per
    (interval, antenna), `FPARAM (1, 2)` float32 ns, the window one channel
    at the mean frequency, `ANTENNA2 = -1`, `INTERVAL 0` and `SNR 0` as
    CASA writes them, rang's delay error in `PARAMERR`."""
    if sol.delays.shape[1] != 1:
        raise ValueError("a K table has one delay per window")
    ntime, _, nant, _ = sol.delays.shape
    subtables = caltable.subtables_from_ms(ms, single_channel=True)
    n = ntime * nant
    t_idx = np.repeat(np.arange(ntime), nant)
    a_idx = np.tile(np.arange(nant), ntime)
    main = {
        "TIME": [float(times[t]) for t in t_idx],
        "FIELD_ID": [int(field_id)] * n,
        "SPECTRAL_WINDOW_ID": [int(spw)] * n,
        "ANTENNA1": [int(a) for a in a_idx],
        "ANTENNA2": [-1] * n,
        "INTERVAL": [0.0] * n,
        "SCAN_NUMBER": [int(scans[t]) for t in t_idx],
        "OBSERVATION_ID": [0] * n,
        "FPARAM": [
            sol.delays[t, 0, a].astype(np.float32).reshape(1, 2)
            for t, a in zip(t_idx, a_idx)
        ],
        "PARAMERR": [
            sol.err[t, 0, a].astype(np.float32).reshape(1, 2)
            for t, a in zip(t_idx, a_idx)
        ],
        "FLAG": [sol.flags[t, 0, a].reshape(1, 2) for t, a in zip(t_idx, a_idx)],
        "SNR": [np.zeros((1, 2), np.float32)] * n,
        "WEIGHT": [None] * n,
    }
    keywords = {
        "ParType": "Float",
        "MSName": str(Path(ms).name),
        "VisCal": "K Jones",
        "PolBasis": "unknown",
        "CASA_Version": "6.7.6-14",
    }
    return caltable.CalTable(
        "K Jones", main, subtables, keywords, ["Calibration", "K Jones", ""]
    )


__all__ = ["DelaySolution", "gaincal", "solve", "to_caltable"]
