"""Compare a core prospective result with an oracle (research/core-phase3b.md).

Usage:
    python examples/compare_core_prospective.py <core result.json> <oracle.json> <receipt.json>

The oracle is either the archive (its `raw_result_projection` is used) or a
host reproduction's raw `result.json`. Field classes follow the frozen
criteria 1-5; the receipt also carries the reported margins (criterion 6).
"""

import json
import sys
from pathlib import Path

from rangtoy.core_compare import compare, key_and_parent

EXCLUDED = {
    "seconds",
    "native_response_seconds",
    "full_training_normals_seconds",
    "allocated_bytes",
    "audit",
    "configuration",
    "status",
    "limitations",
}
FLOATS = {
    "tv",
    "raw_tv",
    "time_tv",
    "frequency_tv",
    "scale",
    "valid_gain_fraction",
    "added_fraction",
    "fixed_support_tv",
    "objective",
    "predicted_fixed_tv",
    "predicted_validation_MSE",
    "predicted_objective",
    "test_MSE",
    "residual_score",
    "tv_score",
    "time",
    "largest_curvature",
    "smallest_retained_curvature",
    "condition",
    "damping",
    "max_relative_step",
}
DIFFERENCES = {"predicted_benefit", "predicted_cost_removed_benefit"}
REPORTED = {"baseline_projected_score_norm", "gauge_null_relative"}
CONFIG_EQUAL = (
    "iterations",
    "grid",
    "maximum_action_confirmations",
    "maximum_actual_QC_solves",
    "minimum_benefit",
    "test_or_truth_selects",
)


def classify(path):
    if any(p in EXCLUDED for p in path if isinstance(p, str)):
        return "excluded"
    key, parent = key_and_parent(path)
    if key in REPORTED:
        return "reported"
    if key in DIFFERENCES:
        return "difference"
    if key in FLOATS or parent == "losses":
        return "float"
    return "exact"


def main():
    core_path, oracle_path, receipt = (Path(x) for x in sys.argv[1:4])
    core = json.loads(core_path.read_text())
    oracle = json.loads(oracle_path.read_text())
    oracle = oracle.get("raw_result_projection", oracle)
    report = compare(oracle, core, classify)
    config = {
        k: oracle["configuration"].get(k) == core["configuration"].get(k)
        for k in CONFIG_EQUAL
    }
    report["configuration_equal"] = config
    if not all(config.values()):
        report["failures"].append({"path": ["configuration"], "reason": str(config)})
    report["selected"] = {
        c["case_id"]: {
            mode: [o["selected"][mode]["mask_id"], c["selected"][mode]["mask_id"]]
            for mode in o["selected"]
        }
        for o, c in zip(oracle["cases"], core["cases"], strict=True)
    }
    report["objective_margins"] = core.get("objective_margins")
    report["passed"] = not report["failures"]
    report["inputs"] = {"core": str(core_path), "oracle": str(oracle_path)}
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
