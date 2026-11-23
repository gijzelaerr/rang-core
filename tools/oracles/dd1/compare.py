# SPDX-License-Identifier: MIT
"""DD1 measurement (research/dd1-facet-gains.md, sections 5 and 6).

    python tools/oracles/dd1/compare.py SIMDIR QCDIR OUT.json [--threads 1,8]

Reads SIMDIR/dd1.ms with rang's reader, solves cases P1-P4 with
`rang._core.cal_gain_solve_dd`, reads QuartiCal's stores QCDIR/gains-P<k>/G,
and evaluates gate A (parity) on every case and gate T (truth, noiseless) on
P3; the same truth statistic is reported for P1, P2. Timing: rang's solve
in-process at each thread count (RAYON_NUM_THREADS is fixed per process, so
every count runs in its own subprocess, `--solve-only`).
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

CASES = {
    "P1": ("DATA", 4, 0, []),
    "P2": ("DATA", 1, 4, []),
    "P3": ("DATA_NF", 4, 0, []),
    "P4": ("DATA", 4, 0, [0]),
}
NDIR = 4
TOL_A = 1e-6
TOL_FRAC = 1e-12
TOL_T = 1e-4


def load(ms):
    from rang import core_ms

    t = core_ms.open_table(str(ms))
    cols = {
        c: t.getcol(c)
        for c in ("TIME", "ANTENNA1", "ANTENNA2", "WEIGHT_SPECTRUM", "FLAG", "FLAG_ROW")
    }
    cols["DATA"] = t.getcol("DATA")
    cols["DATA_NF"] = t.getcol("DATA_NF")
    cols["MODEL"] = np.stack([t.getcol(f"MODEL_D{d}") for d in range(NDIR)], axis=2)
    nant = int(max(cols["ANTENNA1"].max(), cols["ANTENNA2"].max())) + 1
    cols["nant"] = nant
    return cols


def bins(c, ti, fi):
    _utime, tindex = np.unique(c["TIME"], return_inverse=True)
    time_bin = (tindex // ti).astype(np.uint32)
    nchan = c["DATA"].shape[1]
    freq_bin = (
        np.zeros(nchan, np.uint32)
        if fi == 0
        else (np.arange(nchan) // fi).astype(np.uint32)
    )
    return time_bin, freq_bin, int(time_bin.max()) + 1, int(freq_bin.max()) + 1


def solve(c, case):
    from rang import cal_gain

    col, ti, fi, pinned = CASES[case]
    time_bin, freq_bin, _, _ = bins(c, ti, fi)
    t0 = time.perf_counter()
    sol = cal_gain.solve_dd(
        c[col], c["MODEL"], c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"],
        c["ANTENNA1"], c["ANTENNA2"], time_bin, nant=c["nant"], freq_bin=freq_bin,
        refant=0, pinned_directions=pinned,
    )  # fmt: skip
    seconds = time.perf_counter() - t0
    return {
        "gains": sol.gains,
        "flags": sol.flags,
        "iterations": sol.iterations,
        "fraction": sol.converged_fraction,
        "seconds": seconds,
    }


def quartical(qcdir, case):
    from rang.formats import quartical_store as qs

    parts = qs.read_term(Path(qcdir) / f"gains-{case}", "G")
    if len(parts) != 1:
        raise ValueError(f"{case}: {len(parts)} partitions, expected 1")
    v = parts[0].variables
    return {
        "gains": np.asarray(v["gains"].data),
        "flags": np.asarray(v["gain_flags"].data),
        "iterations": int(np.asarray(v["conv_iter"].data).ravel()[0]),
        "fraction": float(np.asarray(v["conv_perc"].data).ravel()[0]),
    }


def products(g, nant):
    """(t, f, pair, dir, hand) g_p conj(g_q) over p < q."""
    p, q = np.triu_indices(nant, 1)
    return g[:, :, p] * np.conj(g[:, :, q])


def gate_a(r, o, nant):
    out = {"flags_equal": bool(np.array_equal(r["flags"], o["flags"]))}
    ok = r["flags"] == 0
    out["gain_max_abs_diff"] = (
        float(np.abs(r["gains"] - o["gains"])[ok].max()) if ok.any() else 0.0
    )
    pr, po = products(r["gains"], nant), products(o["gains"], nant)
    p, q = np.triu_indices(nant, 1)
    okp = (o["flags"][:, :, p] == 0) & (o["flags"][:, :, q] == 0)
    out["product_max_abs_diff"] = (
        float(np.abs(pr - po)[okp].max()) if okp.any() else 0.0
    )
    out["iterations"] = [r["iterations"], o["iterations"]]
    out["fraction"] = [r["fraction"], o["fraction"]]
    out["pass"] = bool(
        out["flags_equal"]
        and out["gain_max_abs_diff"] <= TOL_A
        and out["product_max_abs_diff"] <= TOL_A
        and r["iterations"] == o["iterations"]
        and abs(r["fraction"] - o["fraction"]) <= TOL_FRAC
    )
    return out


def truth_stat(sol, truth, case, nant):
    _, ti, _fi, _ = CASES[case]
    g = truth["gains"]  # (nblock, nant, ndir, 2), block of BLOCK integrations
    block = int(truth["block"])
    ntime = sol["gains"].shape[0]
    # Map each solution time bin to its truth block (ti divides BLOCK).
    tb = (np.arange(ntime) * ti) // block
    tg = g[tb][:, None]  # (t, 1, nant, ndir, 2), constant over frequency
    tg = np.broadcast_to(tg, sol["gains"].shape)
    ps, pt = products(sol["gains"], nant), products(tg, nant)
    p, q = np.triu_indices(nant, 1)
    ok = (sol["flags"][:, :, p] == 0) & (sol["flags"][:, :, q] == 0)
    rel = (np.abs(ps - pt) / np.abs(pt))[np.broadcast_to(ok[..., None], ps.shape)]
    per_dir = {}
    for d in range(NDIR):
        rd = (np.abs(ps - pt) / np.abs(pt))[..., d, :][
            np.broadcast_to(ok[..., d, None], ps[..., d, :].shape)
        ]
        per_dir[f"d{d}"] = {
            "median": float(np.median(rd)),
            "p95": float(np.percentile(rd, 95)),
        }
    return {
        "max": float(rel.max()),
        "median": float(np.median(rel)),
        "p95": float(np.percentile(rel, 95)),
        "per_direction": per_dir,
    }


def timing(sim, threads):
    out = {}
    for n in threads:
        env = dict(os.environ, RAYON_NUM_THREADS=str(n))
        r = subprocess.run(
            [sys.executable, __file__, str(sim), "-", "-", "--solve-only"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        out[str(n)] = json.loads(r.stdout.strip().splitlines()[-1])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("sim")
    ap.add_argument("qcdir")
    ap.add_argument("out")
    ap.add_argument("--threads", default="1,8")
    ap.add_argument("--solve-only", action="store_true")
    a = ap.parse_args(argv)
    sim = Path(a.sim)
    c = load(sim / "dd1.ms")
    if a.solve_only:
        res = {}
        for case in CASES:
            s = solve(c, case)
            res[case] = {"seconds": s["seconds"], "iterations": s["iterations"]}
        print(json.dumps(res))
        return
    truth = dict(np.load(sim / "truth.npz"))
    nant = c["nant"]
    record = {"note": "research/dd1-facet-gains.md", "cases": {}}
    for case in CASES:
        r = solve(c, case)
        o = quartical(a.qcdir, case)
        entry = {"A": gate_a(r, o, nant), "rang_seconds_default_threads": r["seconds"]}
        if case != "P4":
            entry["truth_rang"] = truth_stat(r, truth, case, nant)
            entry["truth_quartical"] = truth_stat(o, truth, case, nant)
        record["cases"][case] = entry
    t3 = record["cases"]["P3"]["truth_rang"]["max"]
    record["T"] = {"P3_max_rel": t3, "pass": bool(t3 <= TOL_T)}
    record["A_all_pass"] = all(e["A"]["pass"] for e in record["cases"].values())
    record["timing_rang"] = timing(sim, [int(x) for x in a.threads.split(",")])
    Path(a.out).write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("A_all_pass", "T")}))
    for case, e in record["cases"].items():
        print(case, json.dumps(e["A"]))


if __name__ == "__main__":
    main()
