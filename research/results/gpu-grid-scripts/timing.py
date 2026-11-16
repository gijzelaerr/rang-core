"""Issue #12 timing (research/gpu-grid.md section 5), native Windows.

one OUT_JSON LOG -- CMD...   run CMD in a Job Object (wall, CPU, peak working set) while
                             sampling nvidia-smi memory.used at about 5 Hz; writes OUT_JSON.
                             Meant to run inside tools/heavy_lock.py (exclusive).
drive PLAN_TXT               for each line "NAME ARGS..." of PLAN_TXT without a result in
                             D:/rang/outputs/20261116-gpu-grid/timing/NAME.json: check the GPU's
                             free memory (GPU arms: budget + 256 MiB, else void and retried
                             later), queue an exclusive heavy_lock ticket, withdraw it after
                             10 min at the head of the queue and retry 10 min later.
The Job Object code is task G8's (g8-wheel-scripts/g8_run.py).
"""

import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path("D:/rang/outputs/20261116-gpu-grid/timing")
LOCK = Path("C:/Users/gijsm/Github/rang/tools/heavy_lock.py")
HERE = Path(__file__).resolve()


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




def gpu_mem():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip().split(",")
        return int(out[0]), int(out[1])
    except Exception:
        return None, None


def one(out_json, log, cmd):
    samples = []
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            used, _ = gpu_mem()
            if used is not None:
                samples.append(used)
            stop.wait(0.2)

    before, total = gpu_mem()
    th = threading.Thread(target=sample, daemon=True)
    th.start()
    rc, stats = run_in_job(cmd, log)
    stop.set()
    th.join()
    after, _ = gpu_mem()
    stats.update(
        rc=rc, cmd=cmd, gpu_used_before_mib=before, gpu_used_after_mib=after,
        gpu_total_mib=total, gpu_peak_mib=max(samples) if samples else None,
        gpu_samples=len(samples), finished=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    Path(out_json).write_text(json.dumps(stats, indent=1))
    return rc


def drive(plan):
    ROOT.mkdir(parents=True, exist_ok=True)
    lines = [ln.split() for ln in Path(plan).read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    pending = list(lines)
    while pending:
        progressed = False
        for item in list(pending):
            name, cmd = item[0], item[1:]
            res = ROOT / f"{name}.json"
            if res.exists():
                pending.remove(item)
                continue
            if "-gpu" in cmd:
                budget = int(cmd[cmd.index("-gpu-memory") + 1]) if "-gpu-memory" in cmd else 1024
                used, total = gpu_mem()
                if used is None or total - used < budget + 256:
                    with open(ROOT / "void.txt", "a") as f:
                        f.write(f"{time.strftime('%H:%M:%S')} {name} starved: {used} of {total} MiB used" + "\n")
                    print(f"{name}: GPU starved ({used}/{total} MiB), later", flush=True)
                    continue
            marker = ROOT / f"{name}.started"
            marker.unlink(missing_ok=True)
            p = subprocess.Popen(
                [sys.executable, str(LOCK), "run", "--", sys.executable, str(HERE), "one",
                 str(res), str(ROOT / f"{name}.log"), "--", *cmd],
                stderr=subprocess.PIPE, text=True,
            )
            head_since = None
            withdrawn = False
            buf = []
            def reader():
                for line in p.stderr:
                    buf.append(line)
            rt = threading.Thread(target=reader, daemon=True)
            rt.start()
            started = False
            while p.poll() is None:
                time.sleep(2)
                if (ROOT / f"{name}.log").exists():
                    started = True
                if started:
                    continue
                last = buf[-1] if buf else ""
                if "behind" in last or "waiting for head" in last:
                    head_since = None
                elif head_since is None:
                    head_since = time.time()
                elif time.time() - head_since > 600:
                    p.kill()
                    withdrawn = True
                    break
            p.wait()
            if withdrawn:
                print(f"{name}: withdrawn after 10 min at the head of the queue", flush=True)
                with open(ROOT / "withdrawn.txt", "a") as f:
                    f.write(f"{time.strftime('%H:%M:%S')} {name}" + "\n")
                time.sleep(600)
                continue
            if res.exists():
                r = json.loads(res.read_text())
                print(f"{name}: rc {r['rc']} wall {r['wall_s']:.2f} s peak WS {r['peak_working_set_bytes']/1e9:.2f} GB gpu peak {r['gpu_peak_mib']} MiB (before {r['gpu_used_before_mib']})", flush=True)
                pending.remove(item)
                progressed = True
        if pending and not progressed:
            time.sleep(300)


if __name__ == "__main__":
    if sys.argv[1] == "one":
        k = sys.argv.index("--")
        sys.exit(one(sys.argv[2], sys.argv[3], sys.argv[k + 1:]))
    drive(sys.argv[2])
