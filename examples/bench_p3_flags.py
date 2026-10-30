"""Timings and identity hashes of the Tricolour port (research/p3-sumthreshold.md).

Usage:
    python examples/bench_p3_flags.py run outputs/<fresh> [--repeats 3] [--per-step]
        [--inputs d,k]
    python examples/bench_p3_flags.py compare <reference-run> <run> [<run> ...]

`run` times `rangtoy.core_flag.flag_rows` on the archived inputs of task D
(the four CARACAL controls exported by the oracle step) and task K (the
fetched LUNO chunk-0 slice, both CARACAL strategies), with the thread count
taken from `RAYON_NUM_THREADS` in the environment. Per call it records wall
time, the core seconds, process CPU seconds (all threads), peak RSS and the
load average, and SHA256 of the final flags and of every per-step window.
For task K it also compares the training additions with the archived
`additions_sha256` of `research/results/core-k-luno-campaign.json`.
`--per-step` adds a single-step replay: each step is run alone with the
previous step's window flags as input, so its time is that of the step in
the chain plus the packing overhead, measured by a `flag_autos` call.
`compare` checks that every hash of each run equals the reference run's.
"""

import argparse
import json
import os
import resource
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np
from rangtoy import core, core_campaign, core_fetch, core_flag

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "outputs/core-d-oracle-20261029-01/run"
FETCHED = ROOT / "outputs/core-k-20261030-01/fetch"
K_ARCHIVE = ROOT / "research/results/core-k-luno-campaign.json"
D_CONTROLS = (
    ("strategy-00-operational", "mk_rfi_flagging_calibrator_fields_firstpass.yaml"),
    ("strategy-00-holdout_masked", "mk_rfi_flagging_calibrator_fields_firstpass.yaml"),
    ("strategy-01-operational", "calibrator_mild_flagging.yaml"),
    ("strategy-01-holdout_masked", "calibrator_mild_flagging.yaml"),
)


def cpu():
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def load():
    return float(open("/proc/loadavg").read().split()[0])


def digest(array):
    return sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def call(inputs, strategies, masks, want_stages=True):
    w, c, l0 = time.perf_counter(), cpu(), load()
    result = core_flag.flag_rows(
        *inputs, strategies, masks=masks, want_intensity=False, want_stages=want_stages
    )
    timing = {
        "wall": time.perf_counter() - w,
        "core_seconds": result["seconds"],
        "cpu": cpu() - c,
        "max_rss_mb": rss_mb(),
        "load": [l0, load()],
    }
    return result, timing


def window_to_rows(window, inputs, ubl, time_inv):
    """Row flags `(row, chan, corr)` carrying a `(bl, 1, time, chan)` window."""
    antenna1, antenna2 = inputs[2], inputs[3]
    lookup = {(int(a), int(b)): i for i, (a, b) in enumerate(ubl)}
    bl = np.array([lookup[(int(a), int(b))] for a, b in zip(antenna1, antenna2)])
    rows = window[bl, 0, time_inv, :]
    return np.ascontiguousarray(
        np.broadcast_to(rows[..., None], inputs[0].shape), dtype=bool
    )


def per_step(inputs, strategies, masks, stages, ubl, time_inv, repeats):
    """Single-step replay: step k alone with the window after step k-1."""
    overhead = []
    for _ in range(repeats):
        _, t = call(inputs, [{"task": "flag_autos"}], masks, want_stages=False)
        overhead.append(t["core_seconds"])
    names = list(stages)
    steps = []
    for k, step in enumerate(strategies):
        if k == 0:
            flags = inputs[1]
        else:
            flags = window_to_rows(stages[names[k - 1]], inputs, ubl, time_inv)
        step_inputs = (inputs[0], flags, *inputs[2:])
        times = []
        for _ in range(repeats):
            _, t = call(step_inputs, [step], masks, want_stages=False)
            times.append(t)
        steps.append(
            {
                "step": names[k],
                "core_seconds": [t["core_seconds"] for t in times],
                "cpu": [t["cpu"] for t in times],
            }
        )
    return {"packing_overhead_core_seconds": overhead, "steps": steps}


def d_inputs():
    for label, strategy in D_CONTROLS:
        arrays = np.load(ORACLE / label / "arrays.npz")
        inputs = tuple(
            arrays[k]
            for k in (
                "DATA",
                "FLAG",
                "ANTENNA1",
                "ANTENNA2",
                "TIME",
                "antenna_position",
                "chan_freq",
                "chan_width",
                "corr_type",
            )
        )
        oracle = np.load(ORACLE / label / "stages.npz")
        yield f"d/{label}", strategy, inputs, {"oracle_stages": oracle}


def k_inputs():
    arrays, _ = core_fetch.decode_slice(FETCHED)
    rows = np.asarray(json.loads((FETCHED / "result.json").read_text())["rows"])
    extra = core_campaign.decode_extra(FETCHED, rows)
    state = core_campaign.build_state(arrays, extra)
    archived = json.loads(K_ARCHIVE.read_text())["arms"]
    inputs = (
        state["data"],
        state["original_flags"],
        state["antenna1"],
        state["antenna2"],
        state["times"],
        extra["antenna_position"],
        state["frequencies"],
        extra["chan_width"],
        extra["corr_type"],
    )
    for label, strategy in core_campaign.STRATEGIES.items():
        yield (
            f"k/{label}",
            strategy,
            inputs,
            {"train": state["train"], "archived": archived[label]["additions_sha256"]},
        )


def replicated_inputs(copies):
    """Probe: the K slice with its baselines copied onto new antenna indices.

    Copy `k` uses antennas `a + k * nant` whose positions repeat the
    originals, so each copy must carry the flags of the original rows.
    """
    for name, strategy, inputs, _ in k_inputs():
        data, flags, a1, a2, times, positions = inputs[:6]
        nant = positions.shape[0]
        replicated = (
            np.concatenate([data] * copies),
            np.concatenate([flags] * copies),
            np.concatenate([a1 + k * nant for k in range(copies)]).astype(np.int32),
            np.concatenate([a2 + k * nant for k in range(copies)]).astype(np.int32),
            np.tile(times, copies),
            np.tile(positions, (copies, 1)),
            *inputs[6:],
        )
        yield (
            f"probe-x{copies}/{name.split('/')[1]}",
            strategy,
            replicated,
            {"copies": copies, "rows": data.shape[0]},
        )


def run(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    report = {
        "threads_env": os.environ.get("RAYON_NUM_THREADS"),
        "backend": core.backend_name(),
        "core_library": str(core.library_path()),
        "core_library_sha256": sha256(core.library_path().read_bytes()).hexdigest(),
        "extension": getattr(core.extension(), "__file__", None),
        "extension_sha256": sha256(
            Path(core.extension().__file__).read_bytes()
        ).hexdigest()
        if core.extension() is not None
        else None,
        "repeats": args.repeats,
        "load_start": load(),
        "inputs": {},
    }
    masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    sources = {
        "d": d_inputs,
        "k": k_inputs,
        "probe": lambda: replicated_inputs(args.copies),
    }
    for source in args.inputs.split(","):
        for name, strategy_name, inputs, extra in sources[source]():
            text = (core_campaign.STRATEGY_DIR / strategy_name).read_text()
            strategies = core_flag.parse_strategy(text)
            timings = []
            hashes = None
            for _ in range(args.repeats):
                result, t = call(inputs, strategies, masks)
                h = {"flags": digest(result["flags"])}
                h.update({k: digest(v) for k, v in result["stages"].items()})
                if hashes is None:
                    hashes = h
                elif h != hashes:
                    hashes["repeat_mismatch"] = True
                timings.append(t)
            entry = {
                "strategy": strategy_name,
                "strategy_sha256": sha256(text.encode()).hexdigest(),
                "shape": list(inputs[0].shape),
                "baselines": int(result["ubl"].shape[0]),
                "times": int(result["time_inv"].max()) + 1,
                "timings": timings,
                "hashes": hashes,
            }
            if "oracle_stages" in extra:
                oracle = extra["oracle_stages"]
                entry["stage_differences_vs_oracle"] = {
                    k: int(np.count_nonzero(result["stages"][k] != oracle[k]))
                    for k in oracle.files
                }
            if "train" in extra:
                additions = extra["train"] & result["flags"].any(axis=-1)
                entry["additions_sha256"] = core_campaign.array_sha256(additions)
                entry["additions_count"] = int(additions.sum())
                entry["additions_equal_archive"] = (
                    entry["additions_sha256"] == extra["archived"]
                )
            if "copies" in extra:
                rows = extra["rows"]
                copy_hashes = [
                    digest(result["flags"][k * rows : (k + 1) * rows])
                    for k in range(extra["copies"])
                ]
                entry["copy_flags_sha256"] = copy_hashes[0]
                entry["copies_identical"] = len(set(copy_hashes)) == 1
            if args.per_step:
                entry["per_step"] = per_step(
                    inputs,
                    strategies,
                    masks,
                    result["stages"],
                    result["ubl"],
                    result["time_inv"],
                    args.repeats,
                )
            report["inputs"][name] = entry
            best = min(t["core_seconds"] for t in timings)
            cpu_best = min(t["cpu"] for t in timings)
            print(f"{name}: best {best:.3f} s, cpu {cpu_best:.3f} s", flush=True)
    report["load_end"] = load()
    report["wall"] = time.perf_counter() - started
    report["max_rss_mb"] = rss_mb()
    (out / "bench.json").write_text(json.dumps(report, indent=1) + "\n")


def compare(args):
    reference = json.loads((Path(args.reference) / "bench.json").read_text())
    ok = True
    for other in args.runs:
        report = json.loads((Path(other) / "bench.json").read_text())
        for name, entry in reference["inputs"].items():
            if name not in report["inputs"]:
                continue
            same = report["inputs"][name]["hashes"] == entry["hashes"]
            ok &= same
            print(f"{other} {name}: {'identical' if same else 'DIFFERENT'}")
    sys.exit(0 if ok else 1)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("run")
    p.add_argument("out")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--per-step", action="store_true")
    p.add_argument("--inputs", default="d,k", help="comma list of d, k, probe")
    p.add_argument("--copies", type=int, default=16, help="probe replication")
    p = sub.add_parser("compare")
    p.add_argument("reference")
    p.add_argument("runs", nargs="+")
    args = parser.parse_args()
    run(args) if args.mode == "run" else compare(args)


if __name__ == "__main__":
    main()
