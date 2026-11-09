"""Task C5b: one compact JSON of every loop result in the given run
directories (research/results/c5b-selfcal-masks.json) and a Markdown table.

    python examples/c5b_summary.py OUT.json RUN [RUN ...]
"""

import json
import sys
from pathlib import Path


def compact(r):
    rounds = []
    for e in r["rounds"]:
        p = e["truth"]["products"]
        d = e["truth"].get("delays")
        rounds.append(
            {
                "round": e["round"],
                "type": e["term"]["type"],
                "phase_deg": [p["phase_deg"]["median"], p["phase_deg"]["p95"]],
                "amp_rel": [p["amp_rel"]["median"], p["amp_rel"]["p95"]],
                "uncorrected_amp_rel_median": p["uncorrected_amp_rel"]["median"],
                "delay_ns": None if d is None else [d["median"], d["p95"]],
                "t2": e.get("t2"),
                "per_antenna_phase_deg_median": e["per_antenna_phase_deg_median"],
            }
        )
    return {
        "case": r["case"],
        "arm": r["arm"],
        "loop": r["loop"],
        "held_out": r["held_out"],
        "t2_pass": r["t2_pass"],
        "gemclean_sha256": r["gemclean_sha256"],
        "stage_wall_s_with_lock_wait": r["stage_wall_s_with_lock_wait"],
        "rounds": rounds,
        "images": r["images"],
        "g4_apply": r["g4_apply"],
        "model_by_baseline": r["model_by_baseline"],
    }


def main(out, runs):
    results = []
    for run in runs:
        for p in sorted(Path(run).glob("loop-*.json")):
            results.append({"run": str(run), **compact(json.loads(p.read_text()))})
    Path(out).write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    for r in results:
        for e in r["rounds"]:
            ph, am, dl = e["phase_deg"], e["amp_rel"], e["delay_ns"]
            amp = (
                f"{100 * am[0]:.2f} / {100 * am[1]:.2f} "
                f"({am[0] / e['uncorrected_amp_rel_median']:.2f}x)"
                if e["type"] == "Sa"
                else "–"
            )
            delay = f"{dl[0]:.4f} / {dl[1]:.3f}" if dl else "–"
            checks = (e["t2"] or {}).get("checks", {})
            failed = ",".join(k for k, v in checks.items() if not v) or "none"
            print(
                f"| {r['case']} | {r['arm']} | {e['round']} {e['type']} | "
                f"{ph[0]:.2f} / {ph[1]:.1f} | {amp} | {delay} | {failed} |"
            )
        imgs = "; ".join(
            f"{i['image']}: {i['clean']['components']} {i['clean']['stop']}"
            for i in r["images"]
        )
        mb = ", ".join(f"{b['rel_rms']:.3f}" for b in r["model_by_baseline"])
        print(
            f"|  |  | images {imgs} | model {mb} | g4 {r['g4_apply']['pass']} |  |  |"
        )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
