# SPDX-License-Identifier: GPL-3.0-or-later
"""CASA `listobs` as the oracle of task V8a (research/v8a-listobs.md).

Runs inside `rang-o-casa:6.7.6.14` with `/opt/casa/bin/python -I`. For each
`NAME=MS` argument it calls `casatasks.listobs(vis=MS, listfile=OUT/NAME.txt,
verbose=True)` and writes the returned record to `OUT/NAME.json`, NumPy values
turned into lists. The MSs are mounted read-only; nothing is written to them.

Usage: listobs.py OUT NAME=MS [NAME=MS ...]
"""

import json
import sys
import time
from pathlib import Path


def plain(value):
    """The returned record as JSON: NumPy arrays and scalars to lists and
    Python numbers."""
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def corrtypes(md, spw):
    ddids = md.datadescids(spw=spw)
    if len(ddids) == 0:
        return []
    return md.corrtypesforpol(md.polidfordatadesc(int(ddids[0])))


def msmd_record(ms):
    """The supplementary oracle: what listobs prints for spectral windows and
    antennas, at full precision, from CASA's own `msmetadata` tool (listobs's
    returned record carries neither)."""
    from casatools import measures, msmetadata

    me = measures()
    md = msmetadata()
    md.open(ms)
    try:
        nspw, nant = md.nspw(), md.nantennas()
        spws = []
        for s in range(nspw):
            spws.append(
                {
                    "name": md.namesforspws(s)[0],
                    "nchan": md.nchan(s),
                    "chanfreqs": md.chanfreqs(s),
                    "chanwidths": md.chanwidths(s),
                    "bandwidth": md.bandwidths(s),
                    "meanfreq": md.meanfreq(s),
                    "reffreq": md.reffreq(s),
                    "corrtypes": corrtypes(md, s),
                }
            )
        ants = []
        for a in range(nant):
            itrf = md.antennaposition(a)
            pos = me.measure(itrf, "WGS84")
            off = md.antennaoffset(a)
            ants.append(
                {
                    "name": md.antennanames(a)[0],
                    "station": md.antennastations(a)[0],
                    "diameter_m": md.antennadiameter(a)["value"],
                    "longitude_rad": pos["m0"]["value"],
                    "latitude_rad": pos["m1"]["value"],
                    "height_m": pos["m2"]["value"],
                    "refer": pos["refer"],
                    "itrf_angles": [
                        itrf["m0"]["value"],
                        itrf["m1"]["value"],
                        itrf["m2"]["value"],
                    ],
                    "itrf_refer": itrf["refer"],
                    "offset_m": [
                        off["longitude offset"]["value"],
                        off["latitude offset"]["value"],
                        off["elevation offset"]["value"],
                    ],
                }
            )
        observatory = md.observatorynames()[0]
        try:
            obs = md.observatoryposition(0)
            obs = {k: obs[k]["value"] for k in ("m0", "m1", "m2")} | {
                "refer": obs["refer"]
            }
        except Exception as exc:  # noqa: BLE001 (recorded, never fatal)
            obs = f"failed: {type(exc).__name__}: {exc}"
        return {
            "spws": spws,
            "antennas": ants,
            "observatory": observatory,
            "observatory_position": obs,
            "fieldnames": md.fieldnames(),
            "scannumbers": md.scannumbers(),
        }
    except Exception as exc:  # noqa: BLE001 (recorded, never fatal)
        return {"failed": f"{type(exc).__name__}: {exc}"}
    finally:
        md.done()
        me.done()


def main(argv):
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    import casatasks
    from casatasks import listobs

    try:
        version = casatasks.version_string()
    except Exception as exc:  # noqa: BLE001 (recorded, never fatal)
        version = f"unknown ({type(exc).__name__})"
    meta = {"casatasks": version, "runs": []}
    for spec in argv[1:]:
        name, ms = spec.split("=", 1)
        listfile = out / f"{name}.txt"
        start = time.perf_counter()
        record = listobs(vis=ms, listfile=str(listfile), verbose=True)
        wall = time.perf_counter() - start
        (out / f"{name}.json").write_text(json.dumps(plain(record), indent=1))
        (out / f"{name}.msmd.json").write_text(json.dumps(plain(msmd_record(ms))))
        meta["runs"].append({"name": name, "ms": ms, "wall_s": round(wall, 3)})
    (out / "meta.json").write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
