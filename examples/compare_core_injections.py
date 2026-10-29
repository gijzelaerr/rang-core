"""Compare a core injection campaign with an archive (research/core-phase3.md).

Usage:
    python examples/compare_core_injections.py <core result.json> <archive.json> <receipt.json>

Walks the archive and compares every field by the frozen classes: exact
decisions and counts (criterion 2), well-posed floats to 1e-9 relative
(criterion 3), distances to the clean solve to 1e-9 relative or 1e-12
absolute (criterion 4), injection metadata floats to 1e-12 relative
(criterion 1), and excluded fields (criterion 5). Writes a JSON receipt and
exits nonzero on any failure.
"""

import json
import math
import sys
from pathlib import Path

FLOAT_TOL = 1e-9
DISTANCE_REL, DISTANCE_ABS = 1e-9, 1e-12
INJECTION_TOL = 1e-12

EXCLUDED = {
    "seconds",
    "seconds_total",
    "data_backup_sha256",
    "audit",
    "manifest",
    "artifact_directory",
    "implementation_provenance",
    "measured_summary",
    "limitations",
    "experiment",
    "timings",
    "policy_objective",
    "diagnostic_tv_reference",
}
WELL_POSED = {
    "tv",
    "raw_tv",
    "time_tv",
    "frequency_tv",
    "fixed_clean_support_tv",
    "fixed_contaminated_support_tv",
    "fixed_clean_support_tv_ratio",
    "scale",
    "valid_gain_fraction",
    "objective",
    "added_fraction",
    "injection_recall",
    "outside_injection_train_fraction",
    # Post-hoc (research/core-phase3.md): archive-only per-case objectives.
    "no_change_objective",
    "diagnostic_oracle_objective",
}
LOSS_PARENTS = {"losses"}
DISTANCES = {"polar_gauge_gain_mse_to_clean"}
DISTANCE_PARENTS = {"weighted_prediction_mse_to_clean"}
INJECTION_FLOATS = {
    "actual_train_occupancy",
    "delta_abs_jy_quantiles",
    "strength_inverse_weight_units",
    "target_train_occupancy",
}


def classify(path):
    key = path[-1] if isinstance(path[-1], str) else path[-2]
    parent = next((p for p in reversed(path[:-1]) if isinstance(p, str)), None)
    if any(p in EXCLUDED for p in path if isinstance(p, str)):
        return "excluded"
    if key in DISTANCES or parent in DISTANCE_PARENTS:
        return "distance"
    if key in INJECTION_FLOATS:
        return "injection_float"
    if key in WELL_POSED or parent in LOSS_PARENTS:
        return "float"
    return "exact"


def numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check(cls, archived, core):
    if archived is None or core is None:
        return archived is None and core is None, None
    if cls == "exact":
        return archived == core, None
    if not (numeric(archived) and numeric(core)):
        return archived == core, None
    if not (math.isfinite(archived) and math.isfinite(core)):
        return archived == core, None
    diff = abs(core - archived)
    rel = diff / abs(archived) if archived else diff
    if cls == "distance":
        return rel <= DISTANCE_REL or diff <= DISTANCE_ABS, rel
    tol = INJECTION_TOL if cls == "injection_float" else FLOAT_TOL
    return rel <= tol, rel


def walk(archived, core, path, report):
    cls = classify(path) if path else "exact"
    if cls == "excluded":
        report["excluded"] += 1
        return
    if isinstance(archived, dict):
        if not isinstance(core, dict):
            report["failures"].append({"path": path, "reason": "missing or not a dict"})
            return
        for key, value in archived.items():
            if key not in core:
                if classify([*path, key]) == "excluded":
                    report["excluded"] += 1
                    continue
                report["failures"].append({"path": [*path, key], "reason": "missing"})
                continue
            walk(value, core[key], [*path, key], report)
        return
    if isinstance(archived, list) and not (
        cls != "exact" and all(numeric(x) for x in archived)
    ):
        if not isinstance(core, list) or len(core) != len(archived):
            report["failures"].append({"path": path, "reason": "list length differs"})
            return
        for i, (a, c) in enumerate(zip(archived, core, strict=True)):
            walk(a, c, [*path, i], report)
        return
    if isinstance(archived, list):
        ok = isinstance(core, list) and len(core) == len(archived)
        rels = []
        if ok:
            for a, c in zip(archived, core, strict=True):
                good, rel = check(cls, a, c)
                ok &= good
                if rel is not None:
                    rels.append(rel)
        result = (ok, max(rels) if rels else None)
    else:
        result = check(cls, archived, core)
    good, rel = result
    stats = report["classes"].setdefault(cls, {"compared": 0, "max_rel": 0.0})
    stats["compared"] += 1
    if rel is not None:
        stats["max_rel"] = max(stats["max_rel"], rel)
    if not good:
        report["failures"].append(
            {"path": path, "class": cls, "archived": archived, "core": core}
        )


def compare(core, archive):
    report = {"classes": {}, "excluded": 0, "failures": []}
    for key in ("clean_reference", "cases", "post_selection_candidate_recovery"):
        walk(archive[key], core[key], [key], report)
    config = {
        k: archive["configuration"][k] == core["configuration"].get(k)
        for k in (
            "seed",
            "strengths_inverse_weight_units",
            "patterns",
            "time_interval",
            "freq_interval",
            "iterations",
            "clean_split_seed",
        )
    }
    report["configuration_equal"] = config
    if not all(config.values()):
        report["failures"].append({"path": ["configuration"], "reason": str(config)})
    report["selected"] = [
        {
            "case": c["case"],
            "archived": a["controls"]["selected_policy"]["trial"],
            "core": c["controls"]["selected_policy"]["trial"],
        }
        for a, c in zip(archive["cases"], core["cases"], strict=True)
    ]
    report["injection_checks"] = core.get("injection_checks")
    report["objective_margins"] = core.get("objective_margins")
    report["passed"] = not report["failures"] and all(
        all(v.values()) for v in (core.get("injection_checks") or {}).values()
    )
    return report


def main():
    core_path, archive_path, receipt = (Path(x) for x in sys.argv[1:4])
    core = json.loads(core_path.read_text())
    archive = json.loads(archive_path.read_text())
    # A campaign result.json keeps candidate recovery in a sibling file.
    sibling = archive_path.parent / "candidate-recovery.json"
    if "post_selection_candidate_recovery" not in archive and sibling.is_file():
        archive["post_selection_candidate_recovery"] = json.loads(sibling.read_text())
    report = compare(core, archive)
    report["inputs"] = {"core": str(core_path), "archive": str(archive_path)}
    receipt.write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "failures": len(report["failures"]),
                "classes": report["classes"],
                "excluded": report["excluded"],
                "selected_equal": all(
                    s["archived"] == s["core"] for s in report["selected"]
                ),
            }
        )
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
