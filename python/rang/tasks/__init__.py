# SPDX-License-Identifier: GPL-3.0-or-later
"""CASA's tasks under CASA's keyword names (research/v8-open-casa.md, section 6).

Each function takes the keyword names and defaults of the CASA 6.7 task of the
same name, so a CASA script's call reads unchanged. A keyword rang does not
implement yet is refused with a `ValueError` naming it, never ignored.
`docs/casa-users.md` maps each task and keyword.

Tasks so far: `listobs` (research/v8a-listobs.md), `flagdata`
(research/v8b-flagdata.md).
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["Unsupported", "flagdata", "listobs"]


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
    given = {
        "spw": spw,
        "field": field,
        "antenna": antenna,
        "uvrange": uvrange,
        "timerange": timerange,
        "correlation": correlation,
        "scan": scan,
        "intent": intent,
        "feed": feed,
        "array": array,
        "observation": observation,
        "verbose": verbose,
        "listunfl": listunfl,
    }
    defaults = {k: "" for k in given} | {"verbose": True, "listunfl": False}
    _refuse("listobs", given, defaults)
    from .. import listobs as _listobs

    record = _listobs.summary(vis)
    report = _listobs.text(record, str(vis))
    if listfile:
        out = Path(listfile)
        if out.exists() and not overwrite:
            raise FileExistsError(f"listobs: {out} exists (overwrite=True replaces it)")
        out.write_text(report, encoding="utf-8", newline="\n")
    else:
        print(report, end="")
    return record


# -- flagdata (research/v8b-flagdata.md) -----------------------------------------

_FLAGDATA_REFUSED = {
    # keyword: the only value rang accepts
    "inpfile": "", "reason": "any", "tbuff": 0.0, "intent": "", "feed": "",
    "channelavg": False, "chanbin": 1, "timeavg": False, "timebin": "0s",
    "addantenna": "", "winsize": 3, "timedev": "", "freqdev": "",
    "timedevscale": 5.0, "freqdevscale": 5.0, "spectralmax": 1000000.0,
    "spectralmin": 0.0, "antint_ref_antenna": "", "minchanfrac": 0.6,
    "action": "apply", "display": "", "savepars": False, "cmdreason": "",
    "outfile": "", "writeflags": True, "fieldcnt": False,
    "minrel": 0.0, "maxrel": 1.0, "minabs": 0, "maxabs": -1,
}  # fmt: skip
_FLAGDATA_MODES = ("manual", "clip", "quack", "shadow", "elevation", "tfcrop", "extend",
                   "unflag", "summary")  # fmt: skip


def flagdata(
    vis,
    mode="manual",
    autocorr=False,
    inpfile="",
    reason="any",
    tbuff=0.0,
    spw="",
    field="",
    antenna="",
    uvrange="",
    timerange="",
    correlation="",
    scan="",
    intent="",
    array="",
    observation="",
    feed="",
    clipminmax=(),
    datacolumn="DATA",
    clipoutside=True,
    channelavg=False,
    chanbin=1,
    timeavg=False,
    timebin="0s",
    clipzeros=False,
    quackinterval=1.0,
    quackmode="beg",
    quackincrement=False,
    tolerance=0.0,
    addantenna="",
    lowerlimit=0.0,
    upperlimit=90.0,
    ntime="scan",
    combinescans=False,
    timecutoff=4.0,
    freqcutoff=3.0,
    timefit="line",
    freqfit="poly",
    maxnpieces=7,
    flagdimension="freqtime",
    usewindowstats="none",
    halfwin=1,
    extendflags=True,
    winsize=3,
    timedev="",
    freqdev="",
    timedevscale=5.0,
    freqdevscale=5.0,
    spectralmax=1000000.0,
    spectralmin=0.0,
    antint_ref_antenna="",
    minchanfrac=0.6,
    verbose=False,
    extendpols=True,
    growtime=50.0,
    growfreq=50.0,
    growaround=False,
    flagneartime=False,
    flagnearfreq=False,
    minrel=0.0,
    maxrel=1.0,
    minabs=0,
    maxabs=-1,
    spwchan=False,
    spwcorr=False,
    basecnt=False,
    fieldcnt=False,
    name="Summary",
    action="apply",
    display="",
    formats="png",
    savepars=False,
    cmdreason="",
    outfile="",
    overwrite=True,
    writeflags=True,
    flagbackup=True,
):
    """CASA's `flagdata` on the Measurement Set (or, for `clip` on `CPARAM`,
    the calibration table) `vis`, under CASA's keyword names and defaults.

    Modes: `manual`, `clip`, `quack`, `shadow`, `elevation`, `tfcrop`,
    `extend`, `unflag`, `summary` (research/v8b-flagdata.md). Returns CASA's
    summary dictionary for `summary`, else rang's write record (rows and
    cells selected, flags before and after, FLAG's SHA-256). Every keyword
    value rang does not implement is refused before anything is written.
    `flagbackup=True` saves CASA's flag version `flagdata_<n>` before
    writing; with `False` rang still saves the flags it first found, once,
    as `rang_original` (rang never writes FLAG without a backup);
    `verbose`, `formats` and `overwrite` have no effect.
    """
    from .. import flagdata as _fd

    given = {k: v for k, v in locals().items() if k in _FLAGDATA_REFUSED}
    _refuse("flagdata", given, _FLAGDATA_REFUSED)
    if mode not in _FLAGDATA_MODES:
        raise Unsupported(f"flagdata: mode={mode!r} not supported yet "
                          f"(rang supports {', '.join(_FLAGDATA_MODES)})")  # fmt: skip
    if mode == "manual" and autocorr not in (True, False):
        raise Unsupported(f"flagdata: autocorr={autocorr!r}")
    dc = str(datacolumn).upper()
    if mode in ("clip", "tfcrop") and dc not in _fd.DATACOLUMNS and dc != "CPARAM":
        raise Unsupported(f"flagdata: datacolumn={datacolumn!r} not supported yet "
                          f"(DATA, CORRECTED, MODEL, RESIDUAL, RESIDUAL_DATA; CPARAM for clip)")  # fmt: skip
    if mode == "tfcrop":
        for key, val, ok in (("timefit", timefit, ("line", "poly")),
                             ("freqfit", freqfit, ("line", "poly")),
                             ("flagdimension", flagdimension, ("freq", "time", "freqtime", "timefreq")),
                             ("usewindowstats", usewindowstats, ("none", "sum", "std", "both"))):  # fmt: skip
            if val not in ok:
                raise Unsupported(f"flagdata: {key}={val!r} (one of {ok})")
        if not 1 <= int(maxnpieces) <= 9 or not 1 <= int(halfwin) <= 3:
            raise Unsupported("flagdata: maxnpieces in 1-9 and halfwin in 1-3")
    if mode == "quack" and quackmode not in ("beg", "endb", "tail", "end"):
        raise Unsupported(f"flagdata: quackmode={quackmode!r}")
    sel_kw = {"field": field, "spw": spw, "antenna": antenna, "timerange": timerange,
              "correlation": correlation, "scan": scan, "uvrange": uvrange,
              "observation": observation, "array": array}  # fmt: skip
    if mode == "manual":
        sel_kw["autocorr"] = bool(autocorr)
    vis = Path(vis)
    if dc == "CPARAM" or _fd.is_caltable(vis):
        if mode != "clip" or dc != "CPARAM":
            raise Unsupported("flagdata: on a calibration table only mode='clip' with "
                              "datacolumn='CPARAM' is supported yet")  # fmt: skip
        if flagbackup:
            raise Unsupported("flagdata: flagbackup=True on a calibration table is not "
                              "supported yet (pass flagbackup=False)")  # fmt: skip
        if any(
            v for k, v in sel_kw.items() if k != "correlation"
        ) or correlation not in ("", "ABS_ALL"):
            raise Unsupported("flagdata: selections on a calibration table are not "
                              "supported yet")  # fmt: skip
        return _fd.clip_caltable(
            vis, list(clipminmax), clipoutside, clipzeros
        ).as_dict()
    if mode == "summary":
        return _fd.summary(vis, sel_kw, spwchan=spwchan, spwcorr=spwcorr, basecnt=basecnt,
                           name=name)  # fmt: skip
    if mode == "manual" and dc != "DATA":
        pass  # datacolumn has no effect on manual flags, as in CASA
    params = {
        "clipminmax": list(clipminmax), "clipoutside": clipoutside, "clipzeros": clipzeros,
        "datacolumn": dc, "quackinterval": quackinterval, "quackmode": quackmode,
        "quackincrement": quackincrement, "tolerance": tolerance,
        "lowerlimit": lowerlimit, "upperlimit": upperlimit, "ntime": ntime,
        "combinescans": combinescans, "timecutoff": timecutoff, "freqcutoff": freqcutoff,
        "timefit": timefit, "freqfit": freqfit, "maxnpieces": maxnpieces,
        "flagdimension": flagdimension, "usewindowstats": usewindowstats,
        "halfwin": halfwin, "extendflags": extendflags, "extendpols": extendpols,
        "growtime": growtime, "growfreq": growfreq, "growaround": growaround,
        "flagneartime": flagneartime, "flagnearfreq": flagnearfreq,
    }  # fmt: skip
    # flagbackup=True saves CASA's numbered version before this call; with
    # False rang still keeps the flags it first found (`rang_original`).
    backup = (
        _fd.next_backup_name(vis) if flagbackup else _fd.core_writeback.DEFAULT_BACKUP
    )
    return _fd.run(vis, mode, sel_kw, params, flag_backup=backup).as_dict()
