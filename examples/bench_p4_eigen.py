"""Task P4 (research/p4-eigen.md): record and replay anchored-response calls.

Usage:
    python examples/bench_p4_eigen.py record <calls.npz> <script.py | -m module> [args...]
    python examples/bench_p4_eigen.py replay <calls.npz> <lib-a.so> <lib-b.so> <out.json> [--passes 7]
    python examples/bench_p4_eigen.py dump <calls.npz> <records.f64>
    python examples/bench_p4_eigen.py diff <a.json> <b.json> <out.json>

`record` wraps `rang.core_influence.anchored_response` before the
target runs (no module is edited), so every call made by the target, also
through `from ... import anchored_response`, is saved with the exact arrays
handed to `rang_response_step` and the native status it returned under the
library in `RANG_TOY_LIB`. `replay` calls both libraries directly through
ctypes on every recorded call, compares statuses, ranks, diagnostics and
deltas, and times the calls in alternating passes. `dump` writes the raw
records that `src/response.rs`'s ignored `p4_dump_audit` test reads. `diff`
lists every leaf where two result JSONs differ: volatile leaves (timings,
paths, and the digests task P8 found to hash timings) are counted apart, and
any other difference that is not between two floats fails.
"""

import ctypes
import json
import math
import runpy
import statistics
import sys
import time
from pathlib import Path

import numpy as np

FIELDS = ("full_h", "full_b", "drop_h", "drop_b", "gains", "active")


def loadavg():
    try:
        return Path("/proc/loadavg").read_text().split()[0]
    except OSError:  # not Linux (task P7: the harness test runs on Windows)
        return None


def record(out, target):
    from rang import core_influence as influence

    original = influence.anchored_response
    calls = {k: [] for k in (*FIELDS, "status")}

    def wrapped(full_h, full_b, drop_h, drop_b, gains, active):
        result = original(full_h, full_b, drop_h, drop_b, gains, active)
        gain = influence._complex(gains, (4, 2, 2)).copy()
        active = np.asarray(active)
        gain[~active] = 0
        for key, value in zip(
            FIELDS,
            (full_h, full_b, drop_h, drop_b, gain.view(np.float64).ravel(), active),
            strict=True,
        ):
            calls[key].append(
                np.array(value, dtype=np.uint8 if key == "active" else np.float64)
            )
        calls["status"].append(result["native_status"])
        return result

    influence.anchored_response = wrapped
    try:
        if target[0] == "-m":
            sys.argv = [target[1], *target[2:]]
            runpy.run_module(target[1], run_name="__main__", alter_sys=True)
        else:
            sys.argv = list(target)
            sys.path.insert(0, str(Path(target[0]).resolve().parent))
            runpy.run_path(target[0], run_name="__main__")
    finally:
        influence.anchored_response = original
        np.savez_compressed(out, **{k: np.array(v) for k, v in calls.items()})
        print(json.dumps({"recorded_calls": len(calls["status"]), "out": str(out)}))


def library(path):
    lib = ctypes.CDLL(str(Path(path).resolve()))
    real = np.ctypeslib.ndpointer(dtype=np.float64, flags=("C_CONTIGUOUS", "ALIGNED"))
    byte = np.ctypeslib.ndpointer(dtype=np.uint8, flags=("C_CONTIGUOUS", "ALIGNED"))
    step = lib.rang_response_step
    step.argtypes = [real] * 5 + [byte] + [real] * 2
    step.restype = ctypes.c_int
    return step


def run_all(step, calls):
    n = len(calls["status"])
    status = np.empty(n, np.int64)
    delta = np.zeros((n, 32))
    info = np.full((n, 10), np.nan)
    arrays = [np.ascontiguousarray(calls[k]) for k in FIELDS]
    started = time.perf_counter()
    for i in range(n):
        status[i] = step(*(a[i] for a in arrays), delta[i], info[i])
    return status, delta, info, time.perf_counter() - started


def replay(path, lib_a, lib_b, out, passes=7):
    calls = dict(np.load(path))
    a, b = library(lib_a), library(lib_b)
    sa, da, ia, _ = run_all(a, calls)
    sb, db, ib, _ = run_all(b, calls)
    ok = (sa == 0) & (sb == 0)
    gain_norm = np.abs(calls["gains"]).max(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        diag_rel = np.abs(ib - ia) / np.abs(ia)
    step = ia[ok, 7]
    seconds = {"a": [], "b": []}
    before = loadavg()
    for k in range(passes):
        for arm, fn in (("a", a), ("b", b)) if k % 2 == 0 else (("b", b), ("a", a)):
            seconds[arm].append(run_all(fn, calls)[3])
    after = loadavg()
    statuses = {
        int(s): int(c) for s, c in zip(*np.unique(sa, return_counts=True), strict=True)
    }
    report = {
        "calls": len(sa),
        "recorded_status_equals_a": bool((calls["status"] == sa).all()),
        "status_identical": bool((sa == sb).all()),
        "status_counts_a": statuses,
        "status_0_ranks_identical": bool(
            (ia[ok, :2] == ib[ok, :2]).all() and ((sa == 0) == (sb == 0)).all()
        ),
        "max_delta_diff_over_max_gain": float(
            (np.abs(db - da).max(axis=1)[ok] / gain_norm[ok]).max(initial=0.0)
        ),
        "max_diagnostic_rel_diff": {
            name: float(np.nanmax(diag_rel[ok, j], initial=0.0))
            for j, name in enumerate(
                (
                    "full_rank",
                    "retained_rank",
                    "gauge_rank",
                    "largest_curvature",
                    "smallest_retained_curvature",
                    "condition",
                    "damping",
                    "max_relative_step",
                    "baseline_projected_score_norm",
                    "gauge_null_relative",
                )
            )
        },
        "trust_threshold_0p1_identical": bool(
            ((ia[ok, 7] <= 0.1) == (ib[ok, 7] <= 0.1)).all()
        ),
        "min_abs_log10_step_over_0p1": float(
            np.abs(np.log10(step[step > 0] / 0.1)).min(initial=np.inf)
        ),
        "timing": {
            "passes": passes,
            "load_before": before,
            "load_after": after,
            **{
                f"{arm}_{stat}": fn(v)
                for arm, v in seconds.items()
                for stat, fn in (("min", min), ("median", statistics.median))
            },
            "per_call_us_a_min": 1e6 * min(seconds["a"]) / max(len(sa), 1),
            "per_call_us_b_min": 1e6 * min(seconds["b"]) / max(len(sa), 1),
        },
        "libraries": {"a": str(lib_a), "b": str(lib_b)},
    }
    Path(out).write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


def dump(path, out):
    calls = dict(np.load(path))
    n = len(calls["status"])
    records = np.concatenate(
        [
            calls["full_h"].reshape(n, 1024),
            calls["drop_h"].reshape(n, 1024),
            calls["gains"].reshape(n, 32),
            calls["active"].reshape(n, 4).astype(np.float64),
        ],
        axis=1,
    )
    records.astype("<f8").tofile(out)
    print(json.dumps({"records": n, "out": str(out)}))


VOLATILE = ("seconds", "frozen_train_responses_sha256", "acceptance_digest_core")


def leaves(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, (*path, index))
    else:
        yield path, value


def volatile(path, a, b):
    keys = [p for p in path if isinstance(p, str)]
    if any(v in k for k in keys for v in VOLATILE) or "wall" in "/".join(keys):
        return True
    return isinstance(a, str) and isinstance(b, str) and ("/" in a or "/" in b)


def diff(path_a, path_b, out):
    a = dict(leaves(json.loads(Path(path_a).read_text())))
    b = dict(leaves(json.loads(Path(path_b).read_text())))
    report = {
        "a": str(path_a),
        "b": str(path_b),
        "leaves_a": len(a),
        "leaves_b": len(b),
        "volatile": [],
        "floats": [],
        "failures": [],
    }
    for path in sorted(set(a) | set(b), key=str):
        x, y = a.get(path, "<missing>"), b.get(path, "<missing>")
        if x == y or (
            isinstance(x, float)
            and isinstance(y, float)
            and math.isnan(x)
            and math.isnan(y)
        ):
            continue
        if volatile(path, x, y):
            report["volatile"].append(list(path))
        elif isinstance(x, float) and isinstance(y, float):
            rel = abs(x - y) / max(abs(x), abs(y))
            report["floats"].append(
                {"path": list(path), "a": x, "b": y, "relative": rel}
            )
        else:
            report["failures"].append({"path": list(path), "a": x, "b": y})
    report["max_float_relative"] = max(
        (f["relative"] for f in report["floats"]), default=0.0
    )
    report["identical_apart_from_volatile_and_floats"] = not report["failures"]
    Path(out).write_text(json.dumps(report, indent=1, default=str) + "\n")
    summary = {k: v for k, v in report.items() if k not in ("floats", "volatile")}
    summary["floats"] = len(report["floats"])
    summary["volatile"] = len(report["volatile"])
    print(json.dumps(summary, default=str))
    return 0 if not report["failures"] else 1


def main():
    mode, args = sys.argv[1], sys.argv[2:]
    if mode == "record":
        record(Path(args[0]), args[1:])
    elif mode == "replay":
        passes = int(args[args.index("--passes") + 1]) if "--passes" in args else 7
        replay(*args[:4], passes=passes)
    elif mode == "dump":
        dump(*args[:2])
    elif mode == "diff":
        raise SystemExit(diff(*args[:3]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
