# SPDX-License-Identifier: MIT
"""research/k-ambiguity.md section 4 step 2: on the arrays `ka_capture.py`
saved for one K solve, separate the hypotheses of section 3 for one antenna:
its FFT start per hand (rang's rule, recomputed), its refant-baseline cells,
the FFT run, the zero run and the zero run without the stop test, their
interval and per-antenna costs, the key's own choice, and where the
antenna's own data put its delay.

    python ka_probe.py CAPTURE.npz ANT OUT.json
"""

import json
import sys

import numpy as np
from rang import cal_delay

NAMES = (
    "data",
    "model",
    "weights",
    "flag",
    "flag_row",
    "antenna1",
    "antenna2",
    "time_bin",
)
POINTS = 2**15


def cells_of(a):
    """Unflagged parallel-hand cells (row, chan, hand) as the cost reads them."""
    w = np.broadcast_to(a["weights"], a["data"].shape)
    f = np.broadcast_to(a["flag"], a["data"].shape).astype(bool)
    ok = ~f & (w > 0) & np.isfinite(a["data"]) & np.isfinite(a["model"])
    ok &= ~(np.asarray(a["flag_row"], bool) | (a["antenna1"] == a["antenna2"]))[
        :, None, None
    ]
    return ok[..., [0, 3]]


def fft_start(a, ant, ref, freq):
    """rang's `fft_pass` for one antenna (core/src/cal/delay.rs): refant
    baseline data averaged per channel, zero-padded FFT, first maximum in the
    fftshift-ed order; per hand (ns), and the unflagged cells used."""
    p, q = a["antenna1"], a["antenna2"]
    rows = ((p == ref) & (q == ant)) | ((p == ant) & (q == ref))
    rows &= ~np.asarray(a["flag_row"], bool)
    # the kernel's cell flag is per (row, chan) over the four correlations
    w = np.broadcast_to(a["weights"], a["data"].shape)
    f = np.broadcast_to(a["flag"], a["data"].shape).astype(bool)
    bad = (f | (w <= 0) | ~np.isfinite(a["data"])).any(-1)
    d = np.where(bad[rows][..., None], 0, np.nan_to_num(a["data"][rows]))
    cnt = (~bad[rows]).sum(0)
    nchan = len(freq)
    n = -(-POINTS // nchan) * nchan
    delta = freq[1] - freq[0]
    out, sign = [], (-1.0 if (p[rows] == ref).all() else 1.0)
    for c in (0, 3):
        s = d[..., c].sum(0) / np.maximum(cnt, 1)
        buf = np.zeros(n, complex)
        buf[:nchan] = s
        amp = np.abs(np.fft.fft(buf))
        order = (np.arange(n) + n - n // 2) % n
        k = order[np.argmax(amp[order])]
        i = k if k < (n - 1) // 2 + 1 else k - n
        out.append(sign * i / (n * delta) * 1e9)
    return {
        "start_ns": out,
        "refant_rows": int(rows.sum()),
        "refant_cells_unflagged": int(cnt.sum()),
        "refant_buffer_all_zero": bool(not np.any(d[..., [0, 3]])),
        "nyquist_ns": -0.5 / delta * 1e9,
    }


def costs(a, gains, ok):
    """Per interval total and per antenna (each baseline to both ends) of
    w |V - g_p M g_q^*|^2 over `ok`."""
    tb, p, q = a["time_bin"], a["antenna1"], a["antenna2"]
    g = gains  # (ntime, nchan, nant, 2)
    nant = g.shape[2]
    per_ant = np.zeros((g.shape[0], nant))
    total = np.zeros(g.shape[0])
    w = np.broadcast_to(a["weights"], a["data"].shape)
    for h, c in ((0, 0), (1, 3)):
        pred = g[tb, :, p, h] * a["model"][..., c] * np.conj(g[tb, :, q, h])
        r = np.where(
            ok[..., h], np.abs(a["data"][..., c] - pred) ** 2 * w[..., c], 0
        ).sum(1)
        np.add.at(total, tb, r)
        np.add.at(per_ant, (tb, p), r)
        np.add.at(per_ant, (tb, q), r)
    return total, per_ant


def own_spectrum(a, gains, ant, ok, freq, t=0):
    """The antenna's own delay spectrum with every other antenna corrected by
    `gains`: z = V / (M g_q^*) on (ant, q) rows (conjugated on (p, ant)),
    |sum w z exp(-2 pi i nu tau)| over tau; its peak, and the adjacent-channel
    phase step of z (median |step|, rad)."""
    tb, p, q = a["time_bin"], a["antenna1"], a["antenna2"]
    w = np.broadcast_to(a["weights"], a["data"].shape)
    sel = (tb == t) & ((p == ant) | (q == ant)) & (p != q)
    out = {}
    taus = np.arange(-2600.0, 2600.0, 0.5)
    for h, c in ((0, 0), (1, 3)):
        z = []
        ww = []
        for r in np.flatnonzero(sel):
            o = q[r] if p[r] == ant else p[r]
            m = a["model"][r, :, c]
            v = a["data"][r, :, c]
            if p[r] == ant:
                zz = v / (m * np.conj(gains[t, :, o, h]))
            else:
                zz = np.conj(v / (m * gains[t, :, o, h]))
            good = ok[r, :, h] & (np.abs(m) > 0)
            z.append(np.where(good, zz, 0))
            ww.append(np.where(good, w[r, :, c], 0))
        z, ww = np.array(z), np.array(ww)
        zs = (z * ww).sum(0)
        f = freq - freq.mean()
        spec = np.abs(np.exp(-2j * np.pi * np.outer(taus * 1e-9, f)) @ zs)
        steps = np.angle(zs[1:] * np.conj(zs[:-1]))
        live = (np.abs(zs[1:]) > 0) & (np.abs(zs[:-1]) > 0)
        i0 = np.argmin(np.abs(taus - 0.0))
        iny = np.argmin(np.abs(taus + 2392.5))
        out[f"hand{h}"] = {
            "rows": int(sel.sum()),
            "cells": int((ww > 0).sum()),
            "peak_tau_ns": float(taus[np.argmax(spec)]),
            "peak": float(spec.max()),
            "at_0_ns": float(spec[i0]),
            "at_-2392.5_ns": float(spec[iny]),
            "median_abs_channel_step_rad": float(np.median(np.abs(steps[live]))) if live.any() else None,
        }  # fmt: skip
    return out


def run(a, kw, **over):
    k = dict(kw, **over, return_gains=True)
    return cal_delay.solve(*[a[n] for n in NAMES], chan_freq=a["chan_freq"], **k)


def main(path, ant, out_path):
    ant = int(ant)
    a = dict(np.load(path))
    rec = json.load(open(path.replace(".npz", ".json")))
    kw = dict(rec["kwargs"])
    for k in ("trace", "return_gains"):
        kw.pop(k, None)
    freq = a["chan_freq"]
    ok = cells_of(a)
    ref = int(kw["refant"][0] if isinstance(kw["refant"], list) else kw["refant"])
    res = {"capture": path, "ant": ant, "kwargs": kw, "recorded": {
        "settings": rec["settings"], "delays_ns_ant": [r[0][ant] for r in rec["delays_ns"]],
        "refant_used": rec["refant_used"], "iterations": rec["iterations"]}}  # fmt: skip
    res["fft_start"] = fft_start(a, ant, ref, freq)
    runs = {
        "fft": dict(zero_start=False),
        "zero": dict(zero_start=False, initial_estimate=False),
        "zero_nostop": dict(zero_start=False, initial_estimate=False, stop_fraction=1.0,
                            max_iterations=max(200, int(kw.get("max_iterations", 50)))),
        "fft_nostop": dict(zero_start=False, stop_fraction=1.0,
                           max_iterations=max(200, int(kw.get("max_iterations", 50)))),
        "key_on": dict(zero_start=True),
    }  # fmt: skip
    sols = {}
    for name, over in runs.items():
        s = run(a, kw, **over)
        sols[name] = s
        tot, per = costs(a, s.gains, ok)
        d = np.asarray(s.delays)
        res[name] = {
            "iterations": s.iterations,
            "converged_fraction": s.converged_fraction,
            "delay_ns_ant": d[:, 0, ant].tolist(),
            "flag_ant": np.asarray(s.flags)[:, 0, ant].tolist(),
            "interval_cost": tot.tolist(),
            "cost_ant": per[:, ant].tolist(),
            "settings_zero_start": s.settings.get("zero_start"),
            "zero_start_intervals": s.settings.get("zero_start_intervals"),
        }
    # per antenna: where the zero run's cost is above the FFT run's
    _, pf = costs(a, sols["fft"].gains, ok)
    _, pz = costs(a, sols["zero"].gains, ok)
    df = np.asarray(sols["fft"].delays)[:, 0]
    dz = np.asarray(sols["zero"].delays)[:, 0]
    res["per_antenna_fft_minus_zero"] = [
        {"t": t, "ant": i, "cost_fft": float(pf[t, i]), "cost_zero": float(pz[t, i]),
         "delay_fft": df[t, i].tolist(), "delay_zero": dz[t, i].tolist()}
        for t in range(pf.shape[0]) for i in range(pf.shape[1])
        if abs(pf[t, i] - pz[t, i]) > 1e-6 * max(abs(pf[t, i]), 1e-30)
        or np.abs(df[t, i] - dz[t, i]).max() > 0.01
    ]  # fmt: skip
    res["own_spectrum_zero_gains"] = own_spectrum(a, sols["zero"].gains, ant, ok, freq)
    res["own_spectrum_fft_gains"] = own_spectrum(a, sols["fft"].gains, ant, ok, freq)
    with open(out_path, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(json.dumps({k: res[k] for k in ("fft_start",)}, default=str))
    for n in runs:
        print(n, json.dumps(res[n], default=str))


if __name__ == "__main__":
    main(*sys.argv[1:])
