"""Simulated truth of research/e2a-3b-k.md section 3, on the subset's rows.

    python k_sim.py noise                   sigma per (channel, correlation) of src.ms -> O/noise.npz
    python k_sim.py make CASE SEED|none     O/sim-TAG-u.ms (DATA replaced) and O/truth-TAG/{K,G,B}

CASE s1 (static) or s2 (varying); SEED an integer or `none` (S0 when
CASE s1). TAG is CASE-SEED (`s0` for the noise-free S1). The model is rang
U's MODEL_DATA on the real subset (`O/rang-u.ms`); the truth terms come
from T-T's archived tables (`O/win/rang-tt.ms.rang-run/calibrate`).
"""

import json
import shutil
import sys
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
from rang import cal_apply, core_ms, core_ms_write
from rang.formats import caltable

O = Path.home() / "rang-data" / "outputs" / "e2a-3b-k-20261117"
TT = O / "win" / "rang-tt.ms.rang-run" / "calibrate"
POOLED = [cal_apply.POOLED] * 3


def cols(ms, names):
    with core_ms.open_table(ms) as t:
        return {n: np.asarray(t.getcol(n)) for n in names}


def freq_of(ms):
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        return np.asarray(t.getcol("CHAN_FREQ")[0], float)


def noise():
    c = cols(O / "src.ms", ("TIME", "ANTENNA1", "ANTENNA2", "DATA", "FLAG", "FLAG_ROW"))
    flag = c["FLAG"] | c["FLAG_ROW"][:, None, None]
    order = np.lexsort((c["TIME"], c["ANTENNA2"], c["ANTENNA1"]))
    a1, a2, t = c["ANTENNA1"][order], c["ANTENNA2"][order], c["TIME"][order]
    nxt = (
        (a1[1:] == a1[:-1])
        & (a2[1:] == a2[:-1])
        & (np.diff(t) < 12)
        & (a1[1:] != a2[1:])
    )
    i0, i1 = order[:-1][nxt], order[1:][nxt]
    nchan = c["DATA"].shape[1]
    sigma = np.full((nchan, 4), np.nan)
    count = np.zeros((nchan, 4), int)
    for k in range(4):
        d = (c["DATA"][i1, :, k] - c["DATA"][i0, :, k]) / np.sqrt(2)
        ok = ~flag[i1, :, k] & ~flag[i0, :, k]
        for ch in range(nchan):
            x = d[ok[:, ch], ch]
            count[ch, k] = x.size
            if x.size >= 50:
                re, im = x.real, x.imag
                mad = 0.5 * (
                    np.median(np.abs(re - np.median(re)))
                    + np.median(np.abs(im - np.median(im)))
                )
                sigma[ch, k] = 1.4826 * mad
    filled = np.isnan(sigma)
    for k in range(4):
        sigma[filled[:, k], k] = np.nanmedian(sigma[:, k])
    np.savez(O / "noise.npz", sigma=sigma, count=count, filled=filled)
    out = {"pairs": int(nxt.sum()), "sigma_median_per_corr": np.nanmedian(sigma, 0).tolist(),
           "channels_filled_per_corr": filled.sum(0).tolist()}  # fmt: skip
    (O / "noise.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out))
    return 0


def _fill_time(times, vals, ok):
    """Per (antenna, hand): values at `times` interpolated over unflagged
    nodes; returns filled values and whether any node existed."""
    out = np.array(vals, copy=True)
    for a in range(vals.shape[1]):
        for h in range(vals.shape[2]):
            good = ok[:, a, h]
            if good.any():
                out[:, a, h] = np.interp(times, times[good], vals[good, a, h])
    return out


def _nodes(tab):
    """(times, scans, params (ntime, nant, hand), ok) of a K or G table."""
    t = np.round(tab.column("TIME"), 3)
    times = np.unique(t)
    ant = tab.column("ANTENNA1")
    nant = int(ant.max()) + 1
    p = tab.params[:, 0, :]
    f = np.stack([np.asarray(x) for x in tab.main["FLAG"]])[:, 0, :]
    vals = np.zeros((len(times), nant, 2), p.dtype)
    ok = np.zeros((len(times), nant, 2), bool)
    ti = np.searchsorted(times, t)
    vals[ti, ant] = p
    ok[ti, ant] = ~f
    scans = np.zeros(len(times), int)
    scans[ti] = tab.column("SCAN_NUMBER")
    return times, scans, vals, ok


def _per_dump(tab, dump_t, dump_scan, kind, mode):
    """Truth values (ndump, nant, 2) from a template K or G table: `static`
    the scan's single solution; `varying` linear in time between the
    scan's nodes (G: amplitude and unwrapped phase), clamped at the edges."""
    times, scans, vals, ok = _nodes(tab)
    nant = vals.shape[1]
    out = np.zeros((len(dump_t), nant, 2), complex if kind == "G" else float)
    for s in np.unique(dump_scan):
        sel_d = dump_scan == s
        sel_n = scans == s
        tn, vn, on = times[sel_n], vals[sel_n], ok[sel_n]
        for a in range(nant):
            for h in range(2):
                g = on[:, a, h]
                if not g.any():
                    out[sel_d, a, h] = 0.0 if kind == "K" else 1.0
                    continue
                if kind == "K":
                    y = vn[g, a, h].real
                    out[sel_d, a, h] = (
                        y.mean()
                        if mode == "static"
                        else np.interp(dump_t[sel_d], tn[g], y)
                    )
                else:
                    amp = np.abs(vn[g, a, h])
                    ph = np.unwrap(np.angle(vn[g, a, h]))
                    if mode == "static":
                        out[sel_d, a, h] = amp.mean() * np.exp(1j * ph.mean())
                    else:
                        out[sel_d, a, h] = np.interp(
                            dump_t[sel_d], tn[g], amp
                        ) * np.exp(1j * np.interp(dump_t[sel_d], tn[g], ph))
    return out


def _table_per_dump(tab, dump_t, dump_scan, values):
    """A copy of template `tab` with one unflagged row per (dump, antenna)."""
    nd, nant, _ = values.shape
    t_idx = np.repeat(np.arange(nd), nant)
    a_idx = np.tile(np.arange(nant), nd)
    n = nd * nant
    name = "FPARAM" if tab.float_param else "CPARAM"
    dt = np.float32 if tab.float_param else np.complex64
    ant2 = int(np.asarray(tab.main["ANTENNA2"])[0])
    main = {
        "TIME": [float(dump_t[t]) for t in t_idx],
        "FIELD_ID": [int(np.asarray(tab.main["FIELD_ID"])[0])] * n,
        "SPECTRAL_WINDOW_ID": [0] * n,
        "ANTENNA1": [int(a) for a in a_idx],
        "ANTENNA2": [ant2] * n,
        "INTERVAL": [0.0] * n,
        "SCAN_NUMBER": [int(dump_scan[t]) for t in t_idx],
        "OBSERVATION_ID": [0] * n,
        name: [values[t, a].astype(dt).reshape(1, 2) for t, a in zip(t_idx, a_idx)],
        "PARAMERR": [np.zeros((1, 2), np.float32)] * n,
        "FLAG": [np.zeros((1, 2), bool)] * n,
        "SNR": [np.ones((1, 2), np.float32)] * n,
        "WEIGHT": [None] * n,
    }
    return caltable.CalTable(tab.vis_cal, main, deepcopy(tab.subtables), dict(tab.keywords),
                             list(tab.info))  # fmt: skip


def _bandpass_truth(tab, freq, mode):
    """B_T from a template B table: flagged channels filled from neighbours
    (1 if none); `static` the amplitude only; `varying` the complex B with
    its least-squares linear phase slope per antenna and hand removed."""
    b = deepcopy(tab)
    out = []
    for cp, fl in zip(tab.main["CPARAM"], tab.main["FLAG"]):
        cp = np.asarray(cp, complex)
        fl = np.asarray(fl, bool)
        new = np.ones_like(cp)
        ch = np.arange(cp.shape[0])
        for h in range(cp.shape[1]):
            g = ~fl[:, h] & (np.abs(cp[:, h]) > 0)
            if g.sum() < 2:
                continue
            amp = np.interp(ch, ch[g], np.abs(cp[g, h]))
            ph = np.interp(ch, ch[g], np.unwrap(np.angle(cp[g, h])))
            if mode == "static":
                new[:, h] = amp
            else:
                x = (freq - freq.mean()) / 1e9
                slope = np.polyfit(x[g], ph[g], 1)[0]
                new[:, h] = amp * np.exp(1j * (ph - slope * x))
        out.append(new.astype(np.complex64))
    b.main["CPARAM"] = out
    b.main["FLAG"] = [np.zeros(np.shape(f), bool) for f in tab.main["FLAG"]]
    return b


def make(case, seed):
    tag = "s0" if (case == "s1" and seed == "none") else f"{case}-{seed}"
    ms = O / f"sim-{tag}-u.ms"
    tdir = O / f"truth-{tag}"
    if ms.exists() or tdir.exists():
        raise SystemExit(f"{ms} or {tdir} exists")
    t0 = time.perf_counter()
    shutil.copytree(O / "src.ms", ms)
    freq = freq_of(ms)
    c = cols(ms, ("TIME", "ANTENNA1", "ANTENNA2", "SCAN_NUMBER", "FLAG"))
    dump_t, first = np.unique(c["TIME"], return_index=True)
    dump_scan = c["SCAN_NUMBER"][first]
    mode = "static" if case == "s1" else "varying"
    kname, gname, bname = ("K0", "G0", "B0") if case == "s1" else ("K1", "G1", "B1")
    kt = caltable.read(TT / kname)
    gt = caltable.read(TT / gname)
    bt = caltable.read(TT / bname)
    K = _table_per_dump(
        kt, dump_t, dump_scan, _per_dump(kt, dump_t, dump_scan, "K", mode)
    )
    G = _table_per_dump(
        gt, dump_t, dump_scan, _per_dump(gt, dump_t, dump_scan, "G", mode)
    )
    B = _bandpass_truth(bt, freq, mode)
    tdir.mkdir()
    for n, tab in (("K", K), ("G", G), ("B", B)):
        caltable.write(tab, tdir / n)
    model = cols(O / "rang-u.ms", ("MODEL_DATA", "TIME", "ANTENNA1", "ANTENNA2"))
    for k in ("TIME", "ANTENNA1", "ANTENNA2"):
        if not np.array_equal(model[k], c[k]):
            raise SystemExit(f"{k} differs between rang-u.ms and the copy")
    m = model["MODEL_DATA"]
    v, _ = cal_apply.apply(m, np.zeros(m.shape, bool), c["TIME"], c["ANTENNA1"], c["ANTENNA2"],
                           freq, [B, K, G], interp="linear", direction="corrupt",
                           table_fields=POOLED)  # fmt: skip
    del m
    info = {
        "tag": tag,
        "case": case,
        "seed": seed,
        "templates": [kname, gname, bname],
        "mode": mode,
    }
    if seed != "none":
        sigma = np.load(O / "noise.npz")["sigma"].astype(np.float32)
        rng = np.random.default_rng(int(seed))
        n = rng.standard_normal(v.shape, np.float32) + 1j * rng.standard_normal(
            v.shape, np.float32
        )
        v = (v + n * sigma[None]).astype(np.complex64)
        info["sigma_median_per_corr"] = np.median(sigma, 0).tolist()
    auto = c["ANTENNA1"] == c["ANTENNA2"]
    with core_ms_write.open_table(ms, readonly=False) as t:
        data = np.asarray(t.getcol("DATA"))
        data[~auto] = v[~auto]
        t.putcol("DATA", data)
    info["seconds"] = time.perf_counter() - t0
    (tdir / "truth.json").write_text(json.dumps(info, indent=1) + "\n")
    print(json.dumps(info))
    return 0


if __name__ == "__main__":
    step, *args = sys.argv[1:]
    sys.exit({"noise": noise, "make": make}[step](*args))
