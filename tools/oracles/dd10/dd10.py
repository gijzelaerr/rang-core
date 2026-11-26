# SPDX-License-Identifier: MIT
"""DD10: the Gauss-Seidel direction update in the Rust DD kernel, and an
off-axis model from DD-corrected facet images on O (research/dd10-gs.md).

    python tools/oracles/dd10/dd10.py abtest OUT.json              # K1b, under one extension
    python tools/oracles/dd10/dd10.py abcompare A.json B.json OUT.json
    python tools/oracles/dd10/dd10.py fixedpoint ROOT              # section 4, T1 and T2 (reference)
    python tools/oracles/dd10/dd10.py point ROOT NAME BASE MODEL UPDATE [--stop-fraction F] [--one]
    python tools/oracles/dd10/dd10.py gates ROOT                   # K1c, K2b, K3 from the points
    python tools/oracles/dd10/dd10.py psf ROOT BASE                # section 5's PSF
    python tools/oracles/dd10/dd10.py loop ROOT ARM                # AL, AT (O) or RL (real)
    python tools/oracles/dd10/dd10.py score ROOT                   # sections 5 and 6 readings

BASE is `O` (DD10's rebuilt O) or `real` (DD7's real subset with the 145 bad
baselines flagged in memory). DD7's, DD8's and DD9's roots are read only.
"""

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DD7_ROOT = Path("D:/rang/outputs/dd7-20261125")
DD8_ROOT = Path("D:/rang/outputs/dd8-20261125")
DD9_ROOT = Path("D:/rang/outputs/dd9-20261126")
TI = 4
CAP = 500
TRUST = (1.0 / 3.0, 3.0)  # section 5: trusted gain amplitudes
NCYCLE = 3
R1_ROWS = 65250
TOL_K2 = {"fraction": 0.005, "flagged_rel": 0.01, "product": 1e-6}
TOL_K3 = {"median": 1e-6, "p99": 1e-4}
TOL_T1 = 1e-6
TOL_T2 = {"median": 1e-6, "p99": 1e-4}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd9 = _load("dd9", HERE.parent / "dd9" / "dd9.py")
dd8 = dd9._dd8()
dd7, dd6, dd5, dd4, dd2 = dd8.dd7, dd8.dd6, dd8.dd5, dd8.dd4, dd8.dd2
dd3 = dd4.dd3


def write_json(path, rec):
    dd9.write_json(path, rec)
    print(json.dumps(rec, default=float)[:2000], flush=True)


def sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


# -- K1b: the default against the main checkout's extension ----------------------------


def abtest(out):
    """Default-settings DD solves on the synthetic problems of
    tests/test_cal_gain_dd.py and tests/test_dd9.py, hashed. Uses only the
    arguments both extensions know."""
    from rang import cal_gain

    t1 = _load("t_cal_gain_dd", REPO / "tests" / "test_cal_gain_dd.py")
    t9 = _load("t_dd9", REPO / "tests" / "test_dd9.py")
    rec = {"extension": str(Path(cal_gain.__file__).parent), "cases": {}}
    problems = {}
    _, data, models, a1, a2, tb, nant = t1.simulate()
    nrow, nchan = data.shape[:2]
    problems["cal_gain_dd"] = (data, models, np.ones((nrow, nchan, 4)), np.zeros((nrow, nchan, 4), bool),
                               np.zeros(nrow, bool), a1, a2, tb, nant)  # fmt: skip
    sy = t9.synthetic()
    m = np.zeros(sy["data"].shape[:2] + (len(sy["vis"]), 4), np.complex64)
    for d, v in enumerate(sy["vis"]):
        m[:, :, d, 0] = m[:, :, d, 3] = v
    problems["dd9"] = (sy["data"], m, sy["weights"], sy["flag"], sy["flag_row"], sy["a1"], sy["a2"],
                       sy["tindex"] // 4, sy["nant"])  # fmt: skip
    for pname, (*args, nant) in problems.items():
        for refant in (0, None):
            for pinned in ((), (0,)):
                for calmode in ("ap", "p"):
                    for cap in (1, 5, 50, 300):
                        sol = cal_gain.solve_dd(*args, nant=nant, refant=refant, pinned_directions=list(pinned),
                                                max_iterations=cap, calmode=calmode)  # fmt: skip
                        key = f"{pname}/refant={refant}/pinned={list(pinned)}/{calmode}/cap={cap}"
                        rec["cases"][key] = {"gains": sha(np.asarray(sol.gains)), "flags": sha(np.asarray(sol.flags)),
                                             "iterations": sol.iterations, "fraction": sol.converged_fraction}  # fmt: skip
    write_json(out, rec)


def abcompare(a, b, out):
    ra, rb = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    keys = sorted(ra["cases"])
    diff = [k for k in keys if ra["cases"][k] != rb["cases"].get(k)]
    rec = {"a": ra["extension"], "b": rb["extension"], "cases": len(keys),
           "same_keys": sorted(rb["cases"]) == keys, "differing": diff,
           "K1b_pass": not diff and sorted(rb["cases"]) == keys}  # fmt: skip
    write_json(out, rec)


# -- section 4: the fixed point (DD9's reference on DD9's sums) ------------------------


def _res(path, K, D=4):
    z = np.load(path)
    return {
        key: [z[f"{key}{K}_{d}"] for d in range(D)] for key in ("g", "f", "g2", "f2")
    }


def _interval_converged(res):
    """Per interval: every unflagged gain converged (all directions)."""
    _, masks = dd9.perdir(res)
    ok = np.ones(res["g"][0].shape[0], bool)
    for d in range(len(masks)):
        free = (res["f"][d] == 0) & (res["f2"][d] == 0)
        ok &= (masks[d] | ~free).all(1)
    return ok


def default_step(P, g, f):
    """One default (Jacobi, halved) iteration's relative step |dg|/|g| per
    gain at gains g with flags f (lists per direction)."""
    st = dd9.State(
        P,
        init=[
            np.where((ff == 1)[..., None], 1.0, gg) for gg, ff in zip(g, f, strict=True)
        ],
    )
    for d in range(P.D):
        st.flag[d] = f[d].copy()
    ne = P.normal(st.g)
    out = []
    for d in range(P.D):
        u = 0.5 * dd9._update(*ne[d], st.g[d], 0.0)
        u = np.where((f[d] == 1)[..., None], 0.0, u)
        out.append(
            np.sqrt(
                (np.abs(u) ** 2).sum(-1)
                / np.maximum((np.abs(st.g[d]) ** 2).sum(-1), 1e-300)
            )
        )
    return out


def run_imposed(P, K, flags, variant="I2"):
    """dd9.run to K (and K + 1), no global stop, with `flags` (1: flagged)
    imposed from the start (held at 1; the ladder cannot unflag them)."""
    st = dd9.State(P)
    for d in range(P.D):
        st.flag[d][flags[d] == 1] = 1
        st.g[d][flags[d] == 1] = 1.0
        st.km1[d] = st.g[d].copy()
    snaps = {}
    for it in range(1, K + 2):
        dd9.iterate(P, st, it - 1, variant)
        if it == K:
            snaps["first"] = st.snapshot()
        if it == K + 1:
            snaps["second"] = st.snapshot()
    (g, f), (g2, f2) = snaps["first"], snaps["second"]
    return {
        "g": g,
        "f": f,
        "g2": g2,
        "f2": f2,
        "iterations": K,
        "fraction": float("nan"),
    }


def _products(g, nant):
    p, q = np.triu_indices(nant, 1)
    return g[:, p] * np.conj(g[:, q])  # (nint, npair, 2)


def compare_products(ra, rb, intervals, nant):
    """Products g_p conj g_q, a against b, on cells converged in both (both
    antennas, both solutions), restricted to `intervals` (bool per interval)."""
    _, ma = dd9.perdir(ra)
    _, mb = dd9.perdir(rb)
    p, q = np.triu_indices(nant, 1)
    vals = []
    for d in range(len(ra["g"])):
        diff = np.abs(_products(ra["g"][d], nant) - _products(rb["g"][d], nant))
        ok = ma[d][:, p] & ma[d][:, q] & mb[d][:, p] & mb[d][:, q] & intervals[:, None]
        vals.append(diff[np.broadcast_to(ok[..., None], diff.shape)])
    v = np.concatenate(vals)
    if not v.size:
        return {"cells": 0, "median": None, "p99": None, "max": None}
    return {"cells": int(v.size), "median": float(np.median(v)), "p99": float(np.percentile(v, 99)),
            "max": float(v.max())}  # fmt: skip


def same_flags(ra, rb):
    """Per interval: identical final flag arrays in every direction."""
    ok = np.ones(ra["f"][0].shape[0], bool)
    for d in range(len(ra["f"])):
        ok &= (ra["f"][d] == rb["f"][d]).all(1)
    return ok


def fixedpoint(root):
    root = Path(root)
    t0 = time.perf_counter()
    S = dd9.Sums(DD9_ROOT / "sums" / "O-skyO.npz")
    P = dd9.Problem(S, np.arange(S.nblock), [1] * S.ndir)
    nconv = np.array(
        json.loads((DD9_ROOT / "solve" / "O-X-default.json").read_text())["N_conv"]
    )
    slow = (nconv > 500) & (nconv <= 2000)
    never = nconv > 2000
    i2 = _res(DD9_ROOT / "solve" / "O-X-I2.npz", 2000)
    de = _res(DD9_ROOT / "solve" / "O-X-default.npz", 2000)
    rec = {"slow_intervals": int(slow.sum()), "never_intervals": int(never.sum())}
    # T1: one default step at I2's converged cap-2000 solution.
    conv_i2 = _interval_converged(i2)
    steps = default_step(P, i2["g"], i2["f"])
    per_int = np.max(
        [np.where(i2["f"][d] == 0, s, 0.0).max(1) for d, s in enumerate(steps)], 0
    )
    rec["T1"] = {"intervals_I2_converged": int(conv_i2.sum()),
                 "max_rel_step_on_converged": float(per_int[conv_i2].max()),
                 "median_of_interval_max": float(np.median(per_int[conv_i2])),
                 "max_rel_step_all_intervals": float(per_int.max()),
                 "reading": "a fixed point of the default update" if per_int[conv_i2].max() <= TOL_T1
                 else "not a fixed point of the default update"}  # fmt: skip
    # T2: I2 with the default's cap-2000 flags imposed, against the default.
    t1 = time.perf_counter()
    imp = run_imposed(P, 2000, de["f"])
    rec["T2_seconds"] = time.perf_counter() - t1
    eq = same_flags(imp, de)
    conv_de = _interval_converged(de)
    extra = [int(((imp["f"][d] == 1) & (de["f"][d] != 1)).sum()) for d in range(4)]
    rec["T2"] = {"extra_flags_per_direction": extra,
                 "slow_with_equal_flags": int((slow & eq).sum()),
                 "slow": compare_products(imp, de, slow & eq, S.nant),
                 "default_converged_with_equal_flags": int((conv_de & eq).sum()),
                 "default_converged": compare_products(imp, de, conv_de & eq, S.nant),
                 "never": compare_products(imp, de, never & eq, S.nant)}  # fmt: skip
    s = rec["T2"]["slow"]
    rec["T2"]["reading"] = ("only the flag ladder" if s["cells"] and s["median"] <= TOL_T2["median"]
                            and s["p99"] <= TOL_T2["p99"] else "a real difference in the fixed point")  # fmt: skip
    # Reported: I2 unconstrained against the default on the slow intervals
    # (DD9's failing comparison) and the imposed run against I2.
    rec["reported"] = {
        "I2_vs_default_slow": compare_products(i2, de, slow, S.nant),
        "imposed_I2_converged_intervals": int(_interval_converged(imp).sum()),
        "imposed_fraction": dd9.perdir(imp)[0],
    }
    rec["seconds"] = time.perf_counter() - t0
    (root / "fixedpoint").mkdir(parents=True, exist_ok=True)
    np.savez_compressed(root / "fixedpoint" / "imposed-I2-2000.npz",
                        **{f"{k}_{d}": imp[k][d] for k in ("g", "f", "g2", "f2") for d in range(4)})  # fmt: skip
    write_json(root / "fixedpoint" / "fixedpoint.json", rec)


# -- Rust points -----------------------------------------------------------------------


def base_ctx(root, base):
    """dd4's context for O (DD10's rebuild) or the real subset with the 145
    bad baselines flagged in memory (setup gate: 65,250 rows)."""
    root = Path(root)
    if base == "O":
        run = root / "O"
        ctx = dd4.context(run, ti=TI)
        ctx["run"] = run
        return ctx
    if base != "real":
        raise SystemExit(f"unknown base {base}")
    run = DD7_ROOT / "real"
    ctx = dd4.context(run, ti=TI)
    c = ctx["c"]
    bad = dd7.baseline_mask(c["ANTENNA1"], c["ANTENNA2"], dd7.bad_pairs())
    if int(bad.sum()) != R1_ROWS:
        raise SystemExit(
            f"setup: {int(bad.sum())} rows on the 145 baselines, not {R1_ROWS}"
        )
    c["FLAG"][bad] = True
    c["w_I"][bad] = 0.0
    ctx["run"] = run
    ctx["bad_rows"] = int(bad.sum())
    return ctx


def solve(ctx, models, update, cap=CAP, stop_fraction=0.99, second=True):
    from rang import cal_gain

    c = ctx["c"]
    args = (c["DATA"], models, c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"],
            c["ANTENNA1"], c["ANTENNA2"], ctx["block"])  # fmt: skip
    kw = {"nant": len(c["ant_names"]), "refant": None, "pinned_directions": [], "calmode": "ap",
          "phase_last_direction_gain": False, "stop_criterion": 1e-7}  # fmt: skip
    if update != "jacobi":
        kw["direction_update"] = update
    t0 = time.perf_counter()
    sol = cal_gain.solve_dd(
        *args, **kw, max_iterations=cap, stop_fraction=stop_fraction
    )
    t1 = time.perf_counter()
    out = {"sol": sol, "seconds_solve": t1 - t0}
    if second:
        sol2 = cal_gain.solve_dd(*args, **kw, max_iterations=sol.iterations + 1,
                                 stop_fraction=1.0 if stop_fraction <= 1 else stop_fraction)  # fmt: skip
        out["sol2"] = sol2
        out["seconds_second"] = time.perf_counter() - t1
    return out


def scores(ctx, models, sol, sol2=None, k=None):
    """Section 5's scores of one solve (truth error where the base has one)."""
    gains, flags = np.asarray(sol.gains), np.asarray(sol.flags)
    rec = {"iterations": sol.iterations, "global_fraction": sol.converged_fraction,
           "flagged": [int((flags[..., f] != 0).sum()) for f in range(4)],
           "d3_amp": dd9.amp_tail(gains[:, 0, :, 3], flags[:, 0, :, 3])}  # fmt: skip
    conv = None
    if sol2 is not None:
        g2, f2 = np.asarray(sol2.gains), np.asarray(sol2.flags)
        rec["perdir_converged"] = dd4.per_direction_converged(gains, g2, flags, f2)
        conv = dd4.per_cell_converged(gains, g2, flags, f2)
    k = k or float(json.loads((DD7_ROOT / "b" / "setup.json").read_text())["dd5"]["k"])
    rec["ehat_d"] = dd5.predicted_error(ctx, models, k, TI)
    if (ctx["run"] / "truth.npz").exists():
        rec["e_d"] = dd5.truth_error(ctx["run"], ctx, gains, flags, TI, False)
        rec["e_over_ehat"] = [
            a / b for a, b in zip(rec["e_d"], rec["ehat_d"], strict=True)
        ]
        if conv is not None:
            tr = np.load(ctx["run"] / "truth.npz")["gains"]
            rec["e_d_converged"] = [dd9.e_dir(gains[:, 0, :, d], flags[:, 0, :, d], tr[:, :, d], 1,
                                              conv=conv[:, 0, :, d]) for d in range(4)]  # fmt: skip
    return rec, conv


def point(root, name, base, model, update, stop_fraction=0.99, second=True):
    root = Path(root)
    t0 = time.perf_counter()
    ctx = base_ctx(root, base)
    models = dd4.facet_models(ctx, np.load(model))
    t1 = time.perf_counter()
    out = solve(ctx, models, update, stop_fraction=stop_fraction, second=second)
    rec, conv = scores(ctx, models, out["sol"], out.get("sol2"))
    rec.update({"base": base, "model": str(model), "update": update, "stop_fraction": stop_fraction,
                "cap": CAP, "models_sha256": sha(models), "seconds_predict": t1 - t0,
                "seconds_solve": out["seconds_solve"], "seconds_second": out.get("seconds_second")})  # fmt: skip
    save = {
        "gains": np.asarray(out["sol"].gains),
        "flags": np.asarray(out["sol"].flags),
    }
    if second:
        save.update(
            gains2=np.asarray(out["sol2"].gains),
            flags2=np.asarray(out["sol2"].flags),
            converged=conv,
        )
    (root / "points").mkdir(parents=True, exist_ok=True)
    np.savez_compressed(root / "points" / f"{name}.npz", **save)
    rec["seconds"] = time.perf_counter() - t0
    write_json(root / "points" / f"{name}.json", rec)


def _rust_res(npz):
    """A Rust point as dd9's result dict (lists per direction)."""
    z = np.load(npz)
    g, f, g2, f2 = (
        np.asarray(z[k])[:, 0] for k in ("gains", "flags", "gains2", "flags2")
    )
    return {"g": [g[:, :, d] for d in range(4)], "f": [f[:, :, d] for d in range(4)],
            "g2": [g2[:, :, d] for d in range(4)], "f2": [f2[:, :, d] for d in range(4)]}  # fmt: skip


def gates(root):
    """K1c, K2b and K3 from the kept points."""
    root = Path(root)
    rec = {}
    k1 = np.load(root / "points" / "K1c-OX-default.npz")
    d8 = np.load(DD8_ROOT / "grid" / "O-X.npz")
    rec["K1c"] = {"gains_bitwise": bool(np.array_equal(k1["gains"], d8["gains"])),
                  "flags_bitwise": bool(np.array_equal(k1["flags"], d8["flags"])),
                  "max_abs_gain_diff": float(np.abs(k1["gains"] - d8["gains"]).max())}  # fmt: skip
    rec["K1c"]["pass"] = rec["K1c"]["gains_bitwise"] and rec["K1c"]["flags_bitwise"]
    # K2b: Rust GS (no global stop) against DD9's reference I2 at cap 500.
    rs = _rust_res(root / "points" / "K2b-OX-gs.npz")
    ref = _res(DD9_ROOT / "solve" / "O-X-I2.npz", 500)
    fr_r, _ = dd9.perdir(rs)
    fr_ref, _ = dd9.perdir(ref)
    fl_r = [int((x != 0).sum()) for x in rs["f"]]
    fl_ref = [int((x != 0).sum()) for x in ref["f"]]
    allint = np.ones(rs["g"][0].shape[0], bool)
    prod = [compare_products({k: [v[d]] for k, v in rs.items()}, {k: [v[d]] for k, v in ref.items()},
                             allint, rs["g"][0].shape[1]) for d in range(4)]  # fmt: skip
    k2j = json.loads((root / "points" / "K2b-OX-gs.json").read_text())
    rec["K2b"] = {"fraction_rust": fr_r, "fraction_ref": fr_ref, "flagged_rust": fl_r, "flagged_ref": fl_ref,
                  "products": prod, "iterations": k2j["iterations"],
                  "flags_identical": all(np.array_equal(a, b) for a, b in zip(rs["f"], ref["f"], strict=True))}  # fmt: skip
    rec["K2b"]["pass"] = bool(
        k2j["iterations"] == CAP
        and max(abs(a - b) for a, b in zip(fr_r, fr_ref, strict=True))
        <= TOL_K2["fraction"]
        and all(
            abs(a - b) <= TOL_K2["flagged_rel"] * b
            for a, b in zip(fl_r, fl_ref, strict=True)
        )
        and all(p["max"] is None or p["max"] <= TOL_K2["product"] for p in prod)
    )
    # K3: Rust GS against the Rust default (DD8's O-X; K1c equals it) where
    # flag arrays agree, on cells converged in both.
    de = {
        "g": [d8["gains"][:, 0, :, d] for d in range(4)],
        "f": [d8["flags"][:, 0, :, d] for d in range(4)],
    }
    conv_d = np.asarray(d8["converged"])[:, 0]
    _, mg = dd9.perdir(rs)
    eq = same_flags(rs, de)
    nant = rs["g"][0].shape[1]
    p, q = np.triu_indices(nant, 1)
    vals = []
    for d in range(4):
        diff = np.abs(_products(rs["g"][d], nant) - _products(de["g"][d], nant))
        ok = mg[d][:, p] & mg[d][:, q] & conv_d[:, p, d] & conv_d[:, q, d] & eq[:, None]
        vals.append(diff[np.broadcast_to(ok[..., None], diff.shape)])
    v = np.concatenate(vals)
    rec["K3"] = {"intervals_equal_flags": int(eq.sum()), "cells": int(v.size),
                 "median": float(np.median(v)), "p99": float(np.percentile(v, 99)), "max": float(v.max())}  # fmt: skip
    rec["K3"]["pass"] = bool(
        rec["K3"]["median"] <= TOL_K3["median"] and rec["K3"]["p99"] <= TOL_K3["p99"]
    )
    write_json(root / "gates.json", rec)


# -- section 5: the loop ---------------------------------------------------------------


def psf(root, base):
    from rang import core_wgridder

    root = Path(root)
    ctx = base_ctx(root, base)
    c = ctx["c"]
    t0 = time.perf_counter()
    out = core_wgridder.fits_image(
        c["UVW"], c["freq"], np.ones(c["w_I"].shape, complex), c["w_I"], 2 * dd4.NX, 2 * dd4.NY,
        dd2.SCALE_ARCSEC, epsilon=dd4.EPS,
    )["psf"]  # fmt: skip
    (root / "psf").mkdir(parents=True, exist_ok=True)
    np.save(root / "psf" / f"{base}.npy", out)
    write_json(root / "psf" / f"{base}.json", {"base": base, "peak": float(out.max()),
                                                 "seconds": time.perf_counter() - t0})  # fmt: skip


def trusted_rows(ctx, gains, flags):
    """Section 5: per row, every direction's gain on both antennas unflagged
    with both hands' amplitudes in TRUST."""
    a = np.abs(gains[:, 0])  # (nint, nant, ndir, 2)
    ok = (flags[:, 0] == 0) & (a >= TRUST[0]).all(-1) & (a <= TRUST[1]).all(-1)
    ok = ok.all(-1)  # (nint, nant): all directions
    c, block = ctx["c"], ctx["block"]
    return ok[block, c["ANTENNA1"]] & ok[block, c["ANTENNA2"]]


def facet_image(ctx, r, gains, w):
    """dd4.facet_image with explicit Stokes I weights w (rows, chans)."""
    from rang import core_wgridder

    c, block, ndir = ctx["c"], ctx["block"], ctx["ndir"]
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    image = np.zeros((dd4.NY, dd4.NX))
    for f in range(ndir):
        gp, gq = gains[block, 0, a1, f], gains[block, 0, a2, f]
        vis = 0.5 * (np.conj(gp[:, None, 0]) * r[..., 0] * gq[:, None, 0]
                     + np.conj(gp[:, None, 1]) * r[..., 3] * gq[:, None, 1])  # fmt: skip
        img = core_wgridder.fits_image(c["UVW"], c["freq"], vis, w, dd4.NX, dd4.NY, dd2.SCALE_ARCSEC,
                                       epsilon=dd4.EPS)["dirty"]  # fmt: skip
        cf = dd2.correction(gp, gq, w, "a")
        sel = ctx["idx"] == f
        image[sel] = img[sel] / cf
    return image


def residual_image(ctx, models, gains, w):
    c, block = ctx["c"], ctx["block"]
    a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
    r = c["DATA"].astype(np.complex128)
    for f in range(ctx["ndir"]):
        gp, gq = gains[block, 0, a1, f], gains[block, 0, a2, f]
        r[..., 0] -= gp[:, None, 0] * models[:, :, f, 0] * np.conj(gq[:, None, 0])
        r[..., 3] -= gp[:, None, 1] * models[:, :, f, 3] * np.conj(gq[:, None, 1])
    return facet_image(ctx, r, gains, w)


def thermal_sigma(ctx, w, k):
    """The Stokes I image noise of weights w (dd5.noise_scale's formula)."""
    c = ctx["c"]
    flag = c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]
    ws = c["WEIGHT_SPECTRUM"].astype(np.float64)
    wxx = np.where(flag[..., 0], 0, ws[..., 0])
    wyy = np.where(flag[..., 3], 0, ws[..., 3])
    sel = w > 0
    var = 0.25 * k * (1 / wxx[sel] + 1 / wyy[sel])
    return float(np.sqrt((w[sel] ** 2 * var).sum()) / w[sel].sum())


def mad_sigma(img, mask):
    v = img[mask]
    return float(1.4826 * np.median(np.abs(v - np.median(v))))


def model_error(ctx, model, sky):
    idx = ctx["idx"]
    return {"abs_error": dd6.facet_abs_error(idx, model, sky, 4),
            "net_flux": [float(model[idx == f].sum()) for f in range(4)],
            "net_flux_truth": [float(sky[idx == f].sum()) for f in range(4)]}  # fmt: skip


# ALu and RLu: amendment A1 (post hoc), untrusted gains set to 1 in the images.
ARMS = {"AL": ("O", "solved"), "AT": ("O", "truth"), "RL": ("real", "solved"),
        "ALu": ("O", "unit"), "RLu": ("real", "unit")}  # fmt: skip
START = {"O": DD7_ROOT / "b" / "sky.npy", "real": DD7_ROOT / "models" / "RM.npy"}


def loop(root, arm):
    """Section 5 (AL, AT), section 6 (RL) and A1 (ALu, RLu). Resumable per
    cycle."""
    root = Path(root)
    base, gain_source = ARMS[arm]
    ctx = base_ctx(root, base)
    c = ctx["c"]
    k = float(json.loads((DD7_ROOT / "b" / "setup.json").read_text())["dd5"]["k"])
    psf_img = np.load(root / "psf" / f"{base}.npy")
    clean_interior = ctx["interior"] & (ctx["idx"] > 0)
    search = ctx["search"] & (ctx["idx"] > 0)
    sky = np.load(root / "O" / "sky.npy") if base == "O" else None
    truth = (
        np.load(root / "O" / "truth.npz")["gains"][:, None]
        if gain_source == "truth"
        else None
    )
    model = np.load(START[base])
    out = root / "loop" / arm
    for cyc in range(NCYCLE + 1):
        d = out / f"cycle-{cyc}"
        if (d / "info.json").exists():
            model = np.load(d / "next_model.npy") if cyc < NCYCLE else model
            print(f"{arm} cycle {cyc}: kept", flush=True)
            continue
        t0 = time.perf_counter()
        models = dd4.facet_models(ctx, model)
        info = {"arm": arm, "cycle": cyc, "seconds_predict": time.perf_counter() - t0}
        if sky is not None:
            info["model_error"] = model_error(ctx, model, sky)
        scored = cyc == 0 or cyc == NCYCLE
        need_solve = gain_source in ("solved", "unit") or cyc == NCYCLE
        gains = flags = None
        reuse = out.parent / arm[:-1] / "cycle-0"
        if gain_source == "unit" and cyc == 0:
            # A1: cycle 0 is the frozen arm's cycle-0 solve (the same solve).
            z = np.load(reuse / "gains.npz")
            gains, flags = z["gains"], z["flags"]
            info["solve"] = json.loads((reuse / "info.json").read_text())["solve"]
            info["solve_reused_from"] = str(reuse)
            d.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(d / "gains.npz", **{key: z[key] for key in z.files})
        elif need_solve:
            res = solve(ctx, models, "gauss-seidel", second=scored)
            sol = res["sol"]
            gains, flags = np.asarray(sol.gains), np.asarray(sol.flags)
            srec, conv = scores(ctx, models, sol, res.get("sol2"), k)
            info["solve"] = srec
            info["seconds_solve"] = res["seconds_solve"]
            info["seconds_second"] = res.get("seconds_second")
            d.mkdir(parents=True, exist_ok=True)
            save = {"gains": gains, "flags": flags}
            if scored:
                save.update(gains2=np.asarray(res["sol2"].gains), flags2=np.asarray(res["sol2"].flags),
                            converged=conv)  # fmt: skip
            np.savez_compressed(d / "gains.npz", **save)
            del res
        if cyc < NCYCLE or base == "real":
            # The image of this cycle: the minor cycle's input (k < NCYCLE),
            # and for the real arms also the final residual (reported rms).
            t1 = time.perf_counter()
            if gain_source == "truth":
                ig = truth
                w = c["w_I"]
                info["excluded_weight_share"] = 0.0
            elif gain_source == "unit":
                a = np.abs(gains)
                bad = (flags != 0) | (a < TRUST[0]).any(-1) | (a > TRUST[1]).any(-1)
                ig = np.where(bad[..., None], 1.0 + 0j, gains)
                w = c["w_I"]
                info["excluded_weight_share"] = 0.0
                info["untrusted_gain_share"] = [
                    float(bad[..., f].mean()) for f in range(4)
                ]
            else:
                ig = gains
                rows = trusted_rows(ctx, gains, flags)
                w = np.where(rows[:, None], c["w_I"], 0.0)
                info["excluded_weight_share"] = float(1 - w.sum() / c["w_I"].sum())
            resid = residual_image(ctx, models, ig, w)
            info["seconds_image"] = time.perf_counter() - t1
            info["residual_sigma_d1_d3"] = mad_sigma(resid, clean_interior)
            info["thermal_sigma"] = thermal_sigma(ctx, w, k)
            d.mkdir(parents=True, exist_ok=True)
            np.save(d / "residual.npy", resid.astype(np.float32))
            if cyc < NCYCLE:
                t2 = time.perf_counter()
                comps, _, hinfo = dd3.hogbom(resid, psf_img, clean_interior, search)
                info["hogbom"] = hinfo
                info["components_flux"] = float(sum(comps.values()))
                info["seconds_hogbom"] = time.perf_counter() - t2
                model = dd3.add_components(model, comps)
                np.save(d / "next_model.npy", model)
        del models
        info["seconds"] = time.perf_counter() - t0
        (d / "info.json").write_text(json.dumps(info, indent=1, default=float))
        print(
            f"{arm} cycle {cyc}: {json.dumps(info, default=float)[:1500]}", flush=True
        )


# -- readings --------------------------------------------------------------------------


def score(root):
    """Sections 5 and 6's frozen readings from the kept points and loops."""
    root = Path(root)
    rd = lambda p: json.loads(Path(p).read_text())
    rec = {}
    a0 = rd(root / "loop" / "AL" / "cycle-0" / "info.json")["solve"]
    ax = rd(root / "points" / "AX-OX-gs.json")
    e0, ex = a0["e_d"], ax["e_d"]
    rec["A0"] = a0
    rec["AX"] = {
        k: ax[k]
        for k in ("e_d", "e_over_ehat", "perdir_converged", "d3_amp", "iterations")
    }
    for arm in ("AL", "AT", "ALu"):  # ALu: A1, reported only
        f = root / "loop" / arm / f"cycle-{NCYCLE}" / "info.json"
        if not f.exists():
            continue
        s = rd(f)["solve"]
        e = s["e_d"]
        G = [(e0[d] - e[d]) / (e0[d] - ex[d]) for d in range(1, 4)]
        harm = any(e[d] > 1.2 * e0[d] for d in (2, 3))
        g1 = G[0]
        reading = ("closes" if g1 >= 0.5 and not harm else "partly" if g1 >= 0.2 and not harm
                   else "moves the error" if g1 >= 0.2 else "no")  # fmt: skip
        cycles = []
        for cyc in range(NCYCLE + 1):
            ci = rd(root / "loop" / arm / f"cycle-{cyc}" / "info.json")
            cycles.append({k: ci.get(k) for k in ("model_error", "hogbom", "excluded_weight_share", "untrusted_gain_share",
                                                    "residual_sigma_d1_d3", "thermal_sigma")}
                          | {"e_d": (ci.get("solve") or {}).get("e_d")})  # fmt: skip
        rec[arm] = {
            "final": s,
            "G_d1_d3": G,
            "harm": harm,
            "reading": reading,
            "cycles": cycles,
        }
    al, at = rec.get("AL", {}).get("reading"), rec.get("AT", {}).get("reading")
    if al and at:
        good = ("closes", "partly")
        rec["section5"] = ("the loop builds a better off-axis model from DD-corrected facet images on O"
                           if al in good else
                           "the rule can build the model, but the solved gains are too wrong to bootstrap it"
                           if at in good else
                           "a point-component Hogbom with the unit-gain PSF cannot build d1's model at this depth")  # fmt: skip
    r0f = root / "loop" / "RL" / "cycle-0" / "info.json"
    rlf = root / "loop" / "RL" / f"cycle-{NCYCLE}" / "info.json"
    if r0f.exists() and rlf.exists():
        r0, rl = rd(r0f), rd(rlf)
        m0 = min(r0["solve"]["perdir_converged"][1:])
        m1 = min(rl["solve"]["perdir_converged"][1:])
        amp = rl["solve"]["d3_amp"]
        rec["section6"] = {"R0_min_d1_d3": m0, "RL_min_d1_d3": m1, "lifts": m1 >= m0 + 0.20,
                           "tames_d3": amp["p99"] <= 3 and amp["max"] <= 10,
                           "supported_by_O": al in ("closes", "partly"),
                           "R0": r0, "RL": rl}  # fmt: skip
    write_json(root / "score.json", rec)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "abtest":
        abtest(argv[1])
    elif cmd == "abcompare":
        abcompare(argv[1], argv[2], argv[3])
    elif cmd == "fixedpoint":
        fixedpoint(argv[1])
    elif cmd == "point":
        sf = (
            float(argv[argv.index("--stop-fraction") + 1])
            if "--stop-fraction" in argv
            else 0.99
        )
        point(
            argv[1],
            argv[2],
            argv[3],
            argv[4],
            argv[5],
            stop_fraction=sf,
            second="--one" not in argv,
        )
    elif cmd == "gates":
        gates(argv[1])
    elif cmd == "psf":
        psf(argv[1], argv[2])
    elif cmd == "loop":
        loop(argv[1], argv[2])
    elif cmd == "score":
        score(argv[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
