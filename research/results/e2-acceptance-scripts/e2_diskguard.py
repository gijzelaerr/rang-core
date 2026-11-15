"""Run one command and stop it before a drive drops under a free-space floor
(research/e2-acceptance.md 9.6, the E2-A rerun's stop rule).

    python e2_diskguard.py --path D:\\ --min-free-gib 165 --log OUT.jsonl -- COMMAND [ARGS...]

Every `--every` seconds (default 5) it reads the free space of the drive that
holds `--path` (shutil.disk_usage). When it is below `--min-free-gib` it stops
the command's whole process tree (psutil terminate, which on Windows is
already TerminateProcess, a hard kill; elsewhere SIGTERM, then kill after
`--grace` s), appends a `halt` record and exits 75; otherwise it returns the
command's exit code. It touches no process outside the tree it started. It
refuses to start (exit 75, a `refused` record) below `--start-min-free-gib`
(default: `--min-free-gib`): run inside the lock, that is the start rule
checked when the run actually starts, not when it was queued.

Every `--record` seconds (default 60), and at start, halt and end, it appends
one JSON line to `--log` and fsyncs it, so the record survives a power cut or
a kill (e2_timed.py writes only at exit, which is how the interrupted run's
timing was lost, 9.4): wall time, free GiB, the tree's summed resident set,
its CPU seconds (live processes plus the exited ones it saw), the host's CPU
load and its process count.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import psutil

GIB = 1024**3
HALT_RC = 75


def tree(root):
    try:
        return [root, *root.children(recursive=True)]
    except psutil.NoSuchProcess:
        return []


def sample(root, cpu_seen):
    """(summed RSS bytes, CPU seconds of the tree so far, process count)."""
    rss, n = 0, 0
    for p in tree(root):
        try:
            with p.oneshot():
                rss += p.memory_info().rss
                t = p.cpu_times()
            cpu_seen[(p.pid, p.create_time())] = t.user + t.system
            n += 1
        except psutil.Error:
            continue
    return rss, sum(cpu_seen.values()), n


def stop_tree(root, grace):
    procs = tree(root)
    for p in reversed(procs):  # children first
        try:
            p.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(procs, timeout=grace)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass
    return len(procs), len(alive)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--" not in argv:
        sys.exit("usage: e2_diskguard.py [options] -- COMMAND [ARGS...]")
    cut = argv.index("--")
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--min-free-gib", type=float, required=True)
    ap.add_argument("--start-min-free-gib", type=float, default=None)
    ap.add_argument("--log", required=True)
    ap.add_argument("--every", type=float, default=5.0)
    ap.add_argument("--record", type=float, default=60.0)
    ap.add_argument("--grace", type=float, default=30.0)
    args = ap.parse_args(argv[:cut])
    cmd = argv[cut + 1 :]
    if not cmd:
        sys.exit("e2_diskguard.py: no command after --")

    def free_gib():
        return shutil.disk_usage(args.path).free / GIB

    def write(rec):
        rec["time"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with open(args.log, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    start_floor = max(args.min_free_gib, args.start_min_free_gib or 0.0)
    if free_gib() < start_floor:
        write({"event": "refused", "free_gib": free_gib(), "start_min_free_gib": start_floor,
               "command": cmd})  # fmt: skip
        print(f"e2_diskguard: {free_gib():.1f} GiB free < {start_floor}; not started",
              file=sys.stderr)  # fmt: skip
        return HALT_RC
    psutil.cpu_percent(None)
    start = time.time()
    proc = subprocess.Popen(cmd)
    root = psutil.Process(proc.pid)
    cpu_seen = {}
    peak_rss, min_free = 0, free_gib()
    write({"event": "start", "pid": proc.pid, "command": cmd, "free_gib": min_free,
           "min_free_gib": args.min_free_gib, "logical_cpus": psutil.cpu_count()})  # fmt: skip
    last = 0.0
    while proc.poll() is None:
        free = free_gib()
        min_free = min(min_free, free)
        rss, cpu, n = sample(root, cpu_seen)
        peak_rss = max(peak_rss, rss)
        now = time.time()
        if free < args.min_free_gib:
            stopped, killed = stop_tree(root, args.grace)
            write({"event": "halt", "wall_s": now - start, "free_gib": free,
                   "min_free_gib": args.min_free_gib, "tree_cpu_s": cpu,
                   "processes_stopped": stopped, "killed_after_grace": killed,
                   "peak_tree_rss_gib": peak_rss / GIB})  # fmt: skip
            print(f"e2_diskguard: {free:.1f} GiB free < {args.min_free_gib}; run stopped",
                  file=sys.stderr)  # fmt: skip
            return HALT_RC
        if now - last >= args.record:
            write({"event": "sample", "wall_s": now - start, "free_gib": free,
                   "tree_rss_gib": rss / GIB, "tree_cpu_s": cpu, "processes": n,
                   "host_cpu_pct": psutil.cpu_percent(None),
                   "host_processes": len(psutil.pids())})  # fmt: skip
            last = now
        time.sleep(args.every)
    write({"event": "end", "rc": proc.returncode, "wall_s": time.time() - start,
           "free_gib": free_gib(), "min_free_gib_seen": min_free,
           "tree_cpu_s": sum(cpu_seen.values()), "peak_tree_rss_gib": peak_rss / GIB})  # fmt: skip
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
