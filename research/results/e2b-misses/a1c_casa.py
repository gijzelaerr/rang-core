"""Arm A1c's container side (research/e2b-misses.md 9.7); imports no `rang`.

    a1c_casa.py MINI_MS OUT_DIR

Per field (1, 2), distinct TIME and antenna of the field's rows, frame =
UTC epoch at TIME and the antenna's ITRF position, all float64:
  K       casacore's parallactic angle as MSDerivedValues::parAngle: the
          position angle, in AZEL, of the HADEC pole seen from the source
  K_geo   the same in AZELGEO
  hadec   the source in HADEC (h, dec)
  app, topo, jtrue   the source's (RA, Dec) in APP, TOPO, JTRUE
  last    local apparent sidereal time (rad)
  lat_itrf, lat_wgs84   the antenna's latitude in casacore (rad)
Also the posangle convention check (a point straight above in AZEL has
position angle 0 from below). Output OUT_DIR/a1c-casa.npz and .json.
"""

import json
import sys
from pathlib import Path

import numpy as np


def main(mini, out):
    from casatools import measures, quanta, table

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    me, qa, tb = measures(), quanta(), table()
    tb.open(mini)
    time, a1, a2, fld = (tb.getcol(k) for k in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID"))
    tb.close()
    tb.open(mini + "/ANTENNA")
    xyz = tb.getcol("POSITION").T
    tb.close()
    tb.open(mini + "/FIELD")
    pdir = tb.getcol("PHASE_DIR")  # (2, 1, nfield)
    tb.close()

    def rad(q):
        return qa.convert(q, "rad")["value"]

    # posangle order check, independent of the data
    me.doframe(me.epoch("utc", qa.quantity(time[0], "s")))
    lo = me.direction("AZEL", "10deg", "40deg")
    hi = me.direction("AZEL", "10deg", "41deg")
    check = {"posangle(lo, hi)": rad(me.posangle(lo, hi)), "posangle(hi, lo)": rad(me.posangle(hi, lo))}
    res = {"posangle_check_rad": check}
    arrays = {}
    for fid in (1, 2):
        rows = fld == fid
        ts = np.unique(time[rows])
        ants = np.union1d(a1[rows], a2[rows])
        ra, dec = pdir[0, 0, fid], pdir[1, 0, fid]
        src = me.direction("J2000", qa.quantity(ra, "rad"), qa.quantity(dec, "rad"))
        pole = me.direction("HADEC", "0rad", qa.quantity(np.pi / 2, "rad"))
        keys = ("K", "K_rev", "K_geo", "h", "hdec", "app_ra", "app_dec", "topo_ra", "topo_dec",
                "jtrue_ra", "jtrue_dec", "last")
        f = {k: np.zeros((ts.size, ants.size)) for k in keys}
        lat_itrf, lat_wgs = [], []
        for j, ant in enumerate(ants):
            pos = me.position("ITRF", *(qa.quantity(float(v), "m") for v in xyz[ant]))
            me.doframe(pos)
            lat_itrf.append(rad(me.measure(pos, "ITRF")["m1"]))
            lat_wgs.append(rad(me.measure(pos, "WGS84")["m1"]))
            for i, t in enumerate(ts):
                ep = me.epoch("utc", qa.quantity(float(t), "s"))
                me.doframe(ep)
                s_az = me.measure(src, "AZEL")
                p_az = me.measure(pole, "AZEL")
                f["K"][i, j] = rad(me.posangle(s_az, p_az))
                f["K_rev"][i, j] = rad(me.posangle(p_az, s_az))
                f["K_geo"][i, j] = rad(me.posangle(me.measure(src, "AZELGEO"), me.measure(pole, "AZELGEO")))
                hd = me.measure(src, "HADEC")
                f["h"][i, j], f["hdec"][i, j] = rad(hd["m0"]), rad(hd["m1"])
                for name in ("APP", "TOPO", "JTRUE"):
                    d = me.measure(src, name)
                    f[name.lower() + "_ra"][i, j] = rad(d["m0"])
                    f[name.lower() + "_dec"][i, j] = rad(d["m1"])
                last = me.measure(ep, "LAST")["m0"]["value"]  # days
                f["last"][i, j] = (last % 1.0) * 2 * np.pi
        for k, v in f.items():
            arrays[f"f{fid}_{k}"] = v
        arrays[f"f{fid}_times"] = ts
        arrays[f"f{fid}_ants"] = ants
        arrays[f"f{fid}_lat_itrf"] = np.array(lat_itrf)
        arrays[f"f{fid}_lat_wgs84"] = np.array(lat_wgs)
    np.savez(out / "a1c-casa.npz", **arrays)
    res["fields"] = {str(fid): {"ntimes": int(arrays[f"f{fid}_times"].size),
                                "nants": int(arrays[f"f{fid}_ants"].size)} for fid in (1, 2)}  # fmt: skip
    (out / "a1c-casa.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
