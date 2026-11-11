"""E3 container watcher (research/e3-caracal.md section 4), runs in WSL beside
the CARACal driver:

    python3 e3_watch.py LOG.jsonl RUNDIR [--limit-cpus 8 --limit-mem 24g]

- follows `docker events` for container create/start/die and logs each with
  the host time;
- with --limit-*, runs `docker update --cpus N --memory M --memory-swap M` on
  every container at its `create` event (Stimela creates, then starts) and
  logs whether the update landed before `start`;
- every second reads `memory.peak` of each live container's cgroup and logs
  the last value seen at `die` (host-side read; the protocol's deviation);
- every 60 s logs `du -sb RUNDIR`.
Stops when the file RUNDIR/.watch-stop exists.
"""

import argparse
import glob
import json
import subprocess
import threading
import time
from pathlib import Path


def cgroup_file(cid, name):
    for pat in (f"/sys/fs/cgroup/system.slice/docker-{cid}*.scope/{name}",
                f"/sys/fs/cgroup/docker/{cid}*/{name}"):
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("log")
    p.add_argument("rundir")
    p.add_argument("--limit-cpus", default=None)
    p.add_argument("--limit-mem", default=None)
    a = p.parse_args()
    out = open(a.log, "a", buffering=1)
    lock = threading.Lock()

    def emit(**kw):
        kw["t"] = time.time()
        with lock:
            out.write(json.dumps(kw) + "\n")

    live = {}  # cid -> dict(name, peak, started, updated)
    stop = Path(a.rundir) / ".watch-stop"

    def events():
        proc = subprocess.Popen(
            ["docker", "events", "--filter", "type=container", "--format", "{{json .}}"],
            stdout=subprocess.PIPE, text=True)
        for line in proc.stdout:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            act, cid = ev.get("Action") or ev.get("status"), ev.get("id")
            name = ev.get("Actor", {}).get("Attributes", {}).get("name")
            image = ev.get("Actor", {}).get("Attributes", {}).get("image")
            if act == "create":
                upd = None
                if a.limit_cpus or a.limit_mem:
                    cmd = ["docker", "update"]
                    if a.limit_cpus:
                        cmd += ["--cpus", a.limit_cpus]
                    if a.limit_mem:
                        cmd += ["--memory", a.limit_mem, "--memory-swap", a.limit_mem]
                    r = subprocess.run(cmd + [cid], capture_output=True, text=True)
                    upd = r.returncode
                with lock:
                    live[cid] = {"name": name, "image": image, "peak": None,
                                 "started": False, "update_rc": upd}
                emit(ev="create", id=cid[:12], name=name, image=image, update_rc=upd)
            elif act == "start":
                with lock:
                    info = live.setdefault(cid, {"name": name, "image": image, "peak": None,
                                                 "update_rc": None})
                    info["started"] = True
                emit(ev="start", id=cid[:12], name=name, image=image,
                     limited_before_start=info.get("update_rc") == 0)
            elif act == "die":
                with lock:
                    info = live.pop(cid, {})
                emit(ev="die", id=cid[:12], name=name, image=image,
                     exit=ev.get("Actor", {}).get("Attributes", {}).get("exitCode"),
                     memory_peak=info.get("peak"))
            if stop.exists():
                proc.terminate()
                return

    th = threading.Thread(target=events, daemon=True)
    th.start()
    last_du = 0.0
    while not stop.exists():
        with lock:
            cids = list(live)
        for cid in cids:
            f = cgroup_file(cid, "memory.peak")
            if f:
                try:
                    v = int(open(f).read().strip())
                except (OSError, ValueError):
                    continue
                with lock:
                    if cid in live:
                        live[cid]["peak"] = max(v, live[cid]["peak"] or 0)
        if time.time() - last_du >= 60:
            last_du = time.time()
            r = subprocess.run(["du", "-sb", a.rundir], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout:
                emit(ev="du", bytes=int(r.stdout.split()[0]))
        time.sleep(1)
    emit(ev="stop")


if __name__ == "__main__":
    main()
