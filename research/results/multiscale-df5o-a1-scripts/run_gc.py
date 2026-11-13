"""Run one gemclean arm on DF5-O's field (issue #23).

    python run_gc.py GEMCLEAN FIELD_DIR OUT_ROOT ARM REPEAT

Arms are DF5-O's WSClean argv (research/df5o-deconv-oracles.md 2.1) without
`-gridder wgridder`, `-no-min-grid-resolution` and `-no-reorder`, which gemclean
does not take (research/multiscale-df5o-a1.md section 3). Writes
OUT_ROOT/ARM-rREPEAT/{run.json, gemclean.log, ARM-*.fits}. Wall time and the
peak working set (Windows) of the gemclean process are recorded.
"""

import ctypes
import hashlib
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

COMMON = (
    "-size 1024 1024 -scale 2asec -weight natural -pol I -data-column DATA "
    "-wgridder-accuracy 1e-6 -channels-out 16 -join-channels -j 4 "
    "-no-update-model-required -nmiter 10 -niter 1000000 -gain 0.1 -mgain 0.8 "
    "-threshold 4.263913e-06"
).split()
MS = "-multiscale -multiscale-scales 0,24,48,96,192 -multiscale-gain 0.2".split()
ARMS = {
    "gc-hogbom": COMMON,
    "gc-multiscale": COMMON + MS,
    # section 5 variants, one change each from gc-multiscale
    "gc-ms-v1": COMMON + "-multiscale -multiscale-scales 0,24,48,96 -multiscale-gain 0.2".split(),
    "gc-ms-v2": COMMON + "-multiscale -multiscale-scales 0,24,48 -multiscale-gain 0.2".split(),
    "gc-ms-v3": COMMON + MS + ["-multiscale-scale-bias", "0.8"],
    "gc-ms-v4": COMMON + "-multiscale -multiscale-scales 0,24,48,96,192 -multiscale-gain 0.1".split(),
}


class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_working_set(handle):
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(int(handle), ctypes.byref(pmc), pmc.cb)
    return pmc.PeakWorkingSetSize if ok else None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def main():
    exe, field, root, arm, repeat = sys.argv[1:6]
    out = Path(root) / f"{arm}-r{repeat}"
    out.mkdir(parents=True, exist_ok=False)
    argv = [exe, *ARMS[arm], "-name", str(out / arm), str(Path(field) / "field.ms")]
    t0 = time.perf_counter()
    with open(out / "gemclean.log", "w") as log:
        p = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
        while p.poll() is None:
            peak = peak_working_set(p._handle)
            time.sleep(0.5)
        peak = peak_working_set(p._handle) or peak
    wall = time.perf_counter() - t0
    run = {
        "arm": arm,
        "repeat": int(repeat),
        "argv": argv,
        "binary_sha256": sha256_file(exe),
        "returncode": p.returncode,
        "wall_s": wall,
        "peak_rss_mb": None if peak is None else peak / 2**20,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - wall)),
    }
    (out / "run.json").write_text(json.dumps(run, indent=1))
    print(json.dumps(run, indent=1))
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
