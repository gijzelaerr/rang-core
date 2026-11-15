"""Arm A5 (research/e2b-misses.md 9.20): run a command on Windows and record
its exit code, wall time, the peak resident memory of its process tree and
its mean CPU use (cores), sampled every 2 s with psutil (a uv venv's
python.exe is a launcher, so the tree is summed).

    a5_time.py OUT_JSON -- COMMAND ...
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
peak, cpu = 0, {}
while p.poll() is None:
    try:
        procs = [root, *root.children(recursive=True)]
        rss = 0
        for q in procs:
            try:
                rss += q.memory_info().rss
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
    "cpu_s": round(sum(cpu.values()), 1),
    "mean_cores": round(sum(cpu.values()) / wall, 2) if wall > 0 else None,
}
with open(out, "w") as f:
    json.dump(rec, f, indent=1)
print(json.dumps({k: v for k, v in rec.items() if k != "argv"}))
sys.exit(p.returncode)
