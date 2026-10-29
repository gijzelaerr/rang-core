"""Run the core injection campaign with a side-effect audit (research/core-phase3.md).

Usage: python examples/run_core_injections.py outputs/<fresh-run> outputs/<prepared>

Snapshots the size and modification time of every file in the prepared
directory and `git status --porcelain` before and after
`rangtoy.core_injections.run`, and writes side-effects.json next to result.json.
"""

import json
import subprocess
import sys
from pathlib import Path

from rangtoy import core_injections

ROOT = Path(__file__).resolve().parents[1]


def snapshot(prepared):
    files = {
        str(p.relative_to(prepared)): [p.stat().st_size, p.stat().st_mtime_ns]
        for p in sorted(prepared.rglob("*"))
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
    run_dir, prepared = Path(sys.argv[1]), Path(sys.argv[2])
    if not str(run_dir).startswith("outputs/") or run_dir.exists():
        raise SystemExit("run directory must be new and beneath outputs/")
    before = snapshot(prepared)
    result = core_injections.run(run_dir, prepared)
    after = snapshot(prepared)
    written = sorted(p.name for p in run_dir.iterdir())
    audit = {
        "prepared_files_checked": len(before[0]),
        "prepared_unchanged": before[0] == after[0],
        "git_status_unchanged": before[1] == after[1],
        "run_dir_files": written,
        "only_result_written": written == ["result.json"],
    }
    (run_dir / "side-effects.json").write_text(json.dumps(audit, indent=1) + "\n")
    print(
        json.dumps(
            {
                "seconds_total": result["seconds_total"],
                "selected": [
                    c["controls"]["selected_policy"]["trial"] for c in result["cases"]
                ],
                "injection_checks_pass": all(
                    all(v.values()) for v in result["injection_checks"].values()
                ),
                **{k: v for k, v in audit.items() if k != "run_dir_files"},
            }
        )
    )


if __name__ == "__main__":
    main()
