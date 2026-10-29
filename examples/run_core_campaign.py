"""Run a core campaign track with a side-effect audit.

Usage: python examples/run_core_campaign.py <track> outputs/<fresh-run> outputs/<inputs>

Tracks: `injections` (research/core-phase3.md) and `prospective`
(research/core-phase3b.md). Snapshots the size and modification time of every
input file and `git status --porcelain` before and after the run, and writes
side-effects.json next to result.json.
"""

import importlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKS = {
    "injections": "rangtoy.core_injections",
    "prospective": "rangtoy.core_prospective",
}


def snapshot(inputs):
    files = {
        str(p.relative_to(inputs)): [p.stat().st_size, p.stat().st_mtime_ns]
        for p in sorted(inputs.rglob("*"))
        if p.is_file() and p.name != "table.lock"
    }
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return files, status


def main():
    track, run_dir, inputs = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if track not in TRACKS:
        raise SystemExit(f"unknown track; choose from {sorted(TRACKS)}")
    if not str(run_dir).startswith("outputs/") or run_dir.exists():
        raise SystemExit("run directory must be new and beneath outputs/")
    module = importlib.import_module(TRACKS[track])
    before = snapshot(inputs)
    result = module.run(run_dir, inputs)
    after = snapshot(inputs)
    written = sorted(p.name for p in run_dir.iterdir())
    audit = {
        "track": track,
        "input_files_checked": len(before[0]),
        "inputs_unchanged": before[0] == after[0],
        "git_status_unchanged": before[1] == after[1],
        "run_dir_files": written,
        "only_result_written": written == ["result.json"],
    }
    (run_dir / "side-effects.json").write_text(json.dumps(audit, indent=1) + "\n")
    print(
        json.dumps(
            {
                "seconds_total": result.get("seconds_total"),
                "solves": result.get("actual_QC_solves"),
                **{k: v for k, v in audit.items() if k != "run_dir_files"},
            }
        )
    )


if __name__ == "__main__":
    main()
