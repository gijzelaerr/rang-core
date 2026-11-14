"""runs.py: the arms of research/rml-gap.md, section 3. Run every command under
tools/heavy_lock.py (the main checkout's copy); this script takes no lock itself.

    runs.py g BIN SKY [ARM [OPTION ...]]
                                 GeMClean natively (Windows) into $O/runs/ARM/SKY/g-* (ARM
                                 defaults to G; the options are appended to BASE)
    runs.py w SKY                WSClean 3.7 (WSL docker) into $O/runs/W/SKY/w-*
    runs.py u CONFIG SKY [CAP_CYCLES CAP_SECONDS]
                                 pfb-imaging 0.0.11 init, grid, sara (WSL docker); stores on
                                 WSL ext4 ($U_WORK), FITS and logs copied to $O/runs/CONFIG/SKY

$O is D:/rang/outputs/rml-gap-20261113 (/mnt/d/... from WSL). Each run appends a row to
$O/runs.tsv: arm, sky, return code, wall seconds, what.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WSL = sys.platform != "win32"
D = "/mnt/d" if WSL else "D:"
O = Path(os.environ.get("RML_OUT", f"{D}/rang/outputs/rml-gap-20261113"))
U_WORK = Path(os.path.expanduser("~/Build/tmp/20261113-rml-gap"))
THREADS = 8

BENCH = f"{D}/rang/outputs/20261102-gemclean/bench/data"
HELD = f"{D}/rang/outputs/20261103-gemclean-heldout/sim/data"
SKIES = {
    "S1": f"{BENCH}/s1.ms",
    "S2": f"{BENCH}/s2.ms",
    "S3": f"{BENCH}/s3.ms",
    "H1": f"{HELD}/h1.ms",
    "H2": f"{HELD}/h2.ms",
    "H3": f"{HELD}/h3.ms",
    "H4": f"{HELD}/h4.ms",
    "M1": f"{D}/rang/outputs/g5-20261107-03/data/m1.ms",
    "N1": f"{O}/data/n1.ms",
    "N2": f"{O}/data/n2.ms",
}


def size(sky):
    return 4096 if sky == "H3" else 2048


BASE = [
    "-weight", "briggs", "0.5", "-niter", "1000000", "-gain", "0.1", "-mgain", "0.8",
    "-nmiter", "1000", "-data-column", "DATA", "-field", "0", "-j", str(THREADS),
    "-multiscale", "-auto-mask", "6", "-auto-threshold", "1",
]  # fmt: skip
W_EXTRA = [
    "-gridder", "wgridder", "-no-min-grid-resolution", "-wgridder-accuracy", "1e-6",
    "-pol", "I", "-no-update-model-required",
]  # fmt: skip

# Section 3: DF5-O's recipe and the tuning configurations.
RECIPE = {
    "bases": "self,db1,db2,db3", "nlevels": "2", "l1-reweight-from": "5", "alpha": "2",
    "rmsfactor": "1.0", "gamma": "0.99", "eta": "5e-4", "positivity": "1",
    "init-factor": "0.5", "pd-tol": "1.5e-4", "pd-maxit": "450", "tol": "5e-4",
}  # fmt: skip
CONFIGS = {
    "U-a": {},
    "U-b": {"nlevels": "4"},
    "U-c": {"rmsfactor": "0.5"},
    "U-d": {"nlevels": "4", "rmsfactor": "0.5"},
}


def log_row(arm, sky, rc, wall, what):
    with open(O / "runs.tsv", "a", encoding="utf-8") as f:
        f.write(f"{arm}\t{sky}\t{rc}\t{wall:.1f}\t{what}\n")


def sim_opts(sky):
    n = str(size(sky))
    return ["-size", n, n, "-scale", "1.5asec"]


def run_g(binary, sky, arm="G", extra=()):
    d = O / "runs" / arm / sky
    d.mkdir(parents=True, exist_ok=False)
    cmd = [binary, "-name", str(d / "g"), *BASE, *extra, *sim_opts(sky), SKIES[sky]]
    (d / "cmd.json").write_text(json.dumps(cmd), encoding="utf-8")
    t = time.time()
    with open(d / "log.txt", "w", encoding="utf-8") as log:
        rc = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT)
    wall = time.time() - t
    (d / "wall.json").write_text(json.dumps({"rc": rc, "wall_s": wall}), encoding="utf-8")
    log_row(arm, sky, rc, wall, " ".join([Path(binary).name, *extra]))
    return rc, wall


def docker_base(threads, mounts, image, workdir=None, name=None):
    uid = f"{os.getuid()}:{os.getgid()}"
    cmd = [
        "docker", "run", "--rm", "--user", uid, "--network", "none", "-e", "HOME=/tmp",
        "-e", f"OMP_NUM_THREADS={threads}",
    ]  # fmt: skip
    if name:
        cmd += ["--name", name]
    for src, dst, mode in mounts:
        cmd += ["-v", f"{src}:{dst}{':ro' if mode == 'ro' else ''}"]
    if workdir:
        cmd += ["-w", workdir]
    return cmd


def run_w(sky):
    d = O / "runs" / "W" / sky
    (d / "tmp").mkdir(parents=True, exist_ok=False)
    ms = SKIES[sky]
    data, name = os.path.dirname(ms), os.path.basename(ms)
    cmd = docker_base(THREADS, [(data, "/data", "ro"), (str(d), "/run", "rw")],
                      "rang-wsclean-native:3.7")  # fmt: skip
    cmd += [
        "rang-wsclean-native:3.7", "/usr/bin/time", "-v", "-o", "/run/time.txt",
        "wsclean", "-temp-dir", "/run/tmp", *W_EXTRA, *BASE, *sim_opts(sky),
        "-name", "/run/w", f"/data/{name}",
    ]  # fmt: skip
    (d / "cmd.json").write_text(json.dumps(cmd), encoding="utf-8")
    t = time.time()
    with open(d / "log.txt", "w", encoding="utf-8") as log:
        rc = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT)
    wall = time.time() - t
    try:
        (d / "tmp").rmdir()
    except OSError:
        pass
    (d / "wall.json").write_text(json.dumps({"rc": rc, "wall_s": wall}), encoding="utf-8")
    log_row("W", sky, rc, wall, "rang-wsclean-native:3.7")
    return rc, wall


def pfb_steps(config, sky, cap_cycles):
    n = str(size(sky))
    common = ["--nthreads", str(THREADS), "--backend", "native", "--log-directory", "/out/logs"]
    init = [
        "pfb", "init", "--ms", f"/data/{os.path.basename(SKIES[sky])}",
        "--output-filename", "/out/pfb", "--data-column", "DATA",
        "--weight-column", "WEIGHT_SPECTRUM", "--channels-per-image", "8",
        "--chan-average", "1", "--bda-decorr", "1.0", "--precision", "double",
        "--product", "I", "--integrations-per-image", "-1", "--no-progressbar",
        "--nworkers", "1", *common,
    ]  # fmt: skip
    grid = [
        "pfb", "grid", "--output-filename", "/out/pfb", "--nx", n, "--ny", n,
        "--cell-size", "1.5", "--robustness", "0.5", "--psf-oversize", "1.4",
        "--epsilon", "1e-6", "--do-wgridding", "--product", "I", "--nworkers", "1",
        *common,
    ]  # fmt: skip
    opts = {**RECIPE, **CONFIGS[config]}
    sara = ["pfb", "sara", "--output-filename", "/out/pfb", "--niter", str(cap_cycles),
            "--epsilon", "1e-6", "--do-wgridding", "--product", "I", *common]  # fmt: skip
    for k, v in opts.items():
        sara += [f"--{k}", v]
    return [("init", init), ("grid", grid), ("sara", sara)]


def run_u(config, sky, cap_cycles, cap_seconds):
    d = O / "runs" / config / sky
    d.mkdir(parents=True, exist_ok=False)
    work = U_WORK / config / sky
    work.mkdir(parents=True, exist_ok=False)
    data = os.path.dirname(SKIES[sky])
    env = [
        "-e", f"NUMBA_NUM_THREADS={THREADS}", "-e", "OPENBLAS_NUM_THREADS=1",
        "-e", "NUMBA_CACHE_DIR=/out/numba-cache", "-e", "RAY_USAGE_STATS_ENABLED=0",
        "-e", "LD_LIBRARY_PATH=/opt/pfb/lib", "--shm-size", "8g",
    ]  # fmt: skip
    records, rc = [], 0
    t_start = time.time()
    for name, step in pfb_steps(config, sky, cap_cycles):
        cname = f"rmlgap-{config}-{sky}-{name}"
        cmd = docker_base(THREADS, [(data, "/data", "ro"), (str(work), "/out", "rw")],
                          "rang-pfb-imaging:0.0.11", "/out", cname)  # fmt: skip
        cmd += [*env, "rang-pfb-imaging:0.0.11", "/usr/bin/time", "-v", "-o",
                f"/out/time-{name}.txt", *step]  # fmt: skip
        t = time.time()
        remaining = cap_seconds - (t - t_start)
        with open(work / f"{name}.log", "w", encoding="utf-8") as log:
            p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            try:
                rc = p.wait(timeout=max(1.0, remaining))
                stopped = False
            except subprocess.TimeoutExpired:
                # The wall cap: stop the container; the iterates written so far stay.
                subprocess.call(["docker", "kill", cname])
                p.wait()
                rc, stopped = 0, True
        records.append({"step": name, "command": step, "docker": cmd, "rc": rc,
                        "start": t, "wall_s": time.time() - t, "wall_cap_hit": stopped})  # fmt: skip
        if rc or stopped:
            break
    total = time.time() - t_start
    run = {"config": config, "sky": sky, "cap_cycles": cap_cycles,
           "cap_seconds": cap_seconds, "start": t_start, "steps": records,
           "rc": rc, "wall_s": total}  # fmt: skip
    copy_back(work, d, run, t_start)
    log_row(config, sky, rc, total, "rang-pfb-imaging:0.0.11")
    return rc, total


def copy_back(work, d, run, t_start):
    # Copy FITS, logs and timings to D:, recording each iterate's file time.
    iterates = {}
    for p in sorted(work.rglob("*")):
        if p.is_file() and (p.suffix in (".fits", ".log", ".txt") or p.name.endswith(".json")):
            rel = p.relative_to(work)
            if "numba-cache" in rel.parts or rel.parts[0].endswith((".xds", ".dds", ".mds")):
                continue
            dst = d / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            if p.suffix == ".fits":
                iterates[str(rel)] = p.stat().st_mtime - t_start
    run["file_seconds_since_start"] = iterates
    (d / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")


# Coordinator rule, 2026-11-14 (after D: filled): no job starts if it would leave D: with
# under 150 GB free. WSL's VHD lives on D:\wsl, so U's stores count too. Checked here, once
# the lock is held, with each mode's measured upper output size.
D_FLOOR_GB = 150
NEED_GB = {"g": 2, "w": 2, "u": 24}  # U: 5 GB at 2048², 20 GB at 4096²


def check_space(mode):
    free = shutil.disk_usage(f"{D}/").free / 1e9
    if free - NEED_GB[mode] < D_FLOOR_GB:
        raise SystemExit(f"D: has {free:.0f} GB free; {mode} needs {NEED_GB[mode]} GB "
                         f"and must leave {D_FLOOR_GB} GB: not starting")  # fmt: skip


def main():
    mode = sys.argv[1]
    check_space(mode)
    O.mkdir(parents=True, exist_ok=True)
    if mode == "g":
        arm = sys.argv[4] if len(sys.argv) > 4 else "G"
        rc, wall = run_g(sys.argv[2], sys.argv[3], arm, sys.argv[5:])
    elif mode == "w":
        rc, wall = run_w(sys.argv[2])
    elif mode == "u":
        config, sky = sys.argv[2], sys.argv[3]
        cap_c = int(sys.argv[4]) if len(sys.argv) > 4 else 40
        cap_s = float(sys.argv[5]) if len(sys.argv) > 5 else 4 * 3600.0
        rc, wall = run_u(config, sky, cap_c, cap_s)
    else:
        raise SystemExit(f"unknown mode {mode}")
    print(f"{mode} {sys.argv[2:]} rc={rc} wall={wall:.1f}s")
    sys.exit(rc)


if __name__ == "__main__":
    main()
