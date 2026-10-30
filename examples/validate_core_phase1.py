"""Validate phase 1 of the Rang core against frozen oracles (research/core-phase1.md).

Usage: python examples/validate_core_phase1.py outputs/<fresh-run-dir>

Reads the fixture clean case and the LUNO solved slice named in the protocol,
runs the fused Rust pass, compares every frozen criterion and writes
result.json in the fresh run directory. Writes nothing else.
"""

import json
import platform
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np
from rang import core
from rang.core_influence import training_normals
from rang.core_policy import residual_features

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "outputs/tv-response-wsl-20261029-01/clean"
TRIAL = FIXTURE / "trials/clean-t2-f32"
LUNO_EXTRACT = ROOT / "outputs/luno-support-20261029-01/extract/group1"
LUNO_SOLVE = ROOT / "outputs/luno-solve-20261029-02/solve"
GRID = (2, 32)
TOL = {"residual": 1e-12, "loss": 1e-12, "score": 1e-12, "normals": 1e-13}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def rel(a, b):
    """Maximum entry difference over the maximum oracle entry."""
    a, b = np.asarray(a), np.asarray(b)
    scale = float(np.max(np.abs(b))) if b.size else 0.0
    return (
        float(np.max(np.abs(a - b)) / scale)
        if scale > 0
        else float(np.max(np.abs(a - b)))
    )


def bins(times, nchan):
    integration = np.unique(times, return_inverse=True)[1]
    return integration // GRID[0], np.arange(nchan) // GRID[1]


def compare_normals(gains, models, residuals, weights, p, q, tb, fb, nf, cells, fused):
    """Full 32x32 blocks from the existing kernel on the selected cells."""
    rows, chans = np.nonzero(cells)
    bin_ids = tb[rows] * nf + fb[chans]
    flat = gains.reshape(-1, 4, 2, 2)
    safe = np.where(np.isfinite(flat), flat, 0)
    h, b, counts = training_normals(
        safe,
        models[rows, chans].astype(np.complex128).reshape(-1, 2, 2),
        residuals[rows, chans].reshape(-1, 2, 2),
        weights[rows, chans].astype(np.float64),
        p[rows],
        q[rows],
        bin_ids,
    )
    nbins = flat.shape[0]
    diag_h = fused.diag_h.reshape(nbins, 4, 8, 8)
    diag_b = fused.diag_b.reshape(nbins, 4, 8)
    full_diag = np.stack(
        [h[:, 8 * a : 8 * a + 8, 8 * a : 8 * a + 8] for a in range(4)], 1
    )
    full_b = b.reshape(nbins, 4, 8)
    return (
        h,
        b,
        counts,
        {
            "diag_h_rel": rel(diag_h, full_diag),
            "diag_b_rel": rel(diag_b, full_b),
            "cells": int(cells.sum()),
            "bins_with_cells": int(np.count_nonzero(counts)),
        },
    )


def fixture():
    with np.load(FIXTURE / "state.npz") as z:
        state = {k: z[k] for k in z.files}
    with np.load(TRIAL / "diagnostics.npz") as z:
        diag = {k: z[k] for k in ("gains", "gain_valid", "residuals")}
    metrics = json.loads((TRIAL / "metrics.json").read_text())
    tb, fb = bins(state["times"], state["data"].shape[1])
    nf = diag["gains"].shape[1]
    labels = core.split_labels(
        train=state["train"], validation=state["validation"], test=state["test"]
    )
    started = time.perf_counter()
    fused = core.fused_pass(
        state["data"],
        state["weights"],
        state["antenna1"],
        state["antenna2"],
        tb,
        fb,
        diag["gains"],
        diag["gain_valid"],
        labels,
        model=state["model"],
    )
    fused_seconds = time.perf_counter() - started
    # The NumPy path this replaces: prediction and residual, then split MSE.
    started = time.perf_counter()
    p, q = state["antenna1"], state["antenna2"]
    gp = diag["gains"][tb[:, None], fb[None], p[:, None]]
    gq = diag["gains"][tb[:, None], fb[None], q[:, None]]
    model = state["model"].reshape(*state["model"].shape[:2], 2, 2)
    reference = state["data"] - (gp @ model @ gq.conj().swapaxes(-1, -2)).reshape(
        state["data"].shape
    )
    mse = np.mean(np.abs(reference) ** 2 * state["weights"], axis=-1)
    numpy_losses = {s: float(np.mean(mse[state[s]])) for s in core.SPLITS}
    numpy_seconds = time.perf_counter() - started
    archived = diag["residuals"]
    nan_same = bool(np.array_equal(np.isnan(fused.residuals), np.isnan(archived)))
    finite = np.isfinite(archived)
    abs_diff = np.abs(fused.residuals[finite] - archived[finite])
    big = np.abs(archived[finite]) > 1e-6
    residual = {
        "max_abs_jy": float(abs_diff.max()),
        "max_rel_where_above_1e-6": float(
            (abs_diff[big] / np.abs(archived[finite][big])).max()
        ),
        "nan_positions_equal": nan_same,
        "numpy_recomputed_max_abs_jy": float(
            np.max(np.abs(reference - archived)[finite])
        ),
    }
    losses = fused.losses()
    loss = {
        name: {
            "fused": losses[name],
            "archived": metrics["losses"][name],
            "rel": abs(losses[name] - metrics["losses"][name])
            / abs(metrics["losses"][name])
            if losses[name] is not None and metrics["losses"][name]
            else None,
        }
        for name in core.SPLITS
    }
    invalid_equal = fused.invalid_predictions() == metrics["invalid_predictions"]
    z_oracle = residual_features(
        archived * np.sqrt(state["weights"]), state["train"], p, q
    )
    score = {"max_abs": float(np.max(np.abs(fused.scores - z_oracle)))}
    valid_cells = (
        diag["gain_valid"][tb[:, None], fb[None], p[:, None]]
        & diag["gain_valid"][tb[:, None], fb[None], q[:, None]]
    )
    cells = state["train"] & valid_cells
    h_fused, b_fused, _, normals = compare_normals(
        diag["gains"],
        state["model"],
        fused.residuals,
        state["weights"],
        p,
        q,
        tb,
        fb,
        nf,
        cells,
        fused,
    )
    rows, chans = np.nonzero(cells)
    flat = diag["gains"].reshape(-1, 4, 2, 2)
    h_arch, b_arch, _ = training_normals(
        np.where(np.isfinite(flat), flat, 0),
        state["model"][rows, chans].astype(np.complex128).reshape(-1, 2, 2),
        archived[rows, chans].reshape(-1, 2, 2),
        state["weights"][rows, chans].astype(np.float64),
        p[rows],
        q[rows],
        tb[rows] * nf + fb[chans],
    )
    normals.update(
        {"full_h_rel": rel(h_fused, h_arch), "full_b_rel": rel(b_fused, b_arch)}
    )
    # Post-hoc criterion 4b (research/core-phase1.md): b = J^T W r cancels at a
    # converged solution, so compare |db_i| with the Cauchy-Schwarz bound
    # |b_i| <= sqrt(H_ii chi2_bin), chi2_bin = sum of w|r|^2 over the bin's cells.
    chi2 = np.bincount(
        tb[rows] * nf + fb[chans],
        weights=np.sum(
            state["weights"][rows, chans] * np.abs(archived[rows, chans]) ** 2, -1
        ),
        minlength=h_arch.shape[0],
    )
    bound = np.sqrt(np.diagonal(h_arch, axis1=1, axis2=2) * chi2[:, None])
    positive = bound > 0
    normals["b_over_cauchy_schwarz_bound_max"] = float(
        np.max(np.abs(b_fused - b_arch)[positive] / bound[positive])
    )
    normals["max_abs_b_archived"] = float(np.max(np.abs(b_arch)))
    normals["max_cauchy_schwarz_bound"] = float(np.max(bound))
    passed = {
        "1_residuals": residual["max_abs_jy"] <= TOL["residual"]
        and residual["max_rel_where_above_1e-6"] <= TOL["residual"]
        and nan_same,
        "2_losses": all(
            v["rel"] is not None and v["rel"] <= TOL["loss"] for v in loss.values()
        )
        and invalid_equal,
        "3_scores": score["max_abs"] <= TOL["score"],
        "4_normals_from_fused_residuals": normals["full_h_rel"] <= TOL["normals"]
        and normals["full_b_rel"] <= TOL["normals"],
        "4b_posthoc_b_against_cauchy_schwarz_bound": normals["full_h_rel"]
        <= TOL["normals"]
        and normals["b_over_cauchy_schwarz_bound_max"] <= TOL["normals"],
        "5_diagonal_blocks_fixture": normals["diag_h_rel"] <= TOL["normals"]
        and normals["diag_b_rel"] <= TOL["normals"],
    }
    return {
        "inputs": {
            "state_sha256": digest(FIXTURE / "state.npz"),
            "diagnostics_sha256": digest(TRIAL / "diagnostics.npz"),
            "metrics_sha256": digest(TRIAL / "metrics.json"),
        },
        "shape": list(state["data"].shape),
        "gain_grid": list(diag["gains"].shape[:3]),
        "residual": residual,
        "losses": loss,
        "invalid_predictions_equal": invalid_equal,
        "numpy_losses_recomputed": numpy_losses,
        "scores": score,
        "normals": normals,
        "seconds": {
            "fused_pass": fused_seconds,
            "numpy_residual_and_mse": numpy_seconds,
        },
        "passed": passed,
    }


def luno():
    arrays = {
        n: np.load(LUNO_EXTRACT / f"{n}.npy")
        for n in ("antenna1", "antenna2", "time", "flag", "weight", "model")
    }
    gains = np.load(LUNO_SOLVE / "gains.npy").astype(np.complex128)
    gain_flags = np.load(LUNO_SOLVE / "gain_flags.npy") != 0
    valid = ~gain_flags & np.isfinite(gains).all(axis=(-1, -2))
    tb, fb = bins(arrays["time"], arrays["flag"].shape[1])
    nf = gains.shape[1]
    train = (
        ~arrays["flag"].any(-1)
        & (arrays["weight"] > 0).all(-1)
        & np.isfinite(arrays["model"]).all(-1)
    )
    labels = core.split_labels(train=train)
    zero = np.zeros(arrays["model"].shape, np.complex64)
    started = time.perf_counter()
    fused = core.fused_pass(
        zero,
        arrays["weight"],
        arrays["antenna1"],
        arrays["antenna2"],
        tb,
        fb,
        gains,
        valid,
        labels,
        model=arrays["model"],
        scores=False,
    )
    fused_seconds = time.perf_counter() - started
    p, q = arrays["antenna1"], arrays["antenna2"]
    cells = (
        train
        & valid[tb[:, None], fb[None], p[:, None]]
        & valid[tb[:, None], fb[None], q[:, None]]
    )
    started = time.perf_counter()
    _, _, _, normals = compare_normals(
        gains,
        arrays["model"],
        fused.residuals,
        arrays["weight"],
        p,
        q,
        tb,
        fb,
        nf,
        cells,
        fused,
    )
    normals_seconds = time.perf_counter() - started
    return {
        "inputs": {
            name: digest(LUNO_EXTRACT / f"{name}.npy")
            for name in ("antenna1", "antenna2", "time", "flag", "weight", "model")
        }
        | {
            "gains_sha256": digest(LUNO_SOLVE / "gains.npy"),
            "gain_flags_sha256": digest(LUNO_SOLVE / "gain_flags.npy"),
        },
        "shape": list(arrays["model"].shape),
        "gain_grid": list(gains.shape[:3]),
        "normals": normals,
        "seconds": {
            "fused_pass": fused_seconds,
            "existing_kernel_normals_incl_prep": normals_seconds,
        },
        "passed": {
            "5_diagonal_blocks_luno": normals["diag_h_rel"] <= TOL["normals"]
            and normals["diag_b_rel"] <= TOL["normals"]
        },
    }


def snapshot():
    files = sorted(FIXTURE.glob("*.npz")) + sorted(TRIAL.glob("*"))
    files += sorted(LUNO_EXTRACT.glob("*.npy")) + sorted(LUNO_SOLVE.glob("*.npy"))
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
    out = Path(sys.argv[1])
    if not str(out).startswith("outputs/"):
        raise SystemExit("output directory must be beneath outputs/")
    out.mkdir(parents=True, exist_ok=False)
    library = core.library_path()
    before = snapshot()
    result = {
        "protocol": "research/core-phase1.md",
        "tolerances": TOL,
        "fixture": fixture(),
        "luno": luno(),
        "library_sha256": digest(library),
        "code_sha256": {
            p.relative_to(ROOT).as_posix(): digest(p)
            for p in sorted((ROOT / "core/src").glob("*.rs"))
            + [
                ROOT / "core/Cargo.toml",
                ROOT / "python/rang/core.py",
                Path(__file__).resolve(),
            ]
        },
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    passed = result["fixture"]["passed"] | result["luno"]["passed"]
    after = snapshot()
    result["side_effects"] = {
        "input_files_checked": len(before[0]),
        "inputs_unchanged": before[0] == after[0],
        "git_status_unchanged": before[1] == after[1],
        "run_dir_empty_before_receipt": sorted(p.name for p in out.iterdir()) == [],
    }
    passed["6_no_side_effects"] = all(result["side_effects"].values())
    result["passed"] = passed
    result["all_passed"] = all(passed.values())
    result["all_passed_with_posthoc_4b"] = all(
        v for k, v in passed.items() if k != "4_normals_from_fused_residuals"
    )
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    print(
        json.dumps(
            {
                "all_passed": result["all_passed"],
                "all_passed_with_posthoc_4b": result["all_passed_with_posthoc_4b"],
                **passed,
            }
        )
    )
    if not result["all_passed_with_posthoc_4b"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
