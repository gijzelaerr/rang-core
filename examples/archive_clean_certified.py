"""Compact archive of the certified CLEAN study (research/clean-certified-imaging.md).

Collects the export's `meta.json`, the Rust example's `clean-certified.json`
(per-cycle diagnostics of every configuration), the comparison with WSClean
(`compare.json`), the CG budget sweep (`cg-sweep.json`) and the WSClean
timings and key log lines into `research/results/clean-certified-imaging.json`.

Usage:
    .venv/bin/python examples/archive_clean_certified.py INPUTS RUN COMPARE CG_SWEEP WSCLEAN OUT
"""

import argparse
import json
import subprocess
from pathlib import Path

KEY_LINES = (
    "Initial peak",
    "Next major iteration",
    "Stopped on peak",
    "Performed",
    "divergence",
    "increased to",
    "major iterations were performed",
    "Inversion:",
    "Fitting beam",
    "Minimal inversion size",
)


def _git(*args):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("inputs", "run", "compare", "cg_sweep", "wsclean", "out"):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    inputs, run, wsc = Path(args.inputs), Path(args.run), Path(args.wsclean)
    wsclean_jobs = {}
    for log in sorted(wsc.glob("*.log")):
        name = log.stem
        timing = (wsc / "timing" / f"{name}.txt").read_text().split()
        wsclean_jobs[name] = {
            "wall_s": float(timing[0]),
            "max_rss_kb": int(timing[1]),
            "exit": int(timing[2]),
            "key_lines": [
                line.strip()
                for line in log.read_text().splitlines()
                if any(k in line for k in KEY_LINES)
            ],
        }
    archive = {
        "study": "certified CLEAN on the LUNO 1934-638 four-station slice",
        "note": "research/clean-certified-imaging.md",
        "code_commit": _git("rev-parse", "HEAD"),
        "run_directories": {
            "inputs": str(inputs.resolve()),
            "run": str(run.resolve()),
            "wsclean": str(wsc.resolve()),
        },
        "inputs": json.loads((inputs / "meta.json").read_text()),
        "certified": json.loads((run / "clean-certified.json").read_text()),
        "comparison": json.loads(Path(args.compare).read_text()),
        "cg_sweep": json.loads(Path(args.cg_sweep).read_text()),
        "wsclean_jobs": wsclean_jobs,
    }
    Path(args.out).write_text(json.dumps(archive, indent=1, sort_keys=True) + "\n")
    print(f"wrote {args.out} ({Path(args.out).stat().st_size} bytes)")


if __name__ == "__main__":
    main()
