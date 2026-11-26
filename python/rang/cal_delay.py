# SPDX-License-Identifier: GPL-3.0-or-later
# Follows CASA's C++ source in part (Copyright (C) Associated
# Universities, Inc. Washington DC, USA; (L)GPL version 2 or later):
# notices in THIRD-PARTY-NOTICES.txt.
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

import warnings
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


def _interval_costs(gains, data, model, weights, cells, a1, a2, tb, dims):
    """Per interval: the sum of w |V - g_p M g_q^*|^2 over the unflagged
    parallel-hand cells (`cells`, row x chan), with the kernel's gains
    (interval, chan, antenna, hand); research/calchain-floor.md section 12."""
    ntime, _, nant, nchan = dims
    g = gains.view(np.complex128).reshape(ntime, nchan, nant, 2)
    cost = np.zeros(ntime)
    step = 2048
    for b in range(0, len(tb), step):
        s = slice(b, min(len(tb), b + step))
        t, p, q = (np.asarray(x[s], np.int64) for x in (tb, a1, a2))
        for h, c in ((0, 0), (1, 3)):
            pred = g[t, :, p, h] * model[s, :, c] * np.conj(g[t, :, q, h])
            r = np.abs(data[s, :, c] - pred) ** 2 * weights[s, :, c]
            np.add.at(cost, t, np.where(cells[s], r, 0.0).sum(1))
    return cost


def _direct(p, q, r, nant):
    """Every antenna on these live rows has a live row to `r` (issue #53:
    the case in which flex is CASA's rule, bit for bit)."""
    on = np.zeros(nant, bool)
    on[p] = True
    on[q] = True
    to = np.zeros(nant, bool)
    m = (p == r) | (q == r)
    to[np.where(p == r, q, p)[m]] = True
    on[r] = False
    return not (on & ~to).any()


def _connected(p, q, r, nant):
    """The antennas reachable from `r` over the live rows `(p, q)`, `r`
    excluded (issue #53)."""
    adj = [[] for _ in range(nant)]
    for a, b in zip(p.tolist(), q.tolist()):
        adj[a].append(b)
        adj[b].append(a)
    seen = np.zeros(nant, bool)
    seen[r] = True
    stack = [r]
    while stack:
        a = stack.pop()
        for b in adj[a]:
            if not seen[b]:
                seen[b] = True
                stack.append(b)
    seen[r] = False
    return seen


def _keep_better(fft, zero, data, model, weights, flag, flag_row, a1, a2, tb, dims):
    """`zero_start`: per interval the run (FFT start or zero start) with the
    lower residual; returns the merged run and the intervals taken from the
    zero start (ties keep the FFT start)."""
    ntime, nfreq, nant, nchan = dims
    cells = ~_cell_flags(data, weights, flag.astype(bool), flag_row)
    args = (data, model, weights, cells, a1, a2, tb, dims)
    better = _interval_costs(zero["gains"], *args) < _interval_costs(
        fft["gains"], *args
    )
    out = dict(fft)
    width = {"delays": 2 * nfreq * nant, "err": 2 * nfreq * nant, "offsets": 2 * nfreq * nant,
             "pflags": nfreq * nant, "gflags": nchan * nant, "gains": 4 * nchan * nant}  # fmt: skip
    for key, w in width.items():
        a = fft[key].reshape(ntime, w).copy()
        a[better] = zero[key].reshape(ntime, w)[better]
        out[key] = a.reshape(-1)
    return out, [int(i) for i in np.flatnonzero(better)]


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
    zero_start=False,
    refantmode="flex",
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
    ngains)` of the counted kernel. `zero_start` (with the initial estimate;
    research/calchain-floor.md section 12, post hoc): the kernel runs a
    second time from zero delays and offsets, and per interval the run with
    the lower weighted residual over the interval's unflagged parallel-hand
    cells is kept (the FFT start, on the refant baselines only, can land on
    a sidelobe in a sparsely sampled interval, from which Gauss-Newton
    converges to a wrong delay); `trace` counts the FFT run only. False:
    one run, as before. `refantmode` (issue #53, research/k-refant-53.md;
    with `casa_rules`): `"flex"`, per interval the reference is the first
    antenna of `refant` with unflagged data, else the antenna with the most
    unflagged cross cells, and an antenna is solved when it is connected to
    the reference through unflagged baselines (CASA's K uses the first refant
    and its direct baselines only); `"strict"`, CASA's rule exactly. Where the
    first refant has data and every antenna with data has an unflagged
    baseline to it, both give CASA's result bit for bit."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if refantmode not in ("flex", "strict"):
        raise ValueError("refantmode must be flex or strict")
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
    if nrow == 0 or nchan == 0:
        raise ValueError(f"no data to solve: {nrow} rows of {nchan} channels")
    data, model, weights, flag = cal_gain.finite_cells(data, model, weights, flag)
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
    zero_start = bool(zero_start) and bool(initial_estimate)
    want_gains = bool(return_gains) or zero_start
    from rang import core

    ext = core.extension()

    def kernel(estimate):
        common = (
            nrow, nchan, ntime, nfreq, int(nant), cal_gain._floats(data), weights,
            cal_gain._floats(model), flag, flag_row.astype(np.uint8), a1, a2,
            tb.astype(np.uint32), fb, freq, int(max_iterations), float(stop_criterion),
            float(stop_fraction), -1 if casa_rules else r0, r0 if estimate else -1,
        )  # fmt: skip
        if trace:  # task W3b: the counts of the stop test only
            counts = np.zeros(2 * max(int(max_iterations), 1), np.uint64)
            if kind == "delay":
                n, error = ext.cal_delay_trace(*common, counts)
            else:
                n, error = ext.cal_delay_offset_trace(
                    *common, bool(offset_start), counts
                )
            return counts[: 2 * n].reshape(-1, 2), error, ngain
        r = {
            "delays": np.zeros(2 * nparam, np.float64),
            "pflags": np.zeros(nparam, np.int8),
            "err": np.zeros(2 * nparam, np.float64),
            "gflags": np.zeros(ngain, np.int8),
            "gains": np.zeros(4 * ngain if want_gains else 0, np.float64),
            "offsets": np.zeros(2 * nparam, np.float64),
        }
        if kind == "delay":
            it, fr = ext.cal_delay_solve(
                *common, r["delays"], r["pflags"], r["err"], r["gflags"], r["gains"]
            )
        else:
            it, fr = ext.cal_delay_offset_solve(
                *common, bool(offset_start), r["delays"], r["offsets"], r["pflags"],
                r["err"], r["gflags"], r["gains"],
            )  # fmt: skip
        r["iterations"], r["fraction"] = it, fr
        return r

    if trace:
        return kernel(initial_estimate)
    run = kernel(initial_estimate)
    zero_kept = None
    if zero_start:
        run, zero_kept = _keep_better(
            run, kernel(False), data, model, weights, flag, flag_row, a1, a2, tb,
            (ntime, nfreq, nant, nchan),
        )  # fmt: skip
    delays, pflags, err, gflags = (
        run["delays"],
        run["pflags"],
        run["err"],
        run["gflags"],
    )
    gains, offsets = run["gains"], run["offsets"]
    iterations, fraction = run["iterations"], run["fraction"]
    shape = (ntime, nfreq, nant)
    tau = delays.reshape(*shape, 2) * 1e9
    phi = offsets.reshape(*shape, 2)
    kernel_flags = pflags.reshape(shape) != 0
    flags = np.repeat(kernel_flags[..., None], 2, axis=-1)
    err = err.reshape(*shape, 2) * 1e9
    refant_used = np.full(ntime, r0, np.int32)
    if casa_rules:
        # CASA's KJones: an antenna needs an unflagged cell on its baseline to
        # the refant; delays referenced to the refant, which is unflagged at 0.
        # Flex (issue #53): per interval the reference is the first refant
        # with data (else the best-connected antenna), and an antenna needs a
        # path of unflagged baselines to it.
        cells = ~_cell_flags(data, weights, flag.astype(bool), flag_row)
        cross = a1 != a2
        live = cells.any(1) & cross
        live_f = np.stack([cells[:, fb == f].any(1) & cross for f in range(nfreq)], 1)
        tbi = tb.astype(np.int64)
        ref = np.full(ntime, r0, np.int64)
        if refantmode == "flex":
            for t in range(ntime):
                rows = live & (tbi == t)
                if not rows.any():
                    continue
                on = np.zeros(nant, np.int64)
                n = cells[rows].sum(1)
                np.add.at(on, a1[rows].astype(np.int64), n)
                np.add.at(on, a2[rows].astype(np.int64), n)
                ok = (on > 0) & ~kernel_flags[t].all(0)
                pick = [r for r in refants if ok[r]]
                if pick:
                    ref[t] = pick[0]
                elif ok.any():
                    ref[t] = int(np.argmax(np.where(ok, on, -1)))
        refant_used = ref.astype(np.int32)
        linked = np.zeros(shape, bool)
        for t in range(ntime):
            sel = tbi == t
            for f in range(nfreq):
                rows = sel & live_f[:, f]
                p, q = a1[rows].astype(np.int64), a2[rows].astype(np.int64)
                if refantmode == "strict" or ref[t] == r0 and _direct(p, q, r0, nant):
                    other = np.where(p == r0, q, p)[(p == r0) | (q == r0)]
                    linked[t, f, other] = True
                else:
                    linked[t, f] = _connected(p, q, int(ref[t]), nant)
        rt = ref[:, None, None, None]
        tau_ref = np.take_along_axis(tau, np.broadcast_to(rt, (ntime, nfreq, 1, 2)), 2)
        phi_ref = np.take_along_axis(phi, np.broadcast_to(rt, (ntime, nfreq, 1, 2)), 2)
        ref_ok = ~np.take_along_axis(
            flags, np.broadcast_to(rt, (ntime, nfreq, 1, 2)), 2
        )
        flags |= ~linked[..., None]
        tau = np.where(ref_ok, tau - tau_ref, tau)
        phi = np.where(ref_ok, phi - phi_ref, phi)
        flags |= ~ref_ok
        it = np.arange(ntime)
        flags[it, :, ref, :] = False
        tau[it, :, ref, :] = 0.0
        phi[it, :, ref, :] = 0.0
        tau[flags] = 0.0
        phi[flags] = 0.0
        err[flags] = 0.0
    out_gains = None
    if return_gains:
        out_gains = gains.view(np.complex128).reshape(ntime, nchan, nant, 2)
    extra = {} if zero_kept is None else {"zero_start_intervals": zero_kept}
    return DelaySolution(
        delays=tau,
        flags=flags,
        err=err,
        iterations=int(iterations),
        converged_fraction=float(fraction),
        refant_used=refant_used,
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
            "zero_start": zero_start,
            **extra,
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
    average_time=False,
    zero_start=False,
    solve_calwt=False,
):
    """`gaincal(gaintype='K')` on one field of a single-window MS: returns
    `(CalTable, DelaySolution, info)`; `kind` and `offset_start` as `solve`, recorded in
    `sol.settings`, with the offsets left out of the table (G absorbs them).
    `refant` is an antenna index or name
    (or a list); `refantmode` as `solve` (issue #53: `flex`, the default,
    falls back along the list and solves antennas connected to the
    reference through other baselines; `strict` is CASA's K); `minsnr` and
    `minblperant` are accepted and not applied, as CASA's K does not apply
    them. `gaintable` CalTables or paths; `model` an array `(row, chan, 4)`
    for the field's rows instead of `model_column`. With tables to
    pre-apply the solve uses SIGMA weights (as `rang.cal_gain.gaincal`),
    otherwise `weight_column`. Raises when no solution is written.
    `weight_column=None` and `scan` as `rang.cal_gain.gaincal` (task C2e),
    and `budget` (task W3b): chunks of whole intervals, the same result.
    `average_time` (task E2) as `rang.cal_gain.gaincal`. `zero_start` as
    `solve` (research/calchain-floor.md section 12). `solve_calwt` (task
    calwt-terms, `calibrate.k_calwt`) as `rang.cal_gain.gaincal`'s."""
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
        uvrange=uvrange, solve_calwt=solve_calwt,
    )  # fmt: skip
    m = fld.meta
    tb, keys = cal_gain.solint_bins(
        m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], solint, combine
    )
    sol, row_w = _solve_field(
        fld, tb, budget=budget, what=f"gaincal K field {field_id}", nant=nant,
        chan_freq=freq, refant=refants, casa_rules=casa_rules, refantmode=refantmode,
        initial_estimate=initial_estimate, max_iterations=max_iterations,
        stop_criterion=stop_criterion, stop_fraction=stop_fraction, kind=kind,
        offset_start=offset_start, zero_start=zero_start,
        **({"average": True} if average_time else {}),
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
        raise cal_gain.NoSolutions(
            f"gaincal K wrote no solutions for field {field_id} (every delay flagged)"
        )
    times, _ = fld.solution_times(tb, row_w, len(keys))
    scans = fld.scans(tb, len(keys))
    table = to_caltable(sol, times, scans, field_id=field_id, ms=ms)
    half = half_period_delays(sol, freq, names=names, scans=scans)
    if half:  # research/k-ambiguity.md: recorded and warned, the table unchanged
        sol.settings["half_period_delays"] = half
        warnings.warn(
            half_period_message(half, field_id), HalfPeriodDelay, stacklevel=2
        )
    info = {"rows": len(rows), "intervals": keys, "time_bin": tb, "frequency": freq}
    if solve_calwt:
        info["calwt"] = True
    return table, sol, info


_PER_INTERVAL = ("delays", "flags", "err", "kernel_flags", "gain_flags", "gains", "offsets",
                 "refant_used")  # fmt: skip


def zero_kept_of_chunks(results):
    """`zero_start_intervals` of a field solved in chunks of whole intervals
    (`results`, the chunks' `DelaySolution`s in order): each chunk counts its
    intervals from 0, so its kept intervals are offset by the intervals of
    the chunks before it (research/k-ambiguity.md; before, the field kept
    the first chunk's list only)."""
    kept, t0 = [], 0
    for r in results:
        kept += [t0 + int(i) for i in r.settings.get("zero_start_intervals", ())]
        t0 += r.delays.shape[0]
    return kept


def _solve_field(fld, tb, *, budget, what, average=False, **opts):
    """`solve` on the rows of `fld` (`rang.cal_gain._Field`) in chunks of
    whole intervals under `budget` (task W3b; None: one call), the stop test
    replayed (`rang.cal_chunks.replayed`); K's referencing is per interval,
    so every chunk is a whole `solve`. `average` (task E2): on the rows
    averaged in time within each interval. Returns `(DelaySolution, row
    weights)`."""
    from . import cal_chunks

    nchan = len(opts["chan_freq"])
    m = fld.meta
    avg = None
    if average:
        avg = fld.averaged(tb)
        chunks, block = cal_chunks.plan(
            avg.time_bin, nchan, 4, budget, per_channel=False, what=what, average=avg
        )
        flag_row, ant1, ant2, bins = (
            avg.flag_row,
            avg.antenna1,
            avg.antenna2,
            avg.time_bin,
        )
    else:
        chunks, block = cal_chunks.plan(
            tb, nchan, 4, budget, per_channel=False, what=what
        )
        flag_row, ant1, ant2, bins = fld.flag_row, m["ANTENNA1"], m["ANTENNA2"], tb
    row_w = np.zeros(len(tb))
    with core_ms.open_table(fld.ms) as reader:

        def run(chunk, max_iterations, stop_fraction, trace):
            pos = chunk.pos
            if avg is None:
                arr = cal_chunks.load(
                    reader, fld.rows, chunk, fld.cells, fld.prepare, block
                )
                if not trace:
                    row_w[pos] = arr.pop("row_w")
            else:
                arr = cal_chunks.load_averaged(
                    reader, fld.rows, chunk, fld.cells, fld.prepare, block, avg
                )
                if not trace:
                    row_w[arr["src"]] = arr["row_w"]
            kw = dict(opts, max_iterations=max_iterations, stop_fraction=stop_fraction)
            return solve(
                arr["data"], arr["model"], arr["weights"], arr["flag"],
                flag_row[pos], ant1[pos], ant2[pos],
                bins[pos] - chunk.t0, trace=trace, **kw,
            )  # fmt: skip

        results, replay = cal_chunks.replayed(
            chunks,
            run,
            max_iterations=opts["max_iterations"],
            stop_fraction=opts["stop_fraction"],
            row_w=row_w,
        )
    sol = results[0]
    if replay is not None:
        if "zero_start_intervals" in sol.settings:
            # before the merge below, which replaces results[0]'s arrays
            sol.settings["zero_start_intervals"] = zero_kept_of_chunks(results)
        for key in _PER_INTERVAL:
            parts = [getattr(r, key) for r in results]
            if parts[0] is not None:
                setattr(sol, key, np.concatenate(parts, axis=0))
        sol.iterations, sol.converged_fraction = replay
        sol.settings["max_iterations"] = int(opts["max_iterations"])
        sol.settings["stop_fraction"] = float(opts["stop_fraction"])
    return sol, row_w


# The FFT start's padded length (core/src/cal/delay.rs `ESTIMATE_POINTS`),
# for `half_period_delays`' one-bin label.
FFT_POINTS = 1 << 15


class HalfPeriodDelay(UserWarning):
    """A K solution near +-1/(2 dnu) (research/k-ambiguity.md)."""


def half_period_delays(sol, freq, *, names=None, scans=None):
    """The unflagged solutions of `sol` with |delay| >= 1/(4 dnu) (dnu the
    channel width): a quarter period or less from +-1/(2 dnu), the delay of
    data that alternate in sign channel to channel, as m054's from scan 50 of
    block 1678312253 (research/k-ambiguity.md). A flipped antenna's K is
    +-1/(2 dnu) plus its own delay against the refant, so the window is a
    quarter period (1,196 ns at 4,096 channels over 856 MHz), not one FFT bin
    (0.146 ns there, which m054 met only because its own delay was 0.13 ns);
    no antenna delay is near it, and E2-A's ID 50 sidelobe solution (2,335 ns)
    is in it too. Such a K fits its own interval but not its neighbours, so
    interpolating it is wrong. A list of `{"interval", "scan", "antenna",
    "name", "hand", "delay_ns", "from_half_period_ns", "within_one_bin"}`;
    empty when none."""
    freq = np.asarray(freq, float)
    if len(freq) < 2:
        return []
    dnu = abs(freq[1] - freq[0])
    n = -(-FFT_POINTS // len(freq)) * len(freq)
    half, width = 0.5e9 / dnu, 1e9 / (n * dnu)
    tau = np.asarray(sol.delays)[:, 0]
    off = np.abs(tau) - half
    near = (np.abs(tau) >= half / 2) & ~np.asarray(sol.flags)[:, 0]
    out = []
    for t, a, h in zip(*np.nonzero(near)):
        out.append({
            "interval": int(t),
            "scan": None if scans is None else int(scans[t]),
            "antenna": int(a),
            "name": None if names is None else str(names[a]),
            "hand": "XY"[h],
            "delay_ns": round(float(tau[t, a, h]), 3),
            "from_half_period_ns": round(float(off[t, a, h]), 3),
            "within_one_bin": bool(abs(off[t, a, h]) <= width),
        })  # fmt: skip
    return out


def half_period_message(half, field_id):
    """The warning for `half_period_delays`' list."""
    seen = sorted({(d["interval"], d["scan"], d["antenna"], d["name"]) for d in half})
    where = "; ".join(
        f"{n or a} interval {t}" + ("" if s is None else f" (scan {s})")
        for t, s, a, n in seen
    )
    values = ", ".join(f"{d['delay_ns']:+.2f} ns" for d in half[:4])
    return (
        f"gaincal K field {field_id}: {len(half)} delay(s) within a quarter period "
        f"of +-1/(2 dnu) ({where}; {values}{', ...' if len(half) > 4 else ''}): the data "
        "may alternate in sign channel to channel, and interpolating this K across "
        "intervals is then wrong; check the scans with "
        "research/results/k-ambiguity/ka_scan.py (research/k-ambiguity.md)"
    )


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


__all__ = [
    "DelaySolution",
    "HalfPeriodDelay",
    "gaincal",
    "half_period_delays",
    "solve",
    "to_caltable",
]
