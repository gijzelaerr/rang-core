"""Arm A1d's container side (research/e2b-misses.md 9.13); imports no `rang`.

    a1d_casa.py MINI_MS OUT_DIR

1. Synthetic directions (not the fields): a grid of APP directions at three
   of the data's epochs and two antenna positions, converted to HADEC by
   casacore, with LAST, TDB and the position's radius and latitude.
2. For the field rows: TDB per TIME and the radius per antenna.
3. Polar motion x, y (arcsec) from IERSeop2000 at every TDB used, linear in
   MJD between the table's rows.
Output OUT_DIR/a1d-casa.npz.
"""

import sys
from pathlib import Path

import numpy as np


def main(mini, out):
    from casatools import ctsys, measures, quanta, table

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    me, qa, tb = measures(), quanta(), table()
    tb.open(mini)
    time, a1, a2, fld = (tb.getcol(k) for k in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID"))
    tb.close()
    tb.open(mini + "/ANTENNA")
    xyz = tb.getcol("POSITION").T
    tb.close()
    tb.open(str(Path(ctsys.measurespath()) / "geodetic" / "IERSeop2000"))
    eop = {k: tb.getcol(k) for k in ("MJD", "x", "y")}
    tb.close()

    def rad(q):
        return qa.convert(q, "rad")["value"]

    def pm(mjd):
        return (float(np.interp(mjd, eop["MJD"], eop["x"])),
                float(np.interp(mjd, eop["MJD"], eop["y"])))  # fmt: skip

    def frame(t, ant):
        pos = me.position("ITRF", *(qa.quantity(float(v), "m") for v in xyz[ant]))
        me.doframe(pos)
        ep = me.epoch("utc", qa.quantity(float(t), "s"))
        me.doframe(ep)
        tdb = me.measure(ep, "TDB")["m0"]["value"]
        last = (me.measure(ep, "LAST")["m0"]["value"] % 1.0) * 2 * np.pi
        p = me.measure(pos, "ITRF")
        return tdb, last, p["m2"]["value"], rad(p["m1"])

    arr = {}
    # 1. synthetic
    ts = np.unique(time)
    s_t = ts[[0, ts.size // 2, -1]]
    s_ant = np.union1d(a1, a2)[[0, -1]]
    ras = np.linspace(0.1, 2 * np.pi - 0.1, 9)
    decs = np.array([-1.3, -0.8, -0.3, 0.2, 0.7])
    rows = []
    for t in s_t:
        for ant in s_ant:
            tdb, last, radius, lat = frame(t, ant)
            x, y = pm(tdb)
            for ra in ras:
                for dec in decs:
                    d = me.direction("APP", qa.quantity(ra, "rad"), qa.quantity(dec, "rad"))
                    hd = me.measure(d, "HADEC")
                    rows.append([ra, dec, last, lat, radius, tdb, x, y,
                                 rad(hd["m0"]), rad(hd["m1"])])  # fmt: skip
    arr["synthetic"] = np.array(rows)
    # 2. field rows
    for fid in (1, 2):
        sel = fld == fid
        tf = np.unique(time[sel])
        ants = np.union1d(a1[sel], a2[sel])
        tdb = np.zeros(tf.size)
        radius = np.zeros(ants.size)
        lat = np.zeros(ants.size)
        for i, t in enumerate(tf):
            tdb[i] = frame(t, ants[0])[0]
        for j, ant in enumerate(ants):
            _, _, radius[j], lat[j] = frame(tf[0], ant)
        arr[f"f{fid}_times"] = tf
        arr[f"f{fid}_ants"] = ants
        arr[f"f{fid}_tdb"] = tdb
        arr[f"f{fid}_radius"] = radius
        arr[f"f{fid}_lat"] = lat
        arr[f"f{fid}_pm"] = np.array([pm(v) for v in tdb])
    np.savez(out / "a1d-casa.npz", **arr)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
