"""fits_cmp.py GDIR WDIR [--json OUT]: GeMClean's files against WSClean's, file by file.

For every FITS file WSClean wrote (prefix `w-`), the GeMClean file of the same
name (prefix `g-`): the largest |G - W| over the image, relative to the
largest |W| of that file and to the largest |W| of the same channel's Stokes I
(or first polarisation) dirty image; WSCIMGWG relative difference; CRVAL3,
CDELT3, CRVAL4 equality; BMAJ/BMIN relative difference. Missing files are
listed. Research note: research/g9-stokes.md.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits


def main():
    gdir, wdir = Path(sys.argv[1]), Path(sys.argv[2])
    out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    rows, missing = [], []
    wfiles = sorted(wdir.glob("w-*.fits"))
    first_dirty = {}
    for f in wfiles:
        m = re.match(r"w-(\d{4}-|MFS-)?([A-Z]+)-dirty\.fits", f.name)
        if m:
            key = m.group(1) or ""
            if key not in first_dirty:
                first_dirty[key] = float(np.abs(fits.getdata(f)).max())
    for f in wfiles:
        g = gdir / ("g-" + f.name[2:])
        if not g.exists():
            missing.append(f.name)
            continue
        hw, hg = fits.getheader(f), fits.getheader(g)
        dw = fits.getdata(f).astype(np.float64)
        dg = fits.getdata(g).astype(np.float64)
        m = re.match(r"w-(\d{4}-|MFS-)?", f.name)
        key = m.group(1) or "" if m else ""
        ref_i = first_dirty.get(key, np.nan)
        diff = float(np.abs(dg - dw).max())
        peak = float(np.abs(dw).max())
        row = {
            "file": f.name,
            "max_abs_diff": diff,
            "rel_own_peak": diff / peak if peak else float("nan"),
            "rel_first_dirty_peak": diff / ref_i,
            "wscimgwg_rel": abs(hg.get("WSCIMGWG", 0) - hw.get("WSCIMGWG", 0))
            / max(abs(hw.get("WSCIMGWG", 0)), 1e-300),
            "crval3_rel": abs(hg["CRVAL3"] - hw["CRVAL3"]) / hw["CRVAL3"],
            "cdelt3_rel": abs(hg["CDELT3"] - hw["CDELT3"]) / abs(hw["CDELT3"]),
            "crval4_equal": hg["CRVAL4"] == hw["CRVAL4"],
            "bmaj_rel": abs(hg.get("BMAJ", 0) - hw.get("BMAJ", 0))
            / max(hw.get("BMAJ", 0), 1e-300),
        }
        rows.append(row)
    for r in rows:
        print(
            f"{r['file']:28s} |d| {r['max_abs_diff']:.3e} own {r['rel_own_peak']:.2e} "
            f"I {r['rel_first_dirty_peak']:.2e} WG {r['wscimgwg_rel']:.1e} "
            f"F {r['crval3_rel']:.0e}/{r['cdelt3_rel']:.0e} S4 {r['crval4_equal']} B {r['bmaj_rel']:.1e}"
        )
    if missing:
        print("missing:", missing)
    if out_json:
        Path(out_json).write_text(
            json.dumps({"rows": rows, "missing": missing}, indent=1) + "\n"
        )


if __name__ == "__main__":
    main()
