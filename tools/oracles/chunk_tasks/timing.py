# SPDX-License-Identifier: GPL-3.0-or-later
"""The timing runs of research/chunk-task-api.md section 5, on the shared
host nash (amendment 2, section 5.1).

    python timing.py point RUN CONFIG REPEAT  # one point: copy, 3 stages, hashes
    python timing.py matrix RUN               # 5 configs x 3 repeats, rotating
    python timing.py report RUN               # medians, S(N), S(N)/N, spawn, identity

CONFIG is B (main 30d9412 at RAYON_NUM_THREADS=16) or N1, N2, N4, N8 (the
pinned branch commit abdfb5a with `processes: N, threads: 16`); every config
has `memory_limit_gb: 32` and RAYON_NUM_THREADS=16. `matrix` runs each point
under its own exclusive hold (`heavy_lock.py run -- ...`). Paths come from the
environment:

    RANG_CTA_W         the case W MS (w3.ms), read only
    RANG_CTA_STRATEGY  CARACal's first-pass strategy YAML
    RANG_CTA_CODE      the pinned branch worktree (abdfb5a)
    RANG_CTA_ORACLE    main 30d9412's worktree, whose python/rang holds the
                       same _core build as RANG_CTA_CODE
    RANG_CTA_PYTHON    the interpreter (RANG_CTA_CODE's venv)
    RANG_HEAVY_LOCK_PY the main checkout's tools/heavy_lock.py

Each stage is one reading of tools/oracles/nash/timed.py (wall, CPU, peak
RSS, foreign load). A point with a void reading is moved aside and run again,
at most MAX_ATTEMPTS times in all. After each stage, the columns and flag
versions are hashed as in run.py (outside the timed reading).
"""

import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "nash"))

import run as harness
import timed

CONFIGS = ("B", "N1", "N2", "N4", "N8")
REPEATS = 3
MAX_ATTEMPTS = 3
STAGES = ("flag", "calibrate", "apply")
THREADS = 16
MAX_FOREIGN = 2.0


def _data_lines(config):
    lines = ["memory_limit_gb: 32"]
    if config != "B":
        lines = [f"processes: {int(config[1:])}", f"threads: {THREADS}"] + lines
    return lines


def config_text(config, ms):
    harness.STRATEGY = Path(os.environ["RANG_CTA_STRATEGY"])
    harness.ARMS["_timing"] = _data_lines(config)
    return harness.config_text("W", "_timing", ms)


def order(repeat):
    k = repeat % len(CONFIGS)
    return CONFIGS[k:] + CONFIGS[:k]


def point(run, config, repeat):
    run = Path(run)
    d = run / f"W-{config}-r{repeat}"
    if (d / "done.json").is_file():
        print(f"{d.name}: done already")
        return 0
    attempts = sorted(run.glob(f"W-{config}-r{repeat}.void-*"))
    if len(attempts) >= MAX_ATTEMPTS:
        print(f"{d.name}: not obtained ({len(attempts)} void attempts)")
        return 0
    if d.exists():  # an interrupted attempt: kept, never deleted
        d.rename(d.with_name(f"{d.name}.void-{int(time.time())}-interrupted"))
    d.mkdir(parents=True)
    ms = d / "work.ms"
    shutil.copytree(os.environ["RANG_CTA_W"], ms)
    (d / "config.yaml").write_text(config_text(config, ms), encoding="utf-8")
    code = Path(os.environ["RANG_CTA_ORACLE" if config == "B" else "RANG_CTA_CODE"])
    tasklog = d / "tasks.log"
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([str(HERE / "spawnlog"), str(code / "python")]),
        RAYON_NUM_THREADS=str(THREADS),
        RANG_CTA_TASKLOG=str(tasklog),
    )
    py = os.environ["RANG_CTA_PYTHON"]
    record = {"config": config, "repeat": repeat, "code": str(code),
              "data": _data_lines(config), "stages": {}}  # fmt: skip
    void = False
    for stage in STAGES:
        harness_cmd = [py, "-m", "rang.core_cli", stage, "config.yaml", "work.ms"]
        rec = timed.measure(harness_cmd, env, str(d), str(d / f"{stage}.log"),
                            MAX_FOREIGN, 7200)  # fmt: skip
        if tasklog.is_file():
            lines = [ln.split() for ln in tasklog.read_text().splitlines()]
            here = [ln for ln in lines if ln[2] == stage]
            if here:
                rec["first_task"] = {"pid": int(here[0][0]), "unix": float(here[0][1]),
                                     "kind": here[0][3], "processes_seen": len(here)}  # fmt: skip
        record["stages"][stage] = rec
        print(f"{d.name} {stage}: exit {rec['exit']}, {rec['wall_s']} s, "
              f"foreign {rec['foreign_cores']}", flush=True)  # fmt: skip
        void |= rec["void"]
        if rec["exit"]:
            break
        (d / f"hashes-{stage}.json").write_text(
            json.dumps(harness.hashes(ms), indent=1) + "\n", encoding="utf-8"
        )
    shutil.rmtree(ms)
    fv = d / "work.ms.flagversions"
    if fv.exists():
        shutil.rmtree(fv)
    (d / "point.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    if void:
        d.rename(d.with_name(f"{d.name}.void-{int(time.time())}"))
        print(f"{d.name}: void (foreign load), to be repeated")
        return 3
    (d / "done.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return 0


def lock_idle(lock):
    """True when the lock has no shared hold, no exclusive hold and no queue
    (the coordinator's rule of 2026-11-17: an exclusive point is queued only
    then, so that it never drains the lock while shared work waits)."""
    text = subprocess.run([sys.executable, lock, "status"], capture_output=True,
                          text=True, check=False).stdout  # fmt: skip
    lines = text.splitlines()
    return (
        any(ln.startswith("exclusive: free") for ln in lines)
        and any(ln.startswith("shared: 0/") for ln in lines)
        and not any(ln.startswith("queue ") for ln in lines)
    )


def matrix(run):
    run = Path(run)
    run.mkdir(parents=True, exist_ok=True)
    lock = os.environ["RANG_HEAVY_LOCK_PY"]
    for repeat in range(REPEATS):
        for config in order(repeat):
            if (run / f"W-{config}-r{repeat}" / "done.json").is_file():
                continue
            for _ in range(MAX_ATTEMPTS):
                while not lock_idle(lock):
                    time.sleep(60)
                proc = subprocess.run(
                    [sys.executable, lock, "run", "--",
                     sys.executable, str(HERE / "timing.py"), "point", str(run),
                     config, str(repeat)],
                    check=False,
                )  # fmt: skip
                if proc.returncode != 3:
                    break
            with open(run / "status.txt", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M')} W-{config}-r{repeat} "
                        f"exit {proc.returncode}\n")  # fmt: skip


def _identity(base, d):
    diffs = []
    for stage in STAGES:
        hb = json.loads((base / f"hashes-{stage}.json").read_text())
        ha = json.loads((d / f"hashes-{stage}.json").read_text())
        for col in sorted(set(hb["columns"]) | set(ha["columns"])):
            if hb["columns"].get(col) != ha["columns"].get(col):
                diffs.append(f"1: {stage} column {col}")
        if stage == STAGES[-1] and hb["flag_versions"] != ha["flag_versions"]:
            diffs.append("2: flag versions")
        if harness._summary(base, stage) != harness._summary(d, stage):
            diffs.append(f"4: {stage} summary")
    fb = harness._files(base / "work.ms.rang-run" / "calibrate")
    fa = harness._files(d / "work.ms.rang-run" / "calibrate")
    if fb != fa:
        diffs.append("3: tables")
    return diffs


def report(run):
    run = Path(run)
    base = run / "W-B-r0"
    out = {"points": {}, "configs": {}}
    for config in CONFIGS:
        walls = {s: [] for s in STAGES}
        spawn = {s: [] for s in STAGES}
        for repeat in range(REPEATS):
            d = run / f"W-{config}-r{repeat}"
            if not (d / "done.json").is_file():
                out["points"][d.name] = "not obtained"
                continue
            rec = json.loads((d / "done.json").read_text())
            row = {"identity": _identity(base, d) if base.is_dir() else "no base"}
            for s in STAGES:
                st = rec["stages"][s]
                walls[s].append(st["wall_s"])
                ft = st.get("first_task")
                if ft:
                    spawn[s].append(round(ft["unix"] - st["started_unix"], 2))
                row[s] = {k: st[k] for k in ("wall_s", "own_cpu_s", "max_rss_kb",
                                             "foreign_cores", "load1_before",
                                             "load1_after")}  # fmt: skip
                row[s]["first_task_s"] = spawn[s][-1] if ft else None
            out["points"][d.name] = row
        out["configs"][config] = {
            "median_wall_s": {s: statistics.median(v) if v else None
                              for s, v in walls.items()},
            "walls_s": walls,
            "first_task_s": spawn,
        }  # fmt: skip
    t1 = out["configs"]["N1"]["median_wall_s"]
    for config in CONFIGS:
        c = out["configs"][config]
        if config == "B":
            continue
        n = int(config[1:])
        c["speedup"] = {s: round(t1[s] / c["median_wall_s"][s], 3)
                        if t1[s] and c["median_wall_s"][s] else None for s in STAGES}  # fmt: skip
        c["efficiency"] = {s: round(v / n, 3) if v else None
                           for s, v in c["speedup"].items()}  # fmt: skip
        f1 = out["configs"]["N1"]["first_task_s"]
        c["spawn_overhead_s"] = {
            s: round(statistics.median(c["first_task_s"][s]) - statistics.median(f1[s]), 2)
            if c["first_task_s"][s] and f1[s] else None
            for s in STAGES
        }  # fmt: skip
    text = json.dumps(out, indent=1) + "\n"
    (run / "timing.json").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    if sys.argv[1] == "point":
        sys.exit(point(sys.argv[2], sys.argv[3], int(sys.argv[4])))
    elif sys.argv[1] == "matrix":
        matrix(sys.argv[2])
    elif sys.argv[1] == "report":
        report(sys.argv[2])
    else:
        raise SystemExit(__doc__)
