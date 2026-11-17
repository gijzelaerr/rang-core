"""Summarise one nash E3 pass's cost (research/e3-caracal.md 10.14), the e3n_watch.py form
of e3_cost.py:

    python e3n_cost.py RUNDIR OUT.json

Reads wall.txt (START/END lines with load averages), time-v.txt, lock-status-start.txt,
host.txt, watch.jsonl (container records: summed RSS of each `apptainer run` subtree;
end record: peak tree RSS; samples: du and load) and CARACal's log (worker times as
e3_cost.py: from the previous worker's finish to its own finish).
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path


def main():
    run, out = Path(sys.argv[1]), Path(sys.argv[2])
    wall = [x for x in (run / "wall.txt").read_text().split("\n") if x.strip()]
    s0, s1 = wall[0].split(), wall[1].split()
    t0, t1 = datetime.fromisoformat(s0[1]), datetime.fromisoformat(s1[1])
    res = {"run": str(run), "host": "nash", "start": s0[1], "end": s1[1], "rc": s1[2],
           "wall_s": (t1 - t0).total_seconds(),
           "load_start": " ".join(s0[3:6]), "load_end": " ".join(s1[4:7]),
           "raw_ms": wall[2] if len(wall) > 2 else None,
           "lock_status_start": (run / "lock-status-start.txt").read_text().strip(),
           "pinning": next((x for x in (run / "host.txt").read_text().splitlines()
                            if x.startswith("cpus ")), None)}
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
    cont = [{"image": e["image"], "s": round(e["end"] - e["start"], 1),
             "peak_rss_gb": e["peak_rss_bytes"] / 1e9} for e in ev if e["kind"] == "container"]
    res["containers"] = cont
    res["container_peak_rss_gb"] = max((c["peak_rss_gb"] for c in cont), default=None)
    end = [e for e in ev if e["kind"] == "end"]
    res["tree_peak_rss_gb"] = end[-1]["peak_tree_rss_bytes"] / 1e9 if end else None
    res["halted"] = any(e["kind"] == "halt" for e in ev)
    du = [e["du_bytes"] for e in ev if e.get("du_bytes")]
    res["peak_disk_gb"] = max(du) / 1e9 if du else None
    loads = [e["load"][0] for e in ev if e["kind"] == "sample"]
    res["load1_mean"] = sum(loads) / len(loads) if loads else None
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("wall_s", "rc", "raw_ms", "driver_max_rss_gb",
                                          "container_peak_rss_gb", "tree_peak_rss_gb",
                                          "peak_disk_gb", "load_start", "load_end", "load1_mean")}))
    for w in workers:
        print(w)


if __name__ == "__main__":
    main()
