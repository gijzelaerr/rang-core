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

import math
from pathlib import Path

import numpy as np

from .flagging_imaging import IMAGE_CLOSURE_JY
from .imaging_sensitivity import FITTED_JOBS, JOBS, ROLES, UNIT_JOBS

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


__all__ = [
    "CHANNELS",
    "FITTED_JOBS",
    "JOBS",
    "ROLES",
    "SIZE",
    "TEST_SAMPLES",
    "TOLERANCES",
    "UNIT_JOBS",
    "classify_replay",
    "compare_replay",
    "pixel_comparison",
    "pixel_record",
    "read_fits",
]
