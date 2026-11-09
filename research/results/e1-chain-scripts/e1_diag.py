"""Post-hoc diagnostics of run -03's term failures (research/e1-chain.md 7):
where the target composite and the cross-hand phase errors sit."""

import json
import sys

import e1_score as S
import numpy as np

run = sys.argv[1]
ctx = S.Ctx(run, sys.argv[2] if len(sys.argv) > 2 else "full")
K, G, B, F = (ctx.table(n) for n in ("K", "G", "B", "F"))
fid = ctx.fields
out = {}
rows = ctx.rows(S.TARGET)[: 2016 * 8]
pc, pf = S.composite(
    ctx, rows, [K, F, B], [fid[S.FCAL], fid[S.GCAL], fid[S.FCAL]], ["linear"] * 3
)
pt = S.truth_product(ctx, rows)
eps = pc / pt - 1
ok = ~pf
amp = np.abs(pc) / np.abs(pt) - 1
ph = np.angle(pc / pt)
out["amp_median_by_chan_x"] = np.nanmedian(np.where(ok, amp, np.nan)[..., 0], 0)[
    ::16
].tolist()
out["phase_median_by_chan_x"] = np.nanmedian(np.where(ok, ph, np.nan)[..., 0], 0)[
    ::16
].tolist()
out["abs_amp_median"] = float(np.nanmedian(np.abs(np.where(ok, amp, np.nan))))
out["abs_phase_median"] = float(np.nanmedian(np.abs(np.where(ok, ph, np.nan))))
# Per antenna: the antenna-based error from B and F alone, against truth.
b = B.params.astype(complex)  # (ant, chan, 2)
bt = ctx.truth["bandpass"] * ctx.truth["k"]
kk = K.params[:, 0, :].astype(float)
# B * K for the first K solution vs truth B*K, referenced per hand to antenna 0
ka = K.column("ANTENNA1")
t0 = K.column("TIME") == K.column("TIME").min()
kph = np.exp(
    2j
    * np.pi
    * kk[t0][:, None, :]
    * 1e-9
    * (ctx.freq - K.k_reference_frequency(0))[None, :, None]
)
kb = b * kph[np.argsort(ka[t0])]
r = kb / bt
r = r / r[0:1]
out["KB_over_truth_ref0_amp_dev_median_by_ant"] = np.median(
    np.abs(np.abs(r) - 1), axis=(1, 2)
).tolist()
out["KB_over_truth_ref0_phase_std_over_chan_by_ant"] = (
    np.std(np.unwrap(np.angle(r), axis=1), axis=1).mean(1).tolist()
)
out["B_flag_fraction"] = float(B.flags.mean())
print(json.dumps(out, indent=1))
