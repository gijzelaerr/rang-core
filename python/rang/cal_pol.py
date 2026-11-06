"""The polarisation terms Gpol, KCROSS, Xf and Df with the parallactic angle
P (task C6, research/c6-polterms.md; C1 terms T6 and T8 to T11,
research/c1-calibration-chain.md).

CARACal's strategy 1 (`polcal_worker.py` at 8f7bb363, C1 steps 12 to 15),
each term a library function on one field of a one-window MS, solved with
earlier tables pre-applied as CASA does (`VisEquation::collapse2`: tables of
a lower VisCal type correct the data, the others corrupt the model; P,
type 7, always corrupts the model, first):

- `gpol(...)`: `gaincal(gaintype='G', calmode='p', parang=True)`, i.e.
  `rang.cal_gain.gaincal` with the P-rotated model;
- `kcross(...)`: `gaincal(gaintype='KCROSS', parang=True)`, CASA's FFT
  estimator (`core/src/cal/crosshand.rs`); a `Kcross Jones` table;
- `xf(...)`: `polcal(poltype='Xf')`, CASA's closed form
  (`crosshand.rs`); an `Xf Jones` table with `ANTENNA2 = -1`;
- `df(...)`: `polcal(poltype='Df')`, the linearised leakage by weighted
  least squares (`core/src/cal/leakage.rs`) with CASA's subtractive
  reference; a `Df Jones` table; `clip_df` is CARACal's
  `flagdata(mode='clip', clipminmax=[-0.6, 0.6])` on it.

`parallactic_angles(...)` gives per row the angle `a = q + RECEPTOR_ANGLE`
of both antennas in the chosen frame, `rotate(...)` applies P in the Rust
kernel (`core/src/cal/parang.rs`), and `apply(...)` corrects or corrupts
by tables (`rang.cal_apply`) and P in CASA's order.

**The parallactic-angle frame (provisional, owner decision; A1 section 7.2):**
`frame='casa'` (the default) is the hour-angle formula on astropy's apparent
(TETE) place with apparent sidereal time and each antenna's **geocentric**
latitude, from apparent north, which A1 measured to reproduce CASA
6.7.6.14's `parang=True` to a few 1e-4 degrees; `frame='rang'` is
`rang.measures.parallactic_angle` (geodetic, ICRS north), rang's frozen
convention before this task. They differ by up to about 0.5 degrees near
the zenith.

Not here: the wiring into `rang-core calibrate` (task C2e owns the command;
proposed in the note), the polarised calibrator models (task C7a),
strategies 2 and 3 (`Dflls`, `Xfparang+QU`; C1 O3), several windows, and
`preavg` (rang solves the cells; for a model constant over the interval
the least-squares answer is the same, see the note).
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import cal_apply, cal_gain, core_ms
from .formats import caltable

FRAMES = ("casa", "rang")
MJD_SECONDS = 86400.0


# -- the parallactic angle --------------------------------------------------


def parallactic_angle_casa(times_mjd_s, ra_rad, dec_rad, itrf_xyz_m):
    """The angle CASA's `parang=True` was measured to use (A1 section 7.2):
    the hour-angle formula on the apparent (TETE) place, apparent sidereal
    time, the **geocentric** latitude of the antenna, from apparent north."""
    from astropy import units
    from astropy.coordinates import TETE, EarthLocation, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False
    times = np.atleast_1d(np.asarray(times_mjd_s, float))
    x, y, z = (float(v) for v in itrf_xyz_m)
    when = Time(times / MJD_SECONDS, format="mjd", scale="utc")
    loc = EarthLocation.from_geocentric(x, y, z, unit=units.m)
    app = SkyCoord(ra_rad * units.rad, dec_rad * units.rad, frame="icrs").transform_to(
        TETE(obstime=when, location=loc)
    )
    h = when.sidereal_time("apparent", longitude=loc.lon).rad - app.ra.rad
    phi = np.arctan2(z, np.hypot(x, y))
    d = app.dec.rad
    return np.arctan2(np.sin(h), np.tan(phi) * np.cos(d) - np.sin(d) * np.cos(h))


def parallactic_angle(times_mjd_s, ra_rad, dec_rad, itrf_xyz_m, frame="casa"):
    """The parallactic angle q (rad) of one antenna at each time."""
    if frame == "casa":
        return parallactic_angle_casa(times_mjd_s, ra_rad, dec_rad, itrf_xyz_m)
    if frame == "rang":
        from . import measures

        return measures.parallactic_angle(times_mjd_s, ra_rad, dec_rad, itrf_xyz_m)
    raise ValueError(f"frame must be one of {FRAMES}")


def receptor_angles(ms):
    """FEED RECEPTOR_ANGLE of the first receptor per antenna (rad); CASA's
    P for linear feeds uses `q + RECEPTOR_ANGLE[0]` (A1 section 2.1)."""
    with core_ms.open_table(Path(ms) / "ANTENNA") as t:
        nant = len(t.getcol("NAME"))
    with core_ms.open_table(Path(ms) / "FEED") as t:
        ant = np.asarray(t.getcol("ANTENNA_ID"))
        ang = np.asarray(t.getcol("RECEPTOR_ANGLE"), float)
    out = np.full(nant, np.nan)
    for a, row in zip(ant, ang):
        if np.isnan(out[a]):
            out[a] = row[0]
    if np.isnan(out).any():
        raise ValueError("FEED has no row for some antennas")
    return out


def row_angles(
    ms, time, antenna1, antenna2, field_id, frame="casa", receptor_angle=None
):
    """Per row the angles `a_p`, `a_q` (rad) of P for ANTENNA1 and ANTENNA2:
    the parallactic angle of field `field_id`'s PHASE_DIR at each antenna and
    time, plus the antenna's receptor angle. `receptor_angle` (rad; task
    C6w) replaces FEED's RECEPTOR_ANGLE for every antenna, in memory, as
    CARACal's `feed_angle_rotation` sets it on both receptors of a copy."""
    ms = Path(ms)
    with core_ms.open_table(ms / "ANTENNA") as t:
        xyz = np.asarray(t.getcol("POSITION"), float)
    with core_ms.open_table(ms / "FIELD") as t:
        ra, dec = np.asarray(t.getcol("PHASE_DIR"), float)[int(field_id)].reshape(-1)[
            :2
        ]
    recept = receptor_angles(ms)
    if receptor_angle is not None:
        recept = np.full(len(recept), float(receptor_angle))
    time = np.asarray(time, float)
    a1 = np.asarray(antenna1, np.int64)
    a2 = np.asarray(antenna2, np.int64)
    times, tindex = np.unique(time, return_inverse=True)
    used = np.union1d(a1, a2)
    q = np.zeros((len(times), len(xyz)))
    for a in used:
        q[:, a] = parallactic_angle(times, ra, dec, xyz[a], frame) + recept[a]
    return q[tindex, a1], q[tindex, a2]


def _ext():
    from rang import core

    return core.extension()


def rotate(data, angle_p, angle_q, inverse=False):
    """P on visibilities `(row, chan, 4)`: `P_p V P_q^T` (corrupt), or the
    inverse (`inverse=True`, correct); returns complex64."""
    data = np.ascontiguousarray(data, np.complex64)
    if data.ndim != 3 or data.shape[2] != 4:
        raise ValueError("data must be (row, chan, 4)")
    out = np.empty_like(data)
    _ext().cal_parang_rotate(
        data.shape[0],
        data.shape[1],
        data.view(np.float32).reshape(-1),
        np.ascontiguousarray(angle_p, np.float64),
        np.ascontiguousarray(angle_q, np.float64),
        bool(inverse),
        out.view(np.float32).reshape(-1),
    )
    return out


def apply(
    data,
    flag,
    time,
    antenna1,
    antenna2,
    frequencies,
    tables,
    *,
    angles=None,
    direction="correct",
    interp="linear",
    field_id=0,
    nant=None,
    table_fields=None,
):
    """Correct (or corrupt) by `tables` and, when `angles` (`(a_p, a_q)` per
    row) are given, by P in CASA's order: P is applied last when correcting
    and first when corrupting, and never flags."""
    tables = list(tables)
    data = np.asarray(data)
    flag = np.broadcast_to(np.asarray(flag, bool), data.shape)
    if direction == "corrupt" and angles is not None:
        data = rotate(data, *angles)
    if tables:
        data, flag = cal_apply.apply(
            data,
            flag,
            time,
            antenna1,
            antenna2,
            frequencies,
            tables,
            field_id=field_id,
            interp=interp,
            direction=direction,
            nant=nant,
            table_fields=table_fields,
        )
    if direction == "correct" and angles is not None:
        data = rotate(data, *angles, inverse=True)
    return np.asarray(data, np.complex64), np.asarray(flag, bool)


# -- loading one field with the pre-apply -----------------------------------


@dataclass
class Loaded:
    """One field's rows, the data corrected and the model corrupted for a
    solve of type `solved`, and the solution intervals."""

    ms: Path
    field_id: int
    rows: np.ndarray
    cols: dict
    data: np.ndarray
    model: np.ndarray
    weights: np.ndarray
    flag: np.ndarray
    flag_row: np.ndarray
    freq: np.ndarray
    nant: int
    names: list
    positions: np.ndarray
    time_bin: np.ndarray
    keys: list
    angles: tuple | None
    settings: dict = field(default_factory=dict)


def load(
    ms,
    *,
    field_id,
    solved,
    solint="inf",
    combine="",
    uvrange="",
    gaintable=(),
    interp="linear",
    parang=True,
    frame="casa",
    data_column="DATA",
    model_column="MODEL_DATA",
    model=None,
    weight_column="WEIGHT_SPECTRUM",
    scan=None,
    receptor_angle=None,
):
    """Read one field of a one-window MS for a solve of VisCal type
    `solved` (`'G'`, `'Kcross'`, `'Xf'`, `'Df'`): the model rotated by P
    (with `parang`) and then corrupted by the higher tables, the data
    corrected by the lower ones (`rang.cal_gain._pre_apply`), the weights
    from SIGMA when tables are pre-applied (as C2a measured for `gaincal`),
    rows outside `uvrange` and autocorrelations flagged by row, and CASA's
    solution intervals. Task C6w: `scan` (SCAN_NUMBERs) restricts the rows,
    `weight_column=None` gives unit weights where `weight_column` would be
    read (WEIGHT is repeated over channels), and `receptor_angle` is
    `row_angles`'."""
    ms = Path(ms)
    with core_ms.open_table(ms / "ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
        positions = np.asarray(t.getcol("POSITION"), float)
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        chan_freq = t.getcol("CHAN_FREQ")
    if len(chan_freq) != 1:
        raise ValueError("one spectral window only (task C6)")
    freq = np.asarray(chan_freq[0], float)
    with core_ms.open_table(ms) as t:
        fields = t.getcol("FIELD_ID")
        sigma_column = "SIGMA_SPECTRUM" if "SIGMA_SPECTRUM" in t.colnames() else "SIGMA"
    rows = np.flatnonzero(cal_gain._scan_keep(ms, scan, fields == field_id))
    if not len(rows):
        raise ValueError(f"no rows of field {field_id}")
    names_cols = [
        "TIME",
        "SCAN_NUMBER",
        "FIELD_ID",
        "ANTENNA1",
        "ANTENNA2",
        "UVW",
        "FLAG",
        "FLAG_ROW",
        data_column,
        *cal_gain._weight_columns(weight_column),
        sigma_column,
    ]
    if model is None:
        names_cols.append(model_column)
    c = cal_gain._ms_columns(ms, names_cols, rows)
    data = np.asarray(c[data_column], np.complex64)
    mdl = np.asarray(c[model_column] if model is None else model, np.complex64)
    if mdl.shape != data.shape:
        raise ValueError("model must be (row, chan, 4) for the field's rows")
    flag = np.asarray(c["FLAG"], bool)
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    flag_row = (
        np.asarray(c["FLAG_ROW"], bool)
        | ~cal_gain.uvrange_keep(c["UVW"], uvrange)
        | (a1 == a2)
    )
    angles = None
    if parang:
        angles = row_angles(ms, c["TIME"], a1, a2, field_id, frame, receptor_angle)
        mdl = rotate(mdl, *angles)
    tables = [
        t if isinstance(t, caltable.CalTable) else caltable.read(t) for t in gaintable
    ]
    if tables:
        data, mdl, flag = cal_gain._pre_apply(
            data,
            mdl,
            flag,
            c["TIME"],
            a1,
            a2,
            freq,
            tables,
            interp,
            len(names),
            field_id,
            solved=solved,
        )
        sigma = np.asarray(c[sigma_column], np.float64)
        if sigma.ndim == 2:
            sigma = np.broadcast_to(sigma[:, None, :], data.shape)
        with np.errstate(divide="ignore"):
            weights = np.where(sigma > 0, 1.0 / sigma**2, 0.0).astype(np.float32)
    elif weight_column is None:
        weights = np.ones(data.shape, np.float32)
    else:
        weights = np.asarray(c[weight_column], np.float32)
        if weights.ndim == 2:  # WEIGHT, repeated over channels (C2e's rule)
            weights = np.broadcast_to(weights[:, None, :], data.shape)
    tb, keys = cal_gain.solint_bins(
        c["TIME"], c["SCAN_NUMBER"], c["FIELD_ID"], solint, combine
    )
    return Loaded(
        ms=ms,
        field_id=int(field_id),
        rows=rows,
        cols=c,
        data=np.ascontiguousarray(data, np.complex64),
        model=np.ascontiguousarray(mdl, np.complex64),
        weights=np.ascontiguousarray(np.broadcast_to(weights, data.shape), np.float32),
        flag=np.ascontiguousarray(flag, bool),
        flag_row=np.ascontiguousarray(flag_row, bool),
        freq=freq,
        nant=len(names),
        names=names,
        positions=positions,
        time_bin=np.asarray(tb, np.int64),
        keys=keys,
        angles=angles,
        settings={
            "solint": solint,
            "combine": combine,
            "uvrange": uvrange,
            "parang": bool(parang),
            "frame": frame,
            "gaintable": [t.vis_cal for t in tables],
            "interp": interp,
            **({} if scan is None else {"scan": [int(s) for s in np.atleast_1d(scan)]}),
            **({} if receptor_angle is None else {"receptor_angle": receptor_angle}),
        },
    )


def _refant_index(names, refant):
    return [
        names.index(r) if isinstance(r, str) else int(r) for r in np.atleast_1d(refant)
    ]


def _times(ld, ntime):
    used = ld.flag | ld.flag_row[:, None, None]
    return cal_gain.solution_times(
        ld.cols["TIME"], ld.time_bin, ld.weights, used, ntime
    )


def _scans(ld, ntime):
    return np.array(
        [ld.cols["SCAN_NUMBER"][ld.time_bin == t].min() for t in range(ntime)]
    )


def _table(kind, ld, values, flags, snr, err, refant, ntime, single_channel):
    """A CASA table of `kind` from `(interval, ant, chan, par)` arrays."""
    times, span = _times(ld, ntime)
    scans = _scans(ld, ntime)
    nant = ld.nant
    t_idx = np.repeat(np.arange(ntime), nant)
    a_idx = np.tile(np.arange(nant), ntime)
    float_param = kind in caltable.FLOAT_KINDS
    dtype = np.float32 if float_param else np.complex64
    refant = np.broadcast_to(np.asarray(refant, np.int64), (ntime,))
    n = len(t_idx)
    main = {
        "TIME": [float(times[t]) for t in t_idx],
        "FIELD_ID": [ld.field_id] * n,
        "SPECTRAL_WINDOW_ID": [0] * n,
        "ANTENNA1": [int(a) for a in a_idx],
        "ANTENNA2": [int(refant[t]) for t in t_idx],
        "INTERVAL": [float(span[t]) for t in t_idx],
        "SCAN_NUMBER": [int(scans[t]) for t in t_idx],
        "OBSERVATION_ID": [0] * n,
        ("FPARAM" if float_param else "CPARAM"): [
            values[t, a].astype(dtype) for t, a in zip(t_idx, a_idx)
        ],
        "PARAMERR": [err[t, a].astype(np.float32) for t, a in zip(t_idx, a_idx)],
        "FLAG": [flags[t, a].astype(bool) for t, a in zip(t_idx, a_idx)],
        "SNR": [snr[t, a].astype(np.float32) for t, a in zip(t_idx, a_idx)],
        "WEIGHT": [None] * n,
    }
    vis_cal = f"{kind} Jones"
    keywords = {
        "ParType": "Float" if float_param else "Complex",
        "MSName": str(ld.ms.name),
        "VisCal": vis_cal,
        "PolBasis": "unknown",
        "CASA_Version": "6.7.6-14",
    }
    subtables = caltable.subtables_from_ms(ld.ms, single_channel=single_channel)
    return caltable.CalTable(
        vis_cal, main, subtables, keywords, ["Calibration", vis_cal, ""]
    )


def _flat(ld):
    """The arrays of a kernel call, rows as loaded."""
    return (
        ld.data.view(np.float32).reshape(-1),
        ld.model.view(np.float32).reshape(-1),
        np.ascontiguousarray(ld.weights.reshape(-1), np.float32),
        np.ascontiguousarray(ld.flag.reshape(-1), np.uint8),
        np.ascontiguousarray(ld.flag_row, np.uint8),
        np.ascontiguousarray(ld.cols["ANTENNA1"], np.uint32),
        np.ascontiguousarray(ld.cols["ANTENNA2"], np.uint32),
        np.ascontiguousarray(ld.time_bin, np.uint32),
    )


# -- Gpol -------------------------------------------------------------------


def gpol(
    ms,
    *,
    field_id,
    solint="60s",
    combine="",
    refant=0,
    refantmode="flex",
    minsnr=3.0,
    minblperant=4,
    uvrange="",
    gaintable=(),
    interp="linear",
    parang=True,
    frame="casa",
    model_column="MODEL_DATA",
    model=None,
    receptor_angle=None,
    **solve_options,
):
    """CARACal's Gpol: `gaincal(gaintype='G', calmode='p', parang=True)` on
    the polarised calibrator. The model is rotated by P here and passed to
    `rang.cal_gain.gaincal`, which pre-applies `gaintable` (G is solved
    with B, K and KCROSS correcting the data and G, Df, Xf corrupting the
    model). Returns `(CalTable, GainSolution, info)`. `solve_options`
    reach `gaincal`; `scan` (task C6w) also selects the model's rows, and
    `receptor_angle` is `row_angles`'."""
    ms = Path(ms)
    with core_ms.open_table(ms) as t:
        fields = t.getcol("FIELD_ID")
    rows = np.flatnonzero(
        cal_gain._scan_keep(ms, solve_options.get("scan"), fields == field_id)
    )
    if model is None:
        model = cal_gain._ms_columns(ms, [model_column], rows)[model_column]
    model = np.asarray(model, np.complex64)
    if parang:
        c = cal_gain._ms_columns(ms, ["TIME", "ANTENNA1", "ANTENNA2"], rows)
        model = rotate(
            model,
            *row_angles(
                ms,
                c["TIME"],
                c["ANTENNA1"],
                c["ANTENNA2"],
                field_id,
                frame,
                receptor_angle,
            ),
        )
    table, sol, info = cal_gain.gaincal(
        ms,
        field_id=field_id,
        solint=solint,
        combine=combine,
        calmode="p",
        refant=refant,
        refantmode=refantmode,
        minsnr=minsnr,
        minblperant=minblperant,
        uvrange=uvrange,
        gaintable=gaintable,
        interp=interp,
        model=model,
        **solve_options,
    )
    info["parang"] = bool(parang)
    info["frame"] = frame
    return table, sol, info


# -- KCROSS -----------------------------------------------------------------


@dataclass
class KcrossSolution:
    delay_ns: np.ndarray
    ok: np.ndarray
    err_ns: np.ndarray
    spectrum: np.ndarray
    settings: dict = field(default_factory=dict)


def kcross_solve(ld):
    """CASA's KCROSS estimator on loaded arrays, one delay per interval."""
    ntime = len(ld.keys)
    nrow, nchan = ld.data.shape[:2]
    delay = np.zeros(ntime)
    ok = np.zeros(ntime, np.uint8)
    err = np.zeros(ntime)
    spec = np.zeros(2 * ntime * nchan)
    _ext().cal_kcross_solve(
        nrow,
        nchan,
        ntime,
        *_flat(ld),
        np.ascontiguousarray(ld.freq, np.float64),
        delay,
        ok,
        err,
        spec,
    )
    return KcrossSolution(
        delay_ns=delay,
        ok=ok.astype(bool),
        err_ns=err,
        spectrum=spec.view(np.complex128).reshape(ntime, nchan),
        settings=dict(ld.settings),
    )


KCROSS_ESTIMATORS = ("casa", "refined")


def kcross_refine(spectrum, freq, tau_ns, iterations=20, tol_ns=1e-9):
    """The delay (ns) that maximises `|sum_c S_c exp(-2 pi i nu_c tau)|`
    over the channels with data (equal weights, as CASA's FFT of the
    normalised spectrum), by Newton steps from `tau_ns` (CASA's FFT and
    parabola). Removes the parabola's bias (up to 2.2e-4 ns, C6 section 9);
    task C6w, `estimator: refined`, owner decision 5 of C6."""
    s = np.asarray(spectrum, np.complex128)
    nu = np.asarray(freq, float)
    use = np.abs(s) > 0
    if use.sum() < 2:
        return float(tau_ns)
    s, nu = s[use], nu[use] - nu[use].mean()
    w = 2 * np.pi * nu
    tau = float(tau_ns) * 1e-9
    for _ in range(iterations):
        e = s * np.exp(-1j * w * tau)
        f0, f1, f2 = e.sum(), (-1j * w * e).sum(), (-(w**2) * e).sum()
        d1 = 2 * (np.conj(f0) * f1).real
        d2 = 2 * (abs(f1) ** 2 + (np.conj(f0) * f2).real)
        if not d2 < 0:
            break
        step = -d1 / d2
        tau += step
        if abs(step) * 1e9 < tol_ns:
            break
    return tau * 1e9


def kcross(
    ms,
    *,
    field_id,
    solint="inf",
    combine="",
    refant=None,
    estimator="casa",
    **load_options,
):
    """CARACal's KCROSS: `gaincal(gaintype='KCROSS', parang=True)`. Returns
    `(CalTable, KcrossSolution, Loaded)`; the table is CASA's `Kcross Jones`
    (`FPARAM (1, 2)`, the delay in ns on X and 0 on Y for every antenna,
    `ANTENNA2 = -1`). `refant` is recorded only: KCROSS has no antenna
    reference, it depends on the refant of the earlier terms. `estimator`
    (task C6w): `casa`, CASA's FFT and parabola; `refined`, then
    `kcross_refine`."""
    if estimator not in KCROSS_ESTIMATORS:
        raise ValueError(f"estimator must be one of {KCROSS_ESTIMATORS}")
    ld = load(
        ms, field_id=field_id, solved="Kcross", solint=solint, combine=combine,
        **load_options,
    )  # fmt: skip
    sol = kcross_solve(ld)
    if estimator == "refined":
        sol.settings["fft_delay_ns"] = sol.delay_ns.tolist()
        sol.delay_ns = np.array(
            [
                kcross_refine(sol.spectrum[t], ld.freq, sol.delay_ns[t])
                if sol.ok[t]
                else sol.delay_ns[t]
                for t in range(len(sol.delay_ns))
            ]
        )
    sol.settings["estimator"] = estimator
    if not sol.ok.any():
        raise RuntimeError(f"KCROSS wrote no solutions for field {field_id}")
    ntime, nant = len(ld.keys), ld.nant
    values = np.zeros((ntime, nant, 1, 2))
    values[:, :, 0, 0] = sol.delay_ns[:, None]
    flags = np.repeat(~sol.ok[:, None, None, None], nant, 1) & np.ones(
        (1, 1, 1, 2), bool
    )
    err = np.zeros((ntime, nant, 1, 2))
    err[:, :, 0, 0] = sol.err_ns[:, None]
    snr = np.zeros((ntime, nant, 1, 2))
    with np.errstate(divide="ignore", invalid="ignore"):
        snr[:, :, 0, 0] = np.where(
            sol.err_ns > 0, np.abs(sol.delay_ns) / sol.err_ns, 0.0
        )[:, None]
    table = _table("Kcross", ld, values, flags, snr, err, -1, ntime, True)
    sol.settings["refant"] = None if refant is None else str(refant)
    return table, sol, ld


# -- Xf ---------------------------------------------------------------------


@dataclass
class XfSolution:
    x: np.ndarray
    ok: np.ndarray
    err: np.ndarray
    settings: dict = field(default_factory=dict)


def xf_solve(ld):
    """CASA's Xf closed form on loaded arrays, per interval and channel."""
    ntime = len(ld.keys)
    nrow, nchan = ld.data.shape[:2]
    x = np.zeros(2 * ntime * nchan)
    ok = np.zeros(ntime * nchan, np.uint8)
    err = np.zeros(ntime * nchan)
    _ext().cal_xf_solve(
        nrow,
        nchan,
        ntime,
        *_flat(ld),
        np.ascontiguousarray(ld.freq, np.float64),
        x,
        ok,
        err,
    )
    return XfSolution(
        x=x.view(np.complex128).reshape(ntime, nchan),
        ok=ok.reshape(ntime, nchan).astype(bool),
        err=err.reshape(ntime, nchan),
        settings=dict(ld.settings),
    )


def xf(ms, *, field_id, solint="inf", combine="scan", **load_options):
    """CARACal's Xf: `polcal(poltype='Xf')` (`parang=True` always). CASA
    ignores the refant for X (`XJones::setSolve`). Returns
    `(CalTable, XfSolution, Loaded)`; the table is CASA's `Xf Jones`
    (`CPARAM (nchan, 1)`, the array value on every antenna,
    `ANTENNA2 = -1`)."""
    ld = load(
        ms, field_id=field_id, solved="Xf", solint=solint, combine=combine,
        **load_options,
    )  # fmt: skip
    sol = xf_solve(ld)
    if not sol.ok.any():
        raise RuntimeError(f"Xf wrote no solutions for field {field_id}")
    ntime, nant = len(ld.keys), ld.nant
    nchan = len(ld.freq)
    values = np.broadcast_to(sol.x[:, None, :, None], (ntime, nant, nchan, 1))
    flags = np.broadcast_to(~sol.ok[:, None, :, None], (ntime, nant, nchan, 1))
    err = np.broadcast_to(sol.err[:, None, :, None], (ntime, nant, nchan, 1))
    with np.errstate(divide="ignore"):
        snr = np.where(err > 0, 1.0 / np.where(err > 0, err, 1), 0.0)
    table = _table("Xf", ld, values, flags, snr, err, -1, ntime, False)
    return table, sol, ld


# -- Df ---------------------------------------------------------------------


@dataclass
class DfSolution:
    """Leakages `(interval, chan, ant, 2)` (d_x, d_y), referenced as CASA
    does, flags, rang's errors and SNR (`1/err`, CASA's `formSolveSNR`)."""

    d: np.ndarray
    flags: np.ndarray
    err: np.ndarray
    snr: np.ndarray
    var_re: np.ndarray
    var_im: np.ndarray
    chi2: np.ndarray
    neq: np.ndarray
    npar: np.ndarray
    refant_used: np.ndarray
    gauge_fixed: bool
    settings: dict = field(default_factory=dict)


def _flex_order(refants, positions):
    """The primary refant(s), then the others by distance from the first
    (CASA's flex priority list)."""
    first = refants[0]
    dist = np.linalg.norm(positions - positions[first], axis=1)
    rest = [int(a) for a in np.argsort(dist, kind="stable") if a not in refants]
    return list(refants) + rest


def unpolarised_gauge(model, flag, tol=1e-6):
    """`(degenerate, rho)`: whether `rho = M_YY / M_XX` is one value over
    the unflagged cells (then the leakages have a free complex number,
    `leakage.rs`), and that value."""
    ok = ~flag[..., 0] & ~flag[..., 3] & (np.abs(model[..., 0]) > 0)
    if not ok.any():
        return True, 1.0
    rho = model[..., 3][ok] / model[..., 0][ok]
    r0 = np.median(rho.real) + 1j * np.median(rho.imag)
    degenerate = bool(np.max(np.abs(rho - r0)) <= tol * max(1.0, abs(r0)))
    return degenerate, complex(r0)


def df_solve(ld, refant=0, minsnr=3.0, minblperant=4):
    """The Df solve on loaded arrays (`leakage.rs`), then CASA's
    subtractive reference and `minsnr` (SNR = 1/err)."""
    ntime = len(ld.keys)
    nrow, nchan = ld.data.shape[:2]
    nant = ld.nant
    refants = _refant_index(ld.names, refant)
    order = _flex_order(refants, ld.positions)
    degenerate, rho = unpolarised_gauge(ld.model, ld.flag | ld.flag_row[:, None, None])
    if degenerate and abs(rho - 1) > 1e-6:
        raise ValueError(
            f"Df: the model's M_YY / M_XX is the constant {rho}, so the leakages "
            "are not determined; a polarised calibrator needs parallactic coverage"
        )
    n = ntime * nchan
    d = np.zeros(4 * n * nant)
    fl = np.zeros(2 * n * nant, np.uint8)
    vr = np.zeros(2 * n * nant)
    vi = np.zeros(2 * n * nant)
    chi2 = np.zeros(n)
    neq = np.zeros(n)
    npar = np.zeros(n)
    gauge = np.zeros(n, np.int64)
    _ext().cal_df_solve(
        nrow,
        nchan,
        ntime,
        nant,
        *_flat(ld),
        int(minblperant),
        bool(degenerate),
        order,
        d,
        fl,
        vr,
        vi,
        chi2,
        neq,
        npar,
        gauge,
    )
    d = d.view(np.complex128).reshape(ntime, nchan, nant, 2)
    flags = fl.reshape(ntime, nchan, nant, 2).astype(bool)
    vr = vr.reshape(ntime, nchan, nant, 2)
    vi = vi.reshape(ntime, nchan, nant, 2)
    chi2 = chi2.reshape(ntime, nchan)
    neq = neq.reshape(ntime, nchan)
    npar = npar.reshape(ntime, nchan)
    gauge = gauge.reshape(ntime, nchan)
    used = gauge.copy()
    if not degenerate:
        # CASA's case D: d_x,p -= d_x,r; d_y,p += conj(d_x,r), per channel, with
        # the first refant of the flex list unflagged in the channel.
        for t in range(ntime):
            for c in range(nchan):
                for r in order:
                    if not flags[t, c, r].any():
                        z = d[t, c, r, 0]
                        d[t, c, :, 0] -= z
                        d[t, c, :, 1] += np.conj(z)
                        used[t, c] = r
                        break
                else:
                    used[t, c] = -1
    red = chi2 / np.maximum(neq - npar, 1)
    err = np.sqrt(np.maximum(red[..., None, None], 0) * (vr + vi) / 2)
    with np.errstate(divide="ignore"):
        snr = np.where(err > 0, 1.0 / np.where(err > 0, err, 1), np.inf)
    # The gauge antenna's d_x is held at 0 (its error 0): it is not a failed
    # solution, as CASA's own error for it, before referencing, is finite.
    good = ~flags & (snr > minsnr)
    flags = ~good
    snr_out = np.where(np.isfinite(snr), snr, 0.0)
    return DfSolution(
        d=d,
        flags=flags,
        err=err,
        snr=snr_out,
        var_re=vr,
        var_im=vi,
        chi2=chi2,
        neq=neq,
        npar=npar,
        refant_used=used,
        gauge_fixed=bool(degenerate),
        settings={
            **ld.settings,
            "refant": refants,
            "minsnr": float(minsnr),
            "minblperant": int(minblperant),
        },
    )


def df(
    ms,
    *,
    field_id,
    solint="inf",
    combine="scan",
    refant=0,
    minsnr=3.0,
    minblperant=4,
    min_data_fraction=None,
    **load_options,
):
    """CARACal's Df: `polcal(poltype='Df')` on the (unpolarised) leakage
    calibrator (`parang=True` always). Returns `(CalTable, DfSolution,
    Loaded)`; the table is CASA's `Df Jones` (`CPARAM (nchan, 2)`,
    `ANTENNA2` the refant used). `min_data_fraction` (task C6w, C6's owner
    decision 3; None: off, the default) flags every leakage of a channel
    and interval whose unflagged cross-hand cells are below that fraction
    of the interval's cross-hand cells (rows not flagged as a whole). This
    is rang's rule: CASA has none (its flags in such channels come from its
    iterative solver, research/c6w-polwire.md)."""
    ld = load(
        ms, field_id=field_id, solved="Df", solint=solint, combine=combine,
        **load_options,
    )  # fmt: skip
    sol = df_solve(ld, refant=refant, minsnr=minsnr, minblperant=minblperant)
    if min_data_fraction is not None:
        frac = data_fraction(ld)
        low = frac < float(min_data_fraction)
        sol.flags = sol.flags | low[:, :, None, None]
        sol.settings["min_data_fraction"] = float(min_data_fraction)
        sol.settings["data_fraction_flagged_channels"] = int(low.sum())
    if sol.flags.all():
        raise RuntimeError(f"Df wrote no solutions for field {field_id}")
    values = sol.d.transpose(0, 2, 1, 3)
    flags = sol.flags.transpose(0, 2, 1, 3)
    err = sol.err.transpose(0, 2, 1, 3)
    snr = sol.snr.transpose(0, 2, 1, 3)
    used = sol.refant_used
    ref = np.array([int(u[u >= 0][0]) if (u >= 0).any() else -1 for u in used])
    table = _table("Df", ld, values, flags, snr, err, ref, len(ld.keys), False)
    return table, sol, ld


def data_fraction(ld):
    """`(interval, chan)`: unflagged cross-hand cells over the cross-hand
    cells of the rows not flagged as a whole (Df's `min_data_fraction`)."""
    ntime = len(ld.keys)
    live = ~ld.flag_row
    cross = ~ld.flag[:, :, 1:3]  # (row, chan, 2)
    good = np.zeros((ntime, ld.flag.shape[1]))
    total = np.zeros(ntime)
    np.add.at(good, ld.time_bin[live], cross[live].sum(axis=-1))
    np.add.at(total, ld.time_bin[live], 2.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(total[:, None] > 0, good / total[:, None], 0.0)


def clip_df(table, limit=0.6):
    """CARACal's `flagdata(vis=Df, mode='clip', clipminmax=[-0.6, 0.6],
    datacolumn='CPARAM')`: flag leakages whose amplitude exceeds `limit`.
    Returns a new table and the number of newly flagged parameters."""
    params = table.params
    flags = table.flags
    new = flags | (np.abs(params) > limit)
    main = dict(table.main)
    main["FLAG"] = [f for f in new]
    out = caltable.CalTable(
        table.vis_cal, main, table.subtables, dict(table.keywords), list(table.info)
    )
    return out, int(new.sum() - flags.sum())


__all__ = [
    "FRAMES",
    "KCROSS_ESTIMATORS",
    "DfSolution",
    "KcrossSolution",
    "Loaded",
    "XfSolution",
    "apply",
    "clip_df",
    "data_fraction",
    "df",
    "df_solve",
    "gpol",
    "kcross",
    "kcross_refine",
    "kcross_solve",
    "load",
    "parallactic_angle",
    "parallactic_angle_casa",
    "receptor_angles",
    "rotate",
    "row_angles",
    "unpolarised_gauge",
    "xf",
    "xf_solve",
]
