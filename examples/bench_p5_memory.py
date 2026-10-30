"""Per-stage memory of the LUNO campaign drivers (research/p5-memory.md).

Wraps the stage functions of `rangtoy.core_campaign_array` (and the core
calls they make) so that each call records its wall time, the resident set
at entry and exit and its own high-water mark. The high-water mark is exact,
Rust allocations included: the kernel's `VmHWM` is reset through
`/proc/self/clear_refs` at every stage entry and read at exit, and a parent
stage keeps the largest peak of its children. Optional `tracemalloc` adds
the Python-heap (NumPy) peak of each stage.

Modes:

- `campaign`: `core_campaign_array.run` on a station subset (`--stations
  0,1,2,3 --k-image --groups 1` is the precondition's four-station replay)
  or on the whole array (`--stations all`);
- `precondition`: `core_campaign_array.precondition`;
- `probe`: the array-scale stage probe (decode, split, the `original` solve
  with features, the first-pass Tricolour port and its solve, one image).

Writes `memory.json` into `--out` (a fresh directory) beside the run's own
outputs. Usage from the repository root:

    .venv/bin/python examples/bench_p5_memory.py campaign \
        --out outputs/p5-memory-20261030-01/k4 --stations 0,1,2,3 --k-image --groups 1
"""

import argparse
import functools
import json
import os
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
from rangtoy import (
    core,
    core_campaign,
    core_campaign_array,
    core_fetch,
    core_flag,
    core_grid,
    core_weights,
)

STATUS = Path("/proc/self/status")
CLEAR_REFS = Path("/proc/self/clear_refs")


def status_kb(*keys):
    values = {}
    for line in STATUS.read_text().splitlines():
        name, _, rest = line.partition(":")
        if name in keys:
            values[name] = int(rest.split()[0])
    return [values.get(k) for k in keys]


def reset_hwm():
    try:
        CLEAR_REFS.write_text("5")
        return True
    except OSError:
        return False


class Recorder:
    """A stack of open stages with exact high-water marks."""

    def __init__(self, use_tracemalloc=False):
        self.stack = []
        self.records = []
        self.t0 = time.perf_counter()
        self.use_tracemalloc = use_tracemalloc
        self.can_reset = reset_hwm()

    def enter(self, name):
        hwm, rss = status_kb("VmHWM", "VmRSS")
        if self.stack:
            parent = self.stack[-1]
            parent["peak_kb"] = max(parent["peak_kb"], hwm)
            if self.use_tracemalloc:
                parent["py_peak"] = max(
                    parent["py_peak"], tracemalloc.get_traced_memory()[1]
                )
        reset_hwm()
        if self.use_tracemalloc:
            tracemalloc.reset_peak()
        frame = {
            "name": name,
            "depth": len(self.stack),
            "start": time.perf_counter() - self.t0,
            "rss_start_kb": rss,
            "peak_kb": rss,
            "py_start": tracemalloc.get_traced_memory()[0]
            if self.use_tracemalloc
            else None,
            "py_peak": 0,
        }
        self.stack.append(frame)

    def leave(self):
        frame = self.stack.pop()
        hwm, rss = status_kb("VmHWM", "VmRSS")
        frame["peak_kb"] = max(frame["peak_kb"], hwm)
        frame["rss_end_kb"] = rss
        frame["seconds"] = time.perf_counter() - self.t0 - frame["start"]
        if self.use_tracemalloc:
            current, peak = tracemalloc.get_traced_memory()
            frame["py_peak"] = max(frame["py_peak"], peak)
            frame["py_end"] = current
        if self.stack:
            parent = self.stack[-1]
            parent["peak_kb"] = max(parent["peak_kb"], frame["peak_kb"])
            if self.use_tracemalloc:
                parent["py_peak"] = max(parent["py_peak"], frame["py_peak"])
        self.records.append(frame)


def wrap(recorder, owner, attribute, label=None):
    original = getattr(owner, attribute, None)
    if original is None or getattr(original, "_p5_wrapped", False):
        return
    name = label or attribute

    @functools.wraps(original)
    def wrapped(*args, **kwargs):
        recorder.enter(name)
        try:
            return original(*args, **kwargs)
        finally:
            recorder.leave()

    wrapped._p5_wrapped = True
    setattr(owner, attribute, wrapped)


STAGE_FUNCTIONS = (
    (core_campaign_array, "verify_inputs"),
    (core_campaign_array, "decode_inputs"),
    (core_campaign_array, "split_holdout_lean"),
    (core_campaign_array, "eligible_cells"),
    (core_campaign_array, "fused_candidates"),
    (core_campaign_array, "correct_stokes_i"),
    (core_campaign_array, "final_flags_summary"),
    (core_campaign_array, "model_stokes_mean"),
    (core_campaign_array, "decode_extra"),
    (core_campaign_array, "build_state"),
    (core_campaign_array, "solve_arm"),
    (core_campaign_array, "residual_amplitude"),
    (core_campaign_array, "baseline_scores"),
    (core_campaign_array, "solve_features"),
    (core_campaign_array, "tricolour_arm"),
    (core_campaign_array, "tv_loop"),
    (core_campaign_array, "image_arm"),
    (core_campaign_array, "corrected_stokes"),
    (core_campaign_array, "grouped_invert"),
    (core_campaign_array, "matched_calls"),
    (core_campaign_array, "restricted_losses"),
    (core_campaign, "precondition"),
    (core_flag, "flag_rows"),
    (core_weights, "imaging_weights"),
    (core_grid, "invert"),
    (core, "solve_complex"),
    (core, "fused_pass"),
)


def instrument(recorder):
    for owner, attribute in STAGE_FUNCTIONS:
        label = f"{owner.__name__.split('.')[-1]}.{attribute}"
        wrap(recorder, owner, attribute, label)


def summarise(records, cells):
    """Per stage name: calls, wall, the largest peak and its per-cell value."""
    by_name = {}
    for r in records:
        s = by_name.setdefault(
            r["name"],
            {"calls": 0, "seconds": 0.0, "peak_mb": 0.0, "peak_above_entry_mb": 0.0},
        )
        s["calls"] += 1
        s["seconds"] += r["seconds"]
        s["peak_mb"] = max(s["peak_mb"], r["peak_kb"] / 1024)
        s["peak_above_entry_mb"] = max(
            s["peak_above_entry_mb"], (r["peak_kb"] - r["rss_start_kb"]) / 1024
        )
        if r.get("py_peak"):
            s["py_peak_mb"] = max(s.get("py_peak_mb", 0.0), r["py_peak"] / 2**20)
    for s in by_name.values():
        s["peak_bytes_per_cell"] = s["peak_mb"] * 2**20 / cells if cells else None
        s["transient_bytes_per_cell"] = (
            s["peak_above_entry_mb"] * 2**20 / cells if cells else None
        )
    return by_name


def probe(out_dir, groups):
    """Array-scale stages once each, in the campaign's order."""
    cad = core_campaign_array
    arrays, rows, _ = cad.decode_inputs(None)
    extra = cad.decode_extra(rows)
    nant = len(extra["antenna_names"])
    state = cad.build_state(arrays, extra, nant)
    del arrays
    zero = np.zeros_like(state["train"])
    original = cad.solve_arm(state, zero, "original", features=True)
    scale0 = original["metrics"]["scale"]
    additions, summary = cad.tricolour_arm(
        state,
        extra,
        core_campaign.STRATEGY_DIR / core_campaign.STRATEGIES["tricolour-firstpass"],
    )
    firstpass = cad.solve_arm(
        state, additions, "tricolour-firstpass", scale=scale0, features=True
    )
    metrics, _ = cad.image_arm(
        state,
        extra,
        cad.strip(original),
        Path(out_dir) / "images",
        "original",
        dict(cad.ARRAY_IMAGE),
        groups,
        boxes="measure",
    )
    return {
        "shape": list(state["data"].shape),
        "original": {
            "losses": original["metrics"]["losses"],
            "tv": original["metrics"]["tv"],
            "gains_sha256": core_campaign.array_sha256(
                original["diagnostics"]["gains"]
            ),
        },
        "firstpass": {
            "summary_newly_flagged": summary["newly_flagged_cells"],
            "additions_sha256": core_campaign.array_sha256(
                cad.additions_dense(state, firstpass["added"])
                if hasattr(cad, "additions_dense")
                else firstpass["added"]
            ),
            "losses": firstpass["metrics"]["losses"],
        },
        "image_original": {
            k: metrics[k]
            for k in ("peak_jy_per_beam", "residual_rms", "offsource_robust_sigma")
        },
    }


# --- comparing two runs ------------------------------------------------------

# Keys whose values are timings, resource figures or labels: never compared.
TIMING_KEYS = {
    "seconds",
    "wall_seconds",
    "cpu_seconds",
    "cores_busy",
    "max_rss_mb",
    "core_seconds",
    "solve_seconds",
    "feature_seconds",
    "decode_seconds",
    "step_seconds",
    "stages",
    "memory",
    "label",
    "cost_clause",
}
IMAGE_RELATIVE = 1e-6


def _walk(a, b, path, report, tolerant):
    key = path[-1] if path else ""
    if key in TIMING_KEYS:
        return
    here = ".".join(str(p) for p in path)
    # Image-derived fields: the metrics, the PSF-measured boxes, the group
    # check and the residual-RMS calls.
    tolerant = tolerant or key in ("image", "group_comparison", "residual_rms", "boxes")
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                report["missing"].append(f"{here}.{k}")
            else:
                _walk(a[k], b[k], [*path, k], report, tolerant)
        return
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            _walk(x, y, [*path, i], report, tolerant)
        return
    report["compared"] += 1
    if a == b:
        return
    numeric = all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in (a, b)
    )
    if tolerant and str(key).endswith("_sha256"):
        report["image_hashes_differing"].append(here)
        return
    if tolerant and numeric:
        scale = max(abs(a), abs(b))
        rel = abs(a - b) / scale if scale else 0.0
        report["image_max_relative"] = max(report["image_max_relative"], rel)
        if rel <= IMAGE_RELATIVE:
            report["image_within_tolerance"] += 1
            return
    report["different"].append({"path": here, "a": a, "b": b})


def compare_runs(run_a, run_b, dirty_tolerance=8.8e-6, psf_tolerance=2.8e-6):
    """Every non-timing field of two runs' `result.json` and `candidates.json`:
    exact, except image metrics (relative 1e-6, hashes listed) and the FITS
    pixels (task A's tolerances: dirty L-inf over the peak, PSF L-inf)."""
    from rangtoy.core_imaging import read_fits

    run_a, run_b = Path(run_a), Path(run_b)
    report = {
        "a": str(run_a),
        "b": str(run_b),
        "compared": 0,
        "different": [],
        "missing": [],
        "image_hashes_differing": [],
        "image_within_tolerance": 0,
        "image_max_relative": 0.0,
    }
    for name in ("result.json", "candidates.json"):
        _walk(
            json.loads((run_a / name).read_text()),
            json.loads((run_b / name).read_text()),
            [name],
            report,
            False,
        )
    pixels = {}
    for path in sorted((run_a / "images").glob("*.fits")):
        other = run_b / "images" / path.name
        if not other.exists():
            report["missing"].append(f"images/{path.name}")
            continue
        x, _ = read_fits(path)
        y, _ = read_fits(other)
        linf = float(np.abs(x - y).max())
        peak = float(np.abs(x).max())
        psf = path.name.endswith("-psf.fits")
        value = linf if psf else linf / peak
        pixels[path.name] = {
            "identical": bool(np.array_equal(x, y)),
            "linf" if psf else "linf_over_peak": value,
            "pass": value <= (psf_tolerance if psf else dirty_tolerance),
        }
    report["pixels"] = pixels
    report["pass"] = bool(
        not report["different"]
        and not report["missing"]
        and all(p["pass"] for p in pixels.values())
    )
    return report


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "compare":
        if len(argv) != 4:
            raise SystemExit("usage: bench_p5_memory.py compare RUN_A RUN_B OUT.json")
        report = compare_runs(argv[1], argv[2])
        Path(argv[3]).write_text(json.dumps(report, indent=1, default=str) + "\n")
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "pass",
                        "compared",
                        "image_within_tolerance",
                        "image_max_relative",
                    )
                }
                | {
                    "different": report["different"][:20],
                    "missing": report["missing"][:20],
                    "image_hashes_differing": len(report["image_hashes_differing"]),
                    "pixels_failing": [
                        k for k, v in report["pixels"].items() if not v["pass"]
                    ],
                    "pixels_identical": sum(
                        v["identical"] for v in report["pixels"].values()
                    ),
                    "pixels_total": len(report["pixels"]),
                },
                indent=1,
                default=str,
            )
        )
        return
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("campaign", "precondition", "probe"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--stations", default="0,1,2,3")
    parser.add_argument("--k-image", action="store_true")
    parser.add_argument("--groups", type=int, default=None)
    parser.add_argument("--group-check", action="store_true")
    parser.add_argument("--tracemalloc", action="store_true")
    parser.add_argument("--label", default="p5 memory bench")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(f"{out} exists; use a fresh directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.tracemalloc:
        tracemalloc.start()
    core.library()
    if hasattr(core_fetch, "p5_library"):  # prebuilt, so no build is measured
        core_fetch.p5_library()
    recorder = Recorder(args.tracemalloc)
    instrument(recorder)
    stations = (
        None
        if args.stations == "all"
        else [int(s) for s in args.stations.split(",") if s]
    )
    started = time.perf_counter()
    rss0 = status_kb("VmRSS")[0]
    recorder.enter("total")
    if args.mode == "campaign":
        groups = args.groups or (
            1 if args.k_image else core_campaign_array.ARRAY_CHANNEL_GROUPS
        )
        result = core_campaign_array.run(
            out / "run",
            stations=stations,
            image=core_campaign.IMAGE if args.k_image else None,
            groups=groups,
            k_metrics=args.k_image,
            group_check=args.group_check,
            label=args.label,
        )
        shape = result["cells"]["shape"]
        summary = {"result": str(out / "run" / "result.json")}
    elif args.mode == "precondition":
        result = core_campaign_array.precondition(out / "precondition")
        shape = [192, 2048, 4]
        summary = {"all_passed": result["all_passed"], "passed": result["passed"]}
    else:
        out.mkdir(parents=True)
        summary = probe(out, args.groups or core_campaign_array.ARRAY_CHANNEL_GROUPS)
        shape = summary["shape"]
    recorder.leave()
    cells = int(shape[0]) * int(shape[1])
    out.mkdir(parents=True, exist_ok=True)
    total = recorder.records[-1]
    payload = {
        "mode": args.mode,
        "argv": sys.argv,
        "stations": args.stations,
        "cells": cells,
        "shape": shape,
        "wall_seconds": time.perf_counter() - started,
        "rss_before_mb": rss0 / 1024,
        "peak_mb": total["peak_kb"] / 1024,
        "peak_bytes_per_cell": total["peak_kb"] * 1024 / cells,
        "peak_above_start_bytes_per_cell": (total["peak_kb"] - rss0) * 1024 / cells,
        "hwm_reset_supported": recorder.can_reset,
        "rayon_threads": os.environ.get("RAYON_NUM_THREADS"),
        "backend": core.backend_name(),
        "stages": summarise(recorder.records, cells),
        "sequence": [
            {
                k: r.get(k)
                for k in (
                    "name",
                    "depth",
                    "start",
                    "seconds",
                    "rss_start_kb",
                    "rss_end_kb",
                    "peak_kb",
                    "py_peak",
                )
            }
            for r in sorted(recorder.records, key=lambda r: r["start"])
            if r["depth"] <= 3
        ],
        "summary": summary,
    }
    (out / "memory.json").write_text(json.dumps(payload, indent=1, default=str) + "\n")
    print(
        json.dumps(
            {
                k: payload[k]
                for k in ("cells", "wall_seconds", "peak_mb", "peak_bytes_per_cell")
            }
        )
    )
    for name, s in sorted(payload["stages"].items(), key=lambda kv: -kv[1]["peak_mb"]):
        print(
            f"{name:40s} calls {s['calls']:4d} {s['seconds']:9.2f} s "
            f"peak {s['peak_mb']:9.1f} MB (+{s['peak_above_entry_mb']:8.1f}) "
            f"{s['peak_bytes_per_cell']:8.1f} B/cell"
        )


if __name__ == "__main__":
    main()
