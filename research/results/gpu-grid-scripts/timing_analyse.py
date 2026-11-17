"""Section 8.4 of research/gpu-grid.md: the timing runs and section 5's decision rule.
Usage: timing_analyse.py OUT_JSON"""
import json
import re
import statistics as st
import sys
from pathlib import Path

T = Path("D:/rang/outputs/20261116-gpu-grid/timing")
W = Path("D:/rang/outputs/20261116-gpu-grid/wsclean")
SKIES, FORMS = ("s1", "h2", "h3"), ("coarse", "fine")


def phases(log):
    t = log.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(\d+) components, (\d+) major cycles.*?resync ([\d.]+) s, major ([\d.]+) s", t)
    g = re.search(r"gpu: .*compute ([\d.]+) s", t)
    return dict(components=int(m.group(1)), cycles=int(m.group(2)), resync_s=float(m.group(3)),
                major_s=float(m.group(4)), gpu_compute_s=float(g.group(1)) if g else None)


runs = {}
for f in sorted(T.glob("*-r[0-9].json")):
    name = f.stem
    r = json.loads(f.read_text())
    sky, form, arm, rep = name.split("-")
    rec = dict(sky=sky, form=form, arm=arm, rep=rep, wall_s=r["wall_s"], rc=r["rc"],
               peak_ws_gb=r["peak_working_set_bytes"] / 1e9, gpu_before_mib=r["gpu_used_before_mib"],
               gpu_peak_mib=r["gpu_peak_mib"], cpu_s=r["user_s"] + r["sys_s"])
    rec.update(phases(T / f"{name}.log"))
    runs[name] = rec
wsc = {}
for f in sorted(W.glob("*-r[0-9].txt")):
    t = f.read_text()
    wall = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", t).group(1).split(":")
    secs = sum(float(x) * 60 ** i for i, x in enumerate(reversed(wall)))
    rss = int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", t).group(1))
    wsc[f.stem] = dict(wall_s=secs, peak_rss_gb=rss * 1024 / 1e9)

cells, savings = [], {}
for sky in SKIES:
    for form in FORMS:
        pairs = []
        for rep in ("r1", "r2", "r3"):
            c, g = runs.get(f"{sky}-{form}-cpu-{rep}"), runs.get(f"{sky}-{form}-gpu-{rep}")
            if c and g:
                pairs.append((c["wall_s"] - g["wall_s"]) / c["wall_s"])
        cw = [runs[k]["wall_s"] for k in runs if k.startswith(f"{sky}-{form}-cpu")]
        gw = [runs[k]["wall_s"] for k in runs if k.startswith(f"{sky}-{form}-gpu")]
        cell = dict(sky=sky, form=form, pairs=pairs, saving_median=st.median(pairs) if pairs else None,
                    cpu_wall=st.median(cw) if cw else None, gpu_wall=st.median(gw) if gw else None,
                    cpu_major=st.median([runs[k]["major_s"] for k in runs if k.startswith(f"{sky}-{form}-cpu")]) if cw else None,
                    gpu_major=st.median([runs[k]["major_s"] for k in runs if k.startswith(f"{sky}-{form}-gpu")]) if gw else None,
                    cpu_peak_gb=max([runs[k]["peak_ws_gb"] for k in runs if k.startswith(f"{sky}-{form}-cpu")], default=None),
                    gpu_peak_gb=max([runs[k]["peak_ws_gb"] for k in runs if k.startswith(f"{sky}-{form}-gpu")], default=None),
                    gpu_dev_mib=max([(runs[k]["gpu_peak_mib"] or 0) - (runs[k]["gpu_before_mib"] or 0) for k in runs if k.startswith(f"{sky}-{form}-gpu")], default=None))
        cells.append(cell)
        savings[(sky, form)] = cell["saving_median"]
# Section 5: kept if >= 10 % on at least two of S1, H2, H3 in one form, no cell below -2 %.
kept_forms = [f for f in FORMS if sum(1 for s in SKIES if (savings.get((s, f)) or -1) >= 0.10) >= 2]
slower = [c for c in cells if c["saving_median"] is not None and c["saving_median"] < -0.02]
complete = all(len(c["pairs"]) == 3 for c in cells)
verdict = "speed option kept" if kept_forms and not slower else "null"
w = {}
for sky in SKIES:
    for mg in ("0.8", "0.9"):
        ks = [k for k in wsc if k.startswith(f"{sky}-minres-mgain{mg}")]
        if ks:
            w[f"{sky}-{mg}"] = dict(wall=st.median([wsc[k]["wall_s"] for k in ks]), rss=max(wsc[k]["peak_rss_gb"] for k in ks), n=len(ks))
print("| sky | form | CPU wall | GPU wall | saving (pairs) | major CPU / GPU | host peak GB CPU / GPU | GPU MiB |")
print("| --- | --- | ---: | ---: | --- | --- | --- | ---: |")
for c in cells:
    p = ", ".join(f"{x:+.1%}" for x in c["pairs"])
    fmt = lambda v, f=".2f": "–" if v is None else format(v, f)
    print(f"| {c['sky'].upper()} | {c['form']} | {fmt(c['cpu_wall'])} | {fmt(c['gpu_wall'])} | {fmt(c['saving_median'], '+.1%')} ({p}) | {fmt(c['cpu_major'])} / {fmt(c['gpu_major'])} | {fmt(c['cpu_peak_gb'])} / {fmt(c['gpu_peak_gb'])} | {fmt(c['gpu_dev_mib'], '.0f')} |")
print("WSClean:", json.dumps(w))
print("verdict:", verdict, "complete" if complete else "INCOMPLETE", "slower cells:", [(c["sky"], c["form"]) for c in slower])
Path(sys.argv[1]).write_text(json.dumps(dict(runs=runs, wsclean=wsc, cells=cells, wsclean_cells=w, verdict=verdict, complete=complete), indent=1))
