# SPDX-License-Identifier: GPL-3.0-or-later
"""One timed reading on a shared Linux host (research/nash-host.md), with the
foreign-load record of the nash amendments (research/ts-p1.md 15.8,
research/chunk-task-api.md 5.1).

    python3 timed.py --out READINGS.jsonl --label NAME [--cwd DIR] [--log FILE]
                     [--max-foreign 2.0] [--quiet-wait 7200] -- COMMAND ...

Before the command: waits until the host's busy CPU, averaged over 30 s, is
at most --max-foreign cores (none of the timed job runs yet, so all of it is
foreign), for at most --quiet-wait seconds. Then it records load1 and a
per-user CPU snapshot (`top -bn2 -d 5`, second frame), runs the command and
records the same after it.

During the command: host busy CPU-seconds from /proc/stat (user, nice,
system, irq, softirq, steal) and the command's own CPU-seconds and peak RSS
from wait4. foreign_cores = (host busy - own) / wall: everything outside the
timed process tree, other users' jobs and our own unlocked jobs alike. The
reading is void when foreign_cores > --max-foreign. One JSON line per
reading is appended to --out; the exit status is the command's.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

HZ = os.sysconf("SC_CLK_TCK")


def busy_seconds():
    with open("/proc/stat", encoding="ascii") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    # user nice system idle iowait irq softirq steal
    return (v[0] + v[1] + v[2] + v[5] + v[6] + v[7]) / HZ


def load1():
    with open("/proc/loadavg", encoding="ascii") as f:
        return float(f.read().split()[0])


def users_cpu():
    """Per-user %CPU from the second frame of top (a 5 s interval)."""
    out = subprocess.run(
        ["top", "-bn2", "-d", "5", "-w", "200"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    frame = out.split("top - ")[-1].splitlines()
    total, rows = {}, False
    for line in frame:
        parts = line.split()
        if parts[:2] == ["PID", "USER"]:
            rows = True
            continue
        if rows and len(parts) >= 12:
            try:
                total[parts[1]] = total.get(parts[1], 0.0) + float(parts[8])
            except ValueError:
                pass
    return {u: round(c, 1) for u, c in sorted(total.items()) if c >= 1.0}


def wait_quiet(limit, timeout):
    start = time.time()
    while True:
        b0, t0 = busy_seconds(), time.time()
        time.sleep(30)
        cores = (busy_seconds() - b0) / (time.time() - t0)
        if cores <= limit or time.time() - start > timeout:
            return round(time.time() - start, 1), round(cores, 2)


def measure(cmd, env=None, cwd=None, log=None, max_foreign=2.0, quiet_wait=7200):
    waited, quiet_cores = wait_quiet(max_foreign, quiet_wait)
    rec = {
        "cmd": cmd,
        "quiet_wait_s": waited,
        "busy_cores_before_30s": quiet_cores,
        "load1_before": load1(),
        "users_cpu_before": users_cpu(),
    }
    samples = []
    out = open(log, "w", encoding="utf-8") if log else None  # noqa: SIM115
    b0, t0 = busy_seconds(), time.time()
    rec["started"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t0))
    rec["started_unix"] = round(t0, 6)
    proc = subprocess.Popen(
        cmd,
        env=env,
        cwd=cwd,
        stdout=out or sys.stdout,
        stderr=subprocess.STDOUT,
    )
    stop = threading.Event()

    def sampler():
        last_b, last_t = b0, t0
        while not stop.wait(10):
            b, t = busy_seconds(), time.time()
            samples.append(round((b - last_b) / (t - last_t), 2))
            last_b, last_t = b, t

    th = threading.Thread(target=sampler, daemon=True)
    th.start()
    _, status, ru = os.wait4(proc.pid, 0)
    wall = time.time() - t0
    busy = busy_seconds() - b0
    stop.set()
    th.join()
    if out:
        out.close()
    own = ru.ru_utime + ru.ru_stime
    foreign = (busy - own) / wall
    rec.update(
        exit=os.waitstatus_to_exitcode(status),
        wall_s=round(wall, 2),
        own_cpu_s=round(own, 1),
        max_rss_kb=ru.ru_maxrss,
        host_busy_cpu_s=round(busy, 1),
        foreign_cores=round(foreign, 2),
        host_busy_cores_10s=samples,
        load1_after=load1(),
        users_cpu_after=users_cpu(),
        max_foreign=max_foreign,
        void=foreign > max_foreign,
    )
    proc.returncode = rec["exit"]
    return rec


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--cwd")
    p.add_argument("--log")
    p.add_argument("--max-foreign", type=float, default=2.0)
    p.add_argument("--quiet-wait", type=float, default=7200)
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    a = p.parse_args()
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    rec = {"label": a.label}
    rec.update(measure(cmd, None, a.cwd, a.log, a.max_foreign, a.quiet_wait))
    with open(a.out, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps({k: rec[k] for k in ("label", "exit", "wall_s", "max_rss_kb",
                                          "foreign_cores", "void")}))  # fmt: skip
    sys.exit(rec["exit"])


if __name__ == "__main__":
    main()
