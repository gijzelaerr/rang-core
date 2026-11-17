# SPDX-License-Identifier: MIT
"""Issue #12, amendment 9.4 of research/gpu-grid.md: the whole timing session in one
exclusive heavy_lock hold, native Windows.

    python heavy_lock.py run --drain 0 -- python session.py

Runs the warm-up, then per repeat the twelve GeMClean arms of timing_plan.txt (rewritten to
ROOT) and that repeat's six WSClean arms (wsclean_run.sh through `wsl -d Ubuntu`), then the
pilot's CPU and GPU coarse runs, then the void GPU arms once more. Per run: wall, own CPU,
other-process CPU (GetSystemTimes), nvidia-smi before and after; written to ROOT/NAME.json
by timing.py's `one` (GeMClean) or here (WSClean). Takes no lock itself.
"""

import ctypes
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import timing  # noqa: E402

OUT = Path("D:/rang/outputs/20261116-gpu-grid")
ROOT = OUT / "timing-20261117"
WSC = OUT / "wsclean"
LOCK = Path("C:/Users/gijsm/Github/rang/tools/heavy_lock.py")
BIN = Path("C:/Users/gijsm/Worktrees/rang/gpu-grid/outputs/gpu-grid/bin")
WSL_RUN = "/mnt/c/Users/gijsm/Worktrees/rang/gpu-grid/research/results/gpu-grid-scripts/wsclean_run.sh"
MS = {
    "s1": "D:/rang/outputs/20261102-gemclean/bench/data/s1.ms",
    "h2": "D:/rang/outputs/20261103-gemclean-heldout/sim/data/h2.ms",
    "h3": "D:/rang/outputs/20261103-gemclean-heldout/sim/data/h3.ms",
    "pilot": "D:/rang/outputs/20261103-gemclean-heldout/real/cal.ms",
}
COMMON = ("-weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -data-column DATA "
          "-field 0 -j 16 -no-update-model-required -single -wgridder-accuracy 1e-4").split()
OTHER_MAX, GPU_DRIFT_MIB = 1.0, 512


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(ROOT / "session.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def busy_s():
    """Host busy CPU seconds over all logical processors."""
    idle, kern, user = (ctypes.c_uint64() for _ in range(3))
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
    return (kern.value - idle.value + user.value) / 1e7


def snapshot(tag):
    smi = subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout
    (ROOT / f"nvidia-smi-{tag}.txt").write_text(smi)
    lock = subprocess.run([sys.executable, str(LOCK), "status"], capture_output=True, text=True)
    (ROOT / f"lock-{tag}.txt").write_text(lock.stdout + lock.stderr)
    t0, b0 = time.perf_counter(), busy_s()
    time.sleep(10)
    cores = (busy_s() - b0) / (time.perf_counter() - t0)
    used, total = timing.gpu_mem()
    log(f"snapshot {tag}: host busy {cores:.2f} cores over 10 s (idle driver), GPU {used}/{total} MiB")
    return used


def mark(name, res, own_cpu_s, wall_s, other_wall_s, b0, b1, gpu_before, base_gpu):
    other = (b1 - b0 - own_cpu_s) / other_wall_s
    reasons = []
    if other > OTHER_MAX:
        reasons.append(f"other CPU {other:.2f} cores")
    if gpu_before is not None and gpu_before - base_gpu > GPU_DRIFT_MIB:
        reasons.append(f"GPU {gpu_before} MiB in use before (start {base_gpu})")
    res.update(other_cores=other, clean=not reasons, unclean=reasons)
    log(f"{name}: wall {wall_s:.2f} s, other {other:.2f} cores, {'clean' if not reasons else 'UNCLEAN ' + '; '.join(reasons)}")


def gemclean(name, cmd, base_gpu, voids):
    res_path = ROOT / f"{name}.json"
    if "-gpu" in cmd:
        budget = int(cmd[cmd.index("-gpu-memory") + 1])
        used, total = timing.gpu_mem()
        if used is None or total - used < budget + 256:
            log(f"{name}: VOID, GPU {used}/{total} MiB used")
            voids.append((name, cmd))
            return
    t0, b0 = time.perf_counter(), busy_s()
    timing.one(str(res_path), str(ROOT / f"{name}.log"), cmd)
    b1, span = busy_s(), time.perf_counter() - t0
    r = json.loads(res_path.read_text())
    mark(name, r, r["user_s"] + r["sys_s"], r["wall_s"], span, b0, b1, r["gpu_used_before_mib"], base_gpu)
    res_path.write_text(json.dumps(r, indent=1))


def wsclean(sky, mg, rep, base_gpu):
    name = f"{sky}-minres-mgain{mg}-r{rep}"
    before, _ = timing.gpu_mem()
    t0, b0 = time.perf_counter(), busy_s()
    p = subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", WSL_RUN, sky, mg, str(rep)],
                       capture_output=True, text=True)
    b1, span = busy_s(), time.perf_counter() - t0
    try:
        t = (WSC / f"{name}.txt").read_text()
    except OSError:
        log(f"{name}: FAILED, no GNU time file; wsl rc {p.returncode}: {p.stdout[-300:]} {p.stderr[-300:]}")
        return
    wall = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", t).group(1).split(":")
    wall_s = sum(float(x) * 60 ** i for i, x in enumerate(reversed(wall)))
    user = float(re.search(r"User time \(seconds\): ([\d.]+)", t).group(1))
    sys_ = float(re.search(r"System time \(seconds\): ([\d.]+)", t).group(1))
    rss = int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", t).group(1))
    status = int(re.search(r"Exit status: (\d+)", t).group(1))
    r = dict(name=name, wall_s=wall_s, span_s=span, user_s=user, sys_s=sys_, peak_rss_gb=rss * 1024 / 1e9,
             rc=status, wsl_rc=p.returncode, stdout=p.stdout[-500:], gpu_used_before_mib=before,
             finished=time.strftime("%Y-%m-%dT%H:%M:%S"))
    # Other CPU over the wsl.exe span: Docker start and the VM count as other.
    mark(name, r, user + sys_, wall_s, span, b0, b1, before, base_gpu)
    (ROOT / f"{name}.json").write_text(json.dumps(r, indent=1))


def warm_up():
    t = time.perf_counter()
    n = 0
    for ms in MS.values():
        for f in Path(ms).rglob("*"):
            if f.is_file():
                with open(f, "rb") as fh:
                    while chunk := fh.read(1 << 24):
                        n += len(chunk)
    log(f"warm-up: read {n / 1e9:.1f} GB of MS in {time.perf_counter() - t:.0f} s")
    p = subprocess.run(["wsl", "-d", "Ubuntu", "--", "docker", "run", "--rm", "--network", "none",
                        "rang-wsclean-native:3.7", "true"], capture_output=True, text=True)
    log(f"warm-up: docker true rc {p.returncode}")
    cmd = [str(BIN / "gemclean-9ad7e75-gpu.exe"), "-name", str(ROOT / "warm" / "s1-coarse-gpu"),
           "-size", "2048", "2048", "-scale", "1.5asec", "-abs-threshold", "0.0001", *COMMON,
           "-gpu", "-gpu-memory", "4096", MS["s1"]]
    (ROOT / "warm").mkdir(exist_ok=True)
    rc = timing.one(str(ROOT / "warm" / "s1-coarse-gpu.json"), str(ROOT / "warm" / "s1-coarse-gpu.log"), cmd)
    log(f"warm-up: S1 coarse GPU rc {rc}")


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "out").mkdir(exist_ok=True)
    plan = [ln.replace("/timing/out/", "/timing-20261117/out/").split()
            for ln in (HERE / "timing_plan.txt").read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]
    log(f"session start, {len(plan)} GeMClean arms")
    base_gpu = snapshot("start")
    warm_up()
    voids = []
    for rep in (1, 2, 3):
        for item in plan:
            if item[0].endswith(f"-r{rep}"):
                gemclean(item[0], item[1:], base_gpu, voids)
        for sky in ("s1", "h2", "h3"):
            for mg in ("0.8", "0.9"):
                wsclean(sky, mg, rep, base_gpu)
    for arm, extra in (("cpu", []), ("gpu", ["-gpu", "-gpu-memory", "4096"])):
        name = f"pilot-coarse-{arm}-r1"
        cmd = [str(BIN / f"gemclean-9ad7e75-{arm}.exe"), "-name", str(ROOT / "out" / name),
               "-size", "4096", "4096", "-scale", "3asec", "-abs-threshold", "0.003", *COMMON,
               *extra, MS["pilot"]]
        gemclean(name, cmd, base_gpu, voids)
    retry, voids = voids, []
    for name, cmd in retry:
        gemclean(name, cmd, base_gpu, voids)
    for name, _ in voids:
        log(f"{name}: void twice, not measured")
    snapshot("end")
    log("session end")


if __name__ == "__main__":
    main()
