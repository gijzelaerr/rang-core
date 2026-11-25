# SPDX-License-Identifier: MIT
"""The container-cluster arms of research/multinode-2.md (section 2), for
run.py. With RANG_MN_CLUSTER=1 every arm runs inside a cluster on this host
(cluster/slurm_cluster.sh or cluster/pbs_cluster.sh): the parent stage on the
login node through `podman exec`, the workers as a job array submitted with
`rang-core spool submit`. O and I run on the Slurm login node, alone.

    RANG_MN_SHARED   the shared directory every container mounts read-write
                     (the run root must be inside it)
    RANG_MN_MOUNTS   read-only mounts, os.pathsep-separated (the checkouts with
                     the venv, uv's Python)

Events: `cancel` scancels / qdels the array task whose worker made the first
claim of the stage; `node` SIGKILLs that worker's node container, which is
started again after the stage.
"""

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = {
    "slurm": HERE / "cluster" / "slurm_cluster.sh",
    "pbs": HERE / "cluster" / "pbs_cluster.sh",
}
LOGIN = {"slurm": "rangmn-ctl", "pbs": "rangpbs-pbs"}
NODE = {"slurm": "rangmn-{}", "pbs": "rangpbs-{}"}
PATH = "/opt/pbs/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
CTL_CPUS = 4
# The login node's memory: the parent's reduce. Case F's MS is small.
CTL_MEM_MB = {"F": 4000, "W": 16000}
IDLE_EXIT_S = 180


def _f(sched, workers, threads, nodes, cpus, mem_mb, mem_gb, data, event=None):
    return {
        "scheduler": sched,
        "workers": workers,
        "threads": threads,
        "nodes": nodes,
        "cpus": cpus,
        "mem_mb": mem_mb,
        "mem_gb": mem_gb,
        "data": data,
        "event": event,
    }


def spec(case, arm):
    """The cluster arm `arm` of `case`, or None (O and I: the login node)."""
    if not enabled():
        return None
    return dict(_spec(case, arm), ctl_mem_mb=CTL_MEM_MB[case])


def _spec(case, arm):
    if arm in ("O", "I"):
        return _f("slurm", 0, None, 1, 1, 2000, None, [])
    if case == "F":
        two = ["processes: 2"]
        many = ["processes: 2", "chunk_rows: 7"]
        table = {
            "Sl2": _f("slurm", 2, 1, 2, 1, 4000, 3, two),
            "Sl4T": _f("slurm", 4, 1, 2, 2, 8000, 3, ["processes: 4", "chunk_rows: 7"]),
            "SlKill": _f("slurm", 2, 1, 2, 1, 4000, 3, many, "cancel"),
            "SlNode": _f(
                "slurm", 3, 1, 3, 1, 4000, 3, ["processes: 3", "chunk_rows: 7"], "node"
            ),
            "Pb2": _f("pbs", 2, 1, 2, 1, 4000, 3, two),
            "PbKill": _f("pbs", 2, 1, 2, 1, 4000, 3, many, "cancel"),
        }
        return table[arm]
    m = re.fullmatch(r"(Sl|Pb)(\d+)", arm)
    if case == "W" and m:
        n = int(m.group(2))
        sched = "slurm" if m.group(1) == "Sl" else "pbs"
        return _f(
            sched, n, 2, n, 2, 6000, 5, [f"processes: {n}", f"memory_limit_gb: {2 * n}"]
        )
    raise KeyError(f"no cluster arm {case}-{arm}")


def enabled():
    return os.environ.get("RANG_MN_CLUSTER") == "1"


def booking(sp, rayon):
    """(slots, GB) for the whole cluster of one arm: the containers' caps
    (login node plus every node), so no container can use more than booked."""
    slots = CTL_CPUS + sp["nodes"] * sp["cpus"]
    gb = -(-(sp["ctl_mem_mb"] + sp["nodes"] * sp["mem_mb"]) // 1000)
    return slots, gb


def _mounts():
    return [m for m in os.environ.get("RANG_MN_MOUNTS", "").split(os.pathsep) if m]


def _script(sched, *args, check=True, ctl_mem_mb=4000):
    env = dict(os.environ, CTL_CPUS=str(CTL_CPUS), CTL_MEM_MB=str(ctl_mem_mb))
    return subprocess.run(
        ["bash", str(SCRIPTS[sched]), *map(str, args)],
        env=env,
        capture_output=True,
        text=True,
        check=check,
    )


def up(sp):
    for other in SCRIPTS:  # one cluster at a time on this host
        _script(other, "down", check=False)
    shared = os.environ["RANG_MN_SHARED"]
    p = _script(
        sp["scheduler"],
        "up",
        shared,
        sp["nodes"],
        sp["cpus"],
        sp["mem_mb"],
        *_mounts(),
        ctl_mem_mb=sp["ctl_mem_mb"],
    )
    return p.stdout


def down(sp):
    _script(sp["scheduler"], "down", check=False)


def login(sched, cmd, cwd, env=None, check=False):
    """`cmd` on the login node, in `cwd`, with `env` added."""
    full = ["podman", "exec", "-w", str(cwd), "-e", f"PATH={PATH}"]
    for k, v in (env or {}).items():
        full += ["-e", f"{k}={v}"]
    full += [LOGIN[sched], *map(str, cmd)]
    return subprocess.run(full, capture_output=True, text=True, check=check)


def _jobs_left(sched, job, cwd):
    if sched == "slurm":
        out = login(sched, ["squeue", "-h", "-r", "-j", job, "-o", "%i %T"], cwd).stdout
        return [line for line in out.splitlines() if line.strip()]
    out = login(sched, ["qstat", "-t", job], cwd).stdout
    return [ln for ln in out.splitlines() if re.search(r"\s[RQHE]\s", ln)]


def _killer(sp, spool, record, halt, cwd):
    """The event of the arm, once, on the worker of the first claim."""
    claimed = spool / "claimed"
    while not halt.is_set():
        for claim in sorted(claimed.glob("*")):
            try:
                owner = claim.read_text(encoding="utf-8").strip()
                info = json.loads((spool / "workers" / f"{owner}.json").read_text())
            except (OSError, ValueError):
                continue  # being written
            job = info.get("scheduler_job", {})
            ev = {
                "owner": owner,
                "claim": claim.name,
                "host": info.get("host"),
                "job": job,
                "unix": time.time(),
            }
            if sp["event"] == "cancel":
                if sp["scheduler"] == "slurm":
                    # ARRAY_TASK, not SLURM_JOB_ID: the last task's job id
                    # equals the array's, and `scancel <array id>` cancels
                    # every task (the void SlKill run of 2026-11-25).
                    jid = f"{job['SLURM_ARRAY_JOB_ID']}_{job['SLURM_ARRAY_TASK_ID']}"
                    cmd = ["scancel", jid]
                else:
                    cmd = ["qdel", "-W", "force", job["PBS_JOBID"]]
                p = login(sp["scheduler"], cmd, cwd)
                ev["command"] = cmd
                ev["exit"] = p.returncode
            else:
                name = NODE[sp["scheduler"]].format(info["host"])
                p = subprocess.run(
                    ["podman", "kill", "-s", "KILL", name],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                ev["killed_container"] = name
                ev["exit"] = p.returncode
            record["killed"] = ev
            return
        halt.wait(0.05)


CPU = re.compile(r"spool worker (\S+): (\d+) tasks, ([\d.]+) CPU-s, exiting")


def stage(d, name, a, py, code):
    """One stage of a cluster arm; returns the driver's exit code."""
    sp = a["cluster"]
    sched = sp["scheduler"]
    spool = d / "spool"
    if spool.exists():
        shutil.rmtree(spool)
    record = {"stage": name, "cluster": sp}
    env = {"PYTHONPATH": code, "RAYON_NUM_THREADS": a["rayon"]}
    halt = threading.Event()
    killer = None
    launch = None
    if sp["workers"]:
        import sys

        sys.path.insert(0, str(code))
        from rang import core_spool

        core_spool.prepare(spool)
        cmd = [
            py,
            "-m",
            "rang.core_cli",
            "spool",
            "submit",
            spool.as_posix(),
            "--scheduler",
            sched,
            "--workers",
            sp["workers"],
            "--threads",
            sp["threads"],
            "--mem-gb",
            sp["mem_gb"],
            "--idle-exit",
            IDLE_EXIT_S,
            "--name",
            f"mn-{name}",
            "--json",
        ]
        p = login(sched, cmd, d, env)
        if p.returncode:
            record["submit_error"] = p.stderr
            (d / f"stage-{name}.json").write_text(json.dumps(record, indent=1) + "\n")
            return 3
        launch = json.loads(p.stdout)
        record["launch"] = {k: launch.get(k) for k in ("id", "job_id", "command")}
        if sp["event"]:
            killer = threading.Thread(target=_killer, args=(sp, spool, record, halt, d))
            killer.start()
    t0 = time.time()
    p = login(
        sched, [py, "-m", "rang.core_cli", name, "config.yaml", "work.ms"], d, env
    )
    record["driver_wall_s"] = round(time.time() - t0, 2)
    (d / f"driver-{name}.log").write_text(p.stdout + p.stderr, encoding="utf-8")
    halt.set()
    if killer:
        killer.join()
    if launch:
        # The stop file first, so running workers exit on their own and log
        # their CPU-seconds; then cancel what is left (pending array tasks).
        stop = [py, "-m", "rang.core_cli", "spool", "stop", spool.as_posix()]
        login(sched, stop, d, env)
        t1 = time.time()
        while _jobs_left(sched, launch["job_id"], d) and time.time() - t1 < 60:
            time.sleep(2)
        login(sched, [*stop, "--cancel"], d, env)
        while _jobs_left(sched, launch["job_id"], d) and time.time() - t1 < 240:
            time.sleep(2)
        record["jobs_left_after_s"] = round(time.time() - t1, 1)
        logs = d / f"workers-{name}"
        src = spool / "launch" / launch["id"]
        if src.is_dir():
            shutil.copytree(src, logs, dirs_exist_ok=True)
        cpu = {}
        for f in logs.glob("*") if logs.is_dir() else []:
            for m in CPU.finditer(f.read_text(encoding="utf-8", errors="replace")):
                cpu[m.group(1)] = {"tasks": int(m.group(2)), "cpu_s": float(m.group(3))}
        record["workers_cpu"] = cpu
        if sp["event"] == "node" and record.get("killed"):
            host = record["killed"]["host"]
            r = _script(sched, "restart", host, check=False)
            record["restart"] = {"host": host, "exit": r.returncode}
        shutil.rmtree(spool, ignore_errors=True)
    (d / f"stage-{name}.json").write_text(json.dumps(record, indent=1) + "\n")
    return p.returncode
