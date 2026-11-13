# SPDX-License-Identifier: GPL-3.0-or-later
"""rang's side of V8b (research/v8b-flagdata.md): every case of a
`v8b_plan.py` plan through `rang.tasks.flagdata` on a fresh copy of its
input, with FLAG, FLAG_ROW and the calls' returns written in the format of
`flagdata.py` (CASA's side) so that `compare_flagdata.py` reads both.

Usage: rang_flagdata.py OUT PLAN.json [NAME ...]

Inputs are mapped from the container paths of `flagdata.sh` to Windows paths
(`INPUTS`, overridable with RANG_V8B_INPUTS=<dir> for /in/luno.ms and
/in/fixture, which live in WSL and are copied there once).
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

SCRATCH = Path(os.environ.get("RANG_V8B_SCRATCH", r"D:\rang\scratch\v8b-20261113"))
INPUTS = {
    "/in/cases": SCRATCH / "cases",
    "/in/luno.ms": Path(os.environ.get("RANG_V8B_INPUTS", SCRATCH / "inputs")) / "luno.ms",
    "/in/a1.ms": Path(r"D:\rang\outputs\c2a-20261106-03\casa\a1.ms"),
    "/in/fixture": Path(os.environ.get("RANG_V8B_INPUTS", SCRATCH / "inputs")) / "fixture",
    "/in/df": Path(r"D:\rang\outputs\c6-20261106-01\casa"),
    "/in/heldout": SCRATCH / "heldout",
}


def local(path):
    for prefix, target in INPUTS.items():
        if path == prefix or path.startswith(prefix + "/"):
            return Path(str(target) + path[len(prefix) :])
    raise SystemExit(f"no local path for {path}")


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def read_flags(path):
    from rang import core_ms

    with core_ms.open_table(path) as t:
        flag = np.asarray(t.getcol("FLAG"), bool)
        flag_row = np.asarray(t.getcol("FLAG_ROW"), bool) if "FLAG_ROW" in t.columns else None
    return flag, flag_row


def run_case(out, case):
    from rang import tasks

    name = case["name"]
    work = out / "work" / name
    if work.exists():
        shutil.rmtree(work)
    work.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(local(case["input"]), work)
    log = {"name": name, "input": case["input"], "calls": []}
    for params in case["calls"]:
        t0 = time.time()
        error = None
        try:
            ret = tasks.flagdata(vis=str(work), flagbackup=False, **params)
        except Exception as exc:  # recorded, the case goes on
            ret, error = None, f"{type(exc).__name__}: {exc}"
        log["calls"].append({"params": params, "return": plain(ret), "error": error,
                             "wall_s": time.time() - t0})  # fmt: skip
    flag, flag_row = read_flags(work)
    np.savez_compressed(out / f"{name}.npz", flag=np.packbits(flag.reshape(-1)),
                        shape=np.array(flag.shape),
                        flag_row=np.zeros(0, bool) if flag_row is None else flag_row)  # fmt: skip
    log["flagged"] = int(flag.sum())
    log["cells"] = int(flag.size)
    (out / f"{name}.json").write_text(json.dumps(log, indent=1), encoding="utf-8", newline="\n")
    shutil.rmtree(work)
    return log


def main(argv):
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    only = set(argv[2:])
    for case in plan:
        if only and not any(case["name"] == o or case["name"].startswith(o) for o in only):
            continue
        t0 = time.time()
        log = run_case(out, case)
        errs = [c["error"] for c in log["calls"] if c["error"]]
        print(f"{case['name']}: {log['flagged']}/{log['cells']} flagged, "
              f"{time.time() - t0:.1f} s{' ERROR ' + errs[0] if errs else ''}", flush=True)  # fmt: skip


if __name__ == "__main__":
    main(sys.argv[1:])
