"""Host side of task C2a (research/c2a-gain.md): the gain term G against
QuartiCal 0.2.7 (class A), CASA 6.7.6.14 `gaincal` (class B) and A1's
simulated truth (class T). Worktree venv; every container step is one
network-less run (`check_formats.docker`), timed.

    python examples/check_gain.py quartical <run>   # class A, section 4
    python examples/check_gain.py casa <run>        # class B
    python examples/check_gain.py casa <run> --heldout   # class B, section 7
    python examples/check_gain.py recheck <run>     # class B again, current code
    python examples/check_gain.py truth <run> [--parang-model]   # class T

`<run>` is a fresh `/mnt/d/rang/outputs/c2a-<date>-NN`. Inputs are read in
place, read-only: O-CASA's slice and `c.K0`, the fixture (both under
`~/Github/rang/outputs`, or `--outputs <dir>`), and A1's small version
(`--a1 <dir>`, default `/mnt/d/rang/outputs/fp-a1-20261106-simtruth`). Each
subcommand writes `<run>/<subcommand>.json`; exit 0 only when every gated
item passes.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_formats as cf
from rang import cal_apply, cal_gain, core_ms
from rang.formats import caltable

QC = "/opt/qc/bin/python"
CASA = "/opt/casa/bin/python"
QC_OPTIONS = [
    "input_ms.weight_column=WEIGHT_SPECTRUM",
    "solver.terms=[G]",
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
# Class A (section 4): name, MS, data column, model column, type, time, freq.
QC_CASES = [
    ("A-slice-ap-t2", "slice", "DATA", "MODEL_DATA", "diag_complex", 2, 0),
    ("A-slice-ap-t1f32", "slice", "DATA", "MODEL_DATA", "diag_complex", 1, 32),
    ("A-slice-p-t2", "slice", "DATA", "MODEL_DATA", "phase", 2, 0),
    ("A-slice-p-t1f32", "slice", "DATA", "MODEL_DATA", "phase", 1, 32),
    ("A-slice-ap-K", "slice", "KDATA", "MODEL_DATA", "diag_complex", 2, 0),
    ("A-fixture-ap", "fixture", "DATA", "RANG_MODEL_DATA", "diag_complex", 2, 32),
    ("A-fixture-p", "fixture", "DATA", "RANG_MODEL_DATA", "phase", 2, 32),
]
CLASS_A_TOL = 1e-6
CLASS_B = {"median": 7e-4, "p95": 3e-3, "mse": 2e-4}
TIME_TOL = 0.01
TRUTH_TOL = 1e-5


def paths(argv):
    outputs = Path.home() / "Github/rang/outputs"
    a1 = Path("/mnt/d/rang/outputs/fp-a1-20261106-simtruth")
    if "--outputs" in argv:
        outputs = Path(argv[argv.index("--outputs") + 1])
    if "--a1" in argv:
        a1 = Path(argv[argv.index("--a1") + 1])
    return {
        "slice": outputs / "o-casa-20261030-01/work.ms",
        "k0": outputs / "o-casa-20261030-01/c.K0",
        "split": outputs / "o-casa-20261030-01/split.npz",
        "fixture": outputs / "tv-response-wsl-20261029-01/clean/work.ms",
        "a1": a1 / "small/a1-small.ms",
        "twin": a1 / "small/a1-small-twin.ms",
        "truth": a1 / "small/truth.npz",
        "rfi": a1 / "small/a1-small.rfi_mask.npz",
        "a1k": a1 / "casa-small/truth.K",
        "a1b": a1 / "casa-small/truth.B",
    }


def columns(ms, names):
    with core_ms.open_table(ms) as t:
        return {n: t.getcol(n) for n in names}


def chan_freq(ms):
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        return np.asarray(t.getcol("CHAN_FREQ")[0], float)


def write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=float) + "\n")


def product_compare(g1, f1, g2, f2, absolute=True):
    """Parallel-hand products of two (interval, freq, ant, 2) gain sets on
    pairs both leave unflagged: max absolute or relative differences."""
    p1, ok1, _ = cal_gain.baseline_products(g1, f1)
    p2, ok2, _ = cal_gain.baseline_products(g2, f2)
    ok = ok1 & ok2
    diff = np.abs(p1 - p2)[ok]
    if absolute:
        return {
            "products": int(ok.sum()),
            "max_abs": float(diff.max()) if diff.size else None,
        }
    rel = diff / np.abs(p2[ok])
    return {
        "products": int(ok.sum()),
        "median_rel": float(np.median(rel)) if rel.size else None,
        "p95_rel": float(np.percentile(rel, 95)) if rel.size else None,
        "max_rel": float(rel.max()) if rel.size else None,
    }


# --- class A ------------------------------------------------------------------


def quartical(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    # KDATA: the slice's DATA corrected by c.K0 (linear) in rang's kernel.
    c = columns(p["slice"], ["DATA", "FLAG", "TIME", "ANTENNA1", "ANTENNA2"])
    k0 = caltable.read(p["k0"])
    kdata, kflag = cal_apply.apply(
        c["DATA"], c["FLAG"], c["TIME"], c["ANTENNA1"], c["ANTENNA2"],
        chan_freq(p["slice"]), [k0], interp="linear",
    )  # fmt: skip
    if np.any(kflag & ~c["FLAG"]):
        raise SystemExit("c.K0 flags cells: KDATA would need its own FLAG")
    np.savez(run / "kdata.npz", values=kdata)
    steps = [
        f"{QC} -I /ex/oracle_gain.py qc-copy /src/slice.ms /run/qc/slice.ms /run/kdata.npz KDATA",
        f"{QC} -I /ex/oracle_gain.py qc-copy /src/fixture.ms /run/qc/fixture.ms",
    ]
    for name, ms, col, model, kind, ti, fi in QC_CASES:
        opts = [
            f"input_ms.data_column={col}",
            f"input_model.recipe={model}",
            f"G.type={kind}",
            f"G.time_interval={ti}",
            f"G.freq_interval={fi}",
            *QC_OPTIONS,
        ]
        steps.append(
            f"{QC} -I /ex/oracle_gain.py qc-solve /run/qc/{ms}.ms /run/qc/{name} "
            + " ".join(opts)
        )
    (run / "qc").mkdir()
    cf.TIMINGS.clear()
    cf.docker(
        cf.FORMATS_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        [
            (run, "/run", "rw"),
            (HERE, "/ex", "ro"),
            (p["slice"], "/src/slice.ms", "ro"),
            (p["fixture"], "/src/fixture.ms", "ro"),
        ],
        f"quartical x{len(QC_CASES)}",
        env={"NUMBA_CACHE_DIR": "/run/numba"},
    )
    results = {}
    for name, ms, col, model, kind, ti, fi in QC_CASES:
        out = run / "qc" / name
        summary = json.loads((out / "summary.json").read_text())
        qg = np.load(out / "gains.npy")
        qg = np.stack([qg[..., 0], qg[..., 3]], -1)
        qf = np.load(out / "gain_flags.npy") != 0
        cols = columns(
            run / "qc" / f"{ms}.ms",
            [
                col,
                model,
                "WEIGHT_SPECTRUM",
                "FLAG",
                "FLAG_ROW",
                "ANTENNA1",
                "ANTENNA2",
                "TIME",
            ],
        )
        nant = int(max(cols["ANTENNA1"].max(), cols["ANTENNA2"].max())) + 1
        integration = np.unique(cols["TIME"], return_inverse=True)[1].ravel()
        nchan = cols[col].shape[1]
        tb = integration // ti
        fb = np.arange(nchan) // fi if fi else np.zeros(nchan, int)
        t0 = time.perf_counter()
        sol = cal_gain.solve(
            cols[col], cols[model], cols["WEIGHT_SPECTRUM"], cols["FLAG"], cols["FLAG_ROW"],
            cols["ANTENNA1"], cols["ANTENNA2"], tb, nant=nant, freq_bin=fb,
            calmode="ap" if kind == "diag_complex" else "p", refant=0, casa_rules=False,
        )  # fmt: skip
        seconds = time.perf_counter() - t0
        rf = sol.kernel_flags
        entries = np.abs(sol.gains - qg)[~qf]
        flags_rang = np.repeat(rf[..., None], 2, -1)
        flags_qc = np.repeat(qf[..., None], 2, -1)
        prods = product_compare(sol.gains, flags_rang, qg, flags_qc)
        conv_iter = int(np.ravel(summary["conv_iter"])[0])
        conv_perc = float(np.ravel(summary["conv_perc"])[0])
        r = {
            "shape": list(qg.shape),
            "gains": int(qf.size),
            "flags_exact": bool(np.array_equal(rf, qf)),
            "flagged": [int(rf.sum()), int(qf.sum())],
            "max_entry_abs": float(entries.max()) if entries.size else None,
            "entries_above_1e-10": int(np.sum(entries > 1e-10)),
            **{f"product_{k}": v for k, v in prods.items()},
            "iterations": [sol.iterations, conv_iter],
            "converged_fraction": [sol.converged_fraction, conv_perc],
            "rang_seconds": seconds,
            "quartical_wall": summary.get("time_wall"),
            "quartical_rss_mb": summary.get("max_rss_mb"),
        }
        r["pass"] = bool(
            r["flags_exact"]
            and (r["max_entry_abs"] or 0) <= CLASS_A_TOL
            and (r["product_max_abs"] or 0) <= CLASS_A_TOL
            and sol.iterations == conv_iter
            and abs(sol.converged_fraction - conv_perc) <= 1e-12
        )
        results[name] = r
        print(name, "PASS" if r["pass"] else "FAIL", json.dumps(r), flush=True)
    report = {
        "class": "A",
        "cases": results,
        "timings": cf.TIMINGS,
        "seconds": time.perf_counter() - started,
        "pass": all(r["pass"] for r in results.values()),
    }
    write(run / "quartical.json", report)
    return 0 if report["pass"] else 1


# --- shared for B and T --------------------------------------------------------


def a1_model(ms, truth, fields, parang=False):
    """MODEL_DATA rows of `fields` from A1's calibrator Stokes per channel.
    With `parang` (post hoc, section 8), A1's own reference `P_p M P_q^T`,
    `P = [[cos a, sin a], [-sin a, cos a]]`, `a = q_p + RECEPTOR_ANGLE`, from
    `truth.npz`'s per-antenna parallactic angles: per-antenna angles do not
    cancel even for an unpolarised source (`XX = I cos(a_p - a_q)`)."""
    c = columns(ms, ["FIELD_ID", "TIME", "ANTENNA1", "ANTENNA2"])
    rows = np.flatnonzero(np.isin(c["FIELD_ID"], fields))
    s = truth["calibrator_stokes"][c["FIELD_ID"][rows]]  # (row, chan, IQUV)
    i, q, u, v = (s[..., k] for k in range(4))
    values = np.stack([i + q, u + 1j * v, u - 1j * v, i - q], -1)
    if parang:
        ti = np.searchsorted(truth["time"], c["TIME"][rows])
        if not np.array_equal(truth["time"][ti], c["TIME"][rows]):
            raise SystemExit("truth times do not match the MS")
        a = truth["parallactic_angle"] + truth["receptor_angle"][0]
        ap, aq = a[ti, c["ANTENNA1"][rows]], a[ti, c["ANTENNA2"][rows]]

        def rot(x):
            return np.stack([np.cos(x), np.sin(x), -np.sin(x), np.cos(x)], -1).reshape(
                -1, 2, 2
            )

        m = values.reshape(*values.shape[:2], 2, 2)
        m = np.einsum("rij,rcjk,rlk->rcil", rot(ap), m, rot(aq))
        values = m.reshape(*values.shape)
    return rows, values.astype(np.complex64)


def rfi_flags(ms, rfi_path, nchan):
    z = np.load(rfi_path)
    mask = np.unpackbits(z["any"], axis=1)[:, :nchan].astype(bool)
    return np.repeat(mask[..., None], 4, -1)


def casa_table_gains(table, nant):
    """(time, 1, ant, 2) gains, flags, SNR and refant of a CASA G table, and
    its solution times."""
    times = np.unique(table.column("TIME"))
    g = np.ones((len(times), 1, nant, 2), complex)
    f = np.ones((len(times), 1, nant, 2), bool)
    snr = np.zeros((len(times), 1, nant, 2))
    ref = np.full(len(times), -2)
    params, flags, s = table.params, table.flags, table.snr
    t_all, a1, a2 = (
        table.column("TIME"),
        table.column("ANTENNA1"),
        table.column("ANTENNA2"),
    )
    for row in range(table.nrows):
        t = int(np.searchsorted(times, t_all[row]))
        g[t, 0, a1[row]] = params[row, 0]
        f[t, 0, a1[row]] = flags[row, 0]
        snr[t, 0, a1[row]] = s[row, 0]
        ref[t] = a2[row]
    return times, g, f, snr, ref


def match_intervals(casa_times, info, rang_times):
    """CASA solution times against rang's intervals (row times of each)."""
    tb = info["time_bin"]
    c = info["row_time"]
    spans = [(c[tb == t].min(), c[tb == t].max()) for t in range(len(rang_times))]
    index = []
    for ct in casa_times:
        hits = [
            t
            for t, (lo, hi) in enumerate(spans)
            if lo - TIME_TOL <= ct <= hi + TIME_TOL
        ]
        index.append(hits[0] if len(hits) == 1 else -1)
    index = np.array(index)
    ok = (index >= 0) & (len(set(index.tolist())) == len(index))
    dt = np.array(
        [abs(rang_times[i] - ct) for i, ct in zip(index, casa_times) if i >= 0]
    )
    return {
        "casa_intervals": len(casa_times),
        "rang_intervals": len(rang_times),
        "all_matched_once": bool(ok.all()),
        "rang_without_casa": sorted(set(range(len(rang_times))) - set(index.tolist())),
        "max_time_diff_s": float(dt.max()) if dt.size else None,
    }, index


def baseline_counts(ms_cols, info, nant):
    """Baselines per (interval, antenna) with an unflagged cell (rang's
    minblperant count before elimination)."""
    tb = info["time_bin"]
    fl = info["flag"].any(-1).all(-1) | info["flag_row"]
    counts = np.zeros((tb.max() + 1, nant), int)
    a1, a2 = ms_cols["ANTENNA1"], ms_cols["ANTENNA2"]
    for t in range(tb.max() + 1):
        rows = (tb == t) & ~fl & (a1 != a2)
        pairs = {(int(p), int(q)) for p, q in zip(a1[rows], a2[rows])}
        for p, q in pairs:
            counts[t, p] += 1
            counts[t, q] += 1
    return counts


# --- class B ------------------------------------------------------------------


def b_cases(p):
    """(name, ms key, field id, solint, combine, calmode, refantmode,
    minblperant, gaintable keys)."""
    slice_ = [
        ("B-slice-inf", "slice", 1, "inf", "", "ap", "flex", 3, ["k0"]),
        ("B-slice-60s", "slice", 1, "60s", "", "ap", "flex", 3, ["k0"]),
        ("B-slice-120s", "slice", 1, "120s", "", "ap", "flex", 3, ["k0"]),
        ("B-slice-p", "slice", 1, "inf", "", "p", "flex", 3, ["k0"]),
    ]
    a1 = []
    for fld in (0, 2):
        for solint in ("inf", "60s", "30s", "int"):
            a1.append(
                (
                    f"B-a1-{solint}-f{fld}",
                    "a1",
                    fld,
                    solint,
                    "",
                    "ap",
                    "flex",
                    4,
                    ["a1k", "a1b"],
                )
            )
    a1 += [
        ("B-a1-combine-f2", "a1", 2, "inf", "scan", "ap", "flex", 4, ["a1k", "a1b"]),
        (
            "B-a1-refant-flex",
            "a1-refant",
            0,
            "int",
            "",
            "ap",
            "flex",
            4,
            ["a1k", "a1b"],
        ),
        (
            "B-a1-refant-strict",
            "a1-refant",
            0,
            "int",
            "",
            "ap",
            "strict",
            4,
            ["a1k", "a1b"],
        ),
        ("B-a1-minblperant", "a1-minbl", 0, "inf", "", "ap", "flex", 4, ["a1k", "a1b"]),
        ("B-a1-minsnr", "a1-snr", 0, "inf", "", "ap", "flex", 4, ["a1k", "a1b"]),
    ]
    return slice_ + a1


def heldout_cases(p):
    """The held-out class B cases (section 7), frozen before their run."""
    a1 = ["a1k", "a1b"]
    return [
        ("H-slice-p-60s", "slice", 1, "60s", "", "p", "flex", 3, ["k0"]),
        ("H-a1-20s-f0", "a1", 0, "20s", "", "ap", "flex", 4, a1),
        ("H-a1-16s-f0", "a1", 0, "16s", "", "ap", "flex", 4, a1),
        ("H-a1-p-int-f2", "a1", 2, "int", "", "p", "flex", 4, a1),
        ("H-a1-refant-flex-f2", "a1-refant2", 2, "inf", "", "ap", "flex", 4, a1),
        ("H-a1-refant-strict-f2", "a1-refant2", 2, "inf", "", "ap", "strict", 4, a1),
        ("H-a1-minbl-f2", "a1-minbl2", 2, "inf", "", "ap", "flex", 4, a1),
        ("H-a1-snr-sigma-f0", "a1-snr2", 0, "inf", "", "ap", "flex", 4, a1),
    ]


def heldout_specs(edits, a1, a2, fld, scan, nchan, base):
    """Edits of the held-out A1 copies: m000 flagged in scans 5 and 7
    (field 2); m011 left with its baselines to m001-m003 in scan 9; SIGMA of
    m009's field-0 rows times 1e4."""
    ref = np.flatnonzero(np.isin(scan, [5, 7]) & ((a1 == 0) | (a2 == 0)))
    np.savez(
        edits / "a1-refant2-flag.npz",
        rows=ref,
        flag=np.ones((len(ref), nchan, 4), bool),
    )
    other = np.where(a1 == 11, a2, a1)
    mb = np.flatnonzero(
        (scan == 9) & ((a1 == 11) | (a2 == 11)) & ~np.isin(other, [1, 2, 3])
    )
    np.savez(
        edits / "a1-minbl2-flag.npz", rows=mb, flag=np.ones((len(mb), nchan, 4), bool)
    )
    snr = np.flatnonzero((fld == 0) & ((a1 == 9) | (a2 == 9))).tolist()
    return {
        "a1": {**base},
        "a1-refant2": {**base, "flag": "/run/edits/a1-refant2-flag.npz"},
        "a1-minbl2": {**base, "flag": "/run/edits/a1-minbl2-flag.npz"},
        "a1-snr2": {**base, "sigma_scale": [[snr, 1e4]]},
    }


def casa(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    truth = dict(np.load(p["truth"]))
    edits = run / "edits"
    edits.mkdir()
    # The slice copy: held-out cells flagged.
    sc = columns(p["slice"], ["ANTENNA1", "ANTENNA2", "TIME", "FLAG"])
    split = np.load(p["split"])
    for k in ("ANTENNA1", "ANTENNA2", "TIME"):
        if not np.array_equal(split[k], sc[k]):
            raise SystemExit(f"split.npz {k} differs from the slice's rows")
    held = split["validation"] | split["test"]
    np.savez(edits / "slice-flag.npz", rows=np.arange(len(held)),
             flag=np.repeat(held[..., None], 4, -1))  # fmt: skip
    write(edits / "slice.json", {"flag": "/run/edits/slice-flag.npz"})
    # A1 copies: model on fields 0 and 2, RFI flags; then the edits.
    ac = columns(
        p["a1"], ["ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER", "TIME", "DATA"]
    )
    nchan = ac["DATA"].shape[1]
    rows, values = a1_model(p["a1"], truth, [0, 2])
    np.savez(edits / "a1-model.npz", rows=rows, values=values)
    rfi = rfi_flags(p["a1"], p["rfi"], nchan)
    np.savez(edits / "a1-rfi.npz", rows=np.arange(len(rfi)), flag=rfi)
    a1, a2, fld, scan, t = (
        ac[k] for k in ("ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER", "TIME")
    )
    # refant: m000 flagged in field 0, scan 23, integrations 2-4 (of 6).
    s23 = np.unique(t[scan == 23])
    ref_rows = np.flatnonzero(
        (scan == 23) & np.isin(t, s23[2:5]) & ((a1 == 0) | (a2 == 0))
    )
    flag_ref = np.zeros((len(ref_rows), nchan, 4), bool) | True
    np.savez(edits / "a1-refant-flag.npz", rows=ref_rows, flag=flag_ref)
    # minblperant: m005 keeps only its baselines to m001, m002, m003 in scan 1.
    keep = {1, 2, 3}
    mb_rows = np.flatnonzero(
        (scan == 1)
        & ((a1 == 5) | (a2 == 5))
        & ~np.isin(np.where(a1 == 5, a2, a1), list(keep))
    )
    np.savez(edits / "a1-minbl-flag.npz", rows=mb_rows,
             flag=np.ones((len(mb_rows), nchan, 4), bool))  # fmt: skip
    snr_rows = np.flatnonzero((fld == 0) & ((a1 == 7) | (a2 == 7)))
    base = {"model": "/run/edits/a1-model.npz"}
    specs = {
        "a1": {**base},
        "a1-refant": {**base, "flag": "/run/edits/a1-refant-flag.npz"},
        "a1-minbl": {**base, "flag": "/run/edits/a1-minbl-flag.npz"},
        "a1-snr": {**base, "weight_scale": [[snr_rows.tolist(), 1e-10]]},
    }
    cases = b_cases(p)
    if "--heldout" in argv:
        (run / "heldout.txt").write_text(
            "held-out case set (research/c2a-gain.md section 7)\n"
        )
        specs, cases = (
            heldout_specs(edits, a1, a2, fld, scan, nchan, base),
            heldout_cases(p),
        )
    steps = [
        "cp -r /src/slice.ms /run/casa/slice.ms",
        f"{CASA} -I /ex/oracle_gain.py casa-edit /run/casa/slice.ms /run/edits/slice.json",
    ]
    for name, spec in specs.items():
        write(edits / f"{name}.json", spec)
        steps += [
            f"cp -r /src/a1.ms /run/casa/{name}.ms",
            f"{CASA} -I /ex/oracle_gain.py casa-edit /run/casa/{name}.ms /run/edits/{name}.json",
        ]
    # The RFI flags on every A1 copy (after the case's own edits).
    for name in specs:
        steps.append(
            f"{CASA} -I /ex/oracle_gain.py casa-edit /run/casa/{name}.ms /run/edits/a1-rfi.json"
        )
    write(edits / "a1-rfi.json", {"flag": "/run/edits/a1-rfi.npz"})
    guest = {"k0": "/src/c.K0", "a1k": "/src/truth.K", "a1b": "/src/truth.B"}
    calls = []
    for name, ms, fid, solint, combine, calmode, mode, minbl, tabs in cases:
        calls.append(
            {
                "vis": f"/run/casa/{ms}.ms",
                "caltable": f"/run/casa/{name}.G",
                "field": str(fid),
                "gaintype": "G",
                "calmode": calmode,
                "solint": solint,
                "combine": combine,
                "refant": "m000",
                "refantmode": mode,
                "minsnr": 3.0,
                "minblperant": minbl,
                "solnorm": False,
                "uvrange": "",
                "gaintable": [guest[k] for k in tabs],
                "interp": ["linear"] * len(tabs),
            }
        )
    write(run / "gaincal-spec.json", calls)
    steps.append(
        f"{CASA} -I /ex/oracle_gain.py casa-gaincal /run/gaincal-spec.json /run/gaincal.json"
    )
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
            (p["k0"], "/src/c.K0", "ro"),
            (p["a1k"], "/src/truth.K", "ro"),
            (p["a1b"], "/src/truth.B", "ro"),
        ],
        "casa edits and gaincal",
    )
    return evaluate(run, p, sc, held, cases, "casa.json", started)


def evaluate(run, p, sc, held, cases, out_name, started):
    """Compare every case of `cases` with CASA's tables of `run`."""
    calls_out = json.loads((run / "gaincal.json").read_text())
    tables = {
        "k0": caltable.read(p["k0"]),
        "a1k": caltable.read(p["a1k"]),
        "a1b": caltable.read(p["a1b"]),
    }
    results = {}
    for (name, ms, fid, solint, combine, calmode, mode, minbl, tabs), call in zip(
        cases, calls_out
    ):
        if call["call"]["caltable"] != f"/run/casa/{name}.G":
            raise SystemExit(f"gaincal.json does not match the case list at {name}")
        results[name] = b_compare(run, name, ms, fid, solint, combine, calmode, mode, minbl,
                                  [tables[k] for k in tabs], call, sc, held)  # fmt: skip
        print(
            name,
            "PASS" if results[name]["pass"] else "FAIL",
            json.dumps(results[name]),
            flush=True,
        )
    report = {
        "class": "B",
        "cases": results,
        "timings": list(cf.TIMINGS),
        "seconds": time.perf_counter() - started,
        "pass": all(r["pass"] for r in results.values()),
    }
    write(run / out_name, report)
    return 0 if report["pass"] else 1


def recheck(run, argv):
    """Re-evaluate an earlier class B run's CASA tables with the current
    rang code (post hoc; writes `casa-recheck.json`)."""
    p = paths(argv)
    run = Path(run)
    started = time.perf_counter()
    sc, held = slice_split(p)
    cases = heldout_cases(p) if (run / "heldout.txt").exists() else b_cases(p)
    for name, *_ in cases:
        stale = run / "casa" / f"{name}.rang.G"
        if stale.exists():
            import shutil

            shutil.rmtree(stale)
    cf.TIMINGS.clear()
    return evaluate(run, p, sc, held, cases, "casa-recheck.json", started)


def slice_split(p):
    sc = columns(p["slice"], ["ANTENNA1", "ANTENNA2", "TIME", "FLAG"])
    split = np.load(p["split"])
    for k in ("ANTENNA1", "ANTENNA2", "TIME"):
        if not np.array_equal(split[k], sc[k]):
            raise SystemExit(f"split.npz {k} differs from the slice's rows")
    return sc, split["validation"] | split["test"]


def b_compare(
    run, name, ms, fid, solint, combine, calmode, mode, minbl, tables, call, sc, held
):
    msp = run / "casa" / f"{ms}.ms"
    if call["error"] or not call["written"]:
        return {"pass": False, "casa_error": call["error"], "written": call["written"]}
    ctab = caltable.read(Path(call["call"]["caltable"].replace("/run", str(run))))
    t0 = time.perf_counter()
    table, sol, info = cal_gain.gaincal(
        msp, field_id=fid, solint=solint, combine=combine, calmode=calmode, refant="m000",
        refantmode=mode, minsnr=3.0, minblperant=minbl, gaintable=tables, interp="linear",
    )  # fmt: skip
    seconds = time.perf_counter() - t0
    caltable.write(table, run / "casa" / f"{name}.rang.G")
    cols = columns(
        msp, ["TIME", "FIELD_ID", "ANTENNA1", "ANTENNA2", "FLAG", "FLAG_ROW"]
    )
    sel = cols["FIELD_ID"] == fid
    info["row_time"] = cols["TIME"][sel]
    info["flag"] = cols["FLAG"][sel]
    info["flag_row"] = cols["FLAG_ROW"][sel]
    nant = sol.gains.shape[2]
    ctimes, cg, cfl, csnr, cref = casa_table_gains(ctab, nant)
    rtimes = np.asarray(table.column("TIME")).reshape(-1, nant)[:, 0]
    bins, index = match_intervals(ctimes, info, rtimes)
    r = {"intervals": bins, "rang_seconds": seconds, "casa_seconds": call["seconds"],
         "casa_solvestats_keys": sorted((call["return"] or {}).keys())}  # fmt: skip
    if not bins["all_matched_once"]:
        r["pass"] = False
        return r
    rg, rf, rs = sol.gains[index], sol.flags[index], sol.snr[index]
    rref = sol.refant_used[index]
    r["products"] = product_compare(rg, rf, cg, cfl, absolute=False)
    if calmode == "p":
        dphi = np.degrees(np.abs(np.angle(rg * np.conj(cg))))[~rf & ~cfl]
        r["phase_median_deg"] = float(np.median(dphi)) if dphi.size else None
    # Flags: differences near minsnr or at minblperant are reported only.
    counts = baseline_counts(
        {"ANTENNA1": cols["ANTENNA1"][sel], "ANTENNA2": cols["ANTENNA2"][sel]},
        info,
        nant,
    )[index]
    near = ((csnr >= 1.5) & (csnr <= 6.0)) | ((rs >= 1.5) & (rs <= 6.0))
    near |= (counts == minbl)[:, None, :, None]
    diff = rf != cfl
    r["flags"] = {
        "rang_flagged": int(rf.sum()),
        "casa_flagged": int(cfl.sum()),
        "differ": int(diff.sum()),
        "differ_gated": int((diff & ~near).sum()),
        "differ_reported": int((diff & near).sum()),
    }
    r["refant"] = {
        "rang": rref.tolist(),
        "casa": cref.tolist(),
        "equal": bool(np.array_equal(rref, cref)),
    }
    r["used_alternate_refant"] = sol.used_alternate_refant
    prod = r["products"]
    ok = (
        r["flags"]["differ_gated"] == 0
        and r["refant"]["equal"]
        and (bins["max_time_diff_s"] or 0) <= TIME_TOL
        and not bins["rang_without_casa"]
    )
    if prod["products"]:
        ok &= (
            prod["median_rel"] <= CLASS_B["median"]
            and prod["p95_rel"] <= CLASS_B["p95"]
        )
    if ms == "slice":
        r["heldout_mse"] = heldout_mse(msp, table, ctab, tables, sc, held)
        ok &= abs(r["heldout_mse"]["relative"]) <= CLASS_B["mse"]
    r["pass"] = bool(ok)
    return r


def heldout_mse(msp, rtab, ctab, pre, sc, held):
    c = columns(
        msp, ["DATA", "MODEL_DATA", "WEIGHT_SPECTRUM", "TIME", "ANTENNA1", "ANTENNA2"]
    )
    freq = chan_freq(msp)
    cells = held & ~sc["FLAG"].any(-1)
    out = {}
    for label, tab in (("rang", rtab), ("casa", ctab)):
        corr, fl = cal_apply.apply(
            c["DATA"], sc["FLAG"], c["TIME"], c["ANTENNA1"], c["ANTENNA2"], freq,
            [*pre, tab], interp="linear", field_id=1,
        )  # fmt: skip
        m = cells & ~fl.any(-1)
        # float64 (post hoc after run -05: float32 rounded the mean to equality)
        r = corr[..., (0, 3)].astype(np.complex128) - c["MODEL_DATA"][..., (0, 3)]
        w = c["WEIGHT_SPECTRUM"][..., (0, 3)].astype(np.float64)
        out[label] = float(np.mean((w * np.abs(r) ** 2)[m]))
        out[f"{label}_cells"] = int(m.sum())
    out["relative"] = (out["rang"] - out["casa"]) / out["casa"]
    return out


# --- class T ------------------------------------------------------------------


def truth(run, argv):
    p = paths(argv)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    tr = dict(np.load(p["truth"]))
    edits = run / "edits"
    edits.mkdir()
    rows, values = a1_model(p["a1"], tr, [0, 2], parang="--parang-model" in argv)
    np.savez(edits / "a1-model.npz", rows=rows, values=values)
    nchan = values.shape[1]
    np.savez(edits / "a1-rfi.npz", rows=np.arange(len(rfi_flags(p["a1"], p["rfi"], nchan))),
             flag=rfi_flags(p["a1"], p["rfi"], nchan))  # fmt: skip
    write(edits / "model.json", {"model": "/run/edits/a1-model.npz"})
    write(
        edits / "noisy.json",
        {"model": "/run/edits/a1-model.npz", "flag": "/run/edits/a1-rfi.npz"},
    )
    (run / "ms").mkdir()
    steps = [
        "cp -r /src/twin.ms /run/ms/twin.ms",
        f"{CASA} -I /ex/oracle_gain.py casa-edit /run/ms/twin.ms /run/edits/model.json",
        "cp -r /src/a1.ms /run/ms/noisy.ms",
        f"{CASA} -I /ex/oracle_gain.py casa-edit /run/ms/noisy.ms /run/edits/noisy.json",
    ]
    cf.TIMINGS.clear()
    cf.docker(
        cf.CASA_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        [
            (run, "/run", "rw"),
            (HERE, "/ex", "ro"),
            (p["twin"], "/src/twin.ms", "ro"),
            (p["a1"], "/src/a1.ms", "ro"),
        ],
        "casa model columns",
    )
    pre = [caltable.read(p["a1k"]), caltable.read(p["a1b"])]
    raw = tr["raw_gain"]  # (integration, ant, 2)
    ttime = tr["time"]
    results = {}
    for label, msname, solints in (
        ("T-twin-ap", "twin", ["int"]),
        ("T-noisy-ap", "noisy", ["int", "inf"]),
    ):
        for solint in solints:
            for fid in (0, 2):
                name = f"{label}-{solint}-f{fid}"
                _, sol, info = cal_gain.gaincal(
                    run / "ms" / f"{msname}.ms", field_id=fid, solint=solint, refant="m000",
                    minsnr=3.0, minblperant=4, gaintable=pre, interp="linear",
                    stop_criterion=1e-10 if msname == "twin" else 1e-7,
                    stop_fraction=1.0 if msname == "twin" else 0.99,
                    max_iterations=200 if msname == "twin" else 50,
                )  # fmt: skip
                cols = columns(run / "ms" / f"{msname}.ms", ["TIME", "FIELD_ID"])
                rt = cols["TIME"][cols["FIELD_ID"] == fid]
                tb = info["time_bin"]
                nint = sol.gains.shape[0]
                tg = np.empty((nint, 1) + raw.shape[1:], complex)
                spread = 0.0
                for t in range(nint):
                    want = np.unique(rt[tb == t])
                    idx = np.searchsorted(ttime, want)
                    if not np.array_equal(ttime[idx], want):
                        raise SystemExit("truth times do not match the MS")
                    g = raw[idx]
                    pr = g[:, :, None, :] * np.conj(g[:, None, :, :])
                    spread = max(spread, float(np.abs(pr - pr[:1]).max()))
                    tg[t, 0] = g[0]
                tf = np.zeros(tg.shape, bool)
                r = {"truth_product_spread_in_interval": spread, "intervals": nint,
                     "flagged": int(sol.flags.sum())}  # fmt: skip
                prod, ok, pairs = cal_gain.baseline_products(sol.gains, sol.flags)
                tprod, _, _ = cal_gain.baseline_products(tg, tf)
                if msname == "twin":
                    d = np.abs(prod - tprod)[ok]
                    r["max_abs"] = float(d.max())
                    r["pass"] = bool(d.max() <= TRUTH_TOL and spread <= 1e-12)
                else:
                    pq = np.array(pairs).T
                    e = sol.err
                    s = np.sqrt(
                        np.abs(sol.gains[:, :, pq[1]]) ** 2 * e[:, :, pq[0]] ** 2
                        + np.abs(sol.gains[:, :, pq[0]]) ** 2 * e[:, :, pq[1]] ** 2
                    )
                    z = ((prod - tprod) / s)[ok]
                    n = z.size
                    limit = 3 * 1.2533 / np.sqrt(n)
                    r.update(
                        {
                            "n": int(n),
                            "median_re_z": float(np.median(z.real)),
                            "median_im_z": float(np.median(z.imag)),
                            "limit": float(limit),
                            "std_re_z": float(np.std(z.real)),
                            "std_im_z": float(np.std(z.imag)),
                            "median_abs_error": float(
                                np.median(np.abs(prod - tprod)[ok])
                            ),
                        }
                    )
                    r["pass"] = bool(
                        abs(r["median_re_z"]) <= limit
                        and abs(r["median_im_z"]) <= limit
                        and spread <= 1e-12
                    )
                results[name] = r
                print(name, "PASS" if r["pass"] else "FAIL", json.dumps(r), flush=True)
    report = {
        "class": "T",
        "cases": results,
        "timings": cf.TIMINGS,
        "seconds": time.perf_counter() - started,
        "pass": all(r["pass"] for r in results.values()),
    }
    write(run / "truth.json", report)
    return 0 if report["pass"] else 1


def main(argv):
    commands = {
        "quartical": quartical,
        "casa": casa,
        "recheck": recheck,
        "truth": truth,
    }
    if len(argv) < 3 or argv[1] not in commands:
        print(__doc__)
        return 2
    return commands[argv[1]](argv[2], argv[3:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
