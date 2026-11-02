"""Collect the runs of research/gridder-theory.md into its JSON archive.

Usage: python3 examples/gridder_gram_archive.py RUN_DIR OUT_JSON

RUN_DIR holds the bench lines (*.jsonl with their *.perf), jobs/ from
examples/gridder_gram_jobs.sh, and scores/*.json from gmclean_bench_compare.py.
"""

import json
import pathlib
import re
import sys


def instructions(path):
    for line in path.read_text().splitlines():
        if "instructions" in line:
            return int(line.split(",")[0])
    return None


def main():
    run = pathlib.Path(sys.argv[1])
    bench = {}
    for path in sorted(run.glob("*.jsonl")):
        rows = [
            json.loads(x) for x in path.read_text().splitlines() if x.startswith("{")
        ]
        perf = path.with_suffix(".perf")
        bench[path.stem] = {
            "rows": rows,
            "instructions": instructions(perf) if perf.exists() else None,
        }
    jobs = {}
    times = {}
    jobs_dir = run / "jobs"
    tsv = jobs_dir / "jobs.tsv"
    if tsv.exists():
        for line in tsv.read_text().splitlines():
            f = line.split()
            times[f[0]] = {"wall_s": float(f[2]), "load": [float(x) for x in f[4:]]}
    for log in sorted(jobs_dir.glob("*.log")):
        name = log.stem
        text = log.read_text()
        entry = dict(times.get(name, {}))
        m = re.search(
            r"(\d+) components, (\d+) major cycles, (\d+) resyncs, stop (\w+); "
            r"Q/Q0 ([\d.e+-]+);.*minor ([\d.]+) s .*resync ([\d.]+) s, major ([\d.]+) s",
            text,
        )
        if m:
            entry.update(
                components=int(m[1]),
                major_cycles=int(m[2]),
                resyncs=int(m[3]),
                stop=m[4],
                q_over_q0=float(m[5]),
                minor_s=float(m[6]),
                resync_s=float(m[7]),
                major_s=float(m[8]),
            )
        m = re.search(r"; PSF ([\d.]+) s, FFT ([\d.]+) s", text)
        if m:
            entry["psf_s"] = float(m[1])
        m = re.search(r"gram operator: (\d+) nodes.*cube ([\d.]+) GB, ([\d.]+) s", text)
        if m:
            entry.update(nodes=int(m[1]), cube_gb=float(m[2]), setup_s=float(m[3]))
        m = re.search(
            r"last residual against the gridder, L-inf ([\d.e+-]+); "
            r"Q ([\d.e+-]+) operator, ([\d.e+-]+) gridder; exact pass ([\d.]+) s",
            text,
        )
        if m:
            entry.update(
                last_residual_linf=float(m[1]),
                q_operator=float(m[2]),
                q_gridder=float(m[3]),
                exact_pass_s=float(m[4]),
            )
        tpath = log.with_suffix(".time")
        if tpath.exists():
            m = re.search(
                r"Maximum resident set size \(kbytes\): (\d+)", tpath.read_text()
            )
            if m:
                entry["peak_rss_gb"] = round(int(m[1]) / 1048576, 2)
            m = re.search(r"User time \(seconds\): ([\d.]+)", tpath.read_text())
            if m:
                entry["user_cpu_s"] = float(m[1])
        jobs[name] = entry
    scores = {}
    for path in (
        sorted((run / "scores").glob("*.json")) if (run / "scores").exists() else []
    ):
        data = json.loads(path.read_text())
        keep = (
            "q_over_q_truth",
            "q_over_q0",
            "false_flux_abs",
            "false_pixels",
            "model_pixels",
            "residual_inner_peak_abs",
            "exact_residual_inner_peak_abs",
            "exact_residual_inner_rms",
            "total_flux_error",
            "dynamic_range",
            "restored_peak",
            "model_fits_sha256",
        )
        scores[path.stem] = {
            "q0": data["q0"],
            "q_truth": data["q_truth"],
            "jobs": {k: {a: v.get(a) for a in keep} for k, v in data["jobs"].items()},
        }
    archive = {
        "experiment": "visibility-free major cycle (research/gridder-theory.md)",
        "timing_status": "PROVISIONAL: shared host; load recorded per job. "
        "Instructions are load-independent.",
        "bench": bench,
        "jobs": jobs,
        "scores": scores,
    }
    pathlib.Path(sys.argv[2]).write_text(json.dumps(archive, indent=1))


if __name__ == "__main__":
    main()
