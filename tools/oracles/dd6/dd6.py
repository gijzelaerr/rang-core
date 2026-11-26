# SPDX-License-Identifier: MIT
"""DD6: d0 left free, or a deeper d0 model, before the off-axis DD solve
(research/dd6-d0.md).

    python tools/oracles/dd6/dd6.py realms RUN                 # section 2, S1
    python tools/oracles/dd6/dd6.py noise RUN OUT.json         # k on the regenerated subset
    python tools/oracles/dd6/dd6.py deep MSRUN OUTDIR [SLOTS]  # the frozen GeMClean run
    python tools/oracles/dd6/dd6.py compose RUN BASE.npy D0.npy OUT.npy  # D0 in facet d0
    python tools/oracles/dd6/dd6.py modelcheck RUN OUT.json MODEL.npy... [--sky SKY.npy]
    python tools/oracles/dd6/dd6.py grid RUN TI MODEL OUT.json [--free]
    python tools/oracles/dd6/dd6.py parity GRID.json SCRATCH OUTDIR  # QuartiCal 0.2.7, cycle 0

RUN is a DD4 run directory (setup.json, psf.npy, header.json, facets.reg,
model0.npy): DD5's simulated ones, or the real one `realms` builds.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DD5_ROOT = Path("D:/rang/outputs/dd5-20261124")
CAL2 = Path("D:/rang/outputs/20261103-gemclean-heldout/real/cal2.ms")
CHANNELS = slice(96, 160)  # DD4 section 2's subset
# Section 3's frozen deep clean (the MS and -name are appended).
GEMCLEAN_ARGS = [
    "-size",
    "2880",
    "2880",
    "-scale",
    "3asec",
    "-weight",
    "natural",
    "-pol",
    "I",
    "-data-column",
    "DATA",
    "-wgridder-accuracy",
    "1e-6",
    "-niter",
    "2000000",
    "-mgain",
    "0.8",
    "-nmiter",
    "30",
    "-multiscale",
    "-auto-mask",
    "4",
    "-auto-threshold",
    "1.5",
]  # fmt: skip  (A1: no -local-rms, not implemented)
DEEP_TIMEOUT_S = 6 * 3600
PARITY_TOL = 1e-5
FRACTION_TOL = 1e-6


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd5 = _load("dd5", HERE.parent / "dd5" / "dd5.py")
dd4, dd3, dd2 = dd5.dd4, dd5.dd4.dd3, dd5.dd2


# -- pure helpers (unit-tested in tests/test_dd6.py) ----------------------------------


def compose(idx, base, d0_model):
    """Section 3: `d0_model` inside facet d0 (idx == 0), `base` elsewhere."""
    return np.where(np.asarray(idx) == 0, d0_model, base)


def pinned_for(free_d0):
    """The pinned directions of an arm: none when d0 is free, else d0."""
    return [] if free_d0 else [0]


def facet_abs_error(idx, model, sky, ndir):
    """Per facet, sum |model - sky| (section 3's M0 in simulation)."""
    d = np.abs(np.asarray(model) - np.asarray(sky))
    return [float(d[np.asarray(idx) == f].sum()) for f in range(ndir)]


def products(gains, p, q):
    """g_p conj(g_q) per pair: gains (t, f, ant, dir, hand) -> (t, f, pair, dir, hand)."""
    return gains[:, :, p] * np.conj(gains[:, :, q])


def parity_gates(
    gr, fr, go, fo, conv, frac_r, frac_o, tol=PARITY_TOL, ftol=FRACTION_TOL
):
    """Section 5's cycle-0 parity: flags equal, aggregate converged fractions
    equal to `ftol`, and gain products within `tol` over the pairs whose both
    cells rang counts as converged (`conv`, (t, f, ant, dir)); the maximum
    over all pairs unflagged in both, the median and the fraction within
    `tol` are reported."""
    gr, go = np.asarray(gr), np.asarray(go)
    fr, fo, conv = np.asarray(fr), np.asarray(fo), np.asarray(conv, bool)
    nant = gr.shape[2]
    p, q = np.triu_indices(nant, 1)
    d = np.abs(products(gr, p, q) - products(go, p, q))  # (t, f, pair, dir, hand)
    ok = (
        (fr[:, :, p] == 0)
        & (fr[:, :, q] == 0)
        & (fo[:, :, p] == 0)
        & (fo[:, :, q] == 0)
    )
    cv = conv[:, :, p] & conv[:, :, q]
    okb = np.broadcast_to(ok[..., None], d.shape)
    cvb = np.broadcast_to(cv[..., None], d.shape)
    on_conv = d[cvb]
    every = d[okb]
    per_dir = []
    for f in range(gr.shape[3]):
        v = d[:, :, :, f][okb[:, :, :, f]]
        w = d[:, :, :, f][cvb[:, :, :, f]]
        per_dir.append({"max_unflagged": float(v.max()) if v.size else None,
                        "median_unflagged": float(np.median(v)) if v.size else None,
                        "frac_le_tol": float((v <= tol).mean()) if v.size else None,
                        "max_converged": float(w.max()) if w.size else None,
                        "converged_pairs": int(w.size // max(d.shape[-1], 1))})  # fmt: skip
    flags_equal = bool(np.array_equal(fr != 0, fo != 0))
    fraction_ok = bool(abs(frac_r - frac_o) <= ftol)
    gains_ok = bool(on_conv.size == 0 or on_conv.max() <= tol)
    return {"flags_equal": flags_equal, "flag_cells_differ": int(((fr != 0) != (fo != 0)).sum()),
            "fraction_rang": float(frac_r), "fraction_oracle": float(frac_o),
            "fraction_equal": fraction_ok,
            "max_converged": float(on_conv.max()) if on_conv.size else None,
            "max_unflagged": float(every.max()) if every.size else None,
            "median_unflagged": float(np.median(every)) if every.size else None,
            "gains_ok": gains_ok, "per_direction": per_dir,
            "parity": bool(flags_equal and fraction_ok and gains_ok),
            "fraction_crosscheck_gt_0.01": bool(abs(frac_r - frac_o) > 0.01)}  # fmt: skip


# -- section 2: the regenerated real subset -------------------------------------------


def real_ms(run, template=DD5_ROOT / "a", cal2=CAL2):
    """Copy a DD5 simulated subset (the real layout, only DATA replaced),
    write cal2.ms's DATA channels 96-159 into it and check S1."""
    from rang import core_ms, core_ms_write

    t0 = time.perf_counter()
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    ms = run / "sub.ms"
    shutil.copytree(template / "sim.ms", ms)
    src = core_ms.open_table(str(cal2))
    dst = core_ms.open_table(str(ms))
    checks = {}
    for col in ("TIME", "ANTENNA1", "ANTENNA2", "UVW", "FLAG_ROW"):
        checks[col] = bool(np.array_equal(src.getcol(col), dst.getcol(col)))
    for col in ("FLAG", "WEIGHT_SPECTRUM"):
        checks[col] = bool(
            np.array_equal(src.getcol(col)[:, CHANNELS], dst.getcol(col))
        )
    data = np.ascontiguousarray(src.getcol("DATA")[:, CHANNELS])
    shape_ok = data.shape == dst.getcol("DATA").shape
    src.close()
    dst.close()
    rec = {"S1": checks, "S1_pass": bool(all(checks.values()) and shape_ok),
           "data_shape": list(data.shape), "template": str(template), "cal2": str(cal2)}  # fmt: skip
    if rec["S1_pass"]:
        t = core_ms_write.open_table(str(ms), readonly=False)
        t.putcol("DATA", data)
        t.close()
        back = core_ms.open_table(str(ms))
        rec["data_written_equal"] = bool(np.array_equal(back.getcol("DATA"), data))
        back.close()
    del data
    for f in ("psf.npy", "header.json", "facets.reg", "model0.npy"):
        shutil.copy(template / f, run / f)
    st = json.loads((template / "setup.json").read_text())
    st.pop("dd5", None)
    st["subms"] = str(ms)
    st["dd6"] = {"real": True, "from": str(cal2), "channels": [96, 159]}
    (run / "setup.json").write_text(json.dumps(st, indent=1))
    rec["seconds"] = time.perf_counter() - t0
    (run / "realms.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))
    if not rec["S1_pass"]:
        raise SystemExit("S1 failed: setup outcome")


# -- section 3: the deeper d0 model ----------------------------------------------------


def gemclean_exe():
    exe = Path(sys.executable).parent / (
        "gemclean.exe" if sys.platform == "win32" else "gemclean"
    )
    return str(exe) if exe.exists() else "gemclean"


def deep(run, outdir, slots=8):
    """Section 3's frozen GeMClean run on RUN's subset; saves deep.npy (DD4's
    grid and pixel order, Jy per pixel)."""
    run, outdir = Path(run), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    st = json.loads((run / "setup.json").read_text())
    cmd = [
        gemclean_exe(),
        *GEMCLEAN_ARGS,
        "-j",
        str(slots),
        "-name",
        str(outdir / "deep"),
        st["subms"],
    ]
    t0 = time.perf_counter()
    with open(outdir / "gemclean.log", "w", encoding="utf-8") as log:
        try:
            r = subprocess.run(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=DEEP_TIMEOUT_S,
                check=False,
            )
            rc, timed_out = r.returncode, False
        except subprocess.TimeoutExpired:
            rc, timed_out = None, True
    rec = {
        "cmd": cmd,
        "returncode": rc,
        "timed_out": timed_out,
        "seconds": time.perf_counter() - t0,
    }
    if rc == 0:
        m = dd2.read_fits(outdir / "deep-model.fits")
        assert m.shape == (dd4.NY, dd4.NX), m.shape
        np.save(outdir / "deep.npy", m)
        rec.update(flux=float(m.sum()), nonzero=int((m != 0).sum()))
    (outdir / "deep.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))
    if rc != 0:
        raise SystemExit(f"gemclean failed (rc {rc}, timed out {timed_out})")


def compose_cmd(run, base, d0, out):
    ctx_idx = facet_idx(Path(run))
    m = compose(ctx_idx, np.load(base), np.load(d0))
    np.save(out, m)
    print(json.dumps({"out": str(out), "flux": float(m.sum()),
                      "flux_d0": float(m[ctx_idx == 0].sum())}))  # fmt: skip


def facet_idx(run):
    st = json.loads((run / "setup.json").read_text())
    l, m = dd2.pixel_lm()
    idx, _ = dd2.facet_index_and_margin(l, m, np.array(st["centres"]))
    return idx


def model_check(run, out, models, sky=None):
    """Section 3's M0: per model, the unit-gain residual image's rms over
    facet d0's interior (plain and robust) and, with `sky`, sum |model - sky|
    per facet."""
    run = Path(run)
    ctx = dd4.context(run)
    c = ctx["c"]
    nint = int(ctx["block"].max()) + 1
    nant = len(c["ant_names"])
    ones = np.ones((nint, 1, nant, ctx["ndir"], 2), complex)
    sel = ctx["interior"] & (ctx["idx"] == 0)
    s = np.load(sky) if sky else None
    rec = {"run": str(run), "sky": str(sky) if sky else None, "models": {}}
    for mp in models:
        t0 = time.perf_counter()
        m = np.load(mp)
        fm = dd4.facet_models(ctx, m)
        res = dd4.residual_image(ctx, fm, ones)
        del fm
        v = res[sel]
        r = {"rms_d0": float(np.sqrt(np.mean(v * v))),
             "robust_rms_d0": float(1.4826 * np.median(np.abs(v - np.median(v)))),
             "flux": float(m.sum()), "flux_d0": float(m[ctx["idx"] == 0].sum())}  # fmt: skip
        if s is not None:
            r["abs_error_per_facet"] = facet_abs_error(ctx["idx"], m, s, ctx["ndir"])
        r["seconds"] = time.perf_counter() - t0
        np.save(
            Path(out).with_name(Path(out).stem + "-" + Path(mp).stem + "-residual.npy"),
            res.astype(np.float32),
        )
        rec["models"][str(mp)] = r
        print(json.dumps({str(mp): r}), flush=True)
    Path(out).write_text(json.dumps(rec, indent=1))


# -- section 5: cycle-0 parity against QuartiCal 0.2.7 ---------------------------------


def parity(grid_json, scratch, outdir):
    """The grid point's solve with refant=0 in rang, and QuartiCal 0.2.7's
    (DD4 arm O steps 0-1) on the same subset, model, interval and pins."""
    from rang import cal_gain

    g = json.loads(Path(grid_json).read_text())
    run, ti, pinned = Path(g["run"]), int(g["ti"]), list(g["pinned"])
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    ctx = dd4.context(run, ti=ti)
    ctx["pinned"] = pinned
    c = ctx["c"]
    model = np.load(g["model"])
    t0 = time.perf_counter()
    fm = dd4.facet_models(ctx, model)
    args = (c["DATA"], fm, c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"],
            c["ANTENNA1"], c["ANTENNA2"], ctx["block"])  # fmt: skip
    kw = {"nant": len(c["ant_names"]), "refant": 0, "pinned_directions": pinned,
          "calmode": "ap", "phase_last_direction_gain": False}  # fmt: skip
    sol = cal_gain.solve_dd(*args, **kw, **dict(dd4.CAP, max_iterations=int(g["cap"])))
    del fm
    t1 = time.perf_counter()
    gr, fr = np.asarray(sol.gains), np.asarray(sol.flags)
    np.savez_compressed(outdir / "rang.npz", gains=gr, flags=fr)
    hdr = json.loads((run / "header.json").read_text())
    d = outdir / "oracle"
    d.mkdir(exist_ok=True)
    for f in range(ctx["ndir"]):
        dd3.write_fits(
            d / f"facet{f}-model.fits", np.where(ctx["idx"] == f, model, 0.0), hdr
        )
    pins = "[" + ",".join(map(str, pinned)) + "]"
    dd4.run_wsl("step4_o0.sh", dd3.to_wsl(ctx["st"]["subms"]), scratch, ctx["ndir"])
    dd4.run_wsl(
        "step4_o1.sh",
        scratch,
        dd3.to_wsl(d),
        ctx["ndir"],
        pins,
        "diag_complex",
        int(g["cap"]),
        ti,
    )
    go, fo, qinfo = dd3.qc_gains(d / "gains")
    t2 = time.perf_counter()
    np.savez_compressed(outdir / "oracle.npz", gains=go, flags=fo)
    conv = np.load(Path(grid_json).with_suffix(".npz"))["converged"]
    # The grid solve (refant=None) and this one (refant=0) differ only by the
    # reference rotation; their products are reported as a check.
    gg = np.load(Path(grid_json).with_suffix(".npz"))["gains"]
    nant = gr.shape[2]
    p, q = np.triu_indices(nant, 1)
    okf = (fr[:, :, p] == 0) & (fr[:, :, q] == 0)
    dref = np.abs(products(gr, p, q) - products(gg, p, q))[
        np.broadcast_to(okf[..., None], (*okf.shape, 2))
    ]
    rec = parity_gates(gr, fr, go, fo, conv, sol.converged_fraction, qinfo["fraction"])
    rec.update(grid=str(grid_json), run=str(run), ti=ti, pinned=pinned, model=g["model"],
               iterations_rang=sol.iterations, iterations_oracle=qinfo["iterations"],
               refant0_vs_grid_products_max=float(dref.max()) if dref.size else None,
               seconds_rang=t1 - t0, seconds_oracle=t2 - t1)  # fmt: skip
    (outdir / "parity.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "realms":
        real_ms(argv[1])
    elif cmd == "noise":
        dd5.noise_scale(argv[2], run=Path(argv[1]), m0c=DD5_ROOT / "b" / "sky.npy")
    elif cmd == "deep":
        deep(argv[1], argv[2], int(argv[3]) if len(argv) > 3 else 8)
    elif cmd == "compose":
        compose_cmd(argv[1], argv[2], argv[3], argv[4])
    elif cmd == "modelcheck":
        sky = argv[argv.index("--sky") + 1] if "--sky" in argv else None
        rest = [
            a
            for i, a in enumerate(argv[3:], 3)
            if a != "--sky" and argv[i - 1] != "--sky"
        ]
        model_check(argv[1], argv[2], rest, sky)
    elif cmd == "grid":
        dd5.grid_point(argv[1], "diag_complex", int(argv[2]), argv[3], argv[4],
                       pinned=pinned_for("--free" in argv))  # fmt: skip
    elif cmd == "parity":
        parity(argv[1], argv[2], argv[3])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
