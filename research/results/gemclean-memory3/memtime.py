# SPDX-License-Identifier: MIT
"""Run a command and record its exit code, wall time, mean cores and peak
memory (research/gemclean-memory.md): arm A5's a5_time.py (the sum of the
process tree's resident sets, sampled every 2 s with psutil) plus, on
Windows, the largest process's own peak working set and peak private bytes
(psutil `peak_wset`, `peak_pagefile`; these are the process's lifetime
peaks, so the last sample before exit holds them up to then). A uv venv's
python.exe is a launcher, so the tree is read.

    memtime.py OUT_JSON -- COMMAND ...
"""

import json
import subprocess
import sys
import time

import psutil

out = sys.argv[1]
cmd = sys.argv[sys.argv.index("--") + 1 :]
t0 = time.time()
p = subprocess.Popen(cmd)
root = psutil.Process(p.pid)
peak, cpu, wset, private = 0, {}, 0, 0
while p.poll() is None:
    try:
        procs = [root, *root.children(recursive=True)]
        rss = 0
        for q in procs:
            try:
                m = q.memory_info()
                rss += m.rss
                wset = max(wset, getattr(m, "peak_wset", 0))
                private = max(private, getattr(m, "peak_pagefile", 0))
                c = q.cpu_times()
                cpu[q.pid] = c.user + c.system
            except psutil.Error:
                pass
        peak = max(peak, rss)
    except psutil.Error:
        pass
    time.sleep(2)
wall = time.time() - t0
rec = {
    "argv": cmd,
    "exit": p.returncode,
    "wall_s": round(wall, 1),
    "peak_rss_gb": round(peak / 2**30, 2),
    "peak_working_set_gib": round(wset / 2**30, 2),
    "peak_private_gib": round(private / 2**30, 2),
    "cpu_s": round(sum(cpu.values()), 1),
    "mean_cores": round(sum(cpu.values()) / wall, 2) if wall > 0 else None,
}
with open(out, "w") as f:
    json.dump(rec, f, indent=1)
print(json.dumps({k: v for k, v in rec.items() if k != "argv"}))
sys.exit(p.returncode)
