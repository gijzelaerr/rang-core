"""The gain term G: diagonal complex (`calmode='ap'`) and phase-only (`'p'`)
solves in the Rust core, with CASA's intervals and rules (task C2a,
research/c2a-gain.md; C1 step 3, research/c1-calibration-chain.md).

Layers, each usable alone:

- `solint_bins(...)`: CASA's row-to-interval map for `solint` (`'inf'`,
  `'int'`, or seconds) and `combine`; `uvrange_keep(...)`: CASA's
  `uvrange` row selection (metres).
- `solve(...)`: one term on arrays. The kernel is `core/src/cal/diag.rs`
  (QuartiCal 0.2.7's `diag_complex` or `phase`). With `casa_rules=True`
  (the default) CASA's rules wrap it (`core/src/cal/reference.rs`):
  `minblperant` before the solve, `minsnr` after it, then the reference
  antenna (`refantmode` `flex` or `strict`) over all intervals; with
  `casa_rules=False` the kernel is QuartiCal's alone, referenced as
  QuartiCal references it (the class A configuration).
- `gaincal(...)`: the Measurement Set route, as CASA `gaincal(gaintype='G')`:
  select the field, pre-apply earlier tables through `rang.cal_apply`
  (lower VisCal types correct DATA, equal or higher types corrupt the
  model, as `VisEquation::collapse2`), solve, and return a
  `formats.caltable.CalTable` that `caltable.write` writes as CASA does.

Not here: K and B (C2b, C2c), `fluxscale` (C2d), `solnorm`, `smodel`,
`preavg`, `append`, several windows or fields in one call, and frequency
parts of `solint` (CASA ignores them for G; C1 section 1.4).
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import cal_apply, core_ms
from .formats import caltable

KINDS = {"ap": 0, "p": 1}
# VisCal::Type order (C1 section 1.1): lower types correct the data while G
# is solved, equal or higher types corrupt the model.
TYPE_ORDER = ("B", "K", "Kcross", "G", "J", "Df", "Xf", "C", "P", "E", "T", "F")


def parse_solint(solint):
    """`'inf'`, `'int'` or a duration in seconds (`'60s'`, `'2min'`, `60`)."""
    if isinstance(solint, (int, float)):
        if solint <= 0:
            raise ValueError("solint must be positive")
        return float(solint)
    text = str(solint).strip().lower()
    if text in ("inf", "int"):
        return text
    for unit, scale in (("min", 60.0), ("s", 1.0), ("h", 3600.0)):
        if text.endswith(unit):
            text, factor = text[: -len(unit)], scale
            break
    else:
        factor = 1.0
    try:
        value = float(text) * factor
    except ValueError:
        raise ValueError(
            f"unsupported solint {solint!r}: use 'inf', 'int' or seconds"
        ) from None
    if value <= 0:
        raise ValueError("solint must be positive")
    return value


def solint_bins(time, scan, field_id, solint="inf", combine=""):
    """CASA's solution intervals: the interval index of every row (rows in
    their order) and the interval keys `(group, slot)`.

    Rows are grouped by field and, unless `combine` contains `scan`, by scan
    (CASA's iteration columns; one window and one observation are assumed).
    `'inf'` is one interval per group; `'int'` one per timestamp; seconds
    are CASA's `MSInterval` bins, `floor((t - t0) / solint)` with `t0` the
    first timestamp of the group. Interval indices ascend with the first
    time of the interval."""
    combine = {c.strip() for c in str(combine).lower().split(",") if c.strip()}
    unknown = combine - {"scan", "field", "spw", "obs"}
    if unknown:
        raise ValueError(f"unsupported combine {sorted(unknown)}")
    if "field" in combine or "spw" in combine:
        raise ValueError(
            "combine field or spw is not supported (one field, one window)"
        )
    time = np.asarray(time, float)
    scan = np.asarray(scan, np.int64)
    field_id = np.asarray(field_id, np.int64)
    group_key = np.stack(
        [field_id, np.zeros_like(scan) if "scan" in combine else scan], 1
    )
    groups, group = np.unique(group_key, axis=0, return_inverse=True)
    group = group.ravel()
    width = parse_solint(solint)
    slot = np.zeros(len(time), np.int64)
    for g in range(len(groups)):
        rows = group == g
        t = time[rows]
        if width == "inf":
            slot[rows] = 0
        elif width == "int":
            slot[rows] = np.unique(t, return_inverse=True)[1].ravel()
        else:
            slot[rows] = np.floor((t - t.min()) / width).astype(np.int64)
    keys = np.stack([group, slot], 1)
    uniq, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    first = np.array([time[inverse == i].min() for i in range(len(uniq))])
    order = np.argsort(first, kind="stable")
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    return rank[inverse], [tuple(int(v) for v in uniq[i]) for i in order]


def uvrange_keep(uvw, uvrange):
    """CASA's `uvrange` in metres on `sqrt(u^2 + v^2)`: `''` (all), `'>X'`,
    `'<X'`, `'X~Y'` (inclusive), optionally with an `m` suffix; several
    ranges joined by `,` are OR-ed."""
    uvw = np.asarray(uvw, float)
    uvdist = np.hypot(uvw[:, 0], uvw[:, 1])
    text = str(uvrange or "").strip()
    if not text:
        return np.ones(len(uvdist), bool)
    keep = np.zeros(len(uvdist), bool)
    for part in text.split(","):
        part = part.strip().lower()
        if part.endswith("lambda"):
            raise ValueError("uvrange in wavelengths is not supported; give metres")
        part = part.removesuffix("m").strip()
        if part.startswith(">"):
            keep |= uvdist > float(part[1:])
        elif part.startswith("<"):
            keep |= uvdist < float(part[1:])
        elif "~" in part:
            lo, hi = (float(x) for x in part.split("~"))
            keep |= (uvdist >= lo) & (uvdist <= hi)
        else:
            raise ValueError(f"unsupported uvrange {uvrange!r}")
    return keep


def _extension():
    from rang import core

    return core.extension()


def _floats(a, dtype=np.complex64):
    return np.ascontiguousarray(a, dtype).view(
        np.float32 if dtype == np.complex64 else np.float64
    )


@dataclass
class GainSolution:
    """One solved term: arrays over (interval, frequency bin, antenna, hand)."""

    gains: np.ndarray
    flags: np.ndarray
    snr: np.ndarray
    err: np.ndarray
    iterations: int
    converged_fraction: float
    refant_used: np.ndarray
    used_alternate_refant: bool
    blperant_ok: np.ndarray
    kernel_flags: np.ndarray
    settings: dict = field(default_factory=dict)


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
    freq_bin=None,
    calmode="ap",
    refant=0,
    refantmode="flex",
    minsnr=3.0,
    minblperant=4,
    positions=None,
    casa_rules=True,
    max_iterations=50,
    stop_criterion=1e-7,
    stop_fraction=0.99,
):
    """Solve one diagonal gain term on arrays (rows, chans, 4 correlations).

    `time_bin` maps rows to intervals (`solint_bins`), `freq_bin` channels to
    frequency bins (default one bin). `refant` is an index or a list
    (primary first). With `casa_rules`, CASA's `minblperant` (data of
    eliminated antennas flagged for the solve), `minsnr` (per hand) and
    reference antenna (`positions`, `(nant, 3)`, needed for `flex`
    alternates) are applied; otherwise QuartiCal's referencing to the
    primary refant. Autocorrelations are not used."""
    refants = _check(calmode, refantmode, refant, nant)
    raw = _kernel(
        data, model, weights, flag, flag_row, antenna1, antenna2, time_bin,
        nant=nant, freq_bin=freq_bin, calmode=calmode, refants=refants,
        minblperant=minblperant, casa_rules=casa_rules,
        max_iterations=max_iterations, stop_criterion=stop_criterion,
        stop_fraction=stop_fraction,
    )  # fmt: skip
    return _finish(
        raw, nant=nant, calmode=calmode, refants=refants, refantmode=refantmode,
        minsnr=minsnr, minblperant=minblperant, positions=positions,
        casa_rules=casa_rules, max_iterations=max_iterations,
        stop_criterion=stop_criterion, stop_fraction=stop_fraction,
    )  # fmt: skip


def _check(calmode, refantmode, refant, nant):
    if calmode not in KINDS:
        raise ValueError(f"calmode must be one of {sorted(KINDS)}")
    if refantmode not in ("flex", "strict"):
        raise ValueError("refantmode must be 'flex' or 'strict'")
    refants = [int(r) for r in np.atleast_1d(refant)]
    if not refants or any(r < 0 or r >= nant for r in refants):
        raise ValueError("refant out of range")
    return refants


def _kernel(
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
    freq_bin,
    calmode,
    refants,
    minblperant,
    casa_rules,
    max_iterations,
    stop_criterion,
    stop_fraction,
    trace=False,
):
    """`solve`'s kernel part, per interval: CASA's `minblperant`, then the
    solve with CASA's statistics. Returns a dict of the per-interval arrays
    (`gains`, `kernel_flags`, `snr`, `err`, `ok`) and `iterations`,
    `fraction`; with `trace` (task W3b) instead `(counts, error, ngains)`
    of the counted kernel (`rang.cal_chunks.replayed`)."""
    data = np.ascontiguousarray(data, np.complex64)
    nrow, nchan = data.shape[:2]
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
    # The kernel wants rows grouped by interval.
    order = np.argsort(time_bin, kind="stable")
    sorted_rows = lambda x: np.ascontiguousarray(x[order])
    data, model, weights, flag = (sorted_rows(x) for x in (data, model, weights, flag))
    a1, a2, flag_row, tb = (sorted_rows(x) for x in (a1, a2, flag_row, time_bin))
    flag_row = flag_row.astype(np.uint8)
    tb = tb.astype(np.uint32)
    fb = np.ascontiguousarray(freq_bin, np.uint32)
    ext = _extension()
    common = (
        nrow,
        nchan,
        ntime,
        nfreq,
        int(nant),
        _floats(data),
        weights,
        _floats(model),
        flag,
        flag_row,
        a1,
        a2,
        tb,
        fb,
    )
    ok = np.ones((ntime, nfreq, nant), bool)
    if casa_rules:
        out = np.empty(ntime * nfreq * nant, np.uint8)
        ext.cal_gain_minblperant(*common, int(minblperant), out)
        ok = out.reshape(ntime, nfreq, nant).astype(bool)
        bad = (
            ~ok[tb[:, None], fb[None, :], a1[:, None]]
            | ~ok[tb[:, None], fb[None, :], a2[:, None]]
        )
        flag = np.ascontiguousarray(flag | bad[..., None].astype(np.uint8))
        common = common[:8] + (flag,) + common[9:]
    ngain = ntime * nfreq * nant
    if trace:
        counts = np.zeros(2 * max(int(max_iterations), 1), np.uint64)
        n, error = ext.cal_gain_trace(
            *common,
            KINDS[calmode],
            int(max_iterations),
            float(stop_criterion),
            float(stop_fraction),
            -1 if casa_rules else refants[0],
            counts,
        )
        return counts[: 2 * n].reshape(-1, 2), error, ngain
    g = np.zeros(4 * ngain, np.float64)
    gf = np.zeros(ngain, np.int8)
    snr = np.zeros(2 * ngain, np.float32)
    err = np.zeros(2 * ngain, np.float32)
    iterations, fraction = ext.cal_gain_solve(
        *common,
        KINDS[calmode],
        int(max_iterations),
        float(stop_criterion),
        float(stop_fraction),
        -1 if casa_rules else refants[0],
        g,
        gf,
        snr,
        err,
    )
    return {
        "gains": g.view(np.complex128).reshape(ntime, nfreq, nant, 2),
        "kernel_flags": gf.reshape(ntime, nfreq, nant) != 0,
        "snr": snr.reshape(ntime, nfreq, nant, 2),
        "err": err.reshape(ntime, nfreq, nant, 2),
        "ok": ok,
        "iterations": int(iterations),
        "fraction": float(fraction),
    }


def _assemble(parts, ntime, nfreq):
    """One `_kernel` dict over every interval from the dicts of chunks
    `(chunk, dict)` (task W3b); `iterations` and `fraction` left to the
    caller."""
    first = parts[0][1]
    out = {}
    for key in ("gains", "kernel_flags", "snr", "err", "ok"):
        shape = (ntime, nfreq, *first[key].shape[2:])
        out[key] = np.empty(shape, first[key].dtype)
        for c, d in parts:
            out[key][c.t0 : c.t1, c.f0 : c.f1] = d[key]
    return out


def _finish(
    raw,
    *,
    nant,
    calmode,
    refants,
    refantmode,
    minsnr,
    minblperant,
    positions,
    casa_rules,
    max_iterations,
    stop_criterion,
    stop_fraction,
):
    """`solve`'s steps over all intervals at once: `minsnr` and CASA's
    reference antenna; returns the `GainSolution`."""
    gains, kernel_flags = raw["gains"], raw["kernel_flags"]
    snr, err, ok = raw["snr"], raw["err"], raw["ok"]
    iterations, fraction = raw["iterations"], raw["fraction"]
    ntime, nfreq = gains.shape[:2]
    flags = np.repeat(kernel_flags[..., None], 2, axis=-1)
    used = np.full(ntime, refants[0], np.int32)
    alternate = False
    if casa_rules:
        good = ~flags
        good &= snr > np.float32(minsnr)
        flags = ~good
        if positions is None:
            if refantmode == "flex":
                raise ValueError("refantmode='flex' needs the antenna positions")
            positions = np.zeros((nant, 3))
        # applyRefAnt per window: (time, antenna, par, chan) with the
        # frequency bins as channels.
        sol = np.ascontiguousarray(gains.transpose(0, 2, 3, 1))
        fl = np.ascontiguousarray(flags.transpose(0, 2, 3, 1).astype(np.uint8))
        used = np.zeros(ntime, np.int32)
        alternate = _extension().cal_gain_apply_refant(
            ntime,
            int(nant),
            2,
            nfreq,
            sol.view(np.float64).reshape(-1),
            fl.reshape(-1),
            np.ascontiguousarray(positions, np.float64).reshape(-1),
            refants,
            refantmode == "strict",
            used,
        )
        gains = sol.transpose(0, 3, 1, 2).copy()
        flags = fl.transpose(0, 3, 1, 2).astype(bool)
    return GainSolution(
        gains=gains,
        flags=flags,
        snr=snr,
        err=err,
        iterations=int(iterations),
        converged_fraction=float(fraction),
        refant_used=used,
        used_alternate_refant=bool(alternate),
        blperant_ok=ok,
        kernel_flags=kernel_flags,
        settings={
            "calmode": calmode,
            "refant": refants,
            "refantmode": refantmode,
            "minsnr": float(minsnr),
            "minblperant": int(minblperant),
            "casa_rules": bool(casa_rules),
            "max_iterations": int(max_iterations),
            "stop_criterion": float(stop_criterion),
            "stop_fraction": float(stop_fraction),
        },
    )


def solution_times(time, time_bin, weights, flag, ntime):
    """CASA-style solution times: per interval the mean of its rows' TIME
    weighted by their unflagged parallel-hand weight (the plain mean of the
    rows where nothing is unflagged), and the interval's time span."""
    return times_from_row_weights(time, time_bin, row_weights(weights, flag), ntime)


def row_weights(weights, flag):
    """Per row the unflagged parallel-hand weight summed over its channels
    (`solution_times`; task W3b computes it per chunk of whole rows)."""
    w = np.where(np.asarray(flag, bool), 0.0, np.asarray(weights, float))
    return w[..., 0].sum(1) + w[..., 3].sum(1)


def times_from_row_weights(time, time_bin, row_w, ntime):
    """`solution_times` from the rows' weights (`row_weights`)."""
    time = np.asarray(time, float)
    centre = np.zeros(ntime)
    span = np.zeros(ntime)
    for t in range(ntime):
        rows = np.asarray(time_bin) == t
        if not rows.any():
            continue
        tw = row_w[rows]
        centre[t] = (
            np.average(time[rows], weights=tw) if tw.sum() > 0 else time[rows].mean()
        )
        span[t] = time[rows].max() - time[rows].min()
    return centre, span


def _ms_columns(ms, names, rows=None):
    """Columns `names` of `rows` (default all), reading only those rows
    (task W3, research/w3-chunking.md: equal to indexing whole columns)."""
    from . import core_chunks

    with core_ms.open_table(ms) as t:
        if rows is None:
            return {n: t.getcol(n) for n in names}
        return {n: core_chunks.read_rows(t, n, rows) for n in names}


def _scan_keep(ms, scan, keep):
    """`keep` AND the rows whose SCAN_NUMBER is in `scan` (CASA's `scan`
    selection as a list of numbers; None keeps `keep`; task C2e)."""
    if scan is None:
        return keep
    with core_ms.open_table(ms) as t:
        numbers = np.asarray(t.getcol("SCAN_NUMBER"))
    return keep & np.isin(numbers, [int(s) for s in np.atleast_1d(scan)])


def _weight_columns(weight_column):
    """The weight column to read: none for unit weights (task C2e)."""
    return [] if weight_column is None else [weight_column]


def _weights(c, weight_column, shape):
    """The solve weights read from `weight_column` (task C2e): None gives 1
    everywhere (rang-core's `data.weights: uniform`), a (row, corr) column
    such as WEIGHT is repeated over the channels, and a (row, chan, corr)
    column is returned as read."""
    if weight_column is None:
        return np.ones(shape, np.float32)
    w = c[weight_column]
    if np.ndim(w) == 2:
        w = np.ascontiguousarray(np.broadcast_to(w[:, None, :], shape), np.float32)
    return w


def _pre_apply(
    data, model, flag, time, a1, a2, freq, tables, interp, nant, field_id=0, solved="G",
    channels=None,
):  # fmt: skip
    """Pre-apply `tables` as CASA does for a solve of type `solved` (G, or K
    for `rang.cal_delay`): lower types correct the data, the others corrupt
    the model. `channels` (a slice of `freq`, the whole band): the arrays
    hold only those channels (`rang.cal_apply.apply`)."""
    lower = [
        i
        for i, t in enumerate(tables)
        if TYPE_ORDER.index(t.kind) < TYPE_ORDER.index(solved)
    ]
    upper = [i for i in range(len(tables)) if i not in lower]
    interp = cal_apply._interps(tables, interp)
    if lower:
        data, f = cal_apply.apply(
            data,
            flag,
            time,
            a1,
            a2,
            freq,
            [tables[i] for i in lower],
            interp=[interp[i] for i in lower],
            nant=nant,
            field_id=field_id,
            channels=channels,
        )
        flag = flag | f
    if upper:
        model, f = cal_apply.apply(
            model,
            flag,
            time,
            a1,
            a2,
            freq,
            [tables[i] for i in upper],
            interp=[interp[i] for i in upper],
            direction="corrupt",
            nant=nant,
            field_id=field_id,
            channels=channels,
        )
        flag = flag | f
    return data, model, flag


META_COLUMNS = (
    "TIME",
    "SCAN_NUMBER",
    "FIELD_ID",
    "ANTENNA1",
    "ANTENNA2",
    "UVW",
    "FLAG_ROW",
)


def _model_rows(model, pos, n):
    """The model of field rows `pos`: `model` an array over the field's `n`
    rows (or a broadcast view), or a callable of the positions (task W3b)."""
    if callable(model):
        return model(pos)
    model = np.asarray(model)
    if len(pos) == n and (n == 0 or (pos[0] == 0 and pos[-1] == n - 1)):
        return model
    return model[pos]


class _Field:
    """The rows of one solve on one field (task W3b,
    research/w3b-chainchunks.md): the row metadata read whole, the cell
    columns (data, flags, weights or SIGMA, model) read and pre-applied per
    chunk by `prepare`, which also gives each row's weight sum for the
    solution times (`row_weights`). `rang.cal_gain`, `rang.cal_delay` and
    `rang.cal_bandpass` read through it."""

    def __init__(
        self, ms, rows, *, data_column, model, model_column, weight_column,
        sigma_column, tables, interp, nant, field_id, solved, freq, uvrange,
    ):  # fmt: skip
        self.ms, self.rows = ms, rows
        self.meta = _ms_columns(ms, META_COLUMNS, rows)
        self.flag_row = np.asarray(self.meta["FLAG_ROW"], bool) | ~uvrange_keep(
            self.meta["UVW"], uvrange
        )
        self.auto = self.meta["ANTENNA1"] == self.meta["ANTENNA2"]
        self.cells = ["FLAG", data_column, *_weight_columns(weight_column)]
        if model is None:
            self.cells.append(model_column)
        if tables:
            self.cells.append(sigma_column)
        self.data_column, self.model, self.model_column = (
            data_column,
            model,
            model_column,
        )
        self.weight_column, self.sigma_column = weight_column, sigma_column
        self.tables, self.interp, self.nant = tables, interp, nant
        self.field_id, self.solved, self.freq = field_id, solved, freq

    def prepare(self, pos, c, chans=None):
        """The arrays of field rows `pos` from their cell columns `c`, as
        the one-call solve computes them. `chans` (a slice): the cell
        columns hold only those channels, and so do the arrays
        (research/sliced-read.md); `row_w` then covers those channels
        only."""
        m = self.meta
        data = c[self.data_column]
        if self.model is None:
            mdl = c[self.model_column]
        else:
            mdl = _model_rows(self.model, pos, len(self.rows))
            if chans is not None:
                mdl = np.asarray(mdl)[:, chans]
        flag = np.asarray(c["FLAG"], bool)
        if self.tables:
            data, mdl, flag = _pre_apply(
                data, mdl, flag, m["TIME"][pos], m["ANTENNA1"][pos], m["ANTENNA2"][pos],
                self.freq, self.tables, self.interp, self.nant, self.field_id,
                solved=self.solved, channels=chans,
            )  # fmt: skip
        weights = _weights(c, self.weight_column, data.shape)
        if self.tables:
            sigma = np.asarray(c[self.sigma_column], np.float64)
            if sigma.ndim == 2:
                sigma = np.broadcast_to(sigma[:, None, :], weights.shape)
            with np.errstate(divide="ignore"):
                weights = np.where(sigma > 0, 1.0 / sigma**2, 0.0).astype(np.float32)
        used = flag | self.flag_row[pos][:, None, None] | self.auto[pos][:, None, None]
        return {
            "data": data,
            "model": mdl,
            "weights": weights,
            "flag": flag,
            "row_w": row_weights(weights, used),
        }

    def solution_times(self, time_bin, row_w, ntime):
        return times_from_row_weights(self.meta["TIME"], time_bin, row_w, ntime)

    def scans(self, time_bin, ntime):
        return np.array(
            [self.meta["SCAN_NUMBER"][time_bin == t].min() for t in range(ntime)]
        )


def _solve_gain_field(
    fld, tb, *, nchan, per_channel, budget, what, freq_bin=None, **opts
):
    """`solve` on the rows of `fld` (`_Field`) with interval index `tb`, in
    chunks of whole intervals under `budget` (task W3b; None: one call),
    the stop test replayed (`rang.cal_chunks.replayed`). `per_channel`: one
    frequency bin per channel (B); otherwise `freq_bin` per channel (task
    C5: channel chunks of a self-calibration term, each chunk of the solve
    holding every channel) or one bin. Returns `(GainSolution, row
    weights)`."""
    import dataclasses

    from . import cal_chunks

    nant = opts["nant"]
    refants = _check(opts["calmode"], opts["refantmode"], opts["refant"], nant)
    if per_channel:
        freq_bin = np.arange(nchan)
    elif freq_bin is not None:
        freq_bin = np.asarray(freq_bin, np.int64)
    chunks, block = cal_chunks.plan(
        tb, nchan, 4, budget, per_channel=per_channel, what=what
    )
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
            fb = None if freq_bin is None else freq_bin[chunk.chans] - chunk.f0
            return _kernel(
                arr["data"], arr["model"], arr["weights"], arr["flag"],
                fld.flag_row[pos], m["ANTENNA1"][pos], m["ANTENNA2"][pos],
                tb[pos] - chunk.t0, nant=nant, freq_bin=fb, calmode=opts["calmode"],
                refants=refants, minblperant=opts["minblperant"],
                casa_rules=opts["casa_rules"], max_iterations=max_iterations,
                stop_criterion=opts["stop_criterion"], stop_fraction=stop_fraction,
                trace=trace,
            )  # fmt: skip

        results, replay = cal_chunks.replayed(
            chunks,
            run,
            max_iterations=opts["max_iterations"],
            stop_fraction=opts["stop_fraction"],
        )
    if replay is None:
        raw = results[0]
    else:
        ntime = int(np.max(tb)) + 1
        nfreq = nchan if per_channel else 1
        parts = list(zip(chunks, results))
        if not per_channel and freq_bin is not None:
            nfreq = int(freq_bin.max()) + 1
            parts = [(dataclasses.replace(c, f0=0, f1=nfreq), d) for c, d in parts]
        raw = _assemble(parts, ntime, nfreq)
        raw["iterations"], raw["fraction"] = replay
    sol = _finish(
        raw, nant=nant, calmode=opts["calmode"], refants=refants,
        refantmode=opts["refantmode"], minsnr=opts["minsnr"],
        minblperant=opts["minblperant"], positions=opts["positions"],
        casa_rules=opts["casa_rules"], max_iterations=opts["max_iterations"],
        stop_criterion=opts["stop_criterion"], stop_fraction=opts["stop_fraction"],
    )  # fmt: skip
    return sol, row_w


def gaincal(
    ms,
    *,
    field_id=0,
    solint="inf",
    combine="",
    calmode="ap",
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
    max_iterations=50,
    stop_criterion=1e-7,
    stop_fraction=0.99,
    spw=None,
    scan=None,
    budget=None,
):
    """`gaincal(gaintype='G')` on one field of one spectral window: returns
    `(CalTable, GainSolution, info)`. `refant` is an antenna index or name
    (or a list); `gaintable` CalTables or paths; `model` an array
    `(row, chan, 4)` for the field's rows (of that window) instead of
    `model_column`. Raises when no solution is written. `spw` (task C2d)
    selects one window of a multi-window MS, as CASA solves each window
    apart; tables are pre-applied only on a single-window MS.

    Weights (post hoc after run -03, research/c2a-gain.md section 6): with
    tables to pre-apply, CASA was measured to solve with weights from SIGMA
    (where it resets them was not found), so the solve uses
    `1/SIGMA_SPECTRUM^2` (or `1/SIGMA^2` per channel; 0 where sigma is 0);
    without, `weight_column` (not compared with CASA). Task C2e:
    `weight_column=None` solves with unit weights where `weight_column`
    would be read, and WEIGHT is repeated over channels; `scan` (a list of
    SCAN_NUMBERs, CASA's `scan`) restricts the rows. Task W3b: `budget` (a
    `core_chunks.ChainBudget`) reads and solves the field in chunks of whole
    solution intervals within it, with the same result; `model` may also be
    a callable of the field-row positions."""
    ms = Path(ms)
    with core_ms.open_table(ms / "ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
        positions = t.getcol("POSITION")
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        chan_freq = t.getcol("CHAN_FREQ")
    if spw is None:
        if len(chan_freq) != 1:
            raise ValueError("several spectral windows: give spw")
        spw = 0
    spw = int(spw)
    if not 0 <= spw < len(chan_freq):
        raise ValueError(f"no spectral window {spw}")
    if len(chan_freq) != 1 and gaintable:
        raise ValueError(
            "tables are pre-applied on a single-window MS only (research/c2d-fluxscale.md)"
        )
    freq = np.asarray(chan_freq[spw], float)
    nant = len(names)
    refants = [
        names.index(r) if isinstance(r, str) else int(r) for r in np.atleast_1d(refant)
    ]
    with core_ms.open_table(ms / "DATA_DESCRIPTION") as t:
        dd_spw = np.asarray(t.getcol("SPECTRAL_WINDOW_ID"))
    with core_ms.open_table(ms) as t:
        fields = t.getcol("FIELD_ID")
        ddid = t.getcol("DATA_DESC_ID")
    rows = np.flatnonzero(
        _scan_keep(ms, scan, (fields == field_id) & (dd_spw[ddid] == spw))
    )
    if not len(rows):
        raise ValueError(f"no rows of field {field_id} in spectral window {spw}")
    with core_ms.open_table(ms) as t:
        sigma_column = "SIGMA_SPECTRUM" if "SIGMA_SPECTRUM" in t.colnames() else "SIGMA"
    tables = [
        t if isinstance(t, caltable.CalTable) else caltable.read(t) for t in gaintable
    ]
    fld = _Field(
        ms, rows, data_column=data_column, model=model, model_column=model_column,
        weight_column=weight_column, sigma_column=sigma_column, tables=tables,
        interp=interp, nant=nant, field_id=field_id, solved="G", freq=freq,
        uvrange=uvrange,
    )  # fmt: skip
    m = fld.meta
    tb, keys = solint_bins(m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], solint, combine)
    sol, row_w = _solve_gain_field(
        fld, tb, nchan=len(freq), per_channel=False, budget=budget,
        what=f"gaincal field {field_id}", nant=nant, calmode=calmode, refant=refants,
        refantmode=refantmode, minsnr=minsnr, minblperant=minblperant,
        positions=positions, casa_rules=casa_rules, max_iterations=max_iterations,
        stop_criterion=stop_criterion, stop_fraction=stop_fraction,
    )  # fmt: skip
    if sol.flags.all():
        raise RuntimeError(
            f"gaincal wrote no solutions for field {field_id} (every solution flagged)"
        )
    times, span = fld.solution_times(tb, row_w, len(keys))
    scans = fld.scans(tb, len(keys))
    table = to_caltable(
        sol, times, span, scans, field_id=field_id, ms=ms, chan_freq=freq, spw=spw
    )
    info = {
        "rows": len(rows),
        "row_index": rows,
        "intervals": keys,
        "time_bin": tb,
        "frequency": freq,
        "spw": spw,
    }
    return table, sol, info


def to_caltable(sol, times, intervals, scans, *, field_id, ms, chan_freq, spw=0):
    """The CASA `G Jones` table of `sol` (one frequency bin): one row per
    (interval, antenna), ANTENNA2 the refant used, PARAMERR and SNR from the
    solve, FLAG per hand."""
    if sol.gains.shape[1] != 1:
        raise ValueError(
            "a G table has one frequency bin; frequency chunks are not CASA's"
        )
    ntime, _, nant, _ = sol.gains.shape
    subtables = caltable.subtables_from_ms(ms, single_channel=True)
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
            sol.gains[t, 0, a].astype(np.complex64).reshape(1, 2)
            for t, a in zip(t_idx, a_idx)
        ],
        "PARAMERR": [
            sol.err[t, 0, a].astype(np.float32).reshape(1, 2)
            for t, a in zip(t_idx, a_idx)
        ],
        "FLAG": [sol.flags[t, 0, a].reshape(1, 2) for t, a in zip(t_idx, a_idx)],
        "SNR": [
            sol.snr[t, 0, a].astype(np.float32).reshape(1, 2)
            for t, a in zip(t_idx, a_idx)
        ],
        "WEIGHT": [None] * n,
    }
    keywords = {
        "ParType": "Complex",
        "MSName": str(Path(ms).name),
        "VisCal": "G Jones",
        "PolBasis": "unknown",
        "CASA_Version": "6.7.6-14",
    }
    return caltable.CalTable(
        "G Jones", main, subtables, keywords, ["Calibration", "G Jones", ""]
    )


def baseline_products(gains, flags, pairs=None):
    """Parallel-hand products `g_p,h conj(g_q,h)` over antenna pairs
    `p < q` (all, or `pairs`), shape `(interval, freq bin, pair, hand)`, and
    their validity (both unflagged and finite)."""
    nant = gains.shape[2]
    if pairs is None:
        pairs = [(p, q) for p in range(nant) for q in range(p + 1, nant)]
    p, q = np.array(pairs).T
    prod = gains[:, :, p, :] * np.conj(gains[:, :, q, :])
    ok = ~flags[:, :, p, :] & ~flags[:, :, q, :] & np.isfinite(prod)
    return prod, ok, pairs


__all__ = [
    "GainSolution",
    "baseline_products",
    "gaincal",
    "parse_solint",
    "solint_bins",
    "solution_times",
    "solve",
    "to_caltable",
    "uvrange_keep",
]
