"""Arm A1d's rang side and rule (research/e2b-misses.md 9.13).

    python a1d_rang.py MINI_MS A1C_CASA_DIR A1D_CASA_DIR OUT_JSON

E emulates casacore's TOPO -> HADEC (MeasMath::applyTOPOtoHADEC): add
g2 * u(LAST, LAT) to the unit vector and renormalise, then the polar motion
rotation Euler(-x", 2; -y", 1; LAST, 3) as `in *= RotMatrix(...)`, then the
sign of the second coordinate flipped. The matrix conventions are chosen on
the synthetic directions (C7) before the field rows are read.
"""

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "python"))
sys.path.insert(0, str(HERE))
from a1c_rang import formula, wrap  # noqa: E402

TOL = 2e-7
C7_TOL = 1e-9
C8_TOL = 1e-8
ARCSEC = np.pi / 180 / 3600
C_LIGHT = 299792458.0
MJD2000 = 51544.5


def ut_to_st(tdb_mjd):
    """MeasTable::UTtoST: the UT -> sidereal rate."""
    t = (tdb_mjd - MJD2000) / 36525.0
    return 1.002737909350795 + (5.9006e-11 - 5.9e-15 * t) * t


def unit(lon, lat):
    return np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], -1)


def rot(axis, angle, sign):
    """casacore-style elementary rotation; `sign` picks the convention."""
    c, s = np.cos(angle), sign * np.sin(angle)
    m = np.zeros(np.shape(angle) + (3, 3))
    i, j = [(1, 2), (2, 0), (0, 1)][axis - 1]
    m[..., axis - 1, axis - 1] = 1
    m[..., i, i], m[..., j, j] = c, c
    m[..., i, j], m[..., j, i] = s, -s
    return m


def emulate(ra, dec, last, lat, radius, tdb, x, y, conv, shift=True, polar=True):
    """(h, dec) in casacore's HADEC from an APP (ra, dec)."""
    sign, order, transpose = conv
    v = unit(ra, dec)
    if shift:
        g2 = 2 * np.pi * radius / 86400.0 * ut_to_st(tdb) / C_LIGHT
        v = v + (g2 * np.ones_like(ra))[..., None] * unit(last * np.ones_like(ra), lat * np.ones_like(ra))
        v = v / np.linalg.norm(v, axis=-1, keepdims=True)
    xa = (x if polar else 0 * x) * -ARCSEC * np.ones_like(ra)
    ya = (y if polar else 0 * y) * -ARCSEC * np.ones_like(ra)
    la = last * np.ones_like(ra)
    r1, r2, r3 = rot(2, xa, sign), rot(1, ya, sign), rot(3, la, sign)
    m = r3 @ r2 @ r1 if order == 0 else r1 @ r2 @ r3
    if transpose:
        m = np.swapaxes(m, -1, -2)
    w = np.einsum("...ij,...j->...i", m, v)
    w[..., 1] = -w[..., 1]
    return np.arctan2(w[..., 1], w[..., 0]), np.arcsin(np.clip(w[..., 2], -1, 1))


def main(mini, a1c_dir, a1d_dir, out_json):
    from a1c_rang import astropy_parts
    from astropy import units
    from astropy.coordinates import TETE, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    from rang import cal_pol, core_ms

    iers.conf.auto_download = False
    k = np.load(Path(a1c_dir) / "a1c-casa.npz")
    d = np.load(Path(a1d_dir) / "a1d-casa.npz")
    res = {"tolerance_rad": TOL}
    # C7 on synthetic directions: choose the convention
    s = d["synthetic"]
    ra, dec, last, lat, radius, tdb, x, y, h0, d0 = s.T
    c7 = {}
    for conv in itertools.product((1, -1), (0, 1), (False, True)):
        h, dd = emulate(ra, dec, last, lat, radius, tdb, x, y, conv)
        c7[str(conv)] = float(max(np.abs(wrap(h - h0)).max(), np.abs(dd - d0).max()))
    best = min(c7, key=c7.get)
    conv = eval(best)  # noqa: S307 (our own tuple repr)
    res["c7_by_convention_rad"] = c7
    res["c7_convention"] = best
    res["c7_max_rad"] = c7[best]
    for flag in ("shift", "polar"):
        h, dd = emulate(ra, dec, last, lat, radius, tdb, x, y, conv, **{flag: False})
        res[f"c7_without_{flag}_rad"] = float(max(np.abs(wrap(h - h0)).max(), np.abs(dd - d0).max()))
    if c7[best] > C7_TOL:
        res["outcome"] = "void: C7 not met"
        Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
        print(json.dumps(res, indent=1))
        return 0
    # field rows
    mini = Path(mini)
    with core_ms.open_table(mini) as t:
        c = {kk: t.getcol(kk) for kk in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID")}
    with core_ms.open_table(mini / "ANTENNA") as t:
        xyz = np.asarray(t.getcol("POSITION"), float)
    with core_ms.open_table(mini / "FIELD") as t:
        phase = np.asarray(t.getcol("PHASE_DIR"), float)
    names = ("C8", "H4", "H4-L", "H4-noPM", "H4-noD", "rang")
    allmax = {n: 0.0 for n in names}
    fields = {}
    for fid in (1, 2):
        rows = c["FIELD_ID"] == fid
        a1, a2, tm = c["ANTENNA1"][rows], c["ANTENNA2"][rows], c["TIME"][rows]
        fra, fdec = phase[fid].reshape(-1)[:2]
        ts, ants = d[f"f{fid}_times"], d[f"f{fid}_ants"]
        assert np.array_equal(ts, k[f"f{fid}_times"]) and np.array_equal(ants, k[f"f{fid}_ants"])
        tdb_t, pm = d[f"f{fid}_tdb"], d[f"f{fid}_pm"]
        when = Time(ts / 86400.0, format="mjd", scale="utc")
        geo = SkyCoord(fra * units.rad, fdec * units.rad, frame="icrs").transform_to(
            TETE(obstime=when)
        )
        g_ra, g_dec = geo.ra.rad, geo.dec.rad
        q = {n: np.zeros((ts.size, ants.size)) for n in names}
        for j, ant in enumerate(ants):
            p = astropy_parts(ts, fra, fdec, xyz[ant])
            phi = p["phi"]
            lat_j, rad_j = d[f"f{fid}_lat"][j], d[f"f{fid}_radius"][j]
            kl = k[f"f{fid}_last"][:, j]
            args = (lat_j, rad_j, tdb_t, pm[:, 0], pm[:, 1], conv)
            h, dd = emulate(k[f"f{fid}_app_ra"][:, j], k[f"f{fid}_app_dec"][:, j], kl, *args)
            q["C8"][:, j] = formula(h, dd, phi)
            h, dd = emulate(g_ra, g_dec, p["last"], *args)
            q["H4"][:, j] = formula(h, dd, phi)
            h, dd = emulate(g_ra, g_dec, kl, *args)
            q["H4-L"][:, j] = formula(h, dd, phi)
            h, dd = emulate(g_ra, g_dec, p["last"], *args, polar=False)
            q["H4-noPM"][:, j] = formula(h, dd, phi)
            h, dd = emulate(g_ra, g_dec, p["last"], *args, shift=False)
            q["H4-noD"][:, j] = formula(h, dd, phi)
            q["rang"][:, j] = cal_pol.parallactic_angle_casa(ts, fra, fdec, xyz[ant])
        ti = np.searchsorted(ts, tm)
        ja, jb = np.searchsorted(ants, a1), np.searchsorted(ants, a2)

        def rows_of(m, ti=ti, ja=ja, jb=jb):
            return np.concatenate([m[ti, ja], m[ti, jb]])

        K = rows_of(k[f"f{fid}_K"])
        f = {}
        for n in names:
            dlt = wrap(rows_of(q[n]) - K)
            f[n] = {"max_abs_rad": float(np.abs(dlt).max()), "median_rad": float(np.median(dlt))}
            allmax[n] = max(allmax[n], f[n]["max_abs_rad"])
        fields[str(fid)] = f
        np.save(Path(a1d_dir) / f"q_h4_f{fid}.npy", q["H4"])
    res["fields"] = fields
    res["max_over_fields_rad"] = allmax
    if allmax["C8"] > C8_TOL:
        outcome = "void: C8 not met"
    elif allmax["H4"] <= TOL:
        outcome = "H4 met: casacore's TOPO -> HADEC step is the cause"
    elif allmax["H4-L"] <= TOL:
        outcome = "H4-L met: H4 plus the sidereal time difference"
    else:
        outcome = "H4 not shown"
    res["outcome"] = outcome
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({"outcome": outcome, "max": allmax, "c7": res["c7_max_rad"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
