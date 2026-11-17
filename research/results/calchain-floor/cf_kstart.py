# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 10 (post hoc): the data the K1 FFT
start sees for one antenna in one K1 interval of an arm: the baseline to
the refant (m022), its unflagged cells and channels under the arm's FLAG
(uvrange > 150 m), and, in NumPy, the zero-padded FFT of the refant
baseline's B0-corrected mean spectrum (the start's construction in
`core/src/cal/delay.rs` `initial_estimate`: rows to the refant, flagged
cells left out, the mean per channel; padded here to 2^18 points).
Then the noise-free least-squares cost of that antenna's delay on all its
baselines in the interval (others at truth), on a grid around truth and
around the solution rang wrote.

    python cf_kstart.py CASE ARM ANT INTERVAL
"""

import json
import sys

import cf_score as S
import numpy as np
from rang import cal_apply, core_ms


def main(case, name, ant, interval):
    ant, interval = int(ant), int(interval)
    d = S.O / case
    ms = d / f"arm-{name}.ms"
    rows = S.Rows(ms)
    A = ms.parent / f"{ms.name}.rang-run" / "calibrate"
    k1 = S.tab(A / "K1")
    t1 = np.unique(np.round(k1.column("TIME"), 3))
    fr = rows.field_rows
    with core_ms.open_table(ms) as t:
        tm = np.asarray(t.getcol("TIME"))[fr]
        a1 = np.asarray(t.getcol("ANTENNA1"))[fr]
        a2 = np.asarray(t.getcol("ANTENNA2"))[fr]
        uvw = np.asarray(t.getcol("UVW"))[fr]
    iv = np.abs(tm[:, None] - t1[None, :]).argmin(1)
    long_ = (np.hypot(uvw[:, 0], uvw[:, 1]) > 150) & (a1 != a2)
    sel = (iv == interval) & long_ & ((a1 == ant) | (a2 == ant))
    idx = fr[sel]
    with core_ms.open_table(ms) as t:
        v = np.asarray(t.getcol_rows("DATA", idx))
        m = np.asarray(t.getcol_rows("MODEL_DATA", idx))
        f = (
            np.asarray(t.getcol_rows("FLAG", idx))
            | np.asarray(t.getcol_rows("FLAG_ROW", idx))[:, None, None]
        )
    b1, b2, tt = a1[sel], a2[sel], tm[sel]
    # B0 corrects the data, G0 corrupts the model (K1's pre-apply, lower/higher VisCal types)
    vc, fc = cal_apply.apply(v, f, tt, b1, b2, rows.freq, [S.tab(A / "B0")], direction="correct",
                             nant=rows.nant, table_fields=[cal_apply.POOLED])  # fmt: skip
    mc, fm = cal_apply.apply(m, np.zeros(m.shape, bool), tt, b1, b2, rows.freq, [S.tab(A / "G0")],
                             direction="corrupt", nant=rows.nant, table_fields=[cal_apply.POOLED])  # fmt: skip
    bad = fc | fm
    bad = bad.any(-1)  # the kernel's whole-cell rule
    out = {"case": case, "arm": name, "antenna": ant, "interval": interval,
           "baseline_dumps": int(sel.sum())}  # fmt: skip
    to_ref = (b1 == rows.ref) | (b2 == rows.ref)
    out["refant_baseline_dumps"] = int(to_ref.sum())
    ok_ref = ~bad[to_ref]
    out["refant_cells"] = int(ok_ref.sum())
    out["refant_channels"] = int(ok_ref.any(0).sum())
    truth = S.tab(d / "truth-s0f" / "K")
    _, vt = S.kvals(truth)
    tk = vt[
        np.abs(np.unique(np.round(truth.column("TIME"), 3)) - t1[interval]).argmin()
    ]
    _, va = S.kvals(k1)
    out["truth_tau_ns (ant - ref)"] = (tk[ant] - tk[rows.ref]).tolist()
    out["rang_tau_ns (ant - ref)"] = (
        va[interval, ant] - va[interval, rows.ref]
    ).tolist()
    freq = rows.freq
    dnu = freq[1] - freq[0]
    for h, corr in ((0, 0), (1, 3)):
        if to_ref.any() and ok_ref.any():
            dd = np.where(~bad[to_ref], vc[to_ref][..., corr], 0)
            cnt = (~bad[to_ref]).sum(0)
            spec = np.where(cnt > 0, dd.sum(0) / np.maximum(cnt, 1), 0)
            n = 2**18
            amp = np.abs(np.fft.fftshift(np.fft.fft(spec, n)))
            lag = np.fft.fftshift(np.fft.fftfreq(n, dnu)) * 1e9
            top = np.argsort(amp)[::-1][:5]
            out[f"fft_peaks_ns_{h}"] = [
                [float(lag[k]), float(amp[k] / amp.max())] for k in top
            ]
        # cost over all the antenna's baselines vs its delay (others at truth)
        ph0 = 2 * np.pi * (freq - truth.k_reference_frequency(0)) / 1e9
        res = {}
        for label, centre in (
            ("truth", tk[ant, h]),
            ("rang", va[interval, ant, h] + tk[rows.ref, h]),
        ):
            grid = centre + np.linspace(-2, 2, 41)
            costs = []
            for tau in grid:
                kk = tk[:, h].copy()
                kk[ant] = tau
                g = np.exp(1j * ph0[None, :] * (kk[b1] - kk[b2])[:, None])
                pred = mc[..., corr] * g
                r = vc[..., corr] - pred
                costs.append(
                    float(
                        (np.abs(r[~bad]) ** 2).sum()
                        / max((np.abs(vc[..., corr][~bad]) ** 2).sum(), 1e-30)
                    )
                )
            res[label] = {"centre_ns": float(centre), "cost_at_centre": costs[20], "min": min(costs),
                          "argmin_ns": float(grid[int(np.argmin(costs))])}  # fmt: skip
        out[f"relative_cost_hand_{h}"] = res
    S.write(S.O / f"score-kstart-{case}-{name}-{ant}-{interval}.json", out)
    print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
