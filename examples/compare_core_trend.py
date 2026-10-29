"""Compare a trend result on the core mirror with the archive (research/core-phase3-trend.md).

Usage:
    python examples/compare_core_trend.py <trend result.json> <archive.json> <receipt.json> [--posthoc-slope-scale]
"""

import json
import sys
from pathlib import Path

from rangtoy.core_compare import compare

EXCLUDED = {"configuration", "allocated_bytes", "source_digest", "runtime_receipts"}
FLOATS = {
    "slopes_time_rad_per_second_frequency_rad_per_hz",
    "primary_polar_TV",
    "detrended_guidance_TV",
}


def classify(path):
    keys = [p for p in path if isinstance(p, str)]
    if any(k in EXCLUDED or "sha256" in k or "digest" in k for k in keys):
        return "excluded"
    if any(k in FLOATS for k in keys):
        return "float"
    return "exact"


SLOPES = "slopes_time_rad_per_second_frequency_rad_per_hz"


def posthoc_slopes(archive, result, tol=1e-9):
    """Post-hoc criterion 3b (research/core-phase3-trend.md).

    The slopes of the reference antenna are rounding-level zeros, so each slope
    is compared with the largest absolute slope of its axis in the same record.
    """
    worst, failures = 0.0, []
    pairs = zip(archive["records"], result["records"], strict=True)
    for i, (a, c) in enumerate(pairs):
        if a[SLOPES] is None or c[SLOPES] is None:
            if a[SLOPES] != c[SLOPES]:
                failures.append({"record": i, "reason": "availability differs"})
            continue
        for axis in (0, 1):
            scale = max(abs(s[axis]) for s in a[SLOPES])
            for antenna, (x, y) in enumerate(zip(a[SLOPES], c[SLOPES], strict=True)):
                d = abs(x[axis] - y[axis]) / scale
                worst = max(worst, d)
                if d > tol:
                    failures.append(
                        {"record": i, "antenna": antenna, "axis": axis, "scaled": d}
                    )
    return {"worst_scaled_difference": worst, "failures": failures}


def main():
    posthoc = sys.argv[4:] == ["--posthoc-slope-scale"]
    result_path, archive_path, receipt = (Path(x) for x in sys.argv[1:4])
    result = json.loads(result_path.read_text())
    archive = json.loads(archive_path.read_text())["raw_result"]
    report = compare(archive, result, classify)
    if posthoc:
        frozen = [
            f
            for f in report["failures"]
            if SLOPES in [p for p in f["path"] if isinstance(p, str)]
        ]
        report["frozen_slope_failures"] = frozen
        report["failures"] = [f for f in report["failures"] if f not in frozen]
        report["posthoc_slopes"] = posthoc_slopes(archive, result)
        report["failures"] += report["posthoc_slopes"]["failures"]
    report["passed"] = not report["failures"]
    report["inputs"] = {"result": str(result_path), "archive": str(archive_path)}
    receipt.write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "failures": len(report["failures"]),
                "classes": report["classes"],
                "excluded": report["excluded"],
            }
        )
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
