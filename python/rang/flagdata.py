# SPDX-License-Identifier: GPL-3.0-or-later
"""CASA's `flagdata` modes on a Measurement Set (task V8b,
research/v8b-flagdata.md).

Modes: `manual`, `clip`, `quack`, `shadow`, `elevation`, `tfcrop`,
`extend`, `unflag`, `summary`; `clip` also on a calibration table's
`CPARAM`. Written from casadocs 6.7 and CASA 6.7.6.14's behaviour on probe
MSs, with no CASA source read; every convention the documentation leaves
open is named in `research/v8b-flagdata.md` section 9 with the output it was
read from. `rang.tasks.flagdata` takes CASA's keyword names; this module
takes a parsed selection.

Flags are read and written in row spans through `core_writeback.WriteBack`
(a flag version saved before the first write, a journal). FLAG_ROW is set
where every cell of a row is flagged after the mode, and cleared by
`unflag` (section 9).
"""

from __future__ import annotations

import datetime as _dt
import fnmatch
import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import core_ms, core_writeback

MODES = (
    "manual", "clip", "quack", "shadow", "elevation", "tfcrop", "extend",
    "unflag", "summary",
)  # fmt: skip
STOKES = {
    1: "I", 2: "Q", 3: "U", 4: "V", 5: "RR", 6: "RL", 7: "LR", 8: "LL",
    9: "XX", 10: "XY", 11: "YX", 12: "YY",
}  # fmt: skip
OPERATORS = ("ABS", "ARG", "REAL", "IMAG", "NORM")
DATACOLUMNS = {
    "DATA": ("DATA",),
    "CORRECTED": ("CORRECTED_DATA",),
    "MODEL": ("MODEL_DATA",),
    "RESIDUAL": ("CORRECTED_DATA", "MODEL_DATA"),
    "RESIDUAL_DATA": ("DATA", "MODEL_DATA"),
}
MJD_EPOCH = _dt.datetime(1858, 11, 17, tzinfo=_dt.timezone.utc)
UNITS_HZ = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}
UNITS_M = {"m": 1.0, "km": 1e3}


class SelectionError(ValueError):
    """A selection string rang cannot parse or that selects nothing."""


# -- metadata ------------------------------------------------------------------


MAIN = (
    "TIME", "INTERVAL", "ANTENNA1", "ANTENNA2", "FIELD_ID", "DATA_DESC_ID",
    "SCAN_NUMBER", "OBSERVATION_ID", "ARRAY_ID", "PROCESSOR_ID", "UVW",
)  # fmt: skip


def _col(path, name):
    with core_ms.open_table(path) as t:
        if name not in t.columns:
            return None
        return t.getcol(name) if t.nrows else np.zeros(0)


@dataclass
class Meta:
    """What the selections and the modes need of an MS."""

    path: Path
    main: dict
    ant_names: list
    ant_pos: np.ndarray
    ant_diam: np.ndarray
    field_names: list
    field_dir: np.ndarray  # (nfield, 2) rad, the first polynomial term
    spw_freq: list  # per spw, channel centres (Hz)
    spw_width: list
    spw_names: list
    dd_spw: np.ndarray
    dd_pol: np.ndarray
    pol_corr: list
    processor_type: list
    nchan: int = 0
    ncorr: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def nrows(self):
        return len(self.main["TIME"])

    def corr_names(self):
        """CORR_TYPE names of the one cell layout (rows of one shape)."""
        pols = {int(self.dd_pol[d]) for d in np.unique(self.main["DATA_DESC_ID"])}
        names = {
            tuple(STOKES.get(int(c), str(c)) for c in self.pol_corr[p]) for p in pols
        }
        if len(names) != 1:
            raise SelectionError(f"{self.path}: more than one correlation layout")
        return list(names.pop())

    def row_spw(self):
        return self.dd_spw[self.main["DATA_DESC_ID"]]


def read_meta(ms, reader=None):
    """`Meta` of `ms`. `reader(name)` reads a MAIN column (a write-back
    session's `read`); without it MAIN is opened read-only."""
    ms = Path(ms)
    main = {}
    if reader is None:
        with core_ms.open_table(ms) as t:
            for name in MAIN:
                main[name] = t.getcol(name)
    else:
        for name in MAIN:
            main[name] = reader(name)
    for name in MAIN:
        if name not in ("TIME", "INTERVAL", "UVW"):
            main[name] = np.asarray(main[name], np.int64)
    ant = ms / "ANTENNA"
    pol = ms / "POLARIZATION"
    with core_ms.open_table(pol) as t:
        pol_corr = [np.asarray(t.getcol("CORR_TYPE", i, 1)[0]) for i in range(t.nrows)]
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        n = t.nrows
        spw_freq = [
            np.asarray(t.getcol("CHAN_FREQ", i, 1)[0], np.float64) for i in range(n)
        ]
        spw_width = [
            np.asarray(t.getcol("CHAN_WIDTH", i, 1)[0], np.float64) for i in range(n)
        ]
        spw_names = [str(v) for v in t.getcol("NAME")] if n else []
    field_dir = np.asarray(_col(ms / "FIELD", "PHASE_DIR"), np.float64)
    field_dir = field_dir.reshape(len(field_dir), -1, 2)[:, 0, :]
    proc = ms / "PROCESSOR"
    ptype = (
        [str(v) for v in _col(proc, "TYPE")] if (proc / "table.dat").exists() else []
    )
    meta = Meta(
        path=ms,
        main=main,
        ant_names=[str(v) for v in _col(ant, "NAME")],
        ant_pos=np.asarray(_col(ant, "POSITION"), np.float64),
        ant_diam=np.asarray(_col(ant, "DISH_DIAMETER"), np.float64),
        field_names=[str(v) for v in _col(ms / "FIELD", "NAME")],
        field_dir=field_dir,
        spw_freq=spw_freq,
        spw_width=spw_width,
        spw_names=spw_names,
        dd_spw=np.asarray(
            _col(ms / "DATA_DESCRIPTION", "SPECTRAL_WINDOW_ID"), np.int64
        ),
        dd_pol=np.asarray(_col(ms / "DATA_DESCRIPTION", "POLARIZATION_ID"), np.int64),
        pol_corr=pol_corr,
        processor_type=ptype,
    )
    return meta


# -- selection -----------------------------------------------------------------


@dataclass
class Selection:
    """Rows, channels per spectral window and correlations selected."""

    rows: np.ndarray  # bool (nrow,)
    chans: dict  # spw id -> bool (nchan,)
    corrs: np.ndarray  # bool (ncorr,)
    operator: str = "ABS"

    def cells(self, meta, start, n):
        """bool (n, nchan, ncorr) of the selected cells of rows start..start+n."""
        spw = meta.row_spw()[start : start + n]
        rows = self.rows[start : start + n]
        nchan = meta.nchan
        out = np.zeros((n, nchan, len(self.corrs)), bool)
        for s in np.unique(spw[rows]):
            pick = rows & (spw == s)
            ch = self.chans.get(int(s))
            if ch is None:
                continue
            out[pick] = ch[:, None] & self.corrs[None, :]
        return out


def _split(text, sep=","):
    return [p.strip() for p in str(text).split(sep) if p.strip()]


def _int_ranges(text, what):
    """A CASA id list: `a`, `a~b`, `<a`, `>a`, comma separated, as a
    predicate on integers."""
    preds = []
    for part in _split(text):
        m = re.fullmatch(r"(\d+)\s*~\s*(\d+)", part)
        if m:
            lo, hi = int(m[1]), int(m[2])
            preds.append(lambda v, lo=lo, hi=hi: (v >= lo) & (v <= hi))
        elif re.fullmatch(r"\d+", part):
            preds.append(lambda v, k=int(part): v == k)
        elif re.fullmatch(r"<\s*\d+", part):
            preds.append(lambda v, k=int(part[1:]): v < k)
        elif re.fullmatch(r">\s*\d+", part):
            preds.append(lambda v, k=int(part[1:]): v > k)
        else:
            raise SelectionError(f"{what}={text!r}: cannot parse {part!r}")
    return preds


def _match_ids(text, values, what):
    values = np.asarray(values)
    out = np.zeros(len(values), bool)
    for pred in _int_ranges(text, what):
        out |= pred(values)
    return out


def select_fields(meta, text):
    """bool (nfield,) of a CASA field selection: ids, ranges, names (with
    `*` patterns)."""
    n = len(meta.field_names)
    out = np.zeros(n, bool)
    ids = np.arange(n)
    for part in _split(text):
        if re.fullmatch(r"[\d~<>\s]+", part):
            out |= _match_ids(part, ids, "field")
        else:
            hit = np.array(
                [fnmatch.fnmatchcase(nm, part) for nm in meta.field_names], bool
            )
            if not hit.any():
                raise SelectionError(f"field={text!r}: no field named {part!r}")
            out |= hit
    return out


def _antenna_ids(meta, token):
    names = meta.ant_names
    token = token.strip()
    if re.fullmatch(r"\d+", token) and token not in names:
        k = int(token)
        if not 0 <= k < len(names):
            raise SelectionError(f"antenna {token!r} out of range")
        return {k}
    hit = {i for i, nm in enumerate(names) if fnmatch.fnmatchcase(nm, token)}
    if not hit:
        raise SelectionError(f"no antenna {token!r}")
    return hit


def select_baselines(meta, text):
    """bool (nrow,) of a CASA antenna selection: `A`, `A&B`, `A&&B`, `A&&&`,
    `A&`, `!item`, `;`-separated antenna lists inside an item."""
    a1, a2 = meta.main["ANTENNA1"], meta.main["ANTENNA2"]
    pos = np.zeros(len(a1), bool)
    neg = np.zeros(len(a1), bool)
    any_pos = False
    for item in _split(text, ","):
        negate = item.startswith("!")
        if negate:
            item = item[1:].strip()
        m = re.fullmatch(r"(.*?)(&{1,3})(.*)", item)
        if m:
            left, amp, right = m[1], m[2], m[3]
        else:
            left, amp, right = item, "", ""
        lhs = set().union(*(_antenna_ids(meta, t) for t in _split(left, ";")))
        lhs_m = np.isin(a1, list(lhs)), np.isin(a2, list(lhs))
        auto = a1 == a2
        if amp == "":
            # CASA: every baseline with an antenna of the list, cross only
            # (section 9, convention A1).
            sel = (
                (lhs_m[0] | lhs_m[1]) & ~auto
                if CONV["antenna_plain_cross_only"]
                else (lhs_m[0] | lhs_m[1])
            )
        elif amp == "&&&":
            if right:
                raise SelectionError(f"antenna={text!r}: '&&&' takes no right side")
            sel = (lhs_m[0] | lhs_m[1]) & auto
        else:
            if right:
                rhs = set().union(*(_antenna_ids(meta, t) for t in _split(right, ";")))
            else:
                rhs = set(range(len(meta.ant_names)))
            r_m = np.isin(a1, list(rhs)), np.isin(a2, list(rhs))
            sel = (lhs_m[0] & r_m[1]) | (r_m[0] & lhs_m[1])
            if amp == "&":
                sel &= ~auto
        if negate:
            neg |= sel
        else:
            pos |= sel
            any_pos = True
    if not any_pos:
        pos[:] = True
    return pos & ~neg


def _parse_time(text, day0):
    """MJD seconds of a CASA time `YYYY/MM/DD/hh:mm:ss[.s]`, `hh:mm:ss`
    (the day of `day0`, MJD seconds) or `YYYY/MM/DD`."""
    text = text.strip()
    m = re.fullmatch(
        r"(?:(\d{4})/(\d{1,2})/(\d{1,2})(?:/|$))?(?:(\d{1,2}):(\d{1,2})(?::(\d{1,2}(?:\.\d*)?))?)?",
        text,
    )
    if not m or not text:
        raise SelectionError(f"timerange: cannot parse {text!r}")
    if m[1]:
        d = _dt.datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=_dt.timezone.utc)
        base = (d - MJD_EPOCH).total_seconds()
    else:
        base = math.floor(day0 / 86400.0) * 86400.0
    secs = 0.0
    if m[4] is not None:
        secs = int(m[4]) * 3600 + int(m[5]) * 60 + float(m[6] or 0)
    return base + secs


def select_timerange(meta, text):
    """bool (nrow,) of a CASA timerange: `T1~T2`, `>T`, `<T`, `T`, lists.
    The second time of `T1~T2` without a date takes T1's date."""
    time = meta.main["TIME"]
    interval = meta.main["INTERVAL"]
    day0 = float(time.min())
    out = np.zeros(len(time), bool)
    for part in _split(text):
        if "~" in part:
            lo_s, hi_s = part.split("~", 1)
            lo = _parse_time(lo_s, day0)
            hi = _parse_time(hi_s, lo if "/" not in hi_s else day0)
            out |= _time_in(time, interval, lo, hi)
        elif part.startswith(">"):
            out |= _time_in(time, interval, _parse_time(part[1:], day0), np.inf)
        elif part.startswith("<"):
            out |= _time_in(time, interval, -np.inf, _parse_time(part[1:], day0))
        else:
            t = _parse_time(part, day0)
            out |= _time_in(time, interval, t, t)
    return out


def _time_in(time, interval, lo, hi):
    """Rows of a time range (section 9, convention T1)."""
    if CONV["timerange"] == "centre":
        return (time >= lo) & (time <= hi)
    half = interval / 2.0
    return (time + half > lo) & (time - half < hi)


def select_uvrange(meta, text):
    uvw = np.asarray(meta.main["UVW"], np.float64)
    uv = np.hypot(uvw[:, 0], uvw[:, 1])
    out = np.zeros(len(uv), bool)
    for part in _split(text):
        m = re.fullmatch(
            r"([<>]?)\s*([\d.eE+-]+)\s*(?:~\s*([\d.eE+-]+))?\s*([a-zA-Z]*)", part
        )
        if not m:
            raise SelectionError(f"uvrange={text!r}: cannot parse {part!r}")
        unit = (m[4] or "m").lower()
        if unit not in UNITS_M:
            raise SelectionError(
                f"uvrange={text!r}: unit {m[4]!r} not supported (m, km)"
            )
        k = UNITS_M[unit]
        a = float(m[2]) * k
        if m[3]:
            out |= (uv >= a) & (uv <= float(m[3]) * k)
        elif m[1] == "<":
            out |= uv < a
        elif m[1] == ">":
            out |= uv > a
        else:
            out |= uv == a
    return out


def _freq_hz(text):
    m = re.fullmatch(r"([\d.eE+-]+)\s*([a-zA-Z]*)", text.strip())
    if not m:
        return None
    unit = m[2].lower()
    if unit == "":
        return None
    if unit not in UNITS_HZ:
        raise SelectionError(f"spw: unit {m[2]!r} not supported")
    return float(m[1]) * UNITS_HZ[unit]


def _chan_range(freq, width, part):
    """bool (nchan,) of one channel range `a~b`, `a`, or `f1~f2UNIT`."""
    nchan = len(freq)
    m = re.fullmatch(
        r"\s*([\d.eE+-]+\s*[a-zA-Z]*)\s*(?:~\s*([\d.eE+-]+\s*[a-zA-Z]*))?\s*", part
    )
    if not m:
        raise SelectionError(f"spw: cannot parse channels {part!r}")
    lo_s, hi_s = m[1], m[2] if m[2] is not None else m[1]
    unit = re.search(r"[a-zA-Z]+$", hi_s.strip())
    if unit:
        if not re.search(r"[a-zA-Z]+$", lo_s.strip()):
            lo_s = lo_s.strip() + unit[0]
        lo, hi = _freq_hz(lo_s), _freq_hz(hi_s)
        return _freq_channels(freq, width, lo, hi)
    if "^" in part:
        raise SelectionError("spw: channel steps (^) are not supported")
    lo, hi = int(float(lo_s)), int(float(hi_s))
    out = np.zeros(nchan, bool)
    out[max(lo, 0) : min(hi, nchan - 1) + 1] = True
    return out


def _freq_channels(freq, width, lo, hi):
    """Channels of a frequency range (section 9, S1): from the first
    channel whose centre is at or above `lo` to the last whose centre is at
    or below `hi`, the two swapped when the range falls between two centres
    (CASA then selects both neighbours); ranges outside the band clip to
    its edge channels."""
    lo, hi = min(lo, hi), max(lo, hi)
    out = np.zeros(len(freq), bool)
    order = np.argsort(freq)
    f = freq[order]
    if hi < f[0] or lo > f[-1]:
        return out
    a = int(np.searchsorted(f, lo, side="left"))
    b = int(np.searchsorted(f, hi, side="right")) - 1
    a, b = min(a, len(f) - 1), max(b, 0)
    if a > b:
        a, b = b, a
    out[order[a : b + 1]] = True
    return out


def select_spw(meta, text):
    """{spw id: bool (nchan,)} of a CASA spw selection."""
    nspw = len(meta.spw_freq)
    out = {}
    for part in _split(text):
        spw_s, _, chan_s = part.partition(":")
        spw_s = spw_s.strip()
        if spw_s in ("*", ""):
            spws = list(range(nspw))
        elif re.fullmatch(r"[\d~<>\s]+", spw_s):
            spws = [s for s in range(nspw) if _match_ids(spw_s, [s], "spw")[0]]
        else:
            spws = [
                s
                for s, nm in enumerate(meta.spw_names)
                if fnmatch.fnmatchcase(nm, spw_s)
            ]
            if not spws:
                raise SelectionError(f"spw={text!r}: no spectral window {spw_s!r}")
        for s in spws:
            freq, width = meta.spw_freq[s], meta.spw_width[s]
            if chan_s.strip():
                ch = np.zeros(len(freq), bool)
                for c in _split(chan_s, ";"):
                    ch |= _chan_range(freq, width, c)
            else:
                ch = np.ones(len(freq), bool)
            if ch.any():
                out[s] = out.get(s, np.zeros(len(freq), bool)) | ch
    if not out:
        raise SelectionError(f"spw={text!r} selects no channels")
    return out


def parse_correlation(meta, text, mode):
    """(operator, bool (ncorr,)) of a CASA correlation string."""
    names = meta.corr_names()
    text = str(text or "").strip().upper()
    op = "ABS"
    if not text:
        return op, np.ones(len(names), bool)
    m = re.fullmatch(r"(ABS|ARG|REAL|IMAG|NORM)_(.*)", text)
    if m:
        if mode not in ("clip", "tfcrop"):
            raise SelectionError(
                f"correlation={text!r}: operators are for clip and tfcrop"
            )
        op, text = m[1], m[2]
    out = np.zeros(len(names), bool)
    for part in _split(text):
        if part == "ALL":
            out[:] = True
        elif part in names:
            out[names.index(part)] = True
        else:
            raise SelectionError(f"correlation {part!r} not in {names}")
    return op, out


def select(meta, mode="manual", field="", spw="", antenna="", timerange="",
           correlation="", scan="", uvrange="", observation="", array="",
           autocorr=False):  # fmt: skip
    """`Selection` of CASA's selection keywords on `meta`."""
    n = meta.nrows
    rows = np.ones(n, bool)
    if field:
        rows &= select_fields(meta, field)[meta.main["FIELD_ID"]]
    if antenna:
        rows &= select_baselines(meta, antenna)
    if timerange:
        rows &= select_timerange(meta, timerange)
    if scan:
        rows &= _match_ids(scan, meta.main["SCAN_NUMBER"], "scan")
    if uvrange:
        rows &= select_uvrange(meta, uvrange)
    if observation:
        rows &= _match_ids(observation, meta.main["OBSERVATION_ID"], "observation")
    if array:
        rows &= _match_ids(array, meta.main["ARRAY_ID"], "array")
    if autocorr:
        auto = meta.main["ANTENNA1"] == meta.main["ANTENNA2"]
        proc = meta.main["PROCESSOR_ID"]
        if meta.processor_type:
            ok = np.array([t.upper() == "CORRELATOR" for t in meta.processor_type])
            auto &= np.where(
                (proc >= 0) & (proc < len(ok)), ok[np.clip(proc, 0, len(ok) - 1)], True
            )
        rows &= auto
    chans = (select_spw(meta, spw) if spw else
             {s: np.ones(len(f), bool) for s, f in enumerate(meta.spw_freq)})  # fmt: skip
    rows &= np.isin(meta.row_spw(), list(chans))
    op, corrs = parse_correlation(meta, correlation, mode)
    return Selection(rows=rows, chans=chans, corrs=corrs, operator=op)


# -- conventions read off CASA's output (research/v8b-flagdata.md section 9) ----

CONV = {
    "antenna_plain_cross_only": True,
    "timerange": "centre",  # rows whose TIME is inside the range (T1)
    "quack_start": "time",  # scan start: first TIME (not TIME - INTERVAL/2)
    "quack_scan_key": ("OBSERVATION_ID", "ARRAY_ID", "SCAN_NUMBER", "FIELD_ID"),
    "elevation_frame": "geocentric",
}


# -- the row-local modes ---------------------------------------------------------


def _value(data, op):
    if op == "ABS":
        return np.abs(data)
    if op == "ARG":
        return np.angle(data)
    if op == "REAL":
        return data.real
    if op == "IMAG":
        return data.imag
    if op == "NORM":
        return np.abs(data) ** 2
    raise SelectionError(f"operator {op}")


def clip_cells(values, sel_cells, clipminmax, clipoutside, clipzeros):
    """bool cells `clip` flags among `sel_cells` of real `values`."""
    bad = ~np.isfinite(values)
    if clipminmax is not None and len(clipminmax) == 2:
        lo, hi = float(clipminmax[0]), float(clipminmax[1])
        with np.errstate(invalid="ignore"):
            if clipoutside:
                bad |= (values < lo) | (values > hi)
            else:
                bad |= (values >= lo) & (values <= hi)
    if clipzeros:
        bad |= values == 0
    return bad & sel_cells


def _data(w, columns, start, n):
    if len(columns) == 1:
        return w.read(columns[0], start, n)
    return w.read(columns[0], start, n) - w.read(columns[1], start, n)


def quack_rows(
    meta, rows, interval, mode, increment=False, flag_row=None, flags_all=None
):
    """bool (nrow,) of the rows `quack` flags among `rows`."""
    m = meta.main
    time, half = m["TIME"], m["INTERVAL"] / 2.0
    keys = np.stack([m[k] for k in CONV["quack_scan_key"]], axis=1)
    out = np.zeros(meta.nrows, bool)
    idx = np.flatnonzero(rows)
    if not len(idx):
        return out
    _, group = np.unique(keys[idx], axis=0, return_inverse=True)
    group = group.reshape(-1)
    for g in range(group.max() + 1):
        mine = idx[group == g]
        t = time[mine]
        live = mine
        if increment and flags_all is not None:
            live = mine[~flags_all[mine]]
            if not len(live):
                continue
        if CONV["quack_start"] == "time":
            t0, t1 = time[live].min(), time[live].max()
        else:
            t0, t1 = (time[live] - half[live]).min(), (time[live] + half[live]).max()
        # The window includes its boundary (section 9, Q1).
        if mode == "beg":
            hit = t <= t0 + interval
        elif mode == "endb":
            hit = t >= t1 - interval
        elif mode == "tail":
            hit = t > t0 + interval
        elif mode == "end":
            hit = t < t1 - interval
        else:
            raise SelectionError(f"quackmode {mode!r}")
        out[mine[hit]] = True
    return out


def elevation_rows(meta, rows, lower, upper):
    """bool (nrow,): rows where either antenna's elevation of the row's
    field is below `lower` or above `upper` (degrees)."""
    from . import measures

    m = meta.main
    out = np.zeros(meta.nrows, bool)
    idx = np.flatnonzero(rows)
    if not len(idx):
        return out
    key = np.stack([m["TIME"][idx], m["FIELD_ID"][idx].astype(np.float64)], axis=1)
    uk, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    ants = np.unique(np.concatenate([m["ANTENNA1"][idx], m["ANTENNA2"][idx]]))
    el = np.full((len(uk), len(meta.ant_names)), np.nan)
    for f in np.unique(uk[:, 1]).astype(int):
        pick = uk[:, 1] == f
        ra, dec = meta.field_dir[f]
        for a in ants:
            el[pick, a] = measures.elevation(uk[pick, 0], ra, dec, meta.ant_pos[a],
                                             frame=CONV["elevation_frame"])  # fmt: skip
    lo, hi = np.radians(lower), np.radians(upper)
    e1 = el[inv, m["ANTENNA1"][idx]]
    e2 = el[inv, m["ANTENNA2"][idx]]
    bad = (e1 < lo) | (e1 > hi) | (e2 < lo) | (e2 > hi)
    out[idx[bad]] = True
    meta.extra["elevation"] = {"rows": idx, "el1": e1, "el2": e2}
    return out


def _source_itrs(times, ra, dec):
    """Unit vectors (n, 3) of a J2000 direction in ITRS at MS TIMEs."""
    from astropy import units
    from astropy.coordinates import ITRS, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False
    when = Time(np.asarray(times, np.float64) / 86400.0, format="mjd", scale="utc")
    src = SkyCoord(ra * units.rad, dec * units.rad, frame="icrs")
    xyz = src.transform_to(ITRS(obstime=when)).cartesian.xyz.value.T
    return xyz / np.linalg.norm(xyz, axis=1, keepdims=True)


def shadow_rows(meta, rows, tolerance=0.0):
    """bool (nrow,): rows with an antenna shadowed at that time by another
    antenna of the ANTENNA table (section 9, H1, H2). A pair's projected
    separation and w come from the UVW column of its row at that time (MS
    convention, ANTENNA1 - ANTENNA2), or, for a pair without a row then,
    from the antenna positions and the field's direction in ITRS. The pair
    shadows when the separation is below r1 + r2 - `tolerance`; the antenna
    farther from the source (ANTENNA2 when w > 0) is flagged on all its rows
    at that time."""
    m = meta.main
    out = np.zeros(meta.nrows, bool)
    time, field = m["TIME"], m["FIELD_ID"]
    a1, a2, uvw = m["ANTENNA1"], m["ANTENNA2"], np.asarray(m["UVW"], np.float64)
    nant = len(meta.ant_names)
    r = meta.ant_diam / 2.0
    pos = meta.ant_pos
    times = np.unique(time[rows])
    first_field = {}
    for t in times:
        first_field[t] = int(field[np.flatnonzero(time == t)[0]])
    src = {}
    for f in sorted(set(first_field.values())):
        ts = np.array([t for t in times if first_field[t] == f])
        for t, v in zip(ts, _source_itrs(ts, *meta.field_dir[f]), strict=True):
            src[t] = v
    iu, ju = np.triu_indices(nant, 1)
    limit = r[iu] + r[ju] - tolerance
    margin = np.inf
    order = np.argsort(time, kind="stable")
    bounds = np.searchsorted(time[order], times, side="left")
    ends = np.searchsorted(time[order], times, side="right")
    for t, lo, hi in zip(times, bounds, ends, strict=True):
        at = order[lo:hi]
        at = at[a1[at] != a2[at]]
        bvec = pos[iu] - pos[ju]
        wv = bvec @ src[t]
        dist = np.sqrt(np.maximum((bvec * bvec).sum(axis=1) - wv * wv, 0.0))
        # Rows present at this time: their UVW column instead.
        key = {(int(a), int(b)): k for k, a, b in zip(at, a1[at], a2[at], strict=True)}
        for p, (i, j) in enumerate(zip(iu, ju, strict=True)):
            k = key.get((int(i), int(j)))
            sign = 1.0
            if k is None:
                k = key.get((int(j), int(i)))
                sign = -1.0
            if k is not None:
                dist[p] = math.hypot(uvw[k, 0], uvw[k, 1])
                wv[p] = sign * uvw[k, 2]
        margin = (
            min(margin, float(np.min(np.abs(dist - limit)))) if len(dist) else margin
        )
        hit = dist < limit
        dead = set(np.where(wv[hit] > 0, ju[hit], iu[hit]).tolist())
        if dead:
            mine = order[lo:hi]
            mine = mine[rows[mine]]
            sel = np.isin(a1[mine], list(dead)) | np.isin(a2[mine], list(dead))
            out[mine[sel]] = True
    meta.extra["shadow_margin_m"] = None if math.isinf(margin) else margin
    return out


# -- chunks (ntime, combinescans) ----------------------------------------------


def parse_ntime(ntime):
    """Seconds of CASA's `ntime` (`'scan'` is infinite)."""
    if isinstance(ntime, (int, float)):
        return float(ntime)
    text = str(ntime).strip().lower()
    if text == "scan":
        return math.inf
    m = re.fullmatch(r"([\d.eE+-]+)\s*(s|sec|min|h)?", text)
    if not m:
        raise SelectionError(f"ntime={ntime!r}: cannot parse")
    k = {"s": 1.0, "sec": 1.0, None: 1.0, "min": 60.0, "h": 3600.0}[m[2]]
    return float(m[1]) * k


def chunks(meta, rows, ntime="scan", combinescans=False):
    """Chunk number (or -1) of every row, as CASA's flagdata iterates them:
    sorted by OBSERVATION_ID, ARRAY_ID, (SCAN_NUMBER unless combinescans),
    FIELD_ID, DATA_DESC_ID and TIME, with casacore's `MSInterval` time
    blocks of `ntime` seconds (`rang.flag_extend.casa_chunks`)."""
    from .flag_extend import casa_chunks

    m = meta.main
    out = np.full(meta.nrows, -1, np.int64)
    idx = np.flatnonzero(rows)
    if not len(idx):
        return out
    secs = parse_ntime(ntime)
    if math.isinf(secs) and combinescans:
        raise SelectionError("combinescans=True needs ntime in seconds")
    scan = m["SCAN_NUMBER"][idx] if not combinescans else np.zeros(len(idx), np.int64)
    obs = m["OBSERVATION_ID"][idx] * (1 << 20) + scan
    out[idx] = casa_chunks(obs, m["ARRAY_ID"][idx], m["FIELD_ID"][idx],
                           m["DATA_DESC_ID"][idx], m["TIME"][idx],
                           ntime=secs if not math.isinf(secs) else 1.0e30)  # fmt: skip
    return out


# -- the driver ------------------------------------------------------------------


@dataclass
class Result:
    mode: str
    rows: int = 0
    cells_selected: int = 0
    flagged_before: int = 0
    flagged_after: int = 0
    flag_sha256: str = ""
    extra: dict = field(default_factory=dict)

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _finish_rows(flag, flag_row_old, mode, whole_rows, hit_rows):
    """FLAG_ROW after a mode (section 9, R1 as amended post hoc after the
    held-out run): when the mode flags whole rows (manual, quack, shadow,
    elevation without a spw or correlation selection), CASA sets FLAG_ROW
    on exactly the rows the mode flags (`hit_rows`), already flagged or
    not, and on no other; `unflag` clears it where it leaves a cell
    unflagged; clip, extend and tfcrop, and any spw or correlation
    selection, leave FLAG_ROW as it was."""
    if mode == "unflag":
        return flag_row_old & flag.all(axis=(1, 2))
    if whole_rows and mode in ("manual", "quack", "shadow", "elevation"):
        return flag_row_old | hit_rows
    return flag_row_old


def run(
    ms, mode, sel_kw, params, flag_backup=core_writeback.DEFAULT_BACKUP, chunk_rows=None
):
    """Run one writing mode on `ms`. `sel_kw` holds the selection keywords
    of `select`; `params` the mode's. Returns a `Result`."""
    ms = Path(ms)
    res = Result(mode=mode)
    # Everything that can refuse runs before the write-back session opens,
    # so a refused call leaves the MS (and its journal) as it was.
    meta = read_meta(ms)
    meta.nchan, meta.ncorr = core_writeback.layout(ms)["cell"]
    sel = select(meta, mode, **sel_kw)
    res.rows = int(sel.rows.sum())
    if not res.rows:
        # CASA: "MSSelectionNullSelection : The selected table has zero rows."
        raise SelectionError("the selection has zero rows")
    columns = DATACOLUMNS[str(params.get("datacolumn", "DATA")).upper()]
    if mode in ("clip", "tfcrop"):
        with core_ms.open_table(ms) as t:
            missing = [c for c in columns if c not in t.columns]
        if missing:
            raise SelectionError(f"{ms} has no column {', '.join(missing)}")
    whole_rows = not sel_kw.get("spw") and not sel_kw.get("correlation")
    rowflag = None
    if mode == "quack":
        flags_all = None
        if params.get("quackincrement"):
            with core_ms.open_table(ms) as t:
                flags_all = np.concatenate([
                    np.asarray(t.getcol("FLAG", s0, n), bool).all(axis=(1, 2))
                    for s0, n in core_writeback.flagversions.spans(meta.nrows, 1 << 14)
                ])  # fmt: skip
        rowflag = quack_rows(meta, sel.rows, float(params.get("quackinterval", 1.0)),
                             params.get("quackmode", "beg"),
                             bool(params.get("quackincrement")), flags_all=flags_all)  # fmt: skip
    elif mode == "elevation":
        rowflag = elevation_rows(meta, sel.rows, float(params.get("lowerlimit", 0.0)),
                                 float(params.get("upperlimit", 90.0)))  # fmt: skip
    elif mode == "shadow":
        rowflag = shadow_rows(meta, sel.rows, float(params.get("tolerance", 0.0)))
    with core_writeback.WriteBack(ms, flag_backup=flag_backup, stage=f"flagdata {mode}",
                                  chunk_rows=chunk_rows) as w:  # fmt: skip
        spans = list(w.chunks(chunk_rows))
        if mode in ("tfcrop", "extend"):
            _run_chunked(w, meta, sel, mode, params, spans, res)
        else:
            digest = hashlib.sha256()
            for s0, n in spans:
                flag = w.read("FLAG", s0, n).astype(bool)
                old_row = w.read("FLAG_ROW", s0, n).astype(bool)
                cells = sel.cells(meta, s0, n)
                res.cells_selected += int(cells.sum())
                res.flagged_before += int(flag.sum())
                if mode == "manual":
                    flag |= cells
                elif mode == "unflag":
                    flag &= ~cells
                elif mode in ("quack", "elevation", "shadow"):
                    flag |= cells & rowflag[s0 : s0 + n, None, None]
                elif mode == "clip":
                    values = _value(_data(w, columns, s0, n), sel.operator)
                    flag |= clip_cells(values, cells, params.get("clipminmax"),
                                       params.get("clipoutside", True),
                                       params.get("clipzeros", False))  # fmt: skip
                hit = sel.rows[s0 : s0 + n]
                if rowflag is not None:
                    hit = hit & rowflag[s0 : s0 + n]
                new_row = _finish_rows(flag, old_row, mode, whole_rows, hit)
                res.flagged_after += int(flag.sum())
                w.write_flags(s0, flag, new_row)
                digest.update(np.ascontiguousarray(flag).tobytes())
            res.flag_sha256 = digest.hexdigest()
    res.extra.update({k: v for k, v in meta.extra.items() if not isinstance(v, dict)})
    return res


def _run_chunked(w, meta, sel, mode, params, spans, res):
    """tfcrop and extend: whole CASA chunks of rows at a time."""
    from . import flag_extend, tfcrop

    chunk = chunks(meta, sel.rows, params.get("ntime", "scan"),
                   bool(params.get("combinescans", False)))  # fmt: skip
    rows = np.flatnonzero(chunk >= 0)
    nchunk = int(chunk.max()) + 1 if len(rows) else 0
    sizes = np.bincount(chunk[rows], minlength=nchunk) if nchunk else np.zeros(0, int)
    a1, a2 = meta.main["ANTENNA1"], meta.main["ANTENNA2"]
    limit = w.chunk_rows()
    columns = DATACOLUMNS[params.get("datacolumn", "DATA").upper()]
    counts = {}
    for mine in flag_extend._batches(rows, chunk, a1, a2, sizes, limit):
        flag = flag_extend._read_rows(w, "FLAG", mine, spans).astype(bool)
        cells = np.zeros_like(flag)
        spw = meta.row_spw()[mine]
        for s in np.unique(spw):
            pick = spw == s
            cells[pick] = sel.chans[int(s)][:, None] & sel.corrs[None, :]
        res.cells_selected += int(cells.sum())
        res.flagged_before += int(flag.sum())
        if mode == "tfcrop":
            data = _read_data_rows(w, columns, mine, spans)
            values = _value(data, sel.operator)
            new = tfcrop.flag_chunk(values, flag, cells, a1[mine], a2[mine],
                                    meta.main["TIME"][mine], chunk[mine], params)  # fmt: skip
            flag |= new & cells
            if params.get("extendflags", True):
                ext = {"growtime": 50.0, "growfreq": 80.0, "growaround": False,
                       "flagneartime": False, "flagnearfreq": False, "extendpols": True}  # fmt: skip
                _extend(flag, cells, a1[mine], a2[mine], meta.main["TIME"][mine], chunk[mine],
                        ext)  # fmt: skip
        else:
            ext = {k: params.get(k, d) for k, d in (
                ("growtime", 50.0), ("growfreq", 50.0), ("growaround", False),
                ("flagneartime", False), ("flagnearfreq", False), ("extendpols", True))}  # fmt: skip
            got = _extend(flag, cells, a1[mine], a2[mine], meta.main["TIME"][mine],
                          chunk[mine], ext)  # fmt: skip
            for k, v in got.items():
                counts[k] = counts.get(k, 0) + v
        res.flagged_after += int(flag.sum())
        _write_rows_flags(w, mine, flag, spans)
    res.extra["added"] = counts
    digest = hashlib.sha256()
    for s0, n in spans:
        digest.update(
            np.ascontiguousarray(w.read("FLAG", s0, n).astype(bool)).tobytes()
        )
    res.flag_sha256 = digest.hexdigest()


def _extend(flag, cells, a1, a2, time, chunk, settings):
    """E0's kernel on the selected cells only: unselected cells are hidden
    as unflagged, extended, then restored."""
    from .flag_extend import extend_flags

    work = (flag & cells).astype(np.uint8)
    if not cells.all():
        # Unselected channels and correlations take no part: extend the
        # selected sub-cube.
        chans = cells.any(axis=(0, 2))
        corrs = cells.any(axis=(0, 1))
        sub = np.ascontiguousarray(work[:, chans][:, :, corrs])
        got = extend_flags(sub, a1, a2, time, chunk, settings)
        view = flag[:, chans]
        view[:, :, corrs] |= sub.astype(bool)
        flag[:, chans] = view
        return got
    got = extend_flags(work, a1, a2, time, chunk, settings)
    flag |= work.astype(bool)
    return got


def _read_data_rows(w, columns, rows, spans):
    from .flag_extend import _read_rows

    if len(columns) == 1:
        return _read_rows(w, columns[0], rows, spans)
    return _read_rows(w, columns[0], rows, spans) - _read_rows(
        w, columns[1], rows, spans
    )


def _write_rows_flags(w, rows, flag, spans):
    for s0, n in spans:
        pick = (rows >= s0) & (rows < s0 + n)
        if not pick.any():
            continue
        out = w.read("FLAG", s0, n).astype(bool)
        out[rows[pick] - s0] = flag[pick]
        w.write_flags(s0, out)


def next_backup_name(ms):
    """CASA's next automatic flag version name, `flagdata_<n>`."""
    from .formats import flagversions

    n = 1
    while flagversions.exists(ms, f"flagdata_{n}"):
        n += 1
    return f"flagdata_{n}"


# -- summary ---------------------------------------------------------------------


def summary(ms, sel_kw, spwchan=False, spwcorr=False, basecnt=False, fieldcnt=False,
            name="Summary"):  # fmt: skip
    """CASA's `flagdata(mode='summary')` dictionary for `ms` (reads only)."""
    ms = Path(ms)
    meta = read_meta(ms)
    with core_ms.open_table(ms) as t:
        first = t.getcol("FLAG", 0, 1)
        meta.nchan, meta.ncorr = first.shape[1:]
        sel = select(meta, "summary", **sel_kw)
        m = meta.main
        corr_names = meta.corr_names()
        acc = {}

        def add(group, key, tot, flg):
            d = acc.setdefault(group, {}).setdefault(key, [0, 0])
            d[0] += tot
            d[1] += flg

        spw_of = meta.row_spw()
        total = flagged = 0
        for s0, n in core_writeback.flagversions.spans(meta.nrows, 1 << 14):
            flag = t.getcol("FLAG", s0, n).astype(bool)
            cells = sel.cells(meta, s0, n)
            f = flag & cells
            tot_r = cells.sum(axis=(1, 2))
            flg_r = f.sum(axis=(1, 2))
            total += int(tot_r.sum())
            flagged += int(flg_r.sum())
            sl = slice(s0, s0 + n)
            x1, x2 = m["ANTENNA1"][sl], m["ANTENNA2"][sl]
            # An autocorrelation counts once for its antenna (section 9, U1).
            x2 = np.where(x1 == x2, -1, x2)
            for xs in (x1, x2):
                for v in np.unique(xs[xs >= 0]):
                    pick = xs == v
                    add(
                        "antenna",
                        int(v),
                        int(tot_r[pick].sum()),
                        int(flg_r[pick].sum()),
                    )
                    if basecnt:
                        sc = m["SCAN_NUMBER"][sl]
                        for s_ in np.unique(sc[pick]):
                            p2 = pick & (sc == s_)
                            add("antenna:scan", f"{meta.ant_names[v]}:{s_}",
                                int(tot_r[p2].sum()), int(flg_r[p2].sum()))  # fmt: skip
            for group, values in (
                ("array", m["ARRAY_ID"][sl]), ("observation", m["OBSERVATION_ID"][sl]),
                ("scan", m["SCAN_NUMBER"][sl]), ("spw", spw_of[sl]),
                ("field", m["FIELD_ID"][sl]),
            ):  # fmt: skip
                for v in np.unique(values):
                    pick = values == v
                    add(group, int(v), int(tot_r[pick].sum()), int(flg_r[pick].sum()))
            for c, cname in enumerate(corr_names):
                add(
                    "correlation",
                    cname,
                    int(cells[:, :, c].sum()),
                    int(f[:, :, c].sum()),
                )
            if basecnt:
                for bl in np.unique(
                    np.stack([m["ANTENNA1"][sl], m["ANTENNA2"][sl]], 1), axis=0
                ):
                    pick = (m["ANTENNA1"][sl] == bl[0]) & (m["ANTENNA2"][sl] == bl[1])
                    key = f"{meta.ant_names[bl[0]]}&&{meta.ant_names[bl[1]]}"
                    add("baseline", key, int(tot_r[pick].sum()), int(flg_r[pick].sum()))
            if spwchan or spwcorr:
                for s in np.unique(spw_of[sl]):
                    pick = spw_of[sl] == s
                    if spwchan:
                        tc = cells[pick].sum(axis=(0, 2))
                        fc = f[pick].sum(axis=(0, 2))
                        for ch in np.flatnonzero(tc):
                            add("spw:channel", f"{s}:{ch}", int(tc[ch]), int(fc[ch]))
                    if spwcorr:
                        for c, cname in enumerate(corr_names):
                            add("spw:correlation", f"{s}:{cname}",
                                int(cells[pick][:, :, c].sum()), int(f[pick][:, :, c].sum()))  # fmt: skip
    return _summary_record(meta, acc, total, flagged, name)


def _summary_record(meta, acc, total, flagged, name):
    out = {
        "name": name,
        "type": "summary",
        "total": float(total),
        "flagged": float(flagged),
    }
    ant = {meta.ant_names[k]: v for k, v in acc.get("antenna", {}).items()}
    out["antenna"] = {
        k: {"total": float(v[0]), "flagged": float(v[1])} for k, v in ant.items()
    }
    names = {
        "array": str,
        "observation": str,
        "scan": str,
        "spw": str,
        "correlation": str,
    }
    for group, conv in names.items():
        out[group] = {conv(k): {"total": float(v[0]), "flagged": float(v[1])}
                      for k, v in acc.get(group, {}).items()}  # fmt: skip
    out["field"] = {meta.field_names[k]: {"total": float(v[0]), "flagged": float(v[1])}
                    for k, v in acc.get("field", {}).items()}  # fmt: skip
    for group in ("baseline", "antenna:scan", "spw:channel", "spw:correlation"):
        if group in acc:
            out[group] = {k: {"total": float(v[0]), "flagged": float(v[1])}
                          for k, v in acc[group].items()}  # fmt: skip
    return out


# -- calibration tables ----------------------------------------------------------


def is_caltable(path):
    path = Path(path)
    try:
        with core_ms.open_table(path) as t:
            return "CPARAM" in t.columns or "FPARAM" in t.columns
    except Exception:  # noqa: BLE001 - any unreadable table is not a cal table
        return False


def clip_caltable(path, clipminmax, clipoutside=True, clipzeros=False, column="CPARAM",
                  operator="ABS"):  # fmt: skip
    """CASA's `clip` on a calibration table's `column` (all correlations)."""
    from . import core_ms_write

    path = Path(path)
    with core_ms.open_table(path) as t:
        values = _value(t.getcol(column), operator)
        flag = t.getcol("FLAG").astype(bool)
    before = int(flag.sum())
    flag |= clip_cells(values, np.ones_like(flag), clipminmax, clipoutside, clipzeros)
    with core_ms_write.open_table(path, readonly=False) as t:
        t.putcol("FLAG", flag)
    return Result(mode="clip", rows=len(flag), cells_selected=int(flag.size),
                  flagged_before=before, flagged_after=int(flag.sum()),
                  flag_sha256=hashlib.sha256(np.ascontiguousarray(flag).tobytes()).hexdigest())  # fmt: skip


__all__ = [
    "CONV", "MODES", "Meta", "Result", "Selection", "SelectionError", "chunks",
    "clip_caltable", "is_caltable", "read_meta", "run", "select", "summary",
]  # fmt: skip
