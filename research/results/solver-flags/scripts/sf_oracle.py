"""solver-flags (#58), research/solver-flags.md section 5: the QuartiCal 0.2.7 oracle cases.

    QC_PY  sf_oracle.py cut  SRC.ms FIELD FLAGVERSION OUT.ms
    QC_PY  sf_oracle.py qc   SUB.ms OUT_DIR KIND [THREADS]     (KIND G or B; OUT_DIR/qc-1, qc-2)
    RANG_PY sf_oracle.py rang SUB.ms OUT_DIR KIND
    RANG_PY sf_oracle.py compare OUT_DIR KIND OUT.json

`cut`: the rows of FIELD (a name) of SRC.ms, with FLAG and FLAG_ROW taken from the
flag version FLAGVERSION (the flags before calibrate: after the flag stage), into a new
MS with the columns the solves read (python-casacore, deep copy).

`qc`: QuartiCal 0.2.7 on a copy of SUB.ms (DATA, MODEL_DATA, WEIGHT_SPECTRUM; one chunk
per scan, `time_chunk: 0`, `freq_chunk: 0`; `diag_complex`, `time_interval: 0`,
`freq_interval` 0 for G, 1 for B; no pre-apply; `mad_flags.enable` with QuartiCal's
defaults; `output.flags`): run 1 writes its MAD flags (`qc-1`), run 2 (`mad_flags` off)
re-solves on them (`qc-2`). Saves the gains, the gain flags and the flags each run left.

`rang`: rang's branch on a copy of SUB.ms: `rang.cal_gain.gaincal` (G) or
`rang.cal_bandpass.bandpass` (B) with `casa_rules=False` (QuartiCal's rules), the same
columns, `solver_flags` `quartical`, guard 1, `min_cells` 0, one round. The pass's new
flags are written to the copy, then the term is re-solved (rang's re-solve).

`compare`: O1/O3/O4 flags (cells unflagged before, any correlation) and O2 gains (the
parallel-hand products g_p g_q^* of the re-solves: max and median absolute difference).
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

COLUMNS = (
    "UVW,FLAG,FLAG_ROW,WEIGHT,SIGMA,ANTENNA1,ANTENNA2,ARRAY_ID,DATA_DESC_ID,EXPOSURE,"
    "FEED1,FEED2,FIELD_ID,INTERVAL,OBSERVATION_ID,PROCESSOR_ID,SCAN_NUMBER,STATE_ID,"
    "TIME,TIME_CENTROID,DATA,MODEL_DATA,WEIGHT_SPECTRUM"
)


def cut(src, field, version, out):
    from casacore.tables import table

    src, out = Path(src), Path(out)
    with table(str(src / "FIELD"), ack=False) as t:
        fid = list(t.getcol("NAME")).index(field)
    with table(str(src), ack=False) as t:
        q = t.query(f"FIELD_ID=={fid}", columns=COLUMNS)
        rows = q.rownumbers()
        q.copy(str(out), deep=True)
        q.close()
    rows = np.asarray(rows)
    lo, hi = int(rows.min()), int(rows.max()) + 1
    with table(str(src) + f".flagversions/flags.{version}", ack=False) as fv:
        flag = fv.getcol("FLAG", lo, hi - lo)[rows - lo]
        flag_row = fv.getcol("FLAG_ROW", lo, hi - lo)[rows - lo]
    with table(str(out), readonly=False, ack=False) as t:
        t.putcol("FLAG", flag)
        t.putcol("FLAG_ROW", flag_row)
    rec = {"src": str(src), "field": field, "field_id": fid, "version": version,
           "rows": len(rows), "first_row": lo, "flagged": float(flag.mean())}  # fmt: skip
    (out.parent / f"{out.name}.cut.json").write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec))


def _copy(src, dst):
    shutil.copytree(src, dst)
    lock = Path(dst) / "table.lock"
    if lock.exists():
        lock.unlink()


def _qc_options(kind, threads, mad):
    return [
        "input_ms.data_column=DATA", "input_model.recipe=MODEL_DATA",
        "input_ms.weight_column=WEIGHT_SPECTRUM", "input_ms.time_chunk=0",
        "input_ms.freq_chunk=0", "solver.terms=[G]", "solver.iter_recipe=[50]",
        "solver.convergence_criteria=1e-07", "solver.convergence_fraction=0.99",
        "solver.reference_antenna=0", "solver.robust=false", "G.type=diag_complex",
        "G.time_interval=0", f"G.freq_interval={0 if kind == 'G' else 1}",
        f"mad_flags.enable={'true' if mad else 'false'}", "mad_flags.threshold_bl=5",
        "mad_flags.threshold_global=10", "mad_flags.max_deviation=0",
        "mad_flags.whitening=disabled", "output.flags=true", "output.overwrite=true",
        f"dask.threads={threads}", f"solver.threads={threads}",
    ]  # fmt: skip


def _qc_run(ms, out, options):
    from casacore.tables import table
    from daskms.experimental.zarr import xds_from_zarr

    out.mkdir(parents=True, exist_ok=False)
    goq = Path(sys.executable).parent / "goquartical"
    command = [str(goq), f"input_ms.path={ms}",
               f"output.gain_directory={out / 'gains.qc'}",
               f"output.log_directory={out / 'logs.qc'}", *options]  # fmt: skip
    t0 = time.perf_counter()
    with (out / "quartical.log").open("x") as log:
        proc = subprocess.run(
            ["/usr/bin/time", "-f", "TIME %e %M", *command],
            stdout=log, stderr=subprocess.STDOUT, check=False,
        )  # fmt: skip
    rec = {"command": command, "returncode": proc.returncode,
           "seconds": time.perf_counter() - t0}  # fmt: skip
    for line in (out / "quartical.log").read_text().splitlines():
        if line.startswith("TIME "):
            _, wall, rss = line.split()
            rec["time_wall"], rec["max_rss_mb"] = float(wall), int(rss) / 1024
    if proc.returncode != 0:
        (out / "summary.json").write_text(json.dumps(rec, indent=1) + "\n")
        raise SystemExit(f"QuartiCal failed: {out}")
    dss = [d.compute() for d in xds_from_zarr(f"{out / 'gains.qc'}::G")]
    dss.sort(key=lambda d: float(d.gain_time.values[0]))
    gains = np.concatenate([d.gains.transpose(
        "gain_time", "gain_freq", "antenna", "direction", "correlation"
    ).values[..., 0, :] for d in dss])  # fmt: skip
    gflags = np.concatenate([d.gain_flags.transpose(
        "gain_time", "gain_freq", "antenna", "direction"
    ).values[..., 0] for d in dss])  # fmt: skip
    np.save(out / "gains.npy", gains)
    np.save(out / "gain_flags.npy", gflags)
    with table(str(ms), ack=False) as t:
        np.save(out / "flag.npy", t.getcol("FLAG").any(-1))
    rec.update(shape=list(gains.shape), chunks=len(dss),
               conv_iter=[np.asarray(d.attrs.get("conv_iter", -1)).tolist() for d in dss])  # fmt: skip
    (out / "summary.json").write_text(json.dumps(rec, indent=1, default=str) + "\n")


def qc(sub, out, kind, threads=4):
    from casacore.tables import table

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with table(str(sub), ack=False) as t:
        np.save(
            out / "flag-before.npy",
            t.getcol("FLAG").any(-1) | t.getcol("FLAG_ROW")[:, None],
        )
    work = out / "qc.ms"
    if work.exists():
        shutil.rmtree(work)
    _copy(sub, work)
    for k, mad in ((1, True), (2, False)):
        _qc_run(work, out / f"qc-{k}", _qc_options(kind, int(threads), mad))
    shutil.rmtree(work)


def rang(sub, out, kind):
    from rang import cal_bandpass, cal_gain, core_config, core_ms, solver_flags

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    work = out / "rang.ms"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(sub, work)  # rang keeps table.lock (its writer needs it)
    with core_ms.open_table(work) as t:
        field = int(np.unique(t.getcol("FIELD_ID"))[0])
    cfg = dict(core_config.resolve({"schema": "rang-config", "version": 1})[0]["calibrate"]["solver_flags"])  # fmt: skip
    cfg.update(mode="quartical", guard=1.0, min_cells=0, rounds=1, tripwire=1.0)
    first = {}

    def resolve_hook(sol):
        first.setdefault("gains", np.asarray(sol.gains))
        first.setdefault("flags", np.asarray(sol.flags))

    writer = solver_flags.or_writer(
        work, flag_backup="rang_original", stage="calibrate"
    )
    captured = []

    def write(rows, new):
        captured.append((np.asarray(rows), np.asarray(new)))
        writer(rows, new)

    real_rounds = solver_flags.rounds

    def rounds(fld, tb, sol, c, w, resolve):
        resolve_hook(sol)
        return real_rounds(fld, tb, sol, c, w, resolve)

    solver_flags.rounds = rounds
    common = {"field_id": field, "refant": 0, "casa_rules": False,
              "model_column": "MODEL_DATA", "weight_column": "WEIGHT_SPECTRUM",
              "solver_flags": {"cfg": cfg, "write": write}}  # fmt: skip
    t0 = time.perf_counter()
    if kind == "G":
        _, sol, info = cal_gain.gaincal(work, calmode="ap", **common)
    else:
        _, sol, info = cal_bandpass.bandpass(work, fillgaps=0, **common)
    seconds = time.perf_counter() - t0
    with core_ms.open_table(work) as t:
        nrow, nchan = t.getcol("TIME").size, t.getcol("FLAG", 0, 1).shape[1]
    new = np.zeros((nrow, nchan), bool)
    for rows, n in captured:
        new[rows] |= n
    np.save(out / "rang-new.npy", new)
    np.save(out / "rang-gains-1.npy", first["gains"])
    np.save(out / "rang-gain-flags-1.npy", first["flags"])
    np.save(out / "rang-gains-2.npy", np.asarray(sol.gains))
    np.save(out / "rang-gain-flags-2.npy", np.asarray(sol.flags))
    rec = {"kind": kind, "seconds": seconds, "solver_flags": info["solver_flags"]}
    (out / "rang.json").write_text(json.dumps(rec, indent=1, default=str) + "\n")
    shutil.rmtree(work)


def _products(g, f, qg, qf):
    """|g_p g_q^* - qg_p qg_q^*| over p < q, both unflagged, per hand."""
    p, q = np.triu_indices(g.shape[2], 1)
    if f.ndim == 4:
        f = f.any(-1)
    ok = ~f[:, :, p] & ~f[:, :, q] & ~qf[:, :, p] & ~qf[:, :, q]
    d = []
    for h in range(2):
        a = g[:, :, p, h] * np.conj(g[:, :, q, h])
        b = qg[:, :, p, h] * np.conj(qg[:, :, q, h])
        d.append(np.abs(a - b)[ok & np.isfinite(a) & np.isfinite(b)])
    d = np.concatenate(d)
    return {"products": int(d.size), "max": float(d.max()) if d.size else None,
            "median": float(np.median(d)) if d.size else None}  # fmt: skip


def compare(out, kind, dst):
    out = Path(out)
    before = np.load(out / "flag-before.npy")
    qc_new = np.load(out / "qc-1" / "flag.npy") & ~before
    rang_new = np.load(out / "rang-new.npy")
    cells = int(before.size)
    diff = qc_new ^ rang_new
    rec = {"kind": kind, "cells": cells, "unflagged_before": int((~before).sum()),
           "quartical_new": int(qc_new.sum()), "rang_new": int(rang_new.sum()),
           "differ": int(diff.sum()), "differ_fraction": float(diff.sum() / cells),
           "only_quartical": int((qc_new & ~rang_new).sum()),
           "only_rang": int((rang_new & ~qc_new).sum())}  # fmt: skip
    rec["flags_pass"] = rec["differ_fraction"] <= 1e-4
    where = np.argwhere(diff)
    rec["differing_cells_first_100"] = where[:100].tolist()
    qg2, qf2 = (
        np.load(out / "qc-2" / "gains.npy"),
        np.load(out / "qc-2" / "gain_flags.npy"),
    )
    rg2, rf2 = np.load(out / "rang-gains-2.npy"), np.load(out / "rang-gain-flags-2.npy")
    qg2 = qg2[..., (0, -1)] if qg2.shape[-1] == 4 else qg2
    rec["resolve_products"] = _products(rg2, rf2, qg2, qf2 != 0)
    p = rec["resolve_products"]
    rec["gains_pass"] = (
        p["max"] is not None and p["max"] <= 1e-4 and p["median"] <= 1e-6
    )
    qg1, qf1 = (
        np.load(out / "qc-1" / "gains.npy"),
        np.load(out / "qc-1" / "gain_flags.npy"),
    )
    qg1 = qg1[..., (0, -1)] if qg1.shape[-1] == 4 else qg1
    rec["first_solve_products"] = _products(
        np.load(out / "rang-gains-1.npy"),
        np.load(out / "rang-gain-flags-1.npy"),
        qg1,
        qf1 != 0,
    )
    Path(dst).write_text(json.dumps(rec, indent=1) + "\n")
    print(
        json.dumps({k: v for k, v in rec.items() if k != "differing_cells_first_100"})
    )


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    {"cut": cut, "qc": qc, "rang": rang, "compare": compare}[cmd](*args)
