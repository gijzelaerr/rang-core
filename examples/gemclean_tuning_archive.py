#!/usr/bin/env python3
"""Archive the GeMClean tuning runs after the native pass (research/gemclean-speed.md).

Usage: gemclean_tuning_archive.py OPT_OUT DEST.json
OPT_OUT holds e3/tauT and e5/{band,bandtau}: NAME-report.json and score-SKY.json for
-j 16 and -j 1 on each sky, and e4/*.log, the band-tolerance sweep.
"""

import json
import re
import sys
from pathlib import Path

SKIES = ("s1", "s2", "s3", "h1", "h2", "h3", "h4")
RUNS = {
    "tau0.3": "e3/tau0.3",
    "tau0.2": "e3/tau0.2",
    "tau0.1": "e3/tau0.1",
    "band": "e5/band",
    "band-tau0.2": "e5/bandtau",
}


def row(root, sky):
    name = f"{sky}-abs-nominres-fast"
    r16 = json.loads((root / f"{name}-j16-report.json").read_text())
    r1 = json.loads((root / f"{name}-j1-report.json").read_text())
    score = json.loads((root / f"score-{sky}.json").read_text())["jobs"][f"{name}-j16"]
    recovery = score["recovery_all"]
    if isinstance(recovery, dict):
        recovery = recovery.get("flux_weighted")
    return {
        "wall_j16_s": round(r16["seconds"]["wall"], 2),
        "wall_j1_s": round(r1["seconds"]["wall"], 2),
        "rss_gb_j16": round(r16["peak_memory_bytes"] / 1e9, 2),
        "major_cycles_j16": r16["run"]["major_cycles"],
        "major_cycles_j1": r1["run"]["major_cycles"],
        "resyncs_j1": r1["run"]["resyncs"]["total"],
        "q_over_q_truth": round(score["q_over_q_truth"], 6),
        "false_flux_mjy": round(score["false_flux_abs"] * 1e3, 3),
        "recovery": round(recovery, 5),
        "exact_inner_peak_ujy": round(score["exact_residual_inner_peak_abs"] * 1e6, 1),
    }


def sweep(root):
    out = {}
    for log in sorted((root / "e4").glob("*.log")):
        text = log.read_text(errors="replace")
        columns = re.search(r"(\d+) of (\d+) spectrum columns", text)
        times = re.search(r"resync ([\d.]+) s, major ([\d.]+) s", text)
        wall = re.search(r"wall ([\d.]+) s", text)
        out[log.stem] = {
            "columns": [int(columns[1]), int(columns[2])],
            "resync_s": float(times[1]),
            "major_s": float(times[2]),
            "wall_s": float(wall[1]),
        }
    return out


def main(opt, dest):
    out = {
        "settings": "all with -single -wgridder-accuracy 1e-4; one run each, not interleaved",
        "binary_e3": "3945394",
        "binary_e5": "the -beam-band commit, profile gemclean; e3 ran 2026-11-04, e5 2026-11-05",
        "runs": {
            label: {sky: row(opt / path, sky) for sky in SKIES}
            for label, path in RUNS.items()
        },
        "band_tolerance_sweep": sweep(opt),
    }
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(len(out["runs"]), "runs,", len(out["band_tolerance_sweep"]), "sweep logs")


main(Path(sys.argv[1]), Path(sys.argv[2]))
