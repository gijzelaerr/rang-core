"""Collect the runs of research/gram-solver.md into research/results/gram-solver.json.

Usage: python3 examples/gram_solver_archive.py ROOT OUT_JSON

ROOT is the SOLVER_ROOT of examples/gram_solver_jobs.sh: runs/<dataset>/ holds
NAME.json (the bench's summary), NAME.jsonl (one line per iterate or outer cycle),
NAME.log, timing/NAME.{perf,txt}, load/NAME.start. scores/*.json are the output of
gemclean_bench_compare.py score, evals/*.jsonl the output of the bench's eval mode.
Standard library only.
"""

import json
import math
import re
import sys
from pathlib import Path


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def perf(path):
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split(",")
            if len(parts) > 2 and parts[0].isdigit():
                out[parts[2].split(":")[0]] = int(parts[0])
    return out


def time_v(path):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    out = {}
    for key, pat in {
        "user_s": r"User time \(seconds\): ([\d.]+)",
        "system_s": r"System time \(seconds\): ([\d.]+)",
        "max_rss_kb": r"Maximum resident set size \(kbytes\): (\d+)",
    }.items():
        m = re.search(pat, text)
        if m:
            out[key] = float(m.group(1))
    m = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([\d:.]+)", text)
    if m:
        parts = [float(x) for x in m.group(1).split(":")]
        out["wall_s"] = sum(v * 60**i for i, v in enumerate(reversed(parts)))
    return out


def load_lines(path):
    if not path.exists():
        return None
    return [
        [float(v) for v in line.split()[:3]]
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def finite(value):
    """JSON has no NaN: turn it into null, throughout."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [finite(v) for v in value]
    return value


def thin(rows, keep=40):
    """Every n-th row, and the last, of a long trajectory."""
    if len(rows) <= keep:
        return rows
    step = max(1, len(rows) // keep)
    return rows[::step] + rows[-1:]


def main(argv):
    root, out = Path(argv[1]), Path(argv[2])
    archive = {
        "note": "research/gram-solver.md",
        "timing_status": "PROVISIONAL: shared host, load recorded per job; "
        "instructions and cycles are from perf stat",
        "runs": {},
        "scores": {},
        "evals": {},
    }
    for run in sorted((root / "runs").glob("s?")):
        dataset = {}
        names = {p.stem for p in run.glob("*.jsonl")} | {
            p.stem for p in (run / "timing").glob("*.perf")
        }
        for name in sorted(names):
            rec = {
                "summary": read_json(run / f"{name}.json"),
                "perf": perf(run / "timing" / f"{name}.perf"),
                "time": time_v(run / "timing" / f"{name}.txt"),
                "load": load_lines(run / "load" / f"{name}.start"),
            }
            lines = []
            path = run / f"{name}.jsonl"
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        lines.append(json.loads(line))
                    except ValueError:
                        pass
            outer = [r for r in lines if "outer" in r]
            iters = [r for r in lines if "k" in r]
            if outer:
                rec["outer"] = outer
            if iters:
                rec["iterates"] = thin(iters)
            log = run / f"{name}.log"
            if log.exists():
                last = [
                    line
                    for line in log.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                    if line.startswith("{")
                ]
                if last and rec["summary"] is None:
                    try:
                        rec["log_last"] = json.loads(last[-1])
                    except ValueError:
                        pass
            dataset[name] = rec
        archive["runs"][run.name] = dataset
    for path in sorted((root / "scores").glob("*.json")):
        data = read_json(path)
        if data:
            for job in data.get("jobs", {}).values():
                for drop in ("report", "log", "busy_processes"):
                    job.pop(drop, None)
            archive["scores"][path.stem] = data
    for path in sorted((root / "evals").glob("*.jsonl")):
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
        archive["evals"][path.stem] = rows
    extra = read_json(root / "derived.json")
    if extra:
        archive["derived"] = extra
    text = json.dumps(finite(archive), indent=1, allow_nan=False)
    out.write_text(text, encoding="utf-8")
    print(f"{out}: {out.stat().st_size} bytes")


if __name__ == "__main__":
    main(sys.argv)
