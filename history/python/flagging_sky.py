"""Paired real MeerKAT L-band sky-model experiment, not a flagging win claim."""

import json
import os
import shutil
import subprocess
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from .flagging import assert_preserved, fixed_support_tv, snapshot_flags
from .flagging_workflow import (
    load_state,
    prepare,
    set_flags,
    solve,
    tree_digest,
    write_json,
)

SKY_SHA256 = "b277bc6d4095bb22798cc70547d9563a56460eb6e450474854b93117534b1fb9"
SKY_URL = "https://archive-gw-1.kat.ac.za/public/repository/10.48479/hhhy-4r55/data/fitted.PKS1934.LBand.wsclean.cat.txt"
SKY_RELEASE = "https://doi.org/10.48479/hhhy-4r55"
SKY_COLUMN = "RANG_SARAO_MODEL_DATA"
PRIMARY_COLUMN = "RANG_SARAO_PRIMARY_DATA"


def model_provenance(path):
    """Accept only the verified official L-band apparent-scale catalog."""
    payload = Path(path).read_bytes()
    digest = sha256(payload).hexdigest()
    if digest != SKY_SHA256:
        raise ValueError("unexpected SARAO L-band sky-model checksum")
    lines = payload.decode().splitlines()
    if not lines[0].startswith("Format = ") or len(lines) != 5154:
        raise ValueError("unexpected full WSClean catalog structure")
    return {
        "sha256": digest,
        "url": SKY_URL,
        "release": SKY_RELEASE,
        "author": "B. V. Hugo, SARAO, 2021",
        "license": "CC BY-NC 4.0",
        "components": len(lines) - 1,
        "convention": "apparent scale; primary-beam response not corrected",
        "beam_action": "none; do not apply another beam to an apparent model",
        "applicability": "L-band, MeerKAT ~13.5 m dishes; pointing-scan applicability unverified",
    }


def require_scalar_model(model, shape):
    """The common polar-gauge symmetry requires an unpolarized scalar sky."""
    model = np.asarray(model)
    if model.shape != tuple(shape) or model.ndim != 3 or model.shape[-1] != 4:
        raise ValueError("four-correlation sky model must match DATA shape")
    if not np.isfinite(model).all():
        raise ValueError("sky model contains nonfinite values")
    if not (
        np.array_equal(model[..., 0], model[..., 3]) and not np.any(model[..., 1:3])
    ):
        raise ValueError("polar gauge requires an unpolarized scalar sky model")
    return model


def array_digest(value):
    value = np.ascontiguousarray(value)
    digest = sha256(str((value.shape, value.dtype.str)).encode())
    digest.update(value.tobytes())
    return digest.hexdigest()


def point_catalog_predict(
    uvw, radec, phase_centre, frequencies, flux, coefficients, reference
):
    """Independent NumPy DFT for this catalog's POINT/ordinary-polynomial sources.

    Positive Fourier phase matches the installed Africanus/MS convention.
    Spectral coefficients are additive Jy coefficients, not spectral indices.
    This tiny-check path does not replace Crystalball's full prediction.
    """
    uvw, radec = np.asarray(uvw, float), np.asarray(radec, float)
    frequencies, reference = (
        np.asarray(frequencies, float),
        np.asarray(reference, float),
    )
    flux, coefficients = np.asarray(flux, float), np.asarray(coefficients, float)
    ra0, dec0 = phase_centre
    ra, dec = radec.T
    difference = ra - ra0
    l = np.cos(dec) * np.sin(difference)
    m = np.sin(dec) * np.cos(dec0) - np.cos(dec) * np.sin(dec0) * np.cos(difference)
    n_minus_one = np.sqrt(1 - l * l - m * m) - 1
    x = frequencies[None] / reference[:, None] - 1
    spectrum = flux[:, None] + sum(
        coefficients[:, k, None] * x ** (k + 1) for k in range(coefficients.shape[1])
    )
    distance = uvw @ np.stack((l, m, n_minus_one))
    phase = 2j * np.pi / 299792458 * distance[..., None] * frequencies
    return np.sum(np.exp(phase) * spectrum[None], axis=1)


def comparison_summary(point, sky, point_edges, sky_edges):
    """Descriptive fixed-support comparison; test loss never selects a model."""
    fixed = fixed_support_tv(sky_edges, point_edges)
    reference = fixed_support_tv(point_edges, point_edges)
    return {
        "point_fixed_support_tv": reference,
        "sky_fixed_support_tv": fixed,
        "fixed_support_tv_ratio": fixed / reference
        if fixed is not None and reference and reference > 0
        else None,
        "lost_reference_edges": int(
            np.count_nonzero(np.isfinite(point_edges) & ~np.isfinite(sky_edges))
        ),
        "reference_edge_counts": [int(np.isfinite(e).sum()) for e in point_edges],
        "weighted_mse_ratios": {
            name: sky["losses"][name] / point["losses"][name]
            if sky["losses"][name] is not None
            and point["losses"][name] is not None
            and point["losses"][name] > 0
            else None
            for name in ("train", "validation", "test")
        },
        "interpretation": "diagnostic paired model comparison, not physical-model verification or a flagging improvement",
    }


def _fingerprint(ms, extra_columns=()):
    from casacore.tables import table

    with table(str(ms), readonly=True, ack=False, lockoptions="autonoread") as source:
        return {
            name: array_digest(source.getcol(name))
            for name in (
                "DATA",
                "FLAG",
                "FLAG_ROW",
                "WEIGHT",
                "WEIGHT_SPECTRUM",
                "UVW",
                "TIME",
                "ANTENNA1",
                "ANTENNA2",
                "FIELD_ID",
                "DATA_DESC_ID",
                "SCAN_NUMBER",
                "RANG_MODEL_DATA",
            )
            + tuple(extra_columns)
            if name in source.colnames()
        }


def _weights_preserved(run_dir):
    from casacore.tables import table

    with (
        table(
            str(run_dir / "original.ms"),
            readonly=True,
            ack=False,
            lockoptions="autonoread",
        ) as original,
        table(
            str(run_dir / "work.ms"), readonly=True, ack=False, lockoptions="autonoread"
        ) as work,
    ):
        return all(
            np.array_equal(original.getcol(column), work.getcol(column), equal_nan=True)
            for column in ("WEIGHT", "WEIGHT_SPECTRUM")
            if column in original.colnames()
        )


def _primary_control(
    run_dir, state, manifest, point, point_edges, multi, multi_edges, config
):
    """Hold the official primary spectrum/position fixed to isolate field sources."""
    from casacore.tables import table

    predictor = Path(config["predictor"])
    shutil.copytree(run_dir / "work.ms", run_dir / "backups/work-before-primary.ms")
    before = _fingerprint(run_dir / "work.ms", (SKY_COLUMN,))
    write_json(run_dir / "backups/primary-prediction-before-columns.json", before)
    with table(str(run_dir / "work.ms"), readonly=True, ack=False) as work:
        snapshot_flags(
            run_dir / "backups/primary-prediction-before-flags.npz",
            work.getcol("FLAG"),
            work.getcol("FLAG_ROW"),
        )
    command = [
        str(predictor),
        str(run_dir / "work.ms"),
        "-sm",
        str(run_dir / "sky-model.wsclean.txt"),
        "-f",
        "0",
        "-j",
        "1",
        "-rc",
        "32",
        "-mc",
        "1",
        "-ns",
        "1",
        "-o",
        PRIMARY_COLUMN,
        "--scheduler",
        "threads",
    ]
    write_json(run_dir / "primary-prediction-command.json", command)
    with (run_dir / "primary-prediction.log").open("x") as log:
        completed = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    after = _fingerprint(run_dir / "work.ms", (SKY_COLUMN,))
    write_json(run_dir / "backups/primary-prediction-after-columns.json", after)
    if before != after:
        raise RuntimeError(
            "primary prediction modified existing input or full-sky columns"
        )
    if completed.returncode:
        raise RuntimeError("official-primary-only Crystalball prediction failed")
    verification = (
        Path(__file__).resolve().parents[2] / "tools/flagging/sky/verify_prediction.py"
    )
    subprocess.run(
        [
            str(predictor.parent / "python"),
            str(verification),
            str(run_dir / "work.ms"),
            str(run_dir / "sky-model.wsclean.txt"),
            PRIMARY_COLUMN,
            str(run_dir / "primary-prediction-verification.json"),
            "primary",
        ],
        check=True,
    )
    with table(str(run_dir / "work.ms"), readonly=True, ack=False) as work:
        state["model"] = require_scalar_model(
            work.getcol(PRIMARY_COLUMN), state["data"].shape
        )
    primary, primary_tv, _, _ = solve(
        run_dir,
        state,
        {**manifest, "model_column": PRIMARY_COLUMN},
        np.zeros_like(state["train"]),
        "sarao-primary",
        config["time_interval"],
        config["freq_interval"],
        config["iterations"],
        scale=point["scale"],
    )
    primary_summary = comparison_summary(
        point, primary, point_edges, primary_tv["edges"]
    )
    full_summary = comparison_summary(point, multi, point_edges, multi_edges)
    primary_fixed = primary_summary["sky_fixed_support_tv"]
    full_fixed = full_summary["sky_fixed_support_tv"]
    secondary = {
        "tv_support": "fixed original point-baseline edge support",
        "full_over_official_primary_fixed_support_tv": full_fixed / primary_fixed
        if full_fixed is not None and primary_fixed and primary_fixed > 0
        else None,
        "weighted_mse_ratios": {
            name: multi["losses"][name] / primary["losses"][name]
            if multi["losses"][name] is not None
            and primary["losses"][name] is not None
            and primary["losses"][name] > 0
            else None
            for name in ("train", "validation", "test")
        },
        "interpretation": "secondary-field contribution isolated from central spectrum/position change; pointing applicability still unverified",
    }
    return primary, primary_summary, secondary


def complete_primary(run_dir):
    """Recoverably append the primary control to an earlier two-model pilot.

    This avoids rerunning expensive verified full prediction. It is exclusive:
    duplicate control trials/backups cannot be overwritten. Original result JSON
    is moved into backups before publishing the three-model result.
    """
    from casacore.tables import table

    run_dir = Path(run_dir).resolve()
    result = json.loads((run_dir / "result.json").read_text())
    if "sarao_primary" in result:
        raise ValueError("official-primary control already measured")
    if (run_dir / "backups/result-before-primary.json").exists():
        raise FileExistsError(
            "original result backup already exists; never overwrite it"
        )
    config = json.loads((run_dir / "sky-config.json").read_text())
    state = load_state(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    with np.load(run_dir / "trials/point/diagnostics.npz", allow_pickle=False) as saved:
        point_edges = saved["edges"]
    with np.load(
        run_dir / "trials/sarao-full/diagnostics.npz", allow_pickle=False
    ) as saved:
        multi_edges = saved["edges"]
    primary, primary_summary, secondary = _primary_control(
        run_dir,
        state,
        manifest,
        result["point"],
        point_edges,
        result["sarao_full"],
        multi_edges,
        config,
    )
    set_flags(
        run_dir,
        state,
        np.zeros_like(state["train"]),
        "restore-original-primary-extension",
        holdout=False,
    )
    with table(str(run_dir / "work.ms"), readonly=True, ack=False) as work:
        assert_preserved(
            state["original_flags"],
            state["original_rows"],
            work.getcol("FLAG"),
            work.getcol("FLAG_ROW"),
        )
        if not np.array_equal(
            work.getcol("DATA"), state["data"], equal_nan=True
        ) or not np.array_equal(work.getcol("FLAG"), state["original_flags"]):
            raise RuntimeError("primary extension DATA/flag preservation audit failed")
    if (
        tree_digest(manifest["source"]) != manifest["source_digest"]
        or tree_digest(run_dir / "original.ms") != manifest["original_copy_digest"]
        or not _weights_preserved(run_dir)
    ):
        raise RuntimeError("primary extension immutable MS audit failed")
    result.update(
        sarao_primary=primary,
        primary_comparison=primary_summary,
        secondary_comparison=secondary,
    )
    result["primary_extension_audit"] = {
        "source_unchanged": True,
        "immutable_copy_unchanged": True,
        "data_preserved": True,
        "weights_preserved": True,
        "exact_flags_restored": True,
        "prediction_input_columns_unchanged": True,
    }
    result["primary_extension_code_sha256"] = sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    (run_dir / "result.json").rename(run_dir / "backups/result-before-primary.json")
    write_json(run_dir / "result.json", result)
    print(json.dumps(secondary, indent=2), flush=True)


def compare(
    run_dir,
    archive,
    sky_model,
    seed=7,
    channel_start=1024,
    channel_stop=3072,
    time_interval=2,
    freq_interval=32,
    iterations=50,
    predictor=None,
):
    """Prepare exclusive copies, predict all 5153 sources, re-solve full Jones.

    The raw fixture, immutable original.ms, DATA and weights remain unchanged.
    Each trial uses the identical fixed split and gain grid. The point baseline's
    normalization and supported TV edges are fixed for the paired comparison.
    """
    from casacore.tables import table

    provenance = model_provenance(sky_model)
    predictor = predictor or os.environ.get(
        "RANG_SKY_PREDICTOR", "/opt/sky/bin/crystalball"
    )
    predictor = Path(predictor).resolve()
    if not predictor.is_file():
        raise FileNotFoundError("verified Crystalball predictor executable not found")
    prepare(
        run_dir,
        archive=archive,
        seed=seed,
        channel_start=channel_start,
        channel_stop=channel_stop,
        time_interval=time_interval,
        freq_interval=freq_interval,
    )
    run_dir = Path(run_dir).resolve()
    state = load_state(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    model = run_dir / "sky-model.wsclean.txt"
    shutil.copyfile(sky_model, model)
    provenance["copied_sha256"] = sha256(model.read_bytes()).hexdigest()
    write_json(run_dir / "sky-provenance.json", provenance)
    write_json(
        run_dir / "sky-config.json",
        {
            "seed": seed,
            "channels": [channel_start, channel_stop],
            "time_interval": time_interval,
            "freq_interval": freq_interval,
            "iterations": iterations,
            "predictor": str(predictor),
            "gauge": "polar",
            "gain_type": "complex 2x2",
            "common_normalization": "fixed point-baseline median gain norm",
            "weights": "original native weights",
            "additional_flags": 0,
            "code_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "predictor_requirements": (
                predictor.parent.parent / "requirements.lock"
            ).read_text(),
            "predictor_installation_report": json.loads(
                (predictor.parent.parent / "install-report.json").read_text()
            )
            if (predictor.parent.parent / "install-report.json").is_file()
            else None,
        },
    )
    zero = np.zeros_like(state["train"])
    point, point_tv, _, _ = solve(
        run_dir,
        state,
        manifest,
        zero,
        "point",
        time_interval,
        freq_interval,
        iterations,
    )
    shutil.copytree(run_dir / "work.ms", run_dir / "backups/work-before-sky.ms")
    with table(str(run_dir / "work.ms"), readonly=True, ack=False) as work:
        snapshot_flags(
            run_dir / "backups/sky-prediction-before-flags.npz",
            work.getcol("FLAG"),
            work.getcol("FLAG_ROW"),
        )
    before = _fingerprint(run_dir / "work.ms")
    write_json(run_dir / "backups/sky-prediction-before-columns.json", before)
    command = [
        str(predictor),
        str(run_dir / "work.ms"),
        "-sm",
        str(model),
        "-f",
        "0",
        "-j",
        "1",
        "-rc",
        "32",
        "-mc",
        "64",
        "-o",
        SKY_COLUMN,
        "--scheduler",
        "threads",
    ]
    write_json(run_dir / "prediction-command.json", command)
    started = time.perf_counter()
    with (run_dir / "prediction.log").open("x") as log:
        completed = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    prediction_seconds = time.perf_counter() - started
    after = _fingerprint(run_dir / "work.ms")
    write_json(run_dir / "backups/sky-prediction-after-columns.json", after)
    if before != after:
        raise RuntimeError(
            "sky prediction modified original DATA, flags, weights or metadata columns"
        )
    if completed.returncode:
        write_json(
            run_dir / "prediction-failure.json",
            {"returncode": completed.returncode, "seconds": prediction_seconds},
        )
        raise RuntimeError("Crystalball prediction failed; inspect prediction.log")
    with table(str(run_dir / "work.ms"), readonly=True, ack=False) as work:
        sky = require_scalar_model(work.getcol(SKY_COLUMN), state["data"].shape)
    verification = (
        Path(__file__).resolve().parents[2] / "tools/flagging/sky/verify_prediction.py"
    )
    verify_command = [
        str(predictor.parent / "python"),
        str(verification),
        str(run_dir / "work.ms"),
        str(model),
        SKY_COLUMN,
        str(run_dir / "prediction-verification.json"),
    ]
    subprocess.run(verify_command, check=True)
    np.savez_compressed(run_dir / "backups/point-model.npz", model=state["model"])
    state["model"] = sky
    manifest = {**manifest, "model_column": SKY_COLUMN}
    multi, multi_tv, _, _ = solve(
        run_dir,
        state,
        manifest,
        zero,
        "sarao-full",
        time_interval,
        freq_interval,
        iterations,
        scale=point["scale"],
    )
    summary = comparison_summary(point, multi, point_tv["edges"], multi_tv["edges"])
    primary, primary_summary, secondary = _primary_control(
        run_dir,
        state,
        manifest,
        point,
        point_tv["edges"],
        multi,
        multi_tv["edges"],
        {
            "predictor": str(predictor),
            "time_interval": time_interval,
            "freq_interval": freq_interval,
            "iterations": iterations,
        },
    )
    set_flags(run_dir, state, zero, "restore-original", holdout=False)
    with table(str(run_dir / "work.ms"), readonly=True, ack=False) as work:
        assert_preserved(
            state["original_flags"],
            state["original_rows"],
            work.getcol("FLAG"),
            work.getcol("FLAG_ROW"),
        )
        data_preserved = np.array_equal(
            work.getcol("DATA"), state["data"], equal_nan=True
        )
        exact_flags = np.array_equal(work.getcol("FLAG"), state["original_flags"])
        additional = int(
            np.count_nonzero(work.getcol("FLAG") & ~state["original_flags"])
        )
    source_digest = tree_digest(manifest["source"])
    original_digest = tree_digest(run_dir / "original.ms")
    audit = {
        "source_digest_before": manifest["source_digest"],
        "source_digest_after": source_digest,
        "original_digest_before": manifest["original_copy_digest"],
        "original_digest_after": original_digest,
        "source_unchanged": source_digest == manifest["source_digest"],
        "immutable_copy_unchanged": original_digest == manifest["original_copy_digest"],
        "original_flags_preserved": True,
        "exact_cell_flags_restored": exact_flags,
        "data_preserved": data_preserved,
        "weights_preserved": _weights_preserved(run_dir),
        "additional_flag_cells": additional,
        "prediction_input_columns_unchanged": before == after,
    }
    if not all(
        audit[name]
        for name in (
            "source_unchanged",
            "immutable_copy_unchanged",
            "original_flags_preserved",
            "data_preserved",
            "weights_preserved",
            "prediction_input_columns_unchanged",
        )
    ):
        raise RuntimeError("sky comparison preservation audit failed")
    write_json(run_dir / "flag-audit.json", audit)
    write_json(
        run_dir / "result.json",
        {
            "status": "measured diagnostic; no flags selected",
            "model": provenance,
            "point": point,
            "sarao_primary": primary,
            "sarao_full": multi,
            "comparison": summary,
            "primary_comparison": primary_summary,
            "secondary_comparison": secondary,
            "prediction_seconds": prediction_seconds,
            "audit": audit,
            "limitations": [
                "four-antenna short-baseline reference-pointing scan, not science imaging benchmark",
                "apparent sky model derived for nominal pointing; current offset/beam state unverified",
                "original unflagged samples are not guaranteed RFI-free",
                "lower TV alone does not establish a physically correct model or improved flagging",
                "amd64 emulation timings are not native performance measurements",
            ],
        },
    )
    print(json.dumps(summary, indent=2), flush=True)
