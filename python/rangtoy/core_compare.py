"""The comparator engine: every core comparator in one module (task P9,
research/p9-cli.md).

Two layers:

1. **The field walker.** `compare(archived, core, classify)` walks an
   archived result and compares every leaf with the core result by the class
   that `classify(path)` returns, where path is the list of keys and list
   indices from the root. Classes:

   - "excluded": not compared (wall times, paths, MS audits, ...);
   - "exact": equal values (strings, integers, booleans, None, decisions);
   - "float": relative difference within `float_tol` (absolute if the oracle
     is 0);
   - "difference": within `float_tol` relative or `difference_abs` absolute,
     for differences of nearly equal quantities;
   - "reported": the difference is recorded but never fails;
   - any other name: the (relative, absolute or None) pair given for it in
     `tolerances` (injections' "distance" and "injection_float").

   Every archived field must exist in the core result unless it is excluded.

2. **The comparators.** One entry of `COMPARATORS` per comparator script
   (`examples/compare_core_<name>.py`, now thin wrappers of `main`). The
   rules (classify functions, tolerances, volatile keys), the printed
   output, the receipt's bytes and the exit status are those of the frozen
   scripts, moved verbatim. `main(name, argv)` behaves as the script did and
   returns its exit status; `run(name, argv)` returns the verdict contract
   `{"name", "exit", "passed", "failures", "counts", "receipt"}` (`passed`
   is None for the gridder's pixel table, a measurement that judges
   nothing).

Oracles may also be `rang.archive` files (`rang-core <stage> archive`); their
`result` is compared. NumPy, astropy and the core are imported only by the
comparators that need them.
"""

import argparse
import json
import math
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path

ARCHIVE_SCHEMA = "rang.archive"


def _numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check(cls, archived, core, tolerances, float_tol):
    if archived is None or core is None:
        return archived is None and core is None, None
    if cls == "exact" or not (_numeric(archived) and _numeric(core)):
        return archived == core, None
    if not (math.isfinite(archived) and math.isfinite(core)):
        return archived == core, None
    diff = abs(core - archived)
    rel = diff / abs(archived) if archived else diff
    if cls == "reported":
        return True, rel
    rel_tol, abs_tol = tolerances.get(cls, (float_tol, None))
    if abs_tol is None:
        return rel <= rel_tol, rel
    return rel <= rel_tol or diff <= abs_tol, rel


def compare(
    archived,
    core,
    classify,
    *,
    float_tol=1e-9,
    difference_abs=1e-12,
    root=(),
    tolerances=None,
    report=None,
    not_dict="not a dict",
):
    """Return {"classes": {...}, "excluded": n, "failures": [...]}.

    `tolerances` maps a class to (relative, absolute or None); "float" and
    "difference" default to (float_tol, None) and (float_tol,
    difference_abs). `report` accumulates several walks into one report;
    `not_dict` is the failure reason when the core side is not a dict.
    """
    tolerances = {
        "float": (float_tol, None),
        "difference": (float_tol, difference_abs),
        **(tolerances or {}),
    }
    if report is None:
        report = {"classes": {}, "excluded": 0, "failures": []}

    def walk(a, c, path):
        cls = classify(path) if path else "exact"
        if cls == "excluded":
            report["excluded"] += 1
            return
        if isinstance(a, dict):
            if not isinstance(c, dict):
                report["failures"].append({"path": path, "reason": not_dict})
                return
            for key, value in a.items():
                if key not in c:
                    if classify([*path, key]) == "excluded":
                        report["excluded"] += 1
                    else:
                        report["failures"].append(
                            {"path": [*path, key], "reason": "missing"}
                        )
                    continue
                walk(value, c[key], [*path, key])
            return
        if isinstance(a, list) and not (cls != "exact" and all(_numeric(x) for x in a)):
            if not isinstance(c, list) or len(c) != len(a):
                report["failures"].append(
                    {"path": path, "reason": "list length differs"}
                )
                return
            for i, (x, y) in enumerate(zip(a, c, strict=True)):
                walk(x, y, [*path, i])
            return
        if isinstance(a, list):
            good = isinstance(c, list) and len(c) == len(a)
            rels = []
            if good:
                for x, y in zip(a, c, strict=True):
                    ok, rel = _check(cls, x, y, tolerances, float_tol)
                    good &= ok
                    if rel is not None:
                        rels.append(rel)
            ok, rel = good, (max(rels) if rels else None)
        else:
            ok, rel = _check(cls, a, c, tolerances, float_tol)
        stats = report["classes"].setdefault(cls, {"compared": 0, "max_rel": 0.0})
        stats["compared"] += 1
        if rel is not None:
            stats["max_rel"] = max(stats["max_rel"], rel)
        if not ok:
            report["failures"].append(
                {"path": path, "class": cls, "archived": a, "core": c}
            )

    walk(archived, core, list(root))
    return report


def key_and_parent(path):
    """The innermost string key and its nearest string ancestor."""
    keys = [p for p in path if isinstance(p, str)]
    return (keys[-1] if keys else None), (keys[-2] if len(keys) > 1 else None)


def is_archive(payload):
    return isinstance(payload, dict) and payload.get("schema") == ARCHIVE_SCHEMA


def unwrap(payload, key=None):
    """The compared part of an oracle: a `rang.archive`'s `result`, else
    `payload[key]` when present (the legacy layouts), else the payload."""
    if is_archive(payload):
        return payload["result"]
    if key is not None:
        return payload.get(key, payload)
    return payload


def _write(path, text):
    """Receipts are written with LF line endings on every platform."""
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print_walker_summary(report, **extra):
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "failures": len(report["failures"]),
                "classes": report["classes"],
                "excluded": report["excluded"],
                **extra,
            }
        )
    )


# ---------------------------------------------------------------------------
# Injections (research/core-phase3.md): criteria 1-5.

INJ_FLOAT_TOL = 1e-9
INJ_DISTANCE_REL, INJ_DISTANCE_ABS = 1e-9, 1e-12
INJ_INJECTION_TOL = 1e-12
INJ_TOLERANCES = {
    "float": (INJ_FLOAT_TOL, None),
    "distance": (INJ_DISTANCE_REL, INJ_DISTANCE_ABS),
    "injection_float": (INJ_INJECTION_TOL, None),
}
INJ_EXCLUDED = {
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
INJ_WELL_POSED = {
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
INJ_LOSS_PARENTS = {"losses"}
INJ_DISTANCES = {"polar_gauge_gain_mse_to_clean"}
INJ_DISTANCE_PARENTS = {"weighted_prediction_mse_to_clean"}
INJ_INJECTION_FLOATS = {
    "actual_train_occupancy",
    "delta_abs_jy_quantiles",
    "strength_inverse_weight_units",
    "target_train_occupancy",
}


def injections_classify(path):
    key = path[-1] if isinstance(path[-1], str) else path[-2]
    parent = next((p for p in reversed(path[:-1]) if isinstance(p, str)), None)
    if any(p in INJ_EXCLUDED for p in path if isinstance(p, str)):
        return "excluded"
    if key in INJ_DISTANCES or parent in INJ_DISTANCE_PARENTS:
        return "distance"
    if key in INJ_INJECTION_FLOATS:
        return "injection_float"
    if key in INJ_WELL_POSED or parent in INJ_LOSS_PARENTS:
        return "float"
    return "exact"


def injections_compare(core, archive):
    report = {"classes": {}, "excluded": 0, "failures": []}
    for key in ("clean_reference", "cases", "post_selection_candidate_recovery"):
        compare(
            archive[key],
            core[key],
            injections_classify,
            root=[key],
            tolerances=INJ_TOLERANCES,
            report=report,
            not_dict="missing or not a dict",
        )
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


def _injections(argv):
    core_path, archive_path, receipt = (Path(x) for x in argv[:3])
    core = _read_json(core_path)
    archive = unwrap(_read_json(archive_path))
    # A campaign result.json keeps candidate recovery in a sibling file.
    sibling = archive_path.parent / "candidate-recovery.json"
    if "post_selection_candidate_recovery" not in archive and sibling.is_file():
        archive["post_selection_candidate_recovery"] = _read_json(sibling)
    report = injections_compare(core, archive)
    report["inputs"] = {"core": str(core_path), "archive": str(archive_path)}
    _write(receipt, json.dumps(report, indent=1, default=str) + "\n")
    _print_walker_summary(
        report,
        selected_equal=all(s["archived"] == s["core"] for s in report["selected"]),
    )
    return (0 if report["passed"] else 1), report, receipt


# ---------------------------------------------------------------------------
# Actions (research/core-phase3-actions.md): criteria 1-4.

ACT_EXCLUDED = {
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
ACT_FLOATS = {
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
ACT_DIFFERENCES = {
    "normalized_tv_change",
    "coefficients",
    "predicted_changes",
    "tuning",
    "validation_action_mse",
    "test_action_mse",
    "constant_predictor_test_mse",
}
ACT_CONFIG_EQUAL = ("seed", "action_count", "iterations", "ridge_penalties")


def actions_classify(path):
    if any(p in ACT_EXCLUDED for p in path if isinstance(p, str)):
        return "excluded"
    keys = [p for p in path if isinstance(p, str)]
    key, parent = key_and_parent(path)
    if any(k in ACT_DIFFERENCES for k in keys):
        # Everything inside a fitted quantity is fitted to the differences,
        # except the penalty labels in the tuning table.
        return "exact" if key == "ridge_penalty" or key == "penalty" else "difference"
    if key in ACT_FLOATS or parent == "losses":
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


def _actions(argv):
    core_path, oracle_path, receipt = (Path(x) for x in argv[:3])
    core = _read_json(core_path)
    oracle = unwrap(_read_json(oracle_path))
    report = compare(oracle, core, actions_classify)
    oracle_config = oracle.get("configuration")
    if oracle_config is None:
        config_path = oracle_path.parent / "action-config.json"
        oracle_config = _read_json(config_path)
    config = {
        k: oracle_config.get(k) == core["configuration"].get(k)
        for k in ACT_CONFIG_EQUAL
    }
    report["configuration_equal"] = config
    if not all(config.values()):
        report["failures"].append({"path": ["configuration"], "reason": str(config)})
    report["selected"] = [oracle["selected"]["trial"], core["selected"]["trial"]]
    report["passed"] = not report["failures"]
    report["inputs"] = {"core": str(core_path), "oracle": str(oracle_path)}
    _write(receipt, json.dumps(report, indent=1, default=str) + "\n")
    _print_walker_summary(report, selected=report["selected"])
    return (0 if report["passed"] else 1), report, receipt


# ---------------------------------------------------------------------------
# Prospective (research/core-phase3b.md): criteria 1-6.

PRO_EXCLUDED = {
    "seconds",
    "native_response_seconds",
    "full_training_normals_seconds",
    "allocated_bytes",
    "audit",
    "configuration",
    "status",
    "limitations",
}
PRO_FLOATS = {
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
PRO_DIFFERENCES = {"predicted_benefit", "predicted_cost_removed_benefit"}
PRO_REPORTED = {"baseline_projected_score_norm", "gauge_null_relative"}
PRO_CONFIG_EQUAL = (
    "iterations",
    "grid",
    "maximum_action_confirmations",
    "maximum_actual_QC_solves",
    "minimum_benefit",
    "test_or_truth_selects",
)


def prospective_classify(path):
    if any(p in PRO_EXCLUDED for p in path if isinstance(p, str)):
        return "excluded"
    key, parent = key_and_parent(path)
    if key in PRO_REPORTED:
        return "reported"
    if key in PRO_DIFFERENCES:
        return "difference"
    if key in PRO_FLOATS or parent == "losses":
        return "float"
    return "exact"


def _prospective(argv):
    core_path, oracle_path, receipt = (Path(x) for x in argv[:3])
    core = _read_json(core_path)
    oracle = unwrap(_read_json(oracle_path), "raw_result_projection")
    report = compare(oracle, core, prospective_classify)
    config = {
        k: oracle["configuration"].get(k) == core["configuration"].get(k)
        for k in PRO_CONFIG_EQUAL
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
    _write(receipt, json.dumps(report, indent=1, default=str) + "\n")
    _print_walker_summary(report)
    return (0 if report["passed"] else 1), report, receipt


# ---------------------------------------------------------------------------
# Signal (research/core-phase3c-b.md): criteria 1-5.

SIG_EXCLUDED = {
    "seconds",
    "configuration",
    "audit",
    "acceptance_file_sha256",
    "observed_allocated_bytes_before_result",
    "imaging",
    "limitations",
}
SIG_FLOATS = {
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
SIG_DIFFERENCE_IN_REFERENCE = {
    "weighted_mse_proxy",
    "unexplained_weighted_response_energy_fraction",
}
SIG_REPORTED = {"visibility_closure_linf_jy", "coefficient_closure_linf_jy"}
SIG_CONFIG_EQUAL = (
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


def signal_classify(path):
    keys = [p for p in path if isinstance(p, str)]
    if any(k in SIG_EXCLUDED for k in keys):
        return "excluded"
    key, parent = key_and_parent(path)
    if key in SIG_REPORTED:
        return "reported"
    if keys and keys[0] == "reference_fits" and key in SIG_DIFFERENCE_IN_REFERENCE:
        return "difference"
    if key in SIG_FLOATS or parent == "losses":
        return "float"
    return "exact"


def _signal(argv):
    core_path, oracle_path, receipt = (Path(x) for x in argv[:3])
    core = _read_json(core_path)
    oracle = unwrap(_read_json(oracle_path), "raw_result")
    report = compare(oracle, core, signal_classify)
    config = {
        k: json.loads(json.dumps(oracle["configuration"].get(k)))
        == json.loads(json.dumps(core["configuration"].get(k)))
        for k in SIG_CONFIG_EQUAL
    }
    report["configuration_equal"] = config
    if not all(config.values()):
        report["failures"].append({"path": ["configuration"], "reason": str(config)})
    report["passed"] = not report["failures"]
    report["inputs"] = {"core": str(core_path), "oracle": str(oracle_path)}
    _write(receipt, json.dumps(report, indent=1, default=str) + "\n")
    _print_walker_summary(report)
    return (0 if report["passed"] else 1), report, receipt


# ---------------------------------------------------------------------------
# Trend (research/core-phase3-trend.md), with the post-hoc slope rule.

TRE_EXCLUDED = {"configuration", "allocated_bytes", "source_digest", "runtime_receipts"}
TRE_FLOATS = {
    "slopes_time_rad_per_second_frequency_rad_per_hz",
    "primary_polar_TV",
    "detrended_guidance_TV",
}
SLOPES = "slopes_time_rad_per_second_frequency_rad_per_hz"


def trend_classify(path):
    keys = [p for p in path if isinstance(p, str)]
    if any(k in TRE_EXCLUDED or "sha256" in k or "digest" in k for k in keys):
        return "excluded"
    if any(k in TRE_FLOATS for k in keys):
        return "float"
    return "exact"


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


def _trend(argv):
    posthoc = argv[3:] == ["--posthoc-slope-scale"]
    result_path, archive_path, receipt = (Path(x) for x in argv[:3])
    result = _read_json(result_path)
    payload = _read_json(archive_path)
    archive = payload["result"] if is_archive(payload) else payload["raw_result"]
    report = compare(archive, result, trend_classify)
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
    _write(receipt, json.dumps(report, indent=1, default=str) + "\n")
    _print_walker_summary(report)
    return (0 if report["passed"] else 1), report, receipt


# ---------------------------------------------------------------------------
# Imaging (research/core-i-imaging-replay.md): `core_imaging.compare_replay`.


def _imaging(argv):
    from .core_imaging import compare_replay, pixel_comparison

    def load(path):
        return unwrap(_read_json(path), "raw_result")

    parser = argparse.ArgumentParser(
        prog="compare_core_imaging.py",
        description="Compare a core imaging replay with the archived imaging result",
    )
    parser.add_argument("result")
    parser.add_argument("oracle")
    parser.add_argument("receipt")
    parser.add_argument("--images", nargs=2, metavar=("CANDIDATE", "REFERENCE"))
    args = parser.parse_args(argv)
    report = compare_replay(load(args.oracle), load(args.result))
    report["result"] = args.result
    report["oracle"] = args.oracle
    passed = report["passed"]
    for cls, stats in sorted(report["classes"].items()):
        print(
            f"{cls:20s} compared {stats['compared']:5d} worst {stats['worst']:.3e}"
            f" at {'/'.join(map(str, stats['worst_path'] or []))}"
        )
    print(f"excluded {report['excluded']} failures {len(report['failures'])}")
    for failure in report["failures"][:20]:
        print("  FAIL", failure)
    if args.images:
        pixels = pixel_comparison(args.images[1], args.images[0])
        report["pixels"] = pixels
        passed &= pixels["passed"]
        for label, job in pixels["jobs"].items():
            for kind in ("dirty", "psf"):
                r = job[kind]
                print(
                    f"{label:28s} {kind:5s} max|d| {r['max_abs_difference']:.3e} "
                    f"rms {r['rms_difference']:.3e} peak {r['reference_peak']:.4g} "
                    f"max|d|/peak {r['max_relative_to_peak']:.3e} "
                    f"central/border rms {r['central_rms_difference']:.2e}/"
                    f"{r['border_rms_difference']:.2e} wcs {r['wcs_equal']}"
                )
        print("pixels", json.dumps(pixels["summary"]), "passed", pixels["passed"])
    report["passed"] = bool(passed)
    _write(args.receipt, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("passed", report["passed"])
    return (0 if passed else 1), report, args.receipt


# ---------------------------------------------------------------------------
# Flags: the Tricolour port (research/core-d-tricolour.md).

FLAG_CONTROLS = (
    "strategy-00-operational",
    "strategy-00-holdout_masked",
    "strategy-01-operational",
    "strategy-01-holdout_masked",
)
FLAG_EXACT = (
    ("native", "returncode"),
    ("native", "audit"),
    ("metrics", "added_count"),
    ("metrics", "added_fraction"),
    ("metrics", "valid_gain_fraction"),
    ("metrics", "invalid_predictions"),
    ("guard_reasons",),
    ("guard_pass",),
    ("strategy",),
    ("artificial_holdout_input_flags",),
)
FLAG_FLOAT = (
    ("metrics", "tv"),
    ("metrics", "raw_tv"),
    ("metrics", "time_tv"),
    ("metrics", "frequency_tv"),
    ("metrics", "scale"),
    ("fixed_support_tv",),
    ("objective",),
)
FLAG_FLOAT_REL = 1e-9


def _get(record, path):
    for key in path:
        record = record[key]
    return record


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= FLAG_FLOAT_REL * max(abs(a), abs(b), 1e-300)


def tree_sha256(path):
    """SHA256 over (POSIX relative path, bytes) of every file, sorted."""
    files = sorted(
        p for p in Path(path).rglob("*") if p.is_file() and p.name != "table.lock"
    )
    digest = sha256()
    for p in files:
        digest.update(p.relative_to(path).as_posix().encode())
        digest.update(p.read_bytes())
    return digest.hexdigest()


def flags_archive_host(archive_path, host_run, out):
    import numpy as np

    archive = _read_json(archive_path)["result"]
    host = _read_json(Path(host_run) / "result.json")
    failures, compared = [], 0
    pairs = list(zip(archive["controls"], host["controls"])) + [
        (archive["baseline"], host["baseline"])
    ]
    if len(archive["controls"]) != 4 or len(host["controls"]) != 4:
        failures.append("expected four controls on both sides")
    for index, (a, h) in enumerate(pairs):
        label = a.get("native", {}).get("label", "baseline")
        for path in FLAG_EXACT + FLAG_FLOAT:
            try:
                va, vh = _get(a, path), _get(h, path)
            except KeyError:
                continue
            compared += 1
            same = _close(va, vh) if path in FLAG_FLOAT else va == vh
            if not same:
                failures.append(f"{label}: {'.'.join(path)} archive={va!r} host={vh!r}")
        if index < 4 and label != FLAG_CONTROLS[index]:
            failures.append(
                f"control {index} is {label}, expected {FLAG_CONTROLS[index]}"
            )
    snapshots = {}
    for label in FLAG_CONTROLS:
        directory = Path(host_run) / "native" / label
        before = np.load(directory / "before-native.npz")
        after = np.load(directory / "after-native.npz")
        if not np.array_equal(before["FLAG_ROW"], after["FLAG_ROW"]):
            failures.append(f"{label}: FLAG_ROW changed by the native run")
        if not np.all(after["FLAG"] == after["FLAG"][..., :1]):
            failures.append(f"{label}: after-native flags differ between correlations")
        snapshots[label] = {
            "before_sha256": sha256(
                (directory / "before-native.npz").read_bytes()
            ).hexdigest(),
            "after_sha256": sha256(
                (directory / "after-native.npz").read_bytes()
            ).hexdigest(),
            "before_fraction": float(before["FLAG"].mean()),
            "after_fraction": float(after["FLAG"].mean()),
        }
    return {
        "mode": "archive-host",
        "archive": str(archive_path),
        "host_run": str(host_run),
        "fields_compared": compared,
        "failures": failures,
        "snapshots": snapshots,
        "pass": not failures,
    }


def flags_run(core_run, host_run, oracle_dir, out):
    import numpy as np

    core_run, host_run, oracle_dir = Path(core_run), Path(host_run), Path(oracle_dir)
    receipt = _read_json(core_run / "receipt.json")
    oracle = _read_json(oracle_dir / "receipt.json")
    criteria = {str(k): {"pass": True, "detail": {}} for k in range(1, 6)}
    for label in FLAG_CONTROLS:
        core = np.load(core_run / label / "flags.npz")
        after = np.load(host_run / "native" / label / "after-native.npz")
        proposal = np.load(host_run / "native" / label / "frozen-proposal.npz")
        stages = np.load(core_run / label / "stages.npz")
        oracle_stages = np.load(oracle_dir / label / "stages.npz")
        # 1. Final flags, exact.
        differ = int(np.count_nonzero(core["FLAG"] != after["FLAG"]))
        criteria["1"]["detail"][label] = {
            "differences": differ,
            "elements": int(after["FLAG"].size),
            "core_fraction": float(core["FLAG"].mean()),
            "host_fraction": float(after["FLAG"].mean()),
        }
        if differ:
            criteria["1"]["pass"] = False
        # 2. Training proposal.
        added_equal = bool(np.array_equal(core["added"], proposal["added"]))
        added_count = int(np.count_nonzero(core["added"]))
        archive_count = receipt["archive_added_count"][label]
        criteria["2"]["detail"][label] = {
            "added_equal": added_equal,
            "added_count": added_count,
            "archive_added_count": archive_count,
        }
        if not added_equal or added_count != archive_count:
            criteria["2"]["pass"] = False
        # 3. Stage windows, exact.
        stage_detail = {}
        for name in oracle_stages.files:
            if name not in stages.files:
                stage_detail[name] = "missing"
                criteria["3"]["pass"] = False
                continue
            diff = int(np.count_nonzero(stages[name] != oracle_stages[name]))
            stage_detail[name] = diff
            if diff:
                criteria["3"]["pass"] = False
        criteria["3"]["detail"][label] = stage_detail
        # 4. Polarised intensity, bit-equal with NaNs equal.
        pol_core = np.load(core_run / label / "intensity.npz")["intensity"]
        pol_oracle = np.load(oracle_dir / label / "intensity.npz")["intensity"]
        pol_equal = pol_core.dtype == pol_oracle.dtype and bool(
            np.array_equal(pol_core.view(np.uint32), pol_oracle.view(np.uint32))
        )
        criteria["4"]["detail"][label] = {"bit_equal": pol_equal}
        if not pol_equal:
            criteria["4"]["pass"] = False
    # 5. No side effects on the host inputs.
    hashes = {}
    for label in FLAG_CONTROLS:
        directory = host_run / "native" / label
        hashes[label] = {
            "before-native.npz": sha256(
                (directory / "before-native.npz").read_bytes()
            ).hexdigest(),
            "after-native.npz": sha256(
                (directory / "after-native.npz").read_bytes()
            ).hexdigest(),
            "diagnostic.ms": tree_sha256(directory / "diagnostic.ms"),
        }
    expected = oracle["host_hashes"]
    criteria["5"]["detail"] = {
        "hashes_equal_to_oracle_record": hashes == expected,
        "hashes_equal_to_core_record": hashes == receipt["host_hashes"],
    }
    criteria["5"]["pass"] = hashes == expected and hashes == receipt["host_hashes"]
    return {
        "mode": "run",
        "core_run": str(core_run),
        "host_run": str(host_run),
        "oracle_dir": str(oracle_dir),
        "criteria": criteria,
        "timings": {"core": receipt.get("timings"), "oracle": oracle.get("timings")},
        "pass": all(c["pass"] for c in criteria.values()),
    }


def _flags(argv):
    mode = argv[0]
    out = Path(argv[-1])
    out.mkdir(parents=True, exist_ok=False)
    if mode == "archive-host":
        result = flags_archive_host(argv[1], argv[2], out)
    elif mode == "run":
        result = flags_run(argv[1], argv[2], argv[3], out)
    else:
        raise SystemExit(f"unknown mode {mode}")
    _write(out / "result.json", json.dumps(result, indent=1) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("snapshots",)}, indent=1
        )
    )
    return (0 if result["pass"] else 1), result, out / "result.json"


# ---------------------------------------------------------------------------
# Weights: imaging weights and Stokes I against WSClean
# (research/core-b-weighting.md).

WEIGHTS_DOC = """Compare the core's imaging weights and Stokes I with the WSClean oracle.

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
W_IMAGE_TOLERANCE_JY = 1e-6
W_HEADER_RELATIVE = 1e-9
W_FLOAT32_FOUR_ULPS = 4 * 2.0**-23
W_CHANNELS = (1024, 3072)
W_SIZE = 512
W_PADDING = 1.2
W_SCALE = 8.0 * math.pi / (180.0 * 60.0 * 60.0)
W_ROBUST = 0.5
W_RANK_FILTER = (3.0, 16)


def weights_load_runs(output):
    import numpy as np

    runs = {}
    for path in sorted((output / "oracle").glob("*.json")):
        if path.name == "summary.json":
            continue
        record = json.loads(path.read_text())
        record["arrays"] = np.load(output / "oracle" / f"{record['name']}.npz")
        runs[record["name"]] = record
    return runs


def _selected_rows(arrays):
    return (
        (arrays["FIELD_ID"] == 0)
        & (arrays["ANTENNA1"] != arrays["ANTENNA2"])
        & (arrays["DATA_DESC_ID"] == 0)
    )


def relative_spread(a, b):
    """Max relative difference on the non-zero cells, after a pattern check."""
    import numpy as np

    pattern = np.array_equal(a != 0, b != 0)
    mask = (a != 0) & (b != 0)
    if not mask.any():
        return pattern, 0.0
    a64 = a[mask].astype(np.float64)
    b64 = b[mask].astype(np.float64)
    return pattern, float(np.max(np.abs(a64 - b64) / np.abs(b64)))


def _column_structure(arrays):
    import numpy as np

    w = arrays["IMAGING_WEIGHT_SPECTRUM"]
    lo, hi = W_CHANNELS
    rows = _selected_rows(arrays)
    checks = {
        "xx_equals_yy": bool(np.array_equal(w[..., 0], w[..., 3])),
        "xy_yx_zero": bool(not np.any(w[..., 1]) and not np.any(w[..., 2])),
        "outside_range_zero": bool(not np.any(w[:, :lo]) and not np.any(w[:, hi:])),
        "unselected_rows_zero": bool(not np.any(w[~rows])),
        "selected_rows": int(rows.sum()),
    }
    checks["pass"] = all(v for k, v in checks.items() if k != "selected_rows")
    return checks


def weights_oracle_only(runs):
    import numpy as np

    report = {"archive": {}, "repeat": {}, "structure": {}}
    worst_image = 0.0
    worst_header = 0.0
    for name, run in runs.items():
        report["structure"][name] = _column_structure(run["arrays"])
        if run["archive_label"] is not None:
            checks = run["archive_checks"]
            image = max(c["max_abs_pixel_difference"] for c in checks.values())
            header = max(c["header_max_relative_difference"] for c in checks.values())
            worst_image = max(worst_image, image)
            worst_header = max(worst_header, header)
            report["archive"][name] = {
                "max_abs_pixel_difference": image,
                "header_max_relative_difference": header,
                "pass": image <= W_IMAGE_TOLERANCE_JY and header <= W_HEADER_RELATIVE,
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
        "derived_tolerance": max(W_FLOAT32_FOUR_ULPS, repeat_spread),
        "archive_pass": all(v["pass"] for v in report["archive"].values()),
        "structure_pass": all(v["pass"] for v in report["structure"].values()),
        "repeat_pattern_pass": all(
            v["pattern_identical"] for v in report["repeat"].values()
        ),
    }
    return report


def numpy_stokes_i(data, weights, flags):
    """Items 3 and 8 of the protocol in NumPy float32 arithmetic."""
    import numpy as np

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


def _run_mode(run):
    """The weighting class of a run, from its name (the oracle records of the
    first run predate the mode field)."""
    suffix = run["name"].split("--")[-1] if "--" in run["name"] else ""
    return run.get("mode", suffix if suffix in ("uniform", "natural") else "briggs")


def weights_core_job(run, tolerance):
    import time

    import numpy as np

    from . import core_weights

    arrays = run["arrays"]
    lo, hi = W_CHANNELS
    rows = _selected_rows(arrays)
    data = np.ascontiguousarray(arrays["CORRECTED_DATA"][:, lo:hi])
    weights = np.ascontiguousarray(arrays["WEIGHT_SPECTRUM"][:, lo:hi])
    flags = np.ascontiguousarray(arrays["FLAG"][:, lo:hi])
    mode = _run_mode(run)
    t0 = time.perf_counter()
    vis, weight = core_weights.stokes_i(data, weights, flags)
    stokes_seconds = time.perf_counter() - t0
    oracle_vis, oracle_weight = numpy_stokes_i(data, weights, flags)
    width = height = core_weights.padded_size(W_SIZE, W_PADDING)
    t0 = time.perf_counter()
    result = core_weights.imaging_weights(
        arrays["UVW"],
        arrays["WAVELENGTH"][lo:hi],
        weight,
        rows,
        mode=mode,
        robust=W_ROBUST,
        width=width,
        height=height,
        pixel_scale=W_SCALE,
        rank_filter=W_RANK_FILTER,
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
            v["relative_difference"] <= W_HEADER_RELATIVE for v in sum_checks.values()
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


def _weights(argv):
    parser = argparse.ArgumentParser(
        prog="compare_core_weights.py", description=WEIGHTS_DOC
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--oracle-only", action="store_true")
    parser.add_argument("--tolerance", type=float, default=None)
    args = parser.parse_args(argv)
    runs = weights_load_runs(args.output)
    report = {"precondition": weights_oracle_only(runs)}
    if args.oracle_only:
        print(json.dumps(report["precondition"]["summary"], indent=2))
        _write(
            args.output / "precondition.json",
            json.dumps(report["precondition"], indent=2),
        )
        return 0, report, args.output / "precondition.json"
    tolerance = args.tolerance
    if tolerance is None:
        raise SystemExit("--tolerance is the frozen value from the protocol")
    report["tolerance"] = tolerance
    report["jobs"] = {}
    for name, run in runs.items():
        if name.endswith("--repeat"):
            continue
        report["jobs"][name] = weights_core_job(run, tolerance)
        job = report["jobs"][name]
        print(
            name,
            "PASS" if job["pass"] else "FAIL",
            job["weights_max_relative_difference"],
            job["weights_identical"],
            file=sys.stderr,
        )
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
    _write(args.output / "compare.json", json.dumps(report, indent=2))
    print(json.dumps(report["criteria"], indent=2))
    return 0, report, args.output / "compare.json"


# ---------------------------------------------------------------------------
# Gridder: dirty and PSF pixels (research/core-c-gridder.md, criteria 4 and 7).

GRID_LABELS = (
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
GRID_WCS_KEYS = (
    "CRPIX1",
    "CRPIX2",
    "CRVAL1",
    "CRVAL2",
    "CDELT1",
    "CDELT2",
    "CTYPE1",
    "CTYPE2",
)
GRID_WCS_TOLERANCE = 1e-9


def _read_fits(path):
    import numpy as np
    from astropy.io import fits

    with fits.open(str(path), memmap=False) as hdus:
        return np.asarray(hdus[0].data, np.float64).squeeze(), hdus[0].header


def gridder_compare_image(reference, candidate):
    import numpy as np

    ref, ref_header = _read_fits(reference)
    cand, cand_header = _read_fits(candidate)
    if ref.shape != cand.shape:
        raise RuntimeError(f"shape mismatch {ref.shape} vs {cand.shape}")
    delta = cand - ref
    peak = float(np.max(np.abs(ref)))
    wcs_equal = True
    for key in GRID_WCS_KEYS:
        a, b = ref_header[key], cand_header[key]
        if isinstance(a, str):
            wcs_equal &= a == b
        else:
            wcs_equal &= abs(float(a) - float(b)) <= GRID_WCS_TOLERANCE
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
        "wcs": {key: cand_header[key] for key in GRID_WCS_KEYS},
    }


def _gridder_main(reference, candidate, output):
    reference, candidate = Path(reference), Path(candidate)
    results = {"reference": str(reference), "candidate": str(candidate), "jobs": {}}
    print(
        f"{'job':28s} {'kind':5s} {'max|d|':>10s} {'rms':>10s} {'peak':>9s} {'max|d|/peak':>11s} wcs"
    )
    for label in GRID_LABELS:
        results["jobs"][label] = {}
        for kind in ("dirty", "psf"):
            record = gridder_compare_image(
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
    _write(output, json.dumps(results, indent=2, sort_keys=True))
    print("summary", json.dumps(results["summary"]), "wcs", results["criterion_4_wcs"])
    return 0, results, output


def _gridder(argv):
    return _gridder_main(*argv[:3])


# ---------------------------------------------------------------------------
# Backends: two suite directories file by file (research/core-j-packaging.md,
# criterion 6).

BACKENDS_VOLATILE = {
    "seconds",
    "seconds_total",
    "core_seconds",
    "wall",
    "wall_seconds",
    "wall_seconds_excluding_decode",
    "wall_excluding_decode",
    "process_wall_seconds",
    "decode_seconds",
    "load_seconds",
    "solve_seconds",
    "fused_seconds",
    "step_seconds",
    "timings",
    "timing",
    "read_seconds",
    "ms_read_seconds",
    "elapsed",
    "started",
    "finished",
    "date",
    "max_rss_mb",
    "max_rss_mb_self",
    "process_max_rss_mb",
    "self_maxrss_mb",
    "peak_rss_mb",
    "cost",
    "library_sha256",
    "core_library_sha256",
    "code_sha256",
    "module_sha256",
    "rang_core_lib",
    "rang_core_backend",
    "executable",
    "python",
    "python_version",
    "platform",
    "hostname",
    "load",
    "run",
    "run_dir",
    "output",
    "candidate",
    "reference",
    "receipt",
    "artifact_directory",
    "git_status_unchanged",
}
BACKENDS_SKIP_SUFFIXES = {".log", ".time", ".tsv"}


def _leaves(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, path + (index,))
    else:
        yield path, value


def _run_path(a, b, roots):
    """Both strings name the same file under their own run directory."""
    return (
        isinstance(a, str)
        and isinstance(b, str)
        and a != b
        and a.replace(roots[0], "<run>") == b.replace(roots[1], "<run>")
    )


def _equal_leaf(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return (math.isnan(a) and math.isnan(b)) or a == b
    return a == b


def backends_compare_json(ref, cand, record, roots=("", "")):
    a = json.loads(ref.read_text())
    b = json.loads(cand.read_text())
    ours = dict(_leaves(a))
    theirs = dict(_leaves(b))
    failures = []
    for path in sorted(set(ours) | set(theirs), key=str):
        keys = [p for p in path if isinstance(p, str)]
        volatile = next((k for k in keys if k in BACKENDS_VOLATILE), None)
        if volatile is not None:
            record["volatile"][volatile] += 1
            continue
        if path not in ours or path not in theirs:
            failures.append(f"{'/'.join(map(str, path))}: missing on one side")
        elif _run_path(ours[path], theirs[path], roots):
            record["volatile"]["<run path>"] += 1
        elif not _equal_leaf(ours[path], theirs[path]):
            failures.append(
                f"{'/'.join(map(str, path))}: {ours[path]!r} != {theirs[path]!r}"
            )
        else:
            record["json_leaves"] += 1
    return failures


def backends_compare_arrays(ref, cand, record):
    import numpy as np

    failures = []
    if ref.suffix == ".npy":
        pairs = [
            ("", np.load(ref, allow_pickle=False), np.load(cand, allow_pickle=False))
        ]
    else:
        with (
            np.load(ref, allow_pickle=False) as a,
            np.load(cand, allow_pickle=False) as b,
        ):
            if set(a.files) != set(b.files):
                return [f"{ref}: keys {sorted(a.files)} != {sorted(b.files)}"]
            pairs = [(k, a[k], b[k]) for k in a.files]
    for key, x, y in pairs:
        if x.dtype != y.dtype or x.shape != y.shape or x.tobytes() != y.tobytes():
            failures.append(f"{ref}:{key}: arrays differ")
        else:
            record["arrays"] += 1
    return failures


def backends_compare_fits(ref, cand, record):
    import numpy as np
    from astropy.io import fits

    failures = []
    with fits.open(ref) as a, fits.open(cand) as b:
        if len(a) != len(b):
            return [f"{ref}: HDU count differs"]
        for i, (x, y) in enumerate(zip(a, b)):
            if x.header.tostring() != y.header.tostring():
                failures.append(f"{ref}[{i}]: header cards differ")
            if (x.data is None) != (y.data is None) or (
                x.data is not None
                and np.asarray(x.data).tobytes() != np.asarray(y.data).tobytes()
            ):
                failures.append(f"{ref}[{i}]: pixel data differ")
            if not failures:
                record["fits_hdus"] += 1
    return failures


def backends_files(root, ignore=()):
    out = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts[0] in ignore:
            continue
        if any((root / parent).is_symlink() for parent in rel.parents):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix in BACKENDS_SKIP_SUFFIXES:
            continue
        # Task P9 (labelled addition): `rang-core` receipts are provenance of
        # the command, not results; no suite before P9 holds one.
        if path.name.endswith(".rang-receipt.json"):
            continue
        out.append(rel)
    return out


def _backends_main(reference, candidate, receipt, ignore=""):
    reference, candidate = Path(reference), Path(candidate)
    ignore = tuple(x for x in ignore.split(",") if x)
    record = {
        "reference": str(reference),
        "candidate": str(candidate),
        "ignored": list(ignore),
        "files": 0,
        "json_leaves": 0,
        "arrays": 0,
        "fits_hdus": 0,
        "bytes_equal_files": 0,
        "volatile": Counter(),
        "failures": [],
    }
    ours = set(backends_files(reference, ignore))
    theirs = set(backends_files(candidate, ignore))
    for rel in sorted(ours ^ theirs):
        record["failures"].append(
            f"{rel}: only in {'reference' if rel in ours else 'candidate'}"
        )
    for rel in sorted(ours & theirs):
        ref, cand = reference / rel, candidate / rel
        record["files"] += 1
        if rel.suffix == ".json":
            record["failures"] += backends_compare_json(
                ref, cand, record, (str(reference), str(candidate))
            )
        elif rel.suffix in (".npz", ".npy"):
            record["failures"] += backends_compare_arrays(ref, cand, record)
        elif rel.suffix == ".fits":
            record["failures"] += backends_compare_fits(ref, cand, record)
        elif ref.read_bytes() == cand.read_bytes():
            record["bytes_equal_files"] += 1
        else:
            record["failures"].append(f"{rel}: bytes differ")
    record["volatile"] = dict(sorted(record["volatile"].items()))
    record["pass"] = not record["failures"]
    _write(receipt, json.dumps(record, indent=1) + "\n")
    summary = {k: v for k, v in record.items() if k not in ("failures", "volatile")}
    print(json.dumps(summary, indent=1))
    print("volatile keys skipped:", record["volatile"])
    for failure in record["failures"][:40]:
        print("FAIL", failure)
    return (0 if record["pass"] else 1), record, receipt


def _backends(argv):
    return _backends_main(*argv[:4])


# ---------------------------------------------------------------------------
# Registry and the verdict contract.


def _verdict_walker(report):
    counts = {
        "classes": {k: v["compared"] for k, v in report["classes"].items()},
        "excluded": report["excluded"],
    }
    if "pixels" in report:
        counts["pixels_passed"] = report["pixels"]["passed"]
    return report["passed"], len(report["failures"]), counts


def _verdict_flags(result):
    if result["mode"] == "run":
        counts = {"criteria": {k: c["pass"] for k, c in result["criteria"].items()}}
        failures = sum(not c["pass"] for c in result["criteria"].values())
    else:
        counts = {"fields_compared": result["fields_compared"]}
        failures = len(result["failures"])
    return result["pass"], failures, counts


def _verdict_weights(report):
    if "criteria" not in report:
        summary = report["precondition"]["summary"]
        checks = {
            k: summary[k]
            for k in ("archive_pass", "structure_pass", "repeat_pattern_pass")
        }
        return all(checks.values()), sum(not v for v in checks.values()), checks
    criteria = {k: v for k, v in report["criteria"].items() if isinstance(v, bool)}
    counts = {"criteria": criteria, "jobs": len(report["jobs"])}
    return all(criteria.values()), sum(not v for v in criteria.values()), counts


def _verdict_gridder(results):
    counts = {
        "jobs": len(results["jobs"]),
        "criterion_4_wcs": results["criterion_4_wcs"],
    }
    return None, 0, counts


def _verdict_backends(record):
    counts = {
        k: record[k]
        for k in ("files", "json_leaves", "arrays", "fits_hdus", "bytes_equal_files")
    }
    return record["pass"], len(record["failures"]), counts


# name -> (function(argv) -> (exit, report, receipt path), verdict(report))
COMPARATORS = {
    "injections": (_injections, _verdict_walker),
    "actions": (_actions, _verdict_walker),
    "prospective": (_prospective, _verdict_walker),
    "signal": (_signal, _verdict_walker),
    "trend": (_trend, _verdict_walker),
    "imaging": (_imaging, _verdict_walker),
    "flags": (_flags, _verdict_flags),
    "weights": (_weights, _verdict_weights),
    "gridder": (_gridder, _verdict_gridder),
    "backends": (_backends, _verdict_backends),
}


def run(name, argv):
    """Run comparator `name` on its script's arguments; return the verdict.

    `{"name", "exit", "passed", "failures", "counts", "receipt"}`; the
    comparator prints and writes exactly what its frozen script did.
    """
    function, verdict = COMPARATORS[name]
    code, report, receipt = function(list(argv))
    passed, failures, counts = verdict(report)
    return {
        "name": name,
        "exit": code,
        "passed": passed,
        "failures": failures,
        "counts": counts,
        "receipt": Path(receipt).as_posix(),
    }


def main(name, argv=None):
    """Behave as `examples/compare_core_<name>.py` did; return its exit status."""
    argv = sys.argv[1:] if argv is None else argv
    return run(name, argv)["exit"]
