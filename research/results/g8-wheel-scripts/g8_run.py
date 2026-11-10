"""g8_run.py: the timed and identity runs of research/g8-wheel.md (sections 3 and 4), from Windows.

    g8_run.py one ARM J REP        one timed run on the pilot-512 (call it under tools/heavy_lock.py)
    g8_run.py plan NAME            every run of plan NAME, each under the heavy lock; runs whose
                                   timing.json exists are skipped, so a restart resumes
    g8_run.py ident ARM CASE       one identity run (call it under the heavy lock): FITS sha256s
    g8_run.py startup ARM N        N runs of `-version`, wall each
    g8_run.py probe                the load probe once

Arms (section 2): SB (source build), WH (the CI wheel), WV3, WF (diagnostic and candidate wheels)
run natively, each started suspended inside a Job Object (CPU and peak memory of the whole tree:
a console script's trampoline starts python.exe); SBL, WHL in WSL under GNU time -v. Commands
come from $G8_OUT/arms.json ({"SB": [exe], "WH": [venv/Scripts/gemclean.exe], "SBL": [wsl path],
...}). Outputs under $G8_OUT (default D:/rang/outputs/g8-20261110-01).
"""

import ctypes
import ctypes.wintypes as wt
import datetime
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

OUT = Path(os.environ.get("G8_OUT", "D:/rang/outputs/g8-20261110-01"))
MS = "D:/rang/outputs/20261103-gemclean-heldout/real/cal.ms"
HERE = Path(__file__).resolve().parent
W = HERE.parents[2]
PY = str(W / ".venv" / "Scripts" / "python.exe")
STATUS = Path(r"C:\Users\gijsm\Github\rang\outputs\status\fp-g8.md")
LINUX = ("SBL", "WHL")

# G2's settings, G7's new defaults (no precision flags).
COMMON = [
    "-size", "4096", "4096", "-scale", "3asec", "-weight", "briggs", "0.5",
    "-niter", "1000000", "-gain", "0.1", "-nmiter", "1000", "-abs-threshold", "0.003",
    "-data-column", "DATA", "-field", "0", "-no-update-model-required",
]  # fmt: skip

B = "D:/rang/outputs/20261102-gemclean/bench/data"
G3 = "D:/rang/outputs/20261106-g3-spectral/data"
IDENT = [
    "-size", "2048", "2048", "-scale", "1.5asec", "-weight", "briggs", "0.5",
    "-niter", "1000000", "-gain", "0.1", "-nmiter", "1000",
    "-data-column", "DATA", "-field", "0", "-j", "16", "-no-update-model-required",
]  # fmt: skip
CASES = {
    "s1-def": (["-abs-threshold", "0.0001"], f"{B}/s1.ms"),
    "s1-d6": (["-abs-threshold", "0.0001", "-wgridder-accuracy", "1e-6"], f"{B}/s1.ms"),
    "d1c1-def": (
        ["-abs-threshold", "0.00015", "-channels-out", "8", "-join-channels",
         "-fit-spectral-pol", "4"],
        f"{G3}/D1.ms",
    ),
}  # fmt: skip

ORDER = ["SB", "WH", "WV3", "WF"]
PLANS = {
    "j16": [(a, 16, r) for r in (1, 2, 3) for a in (ORDER if r % 2 else ORDER[::-1])],
    "j1": [(a, 1, 1) for a in ORDER] + [("WH", 1, 2), ("SB", 1, 2)],
    "lx16": [(a, 16, r) for r in (1, 2, 3) for a in (LINUX if r % 2 else LINUX[::-1])],
    "lx1": [(a, 1, 1) for a in LINUX],
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


def arms():
    return json.loads((OUT / "arms.json").read_text())


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
            capture_output=True, text=True, timeout=60,
        )  # fmt: skip
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


# -- Job Object accounting (Windows) -------------------------------------------------


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


class BasicAccounting(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_int64),
        ("TotalKernelTime", ctypes.c_int64),
        ("ThisPeriodTotalUserTime", ctypes.c_int64),
        ("ThisPeriodTotalKernelTime", ctypes.c_int64),
        ("TotalPageFaultCount", wt.DWORD),
        ("TotalProcesses", wt.DWORD),
        ("ActiveProcesses", wt.DWORD),
        ("TotalTerminatedProcesses", wt.DWORD),
    ]


class BasicLimit(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wt.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wt.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wt.DWORD),
        ("SchedulingClass", wt.DWORD),
    ]


class ExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BasicLimit),
        ("IoInfo", ctypes.c_uint64 * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def run_in_job(cmd, log_path, env=None):
    """Run `cmd` started suspended inside a new Job Object; returns (rc, stats)."""
    k32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll
    k32.CreateJobObjectW.restype = wt.HANDLE
    k32.OpenProcess.restype = wt.HANDLE
    job = k32.CreateJobObjectW(None, None)
    handles = {}
    stop = threading.Event()

    def watch():
        class Pids(ctypes.Structure):
            _fields_ = [
                ("Assigned", wt.DWORD),
                ("InList", wt.DWORD),
                ("Ids", ctypes.c_size_t * 64),
            ]

        while not stop.is_set():
            ids = Pids()
            if k32.QueryInformationJobObject(
                wt.HANDLE(job), 3, ctypes.byref(ids), ctypes.sizeof(ids), None
            ):
                for i in range(ids.InList):
                    pid = ids.Ids[i]
                    if pid not in handles:
                        h = k32.OpenProcess(0x0400 | 0x0010 | 0x00100000, False, pid)
                        if h:
                            handles[pid] = h
            stop.wait(0.25)

    t = time.perf_counter()
    with open(log_path, "w") as log:
        p = subprocess.Popen(
            cmd, stdout=log, stderr=subprocess.STDOUT, env=env, creationflags=0x4
        )
        k32.AssignProcessToJobObject(wt.HANDLE(job), wt.HANDLE(int(p._handle)))
        ntdll.NtResumeProcess(wt.HANDLE(int(p._handle)))
        th = threading.Thread(target=watch, daemon=True)
        th.start()
        rc = p.wait()
        wall = time.perf_counter() - t
    stop.set()
    th.join()
    acc = BasicAccounting()
    k32.QueryInformationJobObject(
        wt.HANDLE(job), 1, ctypes.byref(acc), ctypes.sizeof(acc), None
    )
    ext = ExtendedLimit()
    k32.QueryInformationJobObject(
        wt.HANDLE(job), 9, ctypes.byref(ext), ctypes.sizeof(ext), None
    )
    peak_ws = 0
    for h in handles.values():
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        if k32.K32GetProcessMemoryInfo(wt.HANDLE(h), ctypes.byref(pmc), pmc.cb):
            peak_ws = max(peak_ws, pmc.PeakWorkingSetSize)
        k32.CloseHandle(wt.HANDLE(h))
    k32.CloseHandle(wt.HANDLE(job))
    return rc, {
        "wall_s": wall,
        "user_s": acc.TotalUserTime / 1e7,
        "sys_s": acc.TotalKernelTime / 1e7,
        "processes": acc.TotalProcesses,
        "processes_seen": len(handles),
        "peak_working_set_bytes": peak_ws,
        "peak_job_commit_bytes": ext.PeakJobMemoryUsed,
        "peak_process_commit_bytes": ext.PeakProcessMemoryUsed,
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


def launch(arm, d, args):
    """Run `arm` with `args` (`-name` prefix d/g first) in directory d."""
    prefix = arms()[arm]
    if arm in LINUX:
        a = [wsl_path(x) if ":" in x else x for x in args]
        script = f"/usr/bin/time -v -o {wsl_path(d)}/time.txt " + " ".join(
            [*prefix, *a]
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
        return rc, stats
    cmd = [*prefix, *args]
    (d / "cmd.txt").write_text(" ".join(cmd) + "\n")
    return run_in_job(cmd, d / "log.txt")


def one(arm, j, rep):
    j, rep = int(j), int(rep)
    name = f"{arm}-j{j}-r{rep}"
    d = OUT / "runs" / name
    d.mkdir(parents=True, exist_ok=True)
    waited = 0
    for k in range(11):
        lines, busy = probe()
        if not busy or k == 10:
            break
        time.sleep(60)
        waited += 60
    (d / "load-before.txt").write_text("\n".join(lines) + "\n")
    spoiled = bool(busy)
    rc, stats = launch(arm, d, ["-name", str(d / "g"), *COMMON, "-j", str(j), MS])
    lines, busy_after = probe()
    (d / "load-after.txt").write_text("\n".join(lines) + "\n")
    hashes = {f.name: sha(f) for f in sorted(d.glob("*.fits"))}
    rec = {
        "run": name, "arm": arm, "j": j, "rep": rep, "rc": rc, "spoiled": spoiled,
        "waited_s": waited, "busy_before": busy, "busy_after": busy_after, "end": now(),
        **stats, "sha256": hashes,
    }  # fmt: skip
    (d / "timing.json").write_text(json.dumps(rec, indent=1) + "\n")
    with open(OUT / "runs.tsv", "a") as f:
        f.write(
            f"{name}\t{rc}\t{int(spoiled)}\t{stats.get('wall_s', float('nan')):.1f}\t{now()}\n"
        )
    for f in d.glob("*.fits"):
        f.unlink()
    print(
        f"{name} rc={rc} wall={stats.get('wall_s', float('nan')):.1f}s spoiled={spoiled}"
    )
    return rc


def ident(arm, case):
    flags, ms = CASES[case]
    d = OUT / "identity" / arm / case
    d.mkdir(parents=True, exist_ok=True)
    rc, stats = launch(arm, d, ["-name", str(d / "g"), *IDENT, *flags, ms])
    hashes = {f.name: sha(f) for f in sorted(d.glob("*.fits"))}
    (d / "result.json").write_text(
        json.dumps(
            {"arm": arm, "case": case, "rc": rc, **stats, "sha256": hashes}, indent=1
        )
        + "\n"
    )
    for f in d.glob("*.fits"):
        f.unlink()
    print(
        f"ident {arm} {case} rc={rc} files={len(hashes)} wall={stats.get('wall_s', 0):.1f}s"
    )
    return rc


def startup(arm, n):
    d = OUT / "startup" / arm
    d.mkdir(parents=True, exist_ok=True)
    walls = []
    for i in range(int(n)):
        rc, stats = launch(arm, d, ["-version"])
        walls.append(stats.get("wall_s"))
        assert rc == 0, (arm, rc)
    (d / "walls.json").write_text(json.dumps(walls) + "\n")
    print(arm, "median", sorted(walls)[len(walls) // 2], walls)


def status(line):
    try:
        old = STATUS.read_text(encoding="utf-8").splitlines() if STATUS.exists() else []
        head = [ln for ln in old if not ln.startswith("- ")][:2] or ["# fp-g8"]
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
            [PY, str(W / "tools" / "heavy_lock.py"), "run", "--", PY, __file__, "one",
             arm, str(j), str(rep)]
        )  # fmt: skip
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
    elif mode == "ident":
        sys.exit(ident(*sys.argv[2:4]))
    elif mode == "startup":
        startup(*sys.argv[2:4])
    elif mode == "plan":
        plan(sys.argv[2])
    elif mode == "probe":
        lines, busy = probe()
        print("\n".join(lines))
        print("BUSY:", busy)


if __name__ == "__main__":
    main()
