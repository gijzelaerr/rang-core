"""The bandpass B: a diagonal complex gain per channel, with CASA's
`bandpass(bandtype='B')` rules (task C2c, research/c2c-bandpass.md part 2;
C1 step 5, research/c1-calibration-chain.md).

Layers, each usable alone:

- `solve(...)`: one term on arrays. The kernel is `core/src/cal/diag.rs`'s
  `diag_complex` with one frequency bin per channel (QuartiCal 0.2.7's
  `diag_complex` with `freq_interval=1`), through `rang.cal_gain.solve`.
  With `casa_rules=True` CASA's rules wrap it per channel, in CASA's order
  (`Calibrater::genericGatherAndSolve`, `BJones::globalPostSolveTinker`):
  `minblperant` per interval and channel, the solve, `minsnr` per channel,
  the reference antenna (flex or strict) over the channels, then
  `fillgaps` (`core/src/cal/bandpass.rs`, CASA's `fillChanGapArray` in
  float32), which fills and unflags short runs of flagged channels.
- `bandpass(...)`: the Measurement Set route, as CASA's `bandpass`: field,
  `solint` and `combine` (CASA's default `'scan'`) through
  `rang.cal_gain.solint_bins`, `uvrange`, earlier tables pre-applied through
  `rang.cal_gain._pre_apply(..., solved='B')` (B is CASA's lowest type, so
  every table corrupts the model), SIGMA weights when tables are
  pre-applied; returns a `formats.caltable.CalTable` (`B Jones`, the full
  window).

Not here: `solnorm` (CARACal passes False), `smodel`, BPOLY, several
windows or fields in one call, and CASA's time-averaging estimator (rang
solves the least-squares problem on the cells, as QuartiCal does).
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import cal_gain, core_ms
from .formats import caltable


@dataclass
class BandpassSolution:
    """One solved B over (interval, channel, antenna, hand): `gains`
    complex64 as written, `flags`, `snr`, `err`, and `filled` (the solutions
    `fillgaps` interpolated and unflagged)."""

    gains: np.ndarray
    flags: np.ndarray
    snr: np.ndarray
    err: np.ndarray
    filled: np.ndarray
    iterations: int
    converged_fraction: float
    refant_used: np.ndarray
    used_alternate_refant: bool
    kernel_flags: np.ndarray
    settings: dict = field(default_factory=dict)


def fill_gaps(gains, flags, maxgap):
    """CASA's `fillgaps` on `(ntime, nchan, nant, 2)` solutions and flags:
    returns new complex64 gains and flags. Rows (time, antenna) without an
    unflagged solution are left alone."""
    g = np.ascontiguousarray(np.asarray(gains, np.complex64).transpose(0, 2, 1, 3))
    f = np.ascontiguousarray(np.asarray(flags, bool).transpose(0, 2, 1, 3)).astype(
        np.uint8
    )
    ntime, nant, nchan, npar = g.shape
    if maxgap > 0:
        from rang import core

        core.extension().cal_bandpass_fill_gaps(
            ntime * nant, nchan, npar, int(maxgap), g.view(np.float32).reshape(-1),
            f.reshape(-1),
        )  # fmt: skip
    return g.transpose(0, 2, 1, 3).copy(), f.transpose(0, 2, 1, 3).astype(bool)


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
    refant=0,
    refantmode="flex",
    minsnr=3.0,
    minblperant=4,
    fillgaps=0,
    positions=None,
    casa_rules=True,
    max_iterations=50,
    stop_criterion=1e-7,
    stop_fraction=0.99,
):
    """Solve B on arrays (rows, chans, 4 correlations): one complex gain per
    interval, channel, antenna and hand. Arguments as
    `rang.cal_gain.solve`; `fillgaps` is CASA's (0: off), applied only with
    `casa_rules`."""
    nchan = np.asarray(data).shape[1]
    sol = cal_gain.solve(
        data, model, weights, flag, flag_row, antenna1, antenna2, time_bin,
        nant=nant, freq_bin=np.arange(nchan), calmode="ap", refant=refant,
        refantmode=refantmode, minsnr=minsnr, minblperant=minblperant,
        positions=positions, casa_rules=casa_rules, max_iterations=max_iterations,
        stop_criterion=stop_criterion, stop_fraction=stop_fraction,
    )  # fmt: skip
    gains = sol.gains.astype(np.complex64)
    flags = sol.flags.copy()
    if casa_rules and fillgaps > 0:
        gains, flags = fill_gaps(gains, flags, fillgaps)
    filled = sol.flags & ~flags
    settings = dict(sol.settings, fillgaps=int(fillgaps), term="B")
    return BandpassSolution(
        gains=gains,
        flags=flags,
        snr=sol.snr,
        err=sol.err,
        filled=filled,
        iterations=sol.iterations,
        converged_fraction=sol.converged_fraction,
        refant_used=sol.refant_used,
        used_alternate_refant=sol.used_alternate_refant,
        kernel_flags=sol.kernel_flags,
        settings=settings,
    )


def bandpass(
    ms,
    *,
    field_id=0,
    solint="inf",
    combine="scan",
    refant=0,
    refantmode="flex",
    minsnr=3.0,
    minblperant=4,
    fillgaps=0,
    uvrange="",
    gaintable=(),
    interp="linear",
    data_column="DATA",
    model_column="MODEL_DATA",
    model=None,
    weight_column="WEIGHT_SPECTRUM",
    casa_rules=True,
    max_iterations=50,
    stop_criterion=1e-7,
    stop_fraction=0.99,
    scan=None,
):
    """`bandpass(bandtype='B')` on one field of a single-window MS: returns
    `(CalTable, BandpassSolution, info)`. Defaults are CASA 6.7.6.14's
    (`combine='scan'`, `minblperant=4`, `minsnr=3`, `fillgaps=0`, flex).
    `refant` an index or name (or a list); `gaintable` CalTables or paths;
    `model` an array `(row, chan, 4)` for the field's rows instead of
    `model_column`. Weights: `1/SIGMA^2` when tables are pre-applied (as
    `rang.cal_gain.gaincal`), `weight_column` otherwise. Raises when no
    solution is written. `weight_column=None` and `scan` as
    `rang.cal_gain.gaincal` (task C2e)."""
    ms = Path(ms)
    with core_ms.open_table(ms / "ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
        positions = t.getcol("POSITION")
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
    cols = ["TIME", "SCAN_NUMBER", "FIELD_ID", "ANTENNA1", "ANTENNA2", "UVW", "FLAG",
            "FLAG_ROW", data_column, *cal_gain._weight_columns(weight_column)]  # fmt: skip
    if model is None:
        cols.append(model_column)
    sigma_column = "SIGMA_SPECTRUM" if "SIGMA_SPECTRUM" in colnames else "SIGMA"
    if gaintable:
        cols.append(sigma_column)
    c = cal_gain._ms_columns(ms, cols, rows)
    data = c[data_column]
    mdl = c[model_column] if model is None else np.asarray(model)
    flag = np.asarray(c["FLAG"], bool)
    flag_row = np.asarray(c["FLAG_ROW"], bool) | ~cal_gain.uvrange_keep(
        c["UVW"], uvrange
    )
    tables = [
        t if isinstance(t, caltable.CalTable) else caltable.read(t) for t in gaintable
    ]
    if tables:
        data, mdl, flag = cal_gain._pre_apply(
            data, mdl, flag, c["TIME"], c["ANTENNA1"], c["ANTENNA2"], freq, tables,
            interp, nant, field_id, solved="B",
        )  # fmt: skip
    tb, keys = cal_gain.solint_bins(
        c["TIME"], c["SCAN_NUMBER"], c["FIELD_ID"], solint, combine
    )
    weights = cal_gain._weights(c, weight_column, data.shape)
    if tables:
        sigma = np.asarray(c[sigma_column], np.float64)
        if sigma.ndim == 2:
            sigma = np.broadcast_to(sigma[:, None, :], weights.shape)
        with np.errstate(divide="ignore"):
            weights = np.where(sigma > 0, 1.0 / sigma**2, 0.0).astype(np.float32)
    sol = solve(
        data, mdl, weights, flag, flag_row, c["ANTENNA1"], c["ANTENNA2"], tb,
        nant=nant, refant=refants, refantmode=refantmode, minsnr=minsnr,
        minblperant=minblperant, fillgaps=fillgaps, positions=positions,
        casa_rules=casa_rules, max_iterations=max_iterations,
        stop_criterion=stop_criterion, stop_fraction=stop_fraction,
    )  # fmt: skip
    sol.settings.update(
        {"weights": sigma_column if tables else weight_column, "uvrange": uvrange,
         "solint": solint, "combine": combine}
    )  # fmt: skip
    if sol.flags.all():
        raise RuntimeError(
            f"bandpass wrote no solutions for field {field_id} (every solution flagged)"
        )
    used_flags = (
        flag | flag_row[:, None, None] | (c["ANTENNA1"] == c["ANTENNA2"])[:, None, None]
    )
    times, span = cal_gain.solution_times(c["TIME"], tb, weights, used_flags, len(keys))
    scans = np.array([c["SCAN_NUMBER"][tb == t].min() for t in range(len(keys))])
    table = to_caltable(sol, times, span, scans, field_id=field_id, ms=ms)
    info = {"rows": len(rows), "intervals": keys, "time_bin": tb, "frequency": freq}
    return table, sol, info


def to_caltable(sol, times, intervals, scans, *, field_id, ms, spw=0):
    """The CASA `B Jones` table of `sol`: one row per (interval, antenna),
    `CPARAM`, `PARAMERR`, `FLAG` and `SNR` `(nchan, 2)`, the full window,
    `ANTENNA2` the refant used."""
    ntime, _nchan, nant, _ = sol.gains.shape
    subtables = caltable.subtables_from_ms(ms, single_channel=False)
    n = ntime * nant
    t_idx = np.repeat(np.arange(ntime), nant)
    a_idx = np.tile(np.arange(nant), ntime)
    main = {
        "TIME": [float(times[t]) for t in t_idx],
        "FIELD_ID": [int(field_id)] * n,
        "SPECTRAL_WINDOW_ID": [int(spw)] * n,
        "ANTENNA1": [int(a) for a in a_idx],
        "ANTENNA2": [int(sol.refant_used[t]) for t in t_idx],
        "INTERVAL": [float(intervals[t]) for t in t_idx],
        "SCAN_NUMBER": [int(scans[t]) for t in t_idx],
        "OBSERVATION_ID": [0] * n,
        "CPARAM": [
            np.ascontiguousarray(sol.gains[t, :, a], np.complex64)
            for t, a in zip(t_idx, a_idx)
        ],
        "PARAMERR": [
            np.ascontiguousarray(sol.err[t, :, a], np.float32)
            for t, a in zip(t_idx, a_idx)
        ],
        "FLAG": [
            np.ascontiguousarray(sol.flags[t, :, a]) for t, a in zip(t_idx, a_idx)
        ],
        "SNR": [
            np.ascontiguousarray(sol.snr[t, :, a], np.float32)
            for t, a in zip(t_idx, a_idx)
        ],
        "WEIGHT": [None] * n,
    }
    keywords = {
        "ParType": "Complex",
        "MSName": str(Path(ms).name),
        "VisCal": "B Jones",
        "PolBasis": "unknown",
        "CASA_Version": "6.7.6-14",
    }
    return caltable.CalTable(
        "B Jones", main, subtables, keywords, ["Calibration", "B Jones", ""]
    )


def table_solutions(table, nant):
    """(time, chan, ant, 2) solutions, flags and SNR of a `B Jones` table,
    its solution times and per-time ANTENNA2."""
    times = np.unique(table.column("TIME"))
    params, flags = table.params, table.flags
    nchan = params.shape[1]
    g = np.ones((len(times), nchan, nant, 2), np.complex64)
    f = np.ones((len(times), nchan, nant, 2), bool)
    s = np.zeros((len(times), nchan, nant, 2), np.float32)
    snr = table.snr
    ref = np.full(len(times), -2)
    t_all, a1, a2 = (table.column(k) for k in ("TIME", "ANTENNA1", "ANTENNA2"))
    for row in range(table.nrows):
        t = int(np.searchsorted(times, t_all[row]))
        g[t, :, a1[row]] = params[row]
        f[t, :, a1[row]] = flags[row]
        if snr is not None:
            s[t, :, a1[row]] = snr[row]
        ref[t] = a2[row]
    return times, g, f, s, ref


__all__ = ["BandpassSolution", "bandpass", "fill_gaps", "solve", "table_solutions",
           "to_caltable"]  # fmt: skip
