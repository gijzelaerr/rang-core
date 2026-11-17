"""Wall time and peak memory of one command and its whole process tree
(research/e2-acceptance.md, part 2, timing method).

    python e2_timed.py OUT.json -- COMMAND [ARGS...]

Every second it sums the resident set (Windows: working set) of the command's
process and all its descendants (psutil) and keeps the largest sum and the
largest single process; it records the host's CPU load (psutil, whole host,
percent) at start and its mean and maximum over the run, and the wall time.
The command's exit code is returned and written. Sampling at 1 s can miss a
peak shorter than that; the per-process peak working sets reported by the
operating system at exit are not available for descendants, so the sampled
values are what is reported.
"""

import json
import subprocess
import sys
import time

import psutil


def tree(p):
    try:
        return [p, *p.children(recursive=True)]
    except psutil.NoSuchProcess:
        return []


def main():
    out = sys.argv[1]
    cmd = sys.argv[sys.argv.index("--") + 1 :]
    psutil.cpu_percent(None)
    time.sleep(1.0)
    load0 = psutil.cpu_percent(None)
    start = time.time()
    proc = subprocess.Popen(cmd)
    root = psutil.Process(proc.pid)
    peak_tree = peak_one = 0
    loads = []
    while proc.poll() is None:
        total = 0
        for q in tree(root):
            try:
                rss = q.memory_info().rss
            except psutil.Error:
                continue
            total += rss
            peak_one = max(peak_one, rss)
        peak_tree = max(peak_tree, total)
        loads.append(psutil.cpu_percent(None))
        time.sleep(1.0)
    wall = time.time() - start
    rec = {
        "command": cmd,
        "rc": proc.returncode,
        "wall_s": wall,
        "peak_tree_rss_bytes": peak_tree,
        "peak_process_rss_bytes": peak_one,
        "host_cpu_load_pct_at_start": load0,
        "host_cpu_load_pct_mean": sum(loads) / len(loads) if loads else None,
        "host_cpu_load_pct_max": max(loads) if loads else None,
        "logical_cpus": psutil.cpu_count(),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start)),
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
