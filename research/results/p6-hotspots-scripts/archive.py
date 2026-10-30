"""Assemble research/results/p6-hotspots.json from the run directories."""
import json
import statistics
import sys
from pathlib import Path

out = Path(sys.argv[1])
o = Path("outputs")


def tsv(path, fields):
    rows = []
    for line in Path(path).read_text().splitlines():
        parts = line.split("\t")
        rows.append(dict(zip(fields, parts)))
    return rows


def timing_rows(path, fields):
    rows = []
    for r in tsv(path, fields):
        wall, user, sys_, rss = r.pop("time").split()
        r.update(wall_s=float(wall), user_s=float(user), sys_s=float(sys_), peak_rss_mb=round(int(rss) / 1024, 1),
                 exit=int(r.pop("exit")), repeat=int(r["repeat"]))
        rows.append(r)
    return rows


ab = timing_rows(o / "p6-hotspots-20261030-06/timings.tsv", ["stage", "arm", "repeat", "exit", "time", "load_before", "load_after"])
summary = {}
for stage in ("trend", "signal"):
    s = {}
    for arm in ("base", "new"):
        walls = [r["wall_s"] for r in ab if r["stage"] == stage and r["arm"] == arm]
        s[arm] = {"min": min(walls), "median": statistics.median(walls), "walls": walls,
                  "user": [r["user_s"] for r in ab if r["stage"] == stage and r["arm"] == arm]}
    spread = s["base"]["median"] - s["base"]["min"]
    margin = s["base"]["min"] - s["new"]["min"]
    s["claim_rule"] = {"base_spread": round(spread, 2), "margin": round(margin, 2), "claimed": margin > spread}
    summary[stage] = s
checks = {}
for rep in (1, 2, 3):
    for stage in ("trend", "signal"):
        checks[f"identity-{stage}-{rep}"] = json.loads((o / f"p6-hotspots-20261030-06/identity-{stage}-{rep}.json").read_text())["files"]
        for arm in ("base", "new"):
            c = json.loads((o / f"p6-hotspots-20261030-06/compare-{stage}-{arm}-{rep}.json").read_text())
            checks[f"compare-{stage}-{arm}-{rep}"] = {"passed": c["passed"], "failures": c["failures"], "classes": {k: v["compared"] for k, v in c["classes"].items()}, "excluded": c["excluded"]}
trial = {}
for stage in ("trend", "signal"):
    c = json.loads((o / f"p6-hotspots-20261030-09/compare-{stage}.json").read_text())
    trial[stage] = {"passed": c["passed"], "failures": c["failures"], "classes": {k: v["compared"] for k, v in c["classes"].items()}, "excluded": c["excluded"],
                    "side_effects": json.loads((o / f"p6-hotspots-20261030-09/{stage}/side-effects.json").read_text())}
diag = [json.loads(line) for line in (o / "p6-hotspots-20261030-08/diag.jsonl").read_text().splitlines() if line.startswith("{")]
loads = [line for line in (o / "p6-hotspots-20261030-08/diag.jsonl").read_text().splitlines() if line.startswith("load")]
for d, l in zip(diag, loads):
    d["load_before"] = l.split()[1:4]
result = {
    "task": "P6 frozen Python hot spots (research/p6-python-hotspots.md)",
    "head_measured": (o / "p6-hotspots-20261030-06/provenance.txt").read_text().split()[1],
    "baseline_02": timing_rows(o / "p6-hotspots-20261030-02/timings.tsv", ["label", "stage", "repeat", "exit", "time", "load_before", "load_after"]),
    "frozen_ab_06": {"runs": ab, "summary": summary, "checks": checks},
    "post_hoc_diagnostic_signal_08": diag,
    "labelled_trial_09": {"switch_diff": (o / "p6-hotspots-20261030-09/switch.diff").read_text(), "stages": trial,
                          "loads": (o / "p6-hotspots-20261030-09/loads.txt").read_text().splitlines()},
}
out.write_text(json.dumps(result, indent=1) + "\n")
print(json.dumps(summary, indent=1))
