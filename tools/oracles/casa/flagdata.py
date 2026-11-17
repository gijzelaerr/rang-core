# SPDX-License-Identifier: GPL-3.0-or-later
"""CASA `flagdata` as the oracle of task V8b (research/v8b-flagdata.md).

Runs inside `rang-o-casa:6.7.6.14` with `/opt/casa/bin/python -I`. The plan
is a JSON list of cases, each `{"name", "input", "calls": [params, ...]}`:
the input MS (or calibration table) is copied to `OUT/work/NAME`, every call
runs as `casatasks.flagdata(vis=COPY, flagbackup=False, **params)` in order,
and then FLAG and FLAG_ROW of the copy are written to `OUT/NAME.npz`
(`np.packbits` of FLAG in (row, chan, corr) order, its shape, FLAG_ROW) with
each call's return value and wall time in `OUT/NAME.json`. The copy is
deleted unless the case says `"keep": true`. Inputs are mounted read-only.

Usage: flagdata.py OUT PLAN.json [NAME ...]
"""

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def read_flags(path):
    from casatools import table

    tb = table()
    tb.open(str(path))
    try:
        flag = tb.getcol("FLAG")  # (corr, chan, row)
        flag_row = tb.getcol("FLAG_ROW") if "FLAG_ROW" in tb.colnames() else None
    finally:
        tb.close()
    flag = np.ascontiguousarray(np.transpose(flag, (2, 1, 0)))
    return flag, flag_row


def run_case(out, case):
    from casatasks import flagdata

    name = case["name"]
    work = out / "work" / name
    if work.exists():
        shutil.rmtree(work)
    work.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(case["input"], work)
    log = {"name": name, "input": case["input"], "calls": []}
    for params in case["calls"]:
        t0 = time.time()
        error = None
        try:
            ret = flagdata(vis=str(work), flagbackup=False, **params)
        except Exception as exc:  # noqa: BLE001 - recorded, the case goes on
            ret, error = None, repr(exc)
        log["calls"].append({"params": params, "return": plain(ret), "error": error,
                             "wall_s": time.time() - t0})  # fmt: skip
    flag, flag_row = read_flags(work)
    np.savez_compressed(
        out / f"{name}.npz",
        flag=np.packbits(flag.reshape(-1)),
        shape=np.array(flag.shape),
        flag_row=np.zeros(0, bool) if flag_row is None else flag_row,
    )
    log["flagged"] = int(flag.sum())
    log["cells"] = int(flag.size)
    (out / f"{name}.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    if not case.get("keep"):
        shutil.rmtree(work)
    return log


def main(argv):
    out = Path(argv[0])
    plan = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    only = set(argv[2:])
    for case in plan:
        if only and case["name"] not in only:
            continue
        t0 = time.time()
        log = run_case(out, case)
        errs = [c["error"] for c in log["calls"] if c["error"]]
        print(f"{case['name']}: {log['flagged']}/{log['cells']} flagged, "
              f"{time.time() - t0:.1f} s{' ERROR ' + errs[0] if errs else ''}",
              flush=True)  # fmt: skip


if __name__ == "__main__":
    main(sys.argv[1:])
