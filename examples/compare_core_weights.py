"""Compare the core's imaging weights and Stokes I with the WSClean oracle.

Protocol: research/core-b-weighting.md. Two modes:

* ``--oracle-only``: the comparator precondition. Checks the rerun images and
  header sums against the archive, the repeated WSClean runs against the first
  runs (WSClean's own reproducibility), and the structure of the stored
  ``IMAGING_WEIGHT_SPECTRUM`` column. Prints the measured spreads and the
  tolerance the rule derives from them.
* default: runs the core on every oracle job and evaluates the frozen
  criteria 1-5 and 7, writing ``compare.json`` next to the oracle.

    .venv/bin/python examples/compare_core_weights.py outputs/core-b-20261030-01
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

IMAGE_TOLERANCE_JY = 1e-6
HEADER_RELATIVE = 1e-9
FLOAT32_FOUR_ULPS = 4 * 2.0**-23
CHANNELS = (1024, 3072)
SIZE = 512
PADDING = 1.2
SCALE = 8.0 * np.pi / (180.0 * 60.0 * 60.0)
ROBUST = 0.5
RANK_FILTER = (3.0, 16)


def load_runs(output):
    runs = {}
    for path in sorted((output / "oracle").glob("*.json")):
        if path.name == "summary.json":
            continue
        record = json.loads(path.read_text())
        record["arrays"] = np.load(output / "oracle" / f"{record['name']}.npz")
        runs[record["name"]] = record
    return runs


def selected_rows(arrays):
    return (
        (arrays["FIELD_ID"] == 0)
        & (arrays["ANTENNA1"] != arrays["ANTENNA2"])
        & (arrays["DATA_DESC_ID"] == 0)
    )


def relative_spread(a, b):
    """Max relative difference on the non-zero cells, after a pattern check."""
    pattern = np.array_equal(a != 0, b != 0)
    mask = (a != 0) & (b != 0)
    if not mask.any():
        return pattern, 0.0
    a64 = a[mask].astype(np.float64)
    b64 = b[mask].astype(np.float64)
    return pattern, float(np.max(np.abs(a64 - b64) / np.abs(b64)))


def column_structure(arrays):
    w = arrays["IMAGING_WEIGHT_SPECTRUM"]
    lo, hi = CHANNELS
    rows = selected_rows(arrays)
    checks = {
        "xx_equals_yy": bool(np.array_equal(w[..., 0], w[..., 3])),
        "xy_yx_zero": bool(not np.any(w[..., 1]) and not np.any(w[..., 2])),
        "outside_range_zero": bool(not np.any(w[:, :lo]) and not np.any(w[:, hi:])),
        "unselected_rows_zero": bool(not np.any(w[~rows])),
        "selected_rows": int(rows.sum()),
    }
    checks["pass"] = all(v for k, v in checks.items() if k != "selected_rows")
    return checks


def oracle_only(runs):
    report = {"archive": {}, "repeat": {}, "structure": {}}
    worst_image = 0.0
    worst_header = 0.0
    for name, run in runs.items():
        report["structure"][name] = column_structure(run["arrays"])
        if run["archive_label"] is not None:
            checks = run["archive_checks"]
            image = max(c["max_abs_pixel_difference"] for c in checks.values())
            header = max(c["header_max_relative_difference"] for c in checks.values())
            worst_image = max(worst_image, image)
            worst_header = max(worst_header, header)
            report["archive"][name] = {
                "max_abs_pixel_difference": image,
                "header_max_relative_difference": header,
                "pass": image <= IMAGE_TOLERANCE_JY and header <= HEADER_RELATIVE,
            }
    repeat_spread = 0.0
    for name, run in runs.items():
        if not name.endswith("--repeat"):
            continue
        first = runs[name[: -len("--repeat")]]
        pattern, spread = relative_spread(
            run["arrays"]["IMAGING_WEIGHT_SPECTRUM"],
            first["arrays"]["IMAGING_WEIGHT_SPECTRUM"],
        )
        identical = bool(
            np.array_equal(
                run["arrays"]["IMAGING_WEIGHT_SPECTRUM"],
                first["arrays"]["IMAGING_WEIGHT_SPECTRUM"],
            )
        )
        pixels = max(
            float(
                np.max(
                    np.abs(
                        run["arrays"][f"{k}_pixels"] - first["arrays"][f"{k}_pixels"]
                    )
                )
            )
            for k in ("dirty", "psf")
        )
        repeat_spread = max(repeat_spread, spread)
        report["repeat"][name] = {
            "pattern_identical": pattern,
            "weights_identical": identical,
            "max_relative_weight_difference": spread,
            "max_abs_pixel_difference": pixels,
        }
    report["summary"] = {
        "worst_image_difference_jy": worst_image,
        "worst_header_relative_difference": worst_header,
        "wsclean_repeat_relative_spread": repeat_spread,
        "derived_tolerance": max(FLOAT32_FOUR_ULPS, repeat_spread),
        "archive_pass": all(v["pass"] for v in report["archive"].values()),
        "structure_pass": all(v["pass"] for v in report["structure"].values()),
        "repeat_pattern_pass": all(
            v["pattern_identical"] for v in report["repeat"].values()
        ),
    }
    return report


def numpy_stokes_i(data, weights, flags):
    """Items 3 and 8 of the protocol in NumPy float32 arithmetic."""
    xx = data[..., 0]
    yy = data[..., 3]
    vis = (xx + yy) * np.float32(0.5)
    finite = np.isfinite(vis.real) & np.isfinite(vis.imag)
    vis = np.where(finite, vis, np.complex64(0)).astype(np.complex64)
    ok_xx = ~flags[..., 0] & np.isfinite(xx.real) & np.isfinite(xx.imag)
    ok_yy = ~flags[..., 3] & np.isfinite(yy.real) & np.isfinite(yy.imag)
    wxx = weights[..., 0] * np.float32(4)
    wyy = weights[..., 3] * np.float32(4)
    weight = np.where(ok_xx & ok_yy, np.minimum(wxx, wyy), np.float32(0))
    return vis, weight.astype(np.float32)


def core_job(run, tolerance):
    from rangtoy import core_weights

    arrays = run["arrays"]
    lo, hi = CHANNELS
    rows = selected_rows(arrays)
    data = np.ascontiguousarray(arrays["CORRECTED_DATA"][:, lo:hi])
    weights = np.ascontiguousarray(arrays["WEIGHT_SPECTRUM"][:, lo:hi])
    flags = np.ascontiguousarray(arrays["FLAG"][:, lo:hi])
    mode = run["mode"]
    t0 = time.perf_counter()
    vis, weight = core_weights.stokes_i(data, weights, flags)
    stokes_seconds = time.perf_counter() - t0
    oracle_vis, oracle_weight = numpy_stokes_i(data, weights, flags)
    width = height = core_weights.padded_size(SIZE, PADDING)
    t0 = time.perf_counter()
    result = core_weights.imaging_weights(
        arrays["UVW"],
        arrays["WAVELENGTH"][lo:hi],
        weight,
        rows,
        mode=mode,
        robust=ROBUST,
        width=width,
        height=height,
        pixel_scale=SCALE,
        rank_filter=RANK_FILTER,
    )
    weight_seconds = time.perf_counter() - t0
    oracle = arrays["IMAGING_WEIGHT_SPECTRUM"][:, lo:hi, 0]
    pattern, spread = relative_spread(result["weights"], oracle)
    sums = core_weights.weight_sums(weight, result["weights"])
    header = run["rerun_header"]["psf"]
    archive_header = (
        run["archive_checks"]["psf"]["archive_header"]
        if run["archive_label"] is not None
        else header
    )
    sum_checks = {}
    for key, value in (
        ("WSCVWSUM", sums["visibility_weight_sum"]),
        ("WSCIMGWG", sums["total_weight"]),
        ("WSCNVIS", float(sums["count"])),
    ):
        expected = archive_header[key]
        sum_checks[key] = {
            "core": value,
            "archive": expected,
            "relative_difference": abs(value - expected) / max(abs(expected), 1e-300),
        }
    out = {
        "mode": mode,
        "stokes_i_exact": bool(np.array_equal(vis, oracle_vis)),
        "stokes_weight_exact": bool(np.array_equal(weight, oracle_weight)),
        "weights_pattern_identical": pattern,
        "weights_max_relative_difference": spread,
        "weights_identical": bool(np.array_equal(result["weights"], oracle)),
        "weights_pass": pattern and spread <= tolerance,
        "sums": sum_checks,
        "sums_pass": all(
            v["relative_difference"] <= HEADER_RELATIVE for v in sum_checks.values()
        ),
        "seconds": {
            "stokes_i": stokes_seconds,
            "imaging_weights": weight_seconds,
            "grid_cells_nonzero": int(np.count_nonzero(result["grid"])),
        },
    }
    out["pass"] = (
        out["stokes_i_exact"]
        and out["stokes_weight_exact"]
        and out["weights_pass"]
        and out["sums_pass"]
    )
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--oracle-only", action="store_true")
    parser.add_argument("--tolerance", type=float, default=None)
    args = parser.parse_args()
    runs = load_runs(args.output)
    report = {"precondition": oracle_only(runs)}
    if args.oracle_only:
        print(json.dumps(report["precondition"]["summary"], indent=2))
        (args.output / "precondition.json").write_text(
            json.dumps(report["precondition"], indent=2)
        )
        return
    tolerance = args.tolerance
    if tolerance is None:
        raise SystemExit("--tolerance is the frozen value from the protocol")
    report["tolerance"] = tolerance
    report["jobs"] = {}
    for name, run in runs.items():
        if name.endswith("--repeat"):
            continue
        report["jobs"][name] = core_job(run, tolerance)
        print(name, "PASS" if report["jobs"][name]["pass"] else "FAIL", file=sys.stderr)
    briggs = [j for j in report["jobs"].values() if j["mode"] == "briggs"]
    extra = [j for j in report["jobs"].values() if j["mode"] != "briggs"]
    report["criteria"] = {
        "1_reproduction": report["precondition"]["summary"]["archive_pass"],
        "2_briggs_weights": all(j["weights_pass"] for j in briggs)
        and report["precondition"]["summary"]["structure_pass"],
        "3_uniform_natural": all(j["weights_pass"] for j in extra),
        "4_stokes_i": all(
            j["stokes_i_exact"] and j["stokes_weight_exact"] for j in briggs
        ),
        "5_header_sums": all(j["sums_pass"] for j in briggs),
        "max_relative_weight_difference": max(
            j["weights_max_relative_difference"] for j in report["jobs"].values()
        ),
        "max_sum_relative_difference": max(
            v["relative_difference"]
            for j in report["jobs"].values()
            for v in j["sums"].values()
        ),
    }
    (args.output / "compare.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["criteria"], indent=2))


if __name__ == "__main__":
    main()
