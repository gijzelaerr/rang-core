"""E2-B's 3C 286 transfer and 1934-638 leakage rows, rang's arm
(research/e2-acceptance.md 6.5, 7.1), through rang's library on the CASA copy
R/casa/e2b.ms, which holds rang's model as RANG_MODEL_DATA and RECEPTOR_ANGLE
-90 (the apply's receptor angle is passed explicitly, as the chain does).

    python e2_transfer.py selftest R OUT_DIR
    python e2_transfer.py rang R DEV_RUN OUT_DIR [--average-freq]

Every solve and apply is the chain's own call (`rang.cal_chain._solve_one` and
`_solve_pol`, `rang.applycal.applycal`), with the term specs built by
`rang.core_pipeline.chain_terms` from R's resolved configuration (refant auto
resolved as the chain does), unit weights (`data.weights: uniform`),
`average_time` and, for the amended arm, `average_freq`.

`selftest`: FLAG from R's `rang_apply_*` version (rang's FLAG before apply),
then the E2-B run's own K, G, B, Gpol, Kcross, Xf and Df applied to
J1331+3030 scan 17 into column E2_XFER. CORRECTED_DATA (RANG_CORRECTED_DATA)
and FLAG (RANG_FLAG) must match at class C: the library route reproduces the
chain, so a rotation slip here cannot be read as the chi finding.

`rang`: FLAG from R's flag-stage version (`rang_calibrate_*`, FLAG after rang's
flag stage, identical in both arms), then, per case:
  xfer17   G phase-only (p, 60 s, parang; the chain's Gpol spec) on J1331+3030
           scan 17 with the development K, G, B pre-applied, against 3C 286's
           model; apply dev K, G, B, that G, dev Kcross, Xf, Df.
  leak18p  the same on J1939-6342 scan 18, against 1934-638's model.
  leak18ap scan 18's own G (ap, inf; the chain's primary G spec, dev K
           pre-applied); apply dev K, that G, dev B, Kcross, Xf, Df.
Each apply writes E2_XFER for that field and scan (FLAG restored before each
case), and the case's visibilities are scored or imaged before the next one:
xfer17 by `e2_rows_b.py transfer`, the leak cases by `e2_leakage.py`.
This script writes the tables and OUT_DIR/<case>.json; the caller runs the
scorers between cases (`--case`).
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

RECEPTOR = math.radians(-90.0)
CHAIN_INTERP = {"K": "linear", "G": "linear", "B": "linear", "Gpol": "linear",
                "Kcross": "nearest", "Xf": "nearest", "Df": "nearest"}  # fmt: skip


def resolved(r):
    return json.loads((Path(r) / "rang-run-moved" / "config.resolved.json").read_text())


def state(r):
    return json.loads((Path(r) / "rang-run-moved" / "state.json").read_text())


def terms_for(config, ms):
    from rang import cal_refant, core_pipeline

    cfg, _ = cal_refant.resolve_config(config, ms)
    info = core_pipeline.inspect_ms(ms)
    path = Path(__file__).resolve().parent / "e2b.yaml"  # resolves the strategy file
    terms = {t["name"]: t for t in core_pipeline.chain_terms(cfg, info, path)}
    return cfg, info, terms


def field_id(ms, name):
    from rang import core_ms

    with core_ms.open_table(Path(ms) / "FIELD") as t:
        return [str(n) for n in t.getcol("NAME")].index(name)


def restore(ms, version):
    from rang import core_writeback

    return int(core_writeback.restore_flags(ms, version))


def apply(ms, tables, names, fid, scan, out):
    from rang import applycal

    t0 = time.perf_counter()
    summ = applycal.applycal(
        ms, [tables[n] for n in names], interp=[CHAIN_INTERP[n] for n in names],
        gainfield=[""] * len(names), calwt=[False], field=[fid], applymode="calflag",
        column="E2_XFER", flag_backup="e2_xfer_backup", stage="apply", scan=[scan],
        parang=True, frame="casa", receptor_angle=RECEPTOR,
    )  # fmt: skip
    out["apply"] = {"tables": names, "seconds": time.perf_counter() - t0,
                    "cells_flagged_before": summ["cells_flagged_before"],
                    "cells_flagged_after": summ["cells_flagged_after"],
                    "uncovered": summ["uncovered"]}  # fmt: skip


def selftest(r, out_dir):
    from rang import core_ms
    from rang.formats import caltable

    r, out_dir = Path(r), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ms = r / "casa" / "e2b.ms"
    st = state(r)
    version = st["stages"]["apply"]["flag_version"]
    rec = {"flag_version": version, "restored_rows": restore(ms, version)}
    cal = r / "rang-run-moved" / "calibrate"
    tables = {
        n: caltable.read(cal / n) for n in ("K", "G", "B", "Gpol", "Kcross", "Xf", "Df")
    }
    fid = field_id(ms, "J1331+3030")
    apply(ms, tables, ["K", "G", "B", "Gpol", "Kcross", "Xf", "Df"], fid, 17, rec)
    eps = float(np.finfo(np.float32).eps)
    acc = {"cells": 0, "over_class_c": 0, "flag_elements_differ": 0, "max_rel": 0.0,
           "max_eps_of_cell_max": 0.0}  # fmt: skip
    with core_ms.open_table(ms) as t:
        n = t.nrows
        for r0 in range(0, n, 2000):
            k = min(2000, n - r0)
            sel = (np.asarray(t.getcol("FIELD_ID", r0, k)) == fid) & (
                np.asarray(t.getcol("SCAN_NUMBER", r0, k)) == 17
            )
            if not sel.any():
                continue
            a = np.asarray(t.getcol("E2_XFER", r0, k))[sel]
            b = np.asarray(t.getcol("RANG_CORRECTED_DATA", r0, k))[sel]
            fa = np.asarray(t.getcol("FLAG", r0, k), bool)[sel]
            fb = np.asarray(t.getcol("RANG_FLAG", r0, k), bool)[sel]
            acc["flag_elements_differ"] += int((fa != fb).sum())
            good = ~(fa | fb)
            d = np.abs(a - b)
            cmax = np.abs(b).max(-1, keepdims=True)
            rel = np.where(np.abs(b) > 0, d / np.maximum(np.abs(b), 1e-30), 0)
            ok = (rel <= 1e-6) | (d <= 11 * eps * cmax)
            cell_bad = (~ok & good).any(-1)
            acc["cells"] += int(good.any(-1).sum())
            acc["over_class_c"] += int(cell_bad.sum())
            if good.any():
                acc["max_rel"] = max(acc["max_rel"], float(rel[good].max()))
                acc["max_eps_of_cell_max"] = max(
                    acc["max_eps_of_cell_max"],
                    float((d / np.maximum(cmax, 1e-30))[good].max() / eps),
                )
    rec.update(acc, met=acc["over_class_c"] == 0 and acc["flag_elements_differ"] == 0)
    (out_dir / "selftest.json").write_text(
        json.dumps(rec, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(rec, indent=1))
    return 0


def rang_case(r, dev_run, out_dir, case, average_freq):
    from rang import cal_chain
    from rang.formats import caltable

    r, out_dir = Path(r), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ms = r / "casa" / "e2b.ms"
    st = state(r)
    version = st["stages"]["calibrate"]["flag_version"]
    rec = {"case": case, "flag_version": version, "restored_rows": restore(ms, version),
           "dev_run": str(dev_run), "average_freq": bool(average_freq)}  # fmt: skip
    from rang import core_chunks

    cfg, info, terms = terms_for(resolved(r), ms)
    dev = Path(dev_run) / "calibrate"
    tables = {n: caltable.read(dev / n) for n in ("K", "G", "B", "Kcross", "Xf", "Df")}
    # The chain's memory budget (data.memory_limit_gb, task W3b), as
    # core_pipeline passes it to cal_chain.run; omitted in the first version
    # (2026-11-13: xfer17 asked for 27.8 GiB in one interval and stopped
    # before any value was written).
    common = {"model_column": "RANG_MODEL_DATA", "weight_column": None,
              "average_time": True,
              "budget": core_chunks.budget(cfg, info).chain()}  # fmt: skip
    if average_freq:
        common["average_freq"] = True
    entries = {n: {"table": t} for n, t in tables.items()}
    if case in ("xfer17", "leak18p"):
        field, scan = ("J1331+3030", 17) if case == "xfer17" else ("J1939-6342", 18)
        spec = dict(terms["Gpol"], fields=[field_id(ms, field)], name="Gscan")
        spec["model_column"] = "RANG_MODEL_DATA"
        common["scan"] = [scan]
        t0 = time.perf_counter()
        g, srec = cal_chain._solve_pol(ms, spec, spec["fields"][0], entries, common)
        names = ["K", "G", "B", "Gscan", "Kcross", "Xf", "Df"]
        interp = dict(CHAIN_INTERP, Gscan="linear")
    else:
        field, scan = "J1939-6342", 18
        spec = dict(terms["G"], fields=[field_id(ms, field)], name="Gscan")
        common["scan"] = [scan]
        t0 = time.perf_counter()
        g, _sol, _info = cal_chain._solve_one(
            ms, spec, spec["fields"][0], entries, common
        )
        srec = {}
        names = ["K", "Gscan", "B", "Kcross", "Xf", "Df"]
        interp = dict(CHAIN_INTERP, Gscan="linear")
    rec["solve_seconds"] = time.perf_counter() - t0
    rec["solve"] = {k: v for k, v in srec.items() if not isinstance(v, (list, dict))}
    rec["spec"] = {k: v for k, v in spec.items() if k not in ("fields",)}
    caltable.write(g, out_dir / f"{case}-Gscan")
    tables["Gscan"] = g
    CHAIN_INTERP.update(interp)
    apply(ms, tables, names, spec["fields"][0], scan, rec)
    rec["field"], rec["scan"] = field, scan
    (out_dir / f"{case}.json").write_text(
        json.dumps(rec, indent=1, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(rec, indent=1, default=str)[:3000])
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["selftest", "rang"])
    ap.add_argument("r")
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--case", choices=["xfer17", "leak18p", "leak18ap"])
    ap.add_argument("--average-freq", action="store_true")
    a = ap.parse_args(argv)
    if a.mode == "selftest":
        return selftest(a.r, a.rest[0])
    return rang_case(a.r, a.rest[0], a.rest[1], a.case, a.average_freq)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
