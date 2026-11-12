# SPDX-License-Identifier: GPL-3.0-or-later
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

`rang-core calibrate` runs these terms from its polcal section through
`rang.cal_chain.run`, and `rang-core apply` applies P with
`rang.applycal.applycal(parang=True)` (task C6w, research/c6w-polwire.md);
the polarised calibrator models are C7a's `rang.calmodels.NRAO_XCAL`.

Not here: strategies 2 and 3 (`Dflls`, `Xfparang+QU`; C1 O3), several windows, and
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


LINEAR_FEEDS = ("X", "Y")


def feed_types(ms):
    """FEED POLARIZATION_TYPE per row as a tuple (None for a row without
    one), or None when FEED has no such column."""
    with core_ms.open_table(Path(ms) / "FEED") as t:
        if "POLARIZATION_TYPE" not in t.columns:
            return None
        return _cells(t, "POLARIZATION_TYPE")


def _cells(table, name):
    """Each row of a 1-D string-array column as a tuple, None for an
    undefined cell: one read, or row by row when cells are undefined or
    differ in shape."""
    try:
        return [tuple(r) for r in table.getcol(name).tolist()]
    except OSError:
        out = []
        for row in range(table.nrows):
            try:
                out.append(tuple(table.getcol(name, row, 1)[0].tolist()))
            except OSError:
                out.append(None)
        return out


def receptor_angles(ms):
    """FEED RECEPTOR_ANGLE of the first receptor per antenna (rad); CASA's
    P for linear feeds uses `q + RECEPTOR_ANGLE[0]` (A1 section 2.1), so a
    FEED whose POLARIZATION_TYPE is not X, Y is refused
    (research/feed-poltype-read.md)."""
    types = feed_types(ms) or []
    # Rows without a value, or with empty strings only, are not checked.
    other = sorted({p for p in types if p and any(p) and p != LINEAR_FEEDS})
    if other:
        raise ValueError(
            f"{ms}: FEED POLARIZATION_TYPE {[list(p) for p in other]}; P is "
            "implemented for MeerKAT's linear feeds (X, Y) only "
            "(research/meerkat-scope.md)"
        )
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
    table = angle_table(ms, time, antenna1, antenna2, field_id, frame, receptor_angle)
    return table_angles(table, time, antenna1, antenna2)


def angle_table(
    ms, time, antenna1, antenna2, field_id, frame="casa", receptor_angle=None
):
    """`row_angles`' angles per unique time and antenna (task W3b): `(times,
    q)` with `q[t, a]` the angle of antenna `a` (0 for antennas in neither
    column) at `times[t]`, the unique values of `time`. `table_angles`
    looks rows up in it, so no per-row array of a field is needed."""
    time = np.asarray(time, float)
    used = np.union1d(np.asarray(antenna1, np.int64), np.asarray(antenna2, np.int64))
    return angle_table_at(ms, np.unique(time), used, field_id, frame, receptor_angle)


def angle_table_at(ms, times, used, field_id, frame="casa", receptor_angle=None):
    """`angle_table` from the sorted unique `times` and the antennas `used`
    (task W3b: `rang.applycal` collects them chunk by chunk)."""
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
    times = np.asarray(times, float)
    q = np.zeros((len(times), len(xyz)))
    for a in np.asarray(used, np.int64):
        q[:, a] = parallactic_angle(times, ra, dec, xyz[a], frame) + recept[a]
    return times, q


def table_angles(table, time, antenna1, antenna2):
    """The angles `(a_p, a_q)` of rows from an `angle_table`."""
    times, q = table
    tindex = np.searchsorted(times, np.asarray(time, float))
    a1 = np.asarray(antenna1, np.int64)
    a2 = np.asarray(antenna2, np.int64)
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
    # Task W3b: a chunked solve keeps no cell arrays here (data, model,
    # weights and flag None) but each row's weight sum for the solution
    # times (`rang.cal_gain.row_weights`).
    row_weights: np.ndarray | None = None


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
    fld = _PolField(
        ms, field_id=field_id, solved=solved, solint=solint, combine=combine,
        uvrange=uvrange, gaintable=gaintable, interp=interp, parang=parang,
        frame=frame, data_column=data_column, model_column=model_column,
        model=model, weight_column=weight_column, scan=scan,
        receptor_angle=receptor_angle,
    )  # fmt: skip
    return _load_whole(fld)


class _PolField:
    """`load`'s field (task W3b, research/w3b-chainchunks.md): the row
    metadata, intervals and P's angle table, read whole; the cell arrays
    prepared per chunk of rows by `prepare`, as `load` prepares them."""

    def __init__(
        self, ms, *, field_id, solved, solint, combine, uvrange, gaintable, interp,
        parang, frame, data_column, model_column, model, weight_column, scan,
        receptor_angle,
    ):  # fmt: skip
        ms = Path(ms)
        with core_ms.open_table(ms / "ANTENNA") as t:
            self.names = [str(n) for n in t.getcol("NAME")]
            self.positions = np.asarray(t.getcol("POSITION"), float)
        with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
            chan_freq = t.getcol("CHAN_FREQ")
        if len(chan_freq) != 1:
            raise ValueError("one spectral window only (task C6)")
        self.freq = np.asarray(chan_freq[0], float)
        with core_ms.open_table(ms) as t:
            fields = t.getcol("FIELD_ID")
            sigma_column = (
                "SIGMA_SPECTRUM" if "SIGMA_SPECTRUM" in t.colnames() else "SIGMA"
            )
        rows = np.flatnonzero(cal_gain._scan_keep(ms, scan, fields == field_id))
        if not len(rows):
            raise ValueError(f"no rows of field {field_id}")
        self.ms, self.rows, self.field_id = ms, rows, int(field_id)
        self.meta = cal_gain._ms_columns(ms, cal_gain.META_COLUMNS, rows)
        m = self.meta
        a1, a2 = m["ANTENNA1"], m["ANTENNA2"]
        self.flag_row = (
            np.asarray(m["FLAG_ROW"], bool)
            | ~cal_gain.uvrange_keep(m["UVW"], uvrange)
            | (a1 == a2)
        )
        self.table = (
            angle_table(ms, m["TIME"], a1, a2, field_id, frame, receptor_angle)
            if parang
            else None
        )
        self.tables = [
            t if isinstance(t, caltable.CalTable) else caltable.read(t)
            for t in gaintable
        ]
        self.cells = ["FLAG", data_column, *cal_gain._weight_columns(weight_column)]
        self.cells.append(sigma_column)
        if model is None:
            self.cells.append(model_column)
        self.data_column, self.model_column, self.model = (
            data_column,
            model_column,
            model,
        )
        self.weight_column, self.sigma_column = weight_column, sigma_column
        self.solved, self.interp = solved, interp
        tb, keys = cal_gain.solint_bins(
            m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], solint, combine
        )
        self.time_bin, self.keys = np.asarray(tb, np.int64), keys
        self.settings = {
            "solint": solint,
            "combine": combine,
            "uvrange": uvrange,
            "parang": bool(parang),
            "frame": frame,
            "gaintable": [t.vis_cal for t in self.tables],
            "interp": interp,
            **({} if scan is None else {"scan": [int(s) for s in np.atleast_1d(scan)]}),
            **({} if receptor_angle is None else {"receptor_angle": receptor_angle}),
        }

    def prepare(self, pos, c, chans=None):
        """The arrays of field rows `pos` from their cell columns `c`;
        `chans` (a slice): the cell columns and the arrays hold only those
        channels (research/sliced-read.md)."""
        m = self.meta
        data = np.asarray(c[self.data_column], np.complex64)
        if self.model is None:
            mdl = c[self.model_column]
        else:
            mdl = cal_gain._model_rows(self.model, pos, len(self.rows))
            if chans is not None:
                mdl = np.asarray(mdl)[:, chans]
        mdl = np.asarray(mdl, np.complex64)
        if mdl.shape != data.shape:
            raise ValueError("model must be (row, chan, 4) for the field's rows")
        flag = np.asarray(c["FLAG"], bool)
        a1, a2 = m["ANTENNA1"][pos], m["ANTENNA2"][pos]
        angles = None
        if self.table is not None:
            angles = table_angles(self.table, m["TIME"][pos], a1, a2)
            mdl = rotate(mdl, *angles)
        if self.tables:
            data, mdl, flag = cal_gain._pre_apply(
                data,
                mdl,
                flag,
                m["TIME"][pos],
                a1,
                a2,
                self.freq,
                self.tables,
                self.interp,
                len(self.names),
                self.field_id,
                solved=self.solved,
                channels=chans,
            )
            sigma = np.asarray(c[self.sigma_column], np.float64)
            if sigma.ndim == 2:
                sigma = np.broadcast_to(sigma[:, None, :], data.shape)
            with np.errstate(divide="ignore"):
                weights = np.where(sigma > 0, 1.0 / sigma**2, 0.0).astype(np.float32)
        elif self.weight_column is None:
            weights = np.ones(data.shape, np.float32)
        else:
            weights = np.asarray(c[self.weight_column], np.float32)
            if weights.ndim == 2:  # WEIGHT, repeated over channels (C2e's rule)
                weights = np.broadcast_to(weights[:, None, :], data.shape)
        weights = np.ascontiguousarray(np.broadcast_to(weights, data.shape), np.float32)
        flag = np.ascontiguousarray(flag, bool)
        used = flag | self.flag_row[pos][:, None, None]
        return {
            "data": np.ascontiguousarray(data, np.complex64),
            "model": np.ascontiguousarray(mdl, np.complex64),
            "weights": weights,
            "flag": flag,
            "row_w": cal_gain.row_weights(weights, used),
            "angles": angles,
        }

    def loaded(self, arr, *, cols=None, angles=None):
        """The `Loaded` of the whole field from `prepare`'s arrays, or a
        metadata-only one (`arr` None) carrying the rows' weight sums."""
        whole = arr is not None and "data" in arr
        return Loaded(
            ms=self.ms,
            field_id=self.field_id,
            rows=self.rows,
            cols=self.meta if cols is None else cols,
            data=arr["data"] if whole else None,
            model=arr["model"] if whole else None,
            weights=arr["weights"] if whole else None,
            flag=arr["flag"] if whole else None,
            flag_row=np.ascontiguousarray(self.flag_row, bool),
            freq=self.freq,
            nant=len(self.names),
            names=self.names,
            positions=self.positions,
            time_bin=self.time_bin,
            keys=self.keys,
            angles=angles,
            settings=dict(self.settings),
            row_weights=None if whole else arr["row_w"],
        )

    def chunk_loaded(self, chunk, arr):
        """A `Loaded` of one chunk (`rang.cal_chunks.Chunk`) for the
        kernels: its rows, intervals and channels (task E2: of the averaged
        rows when the field is averaged; `rows` then the chunk's averaged
        row indices)."""
        pos = chunk.pos
        avg = getattr(self, "average", None)
        if avg is None:
            m = self.meta
            rows, a1, a2 = self.rows[pos], m["ANTENNA1"][pos], m["ANTENNA2"][pos]
            flag_row, time_bin = self.flag_row[pos], self.time_bin[pos]
        else:
            rows, a1, a2 = np.asarray(pos), avg.antenna1[pos], avg.antenna2[pos]
            flag_row, time_bin = avg.flag_row[pos], avg.time_bin[pos]
        return Loaded(
            ms=self.ms,
            field_id=self.field_id,
            rows=rows,
            cols={"ANTENNA1": a1, "ANTENNA2": a2},
            data=arr["data"],
            model=arr["model"],
            weights=arr["weights"],
            flag=arr["flag"],
            flag_row=np.ascontiguousarray(flag_row, bool),
            freq=self.freq[chunk.chans],
            nant=len(self.names),
            names=self.names,
            positions=self.positions,
            time_bin=time_bin - chunk.t0,
            keys=self.keys[chunk.t0 : chunk.t1],
            angles=None,
            settings=dict(self.settings),
        )

    def chunks(self, budget, *, per_channel, what, average=False):
        """`rang.cal_chunks.plan` of this field, and the chunk loader.
        `average` (task E2, `calibrate.average_time`): chunks of the rows
        averaged in time within each interval (`rang.cal_chunks.Average`),
        each chunk read in blocks of source rows prepared by `prepare` (the
        model rotated by P and the tables pre-applied per row) before the
        averaging."""
        from . import cal_chunks

        if average:
            m = self.meta
            avg = cal_chunks.Average(
                self.time_bin, m["ANTENNA1"], m["ANTENNA2"], self.flag_row
            )
            self.average = avg
            chunks, block = cal_chunks.plan(
                avg.time_bin, len(self.freq), 4, budget, per_channel=per_channel,
                what=what, average=avg,
            )  # fmt: skip

            kept = {}

            def get_averaged(reader, chunk):
                # One chunk is averaged once (Df reads its chunks four times).
                if len(chunks) == 1 and kept:
                    return dict(kept)
                arr = cal_chunks.load_averaged(
                    reader, self.rows, chunk, self.cells, self._prep, block, avg
                )
                if len(chunks) == 1:
                    kept.update(arr)
                return arr

            return chunks, get_averaged
        chunks, block = cal_chunks.plan(
            self.time_bin, len(self.freq), 4, budget, per_channel=per_channel, what=what
        )

        def get(reader, chunk):
            arr = cal_chunks.load(
                reader, self.rows, chunk, self.cells, self._prep, block
            )
            return arr

        return chunks, get

    def _prep(self, pos, c, chans=None):
        arr = self.prepare(pos, c, chans=chans)
        del arr["angles"]
        return arr


def _refant_index(names, refant):
    return [
        names.index(r) if isinstance(r, str) else int(r) for r in np.atleast_1d(refant)
    ]


def _chunked(ms, budget, *, per_channel, what, average_time=False, **load_options):
    """`load`, or with `budget` (task W3b) the field's `_PolField` and its
    chunks: `(Loaded, None)` when the field is one chunk, else
    `(_PolField, (chunks, get))`. With `average_time` (task E2) always the
    chunks, of the time-averaged rows (`budget` None: one chunk)."""
    if average_time:
        fld = _PolField(ms, **_load_defaults(load_options))
        chunks, get = fld.chunks(
            budget, per_channel=per_channel, what=what, average=True
        )
        return fld, (chunks, get)
    if budget is None:
        return load(ms, **load_options), None
    fld = _PolField(ms, **_load_defaults(load_options))
    chunks, get = fld.chunks(budget, per_channel=per_channel, what=what)
    if len(chunks) == 1:
        return _load_whole(fld), None
    return fld, (chunks, get)


def _load_defaults(options):
    out = {
        "solint": "inf", "combine": "", "uvrange": "", "gaintable": (),
        "interp": "linear", "parang": True, "frame": "casa", "data_column": "DATA",
        "model_column": "MODEL_DATA", "model": None,
        "weight_column": "WEIGHT_SPECTRUM", "scan": None, "receptor_angle": None,
    }  # fmt: skip
    out.update(options)
    return out


def _load_whole(fld):
    pos = np.arange(len(fld.rows))
    cols = cal_gain._ms_columns(fld.ms, fld.cells, fld.rows)
    arr = fld.prepare(pos, cols)
    c = dict(fld.meta)
    c.update(cols)
    return fld.loaded(arr, cols=c, angles=arr.pop("angles"))


def _each_chunk(fld, chunks, get, row_w=None):
    """`(chunk, Loaded of the chunk)` for every chunk, the rows' weight sums
    stored into `row_w`."""
    with core_ms.open_table(fld.ms) as reader:
        for c in chunks:
            arr = get(reader, c)
            if row_w is not None:
                row_w[arr.get("src", c.pos)] = arr["row_w"]
            yield c, fld.chunk_loaded(c, arr)
            del arr


def _times(ld, ntime):
    if ld.row_weights is not None:  # a chunked solve (task W3b)
        return cal_gain.times_from_row_weights(
            ld.cols["TIME"], ld.time_bin, ld.row_weights, ntime
        )
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
    if solve_options.get("budget") is not None:
        # Task W3b: the model is read and rotated per chunk, by P's angle
        # table over the field's rows (the angles `row_angles` gives).
        given = model
        table = None
        if parang:
            c = cal_gain._ms_columns(ms, ["TIME", "ANTENNA1", "ANTENNA2"], rows)
            table = angle_table(
                ms, c["TIME"], c["ANTENNA1"], c["ANTENNA2"], field_id, frame,
                receptor_angle,
            )  # fmt: skip

        def model(pos):
            from . import core_chunks

            if given is None:
                with core_ms.open_table(ms) as t:
                    part = core_chunks.read_rows(t, model_column, rows[pos])
            else:
                part = cal_gain._model_rows(given, pos, len(rows))
            part = np.asarray(part, np.complex64)
            if table is not None:
                part = rotate(
                    part, *table_angles(table, c["TIME"][pos], c["ANTENNA1"][pos],
                                        c["ANTENNA2"][pos])
                )  # fmt: skip
            return part

        parang_done = True
    else:
        parang_done = False
    if not parang_done and model is None:
        model = cal_gain._ms_columns(ms, [model_column], rows)[model_column]
    if not parang_done:
        model = np.asarray(model, np.complex64)
    if parang and not parang_done:
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
    budget=None,
    average_time=False,
    **load_options,
):
    """CARACal's KCROSS: `gaincal(gaintype='KCROSS', parang=True)`. Returns
    `(CalTable, KcrossSolution, Loaded)`; the table is CASA's `Kcross Jones`
    (`FPARAM (1, 2)`, the delay in ns on X and 0 on Y for every antenna,
    `ANTENNA2 = -1`). `refant` is recorded only: KCROSS has no antenna
    reference, it depends on the refant of the earlier terms. `estimator`
    (task C6w): `casa`, CASA's FFT and parabola; `refined`, then
    `kcross_refine`. `average_time` (task E2): solve on the rows averaged
    in time within each interval, after P and the pre-apply per row."""
    if estimator not in KCROSS_ESTIMATORS:
        raise ValueError(f"estimator must be one of {KCROSS_ESTIMATORS}")
    ld, parts = _chunked(
        ms, budget, per_channel=False, what=f"KCROSS field {field_id}",
        field_id=field_id, solved="Kcross", solint=solint, combine=combine,
        average_time=average_time, **load_options,
    )  # fmt: skip
    if parts is None:
        sol = kcross_solve(ld)
    else:  # task W3b: one delay per interval, chunks of whole intervals
        fld, (chunks, get) = ld, parts
        row_w = np.zeros(len(fld.rows))
        got = [kcross_solve(c_ld) for _, c_ld in _each_chunk(fld, chunks, get, row_w)]
        sol = KcrossSolution(
            delay_ns=np.concatenate([s.delay_ns for s in got]),
            ok=np.concatenate([s.ok for s in got]),
            err_ns=np.concatenate([s.err_ns for s in got]),
            spectrum=np.concatenate([s.spectrum for s in got]),
            settings=dict(fld.settings),
        )
        del got
        ld = fld.loaded({"row_w": row_w})
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


def _place(out, chunk, values):
    """Put a chunk's `(interval, chan, ...)` values into the whole array."""
    out[chunk.t0 : chunk.t1, chunk.chans] = values


def xf(
    ms, *, field_id, solint="inf", combine="scan", budget=None, average_time=False,
    **load_options,
):  # fmt: skip
    """CARACal's Xf: `polcal(poltype='Xf')` (`parang=True` always). CASA
    ignores the refant for X (`XJones::setSolve`). Returns
    `(CalTable, XfSolution, Loaded)`; the table is CASA's `Xf Jones`
    (`CPARAM (nchan, 1)`, the array value on every antenna,
    `ANTENNA2 = -1`). `budget` (task W3b): chunks of whole intervals or of
    channels of one interval (Xf is per interval and channel).
    `average_time` (task E2) as `kcross`."""
    ld, parts = _chunked(
        ms, budget, per_channel=True, what=f"Xf field {field_id}",
        field_id=field_id, solved="Xf", solint=solint, combine=combine,
        average_time=average_time, **load_options,
    )  # fmt: skip
    if parts is None:
        sol = xf_solve(ld)
    else:
        fld, (chunks, get) = ld, parts
        shape = (len(fld.keys), len(fld.freq))
        x = np.empty(shape, np.complex128)
        ok = np.empty(shape, bool)
        err = np.empty(shape)
        row_w = np.zeros(len(fld.rows))
        for c, c_ld in _each_chunk(fld, chunks, get, row_w):
            s = xf_solve(c_ld)
            _place(x, c, s.x)
            _place(ok, c, s.ok)
            _place(err, c, s.err)
        sol = XfSolution(x=x, ok=ok, err=err, settings=dict(fld.settings))
        ld = fld.loaded({"row_w": row_w})
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


def df_solve(ld, refant=0, minsnr=3.0, minblperant=4, gauge=None):
    """The Df solve on loaded arrays (`leakage.rs`), then CASA's
    subtractive reference and `minsnr` (SNR = 1/err). `gauge` (task W3b):
    `unpolarised_gauge`'s result over the whole field, when `ld` is a
    chunk of it."""
    refants = _refant_index(ld.names, refant)
    order = _flex_order(refants, ld.positions)
    if gauge is None:
        gauge = unpolarised_gauge(ld.model, ld.flag | ld.flag_row[:, None, None])
    degenerate, rho = gauge
    _check_gauge(degenerate, rho)
    raw = _df_kernel(ld, order, minblperant, degenerate)
    return _df_finish(raw, ld.settings, refants, order, degenerate, minsnr, minblperant)


def _check_gauge(degenerate, rho):
    if degenerate and abs(rho - 1) > 1e-6:
        raise ValueError(
            f"Df: the model's M_YY / M_XX is the constant {rho}, so the leakages "
            "are not determined; a polarised calibrator needs parallactic coverage"
        )


def _df_kernel(ld, order, minblperant, degenerate):
    """The Df kernel on loaded arrays: per (interval, channel) arrays."""
    ntime = len(ld.keys)
    nrow, nchan = ld.data.shape[:2]
    nant = ld.nant
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
    return {
        "d": d.view(np.complex128).reshape(ntime, nchan, nant, 2),
        "flags": fl.reshape(ntime, nchan, nant, 2).astype(bool),
        "vr": vr.reshape(ntime, nchan, nant, 2),
        "vi": vi.reshape(ntime, nchan, nant, 2),
        "chi2": chi2.reshape(ntime, nchan),
        "neq": neq.reshape(ntime, nchan),
        "npar": npar.reshape(ntime, nchan),
        "gauge": gauge.reshape(ntime, nchan),
    }


def _df_finish(raw, settings, refants, order, degenerate, minsnr, minblperant):
    """CASA's subtractive reference, errors, SNR and `minsnr` on the
    kernel's arrays over every interval and channel."""
    d, flags, vr, vi = raw["d"], raw["flags"], raw["vr"], raw["vi"]
    chi2, neq, npar, gauge = raw["chi2"], raw["neq"], raw["npar"], raw["gauge"]
    ntime, nchan = chi2.shape
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
            **settings,
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
    budget=None,
    average_time=False,
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
    iterative solver, research/c6w-polwire.md). `budget` (task W3b): chunks
    of whole intervals or of channels of one interval, the gauge test over
    the whole field first (`rang.cal_chunks.gauge`). `average_time` (task
    E2) as `kcross`; the gauge test and `min_data_fraction` then see the
    averaged cells."""
    ld, parts = _chunked(
        ms, budget, per_channel=True, what=f"Df field {field_id}",
        field_id=field_id, solved="Df", solint=solint, combine=combine,
        average_time=average_time, **load_options,
    )  # fmt: skip
    if parts is None:
        sol = df_solve(ld, refant=refant, minsnr=minsnr, minblperant=minblperant)
        frac = data_fraction(ld) if min_data_fraction is not None else None
    else:
        from . import cal_chunks

        fld, (chunks, get) = ld, parts
        refants = _refant_index(fld.names, refant)
        order = _flex_order(refants, fld.positions)

        def cells():
            for _, c_ld in _each_chunk(fld, chunks, get):
                yield c_ld.model, c_ld.flag | c_ld.flag_row[:, None, None]

        degenerate, rho = cal_chunks.gauge(cells)
        _check_gauge(degenerate, rho)
        ntime, nchan, nant = len(fld.keys), len(fld.freq), len(fld.names)
        raw = {
            "d": np.empty((ntime, nchan, nant, 2), np.complex128),
            "flags": np.empty((ntime, nchan, nant, 2), bool),
            "vr": np.empty((ntime, nchan, nant, 2)),
            "vi": np.empty((ntime, nchan, nant, 2)),
            "chi2": np.empty((ntime, nchan)),
            "neq": np.empty((ntime, nchan)),
            "npar": np.empty((ntime, nchan)),
            "gauge": np.empty((ntime, nchan), np.int64),
        }
        frac = np.empty((ntime, nchan)) if min_data_fraction is not None else None
        row_w = np.zeros(len(fld.rows))
        for c, c_ld in _each_chunk(fld, chunks, get, row_w):
            part = _df_kernel(c_ld, order, minblperant, degenerate)
            for key, value in part.items():
                _place(raw[key], c, value)
            if frac is not None:
                _place(frac, c, data_fraction(c_ld))
        sol = _df_finish(
            raw, fld.settings, refants, order, degenerate, minsnr, minblperant
        )
        ld = fld.loaded({"row_w": row_w})
    if min_data_fraction is not None:
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
    "LINEAR_FEEDS",
    "DfSolution",
    "KcrossSolution",
    "Loaded",
    "XfSolution",
    "apply",
    "clip_df",
    "data_fraction",
    "df",
    "df_solve",
    "feed_types",
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
