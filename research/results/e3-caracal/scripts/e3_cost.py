"""Summarise one E3 pass's cost (research/e3-caracal.md section 4):

    python e3_cost.py RUNDIR OUT.json

Reads wall.txt, time-v.txt, lock-status-start.txt, watch.jsonl (only
quay.io/stimela/ containers count) and CARACal's log (worker 'running' and
'finished' lines; a worker's time is from the previous worker's finish to its
own finish, since CARACal logs 'running' after building the recipe).
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path


def main():
    run, out = Path(sys.argv[1]), Path(sys.argv[2])
    wall = (run / "wall.txt").read_text().split("\n")
    t0 = datetime.fromisoformat(wall[0].split()[1])
    end = wall[1].split()
    t1 = datetime.fromisoformat(end[1])
    res = {"run": str(run), "start": wall[0].split()[1], "end": end[1], "rc": end[2],
           "wall_s": (t1 - t0).total_seconds(), "raw_ms": wall[2] if len(wall) > 2 else None,
           "lock_status_start": (run / "lock-status-start.txt").read_text().strip()}
    tv = (run / "time-v.txt").read_text()
    m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", tv)
    res["driver_max_rss_gb"] = int(m.group(1)) / 1e6 if m else None
    logs = sorted((run / "output").glob("logs-*/log-caracal.txt"))
    workers = []
    if logs:
        prev = None
        for line in logs[-1].read_text(errors="replace").splitlines():
            mm = re.match(r"(\S+ \S+) CARACal INFO: (\S+): (running|finished)$", line)
            if not mm:
                continue
            t = datetime.strptime(mm.group(1), "%Y-%m-%d %H:%M:%S")
            if mm.group(3) == "finished":
                workers.append({"worker": mm.group(2),
                                "s": (t - prev).total_seconds() if prev else None})
                prev = t
            elif prev is None:
                prev = t
    res["workers"] = workers
    ev = [json.loads(x) for x in (run / "watch.jsonl").read_text().splitlines() if x.strip()]
    st = {e["id"]: e["t"] for e in ev if e["ev"] == "start"}
    cont = []
    for e in ev:
        if e["ev"] == "die" and (e.get("image") or "").startswith("quay.io/stimela/"):
            cont.append({"name": e["name"], "image": e["image"], "exit": e["exit"],
                         "s": round(e["t"] - st.get(e["id"], e["t"]), 1),
                         "memory_peak_gb": (e["memory_peak"] or 0) / 1e9})
    res["containers"] = cont
    res["container_peak_gb"] = max((c["memory_peak_gb"] for c in cont), default=None)
    res["containers_not_limited_before_start"] = sum(
        1 for e in ev if e["ev"] == "start"
        and (e.get("image") or "").startswith("quay.io/stimela/")
        and not e.get("limited_before_start"))
    du = [e["bytes"] for e in ev if e["ev"] == "du"]
    res["peak_disk_gb"] = max(du) / 1e9 if du else None
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("wall_s", "rc", "raw_ms", "driver_max_rss_gb",
                                          "container_peak_gb", "peak_disk_gb")}))
    for w in workers:
        print(w)


if __name__ == "__main__":
    main()
