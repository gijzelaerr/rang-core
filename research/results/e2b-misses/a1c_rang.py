"""Arm A1c's rang side and rule (research/e2b-misses.md 9.7).

    python a1c_rang.py MINI_MS A1B_CASA_DIR A1C_CASA_DIR OUT_JSON

Reads casacore's values (a1c_casa.py) and A1b's CASA applycal probe; checks
C4, C5, K1; then Delta = q_rang - K and the candidates (e), (f), (g), (g'),
(g1), (g2), (k) in the frozen order.
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "python"))

RECEPTOR = -np.pi / 2
TOL = 2e-7
C4_TOL = 1e-7
C5_TOL = 1e-12
ASEC = 180 / np.pi * 3600


def wrap(x, period=2 * np.pi):
    return (np.asarray(x) + period / 2) % period - period / 2


def formula(h, d, phi):
    return np.arctan2(np.sin(h), np.tan(phi) * np.cos(d) - np.sin(d) * np.cos(h))


def extract(v):
    """(chi_p, chi_q) from corrected XX, XY, YX of the probe (A1b's form,
    sign +1 as A1b chose on rang's probe)."""
    xx, xy, yx = v[..., 0].real, v[..., 1].real, v[..., 2].real
    return np.arctan2(yx, xx), np.arctan2(xy, xx)


def astropy_parts(times, ra, dec, xyz):
    """What parallactic_angle_casa uses: TETE place, apparent LAST, the
    geocentric latitude; plus erfa's ICRS -> true-of-date place (pnm06a)."""
    import erfa
    from astropy import units
    from astropy.coordinates import TETE, EarthLocation, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False
    when = Time(np.asarray(times, float) / 86400.0, format="mjd", scale="utc")
    x, y, z = (float(v) for v in xyz)
    loc = EarthLocation.from_geocentric(x, y, z, unit=units.m)
    app = SkyCoord(ra * units.rad, dec * units.rad, frame="icrs").transform_to(
        TETE(obstime=when, location=loc)
    )
    last = when.sidereal_time("apparent", longitude=loc.lon).rad
    tt = when.tt
    m = erfa.pnm06a(tt.jd1, tt.jd2)
    v = np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])
    w = m @ v
    tra, tdec = np.arctan2(w[:, 1], w[:, 0]), np.arcsin(w[:, 2])
    return {
        "ra": app.ra.rad, "dec": app.dec.rad, "last": last,
        "phi": float(np.arctan2(z, np.hypot(x, y))), "phi_geodetic": float(loc.lat.rad),
        "true_ra": tra, "true_dec": tdec,
    }  # fmt: skip


def main(mini, a1b_dir, a1c_dir, out_json):
    from rang import cal_pol, core_ms

    mini = Path(mini)
    with core_ms.open_table(mini) as t:
        c = {k: t.getcol(k) for k in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID")}
    with core_ms.open_table(mini / "ANTENNA") as t:
        xyz = np.asarray(t.getcol("POSITION"), float)
    with core_ms.open_table(mini / "FIELD") as t:
        phase = np.asarray(t.getcol("PHASE_DIR"), float)
    k = np.load(Path(a1c_dir) / "a1c-casa.npz")
    kmeta = json.loads((Path(a1c_dir) / "a1c-casa.json").read_text())
    res = {"tolerance_rad": TOL, "c4_tol_rad": C4_TOL,
           "posangle_check_rad": kmeta["posangle_check_rad"]}  # fmt: skip
    cand_names = ("e", "f", "g", "g'", "g1", "g2", "k")
    allmax = {n: 0.0 for n in ("delta", "K1", "K_geo-K", *cand_names)}
    fields = {}
    for fid in (1, 2):
        rows = c["FIELD_ID"] == fid
        a1, a2, tm = c["ANTENNA1"][rows], c["ANTENNA2"][rows], c["TIME"][rows]
        ra, dec = phase[fid].reshape(-1)[:2]
        ts, ants = k[f"f{fid}_times"], k[f"f{fid}_ants"]
        assert np.array_equal(ts, np.unique(tm)) and np.array_equal(ants, np.union1d(a1, a2))

        def g(n, fid=fid):
            return k[f"f{fid}_{n}"]  # [ntime, nant] or [nant]

        q = np.zeros((ts.size, ants.size))
        cand = {n: np.zeros_like(q) for n in cand_names}
        c5 = 0.0
        arcsec = {}

        def keep(key, val):
            arcsec[key] = max(arcsec.get(key, 0.0), float(np.max(np.abs(val)) * ASEC))

        for j, ant in enumerate(ants):
            q[:, j] = cal_pol.parallactic_angle_casa(ts, ra, dec, xyz[ant])
            p = astropy_parts(ts, ra, dec, xyz[ant])
            own = formula(p["last"] - p["ra"], p["dec"], p["phi"])
            c5 = max(c5, float(np.abs(wrap(own - q[:, j])).max()))
            phi = p["phi"]
            cand["e"][:, j] = formula(g("h")[:, j], g("hdec")[:, j], phi)
            cand["f"][:, j] = formula(g("last")[:, j] - p["ra"], p["dec"], phi)
            cand["g"][:, j] = formula(p["last"] - g("app_ra")[:, j], g("app_dec")[:, j], phi)
            cand["g'"][:, j] = formula(p["last"] - g("topo_ra")[:, j], g("topo_dec")[:, j], phi)
            ab_ra, ab_dec = wrap(p["ra"] - p["true_ra"]), p["dec"] - p["true_dec"]
            cand["g1"][:, j] = formula(
                p["last"] - (g("jtrue_ra")[:, j] + ab_ra), g("jtrue_dec")[:, j] + ab_dec, phi
            )
            cab_ra = wrap(g("topo_ra")[:, j] - g("jtrue_ra")[:, j])
            cab_dec = g("topo_dec")[:, j] - g("jtrue_dec")[:, j]
            cand["g2"][:, j] = formula(
                p["last"] - (p["true_ra"] + cab_ra), p["true_dec"] + cab_dec, phi
            )
            cand["k"][:, j] = formula(g("h")[:, j], g("hdec")[:, j], p["phi_geodetic"])
            cd = np.cos(dec)
            keep("jtrue_vs_erfa_true_ra_cosdec", wrap(g("jtrue_ra")[:, j] - p["true_ra"]) * cd)
            keep("jtrue_vs_erfa_true_dec", g("jtrue_dec")[:, j] - p["true_dec"])
            keep("app_vs_tete_ra_cosdec", wrap(g("app_ra")[:, j] - p["ra"]) * cd)
            keep("app_vs_tete_dec", g("app_dec")[:, j] - p["dec"])
            keep("topo_vs_tete_ra_cosdec", wrap(g("topo_ra")[:, j] - p["ra"]) * cd)
            keep("topo_vs_tete_dec", g("topo_dec")[:, j] - p["dec"])
            keep("last_casa_minus_astropy", wrap(g("last")[:, j] - p["last"]))
            keep("hadec_h_casa_minus_astropy", wrap(g("h")[:, j] - (p["last"] - p["ra"])))
            keep("hadec_dec_casa_minus_astropy", g("hdec")[:, j] - p["dec"])
            keep("lat_itrf_minus_rang_phi", float(g("lat_itrf")[j]) - phi)
            keep("lat_wgs84_minus_astropy_geodetic", float(g("lat_wgs84")[j]) - p["phi_geodetic"])
        K = g("K")
        # row-wise (82 values per field): p = ANTENNA1, q = ANTENNA2
        ti = np.searchsorted(ts, tm)
        ja, jb = np.searchsorted(ants, a1), np.searchsorted(ants, a2)

        def rows_of(m, ti=ti, ja=ja, jb=jb):
            return np.concatenate([m[ti, ja], m[ti, jb]])

        qr, Kr = rows_of(q), rows_of(K)
        # C4 on rang's probe (rang's own applycal angles)
        tab = cal_pol.angle_table_at(mini, ts, ants, fid, "casa", RECEPTOR)
        ap, aq = cal_pol.table_angles(tab, tm, a1, a2)
        probe = np.zeros((rows.sum(), 1, 4), np.complex64)
        probe[..., 0] = 1
        rv = cal_pol.rotate(probe, ap, aq, inverse=True)[:, 0]
        ep, eq = extract(rv.astype(np.complex128))
        c4 = float(max(np.abs(wrap(ep - ap, np.pi)).max(), np.abs(wrap(eq - aq, np.pi)).max()))
        rang_vs_table = float(np.abs(wrap(np.concatenate([ap, aq]) - (qr + RECEPTOR))).max())
        z = np.load(Path(a1b_dir) / f"probe_{fid}.npz")
        cp, cq = extract(z["CORRECTED_DATA"][rows][:, 0].astype(np.complex128))
        chi_casa = np.concatenate([cp, cq])
        k1 = wrap(chi_casa - (Kr + RECEPTOR), np.pi)
        delta = wrap(qr - Kr)
        f = {
            "c4_max_rad": c4, "c5_max_rad": c5, "rang_rows_vs_table_max_rad": rang_vs_table,
            "K1_max_rad": float(np.abs(k1).max()), "K1_median_rad": float(np.median(k1)),
            "delta_max_rad": float(np.abs(delta).max()),
            "delta_median_rad": float(np.median(delta)),
            "casa_minus_rang_median_rad": float(
                np.median(wrap(chi_casa - (qr + RECEPTOR), np.pi))),
            "K_geo_minus_K_max_rad": float(np.abs(wrap(g("K_geo") - K)).max()),
            "K_rev_plus_K_max_rad": float(np.abs(wrap(g("K_rev") + K)).max()),
            "place_and_time_arcsec_max": arcsec,
        }  # fmt: skip
        allmax["delta"] = max(allmax["delta"], f["delta_max_rad"])
        allmax["K1"] = max(allmax["K1"], f["K1_max_rad"])
        allmax["K_geo-K"] = max(allmax["K_geo-K"], f["K_geo_minus_K_max_rad"])
        f["candidates"] = {}
        for n in cand_names:
            d = wrap(rows_of(cand[n]) - Kr)
            f["candidates"][n] = {
                "max_abs_rad": float(np.abs(d).max()),
                "median_rad": float(np.median(d)),
            }
            allmax[n] = max(allmax[n], f["candidates"][n]["max_abs_rad"])
        fields[str(fid)] = f
    res["fields"] = fields
    res["max_over_fields_rad"] = allmax
    met = {n: allmax[n] <= TOL for n in cand_names}
    c4ok = all(f["c4_max_rad"] <= C4_TOL for f in fields.values())
    c5ok = all(f["c5_max_rad"] <= C5_TOL for f in fields.values())
    if not (c4ok and c5ok):
        outcome = "void: C4 or C5 not met"
    elif allmax["K1"] > TOL:
        outcome = "cause not found: K1 not met (casacore's measures path is not applycal's)"
    elif allmax["delta"] <= TOL:
        outcome = "rang equals casacore within tolerance; A1b's reading not confirmed"
    elif met["e"]:
        if met["f"]:
            outcome = "H3a: sidereal time"
        elif met["g"] or met["g'"]:
            sub = (
                "precession and nutation" if met["g1"] else "aberration" if met["g2"] else "not split"
            )
            outcome = f"H3b: apparent place ({'g' if met['g'] else 'g-prime'}); within it: {sub}"
        else:
            outcome = "H3: h, dec, combination (not split)"
    elif met["k"]:
        outcome = "H3c: latitude convention"
    else:
        outcome = "cause not found under this rule (H3c pole or formula open)"
    res["met"] = met
    res["outcome"] = outcome
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({"outcome": outcome, "max": allmax}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
