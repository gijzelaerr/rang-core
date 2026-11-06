"""Host side of task C2c (research/c2c-bandpass.md): K as
`delay_and_offset`, the bandpass B and the chain K, G, B against QuartiCal
0.2.7 (class A), CASA 6.7.6.14 and A1's simulated truth (class T). Worktree
venv; every container step is one network-less run (`check_formats.docker`),
timed. Reuses `check_delay.py` and `check_gain.py`.

    python examples/check_bandpass.py kquartical <run>     # part 1, class A
    python examples/check_bandpass.py kcasa <run>          # part 1, C2b's CASA cases
    python examples/check_bandpass.py ktruth <run>         # part 1, class T
    python examples/check_bandpass.py kheld <run>          # part 1, held out
    python examples/check_bandpass.py bquartical <run>     # part 2, class A
    python examples/check_bandpass.py bcasa <run>          # part 2, against CASA
    python examples/check_bandpass.py btruth <run>         # part 2, class T
    python examples/check_bandpass.py bheld <run>          # part 2, held out
    python examples/check_bandpass.py chain <run>          # part 3 (and T)
    python examples/check_bandpass.py chainheld <run>      # part 3, held out

`<run>` is a fresh `/mnt/d/rang/outputs/c2c-<date>-NN`. Inputs are read in
place, read-only (paths as `check_delay.py`; `--h256 <dir>` the held-out
set, default `/mnt/d/rang/outputs/c2c-20261106-h256`; `--c2b02 <dir>` C2b's
run -02). Each subcommand writes `<run>/<subcommand>.json`; exit 0 only when
every gated item passes.
"""

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_delay as cd
import check_formats as cf
import check_gain as cg
from rang import cal_apply, cal_bandpass, cal_chain, cal_delay, cal_gain
from rang.formats import caltable

CLASS_A_TOL = 1e-6
K_TOL = {"median": 0.01, "p95": 0.03}
B_TOL = {"median": 7e-4, "p95": 3e-3}
TIME_TOL = 0.01
TRUTH_TOL = 1e-5
TWIN = {"stop_criterion": 1e-10, "stop_fraction": 1.0, "max_iterations": 200}


def paths(argv):
    p = cd.paths(argv)
    h = Path("/mnt/d/rang/outputs/c2c-20261106-h256")
    if "--h256" in argv:
        h = Path(argv[argv.index("--h256") + 1])
    c2b02 = Path("/mnt/d/rang/outputs/c2b-20261106-02")
    if "--c2b02" in argv:
        c2b02 = Path(argv[argv.index("--c2b02") + 1])
    o = p["slice"].parent
    p.update(
        {
            "a1k": p["a1"].parent.parent / "casa-small/truth.K",
            "d50k": Path(str(p["d50b"]).replace("truth.B", "truth.K")),
            "h256": h / "holdout256/a1-holdout256.ms",
            "h256twin": h / "holdout256/a1-holdout256-twin.ms",
            "h256truth": h / "holdout256/truth.npz",
            "h256rfi": h / "holdout256/a1-holdout256.rfi_mask.npz",
            "h256k": h / "casa-holdout256/truth.K",
            "h256b": h / "casa-holdout256/truth.B",
            "h256g": h / "casa-holdout256/truth.G",
            "c2b02": c2b02,
            "g0": o / "c.G0",
            "b0": o / "c.B0",
            "cms": o / "c.ms",
        }
    )
    return p


def sources(p):
    """Simulated sets: MS, truth, RFI mask (None for a twin), K, B, G."""
    a = (p["truth"], p["a1k"], p["a1b"], p["a1g"])
    d = (p["d50truth"], p["d50k"], p["d50b"], p["d50g"])
    h = (p["h256truth"], p["h256k"], p["h256b"], p["h256g"])
    return {
        "a1": (p["a1"], a[0], p["rfi"], *a[1:]),
        "a1twin": (p["twin"], a[0], None, *a[1:]),
        "d50": (p["d50"], d[0], p["d50rfi"], *d[1:]),
        "d50twin": (p["d50twin"], d[0], None, *d[1:]),
        "h256": (p["h256"], h[0], p["h256rfi"], *h[1:]),
        "h256twin": (p["h256twin"], h[0], None, *h[1:]),
    }


def stamp(name, r):
    print(name, "PASS" if r.get("pass") else "FAIL", json.dumps(r, default=float),
          flush=True)  # fmt: skip


def report(run, name, results, started, extra=None):
    out = {
        "cases": results,
        "timings": list(cf.TIMINGS),
        "seconds": time.perf_counter() - started,
        "pass": all(r.get("pass", False) for r in results.values()),
        **(extra or {}),
    }
    cg.write(run / f"{name}.json", out)
    return 0 if out["pass"] else 1


def model_array(ms, truth_path, field_id):
    """A1's parallactic reference model for one field's rows, in MS order."""
    tr = dict(np.load(truth_path))
    rows, values = cg.a1_model(ms, tr, [field_id], parang=True)
    return rows, values


def prepared(ms, truth, rfi, tabs, fields, solved):
    """Arrays for QuartiCal: DATA and A1's model with `tabs` pre-applied as
    rang does for a solve of type `solved` (lower types correct the data,
    the others corrupt the model), FLAG with the RFI mask."""
    c = cg.columns(ms, ["DATA", "FLAG", "TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID"])
    tr = dict(np.load(truth))
    rows, model = cg.a1_model(ms, tr, fields, parang=True)
    nchan = c["DATA"].shape[1]
    flag = c["FLAG"].copy()
    mask = None
    if rfi is not None:
        mask = cg.rfi_flags(ms, rfi, nchan)
        flag |= mask
    cdata = c["DATA"].copy()
    cmodel = np.zeros_like(cdata)
    freq = cg.chan_freq(ms)
    nant = cd.nants(ms)
    tables = [caltable.read(t) for t in tabs]
    for f in fields:
        idx = np.flatnonzero(c["FIELD_ID"][rows] == f)
        r = rows[idx]
        d, m = c["DATA"][r], model[idx]
        if tables:
            d, m, fl = cal_gain._pre_apply(
                d, m, flag[r], c["TIME"][r], c["ANTENNA1"][r], c["ANTENNA2"][r], freq,
                tables, "linear", nant, f, solved=solved,
            )  # fmt: skip
            if np.any(fl & ~flag[r]):
                raise SystemExit("the truth tables flag cells: needs its own FLAG")
        cdata[r] = d
        cmodel[r] = m
    return cdata.astype(np.complex64), cmodel.astype(np.complex64), mask, flag


def run_quartical(run, p, steps_inputs, cases, opts_for, label):
    """Write the QuartiCal copies and solve every case in one container."""
    src = sources(p)
    steps = [f"{cg.QC} -I /ex/oracle_gain.py qc-copy /src/slice.ms /run/qc/slice.ms"]
    mounts = [
        (run, "/run", "rw"),
        (HERE, "/ex", "ro"),
        (p["slice"], "/src/slice.ms", "ro"),
    ]
    for key, (base, cdata, cmodel, mask) in steps_inputs.items():
        np.savez(run / f"{key}-cdata.npz", values=cdata)
        np.savez(run / f"{key}-cmodel.npz", values=cmodel)
        extra = f"/run/{key}-cdata.npz CDATA /run/{key}-cmodel.npz CMODEL"
        if mask is not None:
            np.savez(run / f"{key}-rfi.npz", values=mask)
            extra += f" /run/{key}-rfi.npz FLAG"
        steps.append(
            f"{cg.QC} -I /ex/oracle_gain.py qc-copy /src/{base}.ms /run/qc/{key}.ms {extra}"
        )
        if (src[base][0], f"/src/{base}.ms", "ro") not in mounts:
            mounts.append((src[base][0], f"/src/{base}.ms", "ro"))
    for case in cases:
        name, key = case[0], case[1]
        steps.append(
            f"{cg.QC} -I /ex/oracle_gain.py qc-solve /run/qc/{key}.ms /run/qc/{name} "
            + " ".join(opts_for(case))
        )
    (run / "qc").mkdir()
    cf.TIMINGS.clear()
    cf.docker(cf.FORMATS_IMAGE, ["sh", "-c", " && ".join(steps)], mounts, label,
              env={"NUMBA_CACHE_DIR": "/run/numba"})  # fmt: skip


def scan_chunks(cols, rows, ti, solve_one):
    """`solve_one(rows, time_bin)` per scan (QuartiCal's chunks), in time
    order; returns the list of results."""
    scans = cols["SCAN_NUMBER"][rows]
    order = sorted(np.unique(scans), key=lambda s: cols["TIME"][rows][scans == s].min())
    out = []
    for s in order:
        r = rows[scans == s]
        integ = np.unique(cols["TIME"][r], return_inverse=True)[1].ravel()
        tb = integ // ti if ti else np.zeros(len(r), int)
        out.append(solve_one(r, tb))
    return out


def iter_equal(r_iter, r_frac, summary):
    qi = [int(np.ravel(x)[0]) for x in np.atleast_1d(summary["conv_iter"])]
    qp = [float(np.ravel(x)[0]) for x in np.atleast_1d(summary["conv_perc"])]
    ok = r_iter == qi and all(abs(a - b) <= 1e-12 for a, b in zip(r_frac, qp))
    return ok, qi, qp


QCOLS = ["WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2", "TIME",
         "SCAN_NUMBER", "FIELD_ID"]  # fmt: skip


def case_columns(p, key, inputs):
    src = sources(p)
    ms = p["slice"] if key == "slice" else src[inputs[key][0]][0]
    cols = cg.columns(ms, QCOLS + (["DATA", "MODEL_DATA"] if key == "slice" else []))
    if key == "slice":
        cols["MODEL"] = cols.pop("MODEL_DATA")
    else:
        _, cdata, cmodel, _ = inputs[key]
        cols["DATA"], cols["MODEL"] = cdata, cmodel
        cols["FLAG"] = cols["FLAG"] | (
            inputs[key][3] if inputs[key][3] is not None else False
        )
    return ms, cols


# --- part 1, K: class A -------------------------------------------------------


K_QC_CASES = [
    # name, inputs key, field, time interval
    ("A-K-slice-t1", "slice", None, 1),
    ("A-K-slice-t4", "slice", None, 4),
    ("A-K-slice-t0", "slice", None, 0),
    ("A-K-a1-f0-t1", "a1bg", 0, 1),
    ("A-K-a1-f2-t0", "a1bg", 2, 0),
    ("A-K-d50-twin-f0-t1", "d50twinbg", 0, 1),
    ("A-K-d50-f0-t0", "d50bg", 0, 0),
    ("A-K-d50-f2-t1", "d50bg", 2, 1),
    ("A-K-a1-noG-f0-t1", "a1b", 0, 1),
    ("A-K-d50-raw-f2-t0", "d50raw", 2, 0),
]


def k_inputs(p):
    """Inputs key: (source, CDATA, CMODEL, RFI mask)."""
    src = sources(p)
    spec = {
        "a1bg": ("a1", ["B", "G"]),
        "d50twinbg": ("d50twin", ["B", "G"]),
        "d50bg": ("d50", ["B", "G"]),
        "a1b": ("a1", ["B"]),
        "d50raw": ("d50", []),
    }
    out = {}
    for key, (base, terms) in spec.items():
        ms, truth, rfi, k, b, g = src[base]
        tabs = [{"K": k, "B": b, "G": g}[t] for t in terms]
        cdata, cmodel, mask, _ = prepared(ms, truth, rfi, tabs, [0, 2], "K")
        out[key] = (base, cdata, cmodel, mask)
    return out


def kquartical(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    inputs = k_inputs(p)
    qc_opts = [
        o.replace("K.type=delay", "K.type=delay_and_offset") for o in cd.QC_OPTIONS
    ]

    def opts(case):
        _name, key, fld, ti = case
        col, model = ("DATA", "MODEL_DATA") if key == "slice" else ("CDATA", "CMODEL")
        o = [f"input_ms.data_column={col}", f"input_model.recipe={model}",
             f"K.time_interval={ti}", *qc_opts]  # fmt: skip
        if fld is not None:
            o.append(f"input_ms.select_fields=[{fld}]")
        return o

    run_quartical(run, p, inputs, K_QC_CASES, opts, f"quartical x{len(K_QC_CASES)}")
    results = {}
    for case in K_QC_CASES:
        name, key, fld, ti = case
        out = run / "qc" / name
        summary = json.loads((out / "summary.json").read_text())
        ms, cols = case_columns(p, key, inputs)
        rows = np.arange(len(cols["TIME"]))
        if fld is not None:
            rows = rows[cols["FIELD_ID"] == fld]
        freq, nant = cg.chan_freq(ms), cd.nants(ms)

        def one(r, tb, cols=cols, nant=nant, freq=freq):
            t0 = time.perf_counter()
            s = cal_delay.solve(
                cols["DATA"][r], cols["MODEL"][r], cols["WEIGHT_SPECTRUM"][r],
                cols["FLAG"][r], cols["FLAG_ROW"][r], cols["ANTENNA1"][r],
                cols["ANTENNA2"][r], tb, nant=nant, chan_freq=freq, refant=0,
                casa_rules=False, return_gains=True, kind="delay_and_offset",
                offset_start=False,
            )  # fmt: skip
            return s, time.perf_counter() - t0

        sols = scan_chunks(cols, rows, ti, one)
        rd = np.concatenate([s.delays for s, _ in sols])
        ro = np.concatenate([s.offsets for s, _ in sols])
        rkf = np.concatenate([s.kernel_flags for s, _ in sols])
        rgf = np.concatenate([s.gain_flags for s, _ in sols])
        rg = np.concatenate([s.gains for s, _ in sols])
        names = summary["param_names"]
        params = np.load(out / "params.npy")  # (time, 1, ant, 4)
        di = [names.index(n) for n in ("delay_XX", "delay_YY")]
        oi = [names.index(n) for n in ("phase_offset_XX", "phase_offset_YY")]
        qd, qo = params[..., di] * 1e9, params[..., oi]
        qpf = np.load(out / "param_flags.npy") != 0
        qg = np.load(out / "gains.npy")
        qg = np.stack([qg[..., 0], qg[..., 3]], -1)
        qgf = np.load(out / "gain_flags.npy") != 0
        ok = np.broadcast_to(~qpf[..., None] & ~rkf[..., None], qd.shape)
        dd = np.abs(rd - qd)[ok]
        do = np.abs(np.angle(np.exp(1j * (ro - qo))))[ok]
        raw_offset = np.abs(ro - qo)[ok]
        ge = np.abs(rg - qg)[~qgf]
        prods = cg.product_compare(rg, np.repeat(rgf[..., None], 2, -1), qg,
                                   np.repeat(qgf[..., None], 2, -1))  # fmt: skip
        it_ok, qi, qp = iter_equal([s.iterations for s, _ in sols],
                                   [s.converged_fraction for s, _ in sols], summary)  # fmt: skip
        r = {
            "shape": list(qd.shape),
            "chunks": len(qi),
            "param_flags_exact": bool(np.array_equal(rkf, qpf)),
            "gain_flags_exact": bool(np.array_equal(rgf, qgf)),
            "flagged_gains": [int(rgf.sum()), int(qgf.sum())],
            "max_delay_abs_ns": float(dd.max()) if dd.size else None,
            "max_offset_abs_rad_mod_2pi": float(do.max()) if do.size else None,
            "max_offset_abs_rad_raw": float(raw_offset.max())
            if raw_offset.size
            else None,
            "max_gain_entry_abs": float(ge.max()) if ge.size else None,
            **{f"product_{k}": v for k, v in prods.items()},
            "iterations": [[s.iterations for s, _ in sols], qi],
            "converged_fraction": [[s.converged_fraction for s, _ in sols], qp],
            "max_abs_delay_ns": float(np.abs(qd).max()),
            "rang_seconds": sum(t for _, t in sols),
            "quartical_wall": summary.get("time_wall"),
            "quartical_rss_mb": summary.get("max_rss_mb"),
        }
        r["pass"] = bool(
            r["param_flags_exact"] and r["gain_flags_exact"]
            and (r["max_delay_abs_ns"] or 0) <= CLASS_A_TOL
            and (r["max_offset_abs_rad_mod_2pi"] or 0) <= CLASS_A_TOL
            and (r["max_gain_entry_abs"] or 0) <= CLASS_A_TOL
            and (r["product_max_abs"] or 0) <= CLASS_A_TOL and it_ok
        )  # fmt: skip
        results[name] = r
        stamp(name, r)
    return report(run, "kquartical", results, started, {"class": "A (K)"})


# --- part 1, K: against CASA ----------------------------------------------------


def k_against(msp, case, tables, ctab, out_dir, kind="delay_and_offset"):
    """Rang's K on `msp` as `case` against CASA's table `ctab`."""
    name, _, fid, solint, _, refant = case
    t0 = time.perf_counter()
    table, sol, info = cal_delay.gaincal(
        msp, field_id=fid, solint=solint, refant=refant, gaintable=tables,
        interp="linear", kind=kind,
    )  # fmt: skip
    seconds = time.perf_counter() - t0
    caltable.write(table, out_dir / f"{name}.rang.K")
    cols = cg.columns(msp, ["TIME", "FIELD_ID"])
    info["row_time"] = cols["TIME"][cols["FIELD_ID"] == fid]
    nant = sol.delays.shape[2]
    ctimes, cdl, cfl, cref = cd.k_table(ctab, nant)
    rtimes = np.asarray(table.column("TIME")).reshape(-1, nant)[:, 0]
    bins, index = cg.match_intervals(ctimes, info, rtimes)
    r = {"intervals": bins, "rang_seconds": seconds, "iterations": sol.iterations,
         "converged_fraction": sol.converged_fraction, "kind": kind}  # fmt: skip
    if not bins["all_matched_once"]:
        r["pass"] = False
        return r, table, sol
    ref = int(sol.refant_used[0])
    rd, rf = sol.delays[index][:, 0], sol.flags[index][:, 0]
    r["delays"] = cd.delay_compare(rd, rf, cdl, cfl, ref)
    r["max_abs_delay_ns"] = float(np.abs(cdl[~cfl]).max())
    diff = rf != cfl
    r["flags"] = {"rang_flagged": int(rf.sum()), "casa_flagged": int(cfl.sum()),
                  "differ": int(diff.sum())}  # fmt: skip
    rref = np.asarray(table.column("ANTENNA2")).reshape(-1, nant)[:, 0]
    r["antenna2_equal"] = bool(np.array_equal(rref[index], cref))
    off = np.abs(sol.offsets[index][:, 0][~rf])
    r["offset_abs_deg"] = {"median": float(np.degrees(np.median(off))) if off.size else None,
                           "max": float(np.degrees(off.max())) if off.size else None}  # fmt: skip
    d = r["delays"]
    ok = (
        r["flags"]["differ"] == 0
        and r["antenna2_equal"]
        and not bins["rang_without_casa"]
    )
    if d["delays"]:
        ok &= d["median_abs_ns"] <= K_TOL["median"] and d["p95_abs_ns"] <= K_TOL["p95"]
    r["pass"] = bool(ok)
    return r, table, sol


def kcasa(run, argv):
    """C2b's 13 CASA K cases and `c.K0`, on run -02's CASA tables and MS
    copies (read only), with rang's `delay_and_offset`."""
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    (run / "rang").mkdir()
    started = time.perf_counter()
    r02 = p["c2b02"]
    calls = json.loads((r02 / "gaincal.json").read_text())
    tables = {k: caltable.read(p[k]) for k in ("a1b", "a1g", "d50b", "d50g")}
    results = {}
    for case, call in zip(cd.B_CASES, calls):
        name, ms = case[0], case[1]
        if call["call"]["caltable"] != f"/run/casa/{name}.K":
            raise SystemExit(f"run -02's gaincal.json does not match at {name}")
        ctab = caltable.read(r02 / "casa" / f"{name}.K")
        r, _, _ = k_against(r02 / "casa" / f"{ms}.ms", case, [tables[k] for k in case[4]],
                            ctab, run / "rang")  # fmt: skip
        r["casa_seconds_run02"] = call["seconds"]
        results[name] = r
        stamp(name, r)
    rt = caltable.read(run / "rang" / "B-slice-120s.rang.K")
    _, rd, rf, _ = cd.k_table(rt, 4)
    _, cdl, cfl, _ = cd.k_table(caltable.read(p["k0"]), 4)
    r = {
        "delays": cd.delay_compare(rd, rf, cdl, cfl, 0),
        "flags_differ": int((rf != cfl).sum()),
    }
    d = r["delays"]
    r["pass"] = bool(rd.shape == cdl.shape and r["flags_differ"] == 0
                     and d["median_abs_ns"] <= K_TOL["median"] and d["p95_abs_ns"] <= K_TOL["p95"])  # fmt: skip
    results["B-slice-c.K0"] = r
    stamp("B-slice-c.K0", r)
    return report(run, "kcasa", results, started, {"class": "B (K)"})


# --- part 1, K: class T -----------------------------------------------------------


def truth_ms(p, key, fid):
    """The MS a class T solve reads and its model: the twin with A1's model
    passed as an array; the noisy sets as C2b's run -02 edited copies (A1's
    model in MODEL_DATA, RFI flags in FLAG), read only; holdout256 with the
    model array and its RFI mask must be prepared by the caller."""
    src = sources(p)
    ms = src[key][0]
    if src[key][2] is None:
        _rows, values = model_array(ms, src[key][1], fid)
        return ms, values
    edited = {"a1": p["c2b02"] / "casa/a1.ms", "d50": p["c2b02"] / "casa/d50.ms"}
    return edited[key], None


def centred_z(d, f, dtrue, err):
    """C2b's gauge-free bias test: delays centred on their antenna mean per
    interval and hand on both sides, over err_p."""
    okc = ~f
    cnt = okc.sum(1, keepdims=True)
    mr = np.where(okc, d, 0).sum(1, keepdims=True) / cnt
    mt = np.where(okc, dtrue[None], 0).sum(1, keepdims=True) / cnt
    ec = (d - mr) - (dtrue[None] - mt)
    z = (ec / np.where(err > 0, err, np.inf))[okc]
    lim = 3 * 1.2533 / np.sqrt(z.size)
    return {"n": int(z.size), "median_z": float(np.median(z)), "limit": float(lim),
            "std_z": float(np.std(z)), "pass": bool(abs(np.median(z)) <= lim)}  # fmt: skip


def ktruth(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    src = sources(p)
    results = {}
    for key in ("a1twin", "a1", "d50twin", "d50"):
        ms0, tr_path, rfi, _, btab, _ = src[key]
        tr = dict(np.load(tr_path))
        dtrue = tr["raw_tau_ns"] - tr["raw_tau_ns"][0][None]
        twin = rfi is None
        freq = cg.chan_freq(ms0)
        nu0 = float(np.mean(freq))
        for solint in ("int", "inf"):
            for fid in (0, 2):
                name = f"T-K-{key}-{solint}-f{fid}"
                ms, model = truth_ms(p, key, fid)
                t0 = time.perf_counter()
                _table, sol, _ = cal_delay.gaincal(
                    ms, field_id=fid, solint=solint, refant="m000", model=model,
                    gaintable=[caltable.read(btab)], interp="linear",
                    **(TWIN if twin else {}),
                )  # fmt: skip
                d, f = sol.delays[:, 0], sol.flags[:, 0]
                err = d - dtrue[None]
                r = {"intervals": d.shape[0], "flagged": int(f.sum()),
                     "iterations": sol.iterations, "seconds": time.perf_counter() - t0}  # fmt: skip
                if twin:
                    e = np.where(f, 0.0, err)
                    pa, pb = np.triu_indices(d.shape[1], 1)
                    de = (e[:, pa] - e[:, pb]) * 1e-9
                    phase = de[..., None] * 2 * np.pi * (freq - nu0)
                    worst = float(np.max(2 * np.abs(np.sin(phase / 2))))
                    r.update({"max_product_error": worst,
                              "max_delay_error_ns": float(np.abs(e).max())})  # fmt: skip
                    r["pass"] = bool(worst <= TRUTH_TOL and not f.any())
                else:
                    r["centred"] = centred_z(d, f, dtrue, sol.err[:, 0])
                    r["median_abs_error_ns"] = float(np.median(np.abs(err[~f])))
                    r["pass"] = r["centred"]["pass"]
                np.savez(run / f"{name}.npz", delays=sol.delays, flags=sol.flags,
                         err=sol.err, offsets=sol.offsets, truth=dtrue)  # fmt: skip
                results[name] = r
                stamp(name, r)
    return report(run, "ktruth", results, started, {"class": "T (K)"})


# --- CASA containers ---------------------------------------------------------------


def edit_copies(run, p, specs):
    """Container steps that copy each source MS into `/run/casa/<name>.ms`
    and apply its edits. `specs`: name -> (source key, edit dict or None,
    rfi True/False, fields for A1's model)."""
    edits = run / "edits"
    edits.mkdir(exist_ok=True)
    src = sources(p)
    steps, mounts = [], {}
    for name, (base, extra, rfi, fields) in specs.items():
        if base == "slice":
            ms = p["slice"]
        else:
            ms = src[base][0]
        mounts[base] = ms
        steps.append(f"cp -r /src/{base}.ms /run/casa/{name}.ms")
        spec = dict(extra or {})
        if fields:
            tr = dict(np.load(src[base][1]))
            rows, values = cg.a1_model(ms, tr, fields, parang=True)
            np.savez(edits / f"{name}-model.npz", rows=rows, values=values)
            spec["model"] = f"/run/edits/{name}-model.npz"
        flag = spec.pop("flag_array", None)
        if rfi:
            nchan = cg.chan_freq(ms).size
            mask = cg.rfi_flags(ms, src[base][2], nchan)
            flag = mask if flag is None else (flag | mask)
        if flag is not None:
            np.savez(edits / f"{name}-flag.npz", rows=np.arange(len(flag)), flag=flag)
            spec["flag"] = f"/run/edits/{name}-flag.npz"
        if spec:
            cg.write(edits / f"{name}.json", spec)
            steps.append(f"{cg.CASA} -I /ex/oracle_gain.py casa-edit /run/casa/{name}.ms /run/edits/{name}.json")  # fmt: skip
    return steps, [(ms, f"/src/{b}.ms", "ro") for b, ms in mounts.items()]


def casa_run(run, steps, mounts, spec, label):
    cg.write(run / "tasks-spec.json", spec)
    steps = steps + [f"{cg.CASA} -I /ex/oracle_gain.py casa-tasks /run/tasks-spec.json /run/tasks.json"]  # fmt: skip
    cf.TIMINGS.clear()
    cf.docker(cf.CASA_IMAGE, ["sh", "-c", " && ".join(steps)],
              [(run, "/run", "rw"), (HERE, "/ex", "ro")] + mounts, label)  # fmt: skip
    return json.loads((run / "tasks.json").read_text())


# --- part 1, K: held out --------------------------------------------------------------


K_HELD = [
    # name, MS copy, field, solint, tables, refant (as cd.B_CASES)
    ("H-K-d50-noapply-inf-f0", "d50", 0, "inf", [], "m000"),
    ("H-K-d50-noapply-int-f2", "d50", 2, "int", [], "m000"),
    ("H-K-a1-noapply-int-f2", "a1", 2, "int", [], "m000"),
    ("H-K-a1-noapply-60s-f0", "a1", 0, "60s", [], "m000"),
    ("H-K-h256-noapply-inf-f0", "h256", 0, "inf", [], "m000"),
    ("H-K-h256-noapply-int-f2", "h256", 2, "int", [], "m000"),
]


def kheld(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    (run / "casa").mkdir()
    started = time.perf_counter()
    specs = {k: (k, None, True, [0, 2]) for k in ("a1", "d50", "h256")}
    steps, mounts = edit_copies(run, p, specs)
    spec = [{"task": "gaincal", "args": {
        "vis": f"/run/casa/{ms}.ms", "caltable": f"/run/casa/{name}.K", "field": str(fid),
        "gaintype": "K", "solint": solint, "combine": "", "refant": refant,
        "refantmode": "flex", "minsnr": 3.0, "minblperant": 4, "gaintable": [],
        "interp": []}} for name, ms, fid, solint, _, refant in K_HELD]  # fmt: skip
    out = casa_run(run, steps, mounts, spec, "casa edits and held-out gaincal K")
    results = {}
    for case, call in zip(K_HELD, out):
        name = case[0]
        if call["error"] or not call["written"]:
            results[name] = {"pass": False, "casa_error": call["error"]}
            continue
        ctab = caltable.read(run / "casa" / f"{name}.K")
        r, _, _ = k_against(
            run / "casa" / f"{case[1]}.ms", case, [], ctab, run / "casa"
        )
        r["casa_seconds"] = call["seconds"]
        results[name] = r
        stamp(name, r)
    return report(run, "kheld", results, started, {"class": "B (K), held out"})


# --- part 2, B: class A ------------------------------------------------------------


B_QC_CASES = [
    ("A-B-slice", "slice", None),
    ("A-B-a1-f0", "a1kg", 0),
    ("A-B-d50-f2", "d50kg", 2),
]
B_QC_OPTIONS = [
    "input_ms.weight_column=WEIGHT_SPECTRUM",
    "solver.terms=[B]",
    "B.type=diag_complex",
    "B.time_interval=0",
    "B.freq_interval=1",
    "solver.iter_recipe=[50]",
    "solver.convergence_criteria=1e-7",
    "solver.reference_antenna=0",
    "solver.robust=false",
    "mad_flags.enable=false",
    "output.flags=false",
    "output.overwrite=false",
    "dask.threads=1",
    "solver.threads=1",
    "dask.scheduler=single-threaded",
]


def bquartical(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    src = sources(p)
    inputs = {}
    for key, base in (("a1kg", "a1"), ("d50kg", "d50")):
        ms, truth, rfi, k, _b, g = src[base]
        cdata, cmodel, mask, _ = prepared(ms, truth, rfi, [k, g], [0, 2], "B")
        inputs[key] = (base, cdata, cmodel, mask)

    def opts(case):
        _name, key, fld = case
        col, model = ("DATA", "MODEL_DATA") if key == "slice" else ("CDATA", "CMODEL")
        o = [
            f"input_ms.data_column={col}",
            f"input_model.recipe={model}",
            *B_QC_OPTIONS,
        ]
        if fld is not None:
            o.append(f"input_ms.select_fields=[{fld}]")
        return o

    run_quartical(run, p, inputs, B_QC_CASES, opts, f"quartical B x{len(B_QC_CASES)}")
    results = {}
    for case in B_QC_CASES:
        name, key, fld = case
        out = run / "qc" / name
        summary = json.loads((out / "summary.json").read_text())
        ms, cols = case_columns(p, key, inputs)
        rows = np.arange(len(cols["TIME"]))
        if fld is not None:
            rows = rows[cols["FIELD_ID"] == fld]
        nant = cd.nants(ms)

        def one(r, tb, cols=cols, nant=nant):
            t0 = time.perf_counter()
            s = cal_bandpass.solve(
                cols["DATA"][r], cols["MODEL"][r], cols["WEIGHT_SPECTRUM"][r],
                cols["FLAG"][r], cols["FLAG_ROW"][r], cols["ANTENNA1"][r],
                cols["ANTENNA2"][r], tb, nant=nant, refant=0, casa_rules=False,
            )  # fmt: skip
            return s, time.perf_counter() - t0

        sols = scan_chunks(cols, rows, 0, one)
        # Unrounded kernel gains for class A: re-solve through cal_gain to keep
        # complex128 (cal_bandpass stores complex64 as CASA writes).
        rg = np.concatenate([s.gains for s, _ in sols]).astype(complex)
        rf = np.concatenate([s.kernel_flags for s, _ in sols])
        qg = np.load(out / "gains.npy")
        qg = np.stack([qg[..., 0], qg[..., 3]], -1)
        qgf = np.load(out / "gain_flags.npy") != 0
        ge = np.abs(rg - qg)[~qgf]
        prods = cg.product_compare(rg, np.repeat(rf[..., None], 2, -1), qg,
                                   np.repeat(qgf[..., None], 2, -1))  # fmt: skip
        it_ok, qi, qp = iter_equal([s.iterations for s, _ in sols],
                                   [s.converged_fraction for s, _ in sols], summary)  # fmt: skip
        r = {
            "shape": list(qg.shape),
            "gain_flags_exact": bool(np.array_equal(rf, qgf)),
            "flagged_gains": [int(rf.sum()), int(qgf.sum())],
            "max_gain_entry_abs": float(ge.max()) if ge.size else None,
            **{f"product_{k}": v for k, v in prods.items()},
            "iterations": [[s.iterations for s, _ in sols], qi],
            "converged_fraction": [[s.converged_fraction for s, _ in sols], qp],
            "rang_seconds": sum(t for _, t in sols),
            "quartical_wall": summary.get("time_wall"),
            "note": "rang's gains are complex64 (the table's precision): entries "
            "carry up to about 6e-8 of rounding",
        }
        r["pass"] = bool(r["gain_flags_exact"] and (r["max_gain_entry_abs"] or 0) <= CLASS_A_TOL
                         and (r["product_max_abs"] or 0) <= CLASS_A_TOL and it_ok)  # fmt: skip
        results[name] = r
        stamp(name, r)
    return report(run, "bquartical", results, started, {"class": "A (B)"})


# --- part 2, B: against CASA ------------------------------------------------------------


def b_compare(msp, name, fid, kw, tables, ctab, out_dir):
    """Rang's B on `msp` against CASA's `ctab`: products per channel,
    flags (the minsnr and minblperant bands reported, not gated), filled
    channels, intervals and ANTENNA2."""
    t0 = time.perf_counter()
    table, sol, info = cal_bandpass.bandpass(msp, field_id=fid, refant="m000",
                                              gaintable=tables, interp="linear", **kw)  # fmt: skip
    seconds = time.perf_counter() - t0
    caltable.write(table, out_dir / f"{name}.rang.B")
    return b_versus(msp, fid, table, sol, info, ctab, kw.get("minblperant", 4), seconds)


def b_versus(msp, fid, table, sol, info, ctab, minbl, seconds=None):
    cols = cg.columns(
        msp, ["TIME", "FIELD_ID", "ANTENNA1", "ANTENNA2", "FLAG", "FLAG_ROW"]
    )
    sel = cols["FIELD_ID"] == fid
    info["row_time"] = cols["TIME"][sel]
    nant = sol.gains.shape[2]
    ctimes, cgn, cfl, csnr, cref = cal_bandpass.table_solutions(ctab, nant)
    rtimes = np.asarray(table.column("TIME")).reshape(-1, nant)[:, 0]
    bins, index = cg.match_intervals(ctimes, info, rtimes)
    r = {"intervals": bins, "rang_seconds": seconds, "iterations": sol.iterations,
         "converged_fraction": sol.converged_fraction}  # fmt: skip
    if not bins["all_matched_once"]:
        r["pass"] = False
        return r
    rg, rf, rs = sol.gains[index], sol.flags[index], sol.snr[index]
    filled = sol.filled[index]
    r["products"] = cg.product_compare(rg.astype(complex), rf, cgn.astype(complex), cfl,
                                       absolute=False)  # fmt: skip
    # Per (interval, channel, antenna) baseline counts with an unflagged cell.
    flag = cols["FLAG"][sel] | cols["FLAG_ROW"][sel][:, None, None]
    a1, a2 = cols["ANTENNA1"][sel], cols["ANTENNA2"][sel]
    tb = info["time_bin"]
    _nt, nchan = rg.shape[0], rg.shape[1]
    counts = np.zeros((len(rtimes), nchan, nant), int)
    good = ~flag.any(-1) & (a1 != a2)[:, None]
    for t in range(len(rtimes)):
        rows = tb == t
        for p_, q_ in {(int(x), int(y)) for x, y in zip(a1[rows], a2[rows])}:
            m = rows & (a1 == p_) & (a2 == q_)
            has = good[m].any(0)
            counts[t, :, p_] += has
            counts[t, :, q_] += has
    counts = counts[index]
    near = ((csnr >= 1.5) & (csnr <= 6.0)) | ((rs >= 1.5) & (rs <= 6.0))
    near |= (counts == minbl)[..., None]
    diff = rf != cfl
    r["flags"] = {"rang_flagged": int(rf.sum()), "casa_flagged": int(cfl.sum()),
                  "differ": int(diff.sum()), "differ_gated": int((diff & ~near).sum()),
                  "differ_reported": int((diff & near).sum()),
                  "rang_filled": int(filled.sum()),
                  "filled_flag_differ": int((diff & filled).sum())}  # fmt: skip
    r["refant"] = {"rang": sorted(set(sol.refant_used[index].tolist())),
                   "casa": sorted(set(cref.tolist())),
                   "equal": bool(np.array_equal(sol.refant_used[index], cref))}  # fmt: skip
    if filled.any():
        fp = cg.product_compare(np.where(filled, rg, 0).astype(complex), ~filled | rf,
                                cgn.astype(complex), cfl, absolute=False)  # fmt: skip
        r["filled_products"] = fp
    pr = r["products"]
    ok = (r["flags"]["differ_gated"] == 0 and r["refant"]["equal"]
          and not bins["rang_without_casa"])  # fmt: skip
    if pr["products"]:
        ok &= pr["median_rel"] <= B_TOL["median"] and pr["p95_rel"] <= B_TOL["p95"]
    r["pass"] = bool(ok)
    return r


def b_specs(p):
    """Edited MS copies for the B cases: name -> (source, extra edits, rfi,
    model fields)."""
    c = cg.columns(p["a1"], ["ANTENNA1", "ANTENNA2", "FIELD_ID", "DATA"])
    a1, a2, fld = c["ANTENNA1"], c["ANTENNA2"], c["FIELD_ID"]
    nrow, nchan = c["DATA"].shape[:2]
    gaps = np.zeros((nrow, nchan, 4), bool)
    gaps[:, 20:23] = True
    gaps[:, 40:50] = True
    refchan = np.zeros((nrow, nchan, 4), bool)
    refchan[(a1 == 0) | (a2 == 0), 10:13] = True
    snr_rows = np.flatnonzero(((a1 == 9) | (a2 == 9)) & (fld == 0)).tolist()
    return {
        "a1": ("a1", None, True, [0, 2]),
        "a1-gaps": ("a1", {"flag_array": gaps}, True, [0, 2]),
        "a1-refchan": ("a1", {"flag_array": refchan}, True, [0, 2]),
        "a1-snr": ("a1", {"sigma_scale": [[snr_rows, 20.0]]}, True, [0, 2]),
        "d50": ("d50", None, True, [0, 2]),
        "slice": ("slice", None, False, None),
    }


B_CASES = [
    # name, MS copy, field, settings, pre-apply keys
    ("B-B-slice", "slice", 1, {"solint": "inf", "combine": "", "minblperant": 3,
                               "fillgaps": 70}, ["k0", "g0"]),
    ("B-B-slice-nofill", "slice", 1, {"solint": "inf", "combine": "", "minblperant": 3,
                                      "fillgaps": 0}, ["k0", "g0"]),
    ("B-B-a1-f0-scan", "a1", 0, {"solint": "inf", "combine": "scan", "fillgaps": 0},
     ["a1k", "a1g"]),
    ("B-B-a1-f2", "a1", 2, {"solint": "inf", "combine": "", "fillgaps": 0}, ["a1k", "a1g"]),
    ("B-B-a1-gaps", "a1-gaps", 0, {"solint": "inf", "combine": "scan", "fillgaps": 5},
     ["a1k", "a1g"]),
    ("B-B-a1-refchan", "a1-refchan", 0, {"solint": "inf", "combine": "scan",
                                         "fillgaps": 0}, ["a1k", "a1g"]),
    ("B-B-a1-snr", "a1-snr", 0, {"solint": "inf", "combine": "scan", "fillgaps": 0},
     ["a1k", "a1g"]),
    ("B-B-d50-f0-scan", "d50", 0, {"solint": "inf", "combine": "scan", "fillgaps": 70},
     ["d50k", "d50g"]),
]  # fmt: skip
GUEST = {"k0": "/src/k0", "g0": "/src/g0", "a1k": "/src/a1.K", "a1g": "/src/a1.G",
         "d50k": "/src/d50.K", "d50g": "/src/d50.G", "h256k": "/src/h256.K",
         "h256g": "/src/h256.G"}  # fmt: skip


def bandpass_call(name, ms, fid, kw, tabs):
    return {"task": "bandpass", "args": {
        "vis": f"/run/casa/{ms}.ms", "caltable": f"/run/casa/{name}.B", "field": str(fid),
        "bandtype": "B", "solint": kw["solint"], "combine": kw["combine"], "refant": "m000",
        "minblperant": kw.get("minblperant", 4), "minsnr": 3.0, "solnorm": False,
        "fillgaps": kw["fillgaps"], "uvrange": kw.get("uvrange", ""),
        "gaintable": [GUEST[t] for t in tabs], "interp": ["linear"] * len(tabs)}}  # fmt: skip


def table_mounts(p, keys):
    return [(p[k], GUEST[k], "ro") for k in keys]


def run_b(run, p, specs, cases, label, out_name, started, extra_checks=None):
    (run / "casa").mkdir()
    steps, mounts = edit_copies(run, p, specs)
    keys = sorted({t for c in cases for t in c[4]})
    spec = [bandpass_call(n, ms, fid, kw, tabs) for n, ms, fid, kw, tabs in cases]
    out = casa_run(run, steps, mounts + table_mounts(p, keys), spec, label)
    results = {}
    for (name, ms, fid, kw, tabs), call in zip(cases, out):
        if call["error"] or not call["written"]:
            results[name] = {"pass": False, "casa_error": call["error"],
                             "written": call["written"]}  # fmt: skip
            stamp(name, results[name])
            continue
        ctab = caltable.read(run / "casa" / f"{name}.B")
        kwr = {k: v for k, v in kw.items()}
        r = b_compare(run / "casa" / f"{ms}.ms", name, fid, kwr,
                      [caltable.read(p[t]) for t in tabs], ctab, run / "casa")  # fmt: skip
        r["casa_seconds"] = call["seconds"]
        results[name] = r
        stamp(name, r)
    if extra_checks:
        results.update(extra_checks(run))
    return report(run, out_name, results, started, {"class": "B (B)"})


def layout_check(rang_path, casa_path):
    """The B table layout against a CASA-written B table."""
    rt, ct = caltable.read(rang_path), caltable.read(casa_path)
    out = {}
    for k in ("VisCal", "ParType"):
        out[k] = [rt.keywords.get(k), ct.keywords.get(k)]
    for col in ("CPARAM", "FLAG", "SNR", "PARAMERR"):
        out[col] = [list(np.asarray(rt.main[col][0]).shape),
                    list(np.asarray(ct.main[col][0]).shape)]  # fmt: skip
    rs, cs = rt.subtables["SPECTRAL_WINDOW"], ct.subtables["SPECTRAL_WINDOW"]
    out["chan_freq_equal"] = bool(np.array_equal(np.asarray(rs["CHAN_FREQ"][0]),
                                                 np.asarray(cs["CHAN_FREQ"][0])))  # fmt: skip
    out["antenna2"] = [sorted(set(rt.column("ANTENNA2").tolist())),
                       sorted(set(ct.column("ANTENNA2").tolist()))]  # fmt: skip
    out["interval"] = [sorted(set(rt.column("INTERVAL").tolist()))[:3],
                       sorted(set(ct.column("INTERVAL").tolist()))[:3]]  # fmt: skip
    out["time"] = [sorted(set(rt.column("TIME").tolist()))[:3],
                   sorted(set(ct.column("TIME").tolist()))[:3]]  # fmt: skip
    gated = ("VisCal", "ParType", "CPARAM", "FLAG", "SNR", "PARAMERR", "antenna2")
    out["pass"] = bool(
        all(out[k][0] == out[k][1] for k in gated) and out["chan_freq_equal"]
    )
    return out


def fill_reference_check(seed=20261106, n=400):
    """`fill_gaps` against a float32 Python transcription of CASA's
    `fillChanGapArray` on random flag patterns."""

    def casa_fill(sol, ok, maxgap):
        sol, ok = sol.copy(), ok.copy()
        n_ = len(sol)
        ich = 0
        while ich < n_ and not ok[ich]:
            ich += 1
        done = ich == n_
        while not done:
            while ich < n_ and ok[ich]:
                ich += 1
            if ich < n_:
                ch1, ch2 = ich - 1, ich + 1
                while ch2 < n_ and not ok[ch2]:
                    ch2 += 1
                if ch2 < n_:
                    dch = ch2 - ch1
                    if dch <= maxgap + 1:
                        a0 = np.float32(abs(sol[ch1]))
                        da = np.float32(np.float32(abs(sol[ch2])) - a0)
                        p0 = np.float32(np.angle(sol[ch1]))
                        dp = np.float32(np.float32(np.angle(sol[ch2])) - p0)
                        if float(dp) > np.pi:
                            dp = np.float32(float(dp) - 2 * np.pi)
                        if float(dp) < -np.pi:
                            dp = np.float32(float(dp) + 2 * np.pi)
                        while ich < ch2:
                            fch = np.float32(ich - ch1) / np.float32(dch)
                            a = a0 + da * fch
                            ph = p0 + dp * fch
                            sol[ich] = np.complex64(complex(np.cos(ph), np.sin(ph))) * a
                            ok[ich] = True
                            ich += 1
                        ich += 1
                    else:
                        ich = ch2 + 1
                else:
                    done = True
            else:
                done = True
            if ich >= n_:
                done = True
        return sol, ok

    rng = np.random.default_rng(seed)
    worst, flags_equal = 0.0, True
    for _ in range(n):
        nchan = int(rng.integers(3, 80))
        sol = rng.uniform(0.2, 2, nchan) * np.exp(
            1j * rng.uniform(-np.pi, np.pi, nchan)
        )
        sol = sol.astype(np.complex64)
        ok = rng.random(nchan) > rng.uniform(0.1, 0.8)
        maxgap = int(rng.integers(0, 10))
        want, wok = casa_fill(sol, ok, maxgap)
        g, f = cal_bandpass.fill_gaps(sol[None, :, None, None], ~ok[None, :, None, None],
                                      maxgap)  # fmt: skip
        flags_equal &= bool(np.array_equal(~f[0, :, 0, 0], wok))
        worst = max(worst, float(np.abs(g[0, :, 0, 0] - want).max()))
    return {"patterns": n, "flags_equal": flags_equal, "max_abs": worst,
            "pass": bool(flags_equal and worst <= 1e-6)}  # fmt: skip


def bcasa(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()

    def extra(run):
        out = {"fill-reference": fill_reference_check()}
        out["layout-c.B0"] = layout_check(run / "casa" / "B-B-slice.rang.B", p["b0"])
        out["layout-casa"] = layout_check(run / "casa" / "B-B-slice.rang.B",
                                          run / "casa" / "B-B-slice.B")  # fmt: skip
        for k in ("fill-reference", "layout-c.B0", "layout-casa"):
            stamp(k, out[k])
        return out

    return run_b(run, p, b_specs(p), B_CASES, "casa edits and bandpass", "bcasa",
                 started, extra)  # fmt: skip


# --- part 2, B: class T ---------------------------------------------------------------


def btruth(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    src = sources(p)
    results = {}
    for key in ("a1twin", "a1", "d50twin", "d50"):
        _ms0, tr_path, rfi, ktab, _, gtab = src[key]
        tr = dict(np.load(tr_path))
        bt = tr["raw_bandpass"]  # (ant, chan, 2)
        twin = rfi is None
        for fid, combine in ((0, "scan"), (2, "")):
            name = f"T-B-{key}-f{fid}"
            ms, model = truth_ms(p, key, fid)
            t0 = time.perf_counter()
            _table, sol, _ = cal_bandpass.bandpass(
                ms, field_id=fid, solint="inf", combine=combine, refant="m000",
                model=model, gaintable=[caltable.read(ktab), caltable.read(gtab)],
                interp="linear", **(TWIN if twin else {}),
            )  # fmt: skip
            g = sol.gains.astype(complex)  # (t, chan, ant, 2)
            f = sol.flags
            nant = g.shape[2]
            pa, pb = np.triu_indices(nant, 1)
            pr = g[:, :, pa] * np.conj(g[:, :, pb])
            pt = (bt[pa] * np.conj(bt[pb])).transpose(1, 0, 2)[None]
            ok = ~f[:, :, pa] & ~f[:, :, pb]
            r = {"intervals": g.shape[0], "flagged": int(f.sum()),
                 "iterations": sol.iterations, "seconds": time.perf_counter() - t0}  # fmt: skip
            if twin:
                worst = float(np.abs(pr - pt)[ok].max())
                r["max_product_error"] = worst
                r["pass"] = bool(worst <= TRUTH_TOL and not f.any())
            else:
                e = sol.err.astype(float)
                s = np.sqrt(np.abs(g[:, :, pb]) ** 2 * e[:, :, pa] ** 2
                            + np.abs(g[:, :, pa]) ** 2 * e[:, :, pb] ** 2)  # fmt: skip
                z = ((pr - pt) / np.where(s > 0, s, np.inf))[ok & (s > 0)]
                lim = 3 * 1.2533 / np.sqrt(z.size)
                r.update({"n": int(z.size), "median_re_z": float(np.median(z.real)),
                          "median_im_z": float(np.median(z.imag)), "limit": float(lim),
                          "std_re_z": float(np.std(z.real)), "std_im_z": float(np.std(z.imag))})  # fmt: skip
                r["pass"] = bool(
                    abs(r["median_re_z"]) <= lim and abs(r["median_im_z"]) <= lim
                )
            results[name] = r
            stamp(name, r)
    return report(run, "btruth", results, started, {"class": "T (B)"})


# --- part 2, B: held out, and CASA reads rang's table -----------------------------------


B_HELD = [
    ("H-B-h256-f0", "h256", 0, {"solint": "inf", "combine": "scan", "fillgaps": 70},
     ["h256k", "h256g"]),
    ("H-B-h256-f2", "h256", 2, {"solint": "inf", "combine": "", "fillgaps": 70},
     ["h256k", "h256g"]),
]  # fmt: skip


def bheld(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    specs = {"h256": ("h256", None, True, [0, 2])}
    return run_b(run, p, specs, B_HELD, "casa held-out bandpass", "bheld", started)


def breadback(run, argv):
    """CASA `applycal` of rang's B-B-d50-f0-scan table (from a `bcasa` run)
    against `rang.cal_apply` with the same table."""
    p = paths(argv)
    bc = Path(argv[0])
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    tab = bc / "casa" / "B-B-d50-f0-scan.rang.B"
    shutil.copytree(tab, run / "R-B.B")
    (run / "R-B.py").write_text(
        "from casatasks import applycal\n"
        "applycal(vis='/run/R-B.ms', field='0', gaintable=['/run/R-B.B'],\n"
        "         interp=['linear'], calwt=[False], applymode='calflag',\n"
        "         parang=False, flagbackup=False)\n"
    )
    cf.TIMINGS.clear()
    cf.docker(cf.CASA_IMAGE, ["sh", "-c", f"cp -r /src/d50.ms /run/R-B.ms && {cg.CASA} -I /run/R-B.py"],
              [(run, "/run", "rw"), (p["d50"], "/src/d50.ms", "ro")], "casa applycal of a rang B")  # fmt: skip
    c = cg.columns(run / "R-B.ms", ["DATA", "CORRECTED_DATA", "FLAG", "TIME", "ANTENNA1",
                                    "ANTENNA2", "FIELD_ID"])  # fmt: skip
    orig = cg.columns(p["d50"], ["FLAG"])["FLAG"]
    rows = c["FIELD_ID"] == 0
    t = caltable.read(run / "R-B.B")
    ours, flags = cal_apply.apply(
        c["DATA"][rows], orig[rows], c["TIME"][rows], c["ANTENNA1"][rows],
        c["ANTENNA2"][rows], cg.chan_freq(p["d50"]), [t], interp="linear", field_id=0,
    )  # fmt: skip
    theirs, tflag = c["CORRECTED_DATA"][rows], c["FLAG"][rows]
    ok = ~flags & ~tflag
    r = {"class_c": cal_apply.class_c(ours, theirs, ok),
         "flags_exact": bool(np.array_equal(flags, tflag))}  # fmt: skip
    r["pass"] = bool(r["class_c"]["pass"] and r["flags_exact"])
    stamp("R-B", r)
    return report(run, "breadback", {"R-B": r}, started)


# --- part 3, the chain --------------------------------------------------------------------


CHAIN_CASES = [
    # name, MS copy, field, K/G/B solint, B combine, minblperant, fillgaps, uvrange
    ("C-slice", "slice", 1, ("inf", "inf", "inf"), "", 3, 70, ""),
    ("C-a1-f0", "a1", 0, ("inf", "inf", "inf"), "scan", 4, 70, ">150"),
    ("C-d50-f0", "d50", 0, ("int", "int", "inf"), "scan", 4, 70, ""),
]
CHAIN_HELD = [("H-C-h256-f2", "h256", 2, ("inf", "inf", "inf"), "", 4, 70, ">150")]


def chain_calls(name, ms, fid, sol, bcomb, minbl, fill, uv):
    vis = f"/run/casa/{ms}.ms"
    base = {"vis": vis, "field": str(fid), "refant": "m000", "minsnr": 3.0,
            "minblperant": minbl}  # fmt: skip
    k = f"/run/casa/{name}.K"
    g = f"/run/casa/{name}.G"
    b = f"/run/casa/{name}.B"
    return [
        {"task": "gaincal", "args": {**base, "caltable": k, "gaintype": "K", "solint": sol[0],
                                     "combine": "", "refantmode": "flex", "gaintable": [],
                                     "interp": []}},
        {"task": "gaincal", "args": {**base, "caltable": g, "gaintype": "G", "calmode": "ap",
                                     "solint": sol[1], "combine": "", "refantmode": "flex",
                                     "uvrange": uv, "gaintable": [k], "interp": ["linear"],
                                     "solnorm": False}},
        {"task": "bandpass", "args": {**base, "caltable": b, "bandtype": "B", "solint": sol[2],
                                      "combine": bcomb, "solnorm": False, "fillgaps": fill,
                                      "uvrange": uv, "gaintable": [k, g],
                                      "interp": ["linear", "linear"]}},
    ]  # fmt: skip


def composite(msp, fid, tables):
    """Per row, channel and parallel hand `J_p J_q^*` of `tables` (unit
    model corrupted by `rang.cal_apply`) and its flags."""
    c = cg.columns(msp, ["TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "FLAG"])
    rows = (c["FIELD_ID"] == fid) & (c["ANTENNA1"] != c["ANTENNA2"])
    nchan = c["FLAG"].shape[1]
    ones = np.zeros((rows.sum(), nchan, 4), np.complex64)
    ones[..., 0] = ones[..., 3] = 1
    v, f = cal_apply.apply(ones, np.zeros(ones.shape, bool), c["TIME"][rows],
                           c["ANTENNA1"][rows], c["ANTENNA2"][rows], cg.chan_freq(msp),
                           tables, interp="linear", field_id=fid, direction="corrupt")  # fmt: skip
    return v[..., (0, 3)], f[..., (0, 3)]


def composite_compare(v1, f1, v2, f2):
    ok = ~f1 & ~f2
    rel = (np.abs(v1 - v2) / np.abs(v2))[ok]
    return {"cells": int(ok.sum()), "median_rel": float(np.median(rel)) if rel.size else None,
            "p95_rel": float(np.percentile(rel, 95)) if rel.size else None,
            "max_rel": float(rel.max()) if rel.size else None,
            "flags_exact": bool(np.array_equal(f1, f2))}  # fmt: skip


def chain_compare(msp, case, rang, ctabs):
    """Term by term and the composite."""
    _name, _, fid, _sol, _bcomb, minbl, _fill, _uv = case
    out = {}
    # K
    kt, ks, ki = rang["K"]
    cols = cg.columns(msp, ["TIME", "FIELD_ID"])
    ki["row_time"] = cols["TIME"][cols["FIELD_ID"] == fid]
    nant = ks.delays.shape[2]
    ctimes, cdl, cfl, _ = cd.k_table(ctabs["K"], nant)
    rt = np.asarray(kt.column("TIME")).reshape(-1, nant)[:, 0]
    bins, index = cg.match_intervals(ctimes, ki, rt)
    rk = {"intervals": bins}
    if bins["all_matched_once"]:
        rd, rf = ks.delays[index][:, 0], ks.flags[index][:, 0]
        rk["delays"] = cd.delay_compare(rd, rf, cdl, cfl, 0)
        rk["flags_differ"] = int((rf != cfl).sum())
        d = rk["delays"]
        rk["pass"] = bool(rk["flags_differ"] == 0 and d["median_abs_ns"] <= K_TOL["median"]
                          and d["p95_abs_ns"] <= K_TOL["p95"] and not bins["rang_without_casa"])  # fmt: skip
    else:
        rk["pass"] = False
    out["K"] = rk
    # G
    gt, gs, gi = rang["G"]
    gi["row_time"] = ki["row_time"]
    ctimes, cgn, cgf, _, cref = cg.casa_table_gains(ctabs["G"], nant)
    rt = np.asarray(gt.column("TIME")).reshape(-1, nant)[:, 0]
    bins, index = cg.match_intervals(ctimes, gi, rt)
    rg = {"intervals": bins}
    if bins["all_matched_once"]:
        rg["products"] = cg.product_compare(gs.gains[index], gs.flags[index], cgn, cgf,
                                            absolute=False)  # fmt: skip
        rg["flags_differ"] = int((gs.flags[index] != cgf).sum())
        rg["refant_equal"] = bool(np.array_equal(gs.refant_used[index], cref))
        pr = rg["products"]
        rg["pass"] = bool(rg["flags_differ"] == 0 and rg["refant_equal"]
                          and pr["median_rel"] <= B_TOL["median"] and pr["p95_rel"] <= B_TOL["p95"]
                          and not bins["rang_without_casa"])  # fmt: skip
    else:
        rg["pass"] = False
    out["G"] = rg
    # B
    bt, bs, bi = rang["B"]
    out["B"] = b_versus(msp, fid, bt, bs, bi, ctabs["B"], minbl)
    # Composite
    v1, f1 = composite(msp, fid, [kt, gt, bt])
    v2, f2 = composite(msp, fid, [ctabs["K"], ctabs["G"], ctabs["B"]])
    cc = composite_compare(v1, f1, v2, f2)
    cc["pass"] = bool(cc["flags_exact"] and cc["cells"]
                      and cc["median_rel"] <= B_TOL["median"] and cc["p95_rel"] <= B_TOL["p95"])  # fmt: skip
    out["composite"] = cc
    out["pass"] = bool(all(out[k]["pass"] for k in ("K", "G", "B", "composite")))
    return out


def rang_chain(msp, case, model=None, **kw):
    _name, _, fid, sol, bcomb, minbl, fill, uv = case
    return cal_chain.primary(
        msp, field_id=fid, refant="m000", k_solint=sol[0], g_solint=sol[1], b_solint=sol[2],
        b_combine=bcomb, uvrange=uv, minblperant=minbl, fillgaps=fill, model=model, **kw,
    )  # fmt: skip


def write_chain(out_dir, name, rang):
    for term, ext in (("K", "K"), ("G", "G"), ("B", "B")):
        caltable.write(rang[term][0], out_dir / f"{name}.rang.{ext}")


def run_chain(run, p, specs, cases, label):
    (run / "casa").mkdir()
    steps, mounts = edit_copies(run, p, specs)
    spec = [c for case in cases for c in chain_calls(*case)]
    out = casa_run(run, steps, mounts, spec, label)
    results = {}
    for i, case in enumerate(cases):
        name, ms, _fid = case[0], case[1], case[2]
        calls = out[3 * i : 3 * i + 3]
        if any(c["error"] or not c["written"] for c in calls):
            results[name] = {
                "pass": False,
                "casa": [(c["error"], c["written"]) for c in calls],
            }
            stamp(name, results[name])
            continue
        msp = run / "casa" / f"{ms}.ms"
        t0 = time.perf_counter()
        rang = rang_chain(msp, case)
        seconds = time.perf_counter() - t0
        write_chain(run / "casa", name, rang)
        ctabs = {
            t: caltable.read(run / "casa" / f"{name}.{t}") for t in ("K", "G", "B")
        }
        r = chain_compare(msp, case, rang, ctabs)
        r["rang_seconds"] = seconds
        r["casa_seconds"] = [c["seconds"] for c in calls]
        results[name] = r
        stamp(name, r)
    return results


def chain_ocasa(run, p):
    """C-slice-ocasa: rang's chain with O-CASA arm c's settings on work.ms's
    DATA and FLAG with c.ms's setjy model, against c.K0, c.G0, c.B0."""
    name = "C-slice-ocasa"
    case = (name, "slice", 1, ("120s", "120s", "inf"), "scan", 3, 70, "")
    model_all = cg.columns(p["cms"], ["MODEL_DATA"])["MODEL_DATA"]
    c = cg.columns(p["slice"], ["FIELD_ID"])
    model = model_all[c["FIELD_ID"] == 1]
    t0 = time.perf_counter()
    rang = rang_chain(p["slice"], case, model=model)
    seconds = time.perf_counter() - t0
    write_chain(run / "casa", name, rang)
    ctabs = {"K": caltable.read(p["k0"]), "G": caltable.read(p["g0"]),
             "B": caltable.read(p["b0"])}  # fmt: skip
    r = chain_compare(p["slice"], case, rang, ctabs)
    r["rang_seconds"] = seconds
    stamp(name, r)
    return {name: r}


def chain_truth(run, p):
    """T-C: rang's chain on the twins (composite against the truth's B, K,
    G composite, gated) and the noisy sets (reported)."""
    src = sources(p)
    out = {}
    for key in ("a1twin", "d50twin", "a1", "d50"):
        _ms0, _tr_path, rfi, ktab, btab, gtab = src[key]
        twin = rfi is None
        name = f"T-C-{key}-f0"
        case = (name, key, 0, ("inf", "inf", "inf"), "scan", 4, 70, "")
        ms, model = truth_ms(p, key, 0)
        t0 = time.perf_counter()
        rang = rang_chain(ms, case, model=model, **(TWIN if twin else {}))
        seconds = time.perf_counter() - t0
        v1, f1 = composite(ms, 0, [rang[t][0] for t in ("K", "G", "B")])
        truth_tabs = [caltable.read(t) for t in (ktab, gtab, btab)]
        v2, f2 = composite(ms, 0, truth_tabs)
        ok = ~f1 & ~f2
        absd = np.abs(v1 - v2)[ok]
        rel = absd / np.abs(v2[ok])
        r = {"cells": int(ok.sum()), "max_abs": float(absd.max()),
             "median_rel": float(np.median(rel)), "flags_rang": int(f1.sum()),
             "seconds": seconds}  # fmt: skip
        r["pass"] = bool(absd.max() <= TRUTH_TOL and not f1.any()) if twin else True
        r["gated"] = twin
        out[name] = r
        stamp(name, r)
    return out


def chain(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    specs = {"slice": ("slice", None, False, None), "a1": ("a1", None, True, [0, 2]),
             "d50": ("d50", None, True, [0, 2])}  # fmt: skip
    results = run_chain(run, p, specs, CHAIN_CASES, "casa chains K G B")
    results.update(chain_ocasa(run, p))
    results.update(chain_truth(run, p))
    return report(run, "chain", results, started, {"class": "chain"})


def chainheld(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    specs = {"h256": ("h256", None, True, [0, 2])}
    results = run_chain(run, p, specs, CHAIN_HELD, "casa held-out chain")
    return report(run, "chainheld", results, started, {"class": "chain, held out"})


def bextras(run, argv):
    """The checks `bcasa` runs after its cases (fill reference, table
    layout), on an earlier `bcasa` run's tables (`argv[0]`), into `run`."""
    p = paths(argv)
    bc = Path(argv[0])
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    cf.TIMINGS.clear()
    out = {"fill-reference": fill_reference_check()}
    out["layout-c.B0"] = layout_check(bc / "casa" / "B-B-slice.rang.B", p["b0"])
    out["layout-casa"] = layout_check(
        bc / "casa" / "B-B-slice.rang.B", bc / "casa" / "B-B-slice.B"
    )
    for k, v in out.items():
        stamp(k, v)
    return report(run, "bextras", out, started)


def main(argv):
    commands = {
        "bextras": bextras,
        "kquartical": kquartical, "kcasa": kcasa, "ktruth": ktruth, "kheld": kheld,
        "bquartical": bquartical, "bcasa": bcasa, "btruth": btruth, "bheld": bheld,
        "breadback": breadback, "chain": chain, "chainheld": chainheld,
    }  # fmt: skip
    if len(argv) < 3 or argv[1] not in commands:
        print(__doc__)
        return 2
    return commands[argv[1]](argv[2], argv[3:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
