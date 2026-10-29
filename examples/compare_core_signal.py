"""Compare a core signal-track result with an oracle (research/core-phase3c-b.md).

Usage:
    python examples/compare_core_signal.py <core result.json> <oracle.json> <receipt.json>

The oracle is the archive (its `raw_result` is used) or a host reproduction's
result.json. Field classes follow the frozen criteria 1-5.
"""

import json
import sys
from pathlib import Path

from rangtoy.core_compare import compare, key_and_parent

EXCLUDED = {
    "seconds",
    "configuration",
    "audit",
    "acceptance_file_sha256",
    "observed_allocated_bytes_before_result",
    "imaging",
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
    "fixed_baseline_edge_TV",
    "objective",
    "flux_jy",
    "condition",
    "weighted_mse_proxy",
    "unexplained_weighted_response_energy_fraction",
    "response_fraction_vs_case_fixedG0",
    "same_mask_Jones_product_relative_drift",
    "injection_recall",
    "outside_injection_train_fraction",
}
DIFFERENCE_IN_REFERENCE = {
    "weighted_mse_proxy",
    "unexplained_weighted_response_energy_fraction",
}
REPORTED = {"visibility_closure_linf_jy", "coefficient_closure_linf_jy"}
CONFIG_EQUAL = (
    "seeds",
    "grid",
    "iterations",
    "maximum_QC_solves",
    "minimum_benefit",
    "probe_jy",
    "absolute_transfer_limit",
    "sources",
    "reference_hz",
)


def classify(path):
    keys = [p for p in path if isinstance(p, str)]
    if any(k in EXCLUDED for k in keys):
        return "excluded"
    key, parent = key_and_parent(path)
    if key in REPORTED:
        return "reported"
    if keys and keys[0] == "reference_fits" and key in DIFFERENCE_IN_REFERENCE:
        return "difference"
    if key in FLOATS or parent == "losses":
        return "float"
    return "exact"


def main():
    core_path, oracle_path, receipt = (Path(x) for x in sys.argv[1:4])
    core = json.loads(core_path.read_text())
    oracle = json.loads(oracle_path.read_text())
    oracle = oracle.get("raw_result", oracle)
    report = compare(oracle, core, classify)
    config = {
        k: json.loads(json.dumps(oracle["configuration"].get(k)))
        == json.loads(json.dumps(core["configuration"].get(k)))
        for k in CONFIG_EQUAL
    }
    report["configuration_equal"] = config
    if not all(config.values()):
        report["failures"].append({"path": ["configuration"], "reason": str(config)})
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
