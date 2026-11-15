"""Run one gemclean arm of issue #23 step 4 (research/multiscale-flux-fix.md).

    python run_gc.py GEMCLEAN FIELD_DIR OUT_ROOT ARM REPEAT

The argv is step 1-3's (research/multiscale-df5o-a1.md section 3) with the
field's own threshold and scales (its field.json), then the arm's one change
(section 3 of the note). Writes OUT_ROOT/ARM-rREPEAT/{run.json, gemclean.log,
ARM-*.fits}. Wall time and the peak working set (Windows) are recorded.
"""

# ruff: noqa: SIM905 (argv kept readable)
import ctypes
import hashlib
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path


def arms(field):
    thr = f"{field['noise']['threshold_3sigma_jy']:.6e}"
    scales = ",".join(str(s) for s in field["psf"]["multiscale_scales_px"])
    common = (
        "-size 1024 1024 -scale 2asec -weight natural -pol I -data-column DATA "
        "-wgridder-accuracy 1e-6 -channels-out 16 -join-channels -j 4 "
        "-no-update-model-required -nmiter 10 -niter 1000000 -gain 0.1 -mgain 0.8"
    ).split() + ["-threshold", thr]
    ms = ["-multiscale", "-multiscale-gain", "0.2"]
    listed = [*ms, "-multiscale-scales", scales]
    fwhm = repr(field["psf"]["fwhm_major_px"])
    return {
        "gc-hogbom": common,
        "gc-multiscale": common + listed,
        "gc-b065": common + listed + ["-multiscale-scale-bias", "0.65"],
        "gc-b070": common + listed + ["-multiscale-scale-bias", "0.7"],
        "gc-b075": common + listed + ["-multiscale-scale-bias", "0.75"],
        "gc-b080": common + listed + ["-multiscale-scale-bias", "0.8"],
        "gc-ref1": common + listed + ["-multiscale-bias-reference", "first-scale"],
        "gc-reff": common + listed + ["-multiscale-bias-reference", fwhm],
        "gc-cap": common + listed + ["-multiscale-point-cap", "0.9"],
        "gc-noneg": common + listed + ["-no-negative"],
        "gc-gauss": common + listed + ["-multiscale-shape", "gaussian"],
        "gc-s48": common + [*ms, "-multiscale-scales", "0,48,96,192"],
        "gc-sauto": common + ms,
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
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(
        int(handle), ctypes.byref(pmc), pmc.cb
    )
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
    spec = json.loads((Path(field) / "field.json").read_text())
    argv = [
        exe,
        *arms(spec)[arm],
        "-name",
        str(out / arm),
        str(Path(field) / "field.ms"),
    ]
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
        "started": time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - wall)
        ),
    }
    (out / "run.json").write_text(json.dumps(run, indent=1))
    print(json.dumps(run, indent=1))
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
