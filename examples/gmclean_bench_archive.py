"""Collect the gmclean benchmark records into one JSON archive.

Research note: research/gmclean-benchmark.md. Reads the catalogues and the
prepare records of the datasets and the scored jobs of each imager, and writes
research/results/gmclean-benchmark.json: dataset provenance and checksums, the
exact checks, the catalogues, one record per job (settings, exact command,
timing with its contention record, metrics, gmclean's report without the
per-cycle lists, kept in outputs/).

Usage:
    .venv/bin/python examples/gmclean_bench_archive.py OUT_ROOT OUT_JSON
"""

import argparse
import json
import subprocess
from pathlib import Path

DATASETS = ("slice", "s1", "s2", "s3")
TIMING_STATUS = (
    "PROVISIONAL (contended): every wall, CPU and speed number here was measured "
    "on a host shared with other sessions; not for speed comparisons"
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def slim_report(report):
    """gmclean's report without its per-cycle table."""
    out = {k: v for k, v in report.items() if k != "run"}
    out["run"] = {k: v for k, v in report["run"].items() if k != "cycles"}
    return out


def slim_job(job):
    job = dict(job)
    if job.get("report"):
        job["report"] = slim_report(job["report"])
    return job


def dataset_record(root, name):
    cat = read(root / "data" / f"{name}.json")
    meta = read(root / "prep" / name / "meta.json")
    keep = {k: v for k, v in meta.items() if k != "imaging_weight_sums"}
    sums = root / "wsclean" / "ms" / f"{name}.ms-sha256-before.txt"
    files = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, filename = line.split()
        files[filename] = digest
    return {"catalogue": cat, "prepare": keep, "main_table_sha256": files}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root")
    parser.add_argument("out_json")
    args = parser.parse_args(argv)
    root = Path(args.root)
    archive = {
        "note": "research/gmclean-benchmark.md",
        "output_root": str(root.resolve()),
        "code_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip(),
        "gmclean_commit": "d94850e",
        "timing_status": TIMING_STATUS,
        "datasets": {n: dataset_record(root, n) for n in DATASETS},
        "imagers": {},
    }
    for imager in ("wsclean", "gmclean"):
        archive["imagers"][imager] = {}
        for name in DATASETS:
            path = root / "scores" / f"{imager}-{name}.json"
            if not path.exists():
                continue
            scored = read(path)
            scored["jobs"] = {k: slim_job(v) for k, v in scored["jobs"].items()}
            scored["timing_status"] = TIMING_STATUS
            archive["imagers"][imager][name] = scored
    extras = {
        "thread_dependence": root / "scores" / "thread-dependence.json",
        "gmclean_tau_min_0p9_s1": root / "scores" / "gmclean-tau09-s1.json",
        "gmclean_mgain_0p1_s1": root / "scores" / "gmclean-mgain01-s1.json",
    }
    for key, path in extras.items():
        if path.exists():
            archive[key] = read(path)
            if "jobs" in archive[key]:
                jobs = archive[key]["jobs"]
                archive[key]["jobs"] = {k: slim_job(v) for k, v in jobs.items()}
    truths = {}
    for name in ("s1", "s2", "s3"):
        path = root / f"truth-{name}" / "score.json"
        if path.exists():
            truths[name] = read(path)["jobs"]["truth"]
    archive["pixelised_truth"] = truths
    Path(args.out_json).write_text(
        json.dumps(archive, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
