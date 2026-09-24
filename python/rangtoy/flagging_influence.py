"""Retrospective TRAIN-only full-Jones deletion response, not an RFI classifier.

Rust computes weighted Jacobians, normal equations and gauge-aware GN steps.
Validation DATA scores already-frozen gain forecasts. Actual action outcomes
are opened only after every forecast is serialized. Injection truth and TEST
values never enter curvature, forecasts, fitting, rankings or output metrics.
"""

import ctypes
import json
import os
import shutil
import sys
import time
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

import numpy as np

from .flagging import fixed_support_tv, gain_tv, polar_gauge
from .flagging_prepared import reject_nested_paths
from .flagging_workflow import tree_digest, write_json
from .projector import _native_library

RESERVE_BYTES = 8 * 1024**3
DERIVED_LIMIT_BYTES = 256 * 1024**2

CASE_IDS = (
    "balanced-clean",
    "time-burst-seed101",
    "antenna-local-seed101",
    "time-burst-seed103",
    "antenna-local-seed103",
    "time-burst-seed105",
    "antenna-local-seed105",
)
INFO = (
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
REASONS = {
    1: "invalid/numerical block",
    2: "native panic",
    3: "underidentified full curvature",
    4: "retained rank loss",
    5: "non-PSD curvature",
    6: "U2 gauge-null mismatch",
}


@lru_cache(maxsize=1)
def _functions():
    lib = _native_library()
    real = np.ctypeslib.ndpointer(dtype=np.float64, flags=("C_CONTIGUOUS", "ALIGNED"))
    integer = np.ctypeslib.ndpointer(dtype=np.uintp, flags=("C_CONTIGUOUS", "ALIGNED"))
    byte = np.ctypeslib.ndpointer(dtype=np.uint8, flags=("C_CONTIGUOUS", "ALIGNED"))
    jac, normal, step = (
        lib.rang_response_jacobian,
        lib.rang_response_normals,
        lib.rang_response_step,
    )
    jac.argtypes = [real] * 4
    normal.argtypes = (
        [ctypes.c_size_t] * 2 + [real] * 4 + [integer] * 3 + [real] * 2 + [integer]
    )
    step.argtypes = [real] * 5 + [byte] + [real] * 2
    for fn in (jac, normal, step):
        fn.restype = ctypes.c_int
    return jac, normal, step


def _complex(value, shape):
    array = np.require(value, dtype=np.complex128, requirements=["C", "A"])
    if array.shape != shape:
        raise ValueError(f"complex shape {shape} required")
    return array


def jones_jacobian(gp, gq, model):
    """Eight Re/Im visibility rows × sixteen local p-then-q parameters."""
    inputs = [_complex(x, (2, 2)).view(np.float64).ravel() for x in (gp, gq, model)]
    if not all(np.isfinite(x).all() for x in inputs):
        raise ValueError("finite Jones matrices required")
    output = np.empty((8, 16))
    if _functions()[0](*inputs, output):
        raise RuntimeError("native Jones Jacobian failed")
    return output


def training_normals(gains, models, residuals, weights, p, q, bin_ids):
    """Caller supplies TRAIN samples only; weights are never replaced/scaled."""
    gains = np.require(gains, dtype=np.complex128, requirements=["C", "A"])
    if gains.ndim != 4 or gains.shape[1:] != (4, 2, 2) or not len(gains):
        raise ValueError("gain bins × four stations × 2×2 required")
    ids = []
    for value in (p, q, bin_ids):
        raw = np.asarray(value)
        if raw.ndim != 1 or raw.dtype.kind not in "iu" or np.any(raw < 0):
            raise ValueError("nonnegative integer sample indices required")
        ids.append(np.require(raw, dtype=np.uintp, requirements=["C", "A"]))
    p, q, bins = ids
    n = len(bins)
    model, residual = [_complex(x, (n, 2, 2)) for x in (models, residuals)]
    weight = np.require(weights, dtype=np.float64, requirements=["C", "A"])
    if (
        p.shape != bins.shape
        or q.shape != bins.shape
        or weight.shape != (n, 4)
        or np.any(p >= 4)
        or np.any(q >= 4)
        or np.any(p == q)
        or np.any(bins >= len(gains))
    ):
        raise ValueError("sample/baseline/bin shape or range mismatch")
    if (
        not np.isfinite(model).all()
        or not np.isfinite(residual).all()
        or not np.isfinite(weight).all()
        or np.any(weight <= 0)
    ):
        raise ValueError(
            "finite samples and positive native four-correlation weights required"
        )
    h, b, counts = (
        np.zeros((len(gains), 32, 32)),
        np.zeros((len(gains), 32)),
        np.zeros(len(gains), dtype=np.uintp),
    )
    status = _functions()[1](
        n,
        len(gains),
        gains.view(np.float64),
        model.view(np.float64),
        residual.view(np.float64),
        weight,
        p,
        q,
        bins,
        h,
        b,
        counts,
    )
    if status:
        raise RuntimeError(f"native TRAIN normals failed: {status}")
    return h, b, counts


def anchored_response(full_h, full_b, drop_h, drop_b, gains, active):
    """Return a horizontal gain delta or a structured missing prediction."""
    arrays = []
    for value, shape in zip(
        (full_h, full_b, drop_h, drop_b),
        ((32, 32), (32,), (32, 32), (32,)),
        strict=True,
    ):
        raw = np.asarray(value)
        if np.iscomplexobj(raw) or raw.shape != shape or not np.isfinite(raw).all():
            raise ValueError("finite real 32D normal block required")
        arrays.append(np.require(raw, dtype=np.float64, requirements=["C", "A"]))
    active = np.asarray(active)
    if active.dtype != np.bool_ or active.shape != (4,):
        raise ValueError("four bool active-station values required")
    gain = _complex(gains, (4, 2, 2)).copy()
    if not np.isfinite(gain[active]).all():
        raise ValueError("finite active-station gains required")
    gain[~active] = 0
    delta, info = np.zeros(32), np.full(10, np.nan)
    status = _functions()[2](
        *arrays,
        gain.view(np.float64),
        np.require(active, dtype=np.uint8, requirements=["C", "A"]),
        delta,
        info,
    )
    audit = {
        key: float(value) if np.isfinite(value) else None
        for key, value in zip(INFO, info, strict=True)
    }
    trust = status == 0 and audit["max_relative_step"] <= 0.1
    return {
        "delta": delta.view(np.complex128).reshape(4, 2, 2) if trust else None,
        "diagnostics": audit,
        "guard_pass": trust,
        "reason": None
        if trust
        else REASONS.get(status, "relative station step exceeds 0.1"),
        "native_status": status,
    }


def _npz(path, keys=None):
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in (archive.files if keys is None else keys)}


def _capacity(output, estimated=0):
    if any(path.is_symlink() for path in Path(output).rglob("*")):
        raise RuntimeError("symlinks forbidden in derived namespace")
    existing = sum(p.stat().st_size for p in Path(output).rglob("*") if p.is_file())
    if existing + estimated >= DERIVED_LIMIT_BYTES:
        raise RuntimeError("derived namespace would exceed 256MiB")
    if shutil.disk_usage(output).free < RESERVE_BYTES + estimated:
        raise RuntimeError("8GiB disk reserve would be violated")


def _json(path, value):
    encoded = json.dumps(value, allow_nan=False).encode()
    _capacity(Path(path).parent, len(encoded) * 2 + 4096)
    write_json(path, value)


def _runtime_receipts():
    modules = (sys.modules[__name__],) + tuple(
        sys.modules[name]
        for name in (
            "rangtoy",
            "rangtoy.flagging",
            "rangtoy.flagging_prepared",
            "rangtoy.flagging_workflow",
            "rangtoy.projector",
        )
    )
    root = Path(__file__).resolve().parents[2]
    native = Path(_native_library()._name).resolve()
    files = {module.__name__: Path(module.__file__).resolve() for module in modules}
    files.update(
        {
            "Rust.response": root / "src/response.rs",
            "Rust.linalg": root / "src/linalg.rs",
            "Rust.lib": root / "src/lib.rs",
            "Rust.tv": root / "src/tv.rs",
            "native_library": native,
        }
    )
    return {
        key: {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
        for key, path in files.items()
    }


def _maps(state):
    time_map = np.unique(state["times"], return_inverse=True)[1] // 2
    return time_map, np.arange(len(state["frequencies"])) // 32


def _predict(state, gains, mask):
    rows, channels = np.where(mask)
    tm, fm = _maps(state)
    gp = gains[tm[rows], fm[channels], state["antenna1"][rows]]
    gq = gains[tm[rows], fm[channels], state["antenna2"][rows]]
    prediction = (
        gp
        @ state["model"][rows, channels].reshape(-1, 2, 2)
        @ gq.conj().swapaxes(-1, -2)
    ).reshape(-1, 4)
    return rows, channels, prediction


def _training_bundle(state, baseline):
    train = state["train"]
    shape = state["data"].shape[:2]
    if (
        state["data"].shape != (*shape, 4)
        or state["model"].shape != (*shape, 4)
        or state["weights"].shape != (*shape, 4)
    ):
        raise ValueError("four-correlation DATA/model/native weights required")
    if (
        state["original_flags"].dtype != np.bool_
        or state["original_flags"].shape != (*shape, 4)
        or state["original_rows"].dtype != np.bool_
        or state["original_rows"].shape != (shape[0],)
        or state["window"].dtype != np.bool_
        or state["window"].shape != (shape[1],)
    ):
        raise ValueError("bool original flags/rows/window shapes required")
    splits = [state[key] for key in ("train", "validation", "test")]
    if any(x.dtype != np.bool_ or x.shape != shape for x in splits) or any(
        np.any(splits[i] & splits[j]) for i in range(3) for j in range(i)
    ):
        raise ValueError("bool disjoint TRAIN/validation/test shapes required")
    protected = (
        state["original_flags"].any(axis=2)
        | state["original_rows"][:, None]
        | (state["antenna1"] == state["antenna2"])[:, None]
        | ~state["window"][None, :]
    )
    if np.any(train & protected) or not train.any():
        raise ValueError("TRAIN overlaps original flags/rows/autos/window")
    rows, channels, prediction = _predict(state, baseline["gains"], train)
    tm, fm = _maps(state)
    valid = (
        baseline["gain_valid"][tm[rows], fm[channels], state["antenna1"][rows]]
        & baseline["gain_valid"][tm[rows], fm[channels], state["antenna2"][rows]]
    )
    if not valid.all():
        raise ValueError("TRAIN baseline gain support missing")
    models = state["model"][rows, channels].reshape(-1, 2, 2)
    if (
        not np.isfinite(models).all()
        or not np.array_equal(models[:, 0, 0], models[:, 1, 1])
        or np.any(models[:, 0, 1] != 0)
        or np.any(models[:, 1, 0] != 0)
    ):
        raise ValueError("scalar unpolarized TRAIN model required for U2 gauge")
    residuals = (state["data"][rows, channels] - prediction).reshape(-1, 2, 2)
    return {
        "gains": baseline["gains"].reshape(-1, 4, 2, 2),
        "models": models,
        "residuals": residuals,
        "weights": state["weights"][rows, channels],
        "p": state["antenna1"][rows],
        "q": state["antenna2"][rows],
        "bin_ids": tm[rows] * baseline["gains"].shape[1] + fm[channels],
        "flat_indices": np.flatnonzero(train),
    }


def forecast_case(path, cache_path=None):
    """Forecast frozen actions without opening result.json or action metrics."""
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text())
    if (
        manifest["split_gain_intervals"] != [2, 32]
        or manifest["scope"]["telescope"].casefold() != "meerkat"
        or manifest["scope"]["band"] != "L"
    ):
        raise ValueError("frozen MeerKAT L-band grid 2×32 required")
    state = _npz(path / "state.npz")
    baseline = _npz(
        path / "trials/baseline/diagnostics.npz",
        ("gains", "gain_valid", "edges", "gain_times", "gain_frequencies"),
    )
    metrics = json.loads((path / "trials/baseline/metrics.json").read_text())
    frozen = json.loads((path / "frozen-rankings.json").read_text())
    candidates = {}
    for mode in ("residual", "tv", "random"):
        for item in frozen["rankings"][mode]:
            candidates.setdefault(item["mask_id"], item)
    actions = _npz(path / "backups/frozen-actions.npz")
    bundle = _training_bundle(state, baseline)
    full_start = time.perf_counter()
    full_h, full_b, _ = training_normals(
        **{k: v for k, v in bundle.items() if k != "flat_indices"}
    )
    full_seconds = time.perf_counter() - full_start
    records, canonical_forecasts, raw_forecasts = [], [], []
    canonical_baseline, baseline_tv_valid = polar_gauge(
        baseline["gains"], baseline["gain_valid"]
    )
    for index, candidate in enumerate(candidates.values()):
        indices = actions[f"action_{index}"]
        if (
            sha256(indices.astype("<i8").tobytes()).hexdigest() != candidate["mask_id"]
            or len(indices) != candidate["sample_count"]
            or not 8 <= len(indices) <= int(0.02 * state["train"].sum())
            or candidate["added_fraction"] != len(indices) / state["train"].sum()
        ):
            raise ValueError("frozen action indices/count/SHA mismatch")
        positions = np.searchsorted(bundle["flat_indices"], indices)
        if np.any(positions >= len(bundle["flat_indices"])) or not np.array_equal(
            bundle["flat_indices"][positions], indices
        ):
            raise ValueError("action contains non-TRAIN cells")
        drop = {
            k: v[positions]
            for k, v in bundle.items()
            if k not in ("gains", "flat_indices")
        }
        start = time.perf_counter()
        drop_h, drop_b, _ = training_normals(bundle["gains"], **drop)
        predicted = baseline["gains"].copy().reshape(-1, 4, 2, 2)
        bin_audits = []
        for bin_id in np.unique(drop["bin_ids"]):
            active = np.array(
                [
                    np.trace(full_h[bin_id, i * 8 : (i + 1) * 8, i * 8 : (i + 1) * 8])
                    > 0
                    for i in range(4)
                ]
            )
            response = anchored_response(
                full_h[bin_id],
                full_b[bin_id],
                drop_h[bin_id],
                drop_b[bin_id],
                bundle["gains"][bin_id],
                active,
            )
            bin_audits.append(
                {
                    "bin_id": int(bin_id),
                    **{k: v for k, v in response.items() if k != "delta"},
                }
            )
            if response["guard_pass"]:
                predicted[bin_id] += response["delta"]
        native_seconds = time.perf_counter() - start
        guard = all(x["guard_pass"] for x in bin_audits)
        record = {
            "mask_id": candidate["mask_id"],
            "candidate": candidate,
            "bin_audits": bin_audits,
            "native_response_seconds": native_seconds,
            "guard_pass": guard,
            "reason": None if guard else "curvature/trust block abstention",
        }
        canonical = np.full_like(canonical_baseline, complex(np.nan, np.nan))
        if guard:
            predicted = predicted.reshape(baseline["gains"].shape)
            aligned, valid = polar_gauge(predicted, baseline["gain_valid"])
            canonical = aligned
            tv = gain_tv(
                aligned,
                valid,
                baseline["gain_times"],
                baseline["gain_frequencies"],
                scale=metrics["scale"],
            )
            support = fixed_support_tv(tv["edges"], baseline["edges"])
            record["predicted_fixed_tv"] = support
            if support is None:
                record.update({"guard_pass": False, "reason": "fixed TV support lost"})
        records.append(record)
        canonical_forecasts.append(canonical)
        raw_forecasts.append(
            predicted.reshape(baseline["gains"].shape)
            if guard
            else np.full_like(baseline["gains"], complex(np.nan, np.nan))
        )
    if cache_path is not None:
        payload = np.stack(canonical_forecasts)
        _capacity(
            Path(cache_path).parent,
            2 * payload.nbytes + canonical_baseline.nbytes + 4096,
        )
        with Path(cache_path).open("xb") as stream:
            np.savez_compressed(
                stream,
                predicted_gauge_gains=payload,
                raw_predicted_gains=np.stack(raw_forecasts),
                baseline_gauge_gains=canonical_baseline,
                baseline_tv_valid=baseline_tv_valid,
            )
    return {
        "baseline_tv": metrics["tv"],
        "baseline_validation_MSE": metrics["losses"]["validation"],
        "full_training_normals_seconds": full_seconds,
        "records": records,
        "frozen_ranking_ids": {
            k: [x["mask_id"] for x in v] for k, v in frozen["rankings"].items()
        },
    }


def _score_validation(path, forecast, cache_path):
    """Only called after all seven TRAIN response caches/JSON are frozen."""
    state = _npz(Path(path) / "state.npz")
    cache = _npz(cache_path, ("raw_predicted_gains",))
    for index, record in enumerate(forecast["records"]):
        if not record["guard_pass"]:
            continue
        rows, channels, prediction = _predict(
            state, cache["raw_predicted_gains"][index], state["validation"]
        )
        val = float(
            np.mean(
                np.mean(
                    np.abs(state["data"][rows, channels] - prediction) ** 2
                    * state["weights"][rows, channels],
                    axis=-1,
                )
            )
        )
        if not np.isfinite(val) or val > 1.01 * forecast["baseline_validation_MSE"]:
            record.update({"guard_pass": False, "reason": "validation guard"})
            continue
        objective = (
            record["predicted_fixed_tv"] / forecast["baseline_tv"]
            + 2 * record["candidate"]["added_fraction"]
            + 0.25 * val / forecast["baseline_validation_MSE"]
        )
        record.update(
            {
                "predicted_validation_MSE": val,
                "predicted_objective": objective,
                "predicted_benefit": 1.25 - objective,
                "predicted_cost_removed_benefit": 1.25
                - objective
                + 2 * record["candidate"]["added_fraction"],
            }
        )


def run(run_dir, source_dir="outputs/tv-concurrent-20260924-01"):
    """Exclusive derived-only retrospective run; never write a measured source."""
    if Path(run_dir).is_symlink():
        raise ValueError("derived destination cannot be a symlink")
    output, source = reject_nested_paths(run_dir, source_dir)
    outputs_root = Path(__file__).resolve().parents[2] / "outputs"
    if (
        not source.is_dir()
        or not output.is_relative_to(outputs_root.resolve())
        or output.exists()
    ):
        raise ValueError("stable source and fresh destination beneath outputs required")
    if shutil.disk_usage(outputs_root).free < RESERVE_BYTES + DERIVED_LIMIT_BYTES:
        raise RuntimeError("8GiB reserve plus 256MiB derived allowance required")
    digest = tree_digest(source)
    receipts = _runtime_receipts()
    output.mkdir(parents=True, exist_ok=False)
    _json(
        output / "config.json",
        {
            "source": str(source),
            "source_digest": digest,
            "case_ids": CASE_IDS,
            "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "runtime_receipts": receipts,
            "suite_image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
            "derived_limit_bytes": DERIVED_LIMIT_BYTES,
            "budget_accounting": "checked logical regular-file bytes/prospective reservation; not an OS-enforced quota",
            "disk_reserve_bytes": RESERVE_BYTES,
            "damping_relative": 1e-6,
            "rank_relative": 1e-10,
            "relative_station_step_limit": 0.1,
            "anchor": "masked GN minus full GN in baseline U2-horizontal gauge",
            "labels_opened_after_all_forecasts": True,
            "truth_test_values_used": False,
            "retrospective_same_observation": True,
            "native_vs_emulated_speedup_claim": False,
        },
    )
    forecasts = {
        name: forecast_case(
            source / "experiments" / name, output / f"gain-forecasts-{name}.npz"
        )
        for name in CASE_IDS
    }
    _json(output / "frozen-train-responses.json", forecasts)
    for name, forecast in forecasts.items():
        _score_validation(
            source / "experiments" / name,
            forecast,
            output / f"gain-forecasts-{name}.npz",
        )
    _json(output / "frozen-forecasts.json", forecasts)
    # No outcome fitting/selection occurred before the complete forecast freeze.
    comparisons = []
    for name, forecast in forecasts.items():
        raw = json.loads((source / "experiments" / name / "result.json").read_text())
        actual = {x["mask_id"]: x for x in raw["actions"]}
        cache = _npz(output / f"gain-forecasts-{name}.npz")
        for index, record in enumerate(forecast["records"]):
            action = actual[record["mask_id"]]
            label = (
                1.25 - action["objective"]
                if action.get("guard_pass") and action.get("objective") is not None
                else None
            )
            canonical_diagnostics = None
            if record.get("predicted_benefit") is not None:
                actual_gains = _npz(
                    source
                    / "experiments"
                    / name
                    / "trials"
                    / action["metrics"]["trial"]
                    / "diagnostics.npz",
                    ("gauge_gains", "tv_valid"),
                )
                common = cache["baseline_tv_valid"] & actual_gains["tv_valid"]
                actual_change = (
                    actual_gains["gauge_gains"] - cache["baseline_gauge_gains"]
                )[common]
                predicted_change = (
                    cache["predicted_gauge_gains"][index]
                    - cache["baseline_gauge_gains"]
                )[common]
                an, pn = (
                    float(np.linalg.norm(actual_change)),
                    float(np.linalg.norm(predicted_change)),
                )
                canonical_diagnostics = {
                    "common_gain_cells": int(common.sum()),
                    "actual_change_norm": an,
                    "predicted_change_norm": pn,
                    "change_relative_error": float(
                        np.linalg.norm(predicted_change - actual_change)
                        / max(an, 1e-30)
                    ),
                    "change_cosine": float(
                        np.vdot(actual_change, predicted_change).real
                        / max(an * pn, 1e-30)
                    ),
                }
            comparisons.append(
                {
                    "case_id": name,
                    **record,
                    "actual_guard_pass": action.get("guard_pass", False),
                    "canonical_gain_change": canonical_diagnostics,
                    "actual_benefit": label,
                    "actual_cost_removed_benefit": label
                    + 2 * record["candidate"]["added_fraction"]
                    if label is not None
                    else None,
                    "known_flag_cost_prediction": -2
                    * record["candidate"]["added_fraction"],
                }
            )
    train = [
        x
        for x in comparisons
        if x["case_id"].endswith("101") and x["actual_benefit"] is not None
    ]
    design = np.array(
        [[1.0, np.log1p(x["candidate"]["residual_score"])] for x in train]
    )
    targets = np.array([x["actual_benefit"] for x in train])
    coefficients = np.linalg.lstsq(design, targets, rcond=1e-10)[0]
    for record in comparisons:
        record["TRAIN101_mean_prediction"] = float(targets.mean())
        record["TRAIN101_residual_linear_prediction"] = float(
            np.array([1.0, np.log1p(record["candidate"]["residual_score"])])
            @ coefficients
        )
    summary = {}
    for group, suffix in (
        ("clean", "clean"),
        ("train", "101"),
        ("validation", "103"),
        ("test_case_group_retrospective", "105"),
    ):
        rows = [
            r
            for r in comparisons
            if r["case_id"].endswith(suffix) and r["actual_benefit"] is not None
        ]
        covered = [r for r in rows if r.get("predicted_benefit") is not None]
        summary[group] = {
            "labels": len(rows),
            "covered": len(covered),
            "abstentions": len(rows) - len(covered),
            "matched_coverage_RMSE": {
                key: float(
                    np.sqrt(
                        np.mean([(r[key] - r["actual_benefit"]) ** 2 for r in covered])
                    )
                )
                if covered
                else None
                for key in (
                    "predicted_benefit",
                    "known_flag_cost_prediction",
                    "TRAIN101_mean_prediction",
                    "TRAIN101_residual_linear_prediction",
                )
            },
            "matched_coverage_cost_removed_RMSE": {
                "physics_response": float(
                    np.sqrt(
                        np.mean(
                            [
                                (
                                    r["predicted_cost_removed_benefit"]
                                    - r["actual_cost_removed_benefit"]
                                )
                                ** 2
                                for r in covered
                            ]
                        )
                    )
                )
                if covered
                else None,
                "known_flag_cost_zero_response": float(
                    np.sqrt(
                        np.mean(
                            [r["actual_cost_removed_benefit"] ** 2 for r in covered]
                        )
                    )
                )
                if covered
                else None,
            },
            "all_label_flag_cost_RMSE": float(
                np.sqrt(
                    np.mean(
                        [
                            (r["known_flag_cost_prediction"] - r["actual_benefit"]) ** 2
                            for r in rows
                        ]
                    )
                )
            )
            if rows
            else None,
        }
    rankings = {}
    rng = np.random.default_rng(137)
    for name in CASE_IDS:
        rows = [r for r in comparisons if r["case_id"] == name]
        predicted = [
            r
            for r in rows
            if r.get("predicted_benefit") is not None
            and r["guard_pass"]
            and r["predicted_benefit"] > 0
        ]
        physics = (
            min(
                predicted,
                key=lambda r: (
                    -r["predicted_benefit"],
                    r["candidate"]["added_fraction"],
                    r["mask_id"],
                ),
            )
            if predicted
            else None
        )
        residual = min(
            rows, key=lambda r: (-r["candidate"]["residual_score"], r["mask_id"])
        )
        random = sorted(rows, key=lambda r: r["mask_id"])[int(rng.integers(len(rows)))]
        optimum = max(
            [0.0]
            + [r["actual_benefit"] for r in rows if r["actual_benefit"] is not None]
        )
        rankings[name] = {
            key: {
                "mask_id": row["mask_id"] if row else None,
                "actual_benefit": row["actual_benefit"] if row else 0.0,
                "regret": optimum - row["actual_benefit"]
                if row and row["actual_benefit"] is not None
                else optimum,
                "requires_actual_guarded_confirmation": True,
            }
            for key, row in (
                ("physics", physics),
                ("residual_first", residual),
                ("seed137_random_first", random),
                ("known_cost_no_change", None),
            )
        }
    unchanged = tree_digest(source) == digest
    runtime_unchanged = _runtime_receipts() == receipts
    if not unchanged or not runtime_unchanged:
        raise RuntimeError("saved source changed during response experiment")
    result = {
        "comparisons": comparisons,
        "summary": summary,
        "retrospective_one_slot_rankings_on_existing_union": rankings,
        "TRAIN101_residual_coefficients": coefficients.tolist(),
        "source_unchanged": unchanged,
        "runtime_unchanged": runtime_unchanged,
        "actual_labels": len(comparisons),
        "injection_truth_test_values_used": False,
        "limitations": "One-step GN deletion response, not a full calibration re-solve. Existing outcomes and case seeds are retrospective on one four-station scan. Abstentions remain missing. No RFI truth, TEST visibility loss, MS/flag writes, new QC solves, deployment, imaging, independent-transfer or fair-runtime/SOTA claims.",
    }
    _json(output / "result.json", result)
    _capacity(output)
    return result
