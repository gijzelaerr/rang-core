# SPDX-License-Identifier: GPL-3.0-or-later
"""Write V8b's synthetic MSs with rang's table writer (research/v8b-flagdata.md,
sections 4.1 and 4.2).

Usage: v8b_cases.py OUT_DIR [syn-noise syn-rfi syn-edges]

All three: six MeerKAT-like antennas (ENU offsets from the array centre,
ITRF positions through astropy's WGS84), linear feeds XX XY YX YY, one field,
UVW computed from the antenna positions and the field's apparent hour angle,
8 s integrations.

- `syn-noise`: 15 cross baselines, 120 integrations in one scan, 256
  channels; DATA = smooth bandpass (per baseline, per correlation) times
  (1 + complex Gaussian noise / 10); no RFI, no flags.
- `syn-rfi`: `syn-noise` plus persistent narrow-band lines, a time burst on
  all channels, a broadband spike on one baseline and 2 % pre-existing
  flags; the injected cells are written to `syn-rfi.inject.npz`.
- `syn-edges`: 21 baselines with autocorrelations; four scans (20, 1, 12
  and 40 integrations, the last with its field rising through 20 degrees
  elevation); two spectral windows (32 channels of 1 MHz from 850 MHz, 32
  of 0.5 MHz from 1415 MHz); antenna m001 39 m from m000 towards the field
  (its projected separation crosses 13.5 m near 20 degrees elevation); DATA with NaN, Inf, zeros and amplitudes on and next to
  50 Jy; existing FLAG and FLAG_ROW; scan 3 begins with two flagged
  integrations.
- `syn-edges-uvwneg`, `syn-edges-nom001` (amendment 2): `syn-edges` with
  UVW negated, and without the rows of m001.
"""

import json
import sys
from pathlib import Path

import numpy as np
from rang import core_ms_write

CENTRE = (21.44389, -30.71317, 1051.0)  # lon, lat (deg), height (m)
ENU = (
    (0.0, 0.0, 0.0),
    (0.0, 20.0, 0.0),
    (100.0, -50.0, 0.5),
    (-300.0, 200.0, 1.0),
    (800.0, 400.0, -2.0),
    (-1500.0, -900.0, 3.0),
)
T0 = 61041.0 * 86400.0  # 2026-01-01 00:00 UTC, MJD seconds
DT = 8.0
CORR = [9, 10, 11, 12]


def _astropy():
    from astropy import units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False
    return u, AltAz, EarthLocation, SkyCoord, Time


def itrf_positions(enu=ENU):
    u, _, EarthLocation, _, _ = _astropy()
    lon, lat, h = (np.radians(CENTRE[0]), np.radians(CENTRE[1]), CENTRE[2])
    centre = EarthLocation.from_geodetic(CENTRE[0] * u.deg, CENTRE[1] * u.deg, h * u.m)
    c = np.array([centre.x.value, centre.y.value, centre.z.value])
    out = []
    for e, n, up in enu:
        # ENU to ECEF rotation at the centre.
        x = (
            -np.sin(lon) * e
            - np.sin(lat) * np.cos(lon) * n
            + np.cos(lat) * np.cos(lon) * up
        )
        y = (
            np.cos(lon) * e
            - np.sin(lat) * np.sin(lon) * n
            + np.cos(lat) * np.sin(lon) * up
        )
        z = np.cos(lat) * n + np.sin(lat) * up
        out.append(c + np.array([x, y, z]))
    return np.array(out)


def elevation(times, ra, dec, xyz):
    u, AltAz, EarthLocation, SkyCoord, Time = _astropy()
    loc = EarthLocation.from_geocentric(*xyz, unit=u.m)
    t = Time(np.asarray(times) / 86400.0, format="mjd", scale="utc")
    src = SkyCoord(ra * u.rad, dec * u.rad, frame="icrs")
    return src.transform_to(AltAz(obstime=t, location=loc)).alt.rad


def _azimuth(time, ra, dec, xyz):
    u, AltAz, EarthLocation, SkyCoord, Time = _astropy()
    loc = EarthLocation.from_geocentric(*xyz, unit=u.m)
    t = Time(time / 86400.0, format="mjd", scale="utc")
    src = SkyCoord(ra * u.rad, dec * u.rad, frame="icrs")
    return float(src.transform_to(AltAz(obstime=t, location=loc)).az.rad)


def uvw(times, ra, dec, xyz, a1, a2):
    """UVW (m) of each row in the MS convention (the position of ANTENNA1
    minus that of ANTENNA2, as the LUNO slice's UVW column has it), from the
    apparent Greenwich hour angle."""
    *_, Time = _astropy()
    t = Time(np.asarray(times) / 86400.0, format="mjd", scale="utc")
    gast = t.sidereal_time("apparent", "greenwich").rad
    h = gast - ra
    b = xyz[a1] - xyz[a2]
    sh, ch, sd, cd = np.sin(h), np.cos(h), np.sin(dec), np.cos(dec)
    uu = sh * b[:, 0] + ch * b[:, 1]
    vv = -sd * ch * b[:, 0] + sd * sh * b[:, 1] + cd * b[:, 2]
    ww = cd * ch * b[:, 0] - cd * sh * b[:, 1] + sd * b[:, 2]
    return np.stack([uu, vv, ww], axis=1)


def _ms(path, nrow, nchan):
    desc = [
        core_ms_write.makearrcoldesc("DATA", 0j, shape=[nchan, 4], valuetype="complex"),
        core_ms_write.makearrcoldesc("FLAG", False, shape=[nchan, 4]),
        core_ms_write.makearrcoldesc("WEIGHT", 0.0, shape=[4], valuetype="float"),
        core_ms_write.makearrcoldesc("SIGMA", 0.0, shape=[4], valuetype="float"),
    ]
    dminfo = {
        "*1": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledData",
            "COLUMNS": ["DATA"],
            "SPEC": {"DEFAULTTILESHAPE": [4, nchan, max(1, 32768 // (nchan * 4))]},
        }
    }
    t = core_ms_write.default_ms(str(path), desc, dminfo)
    t.addrows(nrow)
    return t


def _sub(path, name, n):
    s = core_ms_write.open_table(Path(path) / name, readonly=False)
    s.addrows(n)
    return s


def _subtables(path, xyz, field, spws, observer):
    with _sub(path, "ANTENNA", len(xyz)) as s:
        names = [f"m{a:03d}" for a in range(len(xyz))]
        s.putcol("NAME", names)
        s.putcol("STATION", names)
        s.putcol("TYPE", ["GROUND-BASED"] * len(xyz))
        s.putcol("MOUNT", ["ALT-AZ"] * len(xyz))
        s.putcol("DISH_DIAMETER", np.full(len(xyz), 13.5))
        for a, p in enumerate(xyz):
            s.putcell("POSITION", a, np.asarray(p))
            s.putcell("OFFSET", a, np.zeros(3))
    with _sub(path, "FEED", len(xyz)) as s:
        s.putcol("ANTENNA_ID", np.arange(len(xyz), dtype=np.int32))
        s.putcol("FEED_ID", np.zeros(len(xyz), np.int32))
        s.putcol("SPECTRAL_WINDOW_ID", np.full(len(xyz), -1, np.int32))
        s.putcol("TIME", np.full(len(xyz), T0))
        s.putcol("INTERVAL", np.full(len(xyz), 1.0e30))
        s.putcol("NUM_RECEPTORS", np.full(len(xyz), 2, np.int32))
        s.putcol("BEAM_ID", np.full(len(xyz), -1, np.int32))
        for a in range(len(xyz)):
            s.putcell("POLARIZATION_TYPE", a, np.array(["X", "Y"]))
            s.putcell("RECEPTOR_ANGLE", a, np.array([-np.pi / 2, -np.pi / 2]))
            s.putcell("POL_RESPONSE", a, np.eye(2, dtype=np.complex64))
            s.putcell("BEAM_OFFSET", a, np.zeros((2, 2)))
            s.putcell("POSITION", a, np.zeros(3))
    with _sub(path, "FIELD", 1) as s:
        name, ra, dec = field
        s.putcol("NAME", [name])
        s.putcol("CODE", ["T"])
        s.putcol("NUM_POLY", np.zeros(1, np.int32))
        s.putcol("TIME", np.array([T0]))
        for col in ("PHASE_DIR", "DELAY_DIR", "REFERENCE_DIR"):
            s.putcell(col, 0, np.array([[ra, dec]]))
    with _sub(path, "SPECTRAL_WINDOW", len(spws)) as s:
        for k, (f0, df, n) in enumerate(spws):
            freq = f0 + df * np.arange(n)
            s.putcell("CHAN_FREQ", k, freq)
            for col in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
                s.putcell(col, k, np.full(n, df))
            s.putcell("REF_FREQUENCY", k, freq[0])
            s.putcell("NUM_CHAN", k, np.int32(n))
            s.putcell("TOTAL_BANDWIDTH", k, df * n)
            s.putcell("MEAS_FREQ_REF", k, np.int32(5))
            s.putcell("NAME", k, f"spw{k}")
            s.putcell("NET_SIDEBAND", k, np.int32(1))
            s.putcell("FLAG_ROW", k, False)
    with _sub(path, "POLARIZATION", 1) as s:
        s.putcol("NUM_CORR", np.array([4], np.int32))
        s.putcell("CORR_TYPE", 0, np.array(CORR, np.int32))
        s.putcell(
            "CORR_PRODUCT", 0, np.array([[0, 0], [0, 1], [1, 0], [1, 1]], np.int32)
        )
        s.putcol("FLAG_ROW", np.array([False]))
    with _sub(path, "DATA_DESCRIPTION", len(spws)) as s:
        s.putcol("SPECTRAL_WINDOW_ID", np.arange(len(spws), dtype=np.int32))
        s.putcol("POLARIZATION_ID", np.zeros(len(spws), np.int32))
        s.putcol("FLAG_ROW", np.zeros(len(spws), bool))
    with _sub(path, "OBSERVATION", 1) as s:
        s.putcol("TELESCOPE_NAME", ["MeerKAT"])
        s.putcol("OBSERVER", [observer])
        s.putcol("PROJECT", ["v8b-flagdata"])
    with _sub(path, "PROCESSOR", 1) as s:
        s.putcol("TYPE", ["CORRELATOR"])
        s.putcol("SUB_TYPE", ["MeerKAT"])
        s.putcol("TYPE_ID", np.zeros(1, np.int32))
        s.putcol("MODE_ID", np.zeros(1, np.int32))
        s.putcol("FLAG_ROW", np.zeros(1, bool))


def _main_rows(t, times, a1, a2, scan, ddid, uvw_m, interval=DT):
    n = len(times)
    zeros = np.zeros(n, np.int32)
    t.putcol("ANTENNA1", a1.astype(np.int32))
    t.putcol("ANTENNA2", a2.astype(np.int32))
    for name in ("FIELD_ID", "ARRAY_ID", "OBSERVATION_ID", "FEED1", "FEED2"):
        t.putcol(name, zeros)
    t.putcol("PROCESSOR_ID", zeros)
    t.putcol("STATE_ID", zeros - 1)
    t.putcol("DATA_DESC_ID", ddid.astype(np.int32))
    t.putcol("SCAN_NUMBER", scan.astype(np.int32))
    t.putcol("TIME", times)
    t.putcol("TIME_CENTROID", times)
    t.putcol("INTERVAL", np.full(n, interval))
    t.putcol("EXPOSURE", np.full(n, interval))
    t.putcol("UVW", uvw_m)
    t.putcol("WEIGHT", np.ones((n, 4), np.float32))
    t.putcol("SIGMA", np.ones((n, 4), np.float32))


def _bandpass(rng, nbl, nchan):
    x = np.linspace(-1, 1, nchan)
    shape = np.empty((nbl, nchan, 4))
    for b in range(nbl):
        for c in range(4):
            p = rng.normal(0, 0.3, 4)
            shape[b, :, c] = (
                1 + p[0] * x + p[1] * x**2 + p[2] * x**3 + 0.2 * np.sin(3 * x + p[3])
            )
    amp = np.where(np.isin(np.arange(4), [0, 3]), 20.0, 2.0)
    return np.abs(shape) * amp


def build_tfcrop(path, rfi, seed=20261113):
    rng = np.random.default_rng(seed)
    xyz = itrf_positions()
    pairs = [(a, b) for a in range(6) for b in range(a + 1, 6)]
    nbl, ntime, nchan = len(pairs), 120, 256
    times = T0 + 3 * 3600.0 + DT * np.repeat(np.arange(ntime), nbl)
    a1 = np.tile([p[0] for p in pairs], ntime)
    a2 = np.tile([p[1] for p in pairs], ntime)
    field = ("SYN", 1.2, -0.5)
    t = _ms(path, len(times), nchan)
    with t:
        _main_rows(t, times, a1, a2, np.ones(len(times)), np.zeros(len(times)),
                   uvw(times, field[1], field[2], xyz, a1, a2))  # fmt: skip
        bp = _bandpass(rng, nbl, nchan)[np.tile(np.arange(nbl), ntime)]
        shape = bp.shape
        noise = (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)) / 10.0
        data = bp * (1 + noise)
        flag = np.zeros(shape, bool)
        inject = np.zeros(shape, bool)
        if rfi:
            tidx = np.repeat(np.arange(ntime), nbl)
            for ch, amp in ((40, 3.0), (41, 1.5), (130, 6.0), (200, 0.8), (201, 0.4)):
                data[:, ch, :] += amp * bp[:, ch, :]
                inject[:, ch, :] = True
            burst = (tidx >= 60) & (tidx < 63)
            data[burst] += 2.0 * bp[burst]
            inject[burst] = True
            spike = (a1 == 1) & (a2 == 4) & (tidx == 90)
            data[spike] *= 10.0
            inject[spike] = True
            flag = rng.random(shape) < 0.02
        t.putcol("DATA", data.astype(np.complex64))
        t.putcol("FLAG", flag)
        t.putcol("FLAG_ROW", np.zeros(len(times), bool))
    _subtables(path, xyz, field, [(1.284e9 - 128 * 208984.375, 208984.375, nchan)],
               "V8b tfcrop" + (" rfi" if rfi else " noise"))  # fmt: skip
    if rfi:
        np.savez_compressed(Path(str(path) + ".inject.npz"), inject=np.packbits(inject))
    return path


EL_TARGET = np.radians(20.0)
DEC_EDGES = np.radians(10.0)


def _field_for_track(xyz, t_mid, el_target=EL_TARGET, dec=DEC_EDGES):
    """RA such that the field rises through `el_target` at `t_mid`."""
    ras = np.linspace(0, 2 * np.pi, 721)[:-1]
    el = elevation(np.full(len(ras), t_mid), ras, np.full(len(ras), dec), xyz[0])
    el2 = elevation(np.full(len(ras), t_mid + 600), ras, np.full(len(ras), dec), xyz[0])
    rising = el2 > el
    k = np.argmin(np.where(rising, np.abs(el - el_target), np.inf))
    lo, hi = ras[k] - np.radians(1), ras[k] + np.radians(1)
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        e = elevation([t_mid], [mid], [dec], xyz[0])[0]
        # Larger RA means the source is further east, so lower while rising.
        if e > el_target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi), dec


def build_edges(path, seed=20261114, uvw_sign=1.0, drop=None):
    """`uvw_sign=-1` writes UVW with the opposite sign (amendment 2: does
    CASA's shadow read the column?); `drop` leaves out every row of that
    antenna (can an antenna without rows shadow?)."""
    rng = np.random.default_rng(seed)
    xyz = itrf_positions()
    pairs = [(a, b) for a in range(6) for b in range(a, 6)  # with autocorrelations
             if drop is None or drop not in (a, b)]  # fmt: skip
    nbl = len(pairs)
    scans = ((1, 20, 0.0), (2, 1, 600.0), (3, 12, 1200.0), (4, 40, 2400.0))
    t_mid = T0 + 3 * 3600.0 + 2400.0 + 20 * DT
    ra, dec = _field_for_track(xyz, t_mid)
    # m001 39 m from m000 towards the field's azimuth at t_mid: its projected
    # separation crosses 13.5 m (the sum of the dish radii) near 20 degrees.
    az = _azimuth(t_mid, ra, dec, xyz[0])
    enu = list(ENU)
    enu[1] = (39.0 * np.sin(az), 39.0 * np.cos(az), 0.0)
    xyz = itrf_positions(enu)
    field = ("EDGES", ra, dec)
    times, scan, ddid, tidx = [], [], [], []
    k = 0
    for number, nint, start in scans:
        for i in range(nint):
            for d in (0, 1):
                times.append(np.full(nbl, T0 + 3 * 3600.0 + start + DT * i))
                scan.append(np.full(nbl, number))
                ddid.append(np.full(nbl, d))
                tidx.append(np.full(nbl, k))
            k += 1
    times, scan = np.concatenate(times), np.concatenate(scan)
    ddid, tidx = np.concatenate(ddid), np.concatenate(tidx)
    n = len(times)
    reps = n // nbl
    a1 = np.tile([p[0] for p in pairs], reps)
    a2 = np.tile([p[1] for p in pairs], reps)
    nchan = 32
    t = _ms(path, n, nchan)
    with t:
        _main_rows(t, times, a1, a2, scan, ddid,
                   uvw_sign * uvw(times, ra, dec, xyz, a1, a2))  # fmt: skip
        shape = (n, nchan, 4)
        data = 10 * (rng.standard_normal(shape) + 1j * rng.standard_normal(shape))
        data = data.astype(np.complex64)
        # Values at the clip limit (50 Jy) and next to it, NaN, Inf, zeros.
        f32 = np.float32
        lim = f32(50.0)
        special = {
            0: lim,
            1: np.nextafter(lim, f32(100)),
            2: np.nextafter(lim, f32(0)),
            3: f32(np.nan),
            4: f32(np.inf),
            5: f32(0.0),
            6: f32(-50.0),
            7: f32(0.6),
        }
        for j, (c, v) in enumerate(special.items()):
            r = 37 + 11 * j
            data[r, c, j % 4] = np.complex64(complex(v, 0.0))
        data[200, 3, 1] = np.complex64(complex(0.0, np.nan))
        data[201, 4, 2] = np.complex64(complex(30.0, 40.0))  # |V| = 50
        flag = rng.random(shape) < 0.01
        flag_row = np.zeros(n, bool)
        flag_row[rng.choice(n, 5, replace=False)] = True
        flag[flag_row] = True
        first3 = (scan == 3) & (tidx <= tidx[scan == 3].min() + 1)
        flag[first3] = True
        flag_row[first3] = True
        t.putcol("DATA", data)
        t.putcol("FLAG", flag)
        t.putcol("FLAG_ROW", flag_row)
    _subtables(path, xyz, field, [(850e6, 1e6, nchan), (1415e6, 0.5e6, nchan)],
               "V8b edges")  # fmt: skip
    el = elevation(times[::nbl], ra, dec, xyz[0])
    return {"ra": ra, "dec": dec, "el_deg": [float(np.degrees(el.min())),
                                             float(np.degrees(el.max()))]}  # fmt: skip


def main(argv):
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    names = argv[1:] or ["syn-noise", "syn-rfi", "syn-edges", "syn-edges-uvwneg",
                         "syn-edges-nom001"]  # fmt: skip
    info = {}
    for name in names:
        path = out / f"{name}.ms"
        if path.exists():
            raise SystemExit(f"{path} exists")
        if name == "syn-noise":
            build_tfcrop(path, rfi=False)
        elif name == "syn-rfi":
            build_tfcrop(path, rfi=True)
        elif name == "syn-edges":
            info[name] = build_edges(path)
        elif name == "syn-edges-uvwneg":
            info[name] = build_edges(path, uvw_sign=-1.0)
        elif name == "syn-edges-nom001":
            info[name] = build_edges(path, drop=1)
        else:
            raise SystemExit(f"unknown case {name}")
    (out / "cases.json").write_text(
        json.dumps(info, indent=1), encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
