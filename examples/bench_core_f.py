"""Task F benchmark and equality harness (research/core-f-performance.md).

Usage:
    python examples/bench_core_f.py baseline outputs/<fresh-dir> [--target T]
    python examples/bench_core_f.py check outputs/<fresh-dir> <baseline.json> [--target T]

`baseline` measures the unchanged kernels and writes `baseline.json` with the
result hashes every later `check` run must reproduce bit for bit. Targets:
`solve`, `blosc`, `survey` or `all` (default). Timings are wall seconds from
`time.perf_counter`, single process; each series reports its minimum and
median and the 1-minute load average before and after. The core library is
`RANG_CORE_LIB` or `core/target/release/librang_core.so`, never rebuilt here.
"""

import argparse
import ctypes
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault(
    "RANG_CORE_LIB", str(ROOT / "core/target/release/librang_core.so")
)
sys.path.insert(0, str(ROOT / "examples"))

from rangtoy import core, core_zarr
from rangtoy.flagging_influence import anchored_response, training_normals
from validate_core_phase2 import (
    FIXTURE,
    FIXTURE_FLAGS,
    LUNO_ARRAYS,
    LUNO_SOLVE,
    TRIAL,
    bins,
    compare_gains,
)

ORACLE = ROOT / "outputs/core-section6-oracle-20261029-01/receipt.json"
SUPPORT = ROOT / "outputs/luno-support-20261029-01/slice/MAIN/MAIN_1"
SOLVE = ROOT / "outputs/luno-solve-20261029-02/inputs/MAIN/MAIN_1"
STATIONS = (0, 1, 2, 3)
TILES = range(8, 24)
GRID = (2, 32)
CUTOFF = 1e-10
TILE_COLUMNS = {
    "DATA": (SOLVE, "<c8"),
    "MODEL_DATA": (SUPPORT, "<c8"),
    "FLAG": (SUPPORT, "|b1"),
    "WEIGHT_SPECTRUM": (SUPPORT, "<f4"),
}
REPEATS = {"solve": 7, "blosc": 5, "survey": 7}


def loadavg():
    return float(Path("/proc/loadavg").read_text().split()[0])


def series(values, before, after):
    return {
        "runs": values,
        "min": min(values),
        "median": statistics.median(values),
        "load_before": before,
        "load_after": after,
    }


def timed(fn, repeats):
    before = loadavg()
    out, seconds = None, []
    for _ in range(repeats):
        t = time.perf_counter()
        out = fn()
        seconds.append(time.perf_counter() - t)
    return out, series(seconds, before, loadavg())


def digest(data):
    return sha256(data).hexdigest()


# --- solver -----------------------------------------------------------------


def luno_inputs():
    with np.load(LUNO_ARRAYS) as z:
        a = {k: z[k] for k in z.files}
    tb, fb = bins(a["TIME"], a["DATA"].shape[1])
    qc = np.load(LUNO_SOLVE / "gains.npy").astype(np.complex128)
    qc_flagged = np.load(LUNO_SOLVE / "gain_flags.npy") != 0
    nt, nf, na = qc.shape[:3]
    args = (
        a["DATA"],
        a["WEIGHT_SPECTRUM"],
        a["FLAG"],
        a["FLAG_ROW"],
        a["ANTENNA1"],
        a["ANTENNA2"],
        tb,
        fb,
    )
    kwargs = {"ntime_bins": nt, "nfreq_bins": nf, "nant": na, "model": a["MODEL_DATA"]}
    return a, (tb, fb, nt, nf), args, kwargs, qc, qc_flagged


def fixture_inputs():
    with np.load(FIXTURE / "state.npz") as z:
        s = {k: z[k] for k in z.files}
    with np.load(FIXTURE_FLAGS) as z:
        flag, flag_row = z["FLAG"], z["FLAG_ROW"]
    with np.load(TRIAL / "diagnostics.npz") as z:
        qc, valid = z["gains"].astype(np.complex128), z["gain_valid"]
    tb, fb = bins(s["times"], s["data"].shape[1])
    nt, nf, na = qc.shape[:3]
    args = (
        s["data"],
        s["weights"],
        flag,
        flag_row,
        s["antenna1"],
        s["antenna2"],
        tb,
        fb,
    )
    kwargs = {"ntime_bins": nt, "nfreq_bins": nf, "nant": na, "model": s["model"]}
    return args, kwargs, qc, ~valid


def solution_snapshot(solution):
    return {
        "gains_sha256": digest(np.ascontiguousarray(solution.gains).tobytes()),
        "flags_sha256": digest(np.ascontiguousarray(solution.flags).tobytes()),
        "iterations": solution.iterations,
        "converged_fraction": solution.converged_fraction,
    }


def bench_solve():
    out = {}
    for name, loader in (("luno", luno_inputs), ("fixture", fixture_inputs)):
        loaded = loader()
        args, kwargs, qc, qc_flagged = loaded[-4:]

        def run(args=args, kwargs=kwargs):
            return core.solve_complex(*args, **kwargs)

        solution, timing = timed(run, REPEATS["solve"])
        out[name] = {
            "snapshot": solution_snapshot(solution),
            "quartical": compare_gains(solution, qc, qc_flagged),
            "seconds": timing,
        }
    return out


# --- blosc ------------------------------------------------------------------


def oracle_chunks():
    receipt = json.loads(ORACLE.read_text())["chunks"]
    return {
        key: (ROOT / rec["path"].replace("/workspace/", ""), rec)
        for key, rec in receipt.items()
    }


def rust_decode_into(lib, payload, out):
    status = lib.rang_core_blosc_decode(
        payload, len(payload), out.ctypes.data_as(ctypes.c_char_p), len(out)
    )
    if status:
        raise ValueError("rust blosc decode failed")


def bench_blosc_full():
    """Criterion 2a: every oracle chunk, and timing on the 16 DATA tiles."""
    from numcodecs import blosc as cblosc

    lib = core.library()
    chunks = oracle_chunks()
    hashes = {}
    sizes = {}
    rust_runs = [0.0] * REPEATS["blosc"]
    c1_runs = [0.0] * REPEATS["blosc"]
    cn_runs = [0.0] * REPEATS["blosc"]
    data_bytes = 0
    default_threads = cblosc.get_nthreads() if hasattr(cblosc, "get_nthreads") else None
    before = loadavg()
    for key, (path, rec) in chunks.items():
        payload = path.read_bytes()
        out = np.empty(rec["decoded_bytes"], np.uint8)
        rust_decode_into(lib, payload, out)
        hashes[key] = digest(out.tobytes())
        sizes[key] = rec["decoded_bytes"]
        if not key.startswith("DATA/"):
            continue
        data_bytes += rec["decoded_bytes"]
        ref = np.empty_like(out)
        for r in range(REPEATS["blosc"]):
            t = time.perf_counter()
            rust_decode_into(lib, payload, out)
            rust_runs[r] += time.perf_counter() - t
            cblosc.set_nthreads(1)
            t = time.perf_counter()
            cblosc.decompress(payload, ref)
            c1_runs[r] += time.perf_counter() - t
            if default_threads:
                cblosc.set_nthreads(default_threads)
                t = time.perf_counter()
                cblosc.decompress(payload, ref)
                cn_runs[r] += time.perf_counter() - t
        if not np.array_equal(out, ref):
            raise AssertionError(f"numcodecs and rust disagree on {key}")
    after = loadavg()
    oracle_equal = {
        k: hashes[k] == rec["decoded_sha256"] for k, (_, rec) in chunks.items()
    }
    return {
        "chunks": len(chunks),
        "oracle_equal_all": all(oracle_equal.values()),
        "oracle_mismatches": [k for k, ok in oracle_equal.items() if not ok],
        "decoded_sha256": hashes,
        "data_tiles_decoded_bytes": data_bytes,
        "rust_seconds": series(rust_runs, before, after),
        "cblosc_1thread_seconds": series(c1_runs, before, after),
        "cblosc_default_threads": default_threads,
        "cblosc_default_seconds": series(cn_runs, before, after)
        if default_threads
        else None,
        "rust_gbps": data_bytes / min(rust_runs) / 1e9,
        "cblosc_1thread_gbps": data_bytes / min(c1_runs) / 1e9,
    }


def prototype_rows():
    row = {}
    for name, dtype in (("ANTENNA1", "<i4"), ("ANTENNA2", "<i4"), ("FLAG_ROW", "|b1")):
        row[name] = np.frombuffer(
            core.blosc_decode((SUPPORT / name / "0").read_bytes()), dtype
        )
    a1, a2 = row["ANTENNA1"], row["ANTENNA2"]
    keep = (a1 != a2) & np.isin(a1, STATIONS) & np.isin(a2, STATIONS) & ~row["FLAG_ROW"]
    return np.flatnonzero(keep)


def bench_blosc_rows():
    """Criterion 2b: the block-selective ingest as the prototype runs it."""
    rows = prototype_rows()
    hashes = {}
    wall_runs, decode_runs = [], []
    blocks = bytes_read = 0
    before = loadavg()
    for _ in range(REPEATS["blosc"]):
        t = time.perf_counter()
        decode = 0.0
        blocks = bytes_read = 0
        for name, (root, dtype) in TILE_COLUMNS.items():
            meta = core_zarr.array_meta(root / name)
            row_bytes = meta["chunks"][1] * meta["chunks"][2] * np.dtype(dtype).itemsize
            h = sha256()
            for tile in TILES:
                raw, st = core_zarr.read_rows(
                    root / name / f"0.{tile}.0", row_bytes, rows
                )
                h.update(raw)
                decode += st["decode_seconds"]
                blocks += st["blocks_decoded"]
                bytes_read += st["bytes_read"]
            hashes[name] = h.hexdigest()
        wall_runs.append(time.perf_counter() - t)
        decode_runs.append(decode)
    after = loadavg()
    return {
        "rows": len(rows),
        "blocks_decoded": blocks,
        "bytes_read": bytes_read,
        "selected_sha256": hashes,
        "decode_seconds": series(decode_runs, before, after),
        "wall_seconds": series(wall_runs, before, after),
    }


def bench_blosc():
    return {"full": bench_blosc_full(), "rows": bench_blosc_rows()}


# --- survey -----------------------------------------------------------------


def survey_prototype(a, grid, solution):
    """The prototype's rank survey, with per-part seconds and per-bin records."""
    tb, fb, nt, nf = grid
    seconds = {}
    t = time.perf_counter()
    model, weights, flag = a["MODEL_DATA"], a["WEIGHT_SPECTRUM"], a["FLAG"]
    p, q = a["ANTENNA1"].astype(np.int32), a["ANTENNA2"].astype(np.int32)
    gains = solution.gains
    train = (
        ~flag.any(-1)
        & ~a["FLAG_ROW"][:, None]
        & (weights > 0).all(-1)
        & np.isfinite(model).all(-1)
    )
    rows, channels = np.nonzero(train)
    bins_ = tb[rows] * nf + fb[channels]
    flat = np.ascontiguousarray(gains.reshape(nt * nf, 4, 2, 2))
    seconds["prepare"] = time.perf_counter() - t
    t = time.perf_counter()
    h, _, counts = training_normals(
        np.where(np.isfinite(flat), flat, 0),
        model[rows, channels].astype(np.complex128).reshape(-1, 2, 2),
        np.zeros((len(rows), 2, 2), np.complex128),
        weights[rows, channels].astype(np.float64),
        p[rows],
        q[rows],
        bins_,
    )
    seconds["normals"] = time.perf_counter() - t
    t = time.perf_counter()
    gflags = (solution.flags != 0).reshape(nt * nf, 4)
    with_train = np.flatnonzero(counts)
    eigenvalues = np.zeros((nt * nf, 32))
    eigenvalues[with_train] = np.linalg.eigvalsh(h[with_train])
    seconds["eigenvalues"] = time.perf_counter() - t
    t = time.perf_counter()
    survey = {
        "fully_identified": 0,
        "underidentified": 0,
        "no_train": 0,
        "no_solved_gain": 0,
        "over_rank": 0,
        "status": {},
    }
    labels, statuses = [], []
    response = 0.0
    order = np.argsort(bins_, kind="stable")
    sorted_bins = bins_[order]
    for k in range(nt * nf):
        if not counts[k]:
            survey["no_train"] += 1
            labels.append("no_train")
            statuses.append(-1)
            continue
        lo, hi = np.searchsorted(sorted_bins, [k, k + 1])
        sel = order[lo:hi]
        active = np.zeros(4, bool)
        active[p[rows][sel]] = True
        active[q[rows][sel]] = True
        if gflags[k, active].any():
            survey["no_solved_gain"] += 1
            labels.append("no_solved_gain")
            statuses.append(-1)
            continue
        eig = eigenvalues[k]
        rank = int(np.sum(eig > CUTOFF * eig[-1])) if eig[-1] > 0 else 0
        required = 8 * int(active.sum()) - 4
        label = (
            "fully_identified"
            if rank == required
            else ("underidentified" if rank < required else "over_rank")
        )
        survey[label] += 1
        zero = np.zeros(32)
        t2 = time.perf_counter()
        status = anchored_response(h[k], zero, 0 * h[k], zero, flat[k], active)[
            "native_status"
        ]
        response += time.perf_counter() - t2
        key = f"{label} status{status}"
        survey["status"][key] = survey["status"].get(key, 0) + 1
        labels.append(label)
        statuses.append(int(status))
    seconds["loop"] = time.perf_counter() - t
    seconds["loop_anchored_response"] = response
    return survey, labels, statuses, seconds


def bench_survey():
    a, grid, args, kwargs, _, _ = luno_inputs()
    solution = core.solve_complex(*args, **kwargs)
    parts = []
    before = loadavg()
    wall = []
    for _ in range(REPEATS["survey"]):
        t = time.perf_counter()
        survey, labels, statuses, seconds = survey_prototype(a, grid, solution)
        wall.append(time.perf_counter() - t)
        parts.append(seconds)
    after = loadavg()
    return {
        "survey": survey,
        "labels_sha256": digest(json.dumps(labels).encode()),
        "statuses_sha256": digest(json.dumps(statuses).encode()),
        "seconds": series(wall, before, after),
        "parts_min": {k: min(x[k] for x in parts) for k in parts[0]},
        "parts_median": {k: statistics.median(x[k] for x in parts) for k in parts[0]},
    }


# --- driver -----------------------------------------------------------------


def compare(baseline, current):
    checks = {}
    if "solve" in current and "solve" in baseline:
        for name in ("luno", "fixture"):
            b, c = baseline["solve"][name], current["solve"][name]
            checks[f"solve_{name}_bit_identical"] = b["snapshot"] == c["snapshot"]
            q = c["quartical"]
            checks[f"solve_{name}_quartical"] = (
                q["flags_equal"]
                and q["max_abs_gain_entry_diff"] <= 1e-6
                and q["max_abs_baseline_product_diff"] <= 1e-6
            )
        q = current["solve"]["luno"]["quartical"]
        checks["solve_luno_convergence"] = (
            q["iterations"] == 50
            and abs(q["converged_fraction"] - 0.9833234067897558) <= 1e-12
        )
    if "blosc" in current and "blosc" in baseline:
        checks["blosc_oracle_all_equal"] = current["blosc"]["full"]["oracle_equal_all"]
        checks["blosc_rows_identical"] = (
            current["blosc"]["rows"]["selected_sha256"]
            == baseline["blosc"]["rows"]["selected_sha256"]
        )
    if "survey" in current and "survey" in baseline:
        b, c = baseline["survey"], current["survey"]
        checks["survey_identical"] = (
            b["survey"] == c["survey"]
            and b["labels_sha256"] == c["labels_sha256"]
            and b["statuses_sha256"] == c["statuses_sha256"]
        )
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("baseline", "check"))
    parser.add_argument("out_dir")
    parser.add_argument("baseline", nargs="?")
    parser.add_argument(
        "--target", default="all", choices=("all", "solve", "blosc", "survey")
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    targets = ("solve", "blosc", "survey") if args.target == "all" else (args.target,)
    lib_path = core.library_path()
    result = {
        "protocol": "research/core-f-performance.md",
        "mode": args.mode,
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "library": str(lib_path),
        "library_sha256": digest(lib_path.read_bytes()),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "repeats": REPEATS,
    }
    for target in targets:
        started = time.perf_counter()
        result[target] = {
            "solve": bench_solve,
            "blosc": bench_blosc,
            "survey": bench_survey,
        }[target]()
        result[target]["bench_wall_seconds"] = time.perf_counter() - started
        print(
            target,
            "done in",
            f"{result[target]['bench_wall_seconds']:.1f} s",
            flush=True,
        )
    if args.mode == "check":
        baseline = json.loads(Path(args.baseline).read_text())
        result["baseline"] = str(args.baseline)
        result["checks"] = compare(baseline, result)
        result["all_checks_pass"] = all(result["checks"].values())
    name = "baseline.json" if args.mode == "baseline" else "check.json"
    (out_dir / name).write_text(json.dumps(result, indent=1))
    summary = {}
    if "solve" in result:
        summary["solve"] = {
            k: result["solve"][k]["seconds"]["min"] for k in ("luno", "fixture")
        }
    if "blosc" in result:
        f, r = result["blosc"]["full"], result["blosc"]["rows"]
        summary["blosc"] = {
            "rust_full_min": f["rust_seconds"]["min"],
            "cblosc_1thread_min": f["cblosc_1thread_seconds"]["min"],
            "rows_decode_min": r["decode_seconds"]["min"],
        }
    if "survey" in result:
        summary["survey"] = result["survey"]["parts_min"]
    print(json.dumps(summary, indent=1))
    if args.mode == "check":
        print(json.dumps(result["checks"], indent=1))
        sys.exit(0 if result["all_checks_pass"] else 1)


if __name__ == "__main__":
    main()
