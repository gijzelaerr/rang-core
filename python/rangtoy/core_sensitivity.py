"""WSClean approximation sensitivity of the frozen fifteen-job imaging family.

Verbatim extract of the frozen `rangtoy.imaging_sensitivity` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/imaging_sensitivity.py at commit
2da566c (now history/python/imaging_sensitivity.py),
sha256 1cd310245d138c35a566bb146cc0a689e7e5a10d2b09e6442c0b6ba817a75f60.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

from hashlib import sha256

import numpy as np

from .core_compare import compare, key_and_parent
from .core_image_fit import linear_image_fit

DEFAULTS = {"kernel_size": 7, "oversampling": 1023, "w_layers": 64}


FLAGS = {
    "kernel_size": "-wstack-kernel-size",
    "oversampling": "-wstack-oversampling",
    "w_layers": "-wstack-nwlayers",
}


JOBS = (
    "unit-compact",
    "unit-extended",
    "fixedG0-reference",
    "clean-full",
    "omitted-full",
    "omitted-total",
    "omitted-direct",
    "omitted-adaptation",
    "complete-full",
    "complete-total",
    "complete-direct",
    "complete-adaptation",
    "caracal-no-change",
    "caracal-mild",
    "caracal-firstpass-rejected",
)


ROLES = {job: ("caracal" if job.startswith("caracal") else "response") for job in JOBS}


UNIT_JOBS = ("unit-compact", "unit-extended")


FITTED_JOBS = tuple(
    job
    for job in JOBS
    if ROLES[job] == "response"
    and not job.endswith("full")
    and not job.startswith("unit-")
)


# Header keys that depend only on the imaging weights, never on the kernel.
WEIGHT_KEYS = ("WSCVWSUM", "WSCNVIS", "WSCIMGWG", "WSCNORMF", "WSCENVIS")


ADJACENT = (
    "kernel-5",
    "kernel-9",
    "oversampling-511",
    "oversampling-2047",
    "wlayers-32",
    "wlayers-128",
)


def variants():
    """The frozen variant grid: defaults, one-at-a-time, and two combinations."""
    grid = [("default", dict(DEFAULTS))]
    for size in (3, 5, 9, 11, 15):
        grid.append((f"kernel-{size}", {**DEFAULTS, "kernel_size": size}))
    for factor in (63, 255, 511, 2047, 4095):
        grid.append((f"oversampling-{factor}", {**DEFAULTS, "oversampling": factor}))
    for layers in (1, 4, 16, 32, 128, 256):
        grid.append((f"wlayers-{layers}", {**DEFAULTS, "w_layers": layers}))
    grid.append(
        ("coarse-3-63-1", {"kernel_size": 3, "oversampling": 63, "w_layers": 1})
    )
    grid.append(
        ("fine-15-4095-256", {"kernel_size": 15, "oversampling": 4095, "w_layers": 256})
    )
    return dict(grid)


def variant_command(command, variant, prefix, tempdir, ms):
    """The archived command with the three gridding options set and paths moved.

    ``command`` is an archived ``*-command.json`` list. Any existing
    ``-wstack-nwlayers`` pair is replaced; the kernel and oversampling options
    are appended before the MS path. Only ``-name``, ``-temp-dir`` and the MS
    path change; every other frozen setting is kept verbatim.
    """
    command = list(command)
    if command[-1].endswith(".ms") is False:
        raise ValueError("archived command must end with the MS path")
    out = []
    skip = 0
    for index, token in enumerate(command[:-1]):
        if skip:
            skip -= 1
            continue
        if token in FLAGS.values():
            skip = 1
            continue
        if token == "-name":
            out.extend(["-name", str(prefix)])
            skip = 1
            continue
        if token == "-temp-dir":
            out.extend(["-temp-dir", str(tempdir)])
            skip = 1
            continue
        out.append(token)
    for key in ("kernel_size", "oversampling", "w_layers"):
        value = int(variant[key])
        if value < 1 or (key == "kernel_size" and value % 2 == 0):
            raise ValueError(f"invalid {key} {value}")
        out.extend([FLAGS[key], str(value)])
    out.append(str(ms))
    return out


def pixel_digest(image):
    """SHA256 of the float32 pixel array, independent of FITS headers."""
    return sha256(np.ascontiguousarray(image, np.float32).tobytes()).hexdigest()


def classify_reproduction(path):
    """Classes for comparing an archived imaging result with a rerun of it.

    FITS file hashes differ between runs because WSClean writes the output path
    into HISTORY; wall times, backup digests and allocation counters are run
    specific. Everything else that the archived run computed from pixels or
    columns must agree.
    """
    key, parent = key_and_parent(path)
    if key in (
        "seconds_emulated_not_native_benchmark",
        "allocated_bytes_before_final_result",
        "whole_MS_backup_digests",
        "FITS_sha256",
    ):
        return "excluded"
    if (
        key == "precast_visibility_closures_jy"
        or parent == "precast_visibility_closures_jy"
    ):
        return "reported"
    if key in ("unweighted_pixel_MSE_proxy", "wide_to_native_max_rounding_jy"):
        return "difference"
    if key in ("coefficients_jy", "conditional_response_vs_fixedG0"):
        return "difference"
    if key in (
        "condition",
        "dirty_offsource_RMS_jy_per_beam",
        "dirty_offsource_std_jy_per_beam",
        "peak_abs_jy_per_beam",
        "PSF_linf_difference_vs_fixedG0",
        "BMAJ",
        "BMIN",
        "BPA",
        "WSCVWSUM",
    ) or parent in ("dirty_image_closures_jy_per_beam",):
        return "float"
    return "exact"


def compare_reproduction(archived, rerun):
    """Compare an archived raw imaging result with a rerun (phase 3 comparator)."""
    return compare(
        archived, rerun, classify_reproduction, float_tol=1e-9, difference_abs=1e-12
    )


def job_metrics(label, images, header, basis, reference_fit, psf_reference):
    """The archived per-job metrics recomputed for one variant's images."""
    from .core_image_fit import image_diagnostics

    record = {
        "pixel_sha256": {kind: pixel_digest(images[kind]) for kind in ("dirty", "psf")},
        "beam": {key: header.get(key) for key in ("BMAJ", "BMIN", "BPA")},
        "weights": {key: header.get(key) for key in WEIGHT_KEYS},
        "kernel_header": header.get("WSCGKRNL"),
        "w_layers_header": header.get("WSCNWLAY"),
        "diagnostics": image_diagnostics(images["dirty"]),
        "PSF_linf_difference_vs_fixedG0": float(
            np.max(np.abs(images["psf"] - psf_reference))
        ),
    }
    if label in FITTED_JOBS or label in UNIT_JOBS:
        fit = linear_image_fit(images["dirty"], basis)
        record["known_family_dirty_fit"] = fit
        record["conditional_response_vs_fixedG0"] = (
            (
                np.asarray(fit["coefficients_jy"]) / reference_fit["coefficients_jy"]
            ).tolist()
            if fit["available"] and reference_fit["available"] and label in FITTED_JOBS
            else None
        )
    return record


def variant_metrics(all_images, headers):
    """Reference fit, closures and per-job metrics for one variant."""
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
    jobs = {
        job: job_metrics(
            job, all_images[job], headers[job], basis, reference_fit, psf_reference
        )
        for job in JOBS
    }
    return {
        "reference_fit": reference_fit,
        "dirty_image_closures_jy_per_beam": closures,
        "jobs": jobs,
    }


def pixel_differences(images, reference_images):
    """L-infinity and RMS pixel differences against the default variant."""
    out = {}
    for kind in ("dirty", "psf"):
        delta = np.asarray(images[kind], float) - np.asarray(
            reference_images[kind], float
        )
        peak = float(np.max(np.abs(reference_images[kind])))
        linf = float(np.max(np.abs(delta)))
        out[kind] = {
            "linf": linf,
            "rms": float(np.sqrt(np.mean(delta**2))),
            "reference_peak": peak,
            "linf_relative_to_peak": linf / peak if peak else None,
        }
    return out


def _rel(value, reference):
    if reference == 0:
        return abs(value)
    return abs(value - reference) / abs(reference)


def spread(results, reference="default"):
    """Per-variant movement of the science metrics against the default variant.

    ``results`` maps variant name to the output of :func:`variant_metrics`
    with an added ``"pixels"`` entry from :func:`pixel_differences` per job.
    Flux movements are relative to the default coefficient; response
    movements are absolute (they are already fractions).
    """
    base = results[reference]
    table = {}
    for name, result in results.items():
        if name == reference:
            continue
        flux = []
        response = []
        for job in FITTED_JOBS:
            fit = result["jobs"][job]["known_family_dirty_fit"]
            fit0 = base["jobs"][job]["known_family_dirty_fit"]
            if not (fit["available"] and fit0["available"]):
                flux.append(float("inf"))
                continue
            flux.extend(
                _rel(a, b)
                for a, b in zip(
                    fit["coefficients_jy"], fit0["coefficients_jy"], strict=True
                )
            )
            response.extend(
                abs(a - b)
                for a, b in zip(
                    result["jobs"][job]["conditional_response_vs_fixedG0"],
                    base["jobs"][job]["conditional_response_vs_fixedG0"],
                    strict=True,
                )
            )
        reference_flux = [
            _rel(a, b)
            for a, b in zip(
                result["reference_fit"]["coefficients_jy"],
                base["reference_fit"]["coefficients_jy"],
                strict=True,
            )
        ]
        weights_equal = all(
            result["jobs"][job]["weights"] == base["jobs"][job]["weights"]
            for job in JOBS
        )
        table[name] = {
            "max_relative_flux_change": max(flux + reference_flux),
            "max_absolute_response_change": max(response),
            "max_dirty_linf_jy_per_beam": max(
                result["jobs"][job]["pixels"]["dirty"]["linf"] for job in JOBS
            ),
            "max_dirty_linf_relative_to_peak": max(
                result["jobs"][job]["pixels"]["dirty"]["linf_relative_to_peak"]
                for job in JOBS
            ),
            "max_psf_linf": max(
                result["jobs"][job]["pixels"]["psf"]["linf"] for job in JOBS
            ),
            "max_offsource_rms_relative_change": max(
                _rel(
                    result["jobs"][job]["diagnostics"][
                        "dirty_offsource_RMS_jy_per_beam"
                    ],
                    base["jobs"][job]["diagnostics"]["dirty_offsource_RMS_jy_per_beam"],
                )
                for job in JOBS
            ),
            "closures_jy_per_beam": result["dirty_image_closures_jy_per_beam"],
            "max_beam_relative_change": max(
                _rel(result["jobs"][job]["beam"][key], base["jobs"][job]["beam"][key])
                for job in JOBS
                for key in ("BMAJ", "BMIN", "BPA")
            ),
            "weight_headers_equal_default": weights_equal,
        }
    return table


def proposed_tolerances(table, float32_floor=2.0**-23):
    """Phase 4 tolerances from the measured spread (rule frozen before measuring).

    The smallest movement among the six variants adjacent to the defaults is
    the finest approximation change WSClean itself makes; a port that differs
    from WSClean at matched settings by a tenth of that is indistinguishable
    from such a change. The float32 FITS resolution relative to the peak is a
    floor below which no FITS comparison can resolve a difference.
    """
    adjacent = [table[name] for name in ADJACENT if name in table]
    if len(adjacent) != len(ADJACENT):
        raise ValueError("all six adjacent variants are required")
    smallest_pixel = min(x["max_dirty_linf_relative_to_peak"] for x in adjacent)
    smallest_psf = min(x["max_psf_linf"] for x in adjacent)
    smallest_flux = min(x["max_relative_flux_change"] for x in adjacent)
    smallest_response = min(x["max_absolute_response_change"] for x in adjacent)
    return {
        "rule": "one tenth of the smallest adjacent-variant movement, floored at float32 resolution",
        "dirty_pixel_linf_relative_to_peak": max(smallest_pixel / 10, float32_floor),
        "psf_pixel_linf": max(smallest_psf / 10, float32_floor),
        "template_flux_relative": max(smallest_flux / 10, float32_floor),
        "response_fraction_absolute": max(smallest_response / 10, float32_floor),
        "weight_sums_relative": 1e-9
        if all(x["weight_headers_equal_default"] for x in adjacent)
        else None,
        "adjacent_variants": list(ADJACENT),
        "smallest_adjacent": {
            "dirty_pixel_linf_relative_to_peak": smallest_pixel,
            "psf_pixel_linf": smallest_psf,
            "template_flux_relative": smallest_flux,
            "response_fraction_absolute": smallest_response,
        },
    }
