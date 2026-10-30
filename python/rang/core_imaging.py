"""Imaging track replay on the Rang core (research/core-i-imaging-replay.md).

Wave 2 task I of ``research/core-parallel-plan.md``: the fifteen archived
dirty inversions of ``research/results/gain-tv-next-imaging.json`` run with
the core's imaging weights (task B), w-stacking gridder (task C) and
Measurement Set reader (task E) instead of WSClean, and the archived
template fits, response fractions and closures are recomputed with the
unedited audit algebra of ``flagging_imaging``. The science archive is never
changed; this module reads the checkpointed columns the archived run wrote.

The comparator half (``classify_replay``, ``compare_replay``,
``pixel_comparison``) was written and run on archive versus host reproduction
before the protocol was frozen; the driver half (``run``) came after.
"""

import argparse
import json
import math
import subprocess
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import core, core_grid, core_ms, core_weights
from . import core_image_fit as flagging_imaging
from .core_image_fit import (
    IMAGE_CLOSURE_JY,
    SETTINGS,
    image_diagnostics,
    image_geometry,
    linear_image_fit,
)
from .core_sensitivity import FITTED_JOBS, JOBS, ROLES, UNIT_JOBS

ROOT = Path(__file__).resolve().parents[2]

CHANNELS = (1024, 3072)
TEST_SAMPLES = 9169
SIZE = 512
# Task A's proposed phase 4 tolerances (research/core-a-imaging-sensitivity.md).
TOLERANCES = {
    "template_flux_relative": 4.7e-6,
    "response_fraction_absolute": 1.6e-7,
    "dirty_linf_relative_to_peak": 8.8e-6,
    "psf_linf": 2.8e-6,
    "weight_sums_relative": 1e-9,
    "image_closure_jy_per_beam": IMAGE_CLOSURE_JY,
    "wcs_degrees": 1e-9,
}
# Archive fields the core replay cannot or must not reproduce.
EXCLUDED_KEYS = frozenset(
    {
        # run-specific
        "status",
        "limitations",
        "seconds_emulated_not_native_benchmark",
        "allocated_bytes_before_final_result",
        "FITS_sha256",
        "actual_WSClean_inversions",
        # Measurement Set audits of the WSClean run; the core reads checkpoints
        "column_audit",
        "native_columns_exact",
        "source_unchanged",
        "runtime_unchanged",
        "tool_unchanged",
        "whole_MS_backups_unchanged",
        "whole_MS_backup_digests",
        # computed before the complex64 cast the checkpoints hold
        "precast_visibility_closures_jy",
        # provenance of the caracal inputs, not carried by the checkpoints
        "training_additions",
        # WSClean's version and its Gaussian PSF fit, not ported
        "WSCVERSI",
        "BMAJ",
        "BMIN",
        "BPA",
    }
)
REPORTED_KEYS = frozenset(
    {
        "condition",
        "unweighted_pixel_MSE_proxy",
        "dirty_offsource_RMS_jy_per_beam",
        "dirty_offsource_std_jy_per_beam",
        "peak_abs_jy_per_beam",
    }
)
WCS_FLOAT_KEYS = frozenset({"CRVAL1", "CRVAL2", "CDELT1", "CDELT2"})
WEIGHT_SUM_KEYS = frozenset({"WSCVWSUM", "WSCIMGWG", "WSCNORMF"})
CLASS_RULES = {
    "exact": "equal",
    "template_flux": ("relative", "template_flux_relative"),
    # The two unit-template jobs fit the basis to itself: coefficients 1 and
    # a rounding-level zero (6e-17 Jy in the archive). They are compared
    # absolutely against the 1 Jy template amplitude, since task A's spread
    # never covered them and a relative rule on a rounding zero is undefined.
    "unit_flux": ("absolute", "template_flux_relative"),
    "response_fraction": ("absolute", "response_fraction_absolute"),
    "psf_linf": ("absolute", "psf_linf"),
    "weight_sum": ("relative", "weight_sums_relative"),
    "wcs": ("absolute", "wcs_degrees"),
    "closure": "closure",
    "reported": "reported",
}


def _keys(path):
    return [p for p in path if isinstance(p, str)]


def classify_replay(path):
    """Comparison class of one archive leaf (path of keys and indices)."""
    keys = _keys(path)
    if any(k in EXCLUDED_KEYS for k in keys):
        return "excluded"
    key = keys[-1] if keys else None
    parent = keys[-2] if len(keys) > 1 else None
    if key == "coefficients_jy":
        return "unit_flux" if any(k in UNIT_JOBS for k in keys) else "template_flux"
    if key == "conditional_response_vs_fixedG0":
        return "response_fraction"
    if key == "PSF_linf_difference_vs_fixedG0":
        return "psf_linf"
    if key in WEIGHT_SUM_KEYS:
        return "weight_sum"
    if key in WCS_FLOAT_KEYS:
        return "wcs"
    if parent == "dirty_image_closures_jy_per_beam":
        return "closure"
    if key in REPORTED_KEYS:
        return "reported"
    return "exact"


def _leaves(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaves(child, (*path, index))
    else:
        yield path, value


def _lookup(value, path):
    for step in path:
        if isinstance(value, dict):
            if step not in value:
                raise KeyError(path)
            value = value[step]
        elif isinstance(value, list) and isinstance(step, int) and step < len(value):
            value = value[step]
        else:
            raise KeyError(path)
    return value


def _numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check(cls, archived, core):
    """(passed, measured difference) for one leaf under its class."""
    rule = CLASS_RULES[cls]
    if rule == "equal":
        return archived == core, None
    if not (_numeric(archived) and _numeric(core)):
        return archived == core, None
    if not (math.isfinite(archived) and math.isfinite(core)):
        return archived == core, None
    diff = abs(core - archived)
    if rule == "reported":
        return True, diff / abs(archived) if archived else diff
    if rule == "closure":
        limit = TOLERANCES["image_closure_jy_per_beam"]
        return archived <= limit and core <= limit, diff
    kind, name = rule
    if kind == "relative":
        measured = diff / abs(archived) if archived else diff
    else:
        measured = diff
    return measured <= TOLERANCES[name], measured


def compare_replay(archived, core):
    """Compare an archived raw imaging result with a core replay, leaf by leaf.

    Returns the per-class counts and worst measured differences, the
    excluded count and a list of failures; a missing core field fails
    unless it is excluded.
    """
    report = {"classes": {}, "excluded": 0, "failures": []}
    for path, value in _leaves(archived):
        cls = classify_replay(path)
        if cls == "excluded":
            report["excluded"] += 1
            continue
        try:
            other = _lookup(core, path)
        except KeyError:
            report["failures"].append({"path": list(path), "reason": "missing"})
            continue
        ok, measured = _check(cls, value, other)
        stats = report["classes"].setdefault(
            cls, {"compared": 0, "worst": 0.0, "worst_path": None}
        )
        stats["compared"] += 1
        if measured is not None and measured >= stats["worst"]:
            stats["worst"], stats["worst_path"] = measured, list(path)
        if not ok:
            report["failures"].append(
                {"path": list(path), "class": cls, "archived": value, "core": other}
            )
    report["tolerances"] = dict(TOLERANCES)
    report["passed"] = not report["failures"]
    return report


def read_fits(path):
    """`(height, width)` float64 pixels and the header of a FITS image."""
    from astropy.io import fits

    with fits.open(str(path), memmap=False) as hdus:
        return np.asarray(hdus[0].data, np.float64).squeeze(), hdus[0].header


WCS_KEYS = (
    "CRPIX1",
    "CRPIX2",
    "CRVAL1",
    "CRVAL2",
    "CDELT1",
    "CDELT2",
    "CTYPE1",
    "CTYPE2",
)


def pixel_record(reference, reference_header, candidate, candidate_header):
    """Pixel differences of one image against its reference (task C style),
    with the central 256 x 256 and the border reported separately because
    task A found kernel-related differences at the edges."""
    if reference.shape != candidate.shape:
        raise ValueError(f"shape mismatch {reference.shape} vs {candidate.shape}")
    delta = candidate - reference
    peak = float(np.max(np.abs(reference)))
    height, width = delta.shape
    y0, x0 = height // 4, width // 4
    central = np.zeros(delta.shape, bool)
    central[y0 : height - y0, x0 : width - x0] = True
    wcs_equal = True
    for key in WCS_KEYS:
        a, b = reference_header[key], candidate_header[key]
        if isinstance(a, str):
            wcs_equal &= a == b
        else:
            wcs_equal &= abs(float(a) - float(b)) <= TOLERANCES["wcs_degrees"]
    linf = float(np.max(np.abs(delta)))
    return {
        "max_abs_difference": linf,
        "rms_difference": float(np.sqrt(np.mean(delta**2))),
        "central_rms_difference": float(np.sqrt(np.mean(delta[central] ** 2))),
        "border_rms_difference": float(np.sqrt(np.mean(delta[~central] ** 2))),
        "reference_peak": peak,
        "max_relative_to_peak": linf / peak if peak else None,
        "argmax_difference": [
            int(v) for v in np.unravel_index(np.argmax(np.abs(delta)), delta.shape)
        ],
        "finite": bool(np.isfinite(candidate).all()),
        "wcs_equal": bool(wcs_equal),
    }


def pixel_comparison(reference_dir, candidate_dir, labels=JOBS):
    """Dirty and PSF pixel differences for every job, gated by task A's
    tolerances (dirty L-infinity relative to the reference peak, PSF
    L-infinity absolute) and the WCS keys."""
    reference_dir, candidate_dir = Path(reference_dir), Path(candidate_dir)
    jobs = {}
    for label in labels:
        jobs[label] = {}
        for kind in ("dirty", "psf"):
            ref, ref_header = read_fits(reference_dir / f"{label}-{kind}.fits")
            cand, cand_header = read_fits(candidate_dir / f"{label}-{kind}.fits")
            record = pixel_record(ref, ref_header, cand, cand_header)
            record["within_tolerance"] = (
                record["max_relative_to_peak"]
                <= TOLERANCES["dirty_linf_relative_to_peak"]
                if kind == "dirty"
                else record["max_abs_difference"] <= TOLERANCES["psf_linf"]
            )
            jobs[label][kind] = record
    summary = {
        kind: {
            "max_abs_difference": max(
                j[kind]["max_abs_difference"] for j in jobs.values()
            ),
            "max_relative_to_peak": max(
                j[kind]["max_relative_to_peak"] for j in jobs.values()
            ),
            "max_rms_difference": max(j[kind]["rms_difference"] for j in jobs.values()),
            "max_central_rms": max(
                j[kind]["central_rms_difference"] for j in jobs.values()
            ),
            "max_border_rms": max(
                j[kind]["border_rms_difference"] for j in jobs.values()
            ),
            "all_within_tolerance": all(
                j[kind]["within_tolerance"] for j in jobs.values()
            ),
        }
        for kind in ("dirty", "psf")
    }
    return {
        "reference": str(reference_dir),
        "candidate": str(candidate_dir),
        "tolerances": {
            k: TOLERANCES[k]
            for k in ("dirty_linf_relative_to_peak", "psf_linf", "wcs_degrees")
        },
        "jobs": jobs,
        "summary": summary,
        "wcs_equal": all(
            j[k]["wcs_equal"] for j in jobs.values() for k in ("dirty", "psf")
        ),
        "passed": summary["dirty"]["all_within_tolerance"]
        and summary["psf"]["all_within_tolerance"]
        and all(j[k]["wcs_equal"] for j in jobs.values() for k in ("dirty", "psf")),
    }


# ---------------------------------------------------------------------------
# Driver (written after the protocol was frozen in 80d7523).

GRID = {
    "width": SIZE,
    "height": SIZE,
    "scale_arcsec": float(SETTINGS["scale_arcsec"]),
    "w_layers": int(SETTINGS["w_layers"]),
    "kernel_size": 7,
    "oversampling": 1023,
    "padding": 1.2,
}
ROBUST = float(SETTINGS["robust"])
LINEAR_CORRELATIONS = (9, 10, 11, 12)
DEFAULT_ARCHIVE = ROOT / "outputs" / "tv-next-imaging-wsl-20261029-01"
DEFAULT_EXPORT = ROOT / "outputs" / "core-c-20261029-01" / "inputs"
DEFAULT_ORACLE = ROOT / "research" / "results" / "gain-tv-next-imaging.json"
MODULES = ("core_image_fit", "core_grid", "core_weights", "core_ms", "core_imaging")


def _sha256(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _module_sha256():
    return {name: _sha256(Path(__file__).with_name(f"{name}.py")) for name in MODULES}


def _snapshot(root):
    root = Path(root)
    return {
        p.relative_to(root).as_posix(): [p.stat().st_size, p.stat().st_mtime_ns]
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "table.lock"
    }


def _git_status():
    try:
        return subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")


def read_ms_inputs(ms, channels=CHANNELS):
    """What the imager needs from one archived backup Measurement Set, read
    through the core: UVW in metres, the selected channels' WEIGHT_SPECTRUM
    and frequencies, the phase centre, and the rows WSClean images (field 0,
    cross-correlations, data description 0)."""
    lo, hi = channels
    with core_ms.open_table(ms) as table:
        uvw = table.getcol("UVW")
        weight_spectrum = table.getcol("WEIGHT_SPECTRUM")[:, lo:hi]
        field = table.getcol("FIELD_ID")
        antenna1, antenna2 = table.getcol("ANTENNA1"), table.getcol("ANTENNA2")
        data_desc = table.getcol("DATA_DESC_ID")
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as spw:
        frequencies = spw.getcol("CHAN_FREQ")[0, lo:hi]
    with core_ms.open_table(Path(ms) / "FIELD") as field_table:
        phase_dir = field_table.getcol("PHASE_DIR")[0, 0]
    with core_ms.open_table(Path(ms) / "POLARIZATION") as polarization:
        corr_type = polarization.getcol("CORR_TYPE")[0]
    if tuple(int(c) for c in corr_type) != LINEAR_CORRELATIONS:
        raise ValueError("XX, XY, YX, YY correlations required")
    return {
        "UVW": np.ascontiguousarray(uvw, np.float64),
        "WEIGHT_SPECTRUM": np.ascontiguousarray(weight_spectrum, np.float32),
        "CHAN_FREQ": np.ascontiguousarray(frequencies, np.float64),
        "PHASE_DIR": np.asarray(phase_dir, np.float64),
        "rows": (field == 0) & (antenna1 != antenna2) & (data_desc == 0),
        "nrow": len(uvw),
    }


def check_export(inputs, export):
    """Equality of the core's reads with task C's python-casacore export."""
    with np.load(export) as saved:
        return {
            key: bool(np.array_equal(inputs[key], saved[key]))
            for key in ("UVW", "WEIGHT_SPECTRUM", "CHAN_FREQ", "PHASE_DIR")
        }


def image_job(inputs, checkpoint, grid=GRID, channels=CHANNELS, robust=ROBUST):
    """One archived job on the core: Stokes I, Briggs weights, inversion.

    `inputs` is `read_ms_inputs` of the job's backup MS and `checkpoint` the
    archived `<label>-written.npz` (`CORRECTED_DATA`, `FLAG`, `FLAG_ROW`).
    Returns the dirty image and PSF (`(height, width)`, FITS pixel order),
    the gridder's counters and the stage times.
    """
    lo, hi = channels
    start = time.perf_counter()
    data = np.ascontiguousarray(checkpoint["CORRECTED_DATA"][:, lo:hi], np.complex64)
    flags = np.ascontiguousarray(checkpoint["FLAG"][:, lo:hi], bool)
    flag_rows = np.asarray(checkpoint["FLAG_ROW"], bool)
    if data.shape != inputs["WEIGHT_SPECTRUM"].shape or len(flag_rows) != len(data):
        raise ValueError("checkpoint columns do not match the backup MS")
    sample, weight = core_weights.stokes_i(data, inputs["WEIGHT_SPECTRUM"], flags)
    padded = core_weights.padded_size(grid["width"], grid["padding"])
    padded_height = core_weights.padded_size(grid["height"], grid["padding"])
    imaging = core_weights.imaging_weights(
        inputs["UVW"],
        core_weights.wsclean_wavelengths(inputs["CHAN_FREQ"]),
        weight,
        inputs["rows"],
        mode="briggs",
        robust=robust,
        width=padded,
        height=padded_height,
        pixel_scale=core_weights.pixel_scale_radians(grid["scale_arcsec"]),
        return_grid=False,
    )
    # WSClean's row selection and FLAG_ROW: unselected rows carry a zero
    # imaging weight already; the gridder's reader skips flagged rows.
    gridder_weight = weight.copy()
    gridder_weight[flag_rows] = 0.0
    weighted = time.perf_counter()
    products = core_grid.invert(
        inputs["UVW"],
        inputs["CHAN_FREQ"],
        sample,
        gridder_weight,
        imaging["weights"],
        **grid,
    )
    gridded = time.perf_counter()
    products["imaging_weight_sums"] = imaging["sums"]
    products["seconds"] = {
        "stokes_and_weights": weighted - start,
        "grid": gridded - weighted,
    }
    return products


def _fits_header(inputs, stats, grid, robust):
    header = core_grid.wcs_header(
        inputs["PHASE_DIR"],
        grid["width"],
        grid["height"],
        grid["scale_arcsec"],
        inputs["CHAN_FREQ"],
    )
    extra = {
        "WSCDATAC": "CORRECTED_DATA",
        "WSCWEIGH": f"Briggs'({robust})",
        "WSCNITER": 0,
        "WSCNWLAY": int(stats["n_w_layers"]),
        "WSCVWSUM": float(stats["visibility_weight_sum"]),
        "WSCIMGWG": float(stats["image_weight"]),
        "WSCNORMF": float(stats["image_weight"]),
        "WSCNVIS": int(stats["gridded_count"]),
        "WSCENVIS": int(stats["gridded_count"]),
        "WSCGKRNL": int(grid["kernel_size"]),
    }
    return header, extra


def _archive_weight_check(archive_header, stats):
    """Criterion 1 against the archived FITS header of the same job."""
    checks = {}
    for key, value in (
        ("WSCVWSUM", stats["visibility_weight_sum"]),
        ("WSCIMGWG", stats["image_weight"]),
        ("WSCNORMF", stats["image_weight"]),
    ):
        expected = float(archive_header[key])
        checks[key] = {
            "core": float(value),
            "archive": expected,
            "relative_difference": abs(value - expected) / abs(expected),
        }
    checks["WSCNVIS"] = {
        "core": int(stats["gridded_count"]),
        "archive": int(archive_header["WSCNVIS"]),
        "equal": int(stats["gridded_count"]) == int(archive_header["WSCNVIS"]),
    }
    checks["pass"] = checks["WSCNVIS"]["equal"] and all(
        checks[k]["relative_difference"] <= TOLERANCES["weight_sums_relative"]
        for k in ("WSCVWSUM", "WSCIMGWG", "WSCNORMF")
    )
    return checks


def run(run_dir, archive_dir=DEFAULT_ARCHIVE, export_dir=DEFAULT_EXPORT):
    """The fifteen archived inversions on the core; `result.json` in the
    archive's raw layout plus the core's provenance, `side-effects.json`,
    and `images/<label>-{dirty,psf}.fits`."""
    run_dir, archive, export = Path(run_dir), Path(archive_dir), Path(export_dir)
    if run_dir.exists():
        raise FileExistsError(f"run directory exists: {run_dir}")
    if not (archive / "checkpoints").is_dir() or not (archive / "backups").is_dir():
        raise FileNotFoundError(f"archived imaging run required: {archive}")
    if not export.is_dir():
        raise FileNotFoundError(f"task C export for the read check: {export}")
    started = time.perf_counter()
    snapshot_before = _snapshot(archive)
    status_before = _git_status()
    run_dir.mkdir(parents=True)
    (run_dir / "images").mkdir()
    inputs, export_checks = {}, {}
    read_seconds = {}
    for role in ("response", "caracal"):
        t0 = time.perf_counter()
        inputs[role] = read_ms_inputs(archive / "backups" / f"{role}-input.ms")
        read_seconds[role] = time.perf_counter() - t0
        export_checks[role] = check_export(inputs[role], export / f"{role}-common.npz")
        if not all(export_checks[role].values()):
            raise RuntimeError(f"{role}: core reads differ from the export")
    records, all_images = {}, {}
    for label in JOBS:
        job_start = time.perf_counter()
        role = json.loads(
            (archive / "checkpoints" / f"{label}-result.json").read_text()
        )["role"]
        if role != ROLES[label]:
            raise RuntimeError(f"{label}: archived role {role} unexpected")
        checkpoint_path = archive / "checkpoints" / f"{label}-written.npz"
        with np.load(checkpoint_path) as saved:
            checkpoint = {k: saved[k] for k in saved.files}
        products = image_job(inputs[role], checkpoint)
        stats = products["stats"]
        header, extra = _fits_header(inputs[role], stats, GRID, ROBUST)
        t0 = time.perf_counter()
        for kind in ("dirty", "psf"):
            core_grid.write_fits(
                run_dir / "images" / f"{label}-{kind}.fits",
                products[kind],
                header,
                extra,
            )
        written = time.perf_counter()
        # The frozen reader of the archived driver: float32 FITS pixels,
        # geometry and header subset, exactly as the archive was measured.
        images, headers = flagging_imaging._read_images(run_dir / "images" / label)
        geometry = image_geometry(headers["dirty"])
        if geometry != image_geometry(headers["psf"]):
            raise RuntimeError("dirty image/PSF WCS mismatch")
        _, archive_header = read_fits(archive / "images" / f"{label}-dirty.fits")
        all_images[label] = images
        records[label] = {
            "role": role,
            "checkpoint_sha256": _sha256(checkpoint_path),
            "stats": stats,
            "imaging_weight_sums": products["imaging_weight_sums"],
            "weight_check_vs_archive_fits": _archive_weight_check(
                archive_header, stats
            ),
            "headers": headers,
            "image_geometry": geometry,
            "FITS_sha256": {
                kind: _sha256(run_dir / "images" / f"{label}-{kind}.fits")
                for kind in ("dirty", "psf")
            },
            "unsupported_original_TEST_samples": int(
                TEST_SAMPLES - int(np.asarray(checkpoint["support"]).sum())
            ),
            "diagnostics": image_diagnostics(images["dirty"]),
            "selected_for_policy_or_deployment": False,
            "seconds": {
                **products["seconds"],
                "fits": written - t0,
                "total": time.perf_counter() - job_start,
            },
        }
        print(
            f"{label:28s} {role:8s} grid {products['seconds']['grid']:6.2f}s "
            f"NVIS {stats['gridded_count']} "
            f"IMGWG rel {records[label]['weight_check_vs_archive_fits']['WSCIMGWG']['relative_difference']:.1e}",
            flush=True,
        )
    basis = np.stack([all_images[job]["dirty"] for job in UNIT_JOBS])
    reference_fit = linear_image_fit(all_images["fixedG0-reference"]["dirty"], basis)
    psf_reference = all_images["fixedG0-reference"]["psf"]
    closures = {}
    for name in ("omitted", "complete"):
        delta = (
            all_images[f"{name}-total"]["dirty"]
            - all_images[f"{name}-direct"]["dirty"]
            - all_images[f"{name}-adaptation"]["dirty"]
        )
        closures[name] = float(np.max(np.abs(delta)))
    for label, record in records.items():
        record["PSF_linf_difference_vs_fixedG0"] = float(
            np.max(np.abs(all_images[label]["psf"] - psf_reference))
        )
        if label in FITTED_JOBS or label in UNIT_JOBS:
            fit = linear_image_fit(all_images[label]["dirty"], basis)
            record["known_family_dirty_fit"] = fit
            record["conditional_response_vs_fixedG0"] = (
                (
                    np.asarray(fit["coefficients_jy"])
                    / reference_fit["coefficients_jy"]
                ).tolist()
                if fit["available"]
                and reference_fit["available"]
                and label in FITTED_JOBS
                else None
            )
    seconds_total = time.perf_counter() - started
    result = {
        "status": "core replay of the archived dirty-image family; not deconvolved/blind astronomy",
        "settings": SETTINGS,
        "grid": GRID,
        "channels": list(CHANNELS),
        "jobs": records,
        "reference_fit": reference_fit,
        "dirty_image_closures_jy_per_beam": closures,
        "actual_WSClean_inversions": 0,
        "actual_core_inversions": len(records),
        "new_QC_solves": 0,
        "policy_selection": False,
        "exported_or_deployable_MS": False,
        "provenance": {
            "archive": str(archive),
            "export": str(export),
            "export_checks": export_checks,
            "core_library_sha256": _sha256(core.library_path()),
            "module_sha256": _module_sha256(),
            "ms_read_seconds": read_seconds,
        },
        "seconds_total": seconds_total,
        "limitations": [
            "replay of checkpointed CORRECTED_DATA/FLAG columns; no gain solve, correction or injection is recomputed",
            "WSClean's Gaussian beam fit (BMAJ/BMIN/BPA) is not ported; no restored image",
            "the archived family's own limitations apply unchanged",
        ],
    }
    _write_json(run_dir / "result.json", result)
    snapshot_after = _snapshot(archive)
    audit = {
        "stage": "imaging",
        "inputs": [str(archive), str(export)],
        "input_files_checked": len(snapshot_before),
        "inputs_unchanged": snapshot_before == snapshot_after,
        "git_status_unchanged": status_before == _git_status(),
        "run_dir_files": sorted(p.name for p in run_dir.iterdir()),
        "images_written": len(list((run_dir / "images").iterdir())),
        "seconds": seconds_total,
    }
    _write_json(run_dir / "side-effects.json", audit)
    print(json.dumps({"stage": "imaging", "seconds": seconds_total, **audit}))
    return result


def compare(result, oracle, receipt, candidate_images=None, reference_images=None):
    """Compare a replay with an oracle (the archive or the host reproduction)
    and, when image directories are given, the pixels; write the receipt and
    exit nonzero on failure (the recipe's compare cab)."""
    archived = json.loads(Path(oracle).read_text())
    archived = archived.get("raw_result", archived)
    replay = json.loads(Path(result).read_text())
    replay = replay.get("raw_result", replay)
    report = compare_replay(archived, replay)
    report["result"], report["oracle"] = str(result), str(oracle)
    if candidate_images is not None or reference_images is not None:
        if candidate_images is None or reference_images is None:
            raise ValueError("both image directories are required")
        report["pixels"] = pixel_comparison(reference_images, candidate_images)
        report["passed"] = bool(report["passed"] and report["pixels"]["passed"])
    report["comparator_sha256"] = _sha256(__file__)
    Path(receipt).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "failures": len(report["failures"]),
                "classes": {
                    k: [v["compared"], v["worst"]] for k, v in report["classes"].items()
                },
                "pixels": report.get("pixels", {}).get("summary"),
            }
        )
    )
    if not report["passed"]:
        raise SystemExit(1)
    return report


def _parser():
    parser = argparse.ArgumentParser(
        prog="python -m rang.core_imaging",
        description="The archived imaging track on the Rust core, without WSClean.",
    )
    sub = parser.add_subparsers(dest="stage", required=True)
    p = sub.add_parser("run", help="image the fifteen archived jobs")
    p.add_argument("run_dir")
    p.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE))
    p.add_argument("--export-dir", default=str(DEFAULT_EXPORT))
    p = sub.add_parser("compare", help="compare a replay with an oracle")
    p.add_argument("result")
    p.add_argument("receipt")
    p.add_argument("--oracle", default=str(DEFAULT_ORACLE))
    p.add_argument("--images", nargs=2, metavar=("CANDIDATE", "REFERENCE"))
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.stage == "run":
        return run(args.run_dir, args.archive_dir, args.export_dir)
    images = args.images or (None, None)
    return compare(args.result, args.oracle, args.receipt, *images)


if __name__ == "__main__":
    main()


__all__ = [
    "CHANNELS",
    "FITTED_JOBS",
    "GRID",
    "JOBS",
    "ROLES",
    "SIZE",
    "TEST_SAMPLES",
    "TOLERANCES",
    "UNIT_JOBS",
    "check_export",
    "classify_replay",
    "compare",
    "compare_replay",
    "image_job",
    "main",
    "pixel_comparison",
    "pixel_record",
    "read_fits",
    "read_ms_inputs",
    "run",
]
