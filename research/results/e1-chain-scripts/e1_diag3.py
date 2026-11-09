"""Post hoc, hypothesis written before it ran: the target composite's
per-antenna amplitude errors come from F solved against a flat 1 Jy model
(smodel) while SIM-GCAL has alpha -0.6, with each antenna's own flagged
channels setting its effective frequency. Prediction per antenna and hand:
log|g_p| error = 0.5 * log(S_eff,p / S_flux), S_eff,p the gain solve's
weighted mean of S(nu) over antenna p's unflagged gcal cells (weights
|B_p B_q|^2 |S|, the least-squares weight of an amplitude fit against a flat
model), S_flux fluxscale's value. Compared with the fitted antenna errors of
diag2.json (first 8 target integrations)."""

import json
import sys
from pathlib import Path

import e1_score as S
import numpy as np

ctx = S.Ctx(sys.argv[1], "full")
d2 = json.loads(Path(sys.argv[2]).read_text())
s_flux = json.loads((ctx.rr / "calibrate" / "summary.json").read_text())
rg = ctx.rows(S.GCAL)
rg = rg[ctx.uvdist[rg] > S.UVMIN]
first = ctx.c["SCAN_NUMBER"][rg] == ctx.c["SCAN_NUMBER"][rg].min()
fl = S.cell_flags(ctx.ms, ctx.version_name("rang_apply_"), rg)
sg = ctx.cal[2, :, 0]
out = {}
for h in range(2):
    b2 = np.abs(ctx.truth["bandpass"][..., h]) ** 2
    w = np.where(fl, 0.0, b2[ctx.a1[rg]] * b2[ctx.a2[rg]])
    num = np.zeros(ctx.nant)
    den = np.zeros(ctx.nant)
    for an in (ctx.a1[rg], ctx.a2[rg]):
        np.add.at(num, an, (w * sg**2).sum(1))
        np.add.at(den, an, (w * sg).sum(1))
    s_eff = num / np.where(den > 0, den, 1)  # LS amplitude of S against a flat model
    pred = 0.5 * np.log(s_eff / np.median(s_eff))
    meas = np.array(d2[f"hand{h}_antenna_amp_log_err"]["values"])
    good = meas != 0
    good &= np.abs(meas) < 0.5
    pm = pred[good] - pred[good].mean()
    mm = meas[good] - meas[good].mean()
    out[h] = {
        "corr": float(np.corrcoef(pm, mm)[0, 1]),
        "slope": float((pm @ mm) / (pm @ pm)),
        "rms_meas": float(mm.std()),
        "rms_resid_after_pred": float((mm - pm).std()),
    }
print(json.dumps(out, indent=1))
