"""Bounded gain-only controls; native full-Jones TV remains the objective.

These synthetic gain perturbations do not estimate actual solved-real gain
uncertainty. Calibrations are conditional on the grid and legitimate trend.
No visibility truth, held-out visibility features or Measurement Sets are read.
"""

from hashlib import sha256
from pathlib import Path

import numpy as np

from .flagging import axis_weights, fixed_support_tv, gain_tv, polar_gauge
from .flagging_workflow import write_json
from .projector import _native_library

GRIDS = ((4, 32), (8, 64))
TRENDS = ("flat", "smooth", "rapid")
SEEDS = {
    "train": tuple(range(101, 111)),
    "validation": tuple(range(111, 116)),
    "test": tuple(range(116, 121)),
}
KINDS = ("raw_tv", "detrended_tv", "curvature_tv")


def _station_map(values):
    return values.transpose(0, 2, 1).reshape(-1, values.shape[1])


def _smooth_trend(gains, times, frequencies):
    """Tiny fixed four-column control fit, not a general physical gain solver."""
    t = (times - np.mean(times)) / max(np.ptp(times), 1)
    f = (frequencies - np.mean(frequencies)) / max(np.ptp(frequencies), 1)
    tt, ff = np.broadcast_arrays(t[:, None], f[None, :])
    design = np.column_stack(
        (np.ones(tt.size), tt.ravel(), ff.ravel(), (tt * ff).ravel())
    )
    trend = np.zeros_like(gains)
    amplitude_floor = 0.01 * np.median(np.abs(np.diagonal(gains, axis1=-2, axis2=-1)))
    for antenna in range(gains.shape[2]):
        for row in range(2):
            for column in range(2):
                entry = gains[:, :, antenna, row, column]
                amplitude = np.abs(entry)
                if np.median(amplitude) < amplitude_floor:
                    continue
                if np.any(amplitude <= 1e-12):
                    raise ValueError("trend phase is undefined on supported gains")
                phase = np.unwrap(np.unwrap(np.angle(entry), axis=1), axis=0)
                coefficients = np.linalg.lstsq(
                    design,
                    np.column_stack((np.log(amplitude).ravel(), phase.ravel())),
                    rcond=None,
                )[0]
                fitted = (design @ coefficients).reshape(*entry.shape, 2)
                trend[:, :, antenna, row, column] = np.exp(
                    fitted[..., 0] + 1j * fitted[..., 1]
                )
    return trend


def gain_evidence(gains, valid, times, frequencies, *, scale=1.0, unpolarized=True):
    """Raw primary TV plus descriptive trend/curvature guidance on full support."""
    gains = np.asarray(gains, complex)
    valid = np.asarray(valid)
    times, frequencies = np.asarray(times, float), np.asarray(frequencies, float)
    if (
        gains.ndim != 5
        or gains.shape[-2:] != (2, 2)
        or valid.shape != gains.shape[:3]
        or valid.dtype != np.bool_
        or min(gains.shape[:2]) < 3
        or np.prod(gains.shape[:3]) > 65536
        or not valid.all()
        or not np.isfinite(gains).all()
    ):
        raise ValueError("bounded full finite gain support required; no interpolation")
    if unpolarized is not True:
        raise ValueError("polar gauge requires explicit scalar-unpolarized model")
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("positive fixed gain scale required")
    for coordinates, size in zip((times, frequencies), gains.shape[:2]):
        if coordinates.shape != (size,) or np.any(axis_weights(coordinates) <= 0):
            raise ValueError("complete coordinate edge support required")
    aligned, supported = polar_gauge(gains, valid)
    if not supported.all():
        raise ValueError("singular gauge reference; full support unavailable")
    raw = gain_tv(aligned, supported, times, frequencies, scale=scale)
    trend = _smooth_trend(aligned, times, frequencies)
    residual = aligned - trend
    detrended = gain_tv(residual, supported, times, frequencies, scale=scale)
    if fixed_support_tv(detrended["edges"], raw["edges"]) is None:
        raise ValueError("detrended baseline edge support lost")
    curvature, count = np.zeros(valid.shape), np.zeros(valid.shape)
    for axis in (0, 1):
        difference = np.diff(residual, axis=axis)
        coordinates = [times, frequencies]
        coordinates[axis] = (coordinates[axis][:-1] + coordinates[axis][1:]) / 2
        evidence = gain_tv(
            difference,
            np.ones(difference.shape[:3], bool),
            *coordinates,
            scale=scale,
        )
        lower, upper = [slice(None)] * 3, [slice(None)] * 3
        lower[axis], upper[axis] = slice(None, -1), slice(1, None)
        for index in (tuple(lower), tuple(upper)):
            curvature[index] += evidence["map"]
            count[index] += 1
    curvature /= count
    return {
        "tv": raw["total"],
        "detrended_tv": detrended["total"],
        "raw_edges": raw["edges"],
        "detrended_edges": detrended["edges"],
        "maps": {
            "raw_tv": _station_map(raw["map"]),
            "detrended_tv": _station_map(detrended["map"]),
            "curvature_tv": _station_map(curvature),
        },
        "full_support": True,
        "gauge": "polar; explicitly scalar-unpolarized control",
        "scale": float(scale),
    }


def calibrate_guidance(controls, *, grid_key, trend_key):
    """Condition on one grid/trend, using exclusively no-RFI TRAIN controls."""
    if not controls:
        raise ValueError("no-RFI TRAIN controls required")
    selected = {kind: [] for kind in KINDS}
    for control in controls:
        train = np.asarray(control["train"])
        if (
            control.get("split") != "train"
            or control.get("stress", "none") != "none"
            or control.get("grid_key") != grid_key
            or control.get("trend_key") != trend_key
            or not control.get("full_support", False)
            or train.ndim != 2
            or train.dtype != np.bool_
            or not train.any()
        ):
            raise ValueError(
                "matched no-RFI TRAIN-only full-support calibration required"
            )
        for kind in KINDS:
            values = np.asarray(control["maps"][kind], float)
            if values.shape != train.shape or not np.isfinite(values[train]).all():
                raise ValueError("finite matched TRAIN calibration map required")
            selected[kind].append(values[train])
    statistics = {}
    for kind, parts in selected.items():
        values = np.concatenate(parts)
        center = float(np.median(values))
        statistics[kind] = {
            "median": center,
            "scale": max(float(1.4826 * np.median(np.abs(values - center))), 1e-6),
            "threshold": float(np.quantile(values, 0.95)),
            "train_count": len(values),
        }
    return {
        "grid_key": grid_key,
        "trend_key": trend_key,
        "statistics": statistics,
        "full_support": True,
        "control_count": len(controls),
        "calibration_source": "synthetic gain-only no-RFI TRAIN controls",
        "real_solved_uncertainty_estimate": False,
    }


def excess_guidance(
    state,
    guidance,
    calibration,
    *,
    grid_key,
    trend_key,
    curvature=None,
    evidence_kind="detrended_tv",
):
    """Return standardized positive excess and an audit, identically zero off TRAIN."""
    train = np.asarray(state["train"])
    if train.ndim != 2 or train.dtype != np.bool_ or evidence_kind not in KINDS:
        raise ValueError("bool TRAIN and recognized evidence kind required")
    if (
        calibration.get("grid_key") != grid_key
        or calibration.get("trend_key") != trend_key
        or not calibration.get("full_support", False)
    ):
        raise ValueError("unknown or mismatched calibration domain/support; refused")

    def standardized(values, kind):
        values = np.asarray(values, float)
        stats = calibration["statistics"][kind]
        if (
            values.shape != train.shape
            or not np.isfinite(values[train]).all()
            or np.any(values[train] < 0)
            or not np.isfinite([stats["threshold"], stats["scale"]]).all()
            or stats["scale"] <= 0
        ):
            raise ValueError(
                "finite nonnegative TRAIN evidence and calibration required"
            )
        result = np.zeros(train.shape)
        result[train] = np.clip(
            (values[train] - stats["threshold"]) / stats["scale"], 0, 5
        )
        return result

    result = standardized(guidance, evidence_kind)
    if curvature is not None:
        result = np.minimum(result, standardized(curvature, "curvature_tv"))
    return result, {
        "train_only": True,
        "zero_outside_train": True,
        "grid_key": grid_key,
        "trend_key": trend_key,
        "evidence_kind": evidence_kind,
        "curvature_required_too": curvature is not None,
        "primary_full2x2_TV_objective_unchanged": True,
        "real_uncertainty_or_RFI_classifier_validated": False,
    }


def _control(grid, trend, seed, stress="none"):
    nt, nf = grid
    times = np.linspace(0, 112, nt)
    frequencies = np.linspace(1070e6, 1497.791015625e6, nf)
    time = (times - np.mean(times)) / np.ptp(times)
    frequency = frequencies - np.mean(frequencies)
    multiplier = {"flat": 0, "smooth": 1, "rapid": 2}[trend]
    delay = multiplier * (
        np.array([0, 3, 6, 9])[None, :] * 1e-9
        + time[:, None] * np.array([0, 0.3, -0.3, 0.5])[None, :] * 1e-9
    )
    logamp = multiplier * time[:, None] * np.array([0, 0.04, -0.04, 0.08])[None]
    diagonal = np.exp(
        logamp[:, None, :] + 2j * np.pi * frequency[None, :, None] * delay[:, None, :]
    )
    gains = np.zeros((nt, nf, 4, 2, 2), complex)
    gains[..., 0, 0], gains[..., 1, 1] = diagonal, diagonal
    if stress == "jump":
        gains[nt // 2 :, :, 1] *= 1.15 * np.exp(0.75j)
    sigma = 0.05 if stress == "noise" else 0.005
    rng = np.random.default_rng(seed)
    gains += (
        sigma
        / np.sqrt(2)
        * (rng.normal(size=gains.shape) + 1j * rng.normal(size=gains.shape))
    )
    train = np.random.default_rng(seed + 1000000).random((nt * 4, nf)) < 0.8
    return gains, np.ones(gains.shape[:3], bool), times, frequencies, train


def run(run_dir):
    """Exclusive synthetic control run callable from Stimela2; never writes an MS."""
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "backups").mkdir()
    library = Path(_native_library()._name)
    config = {
        "grids": GRIDS,
        "seeds": SEEDS,
        "trends": TRENDS,
        "scale": 1.0,
        "noise_RMS": 0.005,
        "stress_noise_RMS": 0.05,
        "jump": {"antenna": 1, "phase_rad": 0.75, "voltage_factor": 1.15},
        "delay_ns": [0, 3, 6, 9],
        "delay_time_change_ns": [0, 0.3, -0.3, 0.5],
        "logamp_slopes": [0, 0.04, -0.04, 0.08],
        "rapid_multiplier": 2,
        "calibration_quantile": 0.95,
        "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "native_library_sha256": sha256(library.read_bytes()).hexdigest(),
        "gain_only_not_actual_QuartiCal_solutions": True,
        "no_measurement_set_or_original_flags_written": True,
    }
    write_json(run_dir / "config.json", config)
    calibration, records, training = {}, [], {}

    def measure(grid, trend, seed, split, stress="none"):
        grid_key = f"t{grid[0]}-f{grid[1]}"
        label = f"{grid_key}-{trend}-s{seed}-{stress}"
        gains, valid, times, frequencies, train = _control(grid, trend, seed, stress)
        with (run_dir / "backups" / f"{label}-original.npz").open("xb") as stream:
            np.savez_compressed(
                stream, gains=gains, valid=valid, times=times, frequencies=frequencies
            )
        evidence = gain_evidence(gains, valid, times, frequencies)
        record = {
            "label": label,
            "grid_key": grid_key,
            "trend_key": trend,
            "seed": seed,
            "split": split,
            "stress": stress,
            "full_support": evidence["full_support"],
            "tv": evidence["tv"],
            "detrended_tv": evidence["detrended_tv"],
            "map_train_medians": {
                k: float(np.median(v[train])) for k, v in evidence["maps"].items()
            },
        }
        key = f"{grid_key}/{trend}"
        if split == "train":
            training.setdefault(key, []).append(
                {**record, "maps": evidence["maps"], "train": train}
            )
        else:
            excess, audit = excess_guidance(
                {"train": train},
                evidence["maps"]["detrended_tv"],
                calibration[key],
                grid_key=grid_key,
                trend_key=trend,
                curvature=evidence["maps"]["curvature_tv"],
            )
            record["positive_excess_train_fraction"] = float(np.mean(excess[train] > 0))
            record["mean_excess_train"] = float(np.mean(excess[train]))
            record["audit"] = audit
        records.append(record)
        write_json(run_dir / f"checkpoint-{label}.json", record)

    for grid in GRIDS:
        for trend in TRENDS:
            for seed in SEEDS["train"]:
                measure(grid, trend, seed, "train")
            key = f"t{grid[0]}-f{grid[1]}/{trend}"
            calibration[key] = calibrate_guidance(
                training[key], grid_key=key.split("/")[0], trend_key=trend
            )
    # Frozen before any validation/test controls, with no threshold tuning.
    write_json(run_dir / "calibration.json", calibration)
    for split in ("validation", "test"):
        for grid in GRIDS:
            for trend in TRENDS:
                for seed in SEEDS[split]:
                    measure(grid, trend, seed, split)
                    if split == "test":
                        for stress in ("noise", "jump"):
                            measure(grid, trend, seed, split, stress)
    result = {
        "configuration": config,
        "calibration": calibration,
        "records": records,
        "count": len(records),
        "audit": {
            "thresholds_frozen_before_validation_test": True,
            "per_grid_and_physical_trend_calibration": True,
            "native_Rust_full2x2_all_norms": True,
            "original_MS_FLAGS_DATA_weights_not_touched": True,
        },
        "limitations": "Synthetic gain-only controls, not QC-solved-real uncertainty or a proven RFI classifier. Independent noise realizations, not independent observations; empirical excess thresholds have no calibrated coverage guarantee. Full-support/trend/domain assumptions are strict. Raw native full2x2 TV remains the primary objective; descriptive guidance alone never flags data.",
    }
    write_json(run_dir / "result.json", result)
    return str(run_dir / "result.json")
