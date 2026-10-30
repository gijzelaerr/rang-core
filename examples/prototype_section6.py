"""The section 6 prototype: one pass from LUNO zarr tiles to the rank survey.

Usage: python examples/prototype_section6.py outputs/<fresh-run>

research/core-section6.md and stack-consolidation-feasibility.md section 6.
Zarr ingest (Rust blosc, block-selective reads) -> core complex solve ->
fused pass (residuals, split sums, robust scores, antenna-diagonal normals)
-> TV -> rank survey and response status -> TV-guided policy masks. No
Measurement Set is read or written. Writes result.json, gains.npz and
receipt.json only.
"""

import json
import platform
import resource
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np
from rangtoy import core, core_zarr
from rangtoy.core_influence import anchored_response, training_normals
from rangtoy.core_policy import gain_tv, polar_gauge, policy_mask

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "outputs/luno-support-20261029-01/slice/MAIN/MAIN_1"
SOLVE = ROOT / "outputs/luno-solve-20261029-02/inputs/MAIN/MAIN_1"
STATIONS = (0, 1, 2, 3)
TILES = range(8, 24)
GRID = (2, 32)
CUTOFF = 1e-10
THRESHOLDS = (8.0, 5.0, 3.0)
TV_WEIGHTS = (0.0, 1.0, 3.0)
TILE_COLUMNS = {
    "DATA": (SOLVE, "<c8"),
    "MODEL_DATA": (SUPPORT, "<c8"),
    "FLAG": (SUPPORT, "|b1"),
    "WEIGHT_SPECTRUM": (SUPPORT, "<f4"),
}


def ingest():
    """Row columns in full; tile columns for the kept rows only."""
    stats = {
        "bytes_read": 0,
        "blocks_decoded": 0,
        "blocks_total": 0,
        "decode_seconds": 0.0,
    }
    started = time.perf_counter()
    row = {}
    for name, dtype in (
        ("ANTENNA1", "<i4"),
        ("ANTENNA2", "<i4"),
        ("TIME", "<f8"),
        ("FLAG_ROW", "|b1"),
    ):
        path = SUPPORT / name / "0"
        payload = path.read_bytes()
        stats["bytes_read"] += len(payload)
        decode_started = time.perf_counter()
        row[name] = np.frombuffer(core.blosc_decode(payload), dtype)
        stats["decode_seconds"] += time.perf_counter() - decode_started
    a1, a2 = row["ANTENNA1"], row["ANTENNA2"]
    keep = (a1 != a2) & np.isin(a1, STATIONS) & np.isin(a2, STATIONS) & ~row["FLAG_ROW"]
    rows = np.flatnonzero(keep)
    arrays = {k: np.ascontiguousarray(v[rows]) for k, v in row.items()}
    for name, (root, dtype) in TILE_COLUMNS.items():
        meta = core_zarr.array_meta(root / name)
        nchan, ncorr = meta["chunks"][1], meta["chunks"][2]
        row_bytes = nchan * ncorr * np.dtype(dtype).itemsize
        parts = []
        for tile in TILES:
            raw, st = core_zarr.read_rows(root / name / f"0.{tile}.0", row_bytes, rows)
            for k in stats:
                stats[k] += st[k]
            parts.append(np.frombuffer(raw, dtype).reshape(len(rows), nchan, ncorr))
        arrays[name] = np.concatenate(parts, axis=1)
    stats["seconds"] = time.perf_counter() - started
    return arrays, stats


def section6_pass(arrays):
    """Everything after ingest; returns products and per-step seconds."""
    seconds = {}
    t = time.perf_counter()
    data, model = arrays["DATA"], arrays["MODEL_DATA"]
    weights, flag = arrays["WEIGHT_SPECTRUM"], arrays["FLAG"]
    p, q = arrays["ANTENNA1"].astype(np.int32), arrays["ANTENNA2"].astype(np.int32)
    integration = np.unique(arrays["TIME"], return_inverse=True)[1]
    tb = integration // GRID[0]
    fb = np.arange(data.shape[1]) // GRID[1]
    nt, nf = int(tb.max()) + 1, int(fb.max()) + 1
    solution = core.solve_complex(
        data,
        weights,
        flag,
        arrays["FLAG_ROW"],
        p,
        q,
        tb,
        fb,
        ntime_bins=nt,
        nfreq_bins=nf,
        nant=4,
        model=model,
    )
    seconds["solve"] = time.perf_counter() - t
    t = time.perf_counter()
    gains = solution.gains
    valid = (solution.flags == 0) & np.isfinite(gains).all(axis=(-1, -2))
    train = (
        ~flag.any(-1)
        & ~arrays["FLAG_ROW"][:, None]
        & (weights > 0).all(-1)
        & np.isfinite(model).all(-1)
    )
    fused = core.fused_pass(
        data,
        weights,
        p,
        q,
        tb,
        fb,
        gains,
        valid,
        core.split_labels(train=train),
        model=model,
    )
    seconds["fused"] = time.perf_counter() - t
    t = time.perf_counter()
    unique_times = np.unique(arrays["TIME"])
    gain_times = np.array(
        [
            unique_times[i : i + GRID[0]].mean()
            for i in range(0, len(unique_times), GRID[0])
        ]
    )
    freqs = np.arange(data.shape[1], dtype=float)
    gain_freqs = np.array(
        [freqs[i : i + GRID[1]].mean() for i in range(0, len(freqs), GRID[1])]
    )
    scale = float(np.median(np.linalg.norm(gains[valid], axis=(-1, -2))))
    aligned, tv_valid = polar_gauge(gains, valid)
    tv = gain_tv(aligned, tv_valid, gain_times, gain_freqs, scale=scale)
    guidance = np.maximum(
        tv["map"][tb[:, None], fb[None], p[:, None]],
        tv["map"][tb[:, None], fb[None], q[:, None]],
    )
    masks = {
        f"tau{tau:g}-alpha{alpha:g}": policy_mask(
            fused.scores,
            guidance,
            train,
            threshold=tau,
            tv_weight=alpha,
            max_fraction=0.02,
        )
        for alpha in TV_WEIGHTS
        for tau in THRESHOLDS
    }
    seconds["tv_and_policy"] = time.perf_counter() - t
    t = time.perf_counter()
    rows, channels = np.nonzero(train)
    bins = tb[rows] * nf + fb[channels]
    flat = np.ascontiguousarray(gains.reshape(nt * nf, 4, 2, 2))
    h, _, counts = training_normals(
        np.where(np.isfinite(flat), flat, 0),
        model[rows, channels].astype(np.complex128).reshape(-1, 2, 2),
        np.zeros((len(rows), 2, 2), np.complex128),
        weights[rows, channels].astype(np.float64),
        p[rows],
        q[rows],
        bins,
    )
    gflags = (solution.flags != 0).reshape(nt * nf, 4)
    survey = {
        "fully_identified": 0,
        "underidentified": 0,
        "no_train": 0,
        "no_solved_gain": 0,
        "over_rank": 0,
        "status": {},
    }
    # One batched eigenvalue call over every bin with TRAIN data; LAPACK
    # computes each matrix exactly as a per-bin call does.
    with_train = np.flatnonzero(counts)
    eigenvalues = np.zeros((nt * nf, 32))
    eigenvalues[with_train] = np.linalg.eigvalsh(h[with_train])
    order = np.argsort(bins, kind="stable")
    sorted_bins = bins[order]
    for k in range(nt * nf):
        if not counts[k]:
            survey["no_train"] += 1
            continue
        lo, hi = np.searchsorted(sorted_bins, [k, k + 1])
        sel = order[lo:hi]
        active = np.zeros(4, bool)
        active[p[rows][sel]] = True
        active[q[rows][sel]] = True
        if gflags[k, active].any():
            survey["no_solved_gain"] += 1
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
        status = anchored_response(h[k], zero, 0 * h[k], zero, flat[k], active)[
            "native_status"
        ]
        key = f"{label} status{status}"
        survey["status"][key] = survey["status"].get(key, 0) + 1
    seconds["rank_survey"] = time.perf_counter() - t
    chi2 = fused.losses()["train"]
    return {
        "solution": solution,
        "valid": valid,
        "train": train,
        "fused": fused,
        "tv": tv,
        "guidance": guidance,
        "masks": masks,
        "survey": survey,
        "chi2": chi2,
        "scale": scale,
        "normals_full": h,
        "gain_times": gain_times,
        "gain_freqs": gain_freqs,
        "bins": (tb, fb, nt, nf),
    }, seconds


def digest(path):
    """Streamed SHA256, so hashing a large chunk does not hold it in memory."""
    h = sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    out = Path(sys.argv[1])
    if not str(out).startswith("outputs/") or out.exists():
        raise SystemExit("run directory must be new and beneath outputs/")
    core.extension()  # load before timing
    wall = time.perf_counter()
    arrays, ingest_stats = ingest()
    products, seconds = section6_pass(arrays)
    wall = time.perf_counter() - wall
    out.mkdir(parents=True)
    solution = products["solution"]
    np.savez(out / "gains.npz", gains=solution.gains, gain_flags=solution.flags)
    result = {
        "protocol": "research/core-section6.md",
        "wall_seconds": wall,
        "decode_seconds": ingest_stats["decode_seconds"],
        "wall_seconds_excluding_decode": wall - ingest_stats["decode_seconds"],
        "ingest": ingest_stats,
        "step_seconds": seconds,
        "max_rss_mb_self": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "rows": len(arrays["ANTENNA1"]),
        "shape": list(arrays["DATA"].shape),
        "iterations": solution.iterations,
        "converged_fraction": solution.converged_fraction,
        "flagged_gain_fraction": float(np.mean(solution.flags != 0)),
        "chi2_train_mean_per_cell": products["chi2"],
        "tv_total": products["tv"]["total"],
        "survey": products["survey"],
        "policy_mask_counts": {k: int(v.sum()) for k, v in products["masks"].items()},
        "policy_mask_sha256": {
            k: sha256(v.tobytes()).hexdigest() for k, v in products["masks"].items()
        },
    }
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    inputs = {}
    for name in ("ANTENNA1", "ANTENNA2", "TIME", "FLAG_ROW"):
        inputs[f"{name}/0"] = digest(SUPPORT / name / "0")
    for name, (root, _) in TILE_COLUMNS.items():
        for tile in TILES:
            inputs[f"{name}/0.{tile}.0"] = digest(root / name / f"0.{tile}.0")
    receipt = {
        "input_chunk_sha256": inputs,
        "code_sha256": {
            p.relative_to(ROOT).as_posix(): digest(p)
            for p in sorted((ROOT / "core/src").glob("*.rs"))
            + [
                ROOT / "python/rangtoy/core.py",
                ROOT / "python/rangtoy/core_zarr.py",
                Path(__file__).resolve(),
            ]
        },
        "library_sha256": digest(core.library_path()),
        "settings": {
            "stations": STATIONS,
            "tiles": [TILES.start, TILES.stop],
            "grid": GRID,
            "iterations": 50,
            "stop_criterion": 1e-7,
            "stop_fraction": 0.99,
            "rank_cutoff": CUTOFF,
            "thresholds": THRESHOLDS,
            "tv_weights": TV_WEIGHTS,
        },
        "oracle_gains_sha256": {
            "quartical_cold_cache": "57809b86f7d9bd90c679ed4d4a51875517d1fe6d6eb492c9cb4cfdef04329bc3",
            "quartical_warm_cache": "769a69b1a7b07cabb91c4b31c330edf5ad4af207541946cecbdc1a1478424ce2",
            "comparison": "by tolerance, not hash (upstream-notes.md)",
        },
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "wall_seconds",
                    "decode_seconds",
                    "wall_seconds_excluding_decode",
                    "max_rss_mb_self",
                    "iterations",
                    "converged_fraction",
                    "chi2_train_mean_per_cell",
                )
            }
        )
    )
    print(json.dumps(result["step_seconds"]), json.dumps(result["survey"]))


if __name__ == "__main__":
    main()
