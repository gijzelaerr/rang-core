"""F6: F5's scorer (examples/f5_heldout.py) on F6's sets (research/f6-flagger.md 2d).

Usage:
  python examples/f6_heldout.py real RUN --set sarao:<cbid>:<scan> --method M.json
         --sarao-root C_ROOT [--validation | --heldout-read] [--data-root R] [--ao-sif S]
  python examples/f6_heldout.py real RUN --set luno:MAIN_7 ... (F5's sets, F5's loader)
  python examples/f6_heldout.py r2 RUN --set ... --method M.json --validation (R2 only)
  python examples/f6_heldout.py sim RUN --class calibrator --method M.json [--validation]

A SARAO set is one scan of session C's stage-1 manifest, cut as in training: the
channel window 1024-3071 (1070-1498 MHz) and the central 32 dumps. T is F5's T
computed on the cut scan (as for LUNO and ESO137, needed for the injected cases); A
is C's AOFlagger 2.13 `firstpass_QUV` label for the same cells, OR W3. The manifest's
split must match: validation sets need --validation, held-out sets --heldout-read.
Every case is one shard, F5's layout, so f5_verdict.py reads the result unchanged.
"""

import importlib.util
import json
import sys
from pathlib import Path

from rang import f5flag as f5

HERE = Path(__file__).resolve().parent


def _module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SARAO_ROOT = None
HELDOUT_READ = False


def sarao_entry(root, cbid, scan):
    m = json.loads((Path(root) / "manifests" / "stage1.json").read_text())
    for e in m["entries"]:
        if e["cbid"] == cbid and int(e["scan"]) == int(scan):
            return e
    raise KeyError(f"{cbid} scan {scan} not in the stage-1 manifest")


def load_sarao_set(spec, heldout):
    _, cbid, scan = spec.split(":")
    e = sarao_entry(SARAO_ROOT, cbid, scan)
    if e["split"] == "train":
        raise PermissionError(f"{spec} is a training scan")
    if e["split"] == "heldout" and not (heldout and HELDOUT_READ):
        raise PermissionError(f"{spec} is held out; pass --heldout-read at scoring")
    if e["split"] == "validation" and heldout:
        raise PermissionError(f"{spec} is validation; pass --validation")
    sh = _module("f6_shards")
    scan_ = f5.load_sarao(
        Path(SARAO_ROOT) / e["ms"],
        e["class"],
        Path(SARAO_ROOT) / "labels",
        cbid,
        e["scan"],
    )
    scan_, _ = sh.central_dumps(scan_)
    return scan_


def main():
    global SARAO_ROOT, HELDOUT_READ
    argv = list(sys.argv[1:])
    for flag in ("--sarao-root",):
        if flag in argv:
            i = argv.index(flag)
            SARAO_ROOT = argv[i + 1]
            del argv[i : i + 2]
    if "--heldout-read" in argv:
        HELDOUT_READ = True
        argv.remove("--heldout-read")
    hd = _module("f5_heldout")
    f5_load, f5_a = f5.load, f5.a_flags

    def load(spec, heldout=False):
        if spec.startswith("sarao:"):
            return load_sarao_set(spec, heldout)
        return f5_load(spec, heldout=heldout)

    def a_flags(scan, w3, workdir, data=None):
        if "teachers" in scan:
            if data is not None:
                raise ValueError("C's A labels exist for the uninjected data only")
            a = scan["teachers"]["A"] | w3
            rec = {
                "source": "session C, AOFlagger 2.13 firstpass_QUV",
                "cells": int(a.sum()),
            }
            return a, rec
        return f5_a(scan, w3, workdir, data)

    f5.load, f5.a_flags = load, a_flags
    if argv and argv[0] == "r2":
        # Fix 5: R2 per seed, on validation only, for the seeds that are not scored in full.
        argv[0] = "real"
        hd.real = lambda a: r2_only(hd, a)
    sys.argv = [sys.argv[0], *argv]
    hd.main()


def r2_only(hd, a):
    if not a.validation:
        raise PermissionError("the R2-only mode is for validation")
    run = Path(a.run) / a.set.replace(":", "-")
    run.mkdir(parents=True, exist_ok=True)
    method = hd.Method(a.method, a.data_root)
    full = f5.load(a.set, heldout=False)
    w3 = hd.f3.w3_flags(full)
    for m in f5.HELD_OUT:
        for s in hd.f3.R2_SEEDS:
            hd.shard(
                run,
                f"r2-{m}-{s}",
                lambda m=m, s=s: {
                    "cases": hd.r1_record(full, w3, method, [("r2", m, s)])
                },
            )
    print(json.dumps({"set": a.set, "r2": True}))


if __name__ == "__main__":
    main()
