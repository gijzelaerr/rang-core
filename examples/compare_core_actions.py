"""Compare a core actions result with an oracle (research/core-phase3-actions.md).

Usage:
    python examples/compare_core_actions.py <core result.json> <oracle.json> <receipt.json>

The oracle is the archive or a host reproduction's result.json. Field classes
follow the frozen criteria 1-4.
"""

import json
import sys
from pathlib import Path

from rangtoy.core_compare import compare, key_and_parent

EXCLUDED = {
    "seconds",
    "seconds_total",
    "date",
    "run",
    "provenance",
    "audit",
    "assessment",
    "limitations",
    "configuration",
    "experiment",
}
FLOATS = {
    "tv",
    "raw_tv",
    "time_tv",
    "frequency_tv",
    "fixed_support_tv",
    "scale",
    "valid_gain_fraction",
    "added_fraction",
    "center",
    "objective",
}
DIFFERENCES = {
    "normalized_tv_change",
    "coefficients",
    "predicted_changes",
    "tuning",
    "validation_action_mse",
    "test_action_mse",
    "constant_predictor_test_mse",
}
CONFIG_EQUAL = ("seed", "action_count", "iterations", "ridge_penalties")


def classify(path):
    if any(p in EXCLUDED for p in path if isinstance(p, str)):
        return "excluded"
    keys = [p for p in path if isinstance(p, str)]
    key, parent = key_and_parent(path)
    if any(k in DIFFERENCES for k in keys):
        # Everything inside a fitted quantity is fitted to the differences,
        # except the penalty labels in the tuning table.
        return "exact" if key == "ridge_penalty" or key == "penalty" else "difference"
    if key in FLOATS or parent == "losses":
        return "float"
    # Post-hoc (research/core-phase3-actions.md): criterion 1 covers only
    # non-float action metadata; float metadata such as the candidate score,
    # present in the host reproduction but not the archive, is a float.
    if parent == "action" and key == "score":
        return "float"
    # The model's feature scale, not the solver's gain-norm scale.
    if key == "scale" and parent == "model":
        return "float"
    return "exact"


def main():
    core_path, oracle_path, receipt = (Path(x) for x in sys.argv[1:4])
    core = json.loads(core_path.read_text())
    oracle = json.loads(oracle_path.read_text())
    report = compare(oracle, core, classify)
    oracle_config = oracle.get("configuration")
    if oracle_config is None:
        config_path = oracle_path.parent / "action-config.json"
        oracle_config = json.loads(config_path.read_text())
    config = {
        k: oracle_config.get(k) == core["configuration"].get(k) for k in CONFIG_EQUAL
    }
    report["configuration_equal"] = config
    if not all(config.values()):
        report["failures"].append({"path": ["configuration"], "reason": str(config)})
    report["selected"] = [oracle["selected"]["trial"], core["selected"]["trial"]]
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
                "selected": report["selected"],
            }
        )
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
