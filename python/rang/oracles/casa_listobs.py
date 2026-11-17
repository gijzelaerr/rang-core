# SPDX-License-Identifier: GPL-3.0-or-later
"""rang's `listobs` record against CASA's (research/v8a-listobs.md, section 4).

`compare(rang, casa, msmd, text)` takes rang's record (`rang.listobs.summary`),
CASA's returned record, the supplementary `msmetadata` record and CASA's
listfile text, as `tools/oracles/casa/listobs.py` writes them, and returns
`{"differences": [...], "compared": N}`. The tolerances are the frozen ones;
a value present on one side only is a difference.
"""

from __future__ import annotations

import hashlib
import math
import re

import numpy as np

from ..listobs import STOKES

DAY = 86400.0
TIME_S = 1e-3  # 1 ms
ANGLE_RAD = 1e-3 / 3600 * math.pi / 180  # 1e-3 arcsec
FREQ_HZ = 1.0
POSITION_M = 1e-3


class _Diff:
    def __init__(self):
        self.differences = []
        self.compared = 0
        self.worst = {}  # value kind -> largest |rang - casa| seen

    def exact(self, where, rang, casa):
        self.compared += 1
        if rang != casa:
            self.differences.append({"where": where, "rang": rang, "casa": casa})

    def near(self, where, rang, casa, tol, wrap=None):
        self.compared += 1
        if rang is None or casa is None:
            self.differences.append({"where": where, "rang": rang, "casa": casa})
            return
        d = float(rang) - float(casa)
        if wrap:
            d = (d + wrap / 2) % wrap - wrap / 2
        kind = re.sub(r"\d+", "N", where)
        self.worst[kind] = max(self.worst.get(kind, 0.0), abs(d))
        if not abs(d) <= tol:
            self.differences.append(
                {"where": where, "rang": rang, "casa": casa, "diff": d, "tol": tol}
            )

    def keys(self, where, rang, casa):
        self.exact(where, sorted(rang), sorted(casa))


def _value(x):
    """A CASA quantity ({"value": v, "unit": u}) or a bare number."""
    return x["value"] if isinstance(x, dict) else x


def _list(x):
    return [int(v) for v in np.ravel(x)]


def compare(rang, casa, msmd=None, text=None):
    d = _Diff()
    for key in ("BeginTime", "EndTime"):
        d.near(key, rang.get(key), casa.get(key), TIME_S / DAY)
    d.near(
        "IntegrationTime",
        rang.get("IntegrationTime"),
        casa.get("IntegrationTime"),
        TIME_S,
    )
    for key in ("numrecords", "nfields"):
        d.exact(key, rang.get(key), casa.get(key))

    fields = [k for k in casa if k.startswith("field_")]
    d.keys("field keys", [k for k in rang if k.startswith("field_")], fields)
    for k in fields:
        if k not in rang:
            continue
        r, c = rang[k], casa[k]
        d.exact(f"{k}.name", r["name"], c["name"])
        d.exact(f"{k}.code", r["code"], c["code"])
        rd, cd = r["direction"], c["direction"]
        d.exact(f"{k}.direction.refer", rd["refer"], cd["refer"])
        d.near(
            f"{k}.direction.m0",
            _value(rd["m0"]),
            _value(cd["m0"]),
            ANGLE_RAD,
            wrap=2 * math.pi,
        )
        d.near(f"{k}.direction.m1", _value(rd["m1"]), _value(cd["m1"]), ANGLE_RAD)

    scans = [k for k in casa if k.startswith("scan_")]
    d.keys("scan keys", [k for k in rang if k.startswith("scan_")], scans)
    for k in scans:
        if k not in rang:
            continue
        d.keys(f"{k} sub-entries", rang[k], casa[k])
        for sub, c in casa[k].items():
            r = rang[k].get(sub)
            if r is None:
                continue
            w = f"{k}.{sub}"
            for t in ("BeginTime", "EndTime"):
                d.near(f"{w}.{t}", r[t], c[t], TIME_S / DAY)
            d.near(
                f"{w}.IntegrationTime",
                r["IntegrationTime"],
                c["IntegrationTime"],
                TIME_S,
            )
            for key in ("FieldId", "FieldName", "StateId", "nRow", "scanId"):
                d.exact(f"{w}.{key}", r[key], c[key])
            d.exact(f"{w}.SpwIds", _list(r["SpwIds"]), _list(c["SpwIds"]))

    if msmd is not None and "failed" not in msmd:
        _spws(d, rang["spectral_windows"], msmd["spws"])
        _antennas(d, rang["antennas"], msmd["antennas"])
    elif msmd is not None:
        d.differences.append({"where": "msmd", "casa": msmd["failed"]})
    if text is not None:
        _text(d, rang, parse_text(text))
    return {"differences": d.differences, "compared": d.compared, "worst": d.worst}


def channels_sha256(values):
    """SHA-256 of channel values as little-endian float64 (archives)."""
    return hashlib.sha256(np.asarray(values, "<f8").tobytes()).hexdigest()


def _channels(d, w, rf, rw, c):
    cf, cw = np.asarray(c["chanfreqs"], float), np.asarray(c["chanwidths"], float)
    d.exact(f"{w}.chan count", (rf.size, rw.size), (cf.size, cw.size))
    if rf.size == cf.size and rf.size:
        diff = float(np.max(np.abs(rf - cf)))
        d.near(f"{w}.chan_freq max diff", diff, 0.0, FREQ_HZ)
        d.near(f"{w}.chan_freq[0]", rf[0], cf[0], FREQ_HZ)
    if rw.size == cw.size and rw.size:
        diff = float(np.max(np.abs(rw - cw)))
        d.near(f"{w}.chan_width max diff", diff, 0.0, FREQ_HZ)


def _spws(d, rang, casa):
    d.exact("spw count", len(rang), len(casa))
    for s, (r, c) in enumerate(zip(rang, casa, strict=False)):
        w = f"spw {s}"
        d.exact(f"{w}.name", r["name"], c["name"])
        d.exact(f"{w}.nchan", r["nchan"], int(c["nchan"]))
        corr = [STOKES.get(int(x), str(x)) for x in np.ravel(c["corrtypes"])]
        d.exact(f"{w}.corr_types", r["corr_types"], corr)
        rf, rw = np.asarray(r["chan_freq_hz"]), np.asarray(r["chan_width_hz"])
        if "chanfreqs" in c:
            _channels(d, w, rf, rw, c)
        else:  # an archive: the channels as SHA-256 only, so exact
            for key, values in (("chanfreqs", rf), ("chanwidths", rw)):
                got = channels_sha256(values)
                d.exact(f"{w}.{key} sha256", got, c[f"{key}_sha256"])
        d.near(
            f"{w}.total_bandwidth",
            r["total_bandwidth_hz"],
            _value(c["bandwidth"]),
            FREQ_HZ,
        )
        d.near(
            f"{w}.ref_freq",
            r["ref_freq_hz"],
            _value(c["reffreq"]["m0"])
            if isinstance(c["reffreq"], dict) and "m0" in c["reffreq"]
            else _value(c["reffreq"]),
            FREQ_HZ,
        )
        d.near(f"{w}.centre_freq", r["centre_freq_hz"], _value(c["meanfreq"]), FREQ_HZ)


def _itrf_xyz(angles):
    """casacore ITRF position as (longitude, latitude, radius) to xyz."""
    lon, lat, rad = (float(v) for v in angles)
    return (
        rad * math.cos(lat) * math.cos(lon),
        rad * math.cos(lat) * math.sin(lon),
        rad * math.sin(lat),
    )


def _antennas(d, rang, casa):
    d.exact("antenna count", len(rang), len(casa))
    for a, (r, c) in enumerate(zip(rang, casa, strict=False)):
        w = f"antenna {a}"
        d.exact(f"{w}.name", r["name"], c["name"])
        d.exact(f"{w}.station", r["station"], c["station"])
        d.near(f"{w}.diameter", r["diameter_m"], c["diameter_m"], POSITION_M)
        xyz = _itrf_xyz(c["itrf_angles"])
        for axis, (rv, cv) in enumerate(zip(r["itrf_m"], xyz, strict=True)):
            d.near(f"{w}.itrf[{axis}]", rv, cv, POSITION_M)
        d.exact(f"{w}.wgs84 refer", "WGS84", c["refer"])
        d.near(
            f"{w}.longitude",
            r["longitude_rad"],
            c["longitude_rad"],
            ANGLE_RAD,
            wrap=2 * math.pi,
        )
        d.near(f"{w}.latitude", r["latitude_rad"], c["latitude_rad"], ANGLE_RAD)
        d.near(f"{w}.height", r["height_m"], c["height_m"], POSITION_M)


# --- CASA's listfile ------------------------------------------------------------


def _section(lines, start):
    """Lines after the first line matching `start`, up to a blank line or
    the next heading."""
    for i, line in enumerate(lines):
        if re.match(start, line.strip()):
            out = []
            for nxt in lines[i + 1 :]:
                # A section ends at a blank line or the next heading (CASA
                # starts headings in column 0 and rows with spaces).
                if not nxt.strip() or not nxt[:1].isspace():
                    break
                out.append(nxt)
            return out
    return None


def parse_text(text):
    """The values section 4 takes from CASA's listfile text."""
    lines = text.splitlines()
    out = {}
    for line in lines:
        m = re.search(r"Observer:\s*(.*?)\s{2,}Project:\s*(.*?)\s*$", line)
        if m and "observer" not in out:
            out["observer"], out["project"] = m.group(1).strip(), m.group(2).strip()
        m = re.match(r"\s*Observation:\s*(\S.*?)\s*(\(|$)", line)
        if m and "telescope" not in out:
            out["telescope"] = m.group(1).strip()
    fields = _section(lines, r"Fields:")
    if fields is not None:
        has_source = bool(fields) and "SrcId" in fields[0]
        rows = {}
        for line in fields[1:]:
            parts = line.split()
            if parts and parts[0].isdigit():
                row = {"nrows": int(parts[-1])}
                if has_source:
                    row["source_id"] = int(parts[-2])
                rows[int(parts[0])] = row
        out["fields"] = rows
    spws = _section(lines, r"Spectral Windows:")
    if spws is not None:
        rows = {}
        for line in spws[1:]:
            m = re.match(r"\s*(\d+)\s+(\S+)\s+(\d+)\s+(\S+)\s", line)
            if m:
                rows[int(m.group(1))] = {"name": m.group(2), "frame": m.group(4)}
        out["spws"] = rows
    sources = _section(lines, r"Sources:")
    if sources is not None:
        rows = []
        for line in sources[1:]:
            parts = line.split()
            if len(parts) >= 3 and parts[0].isdigit():
                rows.append(
                    {
                        "id": int(parts[0]),
                        "name": parts[1],
                        "spw_id": int(parts[2]),
                        "rest": parts[3:],
                    }
                )
        out["sources"] = rows
    return out


def _text(d, rang, parsed):
    obs = rang["observation"]
    for key in ("observer", "project", "telescope"):
        d.exact(f"text {key}", obs[key], parsed.get(key))
    if "fields" in parsed:
        extra = {e["id"]: e for e in rang["fields_extra"]}
        for f, c in parsed["fields"].items():
            r = extra.get(f, {})
            d.exact(f"text field {f} nrows", r.get("nrows"), c["nrows"])
            if "source_id" in c:
                d.exact(f"text field {f} source id", r.get("source_id"), c["source_id"])
    if "spws" in parsed:
        spws = {s["id"]: s for s in rang["spectral_windows"]}
        for s, c in parsed["spws"].items():
            d.exact(f"text spw {s} frame", spws.get(s, {}).get("frame"), c["frame"])
    if "sources" in parsed:
        got = [(s["id"], s["name"], s["spw_id"]) for s in rang["sources"]]
        want = [(s["id"], s["name"], s["spw_id"]) for s in parsed["sources"]]
        d.exact("text sources", got, want)
    else:
        d.exact("text sources", rang["sources"], [])
