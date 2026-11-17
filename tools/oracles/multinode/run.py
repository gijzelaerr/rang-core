# SPDX-License-Identifier: GPL-3.0-or-later
"""The identity gate and the scaling points of research/multinode-executor.md
(sections 3 and 4): the spool executor against the oracle O.

    python run.py arm RUN CASE ARM     # one arm: fresh MS copy, stages, hashes
    python run.py stage DIR STAGE      # (inside arm) workers + one stage
    python run.py verdict RUN          # every arm against O, criteria 1-5
    python run.py report RUN           # S(N), efficiency, overhead (case W)

Cases: F (the public fixture, chunk-task-api's case F configuration) and W
(w3.ms, its case W configuration). Arms:

    O      the oracle: RANG_MN_ORACLE's Python at default data settings
    Sp2    F: spool, 2 workers x 1 thread
    Sp4T   F: spool, 4 workers x 1 thread, chunk_rows 7 (many tasks)
    Kill   F: spool, 2 workers x 1 thread, chunk_rows 7; the worker of the
           first claim of each stage is killed after it claims
    I      W: inline, memory_limit_gb 2, RAYON_NUM_THREADS 2 (section 4)
    S<N>   W: spool, N workers x 2 threads, processes N, memory_limit_gb 2N

Every worker is a child of `stage` in a session (POSIX) or process group
(Windows) of its own: one "node" each. On Linux each stage is one reading of
tools/oracles/nash/timed.py, whose wait4 covers the workers. The environment:

    RANG_MN_F, RANG_MN_W   the source MSs (read only; copied per arm)
    RANG_MN_STRATEGY       CARACal's first-pass strategy YAML
    RANG_MN_ORACLE         a checkout of origin/main whose python/rang holds the
                           same _core build as this checkout
    RANG_MN_PYTHON         the interpreter (default: this one)
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKOUT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "chunk_tasks"))
sys.path.insert(0, str(HERE.parent / "nash"))

import run as cta

STAGES = ("flag", "calibrate", "apply")
# Never run a stage on these (the chunk-task-api matrix's copy of w3.ms).
PROTECTED = [Path.home() / "rang-data" / "outputs" / "w3"]
W_THREADS = 2  # per worker (section 4)
W_GB = 2  # per worker (section 4)


def arm_settings(case, arm):
    """(data lines, workers, threads per worker, RAYON_NUM_THREADS, kill)."""
    if arm == "O":
        return [], 0, None, 4, False
    if case == "F":
        return {
            "Sp2": (["processes: 2"], 2, 1, 1, False),
            "Sp4T": (["processes: 4", "chunk_rows: 7"], 4, 1, 1, False),
            "Kill": (["processes: 2", "chunk_rows: 7"], 2, 1, 1, True),
        }[arm]
    if arm == "I":
        return [f"memory_limit_gb: {W_GB}"], 0, None, W_THREADS, False
    n = int(arm[1:])
    return (
        [f"processes: {n}", f"memory_limit_gb: {W_GB * n}"],
        n,
        W_THREADS,
        W_THREADS,
        False,
    )


def _protected(path):
    p = Path(path).resolve()
    return any(p == q or q in p.parents for q in (x.resolve() for x in PROTECTED))


def _code(arm):
    if arm == "O":
        return Path(os.environ["RANG_MN_ORACLE"]) / "python"
    return CHECKOUT / "python"


def _python():
    return os.environ.get("RANG_MN_PYTHON") or sys.executable


def config_text(case, arm, d, ms):
    lines, workers, *_ = arm_settings(case, arm)
    if workers:
        spool = (d / "spool").resolve().as_posix()
        lines = ["executor: spool", f"spool: {json.dumps(spool)}"] + lines
    cta.STRATEGY = Path(os.environ["RANG_MN_STRATEGY"])
    cta.ARMS["_mn"] = lines
    return cta.config_text(case, "_mn", ms)


BUILD_SNIPPET = (
    "import json; from rang import core_spool; print(json.dumps(core_spool.build()))"
)


def _build(py, code):
    out = subprocess.run(
        [py, "-c", BUILD_SNIPPET],
        env=dict(os.environ, PYTHONPATH=str(code)),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


# -- one stage with its workers ------------------------------------------------------


def _start_worker(py, spool, threads, env, log):
    kw = {}
    if os.name == "posix":
        kw["start_new_session"] = True
    else:
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    cmd = [py, "-m", "rang.core_spool", "worker", str(spool), "--threads", str(threads)]
    return subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, **kw)


def _killer(spool, procs, record, halt):
    """Kill the worker of the first claim, once (the kill test)."""
    claimed = spool / "claimed"
    while not halt.is_set():
        for claim in claimed.glob("*"):
            try:
                owner = claim.read_text(encoding="utf-8").strip()
                pid = int(owner.split("-")[-2])
            except (OSError, ValueError, IndexError):
                continue  # being written
            for p in procs:
                if p.pid == pid:
                    p.kill()
                    record["killed"] = {"pid": pid, "claim": claim.name,
                                        "unix": time.time()}  # fmt: skip
                    return
        halt.wait(0.05)


def stage(d, name):
    d = Path(d)
    a = json.loads((d / "arm.json").read_text())
    if _protected(d / "work.ms"):
        raise SystemExit(f"refused: {d / 'work.ms'} is under a protected path")
    py, code = _python(), Path(a["code"])
    env = dict(os.environ, PYTHONPATH=str(code), RAYON_NUM_THREADS=str(a["rayon"]))
    spool = d / "spool"
    if spool.exists():
        shutil.rmtree(spool)
    record = {"stage": name, "workers": []}
    procs, logs = [], []
    if a["workers"]:
        sys.path.insert(0, str(code))
        from rang import core_spool

        core_spool.prepare(spool)
        for i in range(a["workers"]):
            log = open(d / f"worker-{name}-{i}.log", "w", encoding="utf-8")  # noqa: SIM115
            logs.append(log)
            procs.append(_start_worker(py, spool, a["threads"], env, log))
        record["workers"] = [p.pid for p in procs]
    halt = threading.Event()
    killer = None
    if a.get("kill") and procs:
        killer = threading.Thread(target=_killer, args=(spool, procs, record, halt))
        killer.start()
    t0 = time.time()
    proc = subprocess.run(
        [py, "-m", "rang.core_cli", name, "config.yaml", "work.ms"],
        cwd=d,
        env=env,
        check=False,
    )
    record["driver_wall_s"] = round(time.time() - t0, 2)
    halt.set()
    if killer:
        killer.join()
    if procs:
        (spool / "stop").touch()
        for p in procs:
            try:
                p.wait(120)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        record["worker_exits"] = [p.returncode for p in procs]
        for log in logs:
            log.close()
        shutil.rmtree(spool, ignore_errors=True)
    (d / f"stage-{name}.json").write_text(json.dumps(record, indent=1) + "\n")
    return proc.returncode


# -- one arm ---------------------------------------------------------------------------


def arm(run, case, arm_name):
    run = Path(run)
    d = run / f"{case}-{arm_name}"
    if (d / "done.json").is_file():
        print(f"{d.name}: done already")
        return 0
    if d.exists():  # an interrupted attempt: kept, renamed
        d.rename(d.with_name(f"{d.name}.void-{int(time.time())}-interrupted"))
    d.mkdir(parents=True)
    source = Path(os.environ[f"RANG_MN_{case}"])
    ms = d / "work.ms"
    if _protected(ms):
        raise SystemExit(f"refused: {ms} is under a protected path")
    shutil.copytree(source, ms)
    (d / "config.yaml").write_text(config_text(case, arm_name, d, ms), encoding="utf-8")
    lines, workers, threads, rayon, kill = arm_settings(case, arm_name)
    code = _code(arm_name)
    py = _python()
    a = {"case": case, "arm": arm_name, "code": str(code), "data": lines,
         "workers": workers, "threads": threads, "rayon": rayon, "kill": kill,
         "source": str(source), "build": _build(py, code),
         "host": os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME")}  # fmt: skip
    (d / "arm.json").write_text(json.dumps(a, indent=1) + "\n")
    record = dict(a, stages={})
    for name in STAGES:
        cmd = [py, str(HERE / "run.py"), "stage", str(d), name]
        log = d / f"{name}.log"
        if sys.platform.startswith("linux"):
            import timed

            rec = timed.measure(cmd, None, str(d), str(log), 1e9, 0)
        else:
            t0 = time.time()
            with open(log, "w", encoding="utf-8") as f:
                p = subprocess.run(cmd, cwd=d, stdout=f, stderr=subprocess.STDOUT,
                                   check=False)  # fmt: skip
            rec = {"exit": p.returncode, "wall_s": round(time.time() - t0, 2)}
        st = d / f"stage-{name}.json"
        if st.is_file():
            rec["stage"] = json.loads(st.read_text())
        record["stages"][name] = rec
        print(f"{d.name} {name}: exit {rec['exit']}, {rec['wall_s']} s", flush=True)
        if rec["exit"]:
            break
        (d / f"hashes-{name}.json").write_text(
            json.dumps(cta.hashes(ms), indent=1) + "\n", encoding="utf-8"
        )
    shutil.rmtree(ms)
    fv = d / "work.ms.flagversions"
    if fv.exists():
        shutil.rmtree(fv)
    (d / "done.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return 0


# -- verdict and report ---------------------------------------------------------------


def _summary_raw(d, stage):
    path = d / "work.ms.rang-run" / stage / "summary.json"
    return json.loads(path.read_text()) if path.is_file() else None


def verdict(run):
    run = Path(run)
    report = {"cases": {}, "pass": True}
    for case in ("F", "W"):
        o = run / f"{case}-O"
        if not (o / "done.json").is_file():
            continue
        done_o = json.loads((o / "done.json").read_text())
        out = {"O_build": done_o["build"]}
        for d in sorted(run.glob(f"{case}-*")):
            name = d.name.split("-", 1)[1]
            if name == "O" or "." in name or not (d / "done.json").is_file():
                continue
            done_a = json.loads((d / "done.json").read_text())
            diffs = []
            if done_a["build"]["core_sha256"] != done_o["build"]["core_sha256"]:
                diffs.append("_core build differs from O's")
            for stage in STAGES:
                eo = done_o["stages"].get(stage, {}).get("exit")
                ea = done_a["stages"].get(stage, {}).get("exit")
                if eo != 0 or ea != 0:
                    diffs.append(f"5: {stage} exit O {eo}, {name} {ea}")
                    continue
                ho = json.loads((o / f"hashes-{stage}.json").read_text())
                ha = json.loads((d / f"hashes-{stage}.json").read_text())
                for col in sorted(set(ho["columns"]) | set(ha["columns"])):
                    if ho["columns"].get(col) != ha["columns"].get(col):
                        diffs.append(f"1: {stage} column {col}")
                if stage == STAGES[-1] and ho["flag_versions"] != ha["flag_versions"]:
                    diffs.append("2: flag versions")
                if cta._summary(o, stage) != cta._summary(d, stage):
                    diffs.append(f"4: {stage} summary")
            fo = cta._files(o / "work.ms.rang-run" / "calibrate")
            fa = cta._files(d / "work.ms.rang-run" / "calibrate")
            if fo != fa:
                bad = sorted(k for k in set(fo) | set(fa) if fo.get(k) != fa.get(k))
                diffs.append("3: tables " + ", ".join(bad))
            chunking = {}
            for stage in STAGES:
                s = _summary_raw(d, stage)
                if s and "chunking" in s:
                    chunking[stage] = s["chunking"].get("spool_counts")
            out[name] = {
                "pass": not diffs,
                "differences": diffs,
                "files_compared": len(fo),
                "walls_s": {s: v["wall_s"] for s, v in done_a["stages"].items()},
                "killed": {
                    s: v.get("stage", {}).get("killed")
                    for s, v in done_a["stages"].items()
                },
                "spool_counts": chunking,
            }
            report["pass"] &= not diffs
        report["cases"][case] = out
    text = json.dumps(report, indent=1) + "\n"
    (run / "verdict.json").write_text(text, encoding="utf-8")
    print(text)


def report(run):
    run = Path(run)
    points = {}
    for d in sorted(run.glob("W-*")):
        name = d.name[2:]
        if "." in name or not (d / "done.json").is_file():
            continue
        points[name] = json.loads((d / "done.json").read_text())
    out = {"points": {}, "scaling": {}}
    for name, p in points.items():
        row = {}
        for stage, r in p["stages"].items():
            row[stage] = {k: r.get(k) for k in ("wall_s", "own_cpu_s", "max_rss_kb",
                                                 "foreign_cores", "load1_before",
                                                 "load1_after")}  # fmt: skip
            s = _summary_raw(run / f"W-{name}", stage)
            if s and s.get("chunking", {}).get("spool_counts"):
                row[stage]["spool"] = s["chunking"]["spool_counts"]
        row["total_wall_s"] = round(sum(r["wall_s"] for r in p["stages"].values()), 2)
        out["points"][name] = row
    s1 = out["points"].get("S1")
    if s1:
        for name, row in out["points"].items():
            if not name.startswith("S"):
                continue
            n = int(name[1:])
            sc = {}
            for stage in [*STAGES, "total"]:
                key = "total_wall_s" if stage == "total" else stage
                t1 = s1[key] if stage == "total" else s1[stage]["wall_s"]
                tn = row[key] if stage == "total" else row[stage]["wall_s"]
                sc[stage] = {
                    "S": round(t1 / tn, 3),
                    "efficiency": round(t1 / tn / n, 3),
                }
            out["scaling"][name] = sc
        inline = out["points"].get("I")
        if inline:
            out["overhead_S1_over_I"] = {
                stage: round(s1[stage]["wall_s"] / inline[stage]["wall_s"], 3)
                for stage in STAGES
            } | {"total": round(s1["total_wall_s"] / inline["total_wall_s"], 3)}
    plans = {}
    for name in out["points"]:
        if name.startswith("S"):
            plans[name] = {
                st: (out["points"][name][st].get("spool") or {}).get("plan_sha256")
                for st in STAGES
            }
    out["plans"] = plans
    out["plans_equal"] = (
        len({json.dumps(v, sort_keys=True) for v in plans.values()}) <= 1
    )
    text = json.dumps(out, indent=1) + "\n"
    (run / "report.json").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "arm":
        sys.exit(arm(sys.argv[2], sys.argv[3], sys.argv[4]))
    elif cmd == "stage":
        sys.exit(stage(sys.argv[2], sys.argv[3]))
    elif cmd == "verdict":
        verdict(sys.argv[2])
    elif cmd == "report":
        report(sys.argv[2])
    else:
        raise SystemExit(__doc__)
