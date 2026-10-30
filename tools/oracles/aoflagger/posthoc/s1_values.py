"""A-FLAG post-hoc: stage-level S1 variants (research/a-flag-aoflagger.md).

Runs in the Tricolour 0.2.1 venv. Re-chains every sum_threshold step with
Tricolour's `_sum_threshold` replaced by the validated bridge kernel in two
settings, to split the stage-level S0 -> S1 gap:

- `values`: AOFlagger's kernel (lengths 1-256, rho 4/3, exclusion, the 3.5.0
  xRight defect) with Tricolour's input handling: input-flagged samples stay
  in the sums with Tricolour's values (only the slice padding is missing);
- `tric_missing`: Tricolour's own kernel (its windows, rho, clamping) with the
  input flags of the pass removed as missing (compressed), i.e. only the
  input-handling rung.

Usage (Tricolour 0.2.1 venv, from the repository root):
    python -I tools/oracles/aoflagger/posthoc/s1_values.py
        outputs/core-d-oracle-20261029-01/run
        outputs/caracal-strategy-inputs-8f7bb363 outputs/<fresh>
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

W = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(W / "tools/oracles/aoflagger"))
import st_bridge  # noqa: E402
import tricolour_dump as td  # noqa: E402


def kernel_values(data, flags, axis, windows, outlier_nsigma, rho, chunks=None):
    if axis == 0:
        thr = td.thresholds(data, flags, 0, outlier_nsigma, None)
        values, valid, thr = st_bridge.time_columns(data, thr)
        z = st_bridge.normalise(values, thr)
        return st_bridge.aoflagger_columns(z, ~valid, vertical=False).T.copy()
    thr = td.thresholds(data, flags, 1, outlier_nsigma, chunks)
    values, valid, thr, index = st_bridge.chunk_columns(data, thr, chunks, int(np.max(windows)))
    z = st_bridge.normalise(values, thr)
    out = st_bridge.aoflagger_columns(z, ~valid, vertical=True)
    return st_bridge.chunk_flags_back(out, index, data.shape[0], data.shape[1])


def kernel_tric_missing(data, flags, axis, windows, outlier_nsigma, rho, chunks=None):
    """Tricolour's clamping kernel over the concatenated non-flagged samples."""
    if axis == 0:
        thr = td.thresholds(data, flags, 0, outlier_nsigma, None)
        values, valid, thr = st_bridge.time_columns(data, thr)
        miss = np.asarray(flags, bool).T
    else:
        thr = td.thresholds(data, flags, 1, outlier_nsigma, chunks)
        values, valid, thr, index = st_bridge.chunk_columns(data, thr, chunks, int(np.max(windows)))
        miss = ~valid | st_bridge.chunk_missing(flags, index, values.shape[1])
    ncol, n = values.shape
    keep = ~miss
    order = np.argsort(miss, axis=1, kind="stable")
    comp = np.take_along_axis(values, order, axis=1)
    cvalid = np.arange(n)[None, :] < keep.sum(axis=1)[:, None]
    comp = np.where(cvalid, comp, np.float32(0)).astype(np.float32)
    cflags = st_bridge.tricolour_columns(comp, cvalid, thr, windows, rho)
    out = np.zeros((ncol, n), bool)
    np.put_along_axis(out, order, cflags & cvalid, axis=1)
    out &= keep
    if axis == 0:
        return out.T.copy()
    return st_bridge.chunk_flags_back(out, index, data.shape[0], data.shape[1])


def main():
    oracle, strategy_dir, out = (Path(a) for a in sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=False)
    receipt = {"script": "s1_values.py (post-hoc)", "timings": {}}
    for label, strategy_name in td.CONTROLS:
        tic = time.perf_counter()
        vis = np.load(oracle / label / "intensity.npz")["intensity"]
        stages = np.load(oracle / label / "stages.npz")
        names = list(stages.files)
        strategies = yaml.full_load((strategy_dir / strategy_name).read_text())["strategies"]
        res = {}
        for k, step in enumerate(strategies):
            if step["task"] != "sum_threshold":
                continue
            before = stages[names[k - 1]]
            for name, kern in (("values", kernel_values), ("tric_missing", kernel_tric_missing)):
                new, _ = td.rechain(vis, before.copy(), step.get("kwargs", {}), None, kern)
                res[f"{name}_s{k:02d}"] = np.logical_or(new, before)
        np.savez_compressed(out / f"s1v-{label}.npz", **res)
        receipt["timings"][label] = time.perf_counter() - tic
        print(label, f"{receipt['timings'][label]:.1f} s", flush=True)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")


if __name__ == "__main__":
    main()
