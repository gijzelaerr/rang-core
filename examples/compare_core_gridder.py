"""Pixel comparison of two sets of dirty and PSF FITS images
(research/core-c-gridder.md, criteria 4 and 7).

    python examples/compare_core_gridder.py REFERENCE CANDIDATE OUTPUT.json

REFERENCE and CANDIDATE are directories holding `<label>-dirty.fits` and
`<label>-psf.fits` for the fifteen archived imaging jobs. For every job and
kind the script reports the maximum absolute difference, the RMS difference,
the maximum difference relative to the reference peak, and whether the WCS
keys agree (floats to 1e-9 degrees). Running it on the archive against the
WSClean rerun is the comparator precondition; on the archive against the
core output it is the measurement.
"""

import json
import sys
from pathlib import Path

import numpy as np

LABELS = (
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
WCS_TOLERANCE = 1e-9


def read(path):
    from astropy.io import fits

    with fits.open(str(path), memmap=False) as hdus:
        return np.asarray(hdus[0].data, np.float64).squeeze(), hdus[0].header


def compare(reference, candidate):
    ref, ref_header = read(reference)
    cand, cand_header = read(candidate)
    if ref.shape != cand.shape:
        raise RuntimeError(f"shape mismatch {ref.shape} vs {cand.shape}")
    delta = cand - ref
    peak = float(np.max(np.abs(ref)))
    wcs_equal = True
    for key in WCS_KEYS:
        a, b = ref_header[key], cand_header[key]
        if isinstance(a, str):
            wcs_equal &= a == b
        else:
            wcs_equal &= abs(float(a) - float(b)) <= WCS_TOLERANCE
    return {
        "max_abs_difference": float(np.max(np.abs(delta))),
        "rms_difference": float(np.sqrt(np.mean(delta**2))),
        "reference_peak": peak,
        "max_relative_to_peak": float(np.max(np.abs(delta)) / peak) if peak else None,
        "argmax_difference": [
            int(v) for v in np.unravel_index(np.argmax(np.abs(delta)), delta.shape)
        ],
        "finite": bool(np.isfinite(cand).all()),
        "wcs_equal": bool(wcs_equal),
        "wcs": {key: cand_header[key] for key in WCS_KEYS},
    }


def main(reference, candidate, output):
    reference, candidate = Path(reference), Path(candidate)
    results = {"reference": str(reference), "candidate": str(candidate), "jobs": {}}
    print(
        f"{'job':28s} {'kind':5s} {'max|d|':>10s} {'rms':>10s} {'peak':>9s} {'max|d|/peak':>11s} wcs"
    )
    for label in LABELS:
        results["jobs"][label] = {}
        for kind in ("dirty", "psf"):
            record = compare(
                reference / f"{label}-{kind}.fits", candidate / f"{label}-{kind}.fits"
            )
            results["jobs"][label][kind] = record
            print(
                f"{label:28s} {kind:5s} {record['max_abs_difference']:10.3e} "
                f"{record['rms_difference']:10.3e} {record['reference_peak']:9.4g} "
                f"{record['max_relative_to_peak']:11.3e} {record['wcs_equal']}"
            )
    results["summary"] = {
        kind: {
            "max_abs_difference": max(
                j[kind]["max_abs_difference"] for j in results["jobs"].values()
            ),
            "max_relative_to_peak": max(
                j[kind]["max_relative_to_peak"] for j in results["jobs"].values()
            ),
            "max_rms_difference": max(
                j[kind]["rms_difference"] for j in results["jobs"].values()
            ),
        }
        for kind in ("dirty", "psf")
    }
    results["criterion_4_wcs"] = all(
        j[kind]["wcs_equal"]
        for j in results["jobs"].values()
        for kind in ("dirty", "psf")
    )
    Path(output).write_text(json.dumps(results, indent=2, sort_keys=True))
    print("summary", json.dumps(results["summary"]), "wcs", results["criterion_4_wcs"])


if __name__ == "__main__":
    main(*sys.argv[1:4])
