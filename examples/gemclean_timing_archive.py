#!/usr/bin/env python3
"""Archive the quiet-host timing passes (research/gemclean-speed.md).

Usage: gemclean_timing_archive.py MAIN_OUT BASELINE_OUT DEST.json
MAIN_OUT and BASELINE_OUT hold rep1..rep3/{wsclean,gemclean}/timing/NAME.txt
(GNU time -v) and jobs.tsv, as examples/gemclean_bench_timing.sh leaves them.
"""

import json
import re
import statistics as st
import sys
from pathlib import Path

REPEATS = (1, 2, 3)


def parse(path):
    text = path.read_text()
    m = re.search(r"Elapsed.*?: (?:(\d+):)?(\d+):([\d.]+)\n", text)
    return {
        "wall": int(m[1] or 0) * 3600 + int(m[2]) * 60 + float(m[3]),
        "user": float(re.search(r"User time.*?: ([\d.]+)", text)[1]),
        "sys": float(re.search(r"System time.*?: ([\d.]+)", text)[1]),
        "rss_gb": int(re.search(r"Maximum resident.*?: (\d+)", text)[1]) / 1e6,
        "exit": int(re.search(r"Exit status: (\d+)", text)[1]),
    }


def outer_walls(run):
    lines = (run / "jobs.tsv").read_text().splitlines()[1:]
    return {f[0]: float(f[2]) for f in (line.split("\t") for line in lines)}


def summarise(root):
    jobs = {}
    for imager in ("wsclean", "gemclean"):
        names = sorted(
            p.stem for p in (root / "rep1" / imager / "timing").glob("*.txt")
        )
        for name in names:
            runs = []
            for rep in REPEATS:
                run = root / f"rep{rep}" / imager
                t = parse(run / "timing" / f"{name}.txt")
                t["outer_wall"] = outer_walls(run)[name]
                runs.append(t)
            walls = [t["wall"] for t in runs]
            jobs[f"{imager}/{name}"] = {
                "wall_s": [round(w, 2) for w in walls],
                "wall_median_s": round(st.median(walls), 2),
                "spread": round((max(walls) - min(walls)) / st.median(walls), 3),
                "user_median_s": round(st.median(t["user"] for t in runs), 1),
                "sys_median_s": round(st.median(t["sys"] for t in runs), 1),
                "rss_gb": round(max(t["rss_gb"] for t in runs), 2),
                "outside_minus_inside_s": round(
                    st.median(t["outer_wall"] - t["wall"] for t in runs), 2
                ),
                "exits": [t["exit"] for t in runs],
            }
    return jobs


def ratios(main, gem):
    out = {}
    for ds in ("s1", "s2", "s3"):
        for j in (16, 1):
            g = gem[f"gemclean/{ds}-abs-nominres-fast-j{j}"]["wall_median_s"]
            for grid in ("nominres", "minres"):
                w = main[f"wsclean/{ds}-abs-{grid}-fast-j{j}"]["wall_median_s"]
                out[f"{ds}-j{j}-{grid}"] = round(w / g, 2)
    return out


main_root, base_root, dest = map(Path, sys.argv[1:4])
main_jobs = summarise(main_root)
base_jobs = summarise(base_root)
archive = {
    "commit": "3945394",
    "host": "16 threads, WSL 2, data and outputs on the WSL disk",
    "repeats": len(REPEATS),
    "wsclean": "3.7-1kern1 in rang-o-casa:6.7.6.14; /usr/bin/wsclean holds the gridder, 0 ymm or zmm instructions",
    "gemclean_main": "cargo +1.93, profile gemclean (fat LTO), target-cpu x86-64-v3, kernels at AVX-512",
    "gemclean_baseline": "same commit, RUSTFLAGS -C target-cpu=x86-64, RANG_WGRIDDER_SIMD=baseline, RANG_GEMCLEAN_SIMD=baseline",
    "main": main_jobs,
    "baseline": base_jobs,
    "wsclean_over_gemclean_main": ratios(main_jobs, main_jobs),
    "wsclean_over_gemclean_baseline": ratios(main_jobs, base_jobs),
}
dest.write_text(json.dumps(archive, indent=1) + "\n")
for key in ("wsclean_over_gemclean_main", "wsclean_over_gemclean_baseline"):
    print(key, archive[key])
print(
    "outside minus inside, WSClean:",
    sorted(
        v["outside_minus_inside_s"]
        for k, v in main_jobs.items()
        if k.startswith("wsclean")
    ),
)
print(
    "spread max:",
    max(v["spread"] for v in main_jobs.values()),
    max(v["spread"] for v in base_jobs.values()),
)
print(
    "exits:",
    {
        e
        for v in list(main_jobs.values()) + list(base_jobs.values())
        for e in v["exits"]
    },
)
