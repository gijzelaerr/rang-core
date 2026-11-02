"""Interleaved engineering comparison of gmclean variants (research/gmclean.md).

Runs each variant `repeats` times round by round under `perf stat` (Linux) and
prints the minimum wall time, CPU time and instructions per variant, with the
phase split and the science numbers of the report. Provisional by design: it
guides engineering on a shared host and gives no result for a paper.

    python3 examples/gmclean_compare.py SPEC.json OUT.json

SPEC: {"repeats": 3, "ms": {"point": "...", ...}, "base": ["-size", ...],
"sky_args": {"point": ["-abs-threshold", "1e-4"], ...}, "skies": ["point"],
"variants": [{"name": "a", "binary": "path", "args": [], "env": {}}], "scratch": "dir"}.
"""

import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

EVENTS = "task-clock,instructions:u,cycles:u,cache-misses:u"


def run_once(variant, spec, sky):
    prefix = Path(spec["scratch"]) / f"{sky}-{variant['name']}"
    with tempfile.NamedTemporaryFile("r", encoding="utf-8", suffix=".perf") as stat:
        command = [
            "perf", "stat", "-x", ",", "-o", stat.name, "-e", EVENTS,
            variant["binary"], "-name", str(prefix),
            *spec["base"], *spec["sky_args"][sky], *variant.get("args", []),
            spec["ms"][sky],
        ]
        env = {**os.environ, **variant.get("env", {})}
        with open("/proc/loadavg", encoding="utf-8") as f:
            load = float(f.read().split()[0])
        subprocess.run(command, check=True, env=env, stdout=subprocess.DEVNULL)
        counters = {}
        for line in stat.read().splitlines():
            parts = line.split(",")
            if len(parts) > 3 and parts[0] and not line.startswith("#"):
                try:
                    counters[parts[2].split(":")[0]] = float(parts[0])
                except ValueError:
                    pass
    report = json.loads((prefix.parent / f"{prefix.name}-report.json").read_text(encoding="utf-8"))
    return {"load": load, "counters": counters, "report": report}


def main():
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    Path(spec["scratch"]).mkdir(parents=True, exist_ok=True)
    samples = {}
    for repeat in range(spec["repeats"]):
        for sky in spec["skies"]:
            for variant in spec["variants"]:
                result = run_once(variant, spec, sky)
                samples.setdefault((sky, variant["name"]), []).append(result)
                print(sky, variant["name"], repeat, round(result["report"]["seconds"]["wall"], 2),
                      flush=True)
    rows = []
    for (sky, name), runs in samples.items():
        reports = [r["report"] for r in runs]
        last = reports[-1]["run"]
        walls = [r["seconds"]["wall"] for r in reports]
        cpu = [r["counters"].get("task-clock", float("nan")) / 1e9 for r in runs]
        phase = lambda key: min(r["run"]["seconds"][key] for r in reports)
        rows.append({
            "sky": sky, "variant": name,
            "wall_min": min(walls), "wall_median": statistics.median(walls), "cpu_min": min(cpu),
            "instructions_min": min(r["counters"].get("instructions", float("nan")) for r in runs),
            "cache_misses_min": min(r["counters"].get("cache-misses", float("nan")) for r in runs),
            "load": [r["load"] for r in runs],
            "minor_min": phase("minor"), "correction_min": phase("correction"),
            "resync_min": phase("resync"), "major_min": phase("major"),
            "psf_2n_min": min(r["seconds"]["psf_2n"] for r in reports),
            "components": last["components"], "major_cycles": last["major_cycles"],
            "resyncs": last["resyncs"]["total"], "q_final": last["q_final"],
            "model_flux": last["model_flux"], "work": last.get("work"),
        })
        print(f"{sky:8s} {name:24s} wall {min(walls):8.2f} cpu {min(cpu):8.1f} "
              f"minor {phase('minor'):7.2f} resync {phase('resync'):6.2f} major {phase('major'):7.2f} "
              f"comps {last['components']} cycles {last['major_cycles']} Q {last['q_final']:.9e}")
    Path(sys.argv[2]).write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
