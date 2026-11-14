"""df5o.py g|w|u : the rml-gap arms on DF5-O's field (research/rml-gap.md, section 3, "DF5-O
field"; amendments A1, A2). Run each under the main checkout's tools/heavy_lock.py.

    df5o.py g    GeMClean natively (Windows), 8 threads, -wgridder-accuracy 1e-6
    df5o.py gd   the same at GeMClean's default accuracy (arm Gd, amendment A1; reported only)
    df5o.py w    WSClean 3.7 (WSL docker), 8 threads
    df5o.py u    pfb-imaging 0.0.11 sara (WSL docker): DF5-O's pfb-sara arm with --niter 40 and
                 8 threads, wall cap 6 h; stores on WSL ext4, FITS and logs copied to D:

Each writes $O/df5o/<arm>-r1/ in DF5-O's layout, so examples/compare_df5o.py measure scores it:
`ws-G`, `ws-Gd`, `ws-W` (the `ws-` prefix selects compare_df5o's WSClean file layout) and `pfb-sara-U-a`.
G and W image a copy of field.ms (GeMClean adds MODEL_DATA), removed after the run.
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[3] / "examples"))
import runs

O = runs.O / "df5o"
FIELD = O / "field"
CLEAN = [
    "-size", "1024", "1024", "-scale", "2asec", "-weight", "natural", "-data-column", "DATA",
    "-field", "0", "-channels-out", "16", "-join-channels", "-multiscale", "-auto-mask", "6",
    "-auto-threshold", "1", "-mgain", "0.8", "-gain", "0.1", "-nmiter", "1000",
    "-niter", "1000000", "-j", str(runs.THREADS), "-wgridder-accuracy", "1e-6",
]  # fmt: skip
W_ONLY = ["-gridder", "wgridder", "-no-min-grid-resolution", "-pol", "I",
          "-no-update-model-required"]  # fmt: skip
CAP_CYCLES, CAP_SECONDS = 40, 6 * 3600.0


def write_run(out, rec):
    (out / "run.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    runs.log_row(rec["arm"], "DF5-O", rec["returncode"], rec["docker_wall_s"], rec["what"])


def run_g(arm="ws-G"):
    out = O / f"{arm}-r1"
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(FIELD / "field.ms", out / "field.ms")
    binary = str(runs.O / "bin" / "gemclean-30d9412.exe")
    args = CLEAN if arm == "ws-G" else CLEAN[:-2]  # Gd: without -wgridder-accuracy 1e-6
    cmd = [binary, *args, "-name", str(out / arm), str(out / "field.ms")]
    t = time.time()
    with open(out / "wsclean.log", "w", encoding="utf-8") as log:
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        rc = p.wait()
        cpu = runs.process_cpu(p)
    wall = time.time() - t
    shutil.rmtree(out / "field.ms")
    what = "gemclean-30d9412.exe" + (" -wgridder-accuracy 1e-6" if arm == "ws-G" else "")
    write_run(out, {"arm": arm, "repeat": 1, "command": cmd, "returncode": rc,
                    "docker_wall_s": wall, "what": what,
                    "time_v": {"wall_s": wall, "user_s": cpu.get("user_s"),
                               "system_s": cpu.get("kernel_s")}})  # fmt: skip
    return rc


def run_w():
    from oracle_wsclean_clean import parse_time_v

    out = O / "ws-W-r1"
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(FIELD / "field.ms", out / "field.ms")
    image = "rang-wsclean-native:3.7"
    cmd = runs.docker_base(runs.THREADS, [(str(out), "/out", "rw")], image)
    cmd += [image, "/usr/bin/time", "-v", "wsclean", *W_ONLY, *CLEAN, "-name", "/out/ws-W",
            "/out/field.ms"]  # fmt: skip
    t = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.time() - t
    (out / "wsclean.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr,
                                     encoding="utf-8")  # fmt: skip
    shutil.rmtree(out / "field.ms")
    write_run(out, {"arm": "ws-W", "repeat": 1, "command": cmd, "returncode": proc.returncode,
                    "docker_wall_s": wall, "what": image,
                    "time_v": parse_time_v(proc.stderr)})  # fmt: skip
    return proc.returncode


def u_steps(field):
    import oracle_pfb

    steps = []
    for name, step in oracle_pfb.steps("pfb-sara", field):
        step = list(step)
        for i, a in enumerate(step[:-1]):
            if a == "--nthreads":
                step[i + 1] = str(runs.THREADS)
            if a == "--niter" and name == "sara":
                step[i + 1] = str(CAP_CYCLES)
        steps.append((name, step))
    return steps


def run_u():
    from oracle_wsclean_clean import parse_time_v

    field = json.loads((FIELD / "field.json").read_text(encoding="utf-8"))
    out = O / "pfb-sara-U-a-r1"
    out.mkdir(parents=True, exist_ok=False)
    work = runs.U_WORK / "df5o"
    work.mkdir(parents=True, exist_ok=False)
    image = "rang-pfb-imaging:0.0.11"
    env = [
        "-e", f"NUMBA_NUM_THREADS={runs.THREADS}", "-e", "OPENBLAS_NUM_THREADS=1",
        "-e", "NUMBA_CACHE_DIR=/out/numba-cache", "-e", "RAY_USAGE_STATS_ENABLED=0",
        "-e", "LD_LIBRARY_PATH=/opt/pfb/lib", "--shm-size", "8g",
    ]  # fmt: skip
    records, rc, t_start = [], 0, time.time()
    for name, step in u_steps(field):
        cname = f"rmlgap-df5o-{name}"
        mounts = [(str(FIELD), "/field", "ro"), (str(work), "/out", "rw")]
        cmd = runs.docker_base(runs.THREADS, mounts, image, "/out", cname)
        cmd += [*env, image, "/usr/bin/time", "-v", *step]
        t = time.time()
        with open(work / f"{name}.log", "w", encoding="utf-8") as log:
            p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.PIPE, text=True)
            try:
                _, err = p.communicate(timeout=max(1.0, CAP_SECONDS - (t - t_start)))
                stopped = False
            except subprocess.TimeoutExpired:
                subprocess.call(["docker", "kill", cname])
                _, err = p.communicate()
                stopped = True
        rc = 0 if stopped else p.returncode
        (work / f"time-{name}.txt").write_text(err, encoding="utf-8")
        records.append({"step": name, "command": step, "docker_command": cmd, "returncode": rc,
                        "start": t, "docker_wall_s": time.time() - t, "wall_cap_hit": stopped,
                        "time_v": parse_time_v(err)})  # fmt: skip
        if rc or stopped:
            break
    rec = {"arm": "pfb-sara-U-a", "repeat": 1, "image": image, "steps": records,
           "returncode": max(r["returncode"] for r in records),
           "docker_wall_s": sum(r["docker_wall_s"] for r in records), "start": t_start,
           "cap_cycles": CAP_CYCLES, "cap_seconds": CAP_SECONDS, "what": image}  # fmt: skip
    runs.copy_back(work, out, rec, t_start)
    runs.log_row(rec["arm"], "DF5-O", rec["returncode"], rec["docker_wall_s"], image)
    return rec["returncode"]


if __name__ == "__main__":
    mode = sys.argv[1]
    runs.check_space({"g": "g", "gd": "g", "w": "w", "u": "u"}[mode])
    rc = {"g": run_g, "gd": lambda: run_g("ws-Gd"), "w": run_w, "u": run_u}[mode]()
    print(f"df5o {mode} rc={rc}")
    sys.exit(rc)
