"""Host side of task C2b (research/c2b-delay.md): the delay term K against
QuartiCal 0.2.7 `delay` (class A), CASA 6.7.6.14 `gaincal(gaintype='K')`
and A1's simulated truth (class T), and CASA applying rang's K tables.
Worktree venv; every container step is one network-less run
(`check_formats.docker`), timed.

    python examples/check_delay.py quartical <run>          # class A
    python examples/check_delay.py casa <run>               # against CASA
    python examples/check_delay.py truth <run>              # class T
    python examples/check_delay.py readback <run> <casa-run>   # CASA applies rang's tables

`<run>` is a fresh `/mnt/d/rang/outputs/c2b-<date>-NN`. Inputs are read in
place, read-only: O-CASA's slice and `c.K0` (`~/Github/rang/outputs`, or
`--outputs <dir>`), A1's small version (`--a1 <dir>`) and the delay50
version (`--d50 <dir>`, default `/mnt/d/rang/outputs/c2b-20261106-d50`, made
with `examples/a1_simtruth.py generate delay50` and `tools/a1_checks.sh`).
Each subcommand writes `<run>/<subcommand>.json`; exit 0 only when every
gated item passes.
"""

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_formats as cf
import check_gain as cg
from rang import cal_apply, cal_delay, cal_gain
from rang.formats import caltable

QC_OPTIONS = [
    "input_ms.weight_column=WEIGHT_SPECTRUM",
    "solver.terms=[K]",
    "K.type=delay",
    "K.freq_interval=0",
    "K.initial_estimate=true",
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
# Class A (section 4): name, source, field (None: all), time interval.
QC_CASES = [
    ("A-slice-t1", "slice", None, 1),
    ("A-slice-t4", "slice", None, 4),
    ("A-slice-t0", "slice", None, 0),
    ("A-a1-f0-t1", "a1", 0, 1),
    ("A-a1-f2-t0", "a1", 2, 0),
    ("A-d50-twin-f0-t1", "d50twin", 0, 1),
    ("A-d50-f0-t0", "d50", 0, 0),
    ("A-d50-f2-t1", "d50", 2, 1),
]
A = ["a1b", "a1g"]
D = ["d50b", "d50g"]
# Against CASA (section 4): name, MS copy, field, solint, tables, refant.
B_CASES = [
    ("B-slice-inf", "slice", 1, "inf", [], "m000"),
    ("B-slice-120s", "slice", 1, "120s", [], "m000"),
    ("B-slice-int", "slice", 1, "int", [], "m000"),
    ("B-a1-inf-f0", "a1", 0, "inf", A, "m000"),
    ("B-a1-inf-f2", "a1", 2, "inf", A, "m000"),
    ("B-a1-int-f0", "a1", 0, "int", A, "m000"),
    ("B-a1-60s-f2", "a1", 2, "60s", A, "m000"),
    ("B-a1-noapply-inf-f0", "a1", 0, "inf", [], "m000"),
    ("B-a1-refant-flag", "a1-refant", 0, "int", A, "m000"),
    ("B-a1-refant5-inf-f2", "a1", 2, "inf", A, "m020"),
    ("B-d50-inf-f0", "d50", 0, "inf", D, "m000"),
    ("B-d50-inf-f2", "d50", 2, "inf", D, "m000"),
    ("B-d50-int-f2", "d50", 2, "int", D, "m000"),
]
CLASS_A_TOL = 1e-6
CASA_TOL = {"median": 0.01, "p95": 0.03}
TIME_TOL = 0.01
TRUTH_TOL = 1e-5


def paths(argv):
    p = cg.paths(argv)
    d50 = Path("/mnt/d/rang/outputs/c2b-20261106-d50")
    if "--d50" in argv:
        d50 = Path(argv[argv.index("--d50") + 1])
    a1 = p["a1"].parent.parent
    p.update(
        {
            "a1g": a1 / "casa-small/truth.G",
            "d50": d50 / "delay50/a1-delay50.ms",
            "d50twin": d50 / "delay50/a1-delay50-twin.ms",
            "d50truth": d50 / "delay50/truth.npz",
            "d50rfi": d50 / "delay50/a1-delay50.rfi_mask.npz",
            "d50b": d50 / "casa-delay50/truth.B",
            "d50g": d50 / "casa-delay50/truth.G",
        }
    )
    return p


def sources(p):
    """Simulated sets: MS, truth, RFI mask (None for a twin), B and G."""
    return {
        "a1": (p["a1"], p["truth"], p["rfi"], p["a1b"], p["a1g"]),
        "a1twin": (p["twin"], p["truth"], None, p["a1b"], p["a1g"]),
        "d50": (p["d50"], p["d50truth"], p["d50rfi"], p["d50b"], p["d50g"]),
        "d50twin": (p["d50twin"], p["d50truth"], None, p["d50b"], p["d50g"]),
    }


def nants(ms):
    with cg.core_ms.open_table(Path(ms) / "ANTENNA") as t:
        return len(t.getcol("NAME"))


def pre_arrays(ms, truth, rfi, btab, gtab, fields):
    """A1-style inputs for K: DATA corrected by truth B, A1's parallactic
    reference model corrupted by truth G (rang's pre-apply), FLAG with the
    RFI mask. Rows of other fields keep DATA and a zero model."""
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
    tabs = [caltable.read(btab), caltable.read(gtab)]
    freq = cg.chan_freq(ms)
    nant = nants(ms)
    for f in fields:
        idx = np.flatnonzero(c["FIELD_ID"][rows] == f)
        r = rows[idx]
        d, m, fl = cal_gain._pre_apply(
            c["DATA"][r], model[idx], flag[r], c["TIME"][r], c["ANTENNA1"][r],
            c["ANTENNA2"][r], freq, tabs, "linear", nant, f, solved="K",
        )  # fmt: skip
        if np.any(fl & ~flag[r]):
            raise SystemExit(
                "the truth tables flag cells: CDATA would need its own FLAG"
            )
        cdata[r] = d
        cmodel[r] = m
    return cdata.astype(np.complex64), cmodel.astype(np.complex64), mask, flag


# --- class A ------------------------------------------------------------------


def rang_chunks(cols, rows, ti, freq, nant):
    """Rang's delay solve per scan (QuartiCal's chunks), stacked in time."""
    out = {
        "delays": [],
        "kflags": [],
        "gflags": [],
        "gains": [],
        "iter": [],
        "frac": [],
    }
    scans = cols["SCAN_NUMBER"][rows]
    order = sorted(np.unique(scans), key=lambda s: cols["TIME"][rows][scans == s].min())
    seconds = 0.0
    for s in order:
        r = rows[scans == s]
        integ = np.unique(cols["TIME"][r], return_inverse=True)[1].ravel()
        tb = integ // ti if ti else np.zeros(len(r), int)
        t0 = time.perf_counter()
        sol = cal_delay.solve(
            cols["DATA"][r], cols["MODEL"][r], cols["WEIGHT_SPECTRUM"][r], cols["FLAG"][r],
            cols["FLAG_ROW"][r], cols["ANTENNA1"][r], cols["ANTENNA2"][r], tb, nant=nant,
            chan_freq=freq, refant=0, casa_rules=False, return_gains=True,
        )  # fmt: skip
        seconds += time.perf_counter() - t0
        out["delays"].append(sol.delays)
        out["kflags"].append(sol.kernel_flags)
        out["gflags"].append(sol.gain_flags)
        out["gains"].append(sol.gains)
        out["iter"].append(sol.iterations)
        out["frac"].append(sol.converged_fraction)
    for k in ("delays", "kflags", "gflags", "gains"):
        out[k] = np.concatenate(out[k])
    out["seconds"] = seconds
    return out


def quartical(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    src = sources(p)
    needed = sorted({s for _, s, _, _ in QC_CASES if s != "slice"})
    inputs = {}
    steps = [f"{cg.QC} -I /ex/oracle_gain.py qc-copy /src/slice.ms /run/qc/slice.ms"]
    for key in needed:
        ms, truth, rfi, btab, gtab = src[key]
        cdata, cmodel, mask, flag = pre_arrays(ms, truth, rfi, btab, gtab, [0, 2])
        inputs[key] = (cdata, cmodel, flag)
        np.savez(run / f"{key}-cdata.npz", values=cdata)
        np.savez(run / f"{key}-cmodel.npz", values=cmodel)
        extra = f"/run/{key}-cdata.npz CDATA /run/{key}-cmodel.npz CMODEL"
        if mask is not None:
            np.savez(run / f"{key}-rfi.npz", values=mask)
            extra += f" /run/{key}-rfi.npz FLAG"
        steps.append(
            f"{cg.QC} -I /ex/oracle_gain.py qc-copy /src/{key}.ms /run/qc/{key}.ms {extra}"
        )
    for name, key, fld, ti in QC_CASES:
        col, model = ("DATA", "MODEL_DATA") if key == "slice" else ("CDATA", "CMODEL")
        opts = [
            f"input_ms.data_column={col}",
            f"input_model.recipe={model}",
            f"K.time_interval={ti}",
            *QC_OPTIONS,
        ]
        if fld is not None:
            opts.append(f"input_ms.select_fields=[{fld}]")
        steps.append(
            f"{cg.QC} -I /ex/oracle_gain.py qc-solve /run/qc/{key}.ms /run/qc/{name} "
            + " ".join(opts)
        )
    (run / "qc").mkdir()
    mounts = [
        (run, "/run", "rw"),
        (HERE, "/ex", "ro"),
        (p["slice"], "/src/slice.ms", "ro"),
    ]
    mounts += [(src[k][0], f"/src/{k}.ms", "ro") for k in needed]
    cf.TIMINGS.clear()
    cf.docker(
        cf.FORMATS_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        mounts,
        f"quartical x{len(QC_CASES)}",
        env={"NUMBA_CACHE_DIR": "/run/numba"},
    )
    names = ["WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2", "TIME",
             "SCAN_NUMBER", "FIELD_ID"]  # fmt: skip
    results = {}
    for name, key, fld, ti in QC_CASES:
        out = run / "qc" / name
        summary = json.loads((out / "summary.json").read_text())
        ms = p["slice"] if key == "slice" else src[key][0]
        cols = cg.columns(
            ms, names + (["DATA", "MODEL_DATA"] if key == "slice" else [])
        )
        if key == "slice":
            cols["MODEL"] = cols.pop("MODEL_DATA")
        else:
            cols["DATA"], cols["MODEL"], cols["FLAG"] = inputs[key]
        rows = np.arange(len(cols["TIME"]))
        if fld is not None:
            rows = rows[cols["FIELD_ID"] == fld]
        freq = cg.chan_freq(ms)
        nant = nants(ms)
        r = rang_chunks(cols, rows, ti, freq, nant)
        qd = np.load(out / "params.npy") * 1e9  # (time, 1, ant, 2) ns
        qpf = np.load(out / "param_flags.npy") != 0
        qg = np.load(out / "gains.npy")
        qg = np.stack([qg[..., 0], qg[..., 3]], -1)
        qgf = np.load(out / "gain_flags.npy") != 0
        ok = ~qpf[..., None] & ~r["kflags"][..., None]
        dd = np.abs(r["delays"] - qd)[np.broadcast_to(ok, qd.shape)]
        ge = np.abs(r["gains"] - qg)[~qgf]
        prods = cg.product_compare(
            r["gains"], np.repeat(r["gflags"][..., None], 2, -1),
            qg, np.repeat(qgf[..., None], 2, -1),
        )  # fmt: skip
        qi = [int(np.ravel(x)[0]) for x in np.atleast_1d(summary["conv_iter"])]
        qp = [float(np.ravel(x)[0]) for x in np.atleast_1d(summary["conv_perc"])]
        res = {
            "shape": list(qd.shape),
            "chunks": len(qi),
            "param_flags_exact": bool(np.array_equal(r["kflags"], qpf)),
            "gain_flags_exact": bool(np.array_equal(r["gflags"], qgf)),
            "flagged_params": [int(r["kflags"].sum()), int(qpf.sum())],
            "flagged_gains": [int(r["gflags"].sum()), int(qgf.sum())],
            "max_delay_abs_ns": float(dd.max()) if dd.size else None,
            "max_gain_entry_abs": float(ge.max()) if ge.size else None,
            **{f"product_{k}": v for k, v in prods.items()},
            "iterations": [r["iter"], qi],
            "converged_fraction": [r["frac"], qp],
            "max_abs_delay_ns": float(np.abs(qd).max()),
            "rang_seconds": r["seconds"],
            "quartical_wall": summary.get("time_wall"),
            "quartical_rss_mb": summary.get("max_rss_mb"),
        }
        res["pass"] = bool(
            res["param_flags_exact"]
            and res["gain_flags_exact"]
            and (res["max_delay_abs_ns"] or 0) <= CLASS_A_TOL
            and (res["max_gain_entry_abs"] or 0) <= CLASS_A_TOL
            and (res["product_max_abs"] or 0) <= CLASS_A_TOL
            and r["iter"] == qi
            and all(abs(a - b) <= 1e-12 for a, b in zip(r["frac"], qp))
        )
        results[name] = res
        print(name, "PASS" if res["pass"] else "FAIL", json.dumps(res), flush=True)
    report = {
        "class": "A",
        "cases": results,
        "timings": cf.TIMINGS,
        "seconds": time.perf_counter() - started,
        "pass": all(r["pass"] for r in results.values()),
    }
    cg.write(run / "quartical.json", report)
    return 0 if report["pass"] else 1


# --- against CASA ---------------------------------------------------------------


def k_table(table, nant):
    """(time, ant, 2) delays (ns), flags and per-time ANTENNA2 of a K table,
    and its solution times."""
    times = np.unique(table.column("TIME"))
    d = np.zeros((len(times), nant, 2))
    f = np.ones((len(times), nant, 2), bool)
    ref = np.full(len(times), -2)
    params, flags = table.params, table.flags
    t_all, a1, a2 = (table.column(k) for k in ("TIME", "ANTENNA1", "ANTENNA2"))
    for row in range(table.nrows):
        t = int(np.searchsorted(times, t_all[row]))
        d[t, a1[row]] = params[row, 0]
        f[t, a1[row]] = flags[row, 0]
        ref[t] = a2[row]
    return times, d, f, ref


def delay_compare(rd, rf, cd, cf_, refant):
    ok = ~rf & ~cf_
    ok[:, refant] = False
    diff = np.abs(rd - cd)[ok]
    return {
        "delays": int(ok.sum()),
        "median_abs_ns": float(np.median(diff)) if diff.size else None,
        "p95_abs_ns": float(np.percentile(diff, 95)) if diff.size else None,
        "max_abs_ns": float(diff.max()) if diff.size else None,
    }


def casa_specs(p, edits):
    """The edited MS copies (model on fields 0 and 2, RFI flags, refant
    flags) and their source MS."""
    out = {}
    for key in ("a1", "d50"):
        ms, truth, rfi, _, _ = sources(p)[key]
        tr = dict(np.load(truth))
        rows, values = cg.a1_model(ms, tr, [0, 2], parang=True)
        np.savez(edits / f"{key}-model.npz", rows=rows, values=values)
        nchan = values.shape[1]
        mask = cg.rfi_flags(ms, rfi, nchan)
        np.savez(edits / f"{key}-rfi.npz", rows=np.arange(len(mask)), flag=mask)
        cg.write(edits / f"{key}-rfi.json", {"flag": f"/run/edits/{key}-rfi.npz"})
        out[key] = (key, {"model": f"/run/edits/{key}-model.npz"}, True)
    c = cg.columns(p["a1"], ["ANTENNA1", "ANTENNA2", "SCAN_NUMBER", "TIME", "DATA"])
    a1, a2, scan, t = (c[k] for k in ("ANTENNA1", "ANTENNA2", "SCAN_NUMBER", "TIME"))
    s23 = np.unique(t[scan == 23])
    ref_rows = np.flatnonzero(
        (scan == 23) & np.isin(t, s23[2:5]) & ((a1 == 0) | (a2 == 0))
    )
    np.savez(edits / "a1-refant-flag.npz", rows=ref_rows,
             flag=np.ones((len(ref_rows), c["DATA"].shape[1], 4), bool))  # fmt: skip
    out["a1-refant"] = (
        "a1",
        {"model": "/run/edits/a1-model.npz", "flag": "/run/edits/a1-refant-flag.npz"},
        True,
    )
    out["slice"] = ("slice", None, False)
    return out


def casa(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    edits = run / "edits"
    edits.mkdir()
    specs = casa_specs(p, edits)
    steps = []
    for name, (base, spec, rfi) in specs.items():
        steps.append(f"cp -r /src/{base}.ms /run/casa/{name}.ms")
        if spec:
            cg.write(edits / f"{name}.json", spec)
            steps.append(f"{cg.CASA} -I /ex/oracle_gain.py casa-edit /run/casa/{name}.ms /run/edits/{name}.json")  # fmt: skip
        if rfi:
            steps.append(f"{cg.CASA} -I /ex/oracle_gain.py casa-edit /run/casa/{name}.ms /run/edits/{base}-rfi.json")  # fmt: skip
    guest = {
        "a1b": "/src/a1.B",
        "a1g": "/src/a1.G",
        "d50b": "/src/d50.B",
        "d50g": "/src/d50.G",
    }
    calls = []
    for name, ms, fid, solint, tabs, refant in B_CASES:
        calls.append(
            {
                "vis": f"/run/casa/{ms}.ms",
                "caltable": f"/run/casa/{name}.K",
                "field": str(fid),
                "gaintype": "K",
                "solint": solint,
                "combine": "",
                "refant": refant,
                "refantmode": "flex",
                "minsnr": 3.0,
                "minblperant": 4,
                "gaintable": [guest[k] for k in tabs],
                "interp": ["linear"] * len(tabs),
            }
        )
    cg.write(run / "gaincal-spec.json", calls)
    steps.append(f"{cg.CASA} -I /ex/oracle_gain.py casa-gaincal /run/gaincal-spec.json /run/gaincal.json")  # fmt: skip
    (run / "casa").mkdir()
    cf.TIMINGS.clear()
    cf.docker(
        cf.CASA_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        [
            (run, "/run", "rw"),
            (HERE, "/ex", "ro"),
            (p["slice"], "/src/slice.ms", "ro"),
            (p["a1"], "/src/a1.ms", "ro"),
            (p["d50"], "/src/d50.ms", "ro"),
            (p["a1b"], "/src/a1.B", "ro"),
            (p["a1g"], "/src/a1.G", "ro"),
            (p["d50b"], "/src/d50.B", "ro"),
            (p["d50g"], "/src/d50.G", "ro"),
        ],
        "casa edits and gaincal K",
    )
    return evaluate(run, p, "casa.json", started)


def evaluate(run, p, out_name, started):
    calls_out = json.loads((run / "gaincal.json").read_text())
    tables = {k: caltable.read(p[k]) for k in ("a1b", "a1g", "d50b", "d50g")}
    results = {}
    for case, call in zip(B_CASES, calls_out):
        name = case[0]
        if call["call"]["caltable"] != f"/run/casa/{name}.K":
            raise SystemExit(f"gaincal.json does not match the case list at {name}")
        results[name] = k_compare(run, case, [tables[k] for k in case[4]], call)
        print(name, "PASS" if results[name]["pass"] else "FAIL",
              json.dumps(results[name]), flush=True)  # fmt: skip
    # O-CASA's own c.K0 against rang's B-slice-120s table.
    rt = caltable.read(run / "casa" / "B-slice-120s.rang.K")
    _, rd, rf, _ = k_table(rt, 4)
    _, cd, cfl, cref = k_table(caltable.read(p["k0"]), 4)
    r = {"delays": delay_compare(rd, rf, cd, cfl, 0), "flags_differ": int((rf != cfl).sum()),
         "antenna2": sorted(set(cref.tolist()))}  # fmt: skip
    d = r["delays"]
    r["pass"] = bool(
        rd.shape == cd.shape
        and r["flags_differ"] == 0
        and d["median_abs_ns"] <= CASA_TOL["median"]
        and d["p95_abs_ns"] <= CASA_TOL["p95"]
    )
    results["B-slice-c.K0"] = r
    print("B-slice-c.K0", "PASS" if r["pass"] else "FAIL", json.dumps(r), flush=True)
    report = {
        "class": "B (K)",
        "cases": results,
        "timings": list(cf.TIMINGS),
        "seconds": time.perf_counter() - started,
        "pass": all(r["pass"] for r in results.values()),
    }
    cg.write(run / out_name, report)
    return 0 if report["pass"] else 1


def k_compare(run, case, tables, call):
    name, ms, fid, solint, _, refant = case
    msp = run / "casa" / f"{ms}.ms"
    if call["error"] or not call["written"]:
        return {"pass": False, "casa_error": call["error"], "written": call["written"]}
    ctab = caltable.read(Path(call["call"]["caltable"].replace("/run", str(run))))
    t0 = time.perf_counter()
    table, sol, info = cal_delay.gaincal(
        msp,
        field_id=fid,
        solint=solint,
        refant=refant,
        gaintable=tables,
        interp="linear",
    )
    seconds = time.perf_counter() - t0
    caltable.write(table, run / "casa" / f"{name}.rang.K")
    cols = cg.columns(msp, ["TIME", "FIELD_ID", "ANTENNA1", "ANTENNA2"])
    info["row_time"] = cols["TIME"][cols["FIELD_ID"] == fid]
    nant = sol.delays.shape[2]
    ctimes, cd, cfl, cref = k_table(ctab, nant)
    rtimes = np.asarray(table.column("TIME")).reshape(-1, nant)[:, 0]
    bins, index = cg.match_intervals(ctimes, info, rtimes)
    r = {"intervals": bins, "rang_seconds": seconds, "casa_seconds": call["seconds"],
         "iterations": sol.iterations, "converged_fraction": sol.converged_fraction}  # fmt: skip
    if not bins["all_matched_once"]:
        r["pass"] = False
        return r
    ref = int(sol.refant_used[0])
    rd, rf = sol.delays[index][:, 0], sol.flags[index][:, 0]
    r["delays"] = delay_compare(rd, rf, cd, cfl, ref)
    r["max_abs_delay_ns"] = float(np.abs(cd[~cfl]).max())
    diff = rf != cfl
    r["flags"] = {"rang_flagged": int(rf.sum()), "casa_flagged": int(cfl.sum()),
                  "differ": int(diff.sum())}  # fmt: skip
    rref = np.asarray(table.column("ANTENNA2")).reshape(-1, nant)[:, 0]
    r["antenna2"] = {"rang": sorted(set(rref.tolist())), "casa": sorted(set(cref.tolist())),
                     "equal": bool(np.array_equal(rref[index], cref))}  # fmt: skip
    d = r["delays"]
    ok = (
        r["flags"]["differ"] == 0
        and r["antenna2"]["equal"]
        and not bins["rang_without_casa"]
    )
    if d["delays"]:
        ok &= (
            d["median_abs_ns"] <= CASA_TOL["median"]
            and d["p95_abs_ns"] <= CASA_TOL["p95"]
        )
    r["pass"] = bool(ok)
    return r


# --- class T --------------------------------------------------------------------


def truth(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    edits = run / "edits"
    edits.mkdir()
    (run / "ms").mkdir()
    src = sources(p)
    steps = []
    for key, (ms, tr_path, rfi, _, _) in src.items():
        tr = dict(np.load(tr_path))
        rows, values = cg.a1_model(ms, tr, [0, 2], parang=True)
        np.savez(edits / f"{key}-model.npz", rows=rows, values=values)
        spec = {"model": f"/run/edits/{key}-model.npz"}
        if rfi is not None:
            mask = cg.rfi_flags(ms, rfi, values.shape[1])
            np.savez(edits / f"{key}-rfi.npz", rows=np.arange(len(mask)), flag=mask)
            spec["flag"] = f"/run/edits/{key}-rfi.npz"
        cg.write(edits / f"{key}.json", spec)
        steps += [
            f"cp -r /src/{key}.ms /run/ms/{key}.ms",
            f"{cg.CASA} -I /ex/oracle_gain.py casa-edit /run/ms/{key}.ms /run/edits/{key}.json",
        ]
    cf.TIMINGS.clear()
    cf.docker(
        cf.CASA_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        [(run, "/run", "rw"), (HERE, "/ex", "ro")]
        + [(src[k][0], f"/src/{k}.ms", "ro") for k in src],
        "casa model columns",
    )
    results = {}
    for key, (ms, tr_path, rfi, btab, gtab) in src.items():
        tr = dict(np.load(tr_path))
        tau = tr["raw_tau_ns"]
        dtrue = tau - tau[0][None]
        twin = rfi is None
        pre = [caltable.read(btab), caltable.read(gtab)]
        freq = cg.chan_freq(ms)
        nu0 = float(np.mean(freq))
        for solint in ("int", "inf"):
            for fid in (0, 2):
                name = f"T-{key}-{solint}-f{fid}"
                t0 = time.perf_counter()
                table, sol, _ = cal_delay.gaincal(
                    run / "ms" / f"{key}.ms", field_id=fid, solint=solint, refant="m000",
                    gaintable=pre, interp="linear",
                    stop_criterion=1e-10 if twin else 1e-7,
                    stop_fraction=1.0 if twin else 0.99,
                    max_iterations=200 if twin else 50,
                )  # fmt: skip
                seconds = time.perf_counter() - t0
                d = sol.delays[:, 0]
                f = sol.flags[:, 0]
                err = sol.delays[:, 0] - dtrue[None]
                r = {"intervals": d.shape[0], "flagged": int(f.sum()),
                     "iterations": sol.iterations, "seconds": seconds,
                     "max_abs_delay_ns": float(np.abs(dtrue).max())}  # fmt: skip
                if twin:
                    e = np.where(f, 0.0, err)
                    pq = [
                        (a, b)
                        for a in range(d.shape[1])
                        for b in range(a + 1, d.shape[1])
                    ]
                    pa, pb = np.array(pq).T
                    de = (e[:, pa] - e[:, pb]) * 1e-9  # (interval, pair, hand) s
                    x = 2 * np.pi * (freq - nu0)
                    phase = de[..., None] * x  # (interval, pair, hand, chan)
                    worst = float(np.max(2 * np.abs(np.sin(phase / 2))))
                    fp = np.asarray(table.column("FPARAM"))
                    tab = fp.reshape(d.shape[0], d.shape[1], 2).astype(np.float64)
                    r.update({
                        "max_product_error": worst,
                        "max_delay_error_ns": float(np.abs(e).max()),
                        "max_table_float32_delay_error_ns": float(
                            np.abs(np.where(f, 0.0, tab - dtrue[None])).max()),
                    })  # fmt: skip
                    r["pass"] = bool(worst <= TRUTH_TOL and not f.any())
                else:
                    s = np.sqrt(sol.err[:, 0] ** 2 + sol.err[:, 0, :1, :] ** 2)
                    ok = ~f.copy()
                    ok[:, 0] = False
                    z = (err / np.where(s > 0, s, np.inf))[ok]
                    n = z.size
                    limit = 3 * 1.2533 / np.sqrt(n)
                    r.update({
                        "n": int(n), "median_z": float(np.median(z)), "limit": float(limit),
                        "std_z": float(np.std(z)),
                        "median_abs_error_ns": float(np.median(np.abs(err[ok]))),
                        "median_err_ns": float(np.median(sol.err[:, 0][ok])),
                    })  # fmt: skip
                    r["pass"] = bool(abs(r["median_z"]) <= limit)
                    if "--centred" in argv:
                        # Post hoc after run -05: every referenced delay of an
                        # interval shares the refant's error, so the frozen
                        # z values are not independent. Gauge-free form: the
                        # delays centred on their mean over the antennas per
                        # interval and hand, on both sides, over err_p.
                        okc = ~f
                        cnt = okc.sum(1, keepdims=True)
                        mr = np.where(okc, d, 0).sum(1, keepdims=True) / cnt
                        mt = np.where(okc, dtrue[None], 0).sum(1, keepdims=True) / cnt
                        ec = (d - mr) - (dtrue[None] - mt)
                        e1 = sol.err[:, 0]
                        zc = (ec / np.where(e1 > 0, e1, np.inf))[okc]
                        lc = 3 * 1.2533 / np.sqrt(zc.size)
                        r["centred"] = {"n": int(zc.size), "median_z": float(np.median(zc)),
                                        "limit": float(lc), "std_z": float(np.std(zc)),
                                        "pass": bool(abs(np.median(zc)) <= lc)}  # fmt: skip
                np.savez(run / f"{name}.npz", delays=sol.delays, flags=sol.flags,
                         err=sol.err, truth=dtrue)  # fmt: skip
                results[name] = r
                print(name, "PASS" if r["pass"] else "FAIL", json.dumps(r), flush=True)
    report = {
        "class": "T",
        "cases": results,
        "timings": cf.TIMINGS,
        "seconds": time.perf_counter() - started,
        "pass": all(r["pass"] for r in results.values()),
    }
    cg.write(run / "truth.json", report)
    return 0 if report["pass"] else 1


# --- CASA applies rang's tables ---------------------------------------------------


def readback(run, argv):
    p = paths(argv)
    casa_run = Path(argv[0])
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    cases = [
        ("R-slice", p["slice"], 1, casa_run / "casa" / "B-slice-int.rang.K"),
        ("R-d50", p["d50"], 0, casa_run / "casa" / "B-d50-inf-f0.rang.K"),
    ]
    steps = []
    mounts = [(run, "/run", "rw")]
    for name, ms, fid, tab in cases:
        shutil.copytree(tab, run / f"{name}.K")
        (run / f"{name}.py").write_text(
            "from casatasks import applycal\n"
            f"applycal(vis='/run/{name}.ms', field='{fid}', gaintable=['/run/{name}.K'],\n"
            "         interp=['linear'], calwt=[False], applymode='calflag',\n"
            "         parang=False, flagbackup=False)\n"
        )
        steps += [
            f"cp -r /src/{name}.ms /run/{name}.ms",
            f"{cg.CASA} -I /run/{name}.py",
        ]
        mounts.append((ms, f"/src/{name}.ms", "ro"))
    cf.TIMINGS.clear()
    cf.docker(cf.CASA_IMAGE, ["sh", "-c", " && ".join(steps)], mounts,
              "casa applycal of rang K tables")  # fmt: skip
    results = {}
    for name, ms, fid, _ in cases:
        c = cg.columns(run / f"{name}.ms", ["DATA", "CORRECTED_DATA", "FLAG", "TIME",
                                            "ANTENNA1", "ANTENNA2", "FIELD_ID"])  # fmt: skip
        orig = cg.columns(ms, ["FLAG"])["FLAG"]
        rows = c["FIELD_ID"] == fid
        tab = caltable.read(run / f"{name}.K")
        ours, flags = cal_apply.apply(
            c["DATA"][rows], orig[rows], c["TIME"][rows], c["ANTENNA1"][rows],
            c["ANTENNA2"][rows], cg.chan_freq(ms), [tab], interp="linear", field_id=fid,
        )  # fmt: skip
        theirs, tflag = c["CORRECTED_DATA"][rows], c["FLAG"][rows]
        ok = ~flags & ~tflag
        r = {
            "class_c": cal_apply.class_c(ours, theirs, ok),
            "flags_exact": bool(np.array_equal(flags, tflag)),
            "max_abs_delay_ns": float(np.abs(tab.params).max()),
        }
        r["pass"] = bool(r["class_c"]["pass"] and r["flags_exact"])
        results[name] = r
        print(
            name,
            "PASS" if r["pass"] else "FAIL",
            json.dumps(r, default=float),
            flush=True,
        )
    report = {"cases": results, "timings": cf.TIMINGS,
              "seconds": time.perf_counter() - started,
              "pass": all(r["pass"] for r in results.values())}  # fmt: skip
    cg.write(run / "readback.json", report)
    return 0 if report["pass"] else 1


def main(argv):
    commands = {
        "quartical": quartical,
        "casa": casa,
        "truth": truth,
        "readback": readback,
    }
    if len(argv) < 3 or argv[1] not in commands:
        print(__doc__)
        return 2
    return commands[argv[1]](argv[2], argv[3:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
