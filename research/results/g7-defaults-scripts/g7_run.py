"""g7_run.py: the timed runs of research/g7-defaults.md (section 5), driven from Windows.

    g7_run.py one ARM J REP     one run (call it under tools/heavy_lock.py): probe, run, probe
    g7_run.py plan NAME         every run of plan NAME in order, each under the heavy lock;
                                runs whose timing.json exists are skipped, so a restart resumes
    g7_run.py probe             print the load probe once

Arms: GD (default), GC (-single -wgridder-accuracy 1e-4), GB (-beam-band), GT (-tau-min 0.2),
GP (RANG_WGRIDDER_PLANE_GROUP=1), GX (the flags in $G7_GX), WN / WM (WSClean 3.7 nominres /
minres in Docker in WSL), LX (GeMClean built in WSL with the flags in $G7_LX). Native GeMClean
is $G7_BIN, the Linux one $G7_LBIN (a WSL path). Outputs under $G7_OUT
(default D:/rang/outputs/g7-20261109-01): runs/<ARM>-j<J>-r<REP>/, runs.tsv.
"""

import ctypes
import ctypes.wintypes as wt
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

OUT = Path(os.environ.get("G7_OUT", "D:/rang/outputs/g7-20261109-01"))
BIN = os.environ.get("G7_BIN", str(OUT / "bin" / "gemclean-g7.exe"))
LBIN = os.environ.get(
    "G7_LBIN", "/home/gijsm/Build/tmp/20261109-g7-target/gemclean/gemclean"
)
WSCTMP = "/home/gijsm/Build/tmp/20261109-g7-wsctmp"
MS_DIR = "D:/rang/outputs/20261103-gemclean-heldout/real"
MS_NAME = "cal.ms"
HERE = Path(__file__).resolve().parent
W = HERE.parents[2]
PY = str(W / ".venv" / "Scripts" / "python.exe")
STATUS = Path(r"C:\Users\gijsm\Github\rang\outputs\status\fp-g7.md")

COMMON = [
    "-size", "4096", "4096", "-scale", "3asec", "-weight", "briggs", "0.5",
    "-niter", "1000000", "-gain", "0.1", "-nmiter", "1000", "-abs-threshold", "0.003",
    "-data-column", "DATA", "-field", "0",
]  # fmt: skip

GEM = {
    "GD": [],
    "GC": ["-single", "-wgridder-accuracy", "1e-4"],
    "GB": ["-beam-band"],
    "GT": ["-tau-min", "0.2"],
    "GP": [],
}

# The plans of section 5: (arm, j, rep), arms interleaved, reversed on even repeats.
J16 = ["GD", "GC", "WN", "WM", "GB", "GT", "GP"]
PLANS = {
    "j16": [(a, 16, r) for r in (1, 2, 3) for a in (J16 if r % 2 else J16[::-1])],
    "j1": [(a, 1, 1) for a in J16] + [(a, 1, 2) for a in ("GC", "GD")],
    "j1-short": [(a, 1, 1) for a in J16],
    "gx": [("GX", 16, r) for r in (1, 2, 3)] + [("GX", 1, r) for r in (1, 2)],
    "lx": [("LX", 16, r) for r in (1, 2, 3)] + [("LX", 1, 1)],
}

PROBE_PS = (
    "Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object "
    '{ $_.PercentProcessorTime -gt 50 -and $_.Name -notmatch "^(_Total|Idle)$" } | '
    'ForEach-Object { "$($_.PercentProcessorTime) $($_.Name) $($_.IDProcess)" }'
)
PROBE_WSL = (
    "top -b -n 2 -d 1 -c -w 200 | awk '/^top - /{n++} n==2 && $1 ~ /^[0-9]+$/ && $9+0 > 50'; "
    "echo LOADAVG $(cat /proc/loadavg)"
)
IGNORE = ("wmiprvse", "vmmem", "powershell", "top -b", "loadavg", "idle")


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def probe():
    out = ["== Windows " + now()]
    try:
        r = subprocess.run(  # noqa: PLW1510
            ["powershell", "-NoProfile", "-Command", PROBE_PS],
            capture_output=True, text=True, timeout=60,
        )  # fmt: skip
        out += [ln for ln in r.stdout.splitlines() if ln.strip()]
    except Exception as e:  # noqa: BLE001
        out.append(f"(not available: {e})")
    out.append("== WSL")
    try:
        r = subprocess.run(  # noqa: PLW1510
            ["wsl", "-e", "bash", "-c", PROBE_WSL],
            capture_output=True,
            text=True,
            timeout=60,
        )
        out += [ln for ln in r.stdout.splitlines() if ln.strip()]
    except Exception as e:  # noqa: BLE001
        out.append(f"(not available: {e})")
    busy = [
        ln
        for ln in out
        if not ln.startswith("==")
        and not ln.startswith("LOADAVG")
        and not any(k in ln.lower() for k in IGNORE)
    ]
    return out, busy


class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def win_stats(handle):
    k32 = ctypes.windll.kernel32
    ft = [wt.FILETIME() for _ in range(4)]
    k32.GetProcessTimes(wt.HANDLE(handle), *[ctypes.byref(f) for f in ft])

    def secs(f):
        return ((f.dwHighDateTime << 32) | f.dwLowDateTime) / 1e7

    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    k32.K32GetProcessMemoryInfo(wt.HANDLE(handle), ctypes.byref(pmc), pmc.cb)
    return {
        "user_s": secs(ft[3]),
        "sys_s": secs(ft[2]),
        "peak_working_set_bytes": pmc.PeakWorkingSetSize,
        "peak_commit_bytes": pmc.PeakPagefileUsage,
    }


def time_v(path):
    keys = {
        "Elapsed (wall clock) time (h:mm:ss or m:ss)": "wall_s",
        "User time (seconds)": "user_s",
        "System time (seconds)": "sys_s",
        "Maximum resident set size (kbytes)": "max_rss_bytes",
    }
    got = {}
    for ln in Path(path).read_text().splitlines():
        k, _, v = ln.strip().rpartition(": ")
        if k in keys:
            if keys[k] == "wall_s":
                parts = [float(p) for p in v.split(":")]
                got["wall_s"] = sum(
                    p * 60 ** (len(parts) - 1 - i) for i, p in enumerate(parts)
                )
            elif keys[k] == "max_rss_bytes":
                got["max_rss_bytes"] = int(v) * 1024
            else:
                got[keys[k]] = float(v)
    return got


def wsl_path(p):
    p = str(p).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:] if p[1] == ":" else p


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def one(arm, j, rep):
    j, rep = int(j), int(rep)
    name = f"{arm}-j{j}-r{rep}"
    d = OUT / "runs" / name
    d.mkdir(parents=True, exist_ok=True)
    # Wait for a clean probe, up to 10 minutes.
    waited = 0
    for k in range(11):
        lines, busy = probe()
        if not busy or k == 10:
            break
        time.sleep(60)
        waited += 60
    (d / "load-before.txt").write_text("\n".join(lines) + "\n")
    spoiled = bool(busy)
    env = dict(os.environ)
    if arm in GEM or arm == "GX":
        flags = GEM.get(arm) if arm != "GX" else os.environ["G7_GX"].split()
        if arm == "GP":
            env["RANG_WGRIDDER_PLANE_GROUP"] = "1"
        cmd = [
            BIN,
            "-name",
            str(d / "g"),
            *COMMON,
            "-j",
            str(j),
            *flags,
            "-no-update-model-required",
            f"{MS_DIR}/{MS_NAME}",
        ]
        (d / "cmd.txt").write_text(
            " ".join(cmd)
            + ("\nRANG_WGRIDDER_PLANE_GROUP=1" if arm == "GP" else "")
            + "\n"
        )
        t = time.perf_counter()
        with open(d / "log.txt", "w") as log:
            p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
            rc = p.wait()
            wall = time.perf_counter() - t
            stats = win_stats(int(p._handle))
        stats["wall_s"] = wall
    elif arm in ("WN", "WM"):
        acc = (
            ["-no-min-grid-resolution", "-wgridder-accuracy", "1e-6"]
            if arm == "WN"
            else []
        )
        par = ["-parallel-reordering", "1"] if j == 1 else []
        dw = wsl_path(d)
        inner = [
            "docker", "run", "--rm", "--user", "$(id -u):$(id -g)", "--network", "none",
            "-e", "HOME=/tmp", "-e", f"OMP_NUM_THREADS={j}",
            "-v", f"{wsl_path(MS_DIR)}:/data:ro", "-v", f"{dw}:/run", "-v", f"{WSCTMP}:/run/tmp",
            "-w", "/run", "rang-wsclean-native:3.7", "/usr/bin/time", "-v", "-o", "/run/time.txt",
            "wsclean", "-gridder", "wgridder", *acc, "-pol", "I", "-no-update-model-required",
            "-temp-dir", "/run/tmp", *COMMON, "-mgain", "0.8", "-j", str(j), *par,
            "-name", "/run/w", f"/data/{MS_NAME}",
        ]  # fmt: skip
        script = (
            f"mkdir -p {WSCTMP} && rm -rf {WSCTMP}/* && "
            + " ".join(inner)
            + f"; rc=$?; rm -rf {WSCTMP}/*; exit $rc"
        )
        (d / "cmd.txt").write_text(script + "\n")
        t = time.perf_counter()
        with open(d / "log.txt", "w") as log:
            rc = subprocess.call(
                ["wsl", "-e", "bash", "-c", script],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        outer = time.perf_counter() - t
        stats = time_v(d / "time.txt") if (d / "time.txt").exists() else {}
        stats["outer_wall_s"] = outer
    elif arm == "LX":
        flags = os.environ.get("G7_LX", "").split()
        dw = wsl_path(d)
        args = [
            LBIN,
            "-name",
            f"{dw}/g",
            *COMMON,
            "-j",
            str(j),
            *flags,
            "-no-update-model-required",
            f"{wsl_path(MS_DIR)}/{MS_NAME}",
        ]
        script = f"/usr/bin/time -v -o {dw}/time.txt " + " ".join(args)
        (d / "cmd.txt").write_text(script + "\n")
        t = time.perf_counter()
        with open(d / "log.txt", "w") as log:
            rc = subprocess.call(
                ["wsl", "-e", "bash", "-c", script],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        outer = time.perf_counter() - t
        stats = time_v(d / "time.txt") if (d / "time.txt").exists() else {}
        stats["outer_wall_s"] = outer
    else:
        raise SystemExit(f"unknown arm {arm}")
    lines, busy_after = probe()
    (d / "load-after.txt").write_text("\n".join(lines) + "\n")
    hashes = {}
    for f in sorted(d.glob("*.fits")):
        hashes[f.name] = sha(f)
    rec = {
        "run": name, "arm": arm, "j": j, "rep": rep, "rc": rc, "spoiled": spoiled,
        "waited_s": waited, "busy_before": busy, "busy_after": busy_after, "end": now(), **stats,
        "sha256": hashes,
    }  # fmt: skip
    (d / "timing.json").write_text(json.dumps(rec, indent=1) + "\n")
    with open(OUT / "runs.tsv", "a") as f:
        f.write(
            f"{name}\t{rc}\t{int(spoiled)}\t{stats.get('wall_s', float('nan')):.1f}\t{now()}\n"
        )
    # FITS kept for repeat 1 only (scoring); later repeats keep their hashes.
    if rep > 1:
        for f in d.glob("*.fits"):
            f.unlink()
    print(
        f"{name} rc={rc} wall={stats.get('wall_s', float('nan')):.1f}s spoiled={spoiled}"
    )
    return rc


def status(line):
    try:
        old = STATUS.read_text(encoding="utf-8").splitlines() if STATUS.exists() else []
        head = [ln for ln in old if not ln.startswith("- ")][:2] or [
            "# fp-g7 G7 defaults"
        ]
        items = [ln for ln in old if ln.startswith("- ")]
        items = (items + [f"- {now()} {line}"])[-12:]
        STATUS.write_text("\n".join(head + items) + "\n", encoding="utf-8")
    except OSError:
        pass


def plan(name):
    log = OUT / f"plan-{name}.log"
    with open(log, "a") as f:
        f.write(f"START {now()} pid {os.getpid()} plan {name}\n")
    status(f"plan {name} START (log {log})")
    for arm, j, rep in PLANS[name]:
        run = f"{arm}-j{j}-r{rep}"
        if (OUT / "runs" / run / "timing.json").exists():
            continue
        t = time.time()
        rc = subprocess.call(
            [
                PY,
                str(W / "tools" / "heavy_lock.py"),
                "run",
                "--",
                PY,
                __file__,
                "one",
                arm,
                str(j),
                str(rep),
            ]
        )
        with open(log, "a") as f:
            f.write(f"RUN {run} rc={rc} wall={time.time() - t:.0f}s {now()}\n")
        status(f"plan {name} RUN {run} rc={rc} wall={time.time() - t:.0f}s")
        if rc != 0:
            status(f"plan {name} STOPPED at {run} rc={rc}")
            sys.exit(rc)
    with open(log, "a") as f:
        f.write(f"END {now()}\n")
    status(f"plan {name} END")


def main():
    mode = sys.argv[1]
    if mode == "one":
        sys.exit(one(*sys.argv[2:5]))
    elif mode == "plan":
        plan(sys.argv[2])
    elif mode == "probe":
        lines, busy = probe()
        print("\n".join(lines))
        print("BUSY:", busy)


if __name__ == "__main__":
    main()
