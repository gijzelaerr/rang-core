# SPDX-License-Identifier: MIT
"""Amendment 9.4 of research/gpu-grid.md: read the timing session's runs, apply the clean
rule and section 5's saving rule, hash the timed FITS against Gate 2's.
Usage: session_analyse.py OUT_JSON"""

import hashlib
import json
import re
import statistics as st
import sys
from pathlib import Path

OUT = Path("D:/rang/outputs/20261116-gpu-grid")
T = OUT / "timing-20261117b"
SKIES, FORMS = ("s1", "h2", "h3"), ("coarse", "fine")


def phases(log):
    t = log.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"(\d+) components, (\d+) major cycles.*?minor ([\d.]+) s.*?resync ([\d.]+) s, major ([\d.]+) s", t
    )
    g = re.search(
        r"gpu: .*setup ([\d.]+) s, host ([\d.]+) s, upload ([\d.]+) s, compute ([\d.]+) s, "
        r"download ([\d.]+) s; (\d+) MiB",
        t,
    )
    psf = re.search(r"PSF ([\d.]+) s", t)
    d = {
        "components": int(m.group(1)),
        "cycles": int(m.group(2)),
        "minor_s": float(m.group(3)),
        "resync_s": float(m.group(4)),
        "major_s": float(m.group(5)),
        "psf_s": float(psf.group(1)) if psf else None,
    }
    if g:
        setup, host, up, comp, down = (float(g.group(i)) for i in range(1, 6))
        d.update(
            gpu_setup_s=setup, gpu_host_s=host, gpu_upload_s=up, gpu_compute_s=comp,
            gpu_download_s=down, gpu_device_mib=int(g.group(6)),
            gpu_share_of_major=(host + up + comp + down) / d["major_s"],
            compute_share_of_major=comp / d["major_s"],
        )
    return d


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def reference(sky, form, arm):
    d = OUT / ("base" if arm == "cpu" else "gate2/gpu")
    return d, f"{sky}-{form}"


runs, wsc = {}, {}
for f in sorted(T.glob("*-r[0-9].json")):
    r = json.loads(f.read_text())
    name = f.stem
    if "minres" in name:
        wsc[name] = r
        continue
    sky, form, arm, rep = name.split("-")
    rec = {
        "sky": sky, "form": form, "arm": arm, "rep": rep, "wall_s": r["wall_s"], "rc": r["rc"],
        "clean": r.get("clean"), "unclean": r.get("unclean"), "other_cores": r.get("other_cores"),
        "cpu_s": r["user_s"] + r["sys_s"], "peak_ws_gb": r["peak_working_set_bytes"] / 1e9,
        "gpu_before_mib": r["gpu_used_before_mib"], "gpu_peak_mib": r["gpu_peak_mib"],
    }
    rec.update(phases(T / f"{name}.log"))
    d, stem = reference(sky, form, arm)
    rec["fits_equal_gate2"] = {
        k: sha(T / "out" / f"{name}-{k}.fits") == sha(d / f"{stem}-{k}.fits") for k in ("model", "residual", "image")
    }
    runs[name] = rec


def med(xs):
    return st.median(xs) if xs else None


cells = []
for sky in (*SKIES, "pilot"):
    for form in FORMS:
        keys = {a: sorted(k for k in runs if k.startswith(f"{sky}-{form}-{a}-")) for a in ("cpu", "gpu")}
        if not keys["cpu"] and not keys["gpu"]:
            continue
        pairs, pairs_all = [], []
        for rep in ("r1", "r2", "r3"):
            c, g = runs.get(f"{sky}-{form}-cpu-{rep}"), runs.get(f"{sky}-{form}-gpu-{rep}")
            if c and g:
                s = (c["wall_s"] - g["wall_s"]) / c["wall_s"]
                pairs_all.append(s)
                if c["clean"] and g["clean"]:
                    pairs.append(s)
        clean = {a: [runs[k] for k in keys[a] if runs[k]["clean"]] for a in keys}
        cell = {
            "sky": sky, "form": form, "pairs_clean": pairs, "pairs_all": pairs_all,
            "saving_median": med(pairs) if len(pairs) >= 2 or sky == "pilot" else None,
            "measured": len(pairs) >= 2 or (sky == "pilot" and len(pairs) == 1),
        }
        for a in ("cpu", "gpu"):
            rs = clean[a]
            cell[f"{a}_wall"] = med([r["wall_s"] for r in rs])
            cell[f"{a}_major"] = med([r["major_s"] for r in rs])
            cell[f"{a}_cycles"] = sorted({r["cycles"] for r in rs})
            cell[f"{a}_peak_gb"] = max([r["peak_ws_gb"] for r in rs], default=None)
            cell[f"{a}_fits_equal_gate2"] = all(all(r["fits_equal_gate2"].values()) for r in rs) if rs else None
        g = clean["gpu"]
        cell["gpu_share_of_major"] = med([r["gpu_share_of_major"] for r in g if "gpu_share_of_major" in r])
        cell["compute_share_of_major"] = med([r["compute_share_of_major"] for r in g if "compute_share_of_major" in r])
        cell["gpu_device_mib"] = max([r.get("gpu_device_mib", 0) for r in g], default=None)
        cells.append(cell)

sav = {(c["sky"], c["form"]): c["saving_median"] for c in cells}
kept_forms = [f for f in FORMS if sum(1 for s in SKIES if (sav.get((s, f)) or -1) >= 0.10) >= 2]
slower = [(c["sky"], c["form"]) for c in cells if c["sky"] != "pilot" and c["saving_median"] is not None
          and c["saving_median"] < -0.02]
complete = all(c["measured"] for c in cells if c["sky"] != "pilot")
reading = "speed option kept" if kept_forms and not slower and complete else "null"

w = {}
for sky in SKIES:
    for mg in ("0.8", "0.9"):
        rs = [wsc[k] for k in wsc if k.startswith(f"{sky}-minres-mgain{mg}-")]
        cl = [r for r in rs if r.get("clean")]
        w[f"{sky}-{mg}"] = {
            "wall": med([r["wall_s"] for r in cl]), "walls_all": [round(r["wall_s"], 2) for r in rs],
            "n_clean": len(cl), "n": len(rs), "rss_gb": max([r["peak_rss_gb"] for r in rs], default=None),
        }

fmt = lambda v, f=".2f": "–" if v is None else format(v, f)  # noqa: E731
print("| sky | form | CPU wall | GPU wall | saving, median (clean pairs) | major CPU / GPU | GPU share of major (compute) | cycles CPU / GPU | host GB CPU / GPU | FITS = Gate 2 |")
print("| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- |")
for c in cells:
    p = ", ".join(f"{x:+.1%}" for x in c["pairs_all"])
    print(
        f"| {c['sky'].upper()} | {c['form']} | {fmt(c['cpu_wall'])} | {fmt(c['gpu_wall'])} | "
        f"{fmt(c['saving_median'], '+.1%')} ({len(c['pairs_clean'])} of {len(c['pairs_all'])}: {p}) | "
        f"{fmt(c['cpu_major'])} / {fmt(c['gpu_major'])} | {fmt(c['gpu_share_of_major'], '.0%')} "
        f"({fmt(c['compute_share_of_major'], '.0%')}) | {c['cpu_cycles']} / {c['gpu_cycles']} | "
        f"{fmt(c['cpu_peak_gb'])} / {fmt(c['gpu_peak_gb'])} | {c['cpu_fits_equal_gate2']} / {c['gpu_fits_equal_gate2']} |"
    )
print("WSClean:", json.dumps(w))
unclean = {k: v["unclean"] for k, v in {**runs, **wsc}.items() if not v.get("clean")}
print("unclean:", json.dumps(unclean))
print("other cores max:", max((v.get("other_cores") or 0) for v in {**runs, **wsc}.values()) if runs else None)
print("reading:", reading, "complete" if complete else "INCOMPLETE", "kept forms:", kept_forms, "slower:", slower)
Path(sys.argv[1]).write_text(json.dumps(
    {"runs": runs, "wsclean": wsc, "cells": cells, "wsclean_cells": w, "reading": reading,
     "complete": complete, "unclean": unclean}, indent=1))
