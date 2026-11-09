"""Post hoc (e1-chain.md 8): does the twin's Df error follow from its cross-hand
phase error? The chain's Df compared with the truth's leakage moved into the
chain's cross-hand gauge, d_x -> e^s d_x, d_y -> e^-s d_y (A1 2.5), e the
chain/truth cross-hand phasor per channel (scan-mean), for s = +1 and -1."""

import json
import math
import sys

import e1_score as S
import numpy as np

ctx = S.Ctx(sys.argv[1], sys.argv[2])
kc, xf, df = ctx.table("Kcross"), ctx.table("Xf"), ctx.table("Df")
nu0 = kc.k_reference_frequency(0)
x = xf.params[:, :, 0].astype(complex)[0]
truth_c = ctx.gauge["kcross"] * ctx.gauge["xf"]
ph = []
for tm in np.unique(kc.column("TIME")):
    tau = float(np.median(kc.params[kc.column("TIME") == tm, 0, 0]))
    ph.append(np.exp(2j * math.pi * tau * 1e-9 * (ctx.freq - nu0)) * x / truth_c)
e = np.mean(ph, axis=0)
e /= np.abs(e)
d = df.params.astype(complex)
ok = ~df.flags
ant = df.column("ANTENNA1")
t = ctx.gauge["leakage"][ant]
out = {
    "unrotated_max": float(np.abs(d - t)[ok].max()),
    "unrotated_median": float(np.median(np.abs(d - t)[ok])),
}
for sgn in (1, -1):
    tr = t.copy()
    tr[..., 0] *= e[None] ** sgn
    tr[..., 1] *= np.conj(e[None]) ** sgn
    err = np.abs(d - tr)[ok]
    out[f"rotated_s{sgn:+d}"] = {
        "median": float(np.median(err)),
        "max": float(err.max()),
    }
print(json.dumps(out, indent=1))
