# SPDX-License-Identifier: GPL-3.0-or-later
"""CASA's tasks under CASA's keyword names (research/v8-open-casa.md, section 6).

Each function takes the keyword names and defaults of the CASA 6.7 task of the
same name, so a CASA script's call reads unchanged. A keyword rang does not
implement yet is refused with a `ValueError` naming it, never ignored.
`docs/casa-users.md` maps each task and keyword.

Tasks so far: `listobs` (research/v8a-listobs.md).
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["listobs", "Unsupported"]


class Unsupported(ValueError):
    """A CASA keyword value rang does not implement yet."""


def _refuse(task, given, defaults):
    bad = [k for k, v in defaults.items() if given[k] != v]
    if bad:
        names = ", ".join(f"{k}={given[k]!r}" for k in bad)
        raise Unsupported(
            f"{task}: {names} not supported yet (rang supports the defaults "
            f"for these keywords; docs/casa-users.md)"
        )


def listobs(
    vis,
    selectdata=True,
    spw="",
    field="",
    antenna="",
    uvrange="",
    timerange="",
    correlation="",
    scan="",
    intent="",
    feed="",
    array="",
    observation="",
    verbose=True,
    listfile="",
    listunfl=False,
    cachesize=50,
    overwrite=False,
):
    """Summarise the Measurement Set `vis` as CASA's `listobs` does.

    Returns CASA's record (`BeginTime`, `EndTime` in MJD days,
    `IntegrationTime` in s, `nfields`, `numrecords`, `field_N`, `scan_N`)
    plus rang's additions (`observation`, `spectral_windows`, `sources`,
    `antennas`, `fields_extra`, `states`). Prints the report, or writes it
    to `listfile` (refused if it exists, unless `overwrite`). Selections,
    `verbose=False` and `listunfl=True` are refused; `selectdata` and
    `cachesize` have no effect.
    """
    given = dict(
        spw=spw,
        field=field,
        antenna=antenna,
        uvrange=uvrange,
        timerange=timerange,
        correlation=correlation,
        scan=scan,
        intent=intent,
        feed=feed,
        array=array,
        observation=observation,
        verbose=verbose,
        listunfl=listunfl,
    )
    defaults = {k: "" for k in given} | {"verbose": True, "listunfl": False}
    _refuse("listobs", given, defaults)
    from .. import listobs as _listobs

    record = _listobs.summary(vis)
    report = _listobs.text(record, str(vis))
    if listfile:
        out = Path(listfile)
        if out.exists() and not overwrite:
            raise FileExistsError(f"listobs: {out} exists (overwrite=True replaces it)")
        out.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return record
