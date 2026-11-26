"""#48 measures T, G1 and Q on simulations with known noise (research/weights-48.md sections 3-5).

    python w48_sim.py make OUT        # rang venv: the MSs and rang's weights per arm
    python w48_sim.py casa OUT        # inside rang-o-casa_6.7.6.14.sif: statwt on a copy of clean.ms
    python w48_sim.py qc OUT          # QuartiCal 0.2.7 venv: robust weights on clean and rfi
    python w48_sim.py score OUT       # rang venv: score.json

#55's generator (rw_g12.py) at 256 channels: 16 antennas, 3 scans of 8 s integrations over
856-1712 MHz; sigma(p, q, nu) = sigma0 s(nu) sqrt(f_p f_q) per part, #55's s and f (seed 55);
MODEL_DATA 10 Jy on XX and YY, V of the sky 0. Cases (seed w48-<case>):
  clean            20 integrations per scan
  rfi              clean + 100x outliers in 1 % of cells (#55's)
  rfi-low          clean + 3x-5x (uniform) outliers in 2 % of cells
  short            14 integrations per scan, 8 on scan 2
  baseline-excess  clean, the 10 shortest baselines (adjacent antennas 0-1 ... 9-10) at 1.5x sigma
rang's arms: {stokes_v, residual} x {classic, mad, clipped} at the stage defaults (chanbin 16,
minsamp 200, smooth 5, fill true); G1: residual/classic with minsamp 2, smooth 0, fill false.
"""

import json
import os
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

import numpy as np

NANT, NCHAN, CHANBIN = 16, 256, 16
SEED, SIGMA0, FLUX = 55, 0.5, 10.0
CASES = {
    "clean": (20, 20, 20),
    "rfi": (20, 20, 20),
    "rfi-low": (20, 20, 20),
    "short": (14, 8, 14),
    "baseline-excess": (20, 20, 20),
}
MODES, STATS = ("stokes_v", "residual"), ("classic", "mad", "clipped")
DEFAULTS = {
    "chanbin": CHANBIN,
    "timebin": "scan",
    "minsamp": 200,
    "smooth": 5,
    "fill": True,
}
G1 = {"chanbin": CHANBIN, "timebin": "scan", "minsamp": 2, "smooth": 0, "fill": False}


def seed(case):
    return zlib.crc32(f"w48-{case}".encode())


def truth_sigma(freq):
    rng = np.random.default_rng(SEED)
    x = (freq - freq.min()) / np.ptp(freq)
    s = 1.0 + 2.0 * np.exp(-(((x - 0.15) / 0.08) ** 2)) + 0.8 * x**2
    f = rng.uniform(0.7, 1.4, NANT)
    return s, f


def _w1():
    import importlib.util

    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "w1", root / "examples/w1_writeback.py"
    )
    w1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w1)
    return w1


def make_ms(path, case, w1):
    from rang import core_ms_write
    from rang import core_writeback as wb

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rw-scripts"))
    import rw_g12

    rw_g12.NANT = NANT
    nints = CASES[case]
    pairs = NANT * (NANT - 1) // 2
    nrow = pairs * sum(nints)
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
    rw_g12._casa_subtables(path, sum(nints))
    s, f = truth_sigma(freq)
    rng = np.random.default_rng(seed(case))
    with core_ms_write.open_table(path, readonly=False) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        integ = np.arange(nrow) // pairs
        edges = np.cumsum(nints)
        scan = np.searchsorted(edges, integ, side="right")
        t.putcol("SCAN_NUMBER", (scan + 1).astype(np.int32))
        t.putcol("FLAG", np.zeros((nrow, NCHAN, 4), bool))
        t.putcol("FLAG_ROW", np.zeros(nrow, bool))
        t.putcol("WEIGHT", np.ones((nrow, 4), np.float32))
        t.putcol("SIGMA", np.ones((nrow, 4), np.float32))
    excess = np.ones(nrow)
    if case == "baseline-excess":
        lo, hi = np.minimum(a1, a2), np.maximum(a1, a2)
        excess[(hi == lo + 1) & (lo < 10)] = 1.5
    sig = SIGMA0 * s[None, :] * (np.sqrt(f[a1] * f[a2]) * excess)[:, None]
    model = np.zeros((nrow, NCHAN, 4), np.complex64)
    model[..., 0] = model[..., 3] = FLUX
    noise = rng.standard_normal((nrow, NCHAN, 4)) + 1j * rng.standard_normal(
        (nrow, NCHAN, 4)
    )
    noise *= sig[..., None]
    if case == "rfi":
        noise[rng.uniform(size=noise.shape) < 0.01] *= 100.0
    if case == "rfi-low":
        hit = rng.uniform(size=noise.shape) < 0.02
        noise[hit] *= rng.uniform(3.0, 5.0, int(hit.sum()))
    with wb.WriteBack(path, stage="w48") as w:
        for col in ("MODEL_DATA", "CORRECTED_DATA", "WEIGHT_SPECTRUM"):
            w.ensure_column(col)
        w.write("MODEL_DATA", 0, model)
        w.write("CORRECTED_DATA", 0, (model + noise).astype(np.complex64))
        w.write("WEIGHT_SPECTRUM", 0, np.ones((nrow, NCHAN, 4), np.float32))
    return sig, a1, a2, scan


def rang_weights(ms, mode, statistic, opts):
    from rang import core_ms, reweight

    settings = reweight.Settings(mode=mode, statistic=statistic, **opts)
    settings.check()
    with core_ms.open_table(ms) as t:
        nrow = t.nrows

        def read(name, rows, chans):
            return t.getcol_rows(name, rows, chans=chans)

        gid, var, filled = reweight.estimate_rows(
            read, np.arange(nrow), settings, NCHAN
        )
    return reweight.weights_of(var, gid, NCHAN, CHANBIN), filled


def cmd_make(out):
    w1 = _w1()
    out.mkdir(parents=True, exist_ok=True)
    rec = {}
    for case in CASES:
        ms = out / f"{case}.ms"
        if ms.exists():
            shutil.rmtree(ms)
        sig, a1, a2, scan = make_ms(ms, case, w1)
        np.savez(out / f"{case}-truth.npz", sigma=sig, a1=a1, a2=a2, scan=scan)
        arms, rec[case] = {}, {}
        for mode in MODES:
            for stat in STATS:
                w, filled = rang_weights(ms, mode, stat, DEFAULTS)
                arms[f"{mode}-{stat}"] = w
                rec[case][f"{mode}-{stat}"] = filled
        if case == "clean":
            arms["g1-residual-classic"], _ = rang_weights(ms, "residual", "classic", G1)
        np.savez_compressed(out / f"{case}-rang.npz", **arms)
    (out / "make.json").write_text(json.dumps({"filled_blocks": rec}, indent=1) + "\n")
    print("made", out)


def cmd_casa(out):
    import casatasks
    import casatools

    src, dst = out / "clean.ms", out / "clean-statwt.ms"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    casatasks.statwt(vis=str(dst), datacolumn="residual", chanbin=CHANBIN,
                     timebin="100000s", statalg="classic", minsamp=G1["minsamp"])  # fmt: skip
    tb = casatools.table()
    tb.open(str(dst))
    ws, fl, wt = tb.getcol("WEIGHT_SPECTRUM"), tb.getcol("FLAG"), tb.getcol("WEIGHT")
    tb.close()
    np.savez_compressed(out / "clean-casa.npz", ws=np.transpose(ws, (2, 1, 0)),
                        flag=np.transpose(fl, (2, 1, 0)), weight=wt.T)  # fmt: skip


QC_YAML = """input_ms:
  path: {ms}
  data_column: CORRECTED_DATA
  weight_column: WEIGHT_SPECTRUM
  time_chunk: '0'
  freq_chunk: {chanbin}
  group_by: [SCAN_NUMBER, FIELD_ID, DATA_DESC_ID]
input_model:
  recipe: MODEL_DATA
output:
  gain_directory: {gains}
  log_directory: {logs}
  overwrite: true
  products: [weight]
  columns: [QC_WEIGHT]
mad_flags:
  enable: false
solver:
  terms: [G]
  iter_recipe: [25, 25]
  robust: true
  threads: 4
dask:
  threads: 4
G:
  type: diag_complex
  time_interval: '0'
  freq_interval: '0'
"""


def cmd_qc(out):
    """QuartiCal on copies of clean.ms and rfi.ms (the copies take QC_WEIGHT); run with the
    QuartiCal venv's python, goquartical beside it."""
    exe = Path(sys.executable).with_name("goquartical")
    res = {}
    for case in ("clean", "rfi"):
        src, dst = out / f"{case}.ms", out / f"{case}-qc.ms"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        cfg = out / f"qc-{case}.yaml"
        cfg.write_text(QC_YAML.format(ms=dst, chanbin=CHANBIN, gains=out / f"qc-{case}-gains",
                                      logs=out / f"qc-{case}-logs"))  # fmt: skip
        rc = subprocess.run([str(exe), str(cfg)], cwd=out).returncode
        res[case] = {"rc": rc}
        if rc:
            continue
        from casacore.tables import table

        with table(str(dst), ack=False) as t:
            np.savez_compressed(out / f"{case}-qc.npz", w=t.getcol("QC_WEIGHT"),
                                flag=t.getcol("FLAG"))  # fmt: skip
    (out / "qc.json").write_text(json.dumps(res) + "\n")


def e_of(w, sigma2):
    """sqrt(S(w)/S(1/sigma^2)), S(w) = sum w^2 sigma^2 / (sum w)^2 over w > 0."""
    m = w > 0
    w, s2 = w[m].astype(np.float64), sigma2[m]
    s = np.sum(w**2 * s2) / np.sum(w) ** 2
    ideal = 1.0 / s2
    return float(np.sqrt(s / (np.sum(ideal**2 * s2) / np.sum(ideal) ** 2)))


def bounds(case):
    """Section 5's frozen T bounds: (median low, high, e above the floor), None for reported."""
    return {"clean": (0.98, 1.02, 0.003), "rfi": (0.98, 1.02, 0.005), "rfi-low": None,
            "short": (None, None, 0.01), "baseline-excess": (0.98, 1.02, 0.003)}[case]  # fmt: skip


def rfi_low_bias():
    """The expected upward bias of `clipped` on rfi-low: per part variance of the mixture
    (98 % sigma^2, 2 % k^2 sigma^2, k ~ U(3, 5)), each component truncated at the clip
    u <= 9 (complex amplitude 3 sigma) of the fitted variance, solved by fixed point."""
    from math import exp

    ks = np.linspace(3.0, 5.0, 2001)
    k9 = 1 - 9 * exp(-9) / (1 - exp(-9))

    def trunc_mean(s2, c):  # E[u 1(u <= c)] for u ~ s2 Exp(1), in clean-variance units
        a = c / s2
        return s2 * (1 - (1 + a) * exp(-a))

    def trunc_p(s2, c):
        return 1 - exp(-c / s2)

    v = 1.0
    for _ in range(200):
        c = 9.0 * v
        num = 0.98 * trunc_mean(1.0, c) + 0.02 * np.mean(
            [trunc_mean(k * k, c) for k in ks]
        )
        den = 0.98 * trunc_p(1.0, c) + 0.02 * np.mean([trunc_p(k * k, c) for k in ks])
        v = num / den / k9
    return float(v)


def cmd_score(out):
    score = {
        "bounds": {k: bounds(k) for k in CASES},
        "rfi_low_expected_bias": rfi_low_bias(),
    }
    for case in CASES:
        t = np.load(out / f"{case}-truth.npz")
        sigma2 = np.repeat((t["sigma"] ** 2)[..., None], 4, -1)
        rang = np.load(out / f"{case}-rang.npz")
        nb = NCHAN // CHANBIN
        blk = sigma2.reshape(sigma2.shape[0], nb, CHANBIN, 4).mean(2)
        floor = e_of((1 / np.repeat(blk, CHANBIN, axis=1)).astype(np.float32), sigma2)
        arms = {
            "block_ideal": {"e": floor},
            "unity": {"e": e_of(np.ones_like(sigma2, np.float32), sigma2)},
        }
        b = bounds(case)
        for k in rang.files:
            if k.startswith("g1-"):
                continue
            w = rang[k]
            ratio = w[w > 0] * sigma2[w > 0]
            e = e_of(w, sigma2)
            a = {"median_ratio": float(np.median(ratio)), "e": e, "e_minus_floor": e - floor,
                 "unflagged_cells_at_weight_0": int((w == 0).sum())}  # fmt: skip
            if b is not None:
                lo, hi, de = b
                ok = e <= floor + de
                if lo is not None:
                    ok &= lo <= a["median_ratio"] <= hi
                if case == "short":
                    ok &= a["unflagged_cells_at_weight_0"] == 0
                a["pass"] = bool(ok)
            arms[k] = a
        qc = out / f"{case}-qc.npz"
        if qc.exists():
            q = np.load(qc)
            w = (
                np.transpose(q["w"], (0, 1, 2))
                if q["w"].shape == sigma2.shape
                else q["w"]
            )
            m = w > 0
            scale = np.median(w[m] * sigma2[m])
            arms["quartical-robust"] = {"median_ratio_raw": float(scale), "e": e_of(w, sigma2),
                                        "e_minus_floor": e_of(w, sigma2) - floor}  # fmt: skip
        score[case] = arms
    casa = out / "clean-casa.npz"
    if casa.exists():
        c = np.load(casa)
        r = np.load(out / "clean-rang.npz")["g1-residual-classic"]
        both = (r > 0) & ~c["flag"]
        rel = np.abs(r[both] - c["ws"][both]) / c["ws"][both]
        score["G1"] = {"cells": int(both.sum()), "max_rel": float(rel.max()),
                       "pass": bool(rel.max() <= 1e-5)}  # fmt: skip
    gated = [a["pass"] for k in CASES if bounds(k) for n, a in score[k].items()
             if n.endswith("-clipped")]  # fmt: skip
    score["T_clipped_pass"] = bool(all(gated))
    (out / "score.json").write_text(json.dumps(score, indent=1) + "\n")
    print(json.dumps(score, indent=1))


if __name__ == "__main__":
    os.environ.setdefault("RAYON_NUM_THREADS", "4")
    cmd, out = sys.argv[1], Path(sys.argv[2]).resolve()
    {"make": cmd_make, "casa": cmd_casa, "qc": cmd_qc, "score": cmd_score}[cmd](out)
