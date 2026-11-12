# SPDX-License-Identifier: GPL-3.0-or-later
"""A Measurement Set summary in CASA `listobs`'s terms (research/v8a-listobs.md).

`summary(ms)` returns the record CASA 6.7's `listobs` returns (the same keys
and units: times in MJD days, directions in radians), built from rang's own
reader (`rang.core_ms`), plus rang's additions under keys CASA's record does
not use: `observation`, `spectral_windows`, `sources`, `antennas`. `text`
formats it for people. Only scalar MAIN columns are read, never DATA or
FLAG. FEED is not read.

The conventions (how a scan splits into sub-entries, what the times mean) are
CASA's behaviour as documented and probed, not read from CASA's source
(research/v8a-listobs.md, section 6).
"""

from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path

import numpy as np

from . import core_ms
from .formats import _aipsio

DAY = 86400.0
MAIN_COLUMNS = (
    "TIME",
    "INTERVAL",
    "SCAN_NUMBER",
    "FIELD_ID",
    "DATA_DESC_ID",
    "STATE_ID",
    "ARRAY_ID",
    "OBSERVATION_ID",
)
# casacore MFrequency::Types.
FREQ_FRAMES = {
    0: "REST",
    1: "LSRK",
    2: "LSRD",
    3: "BARY",
    4: "GEO",
    5: "TOPO",
    6: "GALACTO",
    7: "LGROUP",
    8: "CMB",
    64: "Undefined",
}
# casacore Stokes::StokesTypes, the codes an MS CORR_TYPE holds.
STOKES = {
    1: "I",
    2: "Q",
    3: "U",
    4: "V",
    5: "RR",
    6: "RL",
    7: "LR",
    8: "LL",
    9: "XX",
    10: "XY",
    11: "YX",
    12: "YY",
    13: "RX",
    14: "RY",
    15: "LX",
    16: "LY",
    17: "XR",
    18: "XL",
    19: "YR",
    20: "YL",
}
# WGS84 ellipsoid.
WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563


class ListobsError(ValueError):
    """An MS listobs cannot summarise (no table, unreadable column)."""


def _table(path):
    path = Path(path)
    if not (path / "table.dat").is_file():
        raise ListobsError(f"{path} is not a casacore table (no table.dat)")
    return core_ms.open_table(path)


def _has(path):
    return (Path(path) / "table.dat").is_file()


def _cols(path, names, optional=()):
    """{name: array} of whole columns of a subtable; `optional` may be
    missing."""
    with _table(path) as t:
        out = {}
        for name in (*names, *optional):
            if name not in t.columns:
                if name in optional:
                    continue
                raise ListobsError(f"{path} has no column {name}")
            out[name] = t.getcol(name) if t.nrows else np.zeros(0)
        out["_nrows"] = t.nrows
    return out


def _measinfo_ref(path, column, default):
    """A column's MEASINFO `Ref` (e.g. J2000), or `default`."""
    try:
        keywords = _aipsio.column_descriptions(path)[column]["keywords"]
        return str(keywords.get("MEASINFO", {}).get("Ref", default))
    except (OSError, KeyError, ValueError, AttributeError):
        return default


def wgs84(xyz):
    """(longitude rad, latitude rad, height m) of ITRF positions (n, 3) on the
    WGS84 ellipsoid: Bowring's start, then fixed-point iteration on latitude
    to below 1e-15 rad."""
    xyz = np.atleast_2d(np.asarray(xyz, np.float64))
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    a, f = WGS84_A, WGS84_F
    b = a * (1.0 - f)
    e2 = f * (2.0 - f)
    ep2 = e2 / (1.0 - e2)
    p = np.hypot(x, y)
    lon = np.arctan2(y, x)
    theta = np.arctan2(z * a, p * b)
    lat = np.arctan2(z + ep2 * b * np.sin(theta) ** 3, p - e2 * a * np.cos(theta) ** 3)
    for _ in range(10):
        n = a / np.sqrt(1.0 - e2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        new = np.arctan2(z, p * (1.0 - e2 * n / (n + h)))
        done = np.max(np.abs(new - lat)) < 1e-15
        lat = new
        if done:
            break
    n = a / np.sqrt(1.0 - e2 * np.sin(lat) ** 2)
    h = p / np.cos(lat) - n
    return lon, lat, h


def _direction(m0, m1, refer):
    return {
        "m0": {"unit": "rad", "value": float(m0)},
        "m1": {"unit": "rad", "value": float(m1)},
        "refer": refer,
        "type": "direction",
    }


def _wrap(angle):
    """An angle in (-pi, pi]."""
    out = math.remainder(float(angle), 2 * math.pi)
    return math.pi if out == -math.pi else out


def summary(ms):
    """CASA listobs's returned record for `ms`, with rang's additions."""
    ms = Path(ms)
    if not _has(ms):
        raise ListobsError(f"{ms} is not a Measurement Set (no table.dat)")
    main = _cols(ms, MAIN_COLUMNS)
    nrows = int(main["_nrows"])
    time = np.asarray(main["TIME"], np.float64)
    interval = np.asarray(main["INTERVAL"], np.float64)
    scan = np.asarray(main["SCAN_NUMBER"], np.int64)
    field = np.asarray(main["FIELD_ID"], np.int64)
    ddid = np.asarray(main["DATA_DESC_ID"], np.int64)
    state = np.asarray(main["STATE_ID"], np.int64)

    fields = _cols(ms / "FIELD", ("NAME", "CODE", "PHASE_DIR"), ("SOURCE_ID",))
    field_ref = _measinfo_ref(ms / "FIELD", "PHASE_DIR", "J2000")
    dd = _cols(ms / "DATA_DESCRIPTION", ("SPECTRAL_WINDOW_ID", "POLARIZATION_ID"))
    spw_of_dd = [int(s) for s in dd["SPECTRAL_WINDOW_ID"]]
    pol_of_dd = [int(p) for p in dd["POLARIZATION_ID"]]
    field_names = [str(n) for n in fields["NAME"]]

    record = {}
    if nrows:
        start = time - interval / 2.0
        end = time + interval / 2.0
        begin_s, end_s = float(start.min()), float(end.max())
        record["BeginTime"] = begin_s / DAY
        record["EndTime"] = end_s / DAY
        record["IntegrationTime"] = end_s - begin_s
    # CASA lists only the fields that have rows in MAIN.
    used = sorted(int(f) for f in np.unique(field) if 0 <= f < int(fields["_nrows"]))
    record["nfields"] = len(used)
    record["numrecords"] = nrows
    record["timeref"] = "UTC"

    for f in used:
        pd = np.asarray(fields["PHASE_DIR"][f], np.float64).reshape(-1, 2)[0]
        record[f"field_{f}"] = {
            "code": str(fields["CODE"][f]),
            # RA in (-pi, pi], as CASA returns it.
            "direction": _direction(_wrap(pd[0]), pd[1], field_ref),
            "name": field_names[f],
        }

    # Scans, as CASA's record has them (amendment 2): one sub-entry per field
    # within a scan, in field-id order; every sub-entry of a scan carries the
    # scan's whole time range; a state change does not split a sub-entry
    # (StateId is the state of its first row in time order).
    order = np.argsort(time, kind="stable")
    per_scan = {}
    for s in np.unique(scan):
        in_scan = order[scan[order] == s]
        t0 = float((time[in_scan] - interval[in_scan] / 2.0).min())
        t1 = float((time[in_scan] + interval[in_scan] / 2.0).max())
        sub = per_scan.setdefault(f"scan_{int(s)}", {})
        for f in np.unique(field[in_scan]):
            rows = in_scan[field[in_scan] == f]
            f = int(f)
            spws = sorted({spw_of_dd[int(d)] for d in np.unique(ddid[rows])})
            sub[str(len(sub))] = {
                "BeginTime": t0 / DAY,
                "EndTime": t1 / DAY,
                "FieldId": f,
                "FieldName": field_names[f] if 0 <= f < len(field_names) else "",
                "IntegrationTime": float(np.mean(interval[rows])),
                "SpwIds": spws,
                "StateId": int(state[rows[0]]),
                "nRow": len(rows),
                "scanId": int(s),
            }
    record.update(per_scan)

    record["observation"] = _observation(ms)
    record["fields_extra"] = _fields_extra(fields, field, used)
    record["spectral_windows"] = _spectral_windows(ms, spw_of_dd, pol_of_dd, ddid)
    record["sources"] = _sources(ms)
    record["antennas"] = _antennas(ms)
    record["states"] = _states(ms)
    return record


def _observation(ms):
    out = {"observer": "", "project": "", "telescope": "", "time_range": []}
    if not _has(ms / "OBSERVATION"):
        return out
    ob = _cols(
        ms / "OBSERVATION", (), ("OBSERVER", "PROJECT", "TELESCOPE_NAME", "TIME_RANGE")
    )
    if ob["_nrows"]:
        out["observer"] = str(ob.get("OBSERVER", [""])[0])
        out["project"] = str(ob.get("PROJECT", [""])[0])
        out["telescope"] = str(ob.get("TELESCOPE_NAME", [""])[0])
        if "TIME_RANGE" in ob:
            out["time_range"] = [float(v) for v in np.ravel(ob["TIME_RANGE"][0])]
    return out


def _fields_extra(fields, field, used):
    counts = np.bincount(field[field >= 0], minlength=int(fields["_nrows"]))
    source = fields.get("SOURCE_ID")
    return [
        {
            "id": f,
            "nrows": int(counts[f]) if f < len(counts) else 0,
            "source_id": int(source[f]) if source is not None else -1,
        }
        for f in used
    ]


def _spectral_windows(ms, spw_of_dd, pol_of_dd, ddid):
    sw = _cols(
        ms / "SPECTRAL_WINDOW",
        ("NUM_CHAN", "CHAN_FREQ", "CHAN_WIDTH", "REF_FREQUENCY"),
        ("NAME", "TOTAL_BANDWIDTH", "MEAS_FREQ_REF"),
    )
    pol = _cols(ms / "POLARIZATION", ("CORR_TYPE",))
    used = {int(d) for d in np.unique(ddid)}
    out = []
    for s in range(int(sw["_nrows"])):
        freqs = np.asarray(sw["CHAN_FREQ"][s], np.float64).ravel()
        widths = np.asarray(sw["CHAN_WIDTH"][s], np.float64).ravel()
        dds = [d for d, w in enumerate(spw_of_dd) if w == s]
        corrs = []
        if dds:
            corrs = [
                STOKES.get(int(c), str(int(c)))
                for c in np.ravel(pol["CORR_TYPE"][pol_of_dd[dds[0]]])
            ]
        frame = (
            FREQ_FRAMES.get(int(sw["MEAS_FREQ_REF"][s]), str(sw["MEAS_FREQ_REF"][s]))
            if "MEAS_FREQ_REF" in sw
            else "TOPO"
        )
        total = (
            float(sw["TOTAL_BANDWIDTH"][s])
            if "TOTAL_BANDWIDTH" in sw
            else float(np.sum(np.abs(widths)))
        )
        out.append(
            {
                "id": s,
                "name": str(sw["NAME"][s]) if "NAME" in sw else "",
                "nchan": int(sw["NUM_CHAN"][s]),
                "frame": frame,
                "chan_freq_hz": freqs.tolist(),
                "chan_width_hz": widths.tolist(),
                "ref_freq_hz": float(sw["REF_FREQUENCY"][s]),
                "total_bandwidth_hz": total,
                "centre_freq_hz": float(np.mean(freqs)) if freqs.size else math.nan,
                "corr_types": corrs,
                "in_main": any(d in used for d in dds),
            }
        )
    return out


def _sources(ms):
    if not _has(ms / "SOURCE"):
        return []
    src = _cols(
        ms / "SOURCE",
        ("SOURCE_ID", "NAME"),
        ("SPECTRAL_WINDOW_ID", "REST_FREQUENCY", "SYSVEL"),
    )
    out = []
    for i in range(int(src["_nrows"])):
        entry = {
            "id": int(src["SOURCE_ID"][i]),
            "name": str(src["NAME"][i]),
            "spw_id": int(src["SPECTRAL_WINDOW_ID"][i])
            if "SPECTRAL_WINDOW_ID" in src
            else -1,
            "rest_freq_hz": [],
            "sysvel_m_s": [],
        }
        for key, name in (("REST_FREQUENCY", "rest_freq_hz"), ("SYSVEL", "sysvel_m_s")):
            if key in src and len(src[key]):
                entry[name] = [float(v) for v in np.ravel(src[key][i])]
        out.append(entry)
    return out


def _antennas(ms):
    an = _cols(
        ms / "ANTENNA", ("NAME", "POSITION"), ("STATION", "DISH_DIAMETER", "MOUNT")
    )
    if not an["_nrows"]:
        return []
    xyz = np.asarray(an["POSITION"], np.float64).reshape(-1, 3)
    lon, lat, h = wgs84(xyz)
    return [
        {
            "id": a,
            "name": str(an["NAME"][a]),
            "station": str(an["STATION"][a]) if "STATION" in an else "",
            "diameter_m": float(an["DISH_DIAMETER"][a])
            if "DISH_DIAMETER" in an
            else 0.0,
            "itrf_m": xyz[a].tolist(),
            "longitude_rad": float(lon[a]),
            "latitude_rad": float(lat[a]),
            "height_m": float(h[a]),
        }
        for a in range(int(an["_nrows"]))
    ]


def _states(ms):
    if not _has(ms / "STATE"):
        return []
    st = _cols(ms / "STATE", (), ("OBS_MODE",))
    return [str(m) for m in st.get("OBS_MODE", [])]


# --- text ---------------------------------------------------------------------

MJD_EPOCH = _dt.datetime(1858, 11, 17, tzinfo=_dt.timezone.utc)
MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def format_time(mjd_days, date=True):
    """CASA's `dd-Mon-yyyy/hh:mm:ss.s` (UTC) for an MJD in days."""
    t = MJD_EPOCH + _dt.timedelta(days=float(mjd_days))
    tenths = round(t.microsecond / 1e5)
    if tenths == 10:
        t, tenths = t.replace(microsecond=0) + _dt.timedelta(seconds=1), 0
    clock = f"{t.hour:02d}:{t.minute:02d}:{t.second:02d}.{tenths}"
    if not date:
        return clock
    return f"{t.day:02d}-{MONTHS[t.month - 1]}-{t.year}/{clock}"


def format_ra(rad):
    hours = (math.degrees(rad) / 15.0) % 24.0
    h = int(hours)
    m = int((hours - h) * 60)
    s = ((hours - h) * 60 - m) * 60
    if round(s, 5) >= 60.0:
        s, m = 0.0, m + 1
    if m == 60:
        m, h = 0, (h + 1) % 24
    return f"{h:02d}:{m:02d}:{s:08.5f}"


def format_dec(rad):
    deg = math.degrees(rad)
    sign = "-" if deg < 0 else "+"
    deg = abs(deg)
    d = int(deg)
    m = int((deg - d) * 60)
    s = ((deg - d) * 60 - m) * 60
    if round(s, 4) >= 60.0:
        s, m = 0.0, m + 1
    if m == 60:
        m, d = 0, d + 1
    return f"{sign}{d:02d}.{m:02d}.{s:07.4f}"


def _dms(rad):
    deg = math.degrees(rad)
    sign = "-" if deg < 0 else "+"
    deg = abs(deg)
    d = int(deg)
    m = int((deg - d) * 60)
    s = ((deg - d) * 60 - m) * 60
    return f"{sign}{d:03d}.{m:02d}.{s:05.2f}"


def text(record, ms=""):
    """A listobs-style report of `summary`'s record (the layout is rang's;
    research/v8a-listobs.md compares values, not layout)."""
    obs = record["observation"]
    lines = [
        "=" * 80,
        f"           MeasurementSet Name:  {ms}      MS Version 2",
        "=" * 80,
        f"   Observer: {obs['observer']}     Project: {obs['project']}  ",
        f"Observation: {obs['telescope']}",
        f"Data records: {record['numrecords']}",
    ]
    if "BeginTime" in record:
        lines += [
            f"   Total elapsed time = {record['IntegrationTime']:.5g} seconds",
            (
                f"   Observed from   {format_time(record['BeginTime'])}"
                f"   to   {format_time(record['EndTime'])} (UTC)"
            ),
        ]
    lines += ["", "Scans (one sub-entry per field in a scan):"]
    lines.append(
        "  Timerange (UTC)                           Scan  FldId FieldName"
        "             nRows  SpwIds  StateId  Average Interval(s)"
    )
    entries = []
    for key, value in record.items():
        if key.startswith("scan_"):
            entries += list(value.values())
    entries.sort(key=lambda e: (e["BeginTime"], e["scanId"]))
    for e in entries:
        lines.append(
            f"  {format_time(e['BeginTime'])} - {format_time(e['EndTime'], date=False)}"
            f"  {e['scanId']:5d}  {e['FieldId']:5d} {e['FieldName']:20s}"
            f" {e['nRow']:7d}  {e['SpwIds']!s:7s} {e['StateId']:7d}"
            f"  {e['IntegrationTime']:.3f}"
        )
    states = record.get("states", [])
    if states:
        lines += ["", "Scan intents (STATE OBS_MODE):"]
        lines += [f"  {i:3d}  {m}" for i, m in enumerate(states)]
    lines += [
        "",
        f"Fields: {record['nfields']}",
        (
            "  ID   Code Name                RA               Decl           Epoch"
            "   SrcId      nRows"
        ),
    ]
    extra = {e["id"]: e for e in record["fields_extra"]}
    for f in sorted(extra):
        fe = record[f"field_{f}"]
        d = fe["direction"]
        lines.append(
            f"  {f:<4d} {fe['code']:4s} {fe['name']:19s} {format_ra(d['m0']['value'])}"
            f" {format_dec(d['m1']['value'])}  {d['refer']:7s}"
            f" {extra[f]['source_id']:5d} {extra[f]['nrows']:10d}"
        )
    spws = record["spectral_windows"]
    lines += [
        "",
        f"Spectral Windows:  ({len(spws)} unique spectral windows)",
        (
            "  SpwID  Name   #Chans   Frame   Ch0(MHz)  ChanWid(kHz)  TotBW(kHz)"
            " CtrFreq(MHz)  Corrs"
        ),
    ]
    for s in spws:
        ch0 = s["chan_freq_hz"][0] / 1e6 if s["chan_freq_hz"] else math.nan
        wid = s["chan_width_hz"][0] / 1e3 if s["chan_width_hz"] else math.nan
        lines.append(
            f"  {s['id']:<6d} {s['name']:6s} {s['nchan']:6d}   {s['frame']:6s}"
            f" {ch0:10.3f} {wid:13.3f} {s['total_bandwidth_hz'] / 1e3:11.1f}"
            f" {s['centre_freq_hz'] / 1e6:12.4f}  {' '.join(s['corr_types'])}"
        )
    sources = record["sources"]
    if sources:
        lines += [
            "",
            f"Sources: {len(sources)}",
            "  ID   Name                SpwId RestFreq(MHz)  SysVel(km/s)",
        ]
        for s in sources:
            rest = " ".join(f"{v / 1e6:.6f}" for v in s["rest_freq_hz"]) or "-"
            vel = " ".join(f"{v / 1e3:.3f}" for v in s["sysvel_m_s"]) or "-"
            lines.append(
                f"  {s['id']:<4d} {s['name']:19s} {s['spw_id']:<5d} {rest:14s} {vel}"
            )
    ants = record["antennas"]
    lines += [
        "",
        f"Antennas: {len(ants)}:",
        (
            "  ID   Name  Station   Diam.    Long.(WGS84)  Lat.(WGS84)   Height(m)"
            "   ITRF Geocentric coordinates (m)"
        ),
    ]
    for a in ants:
        x, y, z = a["itrf_m"]
        lines.append(
            f"  {a['id']:<4d} {a['name']:5s} {a['station']:9s} {a['diameter_m']:4.1f} m"
            f"  {_dms(a['longitude_rad'])}  {_dms(a['latitude_rad'])}"
            f" {a['height_m']:10.3f}  {x:14.4f} {y:14.4f} {z:14.4f}"
        )
    return "\n".join(lines) + "\n"
