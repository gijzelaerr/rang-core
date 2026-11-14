"""Arm A1b's rang side and rule (research/e2b-misses.md 9.5).

    python a1b_rang.py MINI_MS OUT_DIR     reads OUT_DIR/casa/, -> OUT_DIR/a1b.json

The probe (DATA = XX 1, others 0) through `cal_pol.rotate(inverse=True)`
with `angle_table_at` angles; one extraction of each antenna's angle from
the corrected correlations (chi_q from XX, XY; chi_p from XX, YX), checked
on rang's probe (C4) before CASA's is read; then candidates (a) as run,
(b) TIME_CENTROID, (c) TIME -/+ INTERVAL/2, (d) UT1 - UTC set to CASA's.
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "python"))

RECEPTOR = -np.pi / 2
TOL = 2e-7


def wrap(x):
    """Angle differences to (-pi/2, pi/2]: chi from atan2 of a product is
    defined modulo pi."""
    return (np.asarray(x) + np.pi / 2) % np.pi - np.pi / 2


def extract(v, sign):
    """(chi_p, chi_q) per row from corrected XX, XY, YX of the probe."""
    xx, xy, yx = v[..., 0].real, v[..., 1].real, v[..., 2].real
    return sign * np.arctan2(yx, xx), sign * np.arctan2(xy, xx)


def pa_casa_frame(times, ra, dec, xyz, dut1=None):
    """`cal_pol.parallactic_angle_casa`, with UT1 - UTC optionally set
    (candidate d); same formula, script-local, rang unchanged."""
    from astropy import units
    from astropy.coordinates import TETE, EarthLocation, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False
    when = Time(np.asarray(times, float) / 86400.0, format="mjd", scale="utc")
    if dut1 is not None:
        when.delta_ut1_utc = dut1
    x, y, z = (float(v) for v in xyz)
    loc = EarthLocation.from_geocentric(x, y, z, unit=units.m)
    app = SkyCoord(ra * units.rad, dec * units.rad, frame="icrs").transform_to(
        TETE(obstime=when, location=loc)
    )
    h = when.sidereal_time("apparent", longitude=loc.lon).rad - app.ra.rad
    phi = np.arctan2(z, np.hypot(x, y))
    d = app.dec.rad
    return np.arctan2(np.sin(h), np.tan(phi) * np.cos(d) - np.sin(d) * np.cos(h))


def main(mini, out):
    from astropy.time import Time
    from rang import cal_pol, core_ms

    mini, out = Path(mini), Path(out)
    with core_ms.open_table(mini) as t:
        c = {k: t.getcol(k) for k in ("TIME", "TIME_CENTROID", "INTERVAL", "ANTENNA1",
                                       "ANTENNA2", "FIELD_ID")}  # fmt: skip
    with core_ms.open_table(mini / "ANTENNA") as t:
        xyz = np.asarray(t.getcol("POSITION"), float)
    with core_ms.open_table(mini / "FIELD") as t:
        phase = np.asarray(t.getcol("PHASE_DIR"), float)
    casa_ut1 = json.loads((out / "casa" / "casa-ut1.json").read_text())
    res = {"tolerance_rad": TOL, "time_equals_centroid": bool(np.array_equal(c["TIME"], c["TIME_CENTROID"])),
           "interval_s": sorted(set(np.round(c["INTERVAL"], 6).tolist())),
           "casa": {k: casa_ut1[k] for k in ("errors", "measurespath", "IERSeop2000")},
           "casa_ut1_minus_utc_s": [min(casa_ut1["ut1_minus_utc_s"]), max(casa_ut1["ut1_minus_utc_s"])]}  # fmt: skip
    tt = Time(np.unique(c["TIME"]) / 86400.0, format="mjd", scale="utc")
    try:
        a = np.asarray(tt.delta_ut1_utc.to_value("s"), float)
        res["astropy_ut1_minus_utc_s"] = [float(a.min()), float(a.max())]
    except Exception as exc:  # noqa: BLE001
        res["astropy_ut1_minus_utc_s"] = repr(exc)
    dut1 = float(np.mean(casa_ut1["ut1_minus_utc_s"]))
    fields, cands = {}, {k: [] for k in ("a", "b", "c-", "c+", "d")}
    sign_used = None
    for fid in (1, 2):
        rows = c["FIELD_ID"] == fid
        a1, a2 = c["ANTENNA1"][rows], c["ANTENNA2"][rows]
        ra, dec = phase[fid].reshape(-1)[:2]
        tm = c["TIME"][rows]

        def angles(times, dut=None, a1=a1, a2=a2, ra=ra, dec=dec):
            pa = {int(x): pa_casa_frame(times, ra, dec, xyz[x], dut) + RECEPTOR
                  for x in np.union1d(a1, a2)}  # fmt: skip
            return np.array([pa[int(x)][i] for i, x in enumerate(a1)]), np.array(
                [pa[int(x)][i] for i, x in enumerate(a2)]
            )

        # rang's own angles as applycal uses them
        tab = cal_pol.angle_table_at(
            mini, np.unique(tm), np.union1d(a1, a2), fid, "casa", RECEPTOR
        )
        ap, aq = cal_pol.table_angles(tab, tm, a1, a2)
        probe = np.zeros((rows.sum(), 1, 4), np.complex64)
        probe[..., 0] = 1
        rv = cal_pol.rotate(probe, ap, aq, inverse=True)[:, 0]
        # C4: choose the extraction sign on rang's probe only
        c4 = {}
        for s in (1, -1):
            ep, eq = extract(rv.astype(np.complex128), s)
            c4[s] = float(max(np.abs(wrap(ep - ap)).max(), np.abs(wrap(eq - aq)).max()))
        s = min(c4, key=c4.get)
        if sign_used is None:
            sign_used = s
        # script-local formula must equal rang's (a) exactly enough
        fa_p, fa_q = angles(tm)
        z = np.load(out / "casa" / f"probe_{fid}.npz")
        cv = z["CORRECTED_DATA"][rows][:, 0].astype(np.complex128)
        cp, cq = extract(cv, sign_used)
        chi_casa = np.concatenate([cp, cq])
        dt = 1.0
        pp, pq = angles(tm + dt)
        rate = np.concatenate([wrap(pp - fa_p), wrap(pq - fa_q)]) / dt
        cand = {"a": (ap, aq), "b": angles(c["TIME_CENTROID"][rows]),
                "c-": angles(tm - c["INTERVAL"][rows] / 2), "c+": angles(tm + c["INTERVAL"][rows] / 2),
                "d": angles(tm, dut1)}  # fmt: skip
        f = {"c4_max_rad": c4, "c4_met": bool(c4[s] <= 1e-9), "script_formula_vs_rang_max_rad":
             float(max(np.abs(wrap(fa_p - ap)).max(), np.abs(wrap(fa_q - aq)).max()))}  # fmt: skip
        for k, (p, q) in cand.items():
            d = wrap(chi_casa - np.concatenate([p, q]))
            cands[k].append(d)
            f[k] = {
                "max_abs_rad": float(np.abs(d).max()),
                "median_rad": float(np.median(d)),
            }
        d0 = wrap(chi_casa - np.concatenate([ap, aq]))
        f["time_offset_s"] = {"median": float(np.median(d0 / rate)), "min": float((d0 / rate).min()),
                              "max": float((d0 / rate).max())}  # fmt: skip
        fields[str(fid)] = f
    res["fields"] = fields
    res["extraction_sign"] = sign_used
    res["candidates_max_abs_rad"] = {
        k: float(np.abs(np.concatenate(v)).max()) for k, v in cands.items()
    }
    c4ok = all(f["c4_met"] for f in fields.values())
    m = res["candidates_max_abs_rad"]
    if not c4ok:
        outcome = "void: C4 not met"
    elif m["a"] <= TOL:
        outcome = (
            "(a) already within tolerance: 9.3's P reading not confirmed by this probe"
        )
    elif m["b"] <= TOL:
        outcome = "H1: TIME_CENTROID"
    elif m["c-"] <= TOL or m["c+"] <= TOL:
        outcome = "H1: integration " + ("start" if m["c-"] <= TOL else "end")
    elif m["d"] <= TOL:
        outcome = "H2: UT1 - UTC (IERS data) differs"
    else:
        outcome = "cause not found under this rule (H3 open)"
    res["outcome"] = outcome
    (out / "a1b.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("candidates_max_abs_rad", "outcome", "casa_ut1_minus_utc_s",
                      "astropy_ut1_minus_utc_s", "time_equals_centroid")}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
