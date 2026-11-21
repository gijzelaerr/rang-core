"""Issue #55 gates G1 (CASA statwt) and G2 (known per-channel noise), research/apply-reweight.md.

    python rw_g12.py make OUT      # rang venv: the MSs (clean, rfi) and rang's weights
    python rw_g12.py casa OUT      # CASA venv (rang-o-casa_6.7.6.14): statwt on copies
    python rw_g12.py score OUT     # rang venv: score.json

16 antennas, 3 scans of 20 integrations of 8 s, 64 channels over 856-1712 MHz.
MODEL_DATA = 10 Jy on XX and YY; CORRECTED_DATA = model + noise, complex
Gaussian with sigma(p, q, nu) = sigma0 * s(nu) * sqrt(f_p f_q) per part, s a
bandpass-like shape varying 3x over the band, f_p in [0.7, 1.4] (seed 55); V of
the sky 0. The `rfi` MS adds 100x outliers to 1 % of cells. rang's weights come
from the stage's own estimator (`rang.reweight.estimate`, `weights_of`).
"""

import json
import shutil
import sys
from pathlib import Path

import numpy as np

NANT, NINT, NSCAN, NCHAN = 16, 20, 3, 64
SEED, SIGMA0, FLUX, CHANBIN = 55, 0.5, 10.0, 16


def truth_sigma(freq):
    rng = np.random.default_rng(SEED)
    x = (freq - freq.min()) / np.ptp(freq)
    s = 1.0 + 2.0 * np.exp(-(((x - 0.15) / 0.08) ** 2)) + 0.8 * x**2  # varies about 3x
    f = rng.uniform(0.7, 1.4, NANT)
    return s, f


def make_ms(path, rfi, w1):
    from rang import core_ms_write
    from rang import core_writeback as wb

    pairs = NANT * (NANT - 1) // 2
    nrow = pairs * NINT * NSCAN
    w1.make_ms(path, nrow, NCHAN, flag="tiled", nant=NANT)
    freq = 856e6 + 856e6 / NCHAN * (np.arange(NCHAN) + 0.5)
    with core_ms_write.open_table(path / "SPECTRAL_WINDOW", readonly=False) as t:
        t.putcol("CHAN_FREQ", freq[None])
        for c in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
            t.putcol(c, np.full((1, NCHAN), 856e6 / NCHAN))
        t.putcol("TOTAL_BANDWIDTH", np.array([856e6]))
        t.putcol("REF_FREQUENCY", np.array([freq[NCHAN // 2]]))
    base = np.array([5109224.0, 2006790.0, -3239100.0])
    with core_ms_write.open_table(path / "ANTENNA", readonly=False) as t:
        t.addrows(NANT)
        t.putcol("POSITION", base + 150.0 * np.arange(NANT)[:, None] * [1, 0.5, 0.2])
        t.putcol("NAME", [f"m{a:03d}" for a in range(NANT)])
    with core_ms_write.open_table(path / "FIELD", readonly=False) as t:
        t.addrows(1)
        t.putcol("NAME", ["CAL"])
        t.putcol("PHASE_DIR", np.array([[[0.0, -1.0]]]))
    _casa_subtables(path, NINT * NSCAN)
    s, f = truth_sigma(freq)
    rng = np.random.default_rng(SEED + (1 if rfi else 0))
    with core_ms_write.open_table(path, readonly=False) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        scan = (np.arange(nrow) // pairs) // NINT
        t.putcol("SCAN_NUMBER", (scan + 1).astype(np.int32))
        t.putcol("FLAG", np.zeros((nrow, NCHAN, 4), bool))
        t.putcol("FLAG_ROW", np.zeros(nrow, bool))
        t.putcol("WEIGHT", np.ones((nrow, 4), np.float32))
        t.putcol("SIGMA", np.ones((nrow, 4), np.float32))
    sig = SIGMA0 * s[None, :] * np.sqrt(f[a1] * f[a2])[:, None]  # (row, chan) per part
    model = np.zeros((nrow, NCHAN, 4), np.complex64)
    model[..., 0] = model[..., 3] = FLUX
    noise = rng.standard_normal((nrow, NCHAN, 4)) + 1j * rng.standard_normal(
        (nrow, NCHAN, 4)
    )
    noise *= sig[..., None]
    if rfi:
        hit = rng.uniform(size=noise.shape) < 0.01
        noise[hit] *= 100.0
    with wb.WriteBack(path, stage="rw") as w:
        for col in ("MODEL_DATA", "CORRECTED_DATA", "WEIGHT_SPECTRUM"):
            w.ensure_column(col)
        w.write("MODEL_DATA", 0, model)
        w.write("CORRECTED_DATA", 0, (model + noise).astype(np.complex64))
        w.write("WEIGHT_SPECTRUM", 0, np.ones((nrow, NCHAN, 4), np.float32))
    return sig, a1, a2


def _casa_subtables(ms, nint):
    from rang import core_ms_write

    t0, t1 = 5.0e9, 5.0e9 + 8.0 * nint
    with core_ms_write.open_table(ms / "OBSERVATION", readonly=False) as t:
        t.addrows(1)
        t.putcol("TIME_RANGE", np.array([[t0, t1]]))
        t.putcol("TELESCOPE_NAME", ["MeerKAT"])
    with core_ms_write.open_table(ms / "FEED", readonly=False) as t:
        t.addrows(NANT)
        t.putcol("ANTENNA_ID", np.arange(NANT, dtype=np.int32))
        t.putcol("FEED_ID", np.zeros(NANT, np.int32))
        t.putcol("SPECTRAL_WINDOW_ID", np.full(NANT, -1, np.int32))
        t.putcol("BEAM_ID", np.full(NANT, -1, np.int32))
        t.putcol("NUM_RECEPTORS", np.full(NANT, 2, np.int32))
        t.putcol("TIME", np.full(NANT, (t0 + t1) / 2))
        t.putcol("INTERVAL", np.full(NANT, t1 - t0))
        t.putcol("POLARIZATION_TYPE", np.array([["X", "Y"]] * NANT))
        t.putcol("RECEPTOR_ANGLE", np.zeros((NANT, 2)))
        t.putcol("BEAM_OFFSET", np.zeros((NANT, 2, 2)))
        t.putcol("POSITION", np.zeros((NANT, 3)))
        t.putcol("POL_RESPONSE", np.tile(np.eye(2, dtype=complex), (NANT, 1, 1)))


def rang_weights(ms, mode, statistic, minsamp, smooth):
    from rang import core_ms, reweight

    settings = reweight.Settings(mode=mode, chanbin=CHANBIN, timebin="scan",
                                 statistic=statistic, minsamp=minsamp, smooth=smooth)  # fmt: skip
    with core_ms.open_table(ms) as t:
        nrow = t.nrows

        def read(name, rows, chans):
            return t.getcol_rows(name, rows, chans=chans)

        rows = np.arange(nrow)
        group, var = reweight.estimate(read, rows, settings, NCHAN)
    return reweight.weights_of(var, group, NCHAN, CHANBIN)


def cmd_make(out):
    import importlib.util

    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "w1", root / "examples/w1_writeback.py"
    )
    w1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w1)
    out.mkdir(parents=True, exist_ok=True)
    for name, rfi in (("clean", False), ("rfi", True)):
        ms = out / f"{name}.ms"
        if ms.exists():
            shutil.rmtree(ms)
        sig, a1, a2 = make_ms(ms, rfi, w1)
        np.savez(out / f"{name}-truth.npz", sigma=sig, a1=a1, a2=a2)
        arms = {}
        for mode in ("residual", "stokes_v"):
            for stat in ("classic", "mad"):
                arms[f"{mode}-{stat}"] = rang_weights(ms, mode, stat, 2, 0)
        np.savez_compressed(out / f"{name}-rang.npz", **arms)
    print("made", out)


def cmd_casa(out):
    import casatasks
    import casatools

    res = {}
    for name in ("clean", "rfi"):
        src, dst = out / f"{name}.ms", out / f"{name}-statwt.ms"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        casatasks.statwt(vis=str(dst), datacolumn="residual", chanbin=CHANBIN,
                         timebin="100000s", statalg="classic", minsamp=2)  # fmt: skip
        tb = casatools.table()
        tb.open(str(dst))
        ws = tb.getcol("WEIGHT_SPECTRUM")  # (corr, chan, row)
        fl = tb.getcol("FLAG")
        tb.close()
        np.savez_compressed(out / f"{name}-casa.npz", ws=np.transpose(ws, (2, 1, 0)),
                            flag=np.transpose(fl, (2, 1, 0)))  # fmt: skip
        res[name] = {"cells": int(ws.size), "flagged": int(fl.sum())}
    (out / "casa.json").write_text(json.dumps(res) + "\n")


def e_of(w, sigma2):
    """sqrt(S(w)/S(1/sigma^2)), S(w) = sum w^2 sigma^2 / (sum w)^2 over w > 0."""
    m = w > 0
    w, s2 = w[m].astype(np.float64), sigma2[m]
    s = np.sum(w**2 * s2) / np.sum(w) ** 2
    ideal = 1.0 / s2
    si = np.sum(ideal**2 * s2) / np.sum(ideal) ** 2
    return float(np.sqrt(s / si))


def cmd_score(out):
    score = {}
    for name in ("clean", "rfi"):
        t = np.load(out / f"{name}-truth.npz")
        sigma2 = (t["sigma"] ** 2)[..., None].repeat(
            4, -1
        )  # per part = per correlation variance
        rang = np.load(out / f"{name}-rang.npz")
        casa = np.load(out / f"{name}-casa.npz")
        # G1: residual-classic against statwt, cells both leave unflagged.
        r = rang["residual-classic"]
        c = casa["ws"]
        both = (r > 0) & ~casa["flag"]
        rel = np.abs(r[both] - c[both]) / c[both]
        g1 = {"cells": int(both.sum()), "max_rel": float(rel.max()),
              "median_rel": float(np.median(rel)), "ratio_median": float(np.median(r[both] / c[both])),
              "zero_equals_statwt_flags": bool(np.array_equal(r == 0, casa["flag"]))}  # fmt: skip
        g1["pass"] = bool(g1["max_rel"] <= 1e-5 and g1["zero_equals_statwt_flags"])
        arms = {}
        for k in rang.files:
            w = rang[k]
            ratio = w[w > 0] * sigma2[w > 0]
            arms[k] = {"median_ratio": float(np.median(ratio)), "e": e_of(w, sigma2),
                       "pass": bool(0.98 <= np.median(ratio) <= 1.02 and e_of(w, sigma2) <= 1.01)}  # fmt: skip
        arms["unity"] = {"e": e_of(np.ones_like(sigma2, np.float32), sigma2)}
        score[name] = {"G1": g1, "G2": arms}
    (out / "score.json").write_text(json.dumps(score, indent=1) + "\n")
    print(json.dumps(score, indent=1))


if __name__ == "__main__":
    cmd, out = sys.argv[1], Path(sys.argv[2]).resolve()
    {"make": cmd_make, "casa": cmd_casa, "score": cmd_score}[cmd](out)
