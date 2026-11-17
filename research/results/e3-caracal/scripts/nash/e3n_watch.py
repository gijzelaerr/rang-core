"""E3 watcher on nash (research/e3-caracal.md 10.14), the apptainer stand-in for
e3_watch.py (docker events, docker update and docker cgroups do not exist here):

    python e3n_watch.py --log LOG.jsonl --rundir RUN --kill-gib K -- COMMAND ...

Starts COMMAND and, every second, sums the resident set of its whole process
tree. Each `apptainer run` process (one per Stimela step) is a container: its
own subtree's summed RSS is tracked, and at its exit one `container` record
gives its image, start, end and peak. Every 60 s a `sample` record: tree RSS,
du -sb of RUN, load average. If the tree's RSS passes K GiB it stops the tree
(SIGTERM, then SIGKILL after 30 s), writes `halt` and exits 75: the guard that
keeps this job inside its heavy-lock booking on a shared host. Summed RSS
counts shared pages once per process, so it over-states, never under-states.
It touches no process outside the tree it started.
"""

import argparse
import json
import os
import subprocess
import sys
import time

import psutil

GIB = 1024**3


def du(path):
    try:
        out = subprocess.run(["du", "-sb", path], capture_output=True, text=True).stdout
        return int(out.split()[0])
    except Exception:
        return None


def _ancestors(pid, parent):
    out, q = [], parent.get(pid)
    while q is not None and q not in out:
        out.append(q)
        q = parent.get(q)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--rundir", required=True)
    ap.add_argument("--kill-gib", type=float, required=True)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    log = open(a.log, "a")

    def rec(**kw):
        kw["t"] = time.time()
        log.write(json.dumps(kw) + "\n")
        log.flush()
        os.fsync(log.fileno())

    proc = subprocess.Popen(cmd)
    root = psutil.Process(proc.pid)
    rec(kind="start", pid=proc.pid, cmd=cmd, load=os.getloadavg(), kill_gib=a.kill_gib)
    live = {}  # apptainer-run pid -> {"image", "start", "peak"}
    seen = set()
    peak_tree, last_sample, halted = 0, 0.0, False
    while proc.poll() is None:
        try:
            procs = [root, *root.children(recursive=True)]
        except psutil.NoSuchProcess:
            break
        rss, parent, cmd_of = {}, {}, {}
        for p in procs:
            try:
                rss[p.pid] = p.memory_info().rss
                parent[p.pid] = p.ppid()
                if p.pid not in seen:
                    cmd_of[p.pid] = " ".join(p.cmdline())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        # Stimela's xrun starts `apptainer run ... IMAGE.sif ...`, possibly through `sh -c`, and
        # apptainer re-execs as its starter: the outermost new process whose command line names
        # `apptainer run` and a .sif is the container's top.
        for pid in sorted(cmd_of, key=lambda q: len(_ancestors(q, parent))):
            seen.add(pid)
            js = cmd_of[pid]
            if ("apptainer run" in js and ".sif" in js
                    and not any(x in live for x in _ancestors(pid, parent))):
                img = next((c for c in js.split() if c.endswith(".sif")), "?")
                live[pid] = {"image": os.path.basename(img), "start": time.time(), "peak": 0}
        total = sum(rss.values())
        peak_tree = max(peak_tree, total)
        sums = {k: 0 for k in live}
        for pid, r in rss.items():
            q = pid
            while q in parent and q not in live:
                q = parent[q]
            if q in live:
                sums[q] += r
        for k, s in sums.items():
            live[k]["peak"] = max(live[k]["peak"], s)
        for k in [k for k in live if k not in rss]:
            c = live.pop(k)
            rec(kind="container", pid=k, image=c["image"], start=c["start"], end=time.time(),
                peak_rss_bytes=c["peak"])
        now = time.time()
        if now - last_sample >= 60:
            rec(kind="sample", tree_rss_bytes=total, du_bytes=du(a.rundir), load=os.getloadavg(),
                nproc=len(rss))
            last_sample = now
        if total > a.kill_gib * GIB and not halted:
            halted = True
            rec(kind="halt", tree_rss_bytes=total, reason=f"tree RSS over {a.kill_gib} GiB")
            for p in procs:
                try:
                    p.terminate()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(procs, timeout=30)
            for p in procs:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
        time.sleep(1)
    rc = proc.wait()
    for k, c in live.items():
        rec(kind="container", pid=k, image=c["image"], start=c["start"], end=time.time(),
            peak_rss_bytes=c["peak"])
    rec(kind="end", rc=rc, peak_tree_rss_bytes=peak_tree, du_bytes=du(a.rundir), load=os.getloadavg())
    sys.exit(75 if halted else rc)


if __name__ == "__main__":
    main()
