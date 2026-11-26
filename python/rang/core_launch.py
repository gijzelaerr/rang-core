# SPDX-License-Identifier: MIT
"""Start spool workers from a batch scheduler: `rang-core spool submit`
(multi-node stage 2, step 2, research/multinode-2.md).

The spool executor (`core_spool`) needs workers that can read the MS and
the spool at the same paths as the parent. This module starts them: as a
Slurm job array (`sbatch --array`), a PBS Professional / OpenPBS array job
(`qsub -J`), a Torque array job (`qsub -t`, untested) or local detached
processes (any OS). Each array task runs one worker,

    PYTHON -m rang.core_spool worker SPOOL --threads T --idle-exit S

with PYTHON the submitter's interpreter, so the environment (a venv on the
shared filesystem) is the parent's. Recovery from a lost worker or node is
the spool's lease (`core_spool.LEASE_S`), not the scheduler's requeue, so
array tasks are submitted not to requeue (except PBS arrays, which PBS
requires to be rerunnable).

    rang-core spool submit SPOOL --scheduler slurm --workers 8 --threads 4 \
        --mem-gb 16 --directive=--account=b42
    rang-core spool status SPOOL
    rang-core spool stop SPOOL [--cancel]

Each submission writes `SPOOL/launch/<id>/` (the script, the submit command,
the scheduler's output) and `SPOOL/launch/<id>.json` (what was submitted and
the job id), so `stop --cancel` can cancel it.
"""

import argparse
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

SCHEDULERS = ("local", "slurm", "pbs", "torque")
DEFAULT_IDLE_EXIT_S = 600.0
WALLTIME = re.compile(r"^(\d+-)?\d+(:\d{2}){0,2}$")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,14}$")


class LaunchError(RuntimeError):
    """A submission that cannot be made: bad settings, a stale stop file,
    a scheduler command that failed."""


def _script_header(scheduler, n, threads, mem_gb, walltime, name, logdir, extra):
    """The scheduler directives of the worker script, one per line."""
    log = logdir.as_posix()
    lines = []
    if scheduler == "slurm":
        if n > 1:
            lines.append(f"#SBATCH --array=0-{n - 1}")
        lines += [
            f"#SBATCH --job-name={name}",
            "#SBATCH --nodes=1",
            "#SBATCH --ntasks=1",
            f"#SBATCH --cpus-per-task={threads}",
            f"#SBATCH --output={log}/%A_%a.out",
            "#SBATCH --no-requeue",
        ]
        if mem_gb:
            lines.append(f"#SBATCH --mem={_mem(mem_gb, 'G')}")
        if walltime:
            lines.append(f"#SBATCH --time={walltime}")
        lines += [f"#SBATCH {a}" for a in extra]
    elif scheduler == "pbs":
        # PBS Professional refuses a one-element array (`-J 0-0`).
        if n > 1:
            lines.append(f"#PBS -J 0-{n - 1}")
        res = f"select=1:ncpus={threads}"
        if mem_gb:
            res += f":mem={_mem(mem_gb, 'gb')}"
        lines += [f"#PBS -N {name}", f"#PBS -l {res}", "#PBS -j oe"]
        lines.append(f"#PBS -o {log}/")
        # PBS refuses a non-rerunnable array job ("cannot submit non-rerunable
        # Array Job"), so only a single worker is marked `-r n`; a subjob PBS
        # reruns after a node loss is one more worker, results unchanged.
        if n == 1:
            lines.append("#PBS -r n")
        if walltime:
            lines.append(f"#PBS -l walltime={walltime}")
        lines += [f"#PBS {a}" for a in extra]
    elif scheduler == "torque":
        if n > 1:
            lines.append(f"#PBS -t 0-{n - 1}")
        res = f"nodes=1:ppn={threads}"
        if mem_gb:
            res += f",mem={_mem(mem_gb, 'gb')}"
        lines += [f"#PBS -N {name}", f"#PBS -l {res}", "#PBS -j oe"]
        lines += [f"#PBS -o {log}/", "#PBS -r n"]
        if walltime:
            lines.append(f"#PBS -l walltime={walltime}")
        lines += [f"#PBS {a}" for a in extra]
    return lines


def _mem(gb, unit):
    """`gb` in the scheduler's units: whole gigabytes as `16G` / `16gb`,
    anything else in megabytes (`1536M` / `1536mb`)."""
    gb = float(gb)
    if gb == int(gb):
        return f"{int(gb)}{unit}"
    return f"{round(gb * 1024)}{'M' if unit == 'G' else 'mb'}"


def worker_command(spool, threads, idle_exit, python):
    return [
        str(python),
        "-m",
        "rang.core_spool",
        "worker",
        str(spool),
        "--threads",
        str(threads),
        "--idle-exit",
        f"{float(idle_exit):g}",
    ]


def script(
    scheduler,
    spool,
    n,
    threads=1,
    mem_gb=None,
    walltime=None,
    idle_exit=DEFAULT_IDLE_EXIT_S,
    name="rang-spool",
    python=None,
    logdir=None,
    extra=(),
):
    """The text of the worker script for `scheduler` (not `local`)."""
    if scheduler not in SCHEDULERS or scheduler == "local":
        raise LaunchError(f"no script for scheduler {scheduler!r}")
    spool = Path(spool)
    logdir = Path(logdir) if logdir else spool / "launch"
    python = python or sys.executable
    cmd = shlex.join(worker_command(spool.as_posix(), threads, idle_exit, python))
    lines = ["#!/bin/bash"]
    lines += _script_header(
        scheduler, n, threads, mem_gb, walltime, name, logdir, list(extra)
    )
    lines += [
        f"# rang-core spool submit: {n} spool worker(s) of {threads} thread(s)",
        "# (research/multinode-2.md). Recovery is the spool's lease, so the",
        "# scheduler does not requeue a task.",
        "set -e",
        f"export RAYON_NUM_THREADS={threads}",
        f"export OMP_NUM_THREADS={threads}",
        f"export OPENBLAS_NUM_THREADS={threads}",
        f"exec {cmd}",
    ]
    return "\n".join(lines) + "\n"


def submit_command(scheduler, script_path):
    """The command that submits `script_path`."""
    if scheduler == "slurm":
        return ["sbatch", "--parsable", str(script_path)]
    if scheduler in ("pbs", "torque"):
        return ["qsub", str(script_path)]
    raise LaunchError(f"no submit command for scheduler {scheduler!r}")


def cancel_command(scheduler, job_id):
    if scheduler == "slurm":
        return ["scancel", str(job_id)]
    if scheduler == "pbs":
        return ["qdel", "-W", "force", str(job_id)]
    if scheduler == "torque":
        return ["qdel", str(job_id)]
    raise LaunchError(f"no cancel command for scheduler {scheduler!r}")


def _job_id(scheduler, stdout):
    text = stdout.strip().splitlines()[-1].strip() if stdout.strip() else ""
    if scheduler == "slurm":
        return text.split(";")[0]  # --parsable: "jobid[;cluster]"
    return text  # qsub prints the job id (`123[].server` for arrays)


def _check(scheduler, n, threads, mem_gb, walltime, name, idle_exit):
    if scheduler not in SCHEDULERS:
        raise LaunchError(f"--scheduler {scheduler!r}: one of {list(SCHEDULERS)}")
    if int(n) < 1:
        raise LaunchError("--workers must be at least 1")
    if int(threads) < 1:
        raise LaunchError("--threads must be at least 1")
    if mem_gb is not None and float(mem_gb) <= 0:
        raise LaunchError("--mem-gb must be positive")
    if walltime and not WALLTIME.match(walltime):
        raise LaunchError(f"--walltime {walltime!r}: [D-]HH:MM:SS")
    if not NAME.match(name):
        raise LaunchError(f"--name {name!r}: a letter, then up to 14 of [A-Za-z0-9_.-]")
    if idle_exit is not None and float(idle_exit) <= 0:
        raise LaunchError("--idle-exit must be positive")


def submit(
    spool,
    scheduler,
    workers,
    threads=1,
    mem_gb=None,
    walltime=None,
    idle_exit=DEFAULT_IDLE_EXIT_S,
    name="rang-spool",
    python=None,
    dry_run=False,
    clear_stop=False,
    extra=(),
    runner=subprocess.run,
):
    """Start `workers` spool workers on `spool` through `scheduler`; return
    the launch record (also written to `SPOOL/launch/<id>.json`)."""
    from . import core_spool

    _check(scheduler, workers, threads, mem_gb, walltime, name, idle_exit)
    spool = Path(spool)
    if not spool.is_absolute():
        raise LaunchError(
            f"spool {spool} must be an absolute path (every worker opens it)"
        )
    root = core_spool.prepare(spool)
    stop = root / "stop"
    if stop.exists():
        if not clear_stop:
            raise LaunchError(
                f"{stop} exists, so every worker would exit at once; remove it "
                "or pass --clear-stop (no worker of an earlier run may still "
                "be needed)"
            )
        stop.unlink()
    python = str(Path(python or sys.executable).absolute())
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S")
    launch_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
    launch = root / "launch" / launch_id
    launch.mkdir(parents=True, mode=0o700)
    record = {
        "id": launch_id,
        "scheduler": scheduler,
        "workers": int(workers),
        "threads": int(threads),
        "mem_gb": mem_gb,
        "walltime": walltime,
        "idle_exit_s": idle_exit,
        "name": name,
        "python": python,
        "spool": root.as_posix(),
        "build": core_spool.build(),
        "dry_run": bool(dry_run),
        "submitted_unix": time.time(),
    }
    if scheduler == "local":
        cmd = worker_command(root, threads, idle_exit, python)
        record["command"] = cmd
        if not dry_run:
            record["pids"] = _start_local(cmd, int(workers), threads, launch)
    else:
        text = script(
            scheduler,
            root,
            int(workers),
            threads,
            mem_gb,
            walltime,
            idle_exit,
            name,
            python,
            launch,
            extra,
        )
        path = launch / "worker.sh"
        path.write_text(text, encoding="utf-8", newline="\n")
        cmd = submit_command(scheduler, path)
        record["script"] = path.as_posix()
        record["command"] = cmd
        if not dry_run:
            if shutil.which(cmd[0]) is None:
                raise LaunchError(
                    f"{cmd[0]} is not on PATH (is this a {scheduler} login node?)"
                )
            proc = runner(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise LaunchError(
                    f"{shlex.join(cmd)} failed ({proc.returncode}): "
                    f"{(proc.stderr or proc.stdout).strip()}"
                )
            record["job_id"] = _job_id(scheduler, proc.stdout)
    (root / "launch" / f"{launch_id}.json").write_text(
        json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    return record


def _start_local(cmd, n, threads, launch):
    """`n` detached worker processes, each in a session (POSIX) or process
    group (Windows) of its own; their output in `launch/worker-<i>.out`."""
    env = dict(os.environ, RAYON_NUM_THREADS=str(threads))
    kw = {}
    if os.name == "posix":
        kw["start_new_session"] = True
    else:
        kw["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    pids = []
    for i in range(n):
        with open(launch / f"worker-{i}.out", "wb") as log:
            p = subprocess.Popen(
                cmd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                **kw,
            )
        pids.append(p.pid)
    return pids


def launches(spool):
    """The launch records of `spool`, oldest first."""
    out = []
    for path in sorted(Path(spool, "launch").glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda r: r.get("submitted_unix", 0.0))


def status(spool):
    """{'workers', 'tasks', 'launches', 'stop'} of `spool`, read-only."""
    from . import core_spool

    root = Path(spool)
    now = time.time()
    workers = []
    for info in sorted((root / "workers").glob("*.json")):
        try:
            rec = json.loads(info.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        beat = info.with_suffix(".beat")
        try:
            age = now - beat.stat().st_mtime
        except OSError:
            age = None
        rec["worker"] = info.stem
        rec["beat_age_s"] = None if age is None else round(age, 1)
        rec["live"] = age is not None and age <= core_spool.LEASE_S
        workers.append(rec)

    def count(sub, pattern="*"):
        d = root / sub
        return (
            sum(1 for p in d.glob(pattern) if ".tmp-" not in p.name)
            if d.is_dir()
            else 0
        )

    return {
        "spool": root.as_posix(),
        "stop": (root / "stop").exists(),
        "workers": workers,
        "tasks": {
            "queued": count("tasks", "*.json"),
            "claimed": count("claimed"),
            "done": count("done", "*.pkl"),
            "failed": count("done", "*.err"),
        },
        "launches": launches(root),
    }


def stop(spool, cancel=False, runner=subprocess.run):
    """Ask every worker of `spool` to exit; with `cancel`, also cancel the
    recorded scheduler jobs. Returns the cancel commands run."""
    from . import core_spool

    core_spool.stop(spool)
    ran = []
    if cancel:
        for rec in launches(spool):
            job = rec.get("job_id")
            if not job or rec.get("dry_run"):
                continue
            cmd = cancel_command(rec["scheduler"], job)
            runner(cmd, capture_output=True, text=True, check=False)
            ran.append(cmd)
    return ran


def _status_text(st):
    t = st["tasks"]
    lines = [
        f"spool {st['spool']}" + ("  (stop requested)" if st["stop"] else ""),
        (
            f"tasks: {t['queued']} queued, {t['claimed']} claimed, "
            f"{t['done']} done, {t['failed']} failed"
        ),
        f"workers: {sum(w['live'] for w in st['workers'])} live of {len(st['workers'])}",
    ]
    for w in st["workers"]:
        job = w.get("scheduler_job") or {}
        jtxt = " ".join(f"{k}={v}" for k, v in sorted(job.items()))
        lines.append(
            f"  {w['worker']}: {'live' if w['live'] else 'stale'}, beat "
            f"{w['beat_age_s']} s ago, threads {w.get('threads')} {jtxt}".rstrip()
        )
    for rec in st["launches"]:
        lines.append(
            f"launch {rec['id']}: {rec['scheduler']} x{rec['workers']} "
            f"({rec['threads']} threads) job {rec.get('job_id', '-')}"
            + (" (dry run)" if rec.get("dry_run") else "")
        )
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="rang-core spool",
        description="Start, follow and stop the workers of a spool executor "
        "(data.executor: spool) on this host or through Slurm or PBS "
        "(research/multinode-2.md). The MS, the spool and this Python "
        "environment must be on a filesystem every node mounts at the same path.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser(
        "submit",
        help="start workers: local processes, a Slurm job array or a PBS array job",
        description="Write a worker script into SPOOL/launch/ and submit it "
        "(one worker per array task). --directive adds a line to the script's "
        "header, e.g. --directive=--account=X (Slurm) or --directive='-q normal' (PBS).",
    )
    s.add_argument("spool", help="the spool directory (data.spool), absolute")
    s.add_argument("--scheduler", required=True, choices=SCHEDULERS)
    s.add_argument("--workers", type=int, required=True, help="number of workers")
    s.add_argument("--threads", type=int, default=1, help="threads per worker")
    s.add_argument("--mem-gb", type=float, default=None, help="memory per worker, GB")
    s.add_argument("--walltime", default=None, help="[D-]HH:MM:SS per worker")
    s.add_argument(
        "--idle-exit",
        type=float,
        default=DEFAULT_IDLE_EXIT_S,
        help=f"a worker exits after this many idle seconds (default {DEFAULT_IDLE_EXIT_S:g})",
    )
    s.add_argument("--name", default="rang-spool", help="the job name")
    s.add_argument(
        "--python", default=None, help="the workers' interpreter (default: this one)"
    )
    s.add_argument(
        "--dry-run", action="store_true", help="write the script, submit nothing"
    )
    s.add_argument(
        "--clear-stop", action="store_true", help="remove a stop file left in SPOOL"
    )
    s.add_argument(
        "--json", action="store_true", help="print the launch record as JSON"
    )
    s.add_argument(
        "--directive",
        action="append",
        default=[],
        help="an extra scheduler directive for the script's header (repeatable)",
    )
    t = sub.add_parser(
        "status", help="workers, tasks and launches of a spool (read-only)"
    )
    t.add_argument("spool")
    t.add_argument("--json", action="store_true")
    p = sub.add_parser(
        "stop", help="ask the workers to exit; --cancel also cancels the jobs"
    )
    p.add_argument("spool")
    p.add_argument(
        "--cancel", action="store_true", help="scancel / qdel the recorded jobs"
    )
    args = ap.parse_args(argv)
    try:
        if args.cmd == "submit":
            rec = submit(
                args.spool,
                args.scheduler,
                args.workers,
                args.threads,
                args.mem_gb,
                args.walltime,
                args.idle_exit,
                args.name,
                args.python,
                args.dry_run,
                args.clear_stop,
                args.directive,
            )
            if args.json:
                print(json.dumps(rec, indent=1))
            else:
                what = rec.get("job_id") or rec.get("pids") or rec.get("script")
                print(
                    f"rang-core spool: {rec['scheduler']} x{rec['workers']} on "
                    f"{rec['spool']}: {what}" + (" (dry run)" if rec["dry_run"] else "")
                )
        elif args.cmd == "status":
            st = status(args.spool)
            print(json.dumps(st, indent=1) if args.json else _status_text(st))
        else:
            for cmd in stop(args.spool, args.cancel):
                print(shlex.join(cmd))
    except (LaunchError, OSError) as exc:
        print(f"rang-core spool: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    return 0


__all__ = [
    "SCHEDULERS",
    "LaunchError",
    "cancel_command",
    "launches",
    "script",
    "status",
    "stop",
    "submit",
    "submit_command",
    "worker_command",
]
