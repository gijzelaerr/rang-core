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
import os
import sys
from pathlib import Path

import numpy as np
from rang import f3flag as f3
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


def load_eso_set(spec, heldout):
    """ESO137 for F6/F7. F6's held-out target chunks are F4's reserved
    chunks 1, 3, 5, 7, 9, 15, 17 (F5 read 11-13), which `f4flag.load_eso`
    refuses: they are read only by a held-out scoring run with
    `--heldout-read`. Every other chunk keeps F4's guard."""
    from rang import f4flag as f4

    chunk = int(spec.split(":")[1])
    if chunk in f4.ESO_RESERVED:
        if not (heldout and HELDOUT_READ):
            raise PermissionError(f"{spec} is held out; pass --heldout-read at scoring")
        return f3.read_eso(chunk)
    return None


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


def calibrate(kind, logit, eligible, groups):
    """Calibrated score of `logit` (cells, chan) given eligibility and a row -> group map
    (baseline for K1/K2, a single group for K3)."""
    out = np.full(logit.shape, -np.inf, np.float32)
    order = np.argsort(groups, kind="stable")
    bounds = np.flatnonzero(np.diff(groups[order])) + 1
    for rows in np.split(order, bounds):
        v = logit[rows]
        e = eligible[rows]
        if not e.any():
            continue
        m = np.median(v[e])
        if kind == "K2":
            s = 1.4826 * np.median(np.abs(v[e] - m))
            out[rows] = (v - m) / max(s, 1e-6)
        else:
            out[rows] = v - m
    return out


def calibrated_arms(hd):
    """Amendment 2d-3: when the method file names a calibration (K1-K3), N5 thresholds the
    calibrated score instead of the raw logit; the logits returned (G-perm) stay raw."""
    raw = hd.Method.arms

    def arms(self, scan, w3, data=None):
        kind = self.rec.get("calibration")
        if not kind:
            return raw(self, scan, w3, data)
        logit = f5.rust_logits(scan, w3, self.w, self.level, self.degree, data)
        el = ~w3
        bl = f3.index(scan)["bl"].astype(np.int64)
        groups = np.zeros(len(bl), np.int64) if kind == "K3" else bl
        cal = calibrate(kind, logit, el, groups)
        out = {"N": w3, "N5": w3 | (cal > self.tau)}
        out["method"] = out["N5"]
        if self.n4 is not None:
            out["N4"] = hd.f4.n4_flags(scan, w3, self.n4, hd.N4_TAU, data)[0]
        return out, logit

    hd.Method.arms = arms


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
    calibrated_arms(hd)
    f5_load, f5_a = f5.load, f5.a_flags

    def load(spec, heldout=False):
        if spec.startswith("sarao:"):
            return load_sarao_set(spec, heldout)
        if spec.startswith("eso:"):
            scan = load_eso_set(spec, heldout)
            if scan is not None:
                return scan
        return f5_load(spec, heldout=heldout)

    def a_flags(scan, w3, workdir, data=None):
        cache = os.environ.get("F6_A_FROM")  # reuse the set's A from an earlier run
        if cache and data is None:
            p = Path(cache) / Path(workdir).parent.parent.name / "A.npy"
            if p.exists():
                return np.load(p), {"source": f"cached {p}"}
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
