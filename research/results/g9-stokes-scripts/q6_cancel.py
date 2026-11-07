"""q6_cancel.py OUT SKY CATALOGUE CFG : are the shared linear-polarisation failures of a joined QU run
(criterion D) the components whose Q + U nearly cancels in WSClean 3.7's linear peak sum? For
every scored (component, channel): |Q_T + U_T| / (2 P_T), the error of each imager, and the
polarised flux left in each imager's residual within 6 pixels (research/g9-stokes.md)."""

import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

out, sky, catalogue, cfg = (
    Path(sys.argv[1]),
    sys.argv[2],
    Path(sys.argv[3]),
    sys.argv[4],
)
cat = json.loads(catalogue.read_text())
score = json.loads((out / f"score-{sky}.json").read_text())
recs = score[cfg]["D"]["lin_records"]
size = cat["image"]["size"]
yy, xx = np.mgrid[0:size, 0:size]


def resid(who, pol, k):
    f = out / "runs" / who / f"{sky}-{cfg}" / f"{who}-{k:04d}-{pol}-residual.fits"
    return fits.getdata(f).astype(float).squeeze()


nout = 1 + max(r["ch"] for r in recs)
groups = [
    list(range(i * cat["nchan"] // nout, (i + 1) * cat["nchan"] // nout))
    for i in range(nout)
]
cache = {}
rows = []
for r in recs:
    c = cat["components"][r["src"]]
    k = r["ch"]
    s = c["stokes_per_channel"]
    q, u = (
        np.mean(np.asarray(s["Q"])[groups[k]]),
        np.mean(np.asarray(s["U"])[groups[k]]),
    )
    p = float(np.hypot(q, u))
    near = np.argmin((xx - c["x"]) ** 2 + (yy - c["y"]) ** 2)
    left = {}
    for who in ("g", "w"):
        for pol in ("Q", "U"):
            key = (who, pol, k)
            if key not in cache:
                cache[key] = resid(who, pol, k)
        left[who] = float(
            np.hypot(cache[(who, "Q", k)].flat[near], cache[(who, "U", k)].flat[near])
        )
    fail = r["err"]["w"] > r["tol"]
    rows.append(
        (
            abs(q + u) / (2 * p),
            fail,
            r["err"]["g"],
            r["err"]["w"],
            left["g"] / p,
            left["w"] / p,
        )
    )
rows.sort()
print("cancel=|Q+U|/2P  wsclean_fails  err_G  err_W  residual_peak/P G  W")
for row in rows:
    print("%.3f %5s %.4f %.4f %.4f %.4f" % row)
f = [r for r in rows if r[1]]
ok = [r for r in rows if not r[1]]
print(
    f"failing: {len(f)}, median cancel {np.median([r[0] for r in f]):.3f}; passing: {len(ok)}, median cancel {np.median([r[0] for r in ok]):.3f}"
)
