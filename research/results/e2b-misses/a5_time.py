"""Arm A5 (research/e2b-misses.md 9.18): run a command on Windows and record
its exit code, wall time and peak working set (GetProcessMemoryInfo).

    a5_time.py OUT_JSON -- COMMAND ...
"""

import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes


class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (n, ctypes.c_size_t)
        for n in (
            "PeakWorkingSetSize",
            "WorkingSetSize",
            "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage",
            "PagefileUsage",
            "PeakPagefileUsage",
        )
    ]


out = sys.argv[1]
cmd = sys.argv[sys.argv.index("--") + 1 :]
t0 = time.time()
p = subprocess.Popen(cmd)
rc = p.wait()
wall = time.time() - t0
pmc = PMC()
pmc.cb = ctypes.sizeof(PMC)
ok = ctypes.windll.psapi.GetProcessMemoryInfo(int(p._handle), ctypes.byref(pmc), pmc.cb)
rec = {
    "argv": cmd,
    "exit": rc,
    "wall_s": round(wall, 1),
    "peak_working_set_gb": round(pmc.PeakWorkingSetSize / 2**30, 2) if ok else None,
    "peak_pagefile_gb": round(pmc.PeakPagefileUsage / 2**30, 2) if ok else None,
}
json.dump(rec, open(out, "w"), indent=1)
print(json.dumps({k: v for k, v in rec.items() if k != "argv"}))
sys.exit(rc)
