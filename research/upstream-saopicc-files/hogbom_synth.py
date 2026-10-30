"""Overwrite DATA of an MS copy with a synthetic sky (point sources, optional noise), keeping UVW/flags.

usage: python hogbom_synth.py <ms> <mode> [uvw_scale]
mode: "point" (one 1 Jy source at the phase centre), "field" (5 sources, seed 1, plus noise)
"""
import sys
import numpy as np
from casacore.tables import table

ms, mode = sys.argv[1], sys.argv[2]
scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
t = table(ms, readonly=False, ack=False)
uvw = t.getcol("UVW") * scale
if scale != 1.0:
    t.putcol("UVW", uvw)
spw = table(ms + "/SPECTRAL_WINDOW", ack=False)
freqs = spw.getcol("CHAN_FREQ")[0]
ncorr = t.getcell("DATA", 0).shape[1]
lam = 299792458.0 / freqs
rng = np.random.default_rng(1)
if mode == "point":
    comps = [(1.0, 0.0, 0.0)]
else:
    deg = np.pi / 180
    comps = [(1.0, 0.0, 0.0)] + [(rng.uniform(0.2, 2.0), rng.uniform(-0.4, 0.4) * deg, rng.uniform(-0.4, 0.4) * deg) for _ in range(4)]
vis = np.zeros((uvw.shape[0], freqs.size), np.complex128)
for s, l, m in comps:
    n = np.sqrt(1 - l * l - m * m)
    phase = (uvw[:, 0, None] * l + uvw[:, 1, None] * m + uvw[:, 2, None] * (n - 1)) / lam[None, :]
    vis += s * np.exp(-2j * np.pi * phase)
if mode != "point":
    vis += 0.05 * (rng.standard_normal(vis.shape) + 1j * rng.standard_normal(vis.shape))
data = np.zeros((uvw.shape[0], freqs.size, ncorr), np.complex64)
data[:, :, 0] = vis
data[:, :, ncorr - 1] = vis
t.putcol("DATA", data)
print("wrote", mode, "components", comps, "rows", uvw.shape[0], "chans", freqs.size, "ncorr", ncorr,
      "max |uv| m", np.hypot(uvw[:, 0], uvw[:, 1]).max())
t.close()
