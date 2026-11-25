# SPDX-License-Identifier: MIT
"""DD8: the off-axis model gap inserted into simulation B, a held-out-baseline
measure, and cap 2000 at 16/64 x 8 s (research/dd8-offaxis.md).

    python tools/oracles/dd8/dd8.py gates ROOT              # G1
    python tools/oracles/dd8/dd8.py insert ROOT             # O, gate GO
    python tools/oracles/dd8/dd8.py rebuild ROOT R1|R1c     # gate GR
    python tools/oracles/dd8/dd8.py draw ROOT               # held-out baselines, gate GH
    python tools/oracles/dd8/dd8.py holdout ROOT SRC NAME   # an H copy of run dir SRC
    python tools/oracles/dd8/dd8.py grid RUN TI MODEL OUT.json [--free] [--cap N]
    python tools/oracles/dd8/dd8.py di RUN MODEL OUT.json   # one-direction reference, 4 x 8 s
    python tools/oracles/dd8/dd8.py score RUN OUT.json NAME=MODEL:GAINS[:TI] ...

DD7's run root (D:/rang/outputs/dd7-20261125) is read only; ROOT is DD8's
(D:/rang/outputs/dd8-20261125). GAINS is a grid or di `.npz`, `truth` (the
run's truth.npz, per 4 integrations) or `unit`.
"""

import hashlib
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DD7_ROOT = Path("D:/rang/outputs/dd7-20261125")
HELDOUT = {"seed": 8801, "fraction": 0.10, "tries": 100}
DELTA_FLUX = [0.0, 1.604, 0.323, -0.155]  # section 2, GO: DEEP - M0c per facet
DELTA_TOL = 1e-3
R1_ROWS = 65250
V1_TOL = 0.01
SIGNIFICANT = 3.0  # |difference| > 3 SE


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd7 = _load("dd7", HERE.parent / "dd7" / "dd7.py")
dd6, dd5, dd4, dd2 = dd7.dd6, dd7.dd5, dd7.dd4, dd7.dd2
LENGTH_BINS = dd7.LENGTH_BINS


# -- pure helpers (unit-tested in tests/test_dd8.py) ----------------------------------


def draw_heldout(length, bad, b1, b2, seed, fraction=0.10, bins=LENGTH_BINS, tries=100):
    """Per baseline (arrays over baselines): `fraction` of the non-bad
    baselines in each length bin, rounded, drawn with `seed`; redrawn with
    seed + 1, ... until every antenna present is on a held-out baseline.
    Returns (sorted baseline indices, seed used, per-bin counts)."""
    lb = np.digitize(length, bins) - 1
    present = np.union1d(b1, b2)
    for t in range(tries):
        rng = np.random.default_rng(seed + t)
        pick, counts = [], []
        for i in range(len(bins) - 1):
            pool = np.flatnonzero((lb == i) & ~bad)
            n = round(fraction * len(pool))
            counts.append([len(pool), n])
            if n:
                pick.extend(rng.choice(pool, size=n, replace=False).tolist())
        pick = np.sort(np.array(pick, dtype=int))
        if np.isin(present, np.union1d(b1[pick], b2[pick])).all():
            return pick, seed + t, counts
    raise RuntimeError("no held-out draw covers every antenna")


def clustered(d, n):
    """Ratio sum(d)/sum(n) over clusters (baselines) and its SE,
    sqrt(m/(m-1) sum (d_b - r n_b)^2) / sum n (section 4)."""
    d, n = np.asarray(d, float), np.asarray(n, float)
    keep = n > 0
    d, n = d[keep], n[keep]
    m = len(n)
    r = d.sum() / n.sum()
    se = (
        math.sqrt(m / (m - 1) * ((d - r * n) ** 2).sum()) / n.sum()
        if m > 1
        else math.nan
    )
    return float(r), float(se)


def reading(delta, se, pos="positive", neg="negative", none="no difference"):
    if abs(delta) > SIGNIFICANT * se:
        return pos if delta > 0 else neg
    return none


def row_sums(D, W, OK, V, gp, gq, k):
    """Per row: S = sum w|r|^2/(2k) over cells OK, and for each direction f
    the same with f's gains set to 1, and the cell count.
    D, W, OK: (rows, chans, 2); V: (rows, chans, ndir); gp, gq: (rows, ndir, 2)."""
    P = gp[:, None, :, :] * V[:, :, :, None] * np.conj(gq[:, None, :, :])
    r = D - P.sum(2)
    wk = np.where(OK, W / (2.0 * k), 0.0)
    s = (wk * (r.real**2 + r.imag**2)).sum((1, 2))
    sf = np.empty((V.shape[2], len(D)))
    for f in range(V.shape[2]):
        rf = r + P[:, :, f, :] - V[:, :, f, None]
        sf[f] = (wk * (rf.real**2 + rf.imag**2)).sum((1, 2))
    return s, sf, OK.sum((1, 2))


# -- io -------------------------------------------------------------------------------


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def freqs(ms):
    from rang import core_ms

    spw = core_ms.open_table(str(Path(ms) / "SPECTRAL_WINDOW"))
    f = np.asarray(spw.getcol("CHAN_FREQ"), float).reshape(-1)
    spw.close()
    return f


def facet_vis(uvw, freq, idx, model, f):
    """The facet-f predict of `model` (DD4's facet_models, one facet, one hand)."""
    from rang import core_wgridder

    return core_wgridder.dirty2vis(
        uvw=uvw, freq=freq, dirty=np.ascontiguousarray(np.where(idx == f, model, 0.0).T),
        pixsize_x=dd4.DELTA, pixsize_y=dd4.DELTA, epsilon=dd4.EPS, flip_v=True, flip_w=True,
    ).astype(np.complex64)  # fmt: skip


def k_noise():
    return json.loads((DD7_ROOT / "b" / "setup.json").read_text())["dd5"]["k"]


def unique_baselines(a1, a2):
    key = np.minimum(a1, a2).astype(np.int64) * 100000 + np.maximum(a1, a2)
    ukey, inv = np.unique(key, return_inverse=True)
    return ukey, inv, (ukey // 100000).astype(int), (ukey % 100000).astype(int)


# -- setup ----------------------------------------------------------------------------


def gates(root):
    root = Path(root)
    idx = dd6.facet_idx(DD7_ROOT / "real")
    ref = json.loads((DD7_ROOT / "models" / "G2.json").read_text())["per_facet_flux"]
    rec, ok = {"sha256": {}, "per_facet_flux": {}}, True
    for name, path in (("DEEP", DD7_ROOT / "models" / "DEEP.npy"), ("RM", DD7_ROOT / "models" / "RM.npy"),
                       ("M0c", DD7_ROOT / "b" / "sky.npy")):  # fmt: skip
        m = np.load(path)
        per = [float(m[idx == f].sum()) for f in range(4)]
        rec["sha256"][name] = sha256(path)
        rec["per_facet_flux"][name] = per
        ok &= max(abs(a - b) for a, b in zip(per, ref[name], strict=True)) <= 1e-6
    rec["G1_pass"] = bool(ok)
    dd7.write_json(root / "gates" / "G1.json", rec)
    if not ok:
        raise SystemExit("G1 failed: setup outcome")


def insert(root):
    """Section 3: O = B + sum_{f>=1} G_f predict((DEEP - M0c)|f) G_f^H; gate GO."""
    root = Path(root)
    t0 = time.perf_counter()
    base = DD7_ROOT / "b"
    st = json.loads((base / "setup.json").read_text())
    run = root / "O"
    ms = dd7.copy_run(base, run, st["subms"], ("truth.npz", "sky.npy"))
    idx = dd6.facet_idx(run)
    m0c = np.load(base / "sky.npy")
    sky_o = dd6.compose(idx, np.load(DD7_ROOT / "models" / "DEEP.npy"), m0c)
    delta = sky_o - m0c
    np.save(run / "sky.npy", sky_o)  # the truth sky of O
    c = dd7.read2(ms, ("DATA", "WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2",
                       "TIME", "UVW"))  # fmt: skip
    freq = freqs(ms)
    g = np.load(base / "truth.npz")["gains"]  # (nblock, nant, ndir, 2)
    block4 = np.unique(c["TIME"], return_inverse=True)[1] // dd5.BLOCK
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    data_b = c.pop("DATA")
    data = data_b.astype(np.complex64).copy()
    pred_b = np.zeros(data.shape, np.complex64)
    pred_o = np.zeros(data.shape, np.complex64)
    for f in range(4):
        vb = facet_vis(c["UVW"], freq, idx, m0c, f)
        vo = facet_vis(c["UVW"], freq, idx, sky_o, f)
        vd = facet_vis(c["UVW"], freq, idx, delta, f) if f else None
        for h in (0, 1):
            gg = (g[block4, a1, f, h] * np.conj(g[block4, a2, f, h]))[:, None]
            pred_b[..., h] += (gg * vb).astype(np.complex64)
            pred_o[..., h] += (gg * vo).astype(np.complex64)
            if f:
                data[..., h] += (gg * vd).astype(np.complex64)
        del vb, vo, vd
    n = dd7.regen_noise(c["WEIGHT_SPECTRUM"], st["dd5"]["k"])
    ok = ~(c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]) & (
        c["WEIGHT_SPECTRUM"] > 0
    )
    g3 = float(np.abs(np.where(ok, data_b - n - pred_b, 0)).max())
    go = float(np.abs(np.where(ok, data - n - pred_o, 0)).max())
    dd7.put(ms, DATA=data)
    signed = [float(delta[idx == f].sum()) for f in range(4)]
    absd = [float(np.abs(delta[idx == f]).sum()) for f in range(4)]
    flux_ok = (
        max(abs(a - b) for a, b in zip(signed, DELTA_FLUX, strict=True)) <= DELTA_TOL
    )
    rec = {"delta_signed_jy": signed, "delta_abs_sum_jy": absd, "sky_o_flux": float(sky_o.sum()),
           "max_abs_B_minus_n_minus_predictB": g3, "max_abs_O_minus_n_minus_predictO": go,
           "GO_pass": bool(flux_ok and g3 <= 1e-3 and go <= 1e-3),
           "seconds": time.perf_counter() - t0}  # fmt: skip
    dd7.write_json(run / "build.json", rec)
    if not rec["GO_pass"]:
        raise SystemExit("GO failed: setup outcome")


def rebuild(root, arm):
    """DD7's R1 / R1c copies rebuilt from DD7's real subset; gate GR."""
    root = Path(root)
    t0 = time.perf_counter()
    base = DD7_ROOT / "real"
    st = json.loads((base / "setup.json").read_text())
    ms = dd7.copy_run(base, root / arm, st["subms"])
    c = dd7.read2(ms, ("WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2"))
    flag = c["FLAG"].astype(bool)
    w = c["WEIGHT_SPECTRUM"].astype(np.float64)
    okw = np.where(flag | c["FLAG_ROW"].astype(bool)[:, None, None], 0.0, w).sum((1, 2))
    ukey, inv, b1, b2 = unique_baselines(c["ANTENNA1"], c["ANTENNA2"])
    blw = np.zeros(len(ukey))
    np.add.at(blw, inv, okw)
    badkey = dd7.baseline_mask(b1, b2, dd7.bad_pairs())
    target = blw[badkey].sum() / blw.sum()
    rec = {
        "arm": arm,
        "bad_baselines_in_subset": int(badkey.sum()),
        "weight_share_bad": float(target),
    }
    if arm == "R1":
        rows = badkey[inv]
        ok = int(rows.sum()) == R1_ROWS
    elif arm == "R1c":
        pick, share, ndraw = dd7.matched_control(blw, badkey, int(badkey.sum()), target,
                                                 np.random.default_rng(dd7.SEEDS["control"]))  # fmt: skip
        sel = np.zeros(len(ukey), bool)
        sel[pick] = True
        rows = sel[inv]
        mine = [[int(b1[i]), int(b2[i])] for i in pick]
        ref = json.loads((DD7_ROOT / "R1c" / "build.json").read_text())[
            "control_baselines"
        ]
        rec.update(
            control_weight_share=share,
            control_draws=ndraw,
            control_equals_dd7=mine == ref,
        )
        ok = mine == ref
    else:
        raise SystemExit(f"unknown arm {arm}")
    flag[rows] = True
    put_rows = int(rows.sum())
    dd7.put(ms, FLAG=flag)
    rec.update(
        rows_flagged=put_rows, GR_pass=bool(ok), seconds=time.perf_counter() - t0
    )
    dd7.write_json(root / arm / "build.json", rec)
    if not ok:
        raise SystemExit("GR failed: setup outcome")


def draw(root):
    """Section 4 / GH: the held-out baselines, drawn on the real subset's layout."""
    root = Path(root)
    ms = json.loads((DD7_ROOT / "real" / "setup.json").read_text())["subms"]
    c = dd7.read2(ms, ("WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2"))
    ukey, inv, b1, b2 = unique_baselines(c["ANTENNA1"], c["ANTENNA2"])
    pos = dd7.ant_positions(ms)
    length = np.linalg.norm(pos[b1] - pos[b2], axis=1)
    bad = dd7.baseline_mask(b1, b2, dd7.bad_pairs())
    pick, seed, counts = draw_heldout(length, bad, b1, b2, HELDOUT["seed"], HELDOUT["fraction"],
                                      tries=HELDOUT["tries"])  # fmt: skip
    w = c["WEIGHT_SPECTRUM"].astype(np.float64)
    okw = np.where(
        c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None], 0.0, w
    ).sum((1, 2))
    blw = np.zeros(len(ukey))
    np.add.at(blw, inv, okw)
    covered = np.union1d(b1[pick], b2[pick])
    rec = {"seed_used": seed, "baselines": len(ukey), "bad": int(bad.sum()), "heldout": len(pick),
           "per_bin_pool_and_drawn": dict(zip([f"{LENGTH_BINS[i]}-{LENGTH_BINS[i + 1]:g}" for i in range(len(LENGTH_BINS) - 1)], counts, strict=True)),
           "weight_share": float(blw[pick].sum() / blw.sum()), "antennas_covered": len(covered),
           "antennas_present": len(np.union1d(b1, b2)), "any_bad": bool(bad[pick].any()),
           "pairs": [[int(b1[i]), int(b2[i])] for i in pick]}  # fmt: skip
    rec["GH_pass"] = bool(
        not rec["any_bad"] and rec["antennas_covered"] == rec["antennas_present"]
    )
    dd7.write_json(root / "heldout.json", rec)
    if not rec["GH_pass"]:
        raise SystemExit("GH failed: setup outcome")


def holdout(root, src, name):
    """An H copy of run directory `src`: the held-out baselines flagged, their
    original flags kept in heldout.npz."""
    root, src = Path(root), Path(src)
    t0 = time.perf_counter()
    st = json.loads((src / "setup.json").read_text())
    extra = tuple(f for f in ("truth.npz", "sky.npy") if (src / f).exists())
    ms = dd7.copy_run(src, root / name, st["subms"], extra)
    pairs = [tuple(p) for p in json.loads((root / "heldout.json").read_text())["pairs"]]
    c = dd7.read2(ms, ("FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2"))
    sel = dd7.baseline_mask(c["ANTENNA1"], c["ANTENNA2"], pairs)
    rows = np.flatnonzero(sel)
    flag = c["FLAG"].astype(bool)
    np.savez_compressed(root / name / "heldout.npz", rows=rows, flag=flag[rows],
                        flag_row=c["FLAG_ROW"].astype(bool)[rows])  # fmt: skip
    flag[rows] = True
    dd7.put(ms, FLAG=flag)
    rec = {"src": str(src), "rows_heldout": len(rows), "baselines": len(pairs),
           "seconds": time.perf_counter() - t0}  # fmt: skip
    dd7.write_json(root / name / "build.json", rec)


# -- solves ---------------------------------------------------------------------------


def di(run, model, out, ti=4, cap=500):
    """The one-direction reference: the whole model as one direction."""
    from rang import cal_gain

    run, out = Path(run), Path(out)
    t0 = time.perf_counter()
    ctx = dd4.context(run, di=True, ti=ti)
    c = ctx["c"]
    models = dd4.facet_models(ctx, np.load(model))
    t1 = time.perf_counter()
    sol = cal_gain.solve_dd(c["DATA"], models, c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"],
                            c["ANTENNA1"], c["ANTENNA2"], ctx["block"], nant=len(c["ant_names"]),
                            refant=None, pinned_directions=[], calmode="ap",
                            phase_last_direction_gain=False, **dict(dd4.CAP, max_iterations=cap))  # fmt: skip
    g, f = np.asarray(sol.gains), np.asarray(sol.flags)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out.with_suffix(".npz"), gains=g, flags=f)
    rec = {"run": str(run), "model": str(model), "ti": ti, "cap": cap, "iterations": sol.iterations,
           "fraction": sol.converged_fraction, "flagged": int((f != 0).sum()),
           "amp_p10_p50_p90": np.percentile(np.abs(g[..., 0, :][f[..., 0] == 0]), [10, 50, 90]).tolist(),
           "seconds_predict": t1 - t0, "seconds_solve": time.perf_counter() - t1}  # fmt: skip
    out.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec), flush=True)


# -- the held-out score ---------------------------------------------------------------


def parse_entry(s):
    name, rest = s.split("=", 1)
    parts = rest.split(":")
    # Windows paths carry a drive colon: rejoin "D" + ":/..."
    out, i = [], 0
    while i < len(parts):
        if (
            len(parts[i]) == 1
            and i + 1 < len(parts)
            and parts[i + 1].startswith(("/", "\\"))
        ):
            out.append(parts[i] + ":" + parts[i + 1])
            i += 2
        else:
            out.append(parts[i])
            i += 1
    model, gains = out[0], out[1]
    ti = int(out[2]) if len(out) > 2 else 4
    return name, model, gains, ti


def load_gains(run, gains, ti, nant, ndir):
    """(G (t, ant, dir, 2), flags (t, ant, dir) bool, ti, converged or None)."""
    if gains == "unit":
        return (
            np.ones((1, nant, ndir, 2), complex),
            np.zeros((1, nant, ndir), bool),
            10**9,
            None,
        )
    if gains == "truth":
        g = np.load(Path(run) / "truth.npz")["gains"]
        return g, np.zeros(g.shape[:3], bool), dd5.BLOCK, None
    z = np.load(gains)
    g = np.array(z["gains"])[:, 0]
    f = np.asarray(z["flags"])[:, 0] != 0
    g[f] = 1.0
    conv = np.asarray(z["converged"])[:, 0] if "converged" in z.files else None
    return g, f, ti, conv


def score(run, out, specs, chunk=20000):
    run, out = Path(run), Path(out)
    t0 = time.perf_counter()
    st = json.loads((run / "setup.json").read_text())
    ms = st["subms"]
    k = k_noise()
    ho = np.load(run / "heldout.npz")
    hrows = ho["rows"]
    c = dd7.read2(
        ms,
        (
            "DATA",
            "WEIGHT_SPECTRUM",
            "FLAG",
            "FLAG_ROW",
            "ANTENNA1",
            "ANTENNA2",
            "TIME",
            "UVW",
        ),
    )
    freq = freqs(ms)
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    nrow = len(a1)
    nant = int(max(a1.max(), a2.max())) + 1
    tindex = np.unique(c["TIME"], return_inverse=True)[1]
    idx = dd6.facet_idx(run)
    ukey, inv, b1, b2 = unique_baselines(a1, a2)
    nb = len(ukey)
    bad_b = dd7.baseline_mask(b1, b2, dd7.bad_pairs())
    W = c["WEIGHT_SPECTRUM"].astype(np.float64)
    ok = ~(c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]) & (W > 0)
    ok[hrows] = ~(
        ho["flag"].astype(bool) | ho["flag_row"].astype(bool)[:, None, None]
    ) & (W[hrows] > 0)
    held = np.zeros(nrow, bool)
    held[hrows] = True
    insample = ~held & ~bad_b[inv]
    entries = [parse_entry(s) for s in specs]
    vis = {}
    for _, model, _, _ in entries:
        if model not in vis:
            m = np.load(model)
            vis[model] = np.stack(
                [facet_vis(c["UVW"], freq, idx, m, f) for f in range(4)], -1
            )
    loaded = {}
    valid = np.ones(nrow, bool)
    for name, model, gains, ti in entries:
        ndir = (
            1
            if gains not in ("unit", "truth") and np.load(gains)["gains"].shape[3] == 1
            else 4
        )
        g, f, ti_e, conv = load_gains(run, gains, ti, nant, ndir)
        it = np.minimum(tindex // ti_e, g.shape[0] - 1)
        valid &= ~f[it, a1].any(-1) & ~f[it, a2].any(-1)
        loaded[name] = (model, g, it, conv, ndir)
    rec = {"run": str(run), "k": k, "entries": specs, "rows_heldout": len(hrows),
           "heldout_rows_dropped_flagged_gain": float(1 - valid[hrows].mean()),
           "insample_rows_dropped_flagged_gain": float(1 - valid[insample].mean()), "results": {}}  # fmt: skip
    sums = {}
    D = c["DATA"]
    for name, (model, g, it, conv, ndir) in loaded.items():
        V = vis[model]
        out_rows = {}
        for part, rows in (
            ("heldout", np.flatnonzero(held & valid)),
            ("insample", np.flatnonzero(insample & valid)),
        ):
            s_all = np.zeros(len(rows))
            sf_all = np.zeros((ndir, len(rows)))
            n_all = np.zeros(len(rows))
            for j in range(0, len(rows), chunk):
                r = rows[j : j + chunk]
                v = V[r] if ndir == 4 else V[r].sum(-1, keepdims=True)
                gp, gq = g[it[r], a1[r]], g[it[r], a2[r]]
                s, sf, n = row_sums(
                    D[r].astype(np.complex128),
                    W[r],
                    ok[r],
                    v.astype(np.complex128),
                    gp,
                    gq,
                    k,
                )
                s_all[j : j + chunk], sf_all[:, j : j + chunk], n_all[j : j + chunk] = (
                    s,
                    sf,
                    n,
                )
            out_rows[part] = (rows, s_all, sf_all, n_all)
        rows, s, sf, n = out_rows["heldout"]
        S = np.bincount(inv[rows], s, nb)
        N = np.bincount(inv[rows], n, nb)
        SF = np.stack([np.bincount(inv[rows], sf[f], nb) for f in range(ndir)])
        sums[name] = (S, N, SF)
        H, Hse = clustered(S, N)
        res = {"H_heldout": H, "H_heldout_se": Hse, "cells_heldout": int(N.sum())}
        res["dH"] = []
        for f in range(ndir):
            d, se = clustered(SF[f] - S, N)
            res["dH"].append({"dir": f, "dH": d, "se": se,
                              "reading": reading(d, se, "informative", "harmful", "uninformative")})  # fmt: skip
        if conv is not None:
            rc = conv[it[rows], a1[rows], 1:].all(-1) & conv[
                it[rows], a2[rows], 1:
            ].all(-1)
            res["heldout_rows_offaxis_converged_fraction"] = float(rc.mean())
            res["H_heldout_converged_rows"] = float(s[rc].sum() / max(n[rc].sum(), 1))
            res["H_heldout_other_rows"] = float(s[~rc].sum() / max(n[~rc].sum(), 1))
        _, si, _, ni = out_rows["insample"]
        res["H_insample"] = float(si.sum() / max(ni.sum(), 1))
        rec["results"][name] = res
    names = list(sums)
    N0 = sums[names[0]][1]
    for name in names[1:]:
        assert np.array_equal(sums[name][1], N0), "entries scored on different cells"
    rec["pairs"] = {}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            d, se = clustered(sums[a][0] - sums[b][0], N0)
            rec["pairs"][f"{a} - {b}"] = {"dH": d, "se": se,
                                          "reading": reading(d, se, f"{b} predicts better", f"{a} predicts better")}  # fmt: skip
    rec["seconds"] = time.perf_counter() - t0
    np.savez_compressed(out.with_suffix(".npz"), names=np.array(names), N=N0,
                        **{f"S_{n}": sums[n][0] for n in names}, **{f"SF_{n}": sums[n][2] for n in names})  # fmt: skip
    dd7.write_json(out, rec)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "gates":
        gates(argv[1])
    elif cmd == "insert":
        insert(argv[1])
    elif cmd == "rebuild":
        rebuild(argv[1], argv[2])
    elif cmd == "draw":
        draw(argv[1])
    elif cmd == "holdout":
        holdout(argv[1], argv[2], argv[3])
    elif cmd == "grid":
        cap = int(argv[argv.index("--cap") + 1]) if "--cap" in argv else 500
        dd7.grid(
            argv[1], int(argv[2]), argv[3], argv[4], free="--free" in argv, cap=cap
        )
    elif cmd == "di":
        di(argv[1], argv[2], argv[3])
    elif cmd == "score":
        score(argv[1], argv[2], argv[3:])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
