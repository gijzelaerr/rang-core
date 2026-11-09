"""probe_read.py DIR: what the WSClean probe shows (research/g9-stokes.md, section 2)."""

import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

d = Path(sys.argv[1])
cat = json.loads((d / "probe.json").read_text())
for c in cat["components"]:
    print(
        "source",
        round(c["x"]),
        round(c["y"]),
        "I",
        c["flux"],
        "Q",
        c["stokes_per_channel"]["Q"][0],
    )
for run in sorted(p for p in d.iterdir() if p.is_dir() and not p.name.endswith(".ms")):
    print(f"== {run.name}")
    for f in sorted(run.glob("*.fits")):
        h = fits.getheader(f)
        line = f"  {f.name:24s} WSCIMGWG {h.get('WSCIMGWG', 0):.9e} CRVAL4 {h['CRVAL4']:+.0f} BMAJ {h.get('BMAJ', 0) * 3600:.4f}"
        if "model" in f.name:
            m = fits.getdata(f)[0, 0]
            nz = np.argwhere(m != 0)
            line += f" components {[(int(x), int(y), float(m[y, x])) for y, x in nz]}"
        print(line)
