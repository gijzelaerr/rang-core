"""gap_where.py OUT SKY CFG POL [PART] CATALOGUE : where criterion E's largest difference sits.

Prints the pixel of the largest |difference| of the common-beam restored images, the nearest true
component (distance in pixels, its Stokes I and polarisation), and both imagers' residual, model
aperture flux and restored values there (research/g9-stokes.md)."""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import Run, common_beam_image, inner  # noqa: E402

out, sky, cfg, pol = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
part = sys.argv[5] if len(sys.argv) > 6 else ""
cat = json.loads(Path(sys.argv[-1]).read_text())
g, w = Run(out, "g", sky, cfg), Run(out, "w", sky, cfg)
rg, rw = common_beam_image(g, w, pol, part), common_beam_image(w, w, pol, part)
n = rg.shape[0]
lo = n // 6
d = inner(rg - rw)
y, x = np.unravel_index(np.argmax(np.abs(d)), d.shape)
y, x = y + lo, x + lo
print(
    f"largest |diff| {abs(d).max() * 1e6:.1f} uJy at (x {x}, y {y}); G {rg[y, x] * 1e6:.1f} W {rw[y, x] * 1e6:.1f} uJy"
)
best = min(cat["components"], key=lambda c: (c["x"] - x) ** 2 + (c["y"] - y) ** 2)
dist = float(np.hypot(best["x"] - x, best["y"] - y))
s = (
    {p: float(np.mean(best["stokes_per_channel"][p])) for p in "IQUV"}
    if "stokes_per_channel" in best
    else {}
)
print(f"nearest component at {dist:.1f} px: {s}  p {best.get('p')} rm {best.get('rm')}")
for run in (g, w):
    res, _ = run.get("residual", pol, part)
    mod, _ = run.get("model", pol, part)
    yy, xx = np.mgrid[0:n, 0:n]
    ap = (xx - best["x"]) ** 2 + (yy - best["y"]) ** 2 <= 36
    print(
        f"  {run.p}: residual there {res[y, x] * 1e6:.1f} uJy, peak |residual| in aperture {np.abs(res[ap]).max() * 1e6:.1f} uJy, model flux {mod[ap].sum() * 1e3:.4f} mJy"
    )
