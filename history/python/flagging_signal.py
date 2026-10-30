"""Paired full-Jones flagging/calibration response to evaluation-only faint sky.

Frozen direction-independent simulation, not MeerKAT image/morphology validation.
Source templates never enter a policy feature, gain-model column or selector.
"""

import json
import os
import shutil
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import numpy as np

from .flagging import (
    fixed_support_tv,
    policy_mask,
    protected_flags,
    residual_features,
    snapshot_flags,
)
from .flagging_caracal import _native_run, score_control, strategy_provenance
from .flagging_comparators import mad_proposal
from .flagging_prepared import reject_nested_paths, validate_prepared_state
from .flagging_workflow import load_state, set_flags, solve, tree_digest, write_json

REFERENCE_HZ = 1283791015.625
ARCMIN = np.pi / 10800
SOURCES = (
    {
        "name": "compact",
        "flux_jy": 0.05,
        "l_arcmin": 12.0,
        "m_arcmin": 8.0,
        "fwhm_arcmin": 0.0,
        "spectral_index": -0.7,
    },
    {
        "name": "extended",
        "flux_jy": 0.1,
        "l_arcmin": -15.0,
        "m_arcmin": 10.0,
        "fwhm_arcmin": 10.0,
        "spectral_index": -1.0,
    },
)
THRESHOLDS = (8.0, 5.0, 3.0)
TV_WEIGHTS = (0.0, 1.0, 3.0)
INVERSE_CONDITION_LIMIT = 1e8


def spatial_templates(uvw, frequencies, sources=SOURCES):
    """Bounded independent NumPy CASA-sign DFT and circular-Gaussian FT.

    l/m are direction cosines scaled by the arcminute-to-radian factor, not RA
    and declination differences. Gaussian shape uses the usual tangent-plane
    Fourier transform; its central noncoplanar phase includes w(n-1).
    """
    uvw, frequencies = np.asarray(uvw, float), np.asarray(frequencies, float)
    if uvw.ndim != 2 or uvw.shape[1] != 3 or frequencies.ndim != 1:
        raise ValueError("UVW(row,3) and frequency(channel) required")
    if (
        not np.isfinite(uvw).all()
        or not np.isfinite(frequencies).all()
        or np.any(frequencies <= 0)
    ):
        raise ValueError("finite coordinates and positive frequencies required")
    result = []
    wavelength_uv = uvw[:, :2, None] * frequencies[None, None] / 299792458
    for source in sources:
        l, m = source["l_arcmin"] * ARCMIN, source["m_arcmin"] * ARCMIN
        width = source["fwhm_arcmin"] * ARCMIN
        if not np.isfinite([l, m, width]).all() or l * l + m * m >= 1 or width < 0:
            raise ValueError(
                "finite small source direction and nonnegative width required"
            )
        distance = uvw @ [l, m, np.sqrt(1 - l * l - m * m) - 1]
        phase = np.exp(2j * np.pi / 299792458 * distance[:, None] * frequencies)
        shape = np.exp(
            -(np.pi**2) * width**2 / (4 * np.log(2)) * np.sum(wavelength_uv**2, axis=1)
        )
        result.append(phase * shape)
    return np.asarray(result)


def intrinsic_signal(templates, frequencies, sources=SOURCES):
    templates, frequencies = np.asarray(templates), np.asarray(frequencies, float)
    if templates.shape[0] != len(sources) or templates.shape[-1] != len(frequencies):
        raise ValueError("source template and frequency shapes differ")
    return sum(
        source["flux_jy"]
        * templates[i]
        * (frequencies / REFERENCE_HZ) ** source["spectral_index"]
        for i, source in enumerate(sources)
    )


def _sample_gains(state, diagnostics, intervals):
    ti, fi = intervals
    times = np.unique(state["times"], return_inverse=True)[1] // ti
    channels = np.arange(len(state["frequencies"])) // fi
    p, q = state["antenna1"], state["antenna2"]
    gains, flags = diagnostics["gains"], diagnostics["gain_valid"]
    gp = gains[times[:, None], channels[None], p[:, None]]
    gq = gains[times[:, None], channels[None], q[:, None]]
    valid = (
        flags[times[:, None], channels[None], p[:, None]]
        & flags[times[:, None], channels[None], q[:, None]]
    )
    valid &= np.isfinite(gp).all(axis=(-1, -2)) & np.isfinite(gq).all(axis=(-1, -2))
    return gp, gq, valid


def corrected_intensity(data, gp, gq, gain_valid, native_weights):
    """Gauge-invariant Stokes-I trace and original-weight variance propagation.

    Independent native correlation noises with complex variance 1/WEIGHT are a
    diagnostic assumption, not a calibrated noise model. Paired differences
    share the same noisy input, so their variance is not the sum of two variances.
    """
    data, native_weights = np.asarray(data), np.asarray(native_weights, float)
    gp, gq = np.asarray(gp), np.asarray(gq)
    valid = np.asarray(gain_valid, bool).copy()
    if (
        data.shape[-1] != 4
        or data.shape != native_weights.shape
        or gp.shape != (*data.shape[:2], 2, 2)
        or gq.shape != gp.shape
        or valid.shape != data.shape[:2]
    ):
        raise ValueError(
            "four correlations and matched per-sample Jones/weights required"
        )
    valid &= (
        np.isfinite(data).all(axis=-1)
        & np.isfinite(native_weights).all(axis=-1)
        & (native_weights > 0).all(axis=-1)
    )
    valid &= np.isfinite(gp).all(axis=(-1, -2)) & np.isfinite(gq).all(axis=(-1, -2))
    # Invalid matrices are never inverted or silently included in a fit.
    safe_p = np.where(valid[..., None, None], gp, np.eye(2))
    safe_q = np.where(valid[..., None, None], gq, np.eye(2))
    valid &= (np.linalg.cond(safe_p) <= INVERSE_CONDITION_LIMIT) & (
        np.linalg.cond(safe_q) <= INVERSE_CONDITION_LIMIT
    )
    safe_p = np.where(valid[..., None, None], gp, np.eye(2))
    safe_q = np.where(valid[..., None, None], gq, np.eye(2))
    inverse_p, inverse_q = np.linalg.inv(safe_p), np.linalg.inv(safe_q)
    coefficients = 0.5 * (inverse_q.conj().swapaxes(-1, -2) @ inverse_p).swapaxes(
        -1, -2
    ).reshape(data.shape)
    intensity = np.sum(coefficients * data, axis=-1)
    variance = np.sum(
        np.abs(coefficients) ** 2 / np.where(native_weights > 0, native_weights, 1),
        axis=-1,
    )
    valid &= np.isfinite(intensity) & np.isfinite(variance) & (variance > 0)
    return np.where(valid, intensity, np.nan), np.where(valid, variance, np.nan), valid


def fit_signal(intensity, templates, frequencies, weights, mask, sources=SOURCES):
    """Evaluation-only joint real flux/power-law fit at known locations/extents.

    This is template recovery with a known family, not blind source detection.
    No samples are dropped for having negative/noisy recovered brightness.
    """
    from scipy.optimize import least_squares

    intensity, templates = np.asarray(intensity), np.asarray(templates)
    weights, mask = np.asarray(weights, float), np.asarray(mask)
    frequencies = np.asarray(frequencies, float)
    if (
        mask.dtype != np.bool_
        or mask.shape != intensity.shape
        or weights.shape != intensity.shape
        or templates.shape != (len(sources), *intensity.shape)
    ):
        raise ValueError(
            "matched complex template/intensity and bool evaluation mask required"
        )
    if (
        intensity.ndim != 2
        or frequencies.shape != (intensity.shape[1],)
        or mask.sum() < 2 * len(sources)
    ):
        raise ValueError("nonempty row-channel evaluation support required")
    if (
        not np.isfinite(intensity[mask]).all()
        or not np.isfinite(templates[:, mask]).all()
        or not np.isfinite(weights[mask]).all()
        or np.any(weights[mask] <= 0)
    ):
        raise ValueError("invalid evaluation samples must not be silently discarded")
    log_nu = np.broadcast_to(np.log(frequencies / REFERENCE_HZ), intensity.shape)[mask]
    spatial = templates[:, mask]
    target = intensity[mask]
    root_weights = np.sqrt(weights[mask])
    count = len(sources)

    def residual(parameters):
        spectrum = np.exp(parameters[count:, None] * log_nu)
        model = np.sum(parameters[:count, None] * spatial * spectrum, axis=0)
        delta = (model - target) * root_weights
        return np.concatenate((delta.real, delta.imag))

    def jacobian(parameters):
        vectors = spatial * np.exp(parameters[count:, None] * log_nu) * root_weights
        derivatives = np.concatenate(
            (vectors, vectors * parameters[:count, None] * log_nu), axis=0
        ).T
        return np.concatenate((derivatives.real, derivatives.imag), axis=0)

    flux = np.array([source["flux_jy"] for source in sources])
    alpha = np.array([source["spectral_index"] for source in sources])
    initial = np.r_[flux, alpha]
    scale = np.r_[flux, np.ones(count)]
    fit = least_squares(
        residual,
        initial,
        jac=jacobian,
        x_scale=scale,
        bounds=(
            np.r_[np.full(count, -1.0), np.full(count, -5.0)],
            np.r_[np.full(count, 1.0), np.full(count, 3.0)],
        ),
        max_nfev=100,
        ftol=1e-11,
        xtol=1e-11,
        gtol=1e-11,
    )
    singular = np.linalg.svd(jacobian(fit.x) * scale, compute_uv=False)
    rank = int(np.count_nonzero(singular > singular[0] * 1e-10)) if singular.size else 0
    condition = (
        float(singular[0] / singular[-1])
        if singular.size and singular[-1] > 0
        else None
    )
    supported = bool(
        fit.success and rank == 2 * count and condition is not None and condition <= 1e8
    )
    return {
        "available": supported,
        "optimizer_success": bool(fit.success),
        "rank": rank,
        "scaled_jacobian_condition": condition,
        "sample_count": int(mask.sum()),
        "weighted_fit_mse_proxy": float(np.mean(np.abs(residual(fit.x)) ** 2) * 2),
        "function_evaluations": int(fit.nfev),
        "parameters_at_bounds": bool(np.any(fit.active_mask)),
        "sources": [
            {
                "name": source["name"],
                "input_flux_jy": source["flux_jy"],
                "recovered_flux_jy": float(fit.x[i]) if supported else None,
                "flux_fraction": float(fit.x[i] / source["flux_jy"])
                if supported
                else None,
                "input_spectral_index": source["spectral_index"],
                "recovered_spectral_index": float(fit.x[count + i])
                if supported
                else None,
                "spectral_index_error": float(
                    fit.x[count + i] - source["spectral_index"]
                )
                if supported
                else None,
            }
            for i, source in enumerate(sources)
        ],
        "confidence_intervals": "not claimed: conditional template fit and correlated solve/input noise",
    }


def select_policy(records, family):
    """Selector accepts objective/guard/mask identity only, no source or test truth."""
    pool = [
        record
        for record in records
        if family in record["families"]
        and record["guard_pass"]
        and record["objective"] is not None
        and np.isfinite(record["objective"])
    ]
    if not pool:
        raise ValueError("no-change must be present in each policy family")
    return min(
        pool,
        key=lambda record: (
            record["objective"],
            record["added_count"],
            record["mask_id"],
        ),
    )["mask_id"]


def _diagnostics(directory):
    with np.load(Path(directory) / "diagnostics.npz", allow_pickle=False) as saved:
        return {name: saved[name] for name in ("gains", "gain_valid", "edges")}


def _stage(source, destination):
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("state.npz", "manifest.json"):
        shutil.copy2(source / name, destination / name)
    for name in ("original.ms", "work.ms"):
        shutil.copytree(source / name, destination / name)
    state = load_state(destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    return state, manifest, validate_prepared_state(destination, state, manifest)


def _prediction_and_injection(root, clean, injected, state, diagnostics, manifest):
    from africanus.rime import wsclean_predict
    from casacore.tables import table

    injected_state, injected_manifest, boundary = _stage(clean, injected)
    with table(
        str(clean / "work.ms"), readonly=True, ack=False, lockoptions="autonoread"
    ) as work:
        uvw = work.getcol("UVW")
    templates = spatial_templates(uvw, state["frequencies"])
    expected = intrinsic_signal(templates, state["frequencies"])
    lm = (
        np.array([[source["l_arcmin"], source["m_arcmin"]] for source in SOURCES])
        * ARCMIN
    )
    shapes = np.array(
        [
            [source["fwhm_arcmin"] * ARCMIN, source["fwhm_arcmin"] * ARCMIN, 0]
            for source in SOURCES
        ]
    )
    predicted = wsclean_predict(
        uvw,
        lm,
        np.array(["POINT", "GAUSSIAN"]),
        np.array([s["flux_jy"] for s in SOURCES]),
        np.array([[s["spectral_index"]] for s in SOURCES]),
        np.ones(len(SOURCES), bool),
        np.full(len(SOURCES), REFERENCE_HZ),
        shapes,
        state["frequencies"],
    )[..., 0]
    np.testing.assert_allclose(predicted, expected, rtol=1e-11, atol=1e-12)
    gp, gq, good = _sample_gains(state, diagnostics, manifest["split_gain_intervals"])
    eligible = state["train"] | state["validation"] | state["test"]
    if np.any(eligible & ~good):
        raise ValueError(
            "fixed clean gains do not support every frozen injection sample"
        )
    coherency = predicted[..., None, None] * np.eye(2)
    delta = (gp @ coherency @ gq.conj().swapaxes(-1, -2)).reshape(state["data"].shape)
    delta = np.where(eligible[..., None], delta, 0)
    shutil.copytree(injected / "work.ms", injected / "backups/work-before-signal.ms")
    shutil.copy2(injected / "state.npz", injected / "backups/state-before-signal.npz")
    with table(str(injected / "work.ms"), readonly=False, ack=False) as work:
        snapshot_flags(
            injected / "backups/signal-before-flags.npz",
            work.getcol("FLAG"),
            work.getcol("FLAG_ROW"),
        )
        work.putcol("DATA", (state["data"] + delta).astype(state["data"].dtype))
        work.flush()
        injected_state["data"] = work.getcol("DATA")
        snapshot_flags(
            injected / "backups/signal-after-flags.npz",
            work.getcol("FLAG"),
            work.getcol("FLAG_ROW"),
        )
    if not np.array_equal(
        injected_state["data"][~eligible], state["data"][~eligible], equal_nan=True
    ):
        raise RuntimeError("signal injection changed protected DATA")
    actual_delta = np.where(
        eligible[..., None], injected_state["data"] - state["data"], 0
    )
    if not np.array_equal(injected_state["model"], state["model"]):
        raise RuntimeError("signal injection changed protected DATA or calibration sky")
    # This saved truth is not decoded again until after frozen policy selections.
    with (root / "signal-truth.npz").open("xb") as stream:
        np.savez_compressed(
            stream, templates=templates, injected=eligible, actual_delta=actual_delta
        )
    with (injected / "state.npz").open("wb") as stream:
        np.savez_compressed(stream, **injected_state)
    boundary_after = validate_prepared_state(
        injected, injected_state, injected_manifest
    )
    write_json(
        root / "signal-injection.json",
        {
            "sources": list(SOURCES),
            "reference_frequency_hz": REFERENCE_HZ,
            "scope": "intrinsic scalar sky, zero beam/pointing, empirical fixed clean full-Jones DI corruption",
            "predictor": "Africanus wsclean_predict; full bounded NumPy DFT/Gaussian reference verified",
            "max_prediction_reference_error_jy": float(
                np.max(np.abs(predicted - expected))
            ),
            "native_complex_dtype": str(state["data"].dtype),
            "gain_reference_trial": "clean/trials/baseline",
            "injected_samples": int(eligible.sum()),
            "split_counts": {
                name: int(state[name].sum()) for name in ("train", "validation", "test")
            },
            "calibration_sky_unchanged": True,
            "signal_truth_used_for_selection": False,
            "input_boundary": boundary,
            "injected_boundary": boundary_after,
            "data_rounding_linf_jy": float(np.max(np.abs(actual_delta - delta))),
            "truth_sha256": sha256(
                (root / "signal-truth.npz").read_bytes()
            ).hexdigest(),
        },
    )
    return injected_state, injected_manifest


def _mask_identity(mask):
    return sha256(np.ascontiguousarray(mask, dtype=bool).tobytes()).hexdigest()


def _export(directory, state, mask, label):
    from casacore.tables import table

    set_flags(directory, state, mask, label, holdout=False)
    flags, rows = protected_flags(
        state["original_flags"],
        state["original_rows"],
        np.broadcast_to(mask[..., None], state["original_flags"].shape),
    )
    with table(
        str(directory / "work.ms"), readonly=True, ack=False, lockoptions="autonoread"
    ) as work:
        if (
            not np.array_equal(work.getcol("FLAG"), flags)
            or not np.array_equal(work.getcol("FLAG_ROW"), rows)
            or not np.array_equal(work.getcol("DATA"), state["data"], equal_nan=True)
        ):
            raise RuntimeError("paired export DATA/FLAG/FLAG_ROW mismatch")
    with (
        table(
            str(directory / "original.ms"),
            readonly=True,
            ack=False,
            lockoptions="autonoread",
        ) as original,
        table(
            str(directory / "work.ms"),
            readonly=True,
            ack=False,
            lockoptions="autonoread",
        ) as work,
    ):
        columns = [
            name
            for name in ("WEIGHT", "WEIGHT_SPECTRUM", "SIGMA", "SIGMA_SPECTRUM")
            if name in original.colnames()
        ]
        if not all(
            np.array_equal(original.getcol(name), work.getcol(name), equal_nan=True)
            for name in columns
        ):
            raise RuntimeError(
                "paired export changed an original native weight/SIGMA column"
            )
    boundary = validate_prepared_state(
        directory, state, json.loads((directory / "manifest.json").read_text())
    )
    return {
        **boundary,
        "all_native_weight_sigma_columns_preserved": True,
        "audited_weight_sigma_columns": columns,
    }


def run(
    run_dir,
    prepared_dir,
    iterations=50,
    max_fraction=0.02,
    include_native=False,
    mild_strategy=None,
):
    """Bounded paired source response: fixed9-grid, nativeMAD, optional CARACAL.

    Every candidate mask is applied identically to clean and injected solves.
    Selection is based only on injected-case TV/validation/flag objectives.
    Evaluation is performed only after writing immutable frozen selections.
    """
    root, source = reject_nested_paths(run_dir, prepared_dir)
    if (
        not isinstance(iterations, int)
        or isinstance(iterations, bool)
        or iterations < 1
        or not np.isfinite(max_fraction)
        or not 0 <= max_fraction <= 0.02
    ):
        raise ValueError("positive integer iterations and <=2% budget required")
    if not isinstance(include_native, bool):
        raise TypeError("include_native must be bool")
    strategy = None
    if include_native:
        if not mild_strategy:
            raise ValueError(
                "genuine CARACAL comparison requires a pinned mild_strategy"
            )
        strategy = Path(mild_strategy).resolve()
        if strategy.is_relative_to(root) or root.is_relative_to(strategy.parent):
            raise ValueError("strategy and output namespace must not be nested")
        strategy_provenance(strategy)
        if (
            not Path(
                os.environ.get("RANG_TRICOLOUR_PYTHON", "/opt/tricolour/bin/python")
            )
            .with_name("tricolour")
            .is_file()
        ):
            raise ValueError("verified isolated Tricolour executable required")
    # Validate sources read-only and reserve disk before creating new output state.
    source_state, source_manifest = (
        load_state(source),
        json.loads((source / "manifest.json").read_text()),
    )
    source_boundary = validate_prepared_state(source, source_state, source_manifest)
    source_digest = tree_digest(source)
    if shutil.disk_usage(root.parent).free < 8 * 1024**3 + 1024**3:
        raise ValueError("keep8GiB disk reserve plus1GiB bounded signal-run allowance")
    root.mkdir(parents=True, exist_ok=False)
    config = {
        "frozen_before_solve": True,
        "sources": list(SOURCES),
        "reference_frequency_hz": REFERENCE_HZ,
        "prepared_dir": str(source),
        "prepared_digest": source_digest,
        "prepared_boundary": source_boundary,
        "split_seed": source_manifest["seed"],
        "gain_intervals": source_manifest["split_gain_intervals"],
        "iterations": iterations,
        "max_fraction": max_fraction,
        "thresholds": list(THRESHOLDS),
        "tv_weights": list(TV_WEIGHTS),
        "mad_native": {
            "threshold_bl": 5.0,
            "threshold_global": 10.0,
            "whitening": "native",
            "off_diagonals": False,
        },
        "include_native": include_native,
        "mild_strategy": strategy_provenance(strategy) if strategy else None,
        "native_semantics": "operational features may see TEST DATA; comparison only, never claimed unseen-holdout flagging",
        "objective": "TV_fixed/TV0 +2*added_fraction +.25*MSEvalidation/MSEvalidation0",
        "selection": "source truth and TEST losses excluded; same mask for both paired solves",
        "evaluation": "joint flux/power-law template fit on commonTEST; nativeweights propagated through fixed cleanG0",
        "fit": {
            "flux_bounds_jy": [-1, 1],
            "spectral_index_bounds": [-5, 3],
            "max_nfev": 100,
            "reference_frequency_hz": REFERENCE_HZ,
            "conditioning_limit": 1e8,
        },
        "imaging": {
            "wsclean_path": shutil.which("wsclean"),
            "status": "not measured; WSClean absent in verified host/image; visibility-template metrics only",
        },
        "suite_image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
        "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "helper_sha256": {
            name: sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
            for name in (
                "flagging.py",
                "flagging_workflow.py",
                "flagging_prepared.py",
                "flagging_caracal.py",
                "flagging_comparators.py",
            )
        },
        "versions": {
            name: version(name)
            for name in (
                "quartical",
                "stimela",
                "numpy",
                "scipy",
                "numba",
                "codex-africanus",
                "python-casacore",
            )
        },
    }
    write_json(root / "signal-config.json", config)
    clean, injected = root / "clean", root / "injected"
    clean_state, manifest, _ = _stage(source, clean)
    ti, fi = manifest["split_gain_intervals"]
    zero = np.zeros_like(clean_state["train"])
    clean_metrics, _, _, _ = solve(
        clean, clean_state, manifest, zero, "baseline", ti, fi, iterations
    )
    clean_diagnostics = _diagnostics(clean / "trials/baseline")
    injected_state, injected_manifest = _prediction_and_injection(
        root, clean, injected, clean_state, clean_diagnostics, manifest
    )
    baseline, base_tv, residuals, guidance = solve(
        injected,
        injected_state,
        injected_manifest,
        zero,
        "baseline",
        ti,
        fi,
        iterations,
        scale=clean_metrics["scale"],
    )
    if (
        baseline["losses"]["validation"] is None
        or fixed_support_tv(base_tv["edges"], base_tv["edges"]) is None
    ):
        raise ValueError("injected baseline requires full validation and TV support")
    base_score = score_control(baseline, baseline["tv"], baseline)
    zero_id = _mask_identity(zero)
    records = {
        zero_id: {
            "mask_id": zero_id,
            "trial": "baseline",
            "clean_trial": "baseline",
            "families": ["residual", "tv"],
            "policies": [],
            "added_count": 0,
            "metrics": baseline,
            "clean_metrics": clean_metrics,
            "fixed_support_tv": baseline["tv"],
            **base_score,
        }
    }
    masks = {zero_id: zero}
    outliers = residual_features(
        residuals * np.sqrt(injected_state["weights"]),
        injected_state["train"],
        injected_state["antenna1"],
        injected_state["antenna2"],
    )

    def measure(mask, label, metadata):
        identity = _mask_identity(mask)
        if identity not in records:
            with (root / f"frozen-mask-{label}.npz").open("xb") as stream:
                np.savez_compressed(stream, added=mask)
            clean_trial = f"paired-{label}"
            measured, tv, _, _ = solve(
                injected,
                injected_state,
                injected_manifest,
                mask,
                label,
                ti,
                fi,
                iterations,
                scale=clean_metrics["scale"],
            )
            clean_measured, _, _, _ = solve(
                clean,
                clean_state,
                manifest,
                mask,
                clean_trial,
                ti,
                fi,
                iterations,
                scale=clean_metrics["scale"],
            )
            fixed_tv = fixed_support_tv(tv["edges"], base_tv["edges"])
            score = score_control(measured, fixed_tv, baseline)
            if measured["added_fraction"] > max_fraction:
                score["guard_pass"] = False
                score["guard_reasons"].append("frozen run flag budget exceeded")
            records[identity] = {
                "mask_id": identity,
                "trial": label,
                "clean_trial": clean_trial,
                "families": [],
                "policies": [],
                "added_count": int(mask.sum()),
                "metrics": measured,
                "clean_metrics": clean_measured,
                "fixed_support_tv": fixed_tv,
                **score,
            }
            masks[identity] = mask
        write_json(
            root / f"checkpoint-{label}.json",
            {"mask_id": identity, "metadata": metadata, "record": records[identity]},
        )
        return identity

    for weight in TV_WEIGHTS:
        family = "residual" if weight == 0 else "tv"
        for threshold in THRESHOLDS:
            mask = policy_mask(
                outliers,
                guidance,
                injected_state["train"],
                threshold=threshold,
                tv_weight=weight,
                max_fraction=max_fraction,
            )
            identity = measure(
                mask,
                f"grid-w{weight:g}-z{threshold:g}",
                {"threshold": threshold, "tv_weight": weight},
            )
            if family not in records[identity]["families"]:
                records[identity]["families"].append(family)
            records[identity]["policies"].append(
                {"threshold": threshold, "tv_weight": weight}
            )
    selectors = [
        {
            name: record[name]
            for name in (
                "mask_id",
                "families",
                "guard_pass",
                "objective",
                "added_count",
            )
        }
        for record in records.values()
    ]
    selected = {
        "no-added-flags": zero_id,
        "residual-selected": select_policy(selectors, "residual"),
        "tv-selected": select_policy(selectors, "tv"),
    }
    set_flags(injected, injected_state, zero, "mad-generator-input")
    name, mad, metadata = mad_proposal(injected, injected_state, 5.0, 10.0, "native")
    selected["mad-native"] = measure(mad, name, metadata)
    if include_native:
        native, mask = _native_run(
            injected,
            injected_state,
            "operational",
            strategy,
            Path(os.environ.get("RANG_TRICOLOUR_PYTHON", "/opt/tricolour/bin/python")),
            "caracal-mild",
        )
        write_json(root / "native-caracal-result.json", native)
        if mask is not None:
            selected["caracal-mild-operational"] = measure(mask, "caracal-mild", native)
    # All selections are final before any persisted truth is decoded.
    write_json(
        root / "frozen-selections.json",
        {
            "selected_masks": selected,
            "selector_records": selectors,
            "signal_truth_decoded_or_used_for_selection": False,
            "test_losses_used_for_selection": False,
        },
    )
    write_json(
        root / "candidate-records.json",
        {"records": list(records.values()), "signal_truth_used_for_selection": False},
    )
    with np.load(root / "signal-truth.npz", allow_pickle=False) as saved:
        templates, actual_delta, injection_mask = (
            saved["templates"],
            saved["actual_delta"],
            saved["injected"],
        )
    reference_p, reference_q, reference_good = _sample_gains(
        clean_state, clean_diagnostics, manifest["split_gain_intervals"]
    )
    reference, reference_variance, reference_valid = corrected_intensity(
        actual_delta, reference_p, reference_q, reference_good, clean_state["weights"]
    )
    reference_weights = np.where(reference_valid, 1 / reference_variance, np.nan)
    common = clean_state["test"] & reference_valid & injection_mask
    responses = {}
    for identity in set(selected.values()):
        record = records[identity]
        paired = []
        for directory, state, trial in (
            (clean, clean_state, record["clean_trial"]),
            (injected, injected_state, record["trial"]),
        ):
            gp, gq, good = _sample_gains(
                state,
                _diagnostics(directory / "trials" / trial),
                manifest["split_gain_intervals"],
            )
            paired.append(
                corrected_intensity(state["data"], gp, gq, good, state["weights"])
            )
        good = paired[0][2] & paired[1][2]
        common &= good
        responses[identity] = {
            "delta": paired[1][0] - paired[0][0],
            "valid": good,
            "variance_clean": paired[0][1],
            "variance_injected": paired[1][1],
        }
    if common.sum() < 2 * len(SOURCES):
        raise ValueError(
            "common fixed TEST support insufficient; do not silently change evaluation family"
        )
    reference_fit = fit_signal(
        reference, templates, clean_state["frequencies"], reference_weights, common
    )
    reports = []
    for method, identity in selected.items():
        record, response, mask = records[identity], responses[identity], masks[identity]
        recovered = fit_signal(
            response["delta"],
            templates,
            clean_state["frequencies"],
            reference_weights,
            common,
        )
        for source_fit, control_fit in zip(
            recovered["sources"], reference_fit["sources"]
        ):
            denominator = control_fit["recovered_flux_jy"]
            numerator = source_fit["recovered_flux_jy"]
            fraction = (
                numerator / denominator
                if numerator is not None
                and denominator is not None
                and denominator != 0
                else None
            )
            source_fit.update(
                calibration_response_fraction=fraction,
                attenuation_fraction=1 - fraction if fraction is not None else None,
            )
        energy = np.abs(templates) ** 2 * reference_weights[None]
        coverage = []
        for i, source_definition in enumerate(SOURCES):
            total = float(np.sum(energy[i][clean_state["train"] & reference_valid]))
            coverage.append(
                {
                    "name": source_definition["name"],
                    "training_template_weighted_energy_lost_fraction": float(
                        np.sum(energy[i][mask & reference_valid])
                    )
                    / total
                    if total > 0
                    else None,
                }
            )
        reports.append(
            {
                "method": method,
                "mask_id": identity,
                "trial": record["trial"],
                "clean_trial": record["clean_trial"],
                "selected_for_deployment": False,
                "guard_pass": record["guard_pass"],
                "objective": record["objective"],
                "added_count": record["added_count"],
                "evaluation": recovered,
                "template_coverage": coverage,
                "unsupported_test_samples": int(
                    np.count_nonzero(clean_state["test"] & ~response["valid"])
                ),
                "clean_vs_injected_corrected_variance_ratio_median": float(
                    np.median(
                        response["variance_injected"][common]
                        / response["variance_clean"][common]
                    )
                ),
                "unseen_holdout_flagging_features": not method.startswith("caracal"),
            }
        )
    final_clean = _export(clean, clean_state, zero, "final-original-flags")
    final_injected = _export(injected, injected_state, zero, "final-original-flags")
    audit = {
        "prepared_source_unchanged": tree_digest(source) == source_digest,
        "original_input_tree_unchanged": tree_digest(manifest["source"])
        == manifest["source_digest"],
        "clean_boundary": final_clean,
        "injected_boundary": final_injected,
        "signal_truth_decoded_or_used_for_selection": False,
        "test_losses_used_for_selection": False,
        "calibration_model_unchanged": bool(
            np.array_equal(clean_state["model"], injected_state["model"])
        ),
        "original_flags_and_native_weights_preserved": final_clean["validated"]
        and final_injected["validated"],
    }
    if not all(
        audit[name]
        for name in (
            "prepared_source_unchanged",
            "original_input_tree_unchanged",
            "calibration_model_unchanged",
            "original_flags_and_native_weights_preserved",
        )
    ):
        raise RuntimeError("paired science-signal preservation audit failed")
    write_json(root / "signal-audit.json", audit)
    write_json(
        root / "result.json",
        {
            "status": "measured paired visibility-template diagnostic; no deployed flags or images",
            "sources": list(SOURCES),
            "reference_fit": reference_fit,
            "methods": reports,
            "candidates": list(records.values()),
            "common_test_samples": int(common.sum()),
            "original_test_samples": int(clean_state["test"].sum()),
            "lost_common_test_samples": int(
                np.count_nonzero(clean_state["test"] & ~common)
            ),
            "imaging": config["imaging"],
            "audit": audit,
            "limitations": [
                "four-antenna pointing scan, not representative science imaging",
                "DI-gain-corrupted intrinsic injection; no off-axis beam or pointing effects",
                "known template positions/extents and spectral family are evaluation-only",
                "paired differences share the original noisy DATA; no independent-noise confidence intervals",
                "original unflagged data not guaranteed RFI-free",
                "native CARACAL operational features can see TEST DATA",
                "amd64 emulation timings are not native cost claims",
            ],
        },
    )
    print(
        f"Paired source recovery complete: {len(records)} distinct masks, commonTEST={common.sum()}; no imaging claim",
        flush=True,
    )
