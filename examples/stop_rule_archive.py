"""Collect the stop-rule measurements into one JSON (research/stop-rule-theorem.md).

Usage: python examples/stop_rule_archive.py RUNS_DIR SCORES_DIR PROBE_DIR OUT.json

Reads the gemclean reports in RUNS_DIR, the scores of
examples/gemclean_bench_compare.py in SCORES_DIR and the output of
core/examples/stop_rule_probe.rs in PROBE_DIR, and checks the proved inequalities
of formal/RangFormal/StopRule.lean against every certified run:

* the flux of a cycle, `B T Σ|c| ≤ ΔQ`, with `B = 1 − κ − γ/2`, `T` the threshold;
* the stopping point of a rule-stopped cycle, `κ B P_stop P_min ≤ f ΔQ`, with
  `P_stop = P_min` the next cycle's first peak, up to its stale error, and `f` the
  cycle's bound per unit of flux (the proof takes any `f`).

It also records the measured ratio `δ_k / δ_{k−1}` for every run of the default rule.
"""

import json
import sys
from pathlib import Path

GAIN = 0.1


def read(path):
    return json.loads(Path(path).read_text())


def kappa_of(argv):
    if "-stop-rule-kappa" in argv:
        return float(argv[argv.index("-stop-rule-kappa") + 1])
    return 0.5 if "certified" in argv else None


def check_cycles(cycles, kappa, threshold):
    """The proved inequalities on one certified run, per cycle."""
    margin = 1.0 - kappa - GAIN / 2.0
    rows = []
    for i, c in enumerate(cycles):
        dq = c["q_before"] - c["q_after"]
        flux = c["abs_flux"]
        # The flux bound with T the threshold: every working peak is above it.
        flux_bound = dq / (margin * threshold)
        row = {
            "index": c["index"],
            "components": c["components"],
            "stop": c["stop"],
            "peak_start": c["peak_start"],
            "abs_flux": flux,
            "stale_linf": c["stale_linf"],
            "bound_linf": c["bound_linf"],
            "bound_violations": c["bound_violations"],
            "bound_over_stale": c["bound_linf"] / c["stale_linf"]
            if c["stale_linf"] > 0
            else None,
            "delta_q": dq,
            "flux_bound": flux_bound,
            "flux_bound_holds": flux <= flux_bound * (1 + 1e-9),
            "flux_bound_over_flux": flux_bound / flux if flux > 0 else None,
        }
        if i + 1 < len(cycles) and c["stop"] == "PeakRule" and flux > 0:
            stop_peak = cycles[i + 1]["peak_start"]
            f = c["bound_linf"] / flux
            left = kappa * margin * stop_peak * stop_peak
            right = f * dq
            row["stop_peak"] = stop_peak
            row["bound_per_flux"] = f
            row["stop_left"] = left
            row["stop_right"] = right
            # The next peak is a true value: P_next ≤ P_stop + e, so this may
            # exceed the proved form by the factor (1 + κ)² at most.
            row["stop_holds_up_to_stale"] = left <= right * (1 + kappa) ** 2
            row["stop_right_over_left"] = right / left if left > 0 else None
        rows.append(row)
    # The greedy ratio and the contraction of the peak, with Q_inf the final misfit.
    q_final = cycles[-1]["q_after"]
    for i, c in enumerate(cycles[:-1]):
        peak2 = c["peak_start"] ** 2
        reducible = c["q_before"] - q_final
        if peak2 > 0 and reducible > 0:
            mu = peak2 / (2.0 * reducible)
            rows[i]["greedy_mu"] = mu
            f = rows[i]["bound_linf"] / c["abs_flux"] if c["abs_flux"] > 0 else None
            rows[i]["contraction_predicted"] = (
                f / (2.0 * mu * kappa * margin) if f else None
            )
            rows[i]["contraction_measured"] = cycles[i + 1]["peak_start"] ** 2 / peak2
    return rows


def main(argv):
    runs, scores, probe, out = map(Path, argv[1:5])
    result = {"gain": GAIN, "runs": {}, "scores": {}, "probe": {}, "counter": {}}
    for report in sorted(runs.glob("*-report.json")):
        name = report.name[: -len("-report.json")]
        r = read(report)
        cycles = r["run"]["cycles"]
        kappa = kappa_of(r["argv"])
        rec = {
            "argv": r["argv"],
            "major_cycles": len(cycles),
            "components": sum(c["components"] for c in cycles),
            "seconds": r["seconds"],
            "q_final": cycles[-1]["q_after"],
        }
        threshold = r["settings"]["threshold"]
        if kappa is not None:
            rec["kappa"] = kappa
            rec["cycles"] = check_cycles(cycles, kappa, threshold)
        else:
            rec["cycles"] = [
                {
                    "index": c["index"],
                    "components": c["components"],
                    "stop": c["stop"],
                    "peak_start": c["peak_start"],
                    "abs_flux": c["abs_flux"],
                    "stale_linf": c["stale_linf"],
                    "delta": c["stale_linf"] / c["abs_flux"]
                    if c["abs_flux"] > 0
                    else None,
                    "delta_used": c["stale_per_flux_used"],
                    "delta_over_used": (c["stale_linf"] / c["abs_flux"])
                    / c["stale_per_flux_used"]
                    if c["stale_per_flux_used"] > 0 and c["abs_flux"] > 0
                    else None,
                    "stop_level_over_threshold": c["stale_per_flux_used"]
                    * c["abs_flux"]
                    / threshold,
                }
                for c in cycles
            ]
        result["runs"][name] = rec
    for path in sorted(scores.glob("*.json")):
        s = read(path)
        for name, job in s["jobs"].items():
            result["scores"][name] = {
                "q_over_q0": job.get("q_over_q0"),
                "q_over_q_truth": job.get("q_over_q_truth"),
                "false_flux": job.get("false_flux_abs"),
                "false_pixels": job.get("false_pixels"),
                "inner_peak": job.get("residual_inner_peak_abs"),
                "inner_rms": job.get("residual_inner_rms"),
                "flux_total": job.get("model_flux_total"),
            }
    for path in sorted(probe.glob("s*-u*.json")):
        result["probe"][path.stem] = read(path)
    for path in sorted(probe.glob("counter-*.json")):
        result["counter"][path.stem] = read(path)
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main(sys.argv)
