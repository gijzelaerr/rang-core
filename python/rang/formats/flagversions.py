"""CASA flag versions (`<ms>.flagversions/`; research/dfio-formats.md, F6).

CASA's `flagmanager(mode='save')` writes, next to the Measurement Set,
`<ms>.flagversions/FLAG_VERSION_LIST` (one `name : comment` line per
version) and a table `flags.<name>` with the MS's FLAG (Bool, a
TiledShapeStMan named `TiledFlag`, one hypercube) and FLAG_ROW (Bool,
StandardStMan), the table description named after the version with the
comment `!TablePlot Flag Table : <name>`. `save` writes one through the
core writer (E4); FLAG is written as a fixed-shape column (E4 creates
TiledShapeStMan columns with a fixed shape only), which casacore and CASA
read as they read CASA's own. `load` reads a version back. The core cannot
yet write the MS's own FLAG when the MS has an IncrementalStMan (E5), so
restoring into an MS is left to CASA.
"""

from pathlib import Path

import numpy as np

from .. import core, core_ms, core_ms_write


def versions(ms):
    """[(name, comment)] of `<ms>.flagversions/FLAG_VERSION_LIST`."""
    path = Path(str(ms) + ".flagversions") / "FLAG_VERSION_LIST"
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            name, _, comment = line.partition(" : ")
            out.append((name.strip(), comment))
    return out


def save(ms, name, comment="", flag=None, flag_row=None):
    """Save `flag` (row, chan, corr) and `flag_row` (row,) as flag version
    `name` of `ms` (by default the MS's own FLAG and FLAG_ROW)."""
    ms = Path(ms)
    if flag is None or flag_row is None:
        with core_ms.open_table(ms) as t:
            flag = t.getcol("FLAG") if flag is None else flag
            flag_row = t.getcol("FLAG_ROW") if flag_row is None else flag_row
    flag = np.ascontiguousarray(flag, bool)
    flag_row = np.ascontiguousarray(flag_row, bool)
    nrow, nchan, ncorr = flag.shape
    if any(n == name for n, _ in versions(ms)):
        raise ValueError(f"flag version {name!r} exists")
    root = Path(str(ms) + ".flagversions")
    root.mkdir(exist_ok=True)
    path = root / f"flags.{name}"
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
    t = core_ms_write.Table(path, _writer=writer)
    try:
        t.putcol("FLAG", flag)
        t.putcol("FLAG_ROW", flag_row)
    finally:
        t.close()
    with (root / "FLAG_VERSION_LIST").open("a") as f:
        f.write(f"{name} : {comment}\n")
    return path


def load(ms, name):
    """(FLAG, FLAG_ROW) of flag version `name` of `ms`."""
    path = Path(str(ms) + ".flagversions") / f"flags.{name}"
    with core_ms.open_table(path) as t:
        return t.getcol("FLAG"), t.getcol("FLAG_ROW")


__all__ = ["load", "save", "versions"]
