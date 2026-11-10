"""analyse.py OUT.json : the timing tables and the savings of research/g7-defaults.md (sections 5, 6).

Reads runs/*/timing.json and each run's log (GeMClean's phase line, WSClean's inversion,
prediction and deconvolution times) under $G7_OUT, prints Markdown tables and writes OUT.json.
"""

import json
import os
import re
import statistics
import sys
from pathlib import Path

OUT = Path(os.environ.get("G7_OUT", "D:/rang/outputs/g7-20261109-01"))


def hms(s):
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def phases(arm, d):
    text = (d / "log.txt").read_text(errors="replace")
    out = {}
    if arm in ("WN", "WM"):
        m = re.search(
            r"Inversion: ([\d:.]+), prediction: ([\d:.]+), deconvolution: ([\d:.]+)",
            text,
        )
        if m:
            out = {
                "inversion_s": hms(m[1]),
                "prediction_s": hms(m[2]),
                "deconvolution_s": hms(m[3]),
            }
        out["major_cycles"] = (
            len(
                re.findall(
                    r"Continuing cleaning after inversion/prediction round", text
                )
            )
            + 1
        )
        m = re.search(r"major=([\d.]+)'', minor=([\d.]+)''", text)
        if m:
            out["beam_asec"] = [float(m[1]), float(m[2])]
    else:
        m = re.search(r"\(([\d.]+) s read, ([\d.]+) s weights\)", text)
        if m:
            out["read_s"], out["weights_s"] = float(m[1]), float(m[2])
        m = re.search(r"PSF ([\d.]+) s, FFT", text)
        if m:
            out["psf_s"] = float(m[1])
        m = re.search(
            r"(\d+) components, (\d+) major cycles, (\d+) resyncs, stop (\w+); Q/Q0 ([\d.e+-]+);.*"
            r"minor ([\d.]+) s .*resync ([\d.]+) s, major ([\d.]+) s",
            text,
        )
        if m:
            out.update(
                components=int(m[1]), major_cycles=int(m[2]), resyncs=int(m[3]), stop=m[4],
                q_over_q0=float(m[5]), minor_s=float(m[6]), resync_s=float(m[7]), major_s=float(m[8]),
            )  # fmt: skip
    return out


def load():
    runs = {}
    for t in sorted(OUT.glob("runs/*/timing.json")):
        r = json.loads(t.read_text())
        r["phases"] = phases(r["arm"], t.parent)
        cpu = r.get("user_s", 0.0) + r.get("sys_s", 0.0)
        r["cpu_over_wall"] = cpu / r["wall_s"] if r.get("wall_s") else None
        r["peak_bytes"] = r.get("peak_working_set_bytes", r.get("max_rss_bytes"))
        runs[r["run"]] = r
    return runs


def cells(runs):
    by = {}
    for r in runs.values():
        if r["rc"] == 0:
            by.setdefault((r["arm"], r["j"]), []).append(r)
    return by


def saving(by, arm, j):
    """Median over repeats of (GD - X)/GD, paired by repeat, else against GD's median."""
    gd = {r["rep"]: r["wall_s"] for r in by.get(("GD", j), [])}
    xs = by.get((arm, j), [])
    if not gd or not xs:
        return None, []
    med = statistics.median(gd.values())
    s = [(gd.get(r["rep"], med) - r["wall_s"]) / gd.get(r["rep"], med) for r in xs]
    return statistics.median(s), s


def main():
    runs = load()
    by = cells(runs)
    table = {}
    print(
        "| arm | -j | runs (spoiled) | wall median (range), s | CPU/wall | peak memory GB | major cycles | phases (median) |"
    )
    print("| --- | ---: | --- | --- | ---: | ---: | --- | --- |")
    for (arm, j), rs in sorted(by.items(), key=lambda kv: (-kv[0][1], kv[0][0])):
        walls = [r["wall_s"] for r in rs]
        sp = sum(r["spoiled"] for r in rs)
        peak = (
            statistics.median(
                [r["peak_bytes"] for r in rs if r.get("peak_bytes")] or [float("nan")]
            )
            / 1e9
        )
        cw = statistics.median(
            [r["cpu_over_wall"] for r in rs if r["cpu_over_wall"]] or [float("nan")]
        )
        ph = rs[0]["phases"]
        keys = [k for k in ph if k.endswith("_s")]
        phs = ", ".join(
            f"{k[:-2]} {statistics.median([r['phases'].get(k, float('nan')) for r in rs]):.1f}"
            for k in keys
        )
        table[f"{arm}-j{j}"] = {
            "walls_s": walls, "median_s": statistics.median(walls), "spoiled": sp, "cpu_over_wall": cw,
            "peak_gb": peak, "phases": [r["phases"] for r in rs],
        }  # fmt: skip
        print(
            f"| {arm} | {j} | {len(rs)} ({sp}) | {statistics.median(walls):.1f} ({min(walls):.1f}-{max(walls):.1f}) "
            f"| {cw:.2f} | {peak:.2f} | {ph.get('major_cycles', '')} | {phs} |"
        )
    print()
    print(
        "| candidate | -j 16 saving, median (pairs) | -j 1 saving | peak memory change, GB |"
    )
    print("| --- | --- | --- | --- |")
    savings = {}
    for arm in ("GC", "GB", "GT", "GP", "GX"):
        row = {}
        for j in (16, 1):
            m, s = saving(by, arm, j)
            row[j] = (m, s)
        if all(v[0] is None for v in row.values()):
            continue
        pk = []
        for j in (16, 1):
            a = [r["peak_bytes"] for r in by.get((arm, j), [])]
            g = [r["peak_bytes"] for r in by.get(("GD", j), [])]
            if a and g:
                pk.append(statistics.median(a) / 1e9 - statistics.median(g) / 1e9)
        savings[arm] = {"j16": row[16], "j1": row[1], "peak_change_gb": pk}

        def f(v):
            return (
                "–"
                if v[0] is None
                else f"{100 * v[0]:.1f} % ({', '.join(f'{100 * x:.1f}' for x in v[1])})"
            )

        print(
            f"| {arm} | {f(row[16])} | {f(row[1])} | {', '.join(f'{x:+.2f}' for x in pk)} |"
        )
    Path(sys.argv[1]).write_text(
        json.dumps({"runs": runs, "cells": table, "savings": savings}, indent=1) + "\n"
    )


if __name__ == "__main__":
    main()
