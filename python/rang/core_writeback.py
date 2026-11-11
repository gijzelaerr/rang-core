"""Write-back to an existing Measurement Set (research/w1-writeback.md, W1).

The interface C4b (CORRECTED_DATA, FLAG, WEIGHT), G6 (MODEL_DATA) and W2
(the general commands) write through::

    from rang import core_writeback as wb

    with wb.WriteBack(ms, stage="applycal") as w:   # backs up FLAG first
        w.ensure_column("CORRECTED_DATA")            # added as CASA adds it
        for start, n in w.chunks():
            data = w.read("DATA", start, n)
            w.write("CORRECTED_DATA", start, data / 2)
            flag = w.read("FLAG", start, n) | new_flags(start, n)
            w.write_flags(start, flag)

`WriteBack` holds the core writer's lock on the MS for the whole session
on Linux only; on Windows and macOS nothing stops a second writer (E5),
and `rang-core` refuses only a second command on the same run directory.
Before its first write it saves the MS's FLAG and FLAG_ROW as a CASA flag
version (`<ms>.flagversions/flags.<flag_backup>`, default `rang_original`)
unless that version already exists, and it keeps a journal
(`<ms>.flagversions/rang-writeback.json`) that says a session is open. A
session that ends by an exception is marked failed; one that is killed stays
open. Either way the next `WriteBack` on the MS refuses to start (so a
half-written FLAG is never saved as a new original) until the caller
chooses `on_interrupted="restore"` (write the backup back first),
`"continue"` (keep the flags as they are), or calls `restore_flags`.

Every write is flushed before the call returns, so memory follows the chunk
(the tiled writer keeps the tiles it touched until a flush) and a killed
process loses at most the chunk being written. Columns are added as CASA
6.7.6 `clearcal(addmodel=True)` adds them (TiledShapeStMan `TiledModel` and
`TiledCorrected`, about 1 MiB tiles, DATA's comment, DATA's column keywords
on CORRECTED_DATA) and every row is initialised as clearcal leaves it
(CORRECTED_DATA = DATA; MODEL_DATA 1 on the parallel hands, 0 on the cross
hands), but with a fixed cell shape, so an MS whose DATA cells differ in
shape is refused.
"""

import datetime as _dt
import json
import os
import socket
from pathlib import Path

import numpy as np

from . import core_ms, core_ms_write
from .formats import _aipsio, flagversions

JOURNAL = "rang-writeback.json"
DEFAULT_BACKUP = "rang_original"
# CORR_TYPE codes of the parallel hands (Stokes I, RR, LL, XX, YY).
PARALLEL = frozenset({1, 5, 8, 9, 12})
MANAGER_NAMES = {
    "MODEL_DATA": "TiledModel",
    "CORRECTED_DATA": "TiledCorrected",
    "WEIGHT_SPECTRUM": "TiledWgtSpectrum",
    "SIGMA_SPECTRUM": "TiledSigmaSpectrum",
}
SPECTRUM_COMMENTS = {
    "WEIGHT_SPECTRUM": "Weight for each data point",
    "SIGMA_SPECTRUM": "Estimated rms noise for each data point",
}
DEFAULT_INIT = {
    "MODEL_DATA": "unity",
    "CORRECTED_DATA": "data",
    "CORRECTED_1GC": "data",
    "WEIGHT_SPECTRUM": "weight",
    "SIGMA_SPECTRUM": "sigma",
}
FLAG_COLUMNS = ("FLAG", "FLAG_ROW")
# Chunks of FLAG written by any WriteBack in this process (E5): the pipeline
# compares it before and after a stage to learn whether the stage changed
# the flags that later stages start from.
_flag_puts = 0
TILE_BYTES = 1 << 20
CHUNK_BYTES = 64 << 20


class InterruptedWriteBack(RuntimeError):
    """An earlier write-back session on this MS did not finish."""


class UnsupportedLayout(ValueError):
    """The MS has a layout write-back does not handle (task W4 owns these)."""


# -- journal ---------------------------------------------------------------------


def journal_path(ms):
    return flagversions.root(ms) / JOURNAL


def read_journal(ms):
    """The journal of the last write-back session on `ms`, or None."""
    path = journal_path(ms)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _write_journal(ms, record):
    path = journal_path(ms)
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    flagversions._fsync_dir(path.parent)


def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# -- layout ----------------------------------------------------------------------


def layout(ms):
    """What write-back needs to know of `ms`: rows, the one DATA cell shape
    (nchan, ncorr), CORR_TYPE, the columns and their descriptions. Raises
    `UnsupportedLayout` when DATA cells differ in shape or correlation
    types between rows."""
    ms = Path(ms)
    with core_ms.open_table(ms) as t:
        nrows = t.nrows
        columns = dict(t.columns)
        if nrows == 0:
            raise UnsupportedLayout(f"{ms} has no rows")
        if "DATA" not in columns:
            raise UnsupportedLayout(f"{ms} has no DATA column")
        ddids = set()
        for start, n in flagversions.spans(nrows, 1 << 20):
            ddids.update(np.unique(t.getcol("DATA_DESC_ID", start, n)).tolist())
        cell = tuple(t.getcol("DATA", 0, 1).shape[1:])
    with core_ms.open_table(ms / "DATA_DESCRIPTION") as dd:
        spw_of = dd.getcol("SPECTRAL_WINDOW_ID")
        pol_of = dd.getcol("POLARIZATION_ID")
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as sw:
        nchan_of = sw.getcol("NUM_CHAN")
    with core_ms.open_table(ms / "POLARIZATION") as po:
        corr_of = [po.getcol("CORR_TYPE", i, 1)[0] for i in range(po.nrows)]
    shapes, corrs = set(), set()
    for d in sorted(ddids):
        if not 0 <= d < len(spw_of):
            raise UnsupportedLayout(
                f"{ms}: DATA_DESC_ID {d} has no DATA_DESCRIPTION row"
            )
        corr = tuple(int(c) for c in corr_of[int(pol_of[d])])
        shapes.add((int(nchan_of[int(spw_of[d])]), len(corr)))
        corrs.add(corr)
    if len(shapes) != 1 or len(corrs) != 1:
        raise UnsupportedLayout(
            f"{ms}: DATA cells differ in shape or correlations between data "
            f"descriptions ({sorted(shapes)}, {sorted(corrs)}); write-back needs "
            "one cell shape. Split one spectral window out first, for example with "
            "CASA split or mstransform (spw=...)"
        )
    if shapes != {cell}:
        raise UnsupportedLayout(
            f"{ms}: DATA row 0 has cells {cell}, the subtables say {shapes.pop()}"
        )
    return {
        "nrows": nrows,
        "cell": cell,
        "corr_type": corrs.pop(),
        "columns": columns,
        "descriptions": _aipsio.column_descriptions(ms),
    }


def tile_rows(cell, itemsize):
    """Rows per tile of a tiled column of `cell` (all channels and
    correlations in a tile, about 1 MiB, as CASA's TiledModel)."""
    return max(1, TILE_BYTES // (int(np.prod(cell)) * itemsize))


def chunk_rows_for(cell, chunk_bytes=CHUNK_BYTES, multiple=64):
    """Rows per chunk: about `chunk_bytes` of complex64 cells, a multiple of
    `multiple` rows (tile boundaries of the usual layouts)."""
    rows = chunk_bytes // (int(np.prod(cell)) * 8)
    return max(multiple, rows // multiple * multiple)


def flag_row_all(flag):
    """FLAG_ROW as 'every cell of the row flagged' (helper; C4 decides)."""
    flag = np.asarray(flag, bool)
    return flag.reshape(flag.shape[0], -1).all(axis=1)


# -- the session -----------------------------------------------------------------


class WriteBack:
    """A write-back session on an existing MS; use as a context manager.

    `flag_backup` names the flag version saved before the first write (kept
    if it exists); `stage` and `comment` are recorded in the journal and the
    version list. `on_interrupted` is "refuse", "restore" or "continue" (see
    the module docstring). `chunk_rows` is the default of `chunks()`.
    `on_chunk(event, column, start, n)` is called with event "backup" after
    each saved chunk of the backup, "written" after each put and before its
    flush, and "flushed" after the flush (tests use it to interrupt)."""

    def __init__(
        self,
        ms,
        flag_backup=DEFAULT_BACKUP,
        stage="",
        comment=None,
        on_interrupted="refuse",
        chunk_rows=None,
        lock_attempts=10,
        lock_wait=1.0,
        on_chunk=None,
    ):
        if on_interrupted not in ("refuse", "restore", "continue"):
            raise ValueError("on_interrupted is 'refuse', 'restore' or 'continue'")
        self.ms = Path(ms)
        self.flag_backup = flag_backup
        self.stage = stage
        self.comment = comment
        self.on_interrupted = on_interrupted
        self._chunk_rows = chunk_rows
        self._lock = (lock_attempts, lock_wait)
        self._on_chunk = on_chunk
        self.table = None
        self.layout = None
        self._journal = None

    # -- lifetime --------------------------------------------------------------
    def begin(self):
        if self.table is not None:
            return self
        if not (self.ms / "table.dat").is_file():
            raise FileNotFoundError(f"{self.ms} is not a casacore table")
        prior = read_journal(self.ms)
        dirty = []
        if prior and prior.get("state") in ("open", "failed"):
            dirty = list(prior.get("initialising", []))
            what = (
                f"an earlier write-back on {self.ms} (stage {prior.get('stage')!r}, "
                f"pid {prior.get('pid')}, started {prior.get('started')}) is "
                f"{prior['state']}"
            )
            if self.on_interrupted == "refuse":
                raise InterruptedWriteBack(
                    f"{what}; FLAG may be partly written. Call "
                    f"rang.core_writeback.restore_flags({str(self.ms)!r}, "
                    f"{prior.get('flag_backup')!r}) to go back to the flags saved "
                    "before it, or pass on_interrupted='restore' or 'continue'."
                )
            if self.on_interrupted == "restore":
                restore_flags(self.ms, prior["flag_backup"])
            if prior.get("flag_backup") and prior["flag_backup"] != self.flag_backup:
                # The earlier session's backup is the last clean state.
                self.flag_backup = prior["flag_backup"]
        self.layout = layout(self.ms)
        if not flagversions.exists(self.ms, self.flag_backup):
            hook = None
            if self._on_chunk is not None:

                def hook(s, n):
                    self._on_chunk("backup", "FLAG", s, n)

            comment = self.comment or (
                f"rang write-back: flags before {self.stage or 'the first write'}"
            )
            flagversions.save(
                self.ms,
                self.flag_backup,
                comment,
                chunk_rows=self.chunk_rows(),
                on_chunk=hook,
            )
        else:
            with core_ms.open_table(
                flagversions.root(self.ms) / f"flags.{self.flag_backup}"
            ) as v:
                if v.nrows != self.layout["nrows"]:
                    raise ValueError(
                        f"flag version {self.flag_backup!r} has {v.nrows} rows, "
                        f"{self.ms} has {self.layout['nrows']}"
                    )
        self._journal = {
            "state": "open",
            "ms": str(self.ms.resolve()),
            "flag_backup": self.flag_backup,
            "stage": self.stage,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started": _now(),
            "initialising": dirty,
            "written": [],
        }
        _write_journal(self.ms, self._journal)
        self.table = core_ms_write.open_table(
            self.ms,
            readonly=False,
            lock_attempts=self._lock[0],
            lock_wait=self._lock[1],
        )
        return self

    def close(self, error=None):
        if self.table is None:
            return
        try:
            self.table.close()
        finally:
            self.table = None
            self._journal["state"] = "failed" if error is not None else "closed"
            self._journal["finished"] = _now()
            if error is not None:
                self._journal["error"] = f"{type(error).__name__}: {error}"
            _write_journal(self.ms, self._journal)

    def __enter__(self):
        return self.begin()

    def __exit__(self, kind, value, tb):
        self.close(error=value)

    def _require(self):
        if self.table is None:
            raise ValueError("the write-back session is not open")

    def _mark(self, key, name, add=True):
        items = self._journal[key]
        if add and name not in items:
            items.append(name)
        elif not add and name in items:
            items.remove(name)
        else:
            return
        _write_journal(self.ms, self._journal)

    # -- rows ------------------------------------------------------------------
    @property
    def nrows(self):
        return (
            self.layout["nrows"] if self.layout else core_ms.open_table(self.ms).nrows
        )

    @property
    def cell(self):
        """(nchan, ncorr) of every DATA cell."""
        return self.layout["cell"]

    def chunk_rows(self):
        if self._chunk_rows:
            return int(self._chunk_rows)
        if self.layout is None:
            self.layout = layout(self.ms)
        return chunk_rows_for(self.layout["cell"])

    def chunks(self, chunk_rows=None):
        """[(start, n)] over all rows."""
        if self.layout is None:
            self.layout = layout(self.ms)
        return flagversions.spans(self.layout["nrows"], chunk_rows or self.chunk_rows())

    def colnames(self):
        self._require()
        return self.table.colnames()

    def read(self, name, start, n, chans=None):
        """Rows `start` to `start + n - 1` of a column, read through the
        session's writer (opening the MS with another reader in this
        process would drop the lock); `chans` reads only those channels
        (`core_ms.Table.getcol`)."""
        self._require()
        return self.table.getcol(name, int(start), int(n), chans=chans)

    def read_rows(self, name, rows, chans=None):
        """The rows `rows` (any order) of a column in one read through the
        session's writer; `chans` as `read`."""
        self._require()
        return self.table.getcol_rows(name, rows, chans=chans)

    # -- writes ----------------------------------------------------------------
    def _put(self, name, start, values):
        global _flag_puts
        if name == "DATA":
            # Only FLAG is backed up, so the observed visibilities are never
            # written (E5, research/e5-prereview.md).
            raise ValueError("DATA is never written")
        n = values.shape[0]
        self.table.putcol(name, values, int(start))
        if name == "FLAG":
            _flag_puts += 1
        if self._on_chunk is not None:
            self._on_chunk("written", name, int(start), n)
        self.table.flush()
        if self._on_chunk is not None:
            self._on_chunk("flushed", name, int(start), n)
        if name not in self._journal["written"]:
            self._mark("written", name)

    def write(self, name, start, values):
        """Write rows `start` onwards of column `name` (any existing column;
        FLAG and FLAG_ROW go through `write_flags`), then flush."""
        self._require()
        if name in FLAG_COLUMNS:
            if name == "FLAG":
                return self.write_flags(start, values)
            return self.write_flags(start, None, values)
        if name not in self.table.colnames():
            raise ValueError(f"{self.ms} has no column {name}; call ensure_column")
        values = np.asarray(values)
        info = self.layout["columns"].get(name)
        if info is not None and info["is_array"] and values.ndim > 1:
            want = self._cell_of(name)
            if want is not None and values.shape[1:] != want:
                raise ValueError(
                    f"{name}: cells {values.shape[1:]}, the column has {want}"
                )
        if int(start) < 0 or int(start) + values.shape[0] > self.layout["nrows"]:
            raise ValueError(f"{name}: rows {start}+{values.shape[0]} outside the MS")
        self._put(name, start, values)

    def write_flags(self, start, flag, flag_row=None):
        """Write FLAG (rows, nchan, ncorr) and/or FLAG_ROW (rows,) from row
        `start`, exactly as given (merging with the old flags and the
        FLAG_ROW policy are the caller's; see `flag_row_all`)."""
        self._require()
        nrows = self.layout["nrows"]
        if flag is not None:
            flag = np.asarray(flag, bool)
            if flag.shape[1:] != self.layout["cell"]:
                raise ValueError(
                    f"FLAG: cells {flag.shape[1:]}, DATA has {self.layout['cell']}"
                )
            if int(start) < 0 or int(start) + flag.shape[0] > nrows:
                raise ValueError(f"FLAG: rows {start}+{flag.shape[0]} outside the MS")
            self._put("FLAG", start, flag)
        if flag_row is not None:
            flag_row = np.asarray(flag_row, bool).reshape(-1)
            if flag is not None and flag_row.shape[0] != flag.shape[0]:
                raise ValueError("FLAG and FLAG_ROW cover different rows")
            if int(start) < 0 or int(start) + flag_row.shape[0] > nrows:
                raise ValueError(
                    f"FLAG_ROW: rows {start}+{flag_row.shape[0]} outside the MS"
                )
            self._put("FLAG_ROW", start, flag_row)

    # -- columns ---------------------------------------------------------------
    def _cell_of(self, name):
        info = self.layout["columns"].get(name)
        if info is None or not info["is_array"]:
            return None
        if info.get("shape"):
            return tuple(info["shape"])[::-1]
        return tuple(self.table.getcol(name, 0, 1).shape[1:])

    def ensure_column(self, name, init="default", tile=None):
        """Make sure column `name` exists with one cell per row of DATA's
        shape and initialise it when it is added (or was being initialised
        by an interrupted session). Data columns are complex64,
        WEIGHT_SPECTRUM and SIGMA_SPECTRUM float32. `init`: "default" (by
        name: MODEL_DATA "unity", CORRECTED_DATA and CORRECTED_1GC "data",
        WEIGHT_SPECTRUM "weight", SIGMA_SPECTRUM "sigma"), "data" (a copy of
        DATA), "unity" (1 on the parallel hands, 0 on the cross hands),
        "zero", "weight"/"sigma" (WEIGHT/SIGMA repeated over channels), a
        callable `(start, n) -> values`, or None (no initial write: the
        caller must write every row). Returns True when the column was
        added."""
        self._require()
        spectrum = name in SPECTRUM_COMMENTS
        dtype = np.dtype("float32") if spectrum else np.dtype("complex64")
        cell = self.layout["cell"]
        if init == "default":
            init = DEFAULT_INIT.get(name)
            if init is None:
                raise ValueError(f"{name}: give init (no default for this column)")
        added = name not in self.table.colnames()
        if added:
            if name in ("DATA", *FLAG_COLUMNS):
                raise ValueError(f"{name} is not added by write-back")
            data_desc = self.layout["descriptions"].get("DATA", {})
            manager = MANAGER_NAMES.get(name) or "Tiled" + "".join(
                p.capitalize() for p in name.lower().split("_")
            )
            if spectrum:
                comment, keywords = SPECTRUM_COMMENTS[name], {}
            else:
                comment = data_desc.get("comment", "")
                keywords = {} if name == "MODEL_DATA" else data_desc.get("keywords", {})
            rows = tile_rows(cell, dtype.itemsize)
            tile = list(tile) if tile is not None else [cell[1], cell[0], rows]
            desc = core_ms_write.makearrcoldesc(
                name,
                0.0 if spectrum else 0j,
                shape=list(cell),
                valuetype="float" if spectrum else "complex",
                comment=comment,
                datamanagertype="TiledShapeStMan",
                datamanagergroup=manager,
            )
            self._mark("initialising", name)
            self.table.addcols(
                desc,
                {
                    "TYPE": "TiledShapeStMan",
                    "NAME": manager,
                    "SPEC": {"DEFAULTTILESHAPE": tile},
                },
            )
            for key, value in keywords.items():
                self.table.putcolkeyword(name, key, value)
            self.table.flush()
            self.layout["columns"][name] = {
                "name": name,
                "dtype": dtype.name,
                "is_array": True,
                "shape": [cell[1], cell[0]],
            }
        else:
            have = self.table.getcol(name, 0, 1)
            if have.dtype != dtype or have.shape[1:] != cell:
                raise UnsupportedLayout(
                    f"{self.ms}: {name} has {have.dtype} cells {have.shape[1:]}; "
                    f"write-back needs {dtype} cells {cell}"
                )
            if name not in self._journal["initialising"]:
                return False
        if init is not None:
            self._initialise(name, init, dtype)
        self._mark("initialising", name, add=False)
        return added

    def _initialise(self, name, init, dtype):
        nchan, ncorr = self.layout["cell"]
        parallel = np.array([c in PARALLEL for c in self.layout["corr_type"]])
        for start, n in self.chunks():
            if callable(init):
                values = np.asarray(init(start, n), dtype)
            elif init == "data":
                values = self.read("DATA", start, n).astype(dtype, copy=False)
            elif init == "unity":
                values = np.zeros((n, nchan, ncorr), dtype)
                values[:, :, parallel] = 1
            elif init == "zero":
                values = np.zeros((n, nchan, ncorr), dtype)
            elif init in ("weight", "sigma"):
                per_row = self.read(init.upper(), start, n).astype(dtype, copy=False)
                values = np.repeat(per_row[:, None, :], nchan, axis=1)
            else:
                raise ValueError(f"unknown init {init!r}")
            self._put(name, start, values)


# -- helpers ---------------------------------------------------------------------


def add_imaging_columns(ms, columns=("MODEL_DATA", "CORRECTED_DATA"), **kwargs):
    """Add (and initialise, as clearcal does) MODEL_DATA and CORRECTED_DATA
    where they are missing, in one session. Returns {column: added}."""
    with WriteBack(ms, **kwargs) as w:
        return {c: w.ensure_column(c) for c in columns}


def backup_flags(ms, name=DEFAULT_BACKUP, comment="", chunk_rows=None):
    """Save the MS's FLAG and FLAG_ROW as flag version `name` unless it
    exists. Returns True when it was saved now."""
    if flagversions.exists(ms, name):
        return False
    rows = chunk_rows or chunk_rows_for(layout(ms)["cell"])
    flagversions.save(ms, name, comment, chunk_rows=rows)
    return True


def flag_writes():
    """How many chunks of FLAG this process has written through WriteBack."""
    return _flag_puts


def restore_flags(ms, name=DEFAULT_BACKUP, chunk_rows=None):
    """Write flag version `name` back into FLAG and FLAG_ROW, in chunks,
    and mark an interrupted session's journal as restored. Returns the
    number of rows."""
    rows = chunk_rows or chunk_rows_for(layout(ms)["cell"])
    n = flagversions.restore(ms, name, chunk_rows=rows)
    journal = read_journal(ms)
    if journal and journal.get("state") in ("open", "failed"):
        journal["state"] = "restored"
        journal["restored"] = _now()
        journal["restored_from"] = name
        _write_journal(ms, journal)
    return n


__all__ = [
    "DEFAULT_BACKUP",
    "InterruptedWriteBack",
    "UnsupportedLayout",
    "WriteBack",
    "add_imaging_columns",
    "backup_flags",
    "chunk_rows_for",
    "flag_row_all",
    "layout",
    "read_journal",
    "restore_flags",
    "tile_rows",
]
