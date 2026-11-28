# SPDX-License-Identifier: MIT
"""Run a command and report its process tree's memory (Windows stand-in for /usr/bin/time %M).

Polls every 0.2 s: each process's own peak working set (psutil `peak_wset`, exact for a process
seen alive near its end) and the sum of the tree's working sets. Prints one line at the end:
`peak: wall S s, largest process K KiB (name), tree sum K KiB` and writes peak.json next to
the command's cwd when RANG_PEAK_JSON names a path.
"""

import json
import os
import subprocess
import sys
import time

import psutil

t0 = time.perf_counter()
p = subprocess.Popen(sys.argv[1:])
root = psutil.Process(p.pid)
peaks, names, tree = {}, {}, 0
while p.poll() is None:
    try:
        procs = [root, *root.children(recursive=True)]
    except psutil.NoSuchProcess:
        procs = []
    s = 0
    for q in procs:
        try:
            m = q.memory_info()
            peaks[q.pid] = max(peaks.get(q.pid, 0), getattr(m, "peak_wset", m.rss))
            names[q.pid] = (
                " ".join(q.cmdline()[:3])[-80:] if q.pid not in names else names[q.pid]
            )
            s += m.rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    tree = max(tree, s)
    time.sleep(0.2)
wall = time.perf_counter() - t0
pid = max(peaks, key=peaks.get) if peaks else None
out = {
    "argv": sys.argv[1:],
    "returncode": p.returncode,
    "wall_s": wall,
    "largest_kib": (peaks[pid] // 1024) if pid else None,
    "largest": names.get(pid),
    "tree_sum_kib": tree // 1024,
    "processes": {
        names.get(k, str(k)) + f" [{k}]": v // 1024 for k, v in peaks.items()
    },
}
print(
    f"peak: wall {wall:.1f} s, largest process {out['largest_kib']} KiB ({out['largest']}), "
    f"tree sum {out['tree_sum_kib']} KiB",
    flush=True,
)
if os.environ.get("RANG_PEAK_JSON"):
    with open(os.environ["RANG_PEAK_JSON"], "w") as fh:
        json.dump(out, fh, indent=1)
sys.exit(p.returncode)
