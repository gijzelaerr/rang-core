"""Arm A1c, post hoc reading (research/e2b-misses.md 9.8), written after the
frozen rule's outcome was read; decides nothing.

    python a1c_posthoc.py MINI_MS A1B_CASA_DIR A1C_CASA_DIR OUT_JSON

(e) met exactly: casacore's K is the hour-angle formula on casacore's HADEC
(h, dec) with rang's geocentric latitude. So the difference is in h, dec.
This compares casacore's HADEC with astropy's HADec frame (observed place:
polar motion and diurnal aberration included, refraction off) and with
astropy's TETE place, and reports polar motion and the PA from each place
against K and against CASA's applycal probe.
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "python"))
sys.path.insert(0, str(HERE))
from a1c_rang import RECEPTOR, extract, formula, wrap  # noqa: E402

ASEC = 180 / np.pi * 3600


def main(mini, a1b_dir, a1c_dir, out_json):
    from astropy import units
    from astropy.coordinates import TETE, EarthLocation, HADec, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    from rang import cal_pol, core_ms

    iers.conf.auto_download = False
    mini = Path(mini)
    with core_ms.open_table(mini) as t:
        c = {k: t.getcol(k) for k in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID")}
    with core_ms.open_table(mini / "ANTENNA") as t:
        xyz = np.asarray(t.getcol("POSITION"), float)
    with core_ms.open_table(mini / "FIELD") as t:
        phase = np.asarray(t.getcol("PHASE_DIR"), float)
    k = np.load(Path(a1c_dir) / "a1c-casa.npz")
    res = {}
    t0 = Time(np.unique(c["TIME"])[0] / 86400.0, format="mjd", scale="utc")
    try:
        xp, yp = iers.earth_orientation_table.get().pm_xy(t0)
        res["polar_motion_arcsec"] = [float(xp.to_value("arcsec")), float(yp.to_value("arcsec"))]
    except Exception as exc:  # noqa: BLE001
        res["polar_motion_arcsec"] = repr(exc)
    for fid in (1, 2):
        rows = c["FIELD_ID"] == fid
        a1, a2, tm = c["ANTENNA1"][rows], c["ANTENNA2"][rows], c["TIME"][rows]
        ra, dec = phase[fid].reshape(-1)[:2]
        ts, ants = k[f"f{fid}_times"], k[f"f{fid}_ants"]
        when = Time(ts / 86400.0, format="mjd", scale="utc")
        src = SkyCoord(ra * units.rad, dec * units.rad, frame="icrs")
        pa_obs = np.zeros((ts.size, ants.size))
        dh, dd, dh_tete, dd_tete = [], [], [], []
        for j, ant in enumerate(ants):
            x, y, z = xyz[ant]
            loc = EarthLocation.from_geocentric(x, y, z, unit=units.m)
            phi = np.arctan2(z, np.hypot(x, y))
            hd = src.transform_to(HADec(obstime=when, location=loc, pressure=0 * units.hPa))
            h, d = hd.ha.rad, hd.dec.rad
            pa_obs[:, j] = formula(h, d, phi)
            te = src.transform_to(TETE(obstime=when, location=loc))
            h_te = when.sidereal_time("apparent", longitude=loc.lon).rad - te.ra.rad
            kh, kd = k[f"f{fid}_h"][:, j], k[f"f{fid}_hdec"][:, j]
            dh.append(wrap(h - kh) * np.cos(kd))
            dd.append(d - kd)
            dh_tete.append(wrap(h_te - kh) * np.cos(kd))
            dd_tete.append(te.dec.rad - kd)
        ti = np.searchsorted(ts, tm)
        ja, jb = np.searchsorted(ants, a1), np.searchsorted(ants, a2)

        def rows_of(m, ti=ti, ja=ja, jb=jb):
            return np.concatenate([m[ti, ja], m[ti, jb]])

        K = rows_of(k[f"f{fid}_K"])
        z = np.load(Path(a1b_dir) / f"probe_{fid}.npz")
        cp, cq = extract(z["CORRECTED_DATA"][rows][:, 0].astype(np.complex128))
        chi = np.concatenate([cp, cq]) - RECEPTOR
        q_rang = np.concatenate(
            [cal_pol.parallactic_angle_casa(tm[i : i + 1], ra, dec, xyz[a])
             for a_s in (a1, a2) for i, a in enumerate(a_s)]
        )  # fmt: skip
        obs = rows_of(pa_obs)
        res[str(fid)] = {
            "astropy_HADec_minus_casacore_HADEC_arcsec": {
                "h_cosdec_max": float(np.abs(np.concatenate(dh)).max() * ASEC),
                "dec_max": float(np.abs(np.concatenate(dd)).max() * ASEC),
            },
            "astropy_TETE_minus_casacore_HADEC_arcsec": {
                "h_cosdec_max": float(np.abs(np.concatenate(dh_tete)).max() * ASEC),
                "dec_max": float(np.abs(np.concatenate(dd_tete)).max() * ASEC),
            },
            "pa_from_astropy_HADec_minus_K_max_rad": float(np.abs(wrap(obs - K)).max()),
            "pa_from_astropy_HADec_minus_casa_probe_max_rad": float(
                np.abs(wrap(chi - obs, np.pi)).max()),
            "rang_minus_casa_probe_max_rad": float(np.abs(wrap(chi - q_rang, np.pi)).max()),
            "K_minus_casa_probe_max_rad": float(np.abs(wrap(chi - K, np.pi)).max()),
        }  # fmt: skip
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
