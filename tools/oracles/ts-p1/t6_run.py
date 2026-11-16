"""TS-P1 T6 (research/ts-p1.md 13.4, 15): rang's lightcurve and WSClean's
-intervals-out on tsp1-held2, each under an exclusive heavy-lock hold, with
the coordinator's rule: an exclusive ticket waits at the head of the queue
for at most HEAD_LIMIT seconds, then is withdrawn and retried after RETRY_S.

    python tools/oracles/ts-p1/t6_run.py OUTDIR [--attempts 12]

Writes OUTDIR/t6-rang.log, OUTDIR/lc-t6/ (with its receipt beside) and, on
the WSL host, ~/Build/tmp/20261116-ts-p1/wsc-t6/ (timing.txt); appends one
JSON line per attempt to OUTDIR/t6-attempts.jsonl.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LOCK = r"C:\Users\gijsm\Github\rang\tools\heavy_lock.py"
WT = Path(__file__).resolve().parents[3]
HEAD_LIMIT = 600
RETRY_S = 900
POLL = 15


def status():
    return subprocess.run(
        [sys.executable, LOCK, "status", "--sample", "0.2"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout


def head_ticket(text):
    for line in text.splitlines():
        if line.startswith("queue 1: "):
            return line.split()[2]
    return None


def tickets(text):
    return {line.split()[2] for line in text.splitlines() if line.startswith("queue ")}


def attempt(name, argv, kill, granted_marker, log, attempts_log):
    started = time.time()
    before = tickets(status())
    with open(log, "a", encoding="utf-8") as out:
        proc = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT)
        mine, head_since, granted = None, None, False
        tag = f"-windows-{proc.pid}" if name == "windows" else "-wsl-"
        while proc.poll() is None:
            time.sleep(POLL)
            text = status()
            if granted_marker in text and "exclusive: free" not in text:
                granted = True
            if granted:
                continue
            head = head_ticket(text)
            if mine is None:
                new = [t for t in tickets(text) - before if tag in t]
                mine = new[0] if len(new) == 1 else None
            if head is not None and head == mine:
                head_since = head_since or time.time()
                if time.time() - head_since > HEAD_LIMIT:
                    kill(proc)
                    rec = {"job": name, "result": "withdrawn", "waited_s": time.time() - started,
                           "at_head_s": time.time() - head_since}  # fmt: skip
                    attempts_log.write(json.dumps(rec) + "\n")
                    attempts_log.flush()
                    return None
        rec = {"job": name, "result": "ran", "exit": proc.returncode,
               "waited_s": time.time() - started}  # fmt: skip
        attempts_log.write(json.dumps(rec) + "\n")
        attempts_log.flush()
        return proc.returncode


def kill_windows(proc):
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], check=False,
                   capture_output=True)  # fmt: skip


def kill_wsl(proc):
    subprocess.run(["wsl.exe", "-e", "pkill", "-f", "wsclean_intervals.sh .*wsc-t6"],
                   check=False, capture_output=True)  # fmt: skip
    kill_windows(proc)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("outdir")
    p.add_argument("--attempts", type=int, default=12)
    a = p.parse_args()
    o = Path(a.outdir)
    env = dict(os.environ, RAYON_NUM_THREADS="16")
    os.environ.update(env)
    rang = [sys.executable, LOCK, "run", "--", str(WT / ".venv/Scripts/python.exe"),
            "-m", "rang.core_cli", "lightcurve", str(o / "tsp1-held2.ms"), "--field",
            "3", "--positions", str(o / "tsp1-held2.positions.csv"), "--size", "2048",
            "--scale", "2asec", "--out", str(o / "lc-t6")]  # fmt: skip
    wsl = ["wsl.exe", "-e", "bash", "-lc",
           ("mkdir -p ~/Build/tmp/20261116-ts-p1 && cd ~ && python3 "
           "~/Github/rang/tools/heavy_lock.py run -- bash /mnt/c/Users/gijsm/Worktrees/"
           "rang/ts-p1/tools/oracles/ts-p1/wsclean_intervals.sh "
           "/mnt/d/rang/outputs/ts-p1-20261116/tsp1-held2.ms "
           "~/Build/tmp/20261116-ts-p1/wsc-t6 16 450 2048 2asec")]  # fmt: skip
    jobs = [("windows", rang, kill_windows, "lc-t6", o / "t6-rang.log"),
            ("wsl", wsl, kill_wsl, "wsclean_intervals", o / "t6-wsclean.log")]  # fmt: skip
    with open(o / "t6-attempts.jsonl", "a", encoding="utf-8") as attempts_log:
        for name, argv, kill, marker, log in jobs:
            for k in range(a.attempts):
                if name == "windows" and (o / "lc-t6").exists():
                    raise SystemExit(f"{o / 'lc-t6'} exists from a partial run")
                code = attempt(name, argv, kill, marker, log, attempts_log)
                if code is not None:
                    break
                time.sleep(RETRY_S)
            else:
                raise SystemExit(f"{name}: not granted in {a.attempts} attempts")
            if code:
                raise SystemExit(f"{name}: exit {code}")
    print("t6 done")


if __name__ == "__main__":
    main()
