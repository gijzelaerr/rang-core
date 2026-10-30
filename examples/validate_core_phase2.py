"""Validate phase 2 of the Rang core: the ported complex solver (research/core-phase2.md).

Usage:
    python examples/validate_core_phase2.py outputs/<fresh-run-dir>
    python examples/validate_core_phase2.py --cost <arrays.npz>   (internal)

Compares the Rust solve with QuartiCal 0.2.7's archived gains on the fixture
clean case and the LUNO slice, checks every frozen criterion and writes only
result.json in the fresh run directory.
"""

import json
import os
import platform
import resource
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np
from rangtoy import core

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "outputs/tv-response-wsl-20261029-01/clean"
TRIAL = FIXTURE / "trials/clean-t2-f32"
FIXTURE_FLAGS = FIXTURE / "backups/clean-t2-f32-solve.npz"
LUNO_ARRAYS = ROOT / "outputs/core-phase2-inputs-20261029-01/arrays.npz"
LUNO_SOLVE = ROOT / "outputs/luno-solve-20261029-02/solve"
LUNO_ARCHIVE = ROOT / "research/results/meerkat-luno-solved.json"
GRID = (2, 32)
GAIN_TOL = 1e-6
LOSS_TOL = 1e-9
TV_TOL = 1e-9
CONV_TOL = 1e-12
COST_SECONDS = 2.0
COST_RSS_MB = 200.0


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def bins(times, nchan):
    integration = np.unique(times, return_inverse=True)[1]
    return integration // GRID[0], np.arange(nchan) // GRID[1]


def compare_gains(rust, qc, qc_flagged):
    """Gain and baseline-product differences on QuartiCal-unflagged gains."""
    rust_flagged = rust.flags != 0
    keep = ~qc_flagged
    gain_diff = np.abs(rust.gains - qc)[keep]
    products = []
    na = qc.shape[2]
    for p in range(na):
        for q in range(p + 1, na):
            pair = keep[..., p] & keep[..., q]
            a = rust.gains[..., p, :, :] @ rust.gains[..., q, :, :].conj().swapaxes(
                -1, -2
            )
            b = qc[..., p, :, :] @ qc[..., q, :, :].conj().swapaxes(-1, -2)
            products.append(np.abs(a - b)[pair])
    products = np.concatenate([x.ravel() for x in products])
    return {
        "flags_equal": bool(np.array_equal(rust_flagged, qc_flagged)),
        "flag_mismatches": int(np.count_nonzero(rust_flagged != qc_flagged)),
        "unflagged_gains": int(keep.sum()),
        "max_abs_gain_entry_diff": float(gain_diff.max()) if gain_diff.size else 0.0,
        "entries_diff_above_1e-10": int(np.count_nonzero(gain_diff > 1e-10)),
        "max_abs_baseline_product_diff": float(products.max())
        if products.size
        else 0.0,
        "iterations": rust.iterations,
        "converged_fraction": rust.converged_fraction,
    }


def gains_pass(c):
    return (
        c["max_abs_gain_entry_diff"] <= GAIN_TOL
        and c["max_abs_baseline_product_diff"] <= GAIN_TOL
    )


def losses_at(data, model, weights, p, q, tb, fb, gains, valid, labels):
    result = core.fused_pass(
        data,
        weights,
        p,
        q,
        tb,
        fb,
        gains,
        valid,
        labels,
        model=model,
        residuals=False,
        scores=False,
        normals=False,
    )
    return result.losses()


def relative(a, b):
    return abs(a - b) / abs(b) if b else abs(a - b)


def fixture():
    from rangtoy.core_policy import gain_tv, polar_gauge

    with np.load(FIXTURE / "state.npz") as z:
        s = {k: z[k] for k in z.files}
    with np.load(FIXTURE_FLAGS) as z:
        flag, flag_row = z["FLAG"], z["FLAG_ROW"]
    with np.load(TRIAL / "diagnostics.npz") as z:
        d = {k: z[k] for k in ("gains", "gain_valid", "gain_times", "gain_frequencies")}
    metrics = json.loads((TRIAL / "metrics.json").read_text())
    tb, fb = bins(s["times"], s["data"].shape[1])
    nt, nf, na = d["gains"].shape[:3]
    started = time.perf_counter()
    rust = core.solve_complex(
        s["data"],
        s["weights"],
        flag,
        flag_row,
        s["antenna1"],
        s["antenna2"],
        tb,
        fb,
        ntime_bins=nt,
        nfreq_bins=nf,
        nant=na,
        model=s["model"],
    )
    seconds = time.perf_counter() - started
    qc_flagged = ~d["gain_valid"]
    comparison = compare_gains(rust, d["gains"], qc_flagged)
    labels = core.split_labels(
        train=s["train"], validation=s["validation"], test=s["test"]
    )
    args = (s["data"], s["model"], s["weights"], s["antenna1"], s["antenna2"], tb, fb)
    rust_valid = (rust.flags == 0) & np.isfinite(rust.gains).all(axis=(-1, -2))
    loss_rust = losses_at(*args, rust.gains, rust_valid, labels)
    loss_qc = losses_at(*args, d["gains"], d["gain_valid"], labels)
    losses = {
        k: {
            "rust": loss_rust[k],
            "quartical": loss_qc[k],
            "archived": metrics["losses"][k],
            "rel": relative(loss_rust[k], loss_qc[k])
            if loss_rust[k] is not None and loss_qc[k] is not None
            else None,
        }
        for k in core.SPLITS
    }
    raw = gain_tv(
        rust.gains,
        rust_valid,
        d["gain_times"],
        d["gain_frequencies"],
        scale=metrics["scale"],
    )
    aligned, tv_valid = polar_gauge(rust.gains, rust_valid)
    polar = gain_tv(
        aligned,
        tv_valid,
        d["gain_times"],
        d["gain_frequencies"],
        scale=metrics["scale"],
    )
    tv = {
        "raw_rust": raw["total"],
        "raw_archived": metrics["raw_tv"],
        "raw_rel": relative(raw["total"], metrics["raw_tv"]),
        "polar_rust": polar["total"],
        "polar_archived": metrics["tv"],
        "polar_rel": relative(polar["total"], metrics["tv"]),
    }
    passed = {
        "1_gain_flags_fixture": comparison["flags_equal"],
        "2_gains_fixture": gains_pass(comparison),
        "4_losses_fixture": all(
            v["rel"] is not None and v["rel"] <= LOSS_TOL for v in losses.values()
        ),
        "5_tv_fixture": tv["raw_rel"] <= TV_TOL and tv["polar_rel"] <= TV_TOL,
    }
    return {
        "inputs": {
            "state_sha256": digest(FIXTURE / "state.npz"),
            "solve_flags_sha256": digest(FIXTURE_FLAGS),
            "diagnostics_sha256": digest(TRIAL / "diagnostics.npz"),
            "metrics_sha256": digest(TRIAL / "metrics.json"),
        },
        "gain_grid": [nt, nf, na],
        "comparison": comparison,
        "criterion_3_reported_not_gated": {
            "iterations": rust.iterations,
            "converged_fraction": rust.converged_fraction,
        },
        "losses": losses,
        "tv": tv,
        "seconds": {"rust_solve": seconds, "quartical_archived": metrics["seconds"]},
        "passed": passed,
    }


def rank_survey(arrays, gains, flags, tb, fb):
    """examples/survey_luno_solved.py's classification, in memory."""
    from rangtoy.core_influence import anchored_response, training_normals

    flag, weight, model = (
        arrays["FLAG"],
        arrays["WEIGHT_SPECTRUM"],
        arrays["MODEL_DATA"],
    )
    a1, a2 = arrays["ANTENNA1"], arrays["ANTENNA2"]
    nt, nf = gains.shape[:2]
    nbins = nt * nf
    g = np.ascontiguousarray(gains.reshape(nbins, 4, 2, 2).astype(np.complex128))
    gf = flags.reshape(nbins, 4) != 0
    train = ~flag.any(-1) & (weight > 0).all(-1) & np.isfinite(model).all(-1)
    rows, channels = np.nonzero(train)
    b = tb[rows] * nf + fb[channels]
    p, q = a1[rows], a2[rows]
    safe = np.where(np.isfinite(g), g, 0)
    models = model[rows, channels].astype(np.complex128).reshape(-1, 2, 2)
    h, _, counts = training_normals(
        safe,
        models,
        np.zeros_like(models),
        weight[rows, channels].astype(np.float64),
        p,
        q,
        b,
    )
    out = {
        "fully_identified": 0,
        "underidentified": 0,
        "no_train": 0,
        "no_solved_gain": 0,
        "over_rank": 0,
        "status": {},
    }
    for k in range(nbins):
        if not counts[k]:
            out["no_train"] += 1
            continue
        sel = b == k
        active = np.zeros(4, bool)
        active[p[sel]] = True
        active[q[sel]] = True
        if gf[k, active].any() or not np.isfinite(g[k, active]).all():
            out["no_solved_gain"] += 1
            continue
        eig = np.linalg.eigvalsh(h[k])
        rank = int(np.sum(eig > 1e-10 * eig[-1])) if eig[-1] > 0 else 0
        required = 8 * int(active.sum()) - 4
        label = (
            "fully_identified"
            if rank == required
            else ("underidentified" if rank < required else "over_rank")
        )
        out[label] += 1
        zero = np.zeros(32)
        status = anchored_response(h[k], zero, 0 * h[k], zero, g[k], active)[
            "native_status"
        ]
        key = f"{label} status{status}"
        out["status"][key] = out["status"].get(key, 0) + 1
    return out


def cost(arrays_path):
    """Minimal workload for criterion 8: load, solve, fused pass."""
    started = time.perf_counter()
    with np.load(arrays_path) as z:
        a = {k: z[k] for k in z.files}
    loaded = time.perf_counter()
    tb, fb = bins(a["TIME"], a["DATA"].shape[1])
    solve_started = time.perf_counter()
    rust = core.solve_complex(
        a["DATA"],
        a["WEIGHT_SPECTRUM"],
        a["FLAG"],
        a["FLAG_ROW"],
        a["ANTENNA1"],
        a["ANTENNA2"],
        tb,
        fb,
        ntime_bins=int(tb.max()) + 1,
        nfreq_bins=int(fb.max()) + 1,
        nant=4,
        model=a["MODEL_DATA"],
    )
    solve_seconds = time.perf_counter() - solve_started
    train = ~a["FLAG"].any(-1) & ~a["FLAG_ROW"][:, None]
    fused_started = time.perf_counter()
    core.fused_pass(
        a["DATA"],
        a["WEIGHT_SPECTRUM"],
        a["ANTENNA1"],
        a["ANTENNA2"],
        tb,
        fb,
        rust.gains,
        rust.flags == 0,
        core.split_labels(train=train),
        model=a["MODEL_DATA"],
        scores=False,
    )
    fused_seconds = time.perf_counter() - fused_started
    print(
        json.dumps(
            {
                "load_seconds": loaded - started,
                "solve_seconds": solve_seconds,
                "fused_seconds": fused_seconds,
                "iterations": rust.iterations,
                "self_maxrss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                / 1024,
            }
        )
    )


def luno():
    with np.load(LUNO_ARRAYS) as z:
        a = {k: z[k] for k in z.files}
    tb, fb = bins(a["TIME"], a["DATA"].shape[1])
    qc = np.load(LUNO_SOLVE / "gains.npy").astype(np.complex128)
    qc_flagged = np.load(LUNO_SOLVE / "gain_flags.npy") != 0
    nt, nf, na = qc.shape[:3]
    archive = json.loads(LUNO_ARCHIVE.read_text())
    started = time.perf_counter()
    rust = core.solve_complex(
        a["DATA"],
        a["WEIGHT_SPECTRUM"],
        a["FLAG"],
        a["FLAG_ROW"],
        a["ANTENNA1"],
        a["ANTENNA2"],
        tb,
        fb,
        ntime_bins=nt,
        nfreq_bins=nf,
        nant=na,
        model=a["MODEL_DATA"],
    )
    seconds = time.perf_counter() - started
    comparison = compare_gains(rust, qc, qc_flagged)
    conv_qc = float(np.asarray(archive["solve_summary"]["conv_perc"]).ravel()[0])
    iter_qc = int(np.asarray(archive["solve_summary"]["conv_iter"]).ravel()[0])
    train = (
        ~a["FLAG"].any(-1)
        & ~a["FLAG_ROW"][:, None]
        & (a["WEIGHT_SPECTRUM"] > 0).all(-1)
        & np.isfinite(a["MODEL_DATA"]).all(-1)
    )
    labels = core.split_labels(train=train)
    args = (
        a["DATA"],
        a["MODEL_DATA"],
        a["WEIGHT_SPECTRUM"],
        a["ANTENNA1"],
        a["ANTENNA2"],
        tb,
        fb,
    )
    rust_valid = (rust.flags == 0) & np.isfinite(rust.gains).all(axis=(-1, -2))
    qc_valid = ~qc_flagged & np.isfinite(qc).all(axis=(-1, -2))
    # Losses over TRAIN cells whose prediction is valid at both gain sets;
    # invalid cells make the frozen loss unavailable, so restrict to them.
    both = rust_valid & qc_valid
    cell_valid = (
        both[tb[:, None], fb[None], a["ANTENNA1"][:, None]]
        & both[tb[:, None], fb[None], a["ANTENNA2"][:, None]]
    )
    labels = core.split_labels(train=train & cell_valid)
    loss_rust = losses_at(*args, rust.gains, rust_valid, labels)["train"]
    loss_qc = losses_at(*args, qc, qc_valid, labels)["train"]
    survey = rank_survey(a, rust.gains, rust.flags, tb, fb)
    env = dict(os.environ)  # the same interpreter, so the same extension
    proc = subprocess.run(
        [
            "/usr/bin/time",
            "-f",
            "%e %M",
            sys.executable,
            str(Path(__file__).resolve()),
            "--cost",
            str(LUNO_ARRAYS),
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    wall, rss_kb = proc.stderr.strip().splitlines()[-1].split()
    workload = json.loads(proc.stdout.strip().splitlines()[-1])
    cost_result = {
        "process_wall_seconds": float(wall),
        "process_max_rss_mb": int(rss_kb) / 1024,
        **workload,
    }
    passed = {
        "1_gain_flags_luno": comparison["flags_equal"],
        "2_gains_luno": gains_pass(comparison),
        "3_iterations_and_convergence_luno": rust.iterations == iter_qc
        and abs(rust.converged_fraction - conv_qc) <= CONV_TOL,
        "4_losses_luno": loss_rust is not None
        and loss_qc is not None
        and relative(loss_rust, loss_qc) <= LOSS_TOL,
        "6_rank_survey_luno": survey["fully_identified"] == 389
        and survey["underidentified"] == 43
        and survey["no_train"] == 592
        and survey["status"]
        == {"fully_identified status0": 389, "underidentified status3": 43},
        "8_cost_luno": workload["solve_seconds"] <= COST_SECONDS
        and cost_result["process_max_rss_mb"] <= COST_RSS_MB,
    }
    return {
        "inputs": {
            "arrays_sha256": digest(LUNO_ARRAYS),
            "gains_sha256": digest(LUNO_SOLVE / "gains.npy"),
            "gain_flags_sha256": digest(LUNO_SOLVE / "gain_flags.npy"),
        },
        "gain_grid": [nt, nf, na],
        "comparison": comparison,
        "quartical": {
            "iterations": iter_qc,
            "converged_fraction": conv_qc,
            "seconds_archived": archive["solve_summary"]["seconds"],
        },
        "losses": {
            "rust": loss_rust,
            "quartical": loss_qc,
            "rel": relative(loss_rust, loss_qc) if loss_rust and loss_qc else None,
            "train_cells_valid_at_both": int((train & cell_valid).sum()),
        },
        "rank_survey": survey,
        "seconds": {"rust_solve_in_validator": seconds},
        "cost": cost_result,
        "passed": passed,
    }


def snapshot():
    files = [
        FIXTURE / "state.npz",
        FIXTURE_FLAGS,
        *sorted(TRIAL.glob("*.*")),
        LUNO_ARRAYS,
        *sorted(LUNO_SOLVE.glob("*.npy")),
        LUNO_ARCHIVE,
    ]
    stats = {
        p.relative_to(ROOT).as_posix(): [p.stat().st_size, p.stat().st_mtime_ns]
        for p in files
        if p.is_file()
    }
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return stats, status


def main():
    if sys.argv[1:2] == ["--cost"]:
        cost(sys.argv[2])
        return
    out = Path(sys.argv[1])
    if not str(out).startswith("outputs/"):
        raise SystemExit("output directory must be beneath outputs/")
    out.mkdir(parents=True, exist_ok=False)
    library = core.library_path()
    before = snapshot()
    result = {
        "protocol": "research/core-phase2.md",
        "fixture": fixture(),
        "luno": luno(),
    }
    after = snapshot()
    result["side_effects"] = {
        "input_files_checked": len(before[0]),
        "inputs_unchanged": before[0] == after[0],
        "git_status_unchanged": before[1] == after[1],
        "run_dir_empty_before_receipt": sorted(p.name for p in out.iterdir()) == [],
    }
    passed = result["fixture"]["passed"] | result["luno"]["passed"]
    passed["7_no_side_effects"] = all(result["side_effects"].values())
    result.update(
        {
            "passed": dict(sorted(passed.items())),
            "all_passed": all(passed.values()),
            "library_sha256": digest(library),
            "code_sha256": {
                p.relative_to(ROOT).as_posix(): digest(p)
                for p in sorted((ROOT / "core/src").glob("*.rs"))
                + [
                    ROOT / "core/Cargo.toml",
                    ROOT / "python/rangtoy/core.py",
                    Path(__file__).resolve(),
                ]
            },
            "python": platform.python_version(),
            "numpy": np.__version__,
        }
    )
    (out / "result.json").write_text(json.dumps(result, indent=1, default=float) + "\n")
    print(json.dumps({"all_passed": result["all_passed"], **result["passed"]}))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
