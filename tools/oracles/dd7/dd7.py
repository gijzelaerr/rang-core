# SPDX-License-Identifier: MIT
"""DD7: which property of the real ESO 137-006 data the DD5/DD6 simulations
lack (research/dd7-cause.md).

    python tools/oracles/dd7/dd7.py setup ROOT            # copies, real subset (G1)
    python tools/oracles/dd7/dd7.py compose ROOT          # RM and the whole deep model (G2)
    python tools/oracles/dd7/dd7.py prep ROOT             # B's signal and noise (G3)
    python tools/oracles/dd7/dd7.py grid RUN TI MODEL OUT.json [--free] [--cap N]
    python tools/oracles/dd7/dd7.py resid ROOT            # R64 from the real MF-64 point
    python tools/oracles/dd7/dd7.py stats ROOT            # stage 1
    python tools/oracles/dd7/dd7.py build ROOT ARM        # T0 T1 T2 T3 T4 TSa TSb I0 R1 R1c R3

ROOT is the run root (D:/rang/outputs/dd7-20261125). The deep clean itself
is DD6's (`dd6.py deep ROOT/real ROOT/deep-real 8`).
"""

import importlib.util
import json
import math
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DD5_ROOT = Path("D:/rang/outputs/dd5-20261124")
BAD = Path("D:/rang/outputs/20261103-gemclean-heldout/real/badbaselines.json")
SHORT_M = 400.0  # gemclean-heldout section 5
LENGTH_BINS = [0, 100, 200, 400, 1000, 2000, 4000, 1e9]  # metres, section 5 S1a
SEEDS = {"scramble": 7701, "control": 7702}
CONTROL_TOL = 0.10  # R1c: weight share within 10 % of R1's
G2 = {"RM": 63.999251123985815, "RM_d0": 60.5182070217989, "deep": 65.7713090157963}
G4 = {"real-P-4": [1.0, 0.0, 0.0, 0.0],
      "real-MF-4": [0.15208732851453016, 0.0658011212747123, 0.042195337857775156, 0.010537251409913921],
      "real-MF-64": [0.875, 0.79375, 0.7541666666666667, 0.7515657620041754]}  # fmt: skip
G4_P_FLAGS = 1876


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd6 = _load("dd6", HERE.parent / "dd6" / "dd6.py")
dd5, dd4, dd2 = dd6.dd5, dd6.dd4, dd6.dd2


# -- pure helpers (unit-tested in tests/test_dd7.py) ----------------------------------


def baseline_mask(a1, a2, pairs):
    """Rows whose (a1, a2) baseline is in `pairs` (either order)."""
    key = np.minimum(a1, a2).astype(np.int64) * 100000 + np.maximum(a1, a2)
    sel = np.array([min(p, q) * 100000 + max(p, q) for p, q in pairs], np.int64)
    return np.isin(key, sel)


def phase_scramble(r, rng):
    """Each cell's modulus kept, its phase replaced by a uniform random one."""
    phi = rng.uniform(0.0, 2.0 * math.pi, r.shape)
    return (np.abs(r) * np.exp(1j * phi)).astype(r.dtype)


def linear_term(z, ok):
    """Per (row, hand), the least-squares linear term across channels of z
    over the cells `ok` (z, ok: (rows, chans, hands)), centred on the
    unflagged channels' mean index, so it is orthogonal to the constant
    term. Returns (linear part on ok cells, constant part on ok cells)."""
    x = np.arange(z.shape[1], dtype=np.float64)[None, :, None]
    m = ok.astype(np.float64)
    n = m.sum(1, keepdims=True)
    nn = np.where(n > 0, n, 1.0)
    xbar = (m * x).sum(1, keepdims=True) / nn
    xc = (x - xbar) * m
    sxx = (xc * xc).sum(1, keepdims=True)
    zm = np.where(ok, z, 0)
    b = (xc * zm).sum(1, keepdims=True) / np.where(sxx > 0, sxx, 1.0)
    b = np.where(n >= 2, b, 0)
    a = zm.sum(1, keepdims=True) / nn
    return b * xc, np.where(ok, a, 0)


def matched_control(
    bl_weight, exclude, count, target, rng, tol=CONTROL_TOL, draws=20000
):
    """`count` baseline indices outside `exclude`, drawn at random until
    their weight share is within `tol` (relative) of `target`."""
    pool = np.flatnonzero(~exclude)
    total = bl_weight.sum()
    for i in range(draws):
        pick = rng.choice(pool, size=count, replace=False)
        share = bl_weight[pick].sum() / total
        if abs(share / target - 1.0) <= tol:
            return np.sort(pick), float(share), i + 1
    raise RuntimeError("no matched control within tolerance")


def ranks(v):
    v = np.asarray(v, float)
    order = np.argsort(v, kind="mergesort")
    r = np.empty(len(v))
    r[order] = np.arange(len(v))
    # average ties
    for val in np.unique(v):
        sel = v == val
        if sel.sum() > 1:
            r[sel] = r[sel].mean()
    return r


def spearman(a, b):
    ra, rb = ranks(a), ranks(b)
    ra, rb = ra - ra.mean(), rb - rb.mean()
    den = math.sqrt((ra * ra).sum() * (rb * rb).sum())
    return float((ra * rb).sum() / den) if den > 0 else float("nan")


# -- io -------------------------------------------------------------------------------


def read2(
    ms,
    cols=(
        "DATA",
        "WEIGHT_SPECTRUM",
        "FLAG",
        "FLAG_ROW",
        "ANTENNA1",
        "ANTENNA2",
        "TIME",
    ),
):
    """The subset's columns as stored (two correlations)."""
    from rang import core_ms

    t = core_ms.open_table(str(ms))
    c = {k: t.getcol(k) for k in cols}
    t.close()
    return c


def ant_positions(ms):
    from rang import core_ms

    ant = core_ms.open_table(str(Path(ms) / "ANTENNA"))
    pos = np.asarray(ant.getcol("POSITION"), float)
    ant.close()
    return pos


def put(ms, **cols):
    from rang import core_ms_write

    t = core_ms_write.open_table(str(ms), readonly=False)
    for k, v in cols.items():
        t.putcol(k, v)
    t.close()


def write_json(path, rec):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1), flush=True)


SMALL = ("header.json", "facets.reg")


def copy_run(src, dst, ms_src, extra=()):
    """A run directory: the small files, `extra`, a copy of the MS, setup.json
    pointing at it."""
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=False)
    for f in (*SMALL, *extra):
        shutil.copy(src / f, dst / f)
    ms = dst / ("sim.ms" if "sim" in Path(ms_src).name else "sub.ms")
    shutil.copytree(ms_src, ms)
    st = json.loads((src / "setup.json").read_text())
    st["subms"] = str(ms)
    st["dd7"] = {"from": str(src)}
    (dst / "setup.json").write_text(json.dumps(st, indent=1))
    return ms


# -- setup ----------------------------------------------------------------------------


def setup(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    for name, extra in (("a", ()), ("b", ("sky.npy", "truth.npz", "model0.npy"))):
        src = DD5_ROOT / name
        copy_run(src, root / name, src / "sim.ms", extra)
        st = json.loads((root / name / "setup.json").read_text())
        st.pop("dd7", None)
        (root / name / "setup.json").write_text(json.dumps(st, indent=1))
    for f in ("psf.npy", "model0.npy"):  # realms copies these from its template
        shutil.copy(DD5_ROOT / "a" / f, root / "a" / f)
    dd6.real_ms(root / "real", template=root / "a")
    print(json.dumps({"setup_seconds": time.perf_counter() - t0}))


def compose(root):
    root = Path(root)
    idx = dd6.facet_idx(root / "real")
    deep = np.load(root / "deep-real" / "deep.npy")
    m0c = np.load(root / "b" / "sky.npy")
    rm = dd6.compose(idx, m0c, deep)
    (root / "models").mkdir(exist_ok=True)
    np.save(root / "models" / "RM.npy", rm)
    np.save(root / "models" / "DEEP.npy", deep)
    per = {name: [float(m[idx == f].sum()) for f in range(4)]
           for name, m in (("DEEP", deep), ("RM", rm), ("M0c", m0c))}  # fmt: skip
    rec = {"RM": float(rm.sum()), "RM_d0": float(rm[idx == 0].sum()), "deep": float(deep.sum()),
           "per_facet_flux": per}  # fmt: skip
    rec["G2_pass"] = bool(abs(rec["RM"] - G2["RM"]) <= 1e-3 and abs(rec["RM_d0"] - G2["RM_d0"]) <= 1e-3
                          and abs(rec["deep"] - G2["deep"]) <= 1e-3)  # fmt: skip
    write_json(root / "models" / "G2.json", rec)
    if not rec["G2_pass"]:
        raise SystemExit("G2 failed: setup outcome")


def regen_noise(w2, k):
    """dd5.simulate's noise, drawn again: seed 5501, N(0, k/w) per part."""
    w = w2.astype(np.float64)
    sd = np.where(w > 0, np.sqrt(k / np.where(w > 0, w, 1.0)), 0.0)
    rng = np.random.default_rng(dd5.SEEDS["noise"])
    n = rng.standard_normal(w.shape + (2,))
    return (sd * (n[..., 0] + 1j * n[..., 1])).astype(np.complex64)


def prep(root):
    """B's noise regenerated and its signal DATA - n, checked against the
    noise-free predict (G3)."""
    root = Path(root)
    run = root / "b"
    t0 = time.perf_counter()
    st = json.loads((run / "setup.json").read_text())
    k = st["dd5"]["k"]
    c2 = read2(st["subms"], ("DATA", "WEIGHT_SPECTRUM"))
    n = regen_noise(c2["WEIGHT_SPECTRUM"], k)
    signal = (c2["DATA"] - n).astype(np.complex64)
    del c2
    ctx = dd4.context(run)
    c = ctx["c"]
    g = np.load(run / "truth.npz")["gains"]
    block4 = dd2.interval_axes(c, dd5.BLOCK)[2]
    models = dd4.facet_models(ctx, np.load(run / "sky.npy"))
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    pred = np.zeros(signal.shape, np.complex64)
    for f in range(ctx["ndir"]):
        for h, corr in ((0, 0), (1, 3)):
            gp, gq = g[block4, a1, f, h], g[block4, a2, f, h]
            pred[..., h] += (
                gp[:, None] * models[:, :, f, corr] * np.conj(gq[:, None])
            ).astype(np.complex64)
    del models
    diff = float(np.abs(pred - signal).max())
    np.save(run / "signal.npy", signal)
    np.save(run / "noise.npy", n)
    rec = {"k": k, "max_abs_signal_minus_predict_jy": diff, "G3_pass": bool(diff <= 1e-3),
           "seconds": time.perf_counter() - t0}  # fmt: skip
    write_json(run / "prep.json", rec)
    if not rec["G3_pass"]:
        raise SystemExit("G3 failed: setup outcome")


# -- the grid point -------------------------------------------------------------------


def grid(run, ti, model, out, free=False, cap=500):
    dd5.grid_point(
        run, "diag_complex", ti, model, out, cap=cap, pinned=dd6.pinned_for(free)
    )


def g4_check(root):
    """G4 against DD6, read after the three real points."""
    root = Path(root)
    rec = {}
    ok = True
    for name, ref in G4.items():
        r = json.loads((root / "grid" / f"{name}.json").read_text())
        d = [abs(a - b) for a, b in zip(r["perdir_converged"], ref, strict=True)]
        rec[name] = {
            "perdir": r["perdir_converged"],
            "max_diff": max(d),
            "flagged_offaxis": r["flagged_offaxis"],
        }
        ok &= max(d) <= 0.01
    rec["P_flags_within_1pc"] = (
        abs(rec["real-P-4"]["flagged_offaxis"] - G4_P_FLAGS) <= 0.01 * G4_P_FLAGS
    )
    rec["G4_pass"] = bool(ok and rec["P_flags_within_1pc"])
    write_json(root / "grid" / "G4.json", rec)
    if not rec["G4_pass"]:
        raise SystemExit("G4 failed: setup outcome")


# -- the real residual ----------------------------------------------------------------


def solved(npz, ti_shape=None):
    z = np.load(npz)
    g = np.array(z["gains"])
    g[np.asarray(z["flags"]) != 0] = 1.0
    return g  # (t, f, ant, dir, 2)


def residual(ctx, model, gains):
    """DATA - sum_f G_f V_f G_f^H (two hands, complex64)."""
    c = ctx["c"]
    models = dd4.facet_models(ctx, model)
    a1, a2, block = c["ANTENNA1"], c["ANTENNA2"], ctx["block"]
    r = np.stack([c["DATA"][..., 0], c["DATA"][..., 3]], -1).astype(np.complex64)
    for f in range(ctx["ndir"]):
        for h, corr in ((0, 0), (1, 3)):
            gp, gq = gains[block, 0, a1, f, h], gains[block, 0, a2, f, h]
            r[..., h] -= (
                gp[:, None] * models[:, :, f, corr] * np.conj(gq[:, None])
            ).astype(np.complex64)
    return r


def resid(root):
    root = Path(root)
    t0 = time.perf_counter()
    ctx = dd4.context(root / "real", ti=64)
    g = solved(root / "grid" / "real-MF-64.npz")
    r = residual(ctx, np.load(root / "models" / "RM.npy"), g)
    np.save(root / "real" / "R64.npy", r)
    print(
        json.dumps(
            {"R64": str(root / "real" / "R64.npy"), "seconds": time.perf_counter() - t0}
        )
    )


# -- stage 1 --------------------------------------------------------------------------


def lengths(c, pos):
    return np.linalg.norm(pos[c["ANTENNA1"]] - pos[c["ANTENNA2"]], axis=1)


def bad_pairs():
    return [(b["a1"], b["a2"]) for b in json.loads(BAD.read_text())["list"]]


def stats(root):
    root = Path(root)
    t0 = time.perf_counter()
    ms = json.loads((root / "real" / "setup.json").read_text())["subms"]
    c = read2(
        ms, ("WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2", "TIME")
    )
    k = json.loads((root / "b" / "setup.json").read_text())["dd5"]["k"]
    r = np.load(root / "real" / "R64.npy")
    w = c["WEIGHT_SPECTRUM"].astype(np.float64)
    ok = ~(c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]) & (w > 0)
    z = r * np.sqrt(w / k)
    chi = np.where(ok, np.abs(z) ** 2 / 2.0, 0.0)  # per cell, mean 1 for k/w noise
    exc = np.where(ok, chi - 1.0, 0.0)
    pos = ant_positions(ms)
    L = lengths(c, pos)
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    bad = baseline_mask(a1, a2, bad_pairs())
    short = L < SHORT_M
    rec = {"k": k, "cells": int(ok.sum())}
    row_chi, row_n = chi.sum((1, 2)), ok.sum((1, 2))
    row_exc = exc.sum((1, 2))
    tot_exc = row_exc.sum()
    rec["chi2_all"] = float(row_chi.sum() / row_n.sum())
    rec["excess_share_bad"] = float(row_exc[bad].sum() / tot_exc)
    rec["excess_share_short"] = float(row_exc[short].sum() / tot_exc)
    rec["weight_share_bad"] = float((w * ok)[bad].sum() / (w * ok).sum())
    rec["weight_share_short"] = float((w * ok)[short].sum() / (w * ok).sum())
    rec["chi2_bad"] = float(row_chi[bad].sum() / row_n[bad].sum())
    rec["chi2_not_bad"] = float(row_chi[~bad].sum() / row_n[~bad].sum())
    lb = np.digitize(L, LENGTH_BINS) - 1
    rec["chi2_by_length"] = {f"{LENGTH_BINS[i]}-{LENGTH_BINS[i + 1]:g}": float(row_chi[lb == i].sum() / max(row_n[lb == i].sum(), 1))
                             for i in range(len(LENGTH_BINS) - 1)}  # fmt: skip
    rec["excess_share_by_length"] = {f"{LENGTH_BINS[i]}-{LENGTH_BINS[i + 1]:g}": float(row_exc[lb == i].sum() / tot_exc)
                                     for i in range(len(LENGTH_BINS) - 1)}  # fmt: skip
    nant = int(max(a1.max(), a2.max())) + 1
    ac, an = np.zeros(nant), np.zeros(nant)
    for a in (a1, a2):
        np.add.at(ac, a, row_chi)
        np.add.at(an, a, row_n)
    chi_ant = ac / np.maximum(an, 1)
    rec["chi2_by_antenna"] = chi_ant.tolist()
    rec["chi2_antenna_top5"] = [
        [int(i), float(chi_ant[i])] for i in np.argsort(chi_ant)[::-1][:5]
    ]
    _, tindex = np.unique(c["TIME"], return_inverse=True)
    blk = tindex // 4
    nb = int(blk.max()) + 1
    bc, bn = np.zeros(nb), np.zeros(nb)
    np.add.at(bc, blk, row_chi)
    np.add.at(bn, blk, row_n)
    chi_int = bc / np.maximum(bn, 1)
    rec["chi2_by_interval4_p10_p50_p90"] = np.percentile(chi_int, [10, 50, 90]).tolist()
    rec["chi2_by_channel"] = (chi.sum((0, 2)) / np.maximum(ok.sum((0, 2)), 1)).tolist()
    # S1b: k from adjacent-channel differences, per hand, weight decile, length bin
    parts, wh, hs, ls = [], [], [], []
    for h in (0, 1):
        o = ok[:, :-1, h] & ok[:, 1:, h]
        d = (r[:, :-1, h] - r[:, 1:, h])[o]
        hw = 1.0 / (1.0 / w[:, :-1, h][o] + 1.0 / w[:, 1:, h][o])
        s = np.sqrt(hw)
        rows = np.broadcast_to(np.arange(len(L))[:, None], o.shape)[o]
        for v in (d.real * s, d.imag * s):
            parts.append(v)
            wh.append(hw)
            hs.append(np.full(v.shape, h, np.int8))
            ls.append(lb[rows].astype(np.int8))
    v, wh, hs, ls = map(np.concatenate, (parts, wh, hs, ls))
    del parts

    def kk(x):
        return (
            float((1.4826 * np.median(np.abs(x - np.median(x)))) ** 2)
            if x.size
            else float("nan")
        )

    rec["k_robust_all"] = kk(v)
    rec["k_variance_all"] = float(np.mean(v * v))
    rec["k_by_hand"] = [kk(v[hs == h]) for h in (0, 1)]
    rec["k_variance_by_hand"] = [float(np.mean(v[hs == h] ** 2)) for h in (0, 1)]
    dec = np.percentile(wh, np.arange(10, 100, 10))
    db = np.digitize(wh, dec)
    rec["k_by_weight_decile"] = [kk(v[db == i]) for i in range(10)]
    rec["k_by_length"] = {
        f"{LENGTH_BINS[i]}-{LENGTH_BINS[i + 1]:g}": kk(v[ls == i])
        for i in range(len(LENGTH_BINS) - 1)
    }
    rec["k_variance_by_length"] = {
        f"{LENGTH_BINS[i]}-{LENGTH_BINS[i + 1]:g}": float(np.mean(v[ls == i] ** 2))
        for i in range(len(LENGTH_BINS) - 1)
    }
    sig = math.sqrt(rec["k_robust_all"])
    rec["tail_fraction_gt5sigma"] = float((np.abs(v) > 5 * sig).mean())
    rec["tail_fraction_gaussian"] = 5.733e-7
    del v, wh, hs, ls
    # S1c: linear (and constant) term across the band, in z units
    lin, const = linear_term(z, ok)
    p_lin = (np.abs(lin) ** 2).sum((1,))  # (rows, hands)
    p_all = np.where(ok, np.abs(z) ** 2, 0).sum(1)
    p_const = (np.abs(const) ** 2).sum(1)
    nrh = ok.sum(1)
    use = nrh >= 2
    rec["linear_share"] = float(p_lin[use].sum() / p_all[use].sum())
    rec["linear_share_expected_noise"] = float(use.sum() / nrh[use].sum())
    rec["constant_share"] = float(p_const[use].sum() / p_all[use].sum())
    rec["linear_share_by_length"] = {f"{LENGTH_BINS[i]}-{LENGTH_BINS[i + 1]:g}": float(p_lin[(lb == i)[:, None] & use].sum() / max(p_all[(lb == i)[:, None] & use].sum(), 1e-30))
                                     for i in range(len(LENGTH_BINS) - 1)}  # fmt: skip
    del lin, const, z
    # S1d: model flux per facet
    rec["model_flux_per_facet"] = json.loads((root / "models" / "G2.json").read_text())[
        "per_facet_flux"
    ]
    # S1e: per-interval convergence of MF-4 against chi2 and flagged fraction
    zf = np.load(root / "grid" / "real-MF-4.npz")
    conv, fl = np.asarray(zf["converged"]), np.asarray(zf["flags"])
    okc = fl == 0
    frac_int = conv[:, 0, :, 1:].sum((1, 2)) / np.maximum(
        okc[:, 0, :, 1:].sum((1, 2)), 1
    )
    flag_int = np.zeros(nb)
    cells = np.zeros(nb)
    np.add.at(flag_int, blk, (~ok).sum((1, 2)))
    np.add.at(cells, blk, np.full(len(blk), ok.shape[1] * ok.shape[2]))
    flag_int /= cells
    rec["interval_offaxis_fraction_p10_p50_p90"] = np.percentile(
        frac_int, [10, 50, 90]
    ).tolist()
    rec["spearman_fraction_vs_chi2"] = spearman(frac_int, chi_int)
    rec["spearman_fraction_vs_flagged"] = spearman(frac_int, flag_int)
    # S1f: d0's gain error in MF-4
    g = np.asarray(zf["gains"])[:, 0, :, 0, :]  # (t, ant, hand)
    f0 = fl[:, 0, :, 0][..., None].repeat(2, -1) != 0
    gm = np.where(f0, 0, g)
    ref = gm.sum(1, keepdims=True)
    ref = ref / np.where(np.abs(ref) > 0, np.abs(ref), 1)
    ph = np.angle(g * np.conj(ref))
    amp = np.abs(g)
    good = ~f0
    rec["d0_phase_spread_rad"] = float(np.std(ph[good]))
    rec["d0_amp_p10_p50_p90"] = np.percentile(amp[good], [10, 50, 90]).tolist()
    phm = np.where(good, ph, np.nan)
    static = np.nanmean(phm, axis=0)  # (ant, hand)
    rec["d0_phase_static_spread_rad"] = float(np.nanstd(static))
    rec["d0_phase_timevar_median_rad"] = float(
        np.nanmedian(np.nanstd(phm - static[None], axis=0))
    )
    step = np.abs(np.angle(np.exp(1j * (phm[1:] - phm[:-1]))))
    rec["d0_phase_step_median_rad"] = float(np.nanmedian(step))
    rec["seconds"] = time.perf_counter() - t0
    write_json(root / "stats.json", rec)


# -- stage 2 builds -------------------------------------------------------------------


def build(root, arm):
    root = Path(root)
    t0 = time.perf_counter()
    rec = {"arm": arm}
    if arm in ("T0", "T1", "T2", "T3", "T4", "TSa", "TSb", "I0"):
        base = root / "b"
        extra = ("truth.npz", "sky.npy")
        st = json.loads((base / "setup.json").read_text())
        ms = copy_run(base, root / arm, st["subms"], extra)
        c = read2(ms, ("WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2"))
        w = c["WEIGHT_SPECTRUM"].astype(np.float64)
        ok = ~(c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]) & (
            w > 0
        )
        signal = np.load(base / "signal.npy")
        n = np.load(base / "noise.npy")
        k = st["dd5"]["k"]
        if arm == "I0":
            data = (signal + n).astype(np.complex64)
            ctx = dd4.context(root / arm, ti=4)
            cc = ctx["c"]
            sky = np.load(base / "sky.npy")
            from rang import core_wgridder

            v0 = core_wgridder.dirty2vis(
                uvw=cc["UVW"], freq=cc["freq"],
                dirty=np.ascontiguousarray(np.where(ctx["idx"] == 0, sky, 0.0).T),
                pixsize_x=dd4.DELTA, pixsize_y=dd4.DELTA, epsilon=dd4.EPS, flip_v=True, flip_w=True,
            )  # fmt: skip
            g0 = solved(root / "grid" / "real-MF-4.npz")[
                :, 0, :, 0, :
            ]  # (113, ant, hand)
            tr = dict(np.load(base / "truth.npz"))
            assert tr["gains"].shape[0] == g0.shape[0], (tr["gains"].shape, g0.shape)
            block4 = dd2.interval_axes(cc, dd5.BLOCK)[2]
            a1, a2 = cc["ANTENNA1"], cc["ANTENNA2"]
            for h in (0, 1):
                gg = g0[block4, a1, h] * np.conj(g0[block4, a2, h])
                data[..., h] += ((gg[:, None] - 1.0) * v0).astype(np.complex64)
            tr["gains"] = tr["gains"].copy()
            tr["gains"][:, :, 0, :] = g0
            np.savez(root / arm / "truth.npz", **tr)
            rec["d0_truth"] = "real MF-4 d0 gains (flagged cells 1)"
        else:
            r = np.load(root / "real" / "R64.npy")
            a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
            if arm == "T0":
                x = r
            elif arm in ("T1", "T4"):
                bad = baseline_mask(a1, a2, bad_pairs())
                sel = bad if arm == "T1" else ~bad
                x = np.where(sel[:, None, None], r, n)
                rec["rows_from_R64"] = int(sel.sum())
            elif arm == "T2":
                sel = lengths(c, ant_positions(ms)) < SHORT_M
                x = np.where(sel[:, None, None], r, n)
                rec["rows_from_R64"] = int(sel.sum())
            elif arm == "T3":
                x = phase_scramble(r, np.random.default_rng(SEEDS["scramble"]))
            else:  # TSa, TSb
                s = np.sqrt(k / np.where(w > 0, w, 1.0))
                z = r * np.where(w > 0, 1.0 / s, 0.0)
                lin, _ = linear_term(z, ok)
                rlin = (lin * s).astype(np.complex64)
                x = (r - rlin) if arm == "TSa" else (n + rlin)
                del z, lin
            data = np.where(ok, signal + x, signal + n).astype(np.complex64)
        put(ms, DATA=data)
    elif arm in ("R1", "R1c", "R3"):
        base = root / "real"
        st = json.loads((base / "setup.json").read_text())
        ms = copy_run(base, root / arm, st["subms"])
        c = read2(ms, ("WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2"))
        a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
        flag = c["FLAG"].astype(bool)
        if arm in ("R1", "R1c"):
            w = c["WEIGHT_SPECTRUM"].astype(np.float64)
            okw = np.where(
                flag | c["FLAG_ROW"].astype(bool)[:, None, None], 0.0, w
            ).sum((1, 2))
            key = np.minimum(a1, a2).astype(np.int64) * 100000 + np.maximum(a1, a2)
            ukey, inv = np.unique(key, return_inverse=True)
            blw = np.zeros(len(ukey))
            np.add.at(blw, inv, okw)
            badkey = baseline_mask(ukey // 100000, ukey % 100000, bad_pairs())
            target = blw[badkey].sum() / blw.sum()
            rec["bad_baselines_in_subset"] = int(badkey.sum())
            rec["weight_share_bad"] = float(target)
            if arm == "R1":
                rows = badkey[inv]
            else:
                pick, share, ndraw = matched_control(blw, badkey, int(badkey.sum()), target,
                                                     np.random.default_rng(SEEDS["control"]))  # fmt: skip
                sel = np.zeros(len(ukey), bool)
                sel[pick] = True
                rows = sel[inv]
                rec.update(control_weight_share=share, control_draws=ndraw,
                           control_baselines=[[int(u // 100000), int(u % 100000)] for u in ukey[pick]])  # fmt: skip
            flag[rows] = True
            rec["rows_flagged"] = int(rows.sum())
            put(ms, FLAG=flag)
        else:  # R3: the DI pre-solve
            from rang import cal_gain

            ctx = dd4.context(root / arm, di=True)
            cc = ctx["c"]
            models = dd4.facet_models(ctx, np.load(root / "models" / "DEEP.npy"))
            _, tindex = np.unique(cc["TIME"], return_inverse=True)
            fbin = np.arange(cc["DATA"].shape[1]) // 8
            sol = cal_gain.solve_dd(cc["DATA"], models, cc["WEIGHT_SPECTRUM"], cc["FLAG"], cc["FLAG_ROW"],
                                    cc["ANTENNA1"], cc["ANTENNA2"], tindex, nant=len(cc["ant_names"]),
                                    freq_bin=fbin, refant=None, pinned_directions=[], calmode="ap",
                                    phase_last_direction_gain=False, **dict(dd4.CAP, max_iterations=500))  # fmt: skip
            del models
            g, gf = (
                np.asarray(sol.gains),
                np.asarray(sol.flags),
            )  # (t, f, ant, 1, 2), (t, f, ant, 1)
            rec.update(di_iterations=sol.iterations, di_fraction=sol.converged_fraction,
                       di_flagged=int((gf != 0).sum()), di_amp_p10_p50_p90=np.percentile(np.abs(g[gf == 0]), [10, 50, 90]).tolist())  # fmt: skip
            np.savez_compressed(root / arm / "di-gains.npz", gains=g, flags=gf)
            c2 = read2(ms, ("DATA", "WEIGHT_SPECTRUM"))
            data, wt = (
                c2["DATA"].astype(np.complex128),
                c2["WEIGHT_SPECTRUM"].astype(np.float64),
            )
            for h in (0, 1):
                gp = g[tindex[:, None], fbin[None, :], a1[:, None], 0, h]
                gq = g[tindex[:, None], fbin[None, :], a2[:, None], 0, h]
                bad = (gf[tindex[:, None], fbin[None, :], a1[:, None], 0] != 0) | (
                    gf[tindex[:, None], fbin[None, :], a2[:, None], 0] != 0
                )
                pq = gp * np.conj(gq)
                good = ~bad & (np.abs(pq) > 0)
                data[..., h] = np.where(
                    good, data[..., h] / np.where(good, pq, 1.0), data[..., h]
                )
                wt[..., h] = np.where(good, wt[..., h] * np.abs(pq) ** 2, wt[..., h])
                flag[..., h] |= bad
            put(
                ms,
                DATA=data.astype(np.complex64),
                WEIGHT_SPECTRUM=wt.astype(np.float32),
                FLAG=flag,
            )
            rec["cells_newly_flagged"] = int(flag.sum() - c["FLAG"].astype(bool).sum())
    else:
        raise SystemExit(f"unknown arm {arm}")
    rec["seconds"] = time.perf_counter() - t0
    write_json(root / arm / "build.json", rec)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "setup":
        setup(argv[1])
    elif cmd == "compose":
        compose(argv[1])
    elif cmd == "prep":
        prep(argv[1])
    elif cmd == "grid":
        cap = int(argv[argv.index("--cap") + 1]) if "--cap" in argv else 500
        grid(argv[1], int(argv[2]), argv[3], argv[4], free="--free" in argv, cap=cap)
    elif cmd == "g4":
        g4_check(argv[1])
    elif cmd == "resid":
        resid(argv[1])
    elif cmd == "stats":
        stats(argv[1])
    elif cmd == "build":
        build(argv[1], argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
