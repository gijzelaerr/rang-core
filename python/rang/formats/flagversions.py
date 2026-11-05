"""CASA flag versions (`<ms>.flagversions/`; research/dfio-formats.md, F6,
and research/w1-writeback.md, W1).

CASA's `flagmanager(mode='save')` writes, next to the Measurement Set,
`<ms>.flagversions/FLAG_VERSION_LIST` (one `name : comment` line per
version) and a table `flags.<name>` with the MS's FLAG (Bool, a
TiledShapeStMan named `TiledFlag`, one hypercube) and FLAG_ROW (Bool,
StandardStMan), the table description named after the version with the
comment `!TablePlot Flag Table : <name>`. `save` writes one through the
core writer; FLAG is written as a fixed-shape column (the writer creates
TiledShapeStMan columns with a fixed shape only), which casacore and CASA
read as they read CASA's own.

A version is written in row chunks (the MS's FLAG is never read whole when
`flag` is not given), under a temporary name; it is read back and compared
with the MS, renamed to `flags.<name>` and only then listed (with fsync), so
a process killed while saving leaves no listed, partial version. `restore`
writes a version back into the MS's FLAG and FLAG_ROW, in row chunks.
`load` reads a version back.
"""

import os
import shutil
from pathlib import Path

import numpy as np

from .. import core, core_ms, core_ms_write

LIST = "FLAG_VERSION_LIST"
PARTIAL = ".rang-partial"


def root(ms):
    """The flag-version directory of `ms` (`<ms>.flagversions`)."""
    return Path(str(ms) + ".flagversions")


def versions(ms):
    """[(name, comment)] of `<ms>.flagversions/FLAG_VERSION_LIST`."""
    path = root(ms) / LIST
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            name, _, comment = line.partition(" : ")
            out.append((name.strip(), comment))
    return out


def exists(ms, name):
    """True when flag version `name` of `ms` is listed."""
    return any(n == name for n, _ in versions(ms))


def _fsync_dir(path):
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _create(path, name, nrow, nchan, ncorr):
    columns = [
        core_ms_write.makearrcoldesc(
            "FLAG",
            False,
            shape=[nchan, ncorr],
            valuetype="boolean",
            datamanagertype="TiledShapeStMan",
            datamanagergroup="TiledFlag",
        ),
        core_ms_write.makescacoldesc("FLAG_ROW", False, valuetype="boolean"),
    ]
    dminfo = {
        "*1": {
            "TYPE": "TiledShapeStMan",
            "NAME": "TiledFlag",
            "SPEC": {"DEFAULTTILESHAPE": [ncorr, nchan, max(1, min(nrow, 1024))]},
            "COLUMNS": ["FLAG"],
        },
        "*2": {
            "TYPE": "StandardStMan",
            "NAME": "StandardStMan",
            "SPEC": {"BUCKETSIZE": 128},
            "COLUMNS": ["FLAG_ROW"],
        },
    }
    descs = [core_ms_write._column_args(c) for c in core_ms_write.maketabdesc(columns)]
    writer = core.extension().ms_create_table(
        str(path),
        (name, "", f"!TablePlot Flag Table : {name}"),
        descs,
        core_ms_write._manager_args(dminfo),
        ("", "", ""),
        int(nrow),
        False,
        False,
    )
    return core_ms_write.Table(path, _writer=writer)


def spans(nrow, chunk_rows):
    """[(start, n)] covering `nrow` rows in chunks of `chunk_rows`."""
    chunk_rows = max(1, int(chunk_rows))
    return [(s, min(chunk_rows, nrow - s)) for s in range(0, nrow, chunk_rows)]


def save(
    ms,
    name,
    comment="",
    flag=None,
    flag_row=None,
    chunk_rows=1024,
    on_chunk=None,
):
    """Save `flag` (row, chan, corr) and `flag_row` (row,) as flag version
    `name` of `ms`; by default the MS's own FLAG and FLAG_ROW, read and
    written `chunk_rows` rows at a time (the MS must not be open for
    writing in this process). `on_chunk(start, n)` is called after each
    chunk is flushed (tests use it to interrupt a save). Returns the
    version's path."""
    ms = Path(ms)
    if exists(ms, name):
        raise ValueError(f"flag version {name!r} exists")
    if "/" in name or " : " in name or name.endswith(PARTIAL) or not name.strip():
        raise ValueError(f"flag version name {name!r} is not allowed")
    if (flag is None) != (flag_row is None):
        raise ValueError("give both flag and flag_row, or neither")
    given = flag is not None
    if given:
        flag = np.ascontiguousarray(flag, bool)
        flag_row = np.ascontiguousarray(flag_row, bool)
        nrow, nchan, ncorr = flag.shape
        if flag_row.shape != (nrow,):
            raise ValueError("flag_row must have one value per row")
    else:
        with core_ms.open_table(ms) as t:
            nrow = t.nrows
            if nrow == 0:
                raise ValueError(f"{ms} has no rows")
            _, nchan, ncorr = t.getcol("FLAG", 0, 1).shape
    top = root(ms)
    top.mkdir(exist_ok=True)
    final = top / f"flags.{name}"
    partial = top / f"flags.{name}{PARTIAL}"
    if final.exists():
        raise ValueError(f"{final} exists but is not listed; remove it first")
    shutil.rmtree(partial, ignore_errors=True)

    def source(start, n):
        if given:
            return flag[start : start + n], flag_row[start : start + n]
        with core_ms.open_table(ms) as t:
            return t.getcol("FLAG", start, n), t.getcol("FLAG_ROW", start, n)

    t = _create(partial, name, nrow, nchan, ncorr)
    try:
        for start, n in spans(nrow, chunk_rows):
            f, r = source(start, n)
            if f.shape[1:] != (nchan, ncorr):
                raise ValueError(
                    f"rows {start}-{start + n - 1}: FLAG cells {f.shape[1:]} differ "
                    f"from row 0's {(nchan, ncorr)}; a flag version needs one shape"
                )
            t.putcol("FLAG", f, start)
            t.putcol("FLAG_ROW", r, start)
            t.flush()
            if on_chunk is not None:
                on_chunk(start, n)
    finally:
        t.close()
    # Read back and compare before the version counts as saved.
    with core_ms.open_table(partial) as v:
        if v.nrows != nrow:
            raise RuntimeError(f"flag version {name}: {v.nrows} rows, expected {nrow}")
        for start, n in spans(nrow, chunk_rows):
            f, r = source(start, n)
            if not (
                np.array_equal(v.getcol("FLAG", start, n), f)
                and np.array_equal(v.getcol("FLAG_ROW", start, n), r)
            ):
                raise RuntimeError(
                    f"flag version {name}: rows {start}-{start + n - 1} read back "
                    "differently from what was written"
                )
    os.replace(partial, final)
    _fsync_dir(top)
    with (top / LIST).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{name} : {comment}\n")
        fh.flush()
        os.fsync(fh.fileno())
    _fsync_dir(top)
    return final


def load(ms, name, startrow=0, nrow=None):
    """(FLAG, FLAG_ROW) of flag version `name` of `ms`: rows `startrow`
    onwards (all, or `nrow` of them)."""
    path = root(ms) / f"flags.{name}"
    with core_ms.open_table(path) as t:
        return t.getcol("FLAG", startrow, nrow), t.getcol("FLAG_ROW", startrow, nrow)


def restore(ms, name, chunk_rows=1024, table=None, on_chunk=None):
    """Write flag version `name` back into the FLAG and FLAG_ROW of `ms`
    (`flagmanager(mode='restore')`), `chunk_rows` rows at a time, each chunk
    flushed and read back. `table` is an open `core_ms_write.Table` of the
    MS to write through (its lock is kept); without one the MS is opened
    for writing and closed. `on_chunk(start, n)` is called after each
    chunk. Returns the number of rows restored."""
    if not exists(ms, name):
        raise ValueError(f"flag version {name!r} of {ms} does not exist")
    with core_ms.open_table(root(ms) / f"flags.{name}") as v:
        nrow = v.nrows
    own = table is None
    t = core_ms_write.open_table(ms, readonly=False) if own else table
    try:
        if t.nrows() != nrow:
            raise ValueError(
                f"flag version {name!r} has {nrow} rows, the MS {t.nrows()}"
            )
        for start, n in spans(nrow, chunk_rows):
            f, r = load(ms, name, start, n)
            t.putcol("FLAG", f, start)
            t.putcol("FLAG_ROW", r, start)
            t.flush()
            if not (
                np.array_equal(t.getcol("FLAG", start, n), f)
                and np.array_equal(t.getcol("FLAG_ROW", start, n), r)
            ):
                raise RuntimeError(
                    f"rows {start}-{start + n - 1} of {ms} read back differently "
                    f"from flag version {name!r}"
                )
            if on_chunk is not None:
                on_chunk(start, n)
    finally:
        if own:
            t.close()
    return nrow


__all__ = ["exists", "load", "restore", "root", "save", "spans", "versions"]
