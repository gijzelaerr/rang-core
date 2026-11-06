"""breakdown.py TAG [NAME...]: the memory report of instrumented runs, as Markdown tables.

Reads runs/<TAG>/img/<name>-report.json and runs/<TAG>/time/<name>.txt under the G2 output directory.
Phases are collapsed: repeated per-cycle phases are reported by their largest value.
"""
import json
import sys
from pathlib import Path

O = Path("/mnt/d/rang/outputs/20261106-g2-memory")
tag = sys.argv[1]
names = sys.argv[2:] or ["s1-def", "h3-def", "p256-def", "s1-coarse", "h3-coarse"]
GB = 1e9


def rss_time(name):
    t = O / "runs" / tag / "time" / f"{name}.txt"
    for line in t.read_text().splitlines():
        if "Maximum resident" in line:
            return int(line.split(":")[1]) * 1024
    return None


for name in names:
    rep = O / "runs" / tag / "img" / f"{name}-report.json"
    if not rep.exists():
        print(f"## {name}: no report")
        continue
    r = json.loads(rep.read_text())
    m = r.get("memory")
    if not m or m == "null":
        print(f"## {name}: no memory section")
        continue
    print(f"## {tag} {name}: peak RSS {rss_time(name) / GB:.3f} GB (time -v), "
          f"cells {r['rows_gridded']} rows x {r['channels']} ch, active {r['visibilities_weighted']}")
    print()
    print("| phase | heap at end, GB | heap peak in phase, GB | RSS at end, GB | swap, GB |")
    print("| --- | ---: | ---: | ---: | ---: |")
    agg = {}
    order = []
    for p in m["phases"]:
        lab = p["label"]
        key = "cycle k: minor" if lab.startswith("cycle ") else lab
        if key not in agg:
            agg[key] = dict(end=0, peak=0, rss=0, swap=0, n=0)
            order.append(key)
        a = agg[key]
        a["end"] = max(a["end"], p["heap_end_bytes"])
        a["peak"] = max(a["peak"], p["heap_peak_bytes"])
        a["rss"] = max(a["rss"], p["rss_bytes"] or 0)
        a["swap"] = max(a["swap"], p["swap_bytes"] or 0)
        a["n"] += 1
    for k in order:
        a = agg[k]
        lab = k if a["n"] == 1 else f"{k} (largest of {a['n']})"
        print(f"| {lab} | {a['end'] / GB:.3f} | {a['peak'] / GB:.3f} | {a['rss'] / GB:.3f} | {a['swap'] / GB:.3f} |")
    print()
    print("| buffer | GB |")
    print("| --- | ---: |")
    for b in m["buffers"]:
        print(f"| {b['label']} | {b['bytes'] / GB:.3f} |")
    print()
