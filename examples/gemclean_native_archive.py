#!/usr/bin/env python3
"""Archive the timing against WSClean built for this CPU (research/gemclean-speed.md).

Usage: gemclean_native_archive.py NATIVE_OUT OPT_OUT MGAIN_OUT DEST.json
NATIVE_OUT holds rep1..rep3/{wsclean,gemclean}/timing/NAME.txt and
scores/{wsclean,gemclean}-SKY.json; OPT_OUT holds LABEL/rep*/timing/NAME.txt and
LABEL/score-SKY.json, the GeMClean variants at coarser gridding; MGAIN_OUT holds
mgainM/timing/NAME.txt and mgainM/score-SKY.json, WSClean minres at other -mgain.
"""

import json
import re
import statistics as st
import sys
from pathlib import Path

SKIES = ("s1", "s2", "s3", "h1", "h2", "h3", "h4")
THREADS = (16, 1)
VARIANTS = {"single-1e4": (1, 2, 3), "single-1e5": (1,)}
MGAINS = ("0.9", "0.95")


def parse(path):
    text = path.read_text()
    m = re.search(r"Elapsed.*?: (?:(\d+):)?(\d+):([\d.]+)\n", text)
    return {
        "wall": int(m[1] or 0) * 3600 + int(m[2]) * 60 + float(m[3]),
        "rss_gb": int(re.search(r"Maximum resident.*?: (\d+)", text)[1]) / 1e6,
        "exit": int(re.search(r"Exit status: (\d+)", text)[1]),
    }


def timing(paths):
    runs = [parse(p) for p in paths]
    walls = [t["wall"] for t in runs]
    return {
        "wall_s": [round(w, 2) for w in walls],
        "wall_median_s": round(st.median(walls), 2),
        "rss_gb": round(max(t["rss_gb"] for t in runs), 2),
        "exits": [t["exit"] for t in runs],
    }


def accuracy(rec):
    recovery = rec["recovery_all"]
    if isinstance(recovery, dict):
        recovery = recovery.get("flux_weighted")
    cycles = (rec.get("report") or {}).get("run", {}).get("major_cycles")
    if cycles is None:
        cycles = (rec.get("log") or {}).get("major_iterations")
    return {
        "q_over_q_truth": round(rec["q_over_q_truth"], 6),
        "false_flux_mjy": round(rec["false_flux_abs"] * 1e3, 3),
        "recovery": round(recovery, 5),
        "inner_peak_ujy": round(rec["residual_inner_peak_abs"] * 1e6, 1),
        "exact_inner_peak_ujy": round(rec["exact_residual_inner_peak_abs"] * 1e6, 1),
        "inner_rms_ujy": round(rec["residual_inner_rms"] * 1e6, 2),
        "major_cycles": cycles,
    }


def main(native, opt, mgain, dest):
    out = {
        "gemclean_commit": "3945394",
        "gemclean_build": "cargo +1.93, profile gemclean, target-cpu x86-64-v3, kernels at AVX-512",
        "wsclean": "v3.7, 4f395b28abb5eb0ceacfa05f61e3ee49d154d001, -DPORTABLE=OFF, tools/oracles/wsclean-native",
        "host": "Ryzen 7 7700X, 16 threads, WSL 2, data and outputs on the WSL disk; WSClean in Docker",
        "timing": {},
        "accuracy_j16": {},
    }
    for sky in SKIES:
        for j in THREADS:
            key = f"{sky}-j{j}"
            row = {}
            for grid in ("nominres", "minres"):
                name = f"{sky}-abs-{grid}-fast-j{j}"
                row[f"wsclean-{grid}"] = timing(
                    native / f"rep{r}" / "wsclean" / "timing" / f"{name}.txt"
                    for r in (1, 2, 3)
                )
            name = f"{sky}-abs-nominres-fast-j{j}"
            row["gemclean"] = timing(
                native / f"rep{r}" / "gemclean" / "timing" / f"{name}.txt"
                for r in (1, 2, 3)
            )
            for label, reps in VARIANTS.items():
                row[f"gemclean-{label}"] = timing(
                    opt / label / f"rep{r}" / "timing" / f"{name}.txt" for r in reps
                )
            for m in MGAINS:
                row[f"wsclean-minres-mgain{m}"] = timing(
                    [mgain / f"mgain{m}" / "timing" / f"{sky}-abs-minres-fast-j{j}.txt"]
                )
            out["timing"][key] = row
        name = f"{sky}-abs-nominres-fast-j16"
        scores = {
            "gemclean": json.loads(
                (native / "scores" / f"gemclean-{sky}.json").read_text()
            )["jobs"][name]
        }
        for label in VARIANTS:
            scores[f"gemclean-{label}"] = json.loads(
                (opt / label / f"score-{sky}.json").read_text()
            )["jobs"][name]
        ws = json.loads((native / "scores" / f"wsclean-{sky}.json").read_text())["jobs"]
        for grid in ("nominres", "minres"):
            scores[f"wsclean-{grid}"] = ws[f"{sky}-abs-{grid}-fast-j16"]
        for m in MGAINS:
            scores[f"wsclean-minres-mgain{m}"] = json.loads(
                (mgain / f"mgain{m}" / f"score-{sky}.json").read_text()
            )["jobs"][f"{sky}-abs-minres-fast-j16"]
        out["accuracy_j16"][sky] = {k: accuracy(v) for k, v in scores.items()}
    repeats = json.loads((native / "scores" / "repeats.json").read_text())
    out["repeats"] = {
        "comparisons": len(repeats),
        "identical": sum(1 for v in repeats.values() if v[0] == 0),
        "gemclean_differing": sum(
            1 for k, v in repeats.items() if k.startswith("gemclean/") and v[0]
        ),
        "wsclean_minres_j16_model_pixels": sorted(
            v[0] for k, v in repeats.items() if "abs-minres-fast-j16/model/rep" in k
        ),
        "wsclean_minres_j16_model_linf_mjy": round(
            max(
                v[1] for k, v in repeats.items() if "abs-minres-fast-j16/model/rep" in k
            )
            * 1e3,
            2,
        ),
    }
    dest.write_text(json.dumps(out, indent=1) + "\n")
    for key, row in out["timing"].items():
        print(key, {k: (v["wall_median_s"], v["rss_gb"]) for k, v in row.items()})
    print(out["repeats"])
    print(
        "exits",
        {e for row in out["timing"].values() for v in row.values() for e in v["exits"]},
    )


main(*map(Path, sys.argv[1:5]))
