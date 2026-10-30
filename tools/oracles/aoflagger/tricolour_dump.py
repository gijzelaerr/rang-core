"""Tricolour 0.2.1 per-pass dump for A-FLAG (research/a-flag-aoflagger.md, 2.3).

Usage (Tricolour 0.2.1 venv, RV1's `venv-tric021` resolution):
    python tools/oracles/aoflagger/tricolour_dump.py <oracle-run> <strategy-dir> <fresh-out>

For every control and every `sum_threshold` step it re-chains the unmodified
jitted Tricolour functions exactly as `tricolour.flagging.sum_threshold_flagger`
and `_get_baseline_flags` do, starting from the oracle's window flags before
the step, and

- checks (the gate) that the re-chain reproduces the oracle's window flags
  after the step bitwise;
- saves, per baseline and major iteration, the inputs and raw outputs of the
  three `_sum_threshold` passes (spectrum, time, frequency) and the
  thresholds `_sum_threshold1d` derives from them (`_median_abs_axis0` per
  column or chunk, times `outlier_nsigma * MAD_NORMAL`, inf where NaN);
- runs the stage-level bridge S1: the same chain with the three
  `_sum_threshold` calls replaced by AOFlagger's masked SumThreshold
  semantics (`st_bridge.aoflagger_columns`, input flags as missing, Tricolour's
  thresholds as absolute chi_1).

Nothing from the oracle run is modified.
"""

import inspect
import json
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np
import tricolour
import yaml
from tricolour import flagging as tf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import st_bridge

CONTROLS = (
    ("strategy-00-operational", "mk_rfi_flagging_calibrator_fields_firstpass.yaml"),
    ("strategy-00-holdout_masked", "mk_rfi_flagging_calibrator_fields_firstpass.yaml"),
    ("strategy-01-operational", "calibrator_mild_flagging.yaml"),
    ("strategy-01-holdout_masked", "calibrator_mild_flagging.yaml"),
)
PASSES = ("spec", "time", "freq")


def file_sha256(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def thresholds(data, flags, axis, outlier_nsigma, chunks):
    """The per-column (axis 0) or per-(row, chunk) (axis 1) chi_1 of
    `_sum_threshold1d`, float32 as Tricolour stores it."""
    scale = outlier_nsigma * tf.MAD_NORMAL
    if axis == 0:
        thr = tf._median_abs_axis0(data, flags)[0]
        out = np.empty_like(thr)
        for j in range(thr.size):
            out[j] = (
                np.inf if np.isnan(thr[j]) else np.float32(np.float64(thr[j]) * scale)
            )
        return out
    nrow = data.shape[0]
    out = np.empty((nrow, len(chunks) - 1), np.float32)
    for i in range(nrow):
        for c in range(len(chunks) - 1):
            v = tf._median_abs_axis0(
                data[i, chunks[c] : chunks[c + 1]], flags[i, chunks[c] : chunks[c + 1]]
            )[0]
            out[i, c] = np.inf if np.isnan(v) else np.float32(np.float64(v) * scale)
    return out


def ao_kernel(data, flags, axis, windows, outlier_nsigma, rho, chunks=None):
    """AOFlagger 3.5 masked SumThreshold (K3 semantics) in place of
    `_sum_threshold`, with Tricolour's thresholds as absolute chi_1."""
    if axis == 0:
        thr = thresholds(data, flags, 0, outlier_nsigma, None)
        values, valid, thr = st_bridge.time_columns(data, thr)
        missing = np.ascontiguousarray(np.asarray(flags, bool).T)
        z = st_bridge.normalise(values, thr)
        return st_bridge.aoflagger_columns(z, missing, vertical=False).T.copy()
    thr = thresholds(data, flags, 1, outlier_nsigma, chunks)
    values, valid, thr, index = st_bridge.chunk_columns(
        data, thr, chunks, int(np.max(windows))
    )
    missing = ~valid | st_bridge.chunk_missing(flags, index, values.shape[1])
    z = st_bridge.normalise(values, thr)
    flags_out = st_bridge.aoflagger_columns(z, missing, vertical=True)
    return st_bridge.chunk_flags_back(flags_out, index, data.shape[0], data.shape[1])


def baseline_flags(data, flags, out_flags, p, record=None, kernel=None):
    """`_get_baseline_flags` as Python over the jitted pieces."""
    st = kernel or tf._sum_threshold
    spec_data, spec_flags = tf._time_median(data, flags)
    spec_background = tf._get_background2d(
        spec_data,
        spec_flags,
        p["background_iterations"],
        np.array((0.0, p["spike_width_freq"])),
        p["background_reject"],
        p["freq_chunk_ends"],
    )
    spec_data -= spec_background
    spec_in = spec_flags.copy()
    spec_flags = st(
        spec_data,
        spec_flags,
        1,
        p["windows_freq"],
        p["outlier_nsigma"],
        p["rho"],
        p["freq_chunk_ends"],
    )
    if record is not None:
        record["spec"] = (spec_data.copy(), spec_in, spec_flags.copy())
    flags |= spec_flags
    background = tf._get_background2d(
        data,
        flags,
        p["background_iterations"],
        np.array((p["spike_width_time"], p["spike_width_freq"])),
        p["background_reject"],
        p["freq_chunk_ends"],
    )
    data -= background
    time_in = flags.copy()
    if kernel is None:
        time_flags = st(
            data, flags, 0, p["windows_time"], p["outlier_nsigma"], p["rho"]
        )
    else:
        time_flags = st(
            data, flags, 0, p["windows_time"], p["outlier_nsigma"], p["rho"], None
        )
    flags |= time_flags
    freq_in = flags.copy()
    freq_flags = st(
        data,
        flags,
        1,
        p["windows_freq"],
        p["outlier_nsigma"],
        p["rho"],
        p["freq_chunk_ends"],
    )
    if record is not None:
        record["time"] = (data.copy(), time_in, time_flags.copy())
        record["freq"] = (data.copy(), freq_in, freq_flags.copy())
    tf._combine_flags(spec_flags, time_flags, freq_flags, p["time_extend"], flags)
    tf._unaverage_freq(
        flags,
        p["freq_extend"],
        p["average_freq"],
        p["flag_all_time_frac"],
        p["flag_all_freq_frac"],
        out_flags,
    )


def rechain(vis, flags, kwargs, records=None, kernel=None):
    """`sum_threshold_flagger` with the per-baseline step in Python."""
    defaults = {
        k: v.default
        for k, v in inspect.signature(tf.sum_threshold_flagger).parameters.items()
        if v.default is not inspect.Parameter.empty
    }
    q = dict(defaults)
    q.update(kwargs)
    nbl, ncorr, ntime, nchan = vis.shape
    vis = vis.reshape(nbl * ncorr, ntime, nchan)
    flags = flags.reshape(nbl * ncorr, ntime, nchan)
    windows_freq = np.asarray(q["windows_freq"], dtype=np.float32)
    windows_freq = np.ceil(windows_freq) / q["average_freq"]
    windows_freq = np.unique(windows_freq.astype(np.int_))
    p = {
        "outlier_nsigma": q["outlier_nsigma"],
        "background_reject": q["background_reject"],
        "background_iterations": q["background_iterations"],
        "spike_width_time": q["spike_width_time"],
        "spike_width_freq": q["spike_width_freq"],
        "time_extend": tf._as_min_dtype(q["time_extend"]),
        "freq_extend": tf._as_min_dtype(q["freq_extend"]),
        "average_freq": tf._as_min_dtype(q["average_freq"]),
        "flag_all_time_frac": q["flag_all_time_frac"],
        "flag_all_freq_frac": q["flag_all_freq_frac"],
        "rho": q["rho"],
    }
    averaged_channels = (int(nchan) + int(p["average_freq"]) - 1) // int(
        p["average_freq"]
    )
    p["freq_chunk_ends"] = np.linspace(
        0, averaged_channels, q["freq_chunks"] + 1
    ).astype(np.int_)
    p["windows_time"] = np.array([w for w in q["windows_time"] if w <= ntime], np.int_)
    p["windows_freq"] = np.array(
        [w for w in windows_freq if w <= averaged_channels], np.int_
    )
    out_flags = np.empty_like(flags)
    iter_flags = flags.copy()
    for i in range(q["num_major_iterations"]):
        data, aflags = tf._average_freq(vis, iter_flags, p["average_freq"])
        tmp = np.empty((nbl * ncorr, ntime, nchan), np.bool_)
        for cp in range(nbl * ncorr):
            record = {} if records is not None else None
            baseline_flags(data[cp], aflags[cp], tmp[cp], p, record, kernel)
            if records is not None:
                records.append((i, cp, record))
        out_flags[...] = tmp | np.isnan(vis)
        iter_flags = np.logical_or(iter_flags, out_flags)
    meta = {
        "windows_time": p["windows_time"].tolist(),
        "windows_freq": p["windows_freq"].tolist(),
        "freq_chunk_ends": p["freq_chunk_ends"].tolist(),
        "rho": float(p["rho"]),
        "outlier_nsigma": float(p["outlier_nsigma"]),
        "num_major_iterations": int(q["num_major_iterations"]),
        "time_extend": int(p["time_extend"]),
        "freq_extend": int(p["freq_extend"]),
        "flag_all_time_frac": float(p["flag_all_time_frac"]),
        "flag_all_freq_frac": float(p["flag_all_freq_frac"]),
    }
    return out_flags.reshape(nbl, ncorr, ntime, nchan), meta


def main():
    oracle, strategy_dir, out = (Path(a) for a in sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=False)
    receipt = {
        "oracle_run": str(oracle),
        "tricolour_version": tricolour.__version__,
        "numpy_version": np.__version__,
        "numba_version": __import__("numba").__version__,
        "flagging_py_sha256": file_sha256(tf.__file__),
        "st_bridge_sha256": file_sha256(st_bridge.__file__),
        "inputs": {},
        "controls": {},
        "timings": {},
    }
    total = time.perf_counter()
    for label, strategy_name in CONTROLS:
        tic = time.perf_counter()
        cdir = oracle / label
        receipt["inputs"][label] = {
            n: file_sha256(cdir / n) for n in ("intensity.npz", "stages.npz")
        }
        vis = np.load(cdir / "intensity.npz")["intensity"]
        stages = np.load(cdir / "stages.npz")
        names = list(stages.files)
        strategies = yaml.full_load((strategy_dir / strategy_name).read_text())[
            "strategies"
        ]
        dump, s1, info = {}, {}, {}
        for k, strategy in enumerate(strategies):
            if strategy["task"] != "sum_threshold":
                continue
            before = stages[names[k - 1]]
            records = []
            t0 = time.perf_counter()
            new, meta = rechain(vis, before.copy(), strategy.get("kwargs", {}), records)
            seconds = time.perf_counter() - t0
            got = np.logical_or(new, before)
            diff = int(np.count_nonzero(got != stages[names[k]]))
            t0 = time.perf_counter()
            new_s1, _ = rechain(
                vis, before.copy(), strategy.get("kwargs", {}), None, ao_kernel
            )
            s1_seconds = time.perf_counter() - t0
            s1[f"s{k:02d}"] = np.logical_or(new_s1, before)
            niter = meta["num_major_iterations"]
            nbl = vis.shape[0]
            for pas in PASSES:
                d0 = records[0][2][pas][0]
                data = np.zeros((nbl, niter) + d0.shape, np.float32)
                fin = np.zeros((nbl, niter) + d0.shape, bool)
                fout = np.zeros((nbl, niter) + d0.shape, bool)
                thr_shape = (
                    (d0.shape[1],)
                    if pas == "time"
                    else (d0.shape[0], len(meta["freq_chunk_ends"]) - 1)
                )
                thr = np.zeros((nbl, niter) + thr_shape, np.float32)
                for i, cp, rec in records:
                    d, fi, fo = rec[pas]
                    data[cp, i], fin[cp, i], fout[cp, i] = d, fi, fo
                    axis = 0 if pas == "time" else 1
                    chunks = (
                        None if pas == "time" else np.asarray(meta["freq_chunk_ends"])
                    )
                    thr[cp, i] = thresholds(d, fi, axis, meta["outlier_nsigma"], chunks)
                dump[f"s{k:02d}_{pas}_data"] = data
                dump[f"s{k:02d}_{pas}_flags"] = fin
                dump[f"s{k:02d}_{pas}_out"] = fout
                dump[f"s{k:02d}_{pas}_thr"] = thr
            info[f"s{k:02d}"] = {
                "name": names[k],
                "meta": meta,
                "gate_differences": diff,
                "rechain_seconds": seconds,
                "s1_seconds": s1_seconds,
                "s1_fraction": float(s1[f"s{k:02d}"].mean()),
            }
            print(
                label,
                names[k],
                "gate differences",
                diff,
                f"{seconds:.1f} s",
                flush=True,
            )
        np.savez_compressed(out / f"dump-{label}.npz", **dump)
        np.savez_compressed(out / f"s1-{label}.npz", **s1)
        receipt["controls"][label] = info
        receipt["timings"][label] = time.perf_counter() - tic
    receipt["timings"]["total"] = time.perf_counter() - total
    receipt["gate_pass"] = all(
        v["gate_differences"] == 0
        for c in receipt["controls"].values()
        for v in c.values()
    )
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print("gate_pass", receipt["gate_pass"], f"{receipt['timings']['total']:.1f} s")


if __name__ == "__main__":
    main()
