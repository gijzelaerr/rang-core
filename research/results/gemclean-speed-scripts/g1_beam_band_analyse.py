"""Apply the -beam-band rule of research/gemclean-speed.md to a G1 run.

Usage: g1_beam_band_analyse.py OUT_DIR ARCHIVE.json
Reads OUT_DIR/{runs.tsv,logs,load,scores,images,sha256.txt}; writes the archive
and prints the tables and the verdict. The thresholds are those committed with
the rule, before the run.
"""

import json
import re
import statistics as st
import sys
from pathlib import Path

import numpy as np
from rang.core_imaging import read_fits

SAVING_BAR = 0.10
MIN_POSITIVE_ALLOWANCE = 1  # pairs in a cell that may fail to save
SLOWER_LIMIT = -0.02
MIN_CLEAN_PAIRS = 6
THRESHOLD_JY = 1e-4
BOUNDS = {
    "image_rms_over_sigma": 0.1,
    "image_linf_jy": THRESHOLD_JY,
    "q_over_q_truth": 1e-3,
    "false_flux_abs_jy": 1e-3,
    "recovery_flux_weighted": 1e-3,
    "exact_residual_inner_peak_jy": 0.1 * THRESHOLD_JY,
}
TIMED = ("s1", "h2", "h3")
ALL = ("s1", "s2", "s3", "h1", "h2", "h3", "h4")


def parse_log(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    rec = {}
    m = re.search(
        r"(\d+) components, (\d+) major cycles, (\d+) resyncs.*?resync ([\d.]+) s, major ([\d.]+) s",
        text,
    )
    rec["components"], rec["cycles"], rec["resyncs"] = map(int, m.group(1, 2, 3))
    rec["resync_s"], rec["major_s"] = map(float, m.group(4, 5))
    m = re.search(r"(\d+) of (\d+) spectrum columns, (\S+) left out", text)
    rec["columns"] = [int(m.group(1)), int(m.group(2))]
    rec["dropped_rms"] = float(m.group(3))
    m = re.search(r" wall ([\d.]+) user ([\d.]+) sys ([\d.]+) rss_kb (\d+)", text)
    rec["wall"], rec["user"], rec["sys"] = map(float, m.group(1, 2, 3))
    rec["rss_kb"] = int(m.group(4))
    return rec


def load_runs(out):
    runs = {}
    for line in (out / "runs.tsv").read_text(encoding="utf-8").splitlines():
        name, sky, j, flag, rep, spoiled = line.split("\t")[:6]
        rec = parse_log(out / "logs" / f"{name}.log")
        load = (out / "load" / f"{name}.txt").read_text(encoding="utf-8").splitlines()
        busy = (out / "load" / f"{name}.busy.txt").read_text(encoding="utf-8")
        rec.update(
            name=name,
            sky=sky,
            j=int(j),
            flag=flag,
            rep=rep,
            spoiled=int(spoiled),
            load1_before=float(load[0].split()[0]),
            load1_after=float(load[1].split()[0]),
            busy=[x for x in busy.splitlines() if x and not x.startswith("==")],
        )
        runs[name] = rec
    return runs


def summary(values):
    return {
        "median": st.median(values),
        "min": min(values),
        "max": max(values),
        "n": len(values),
    }


def cell(runs, sky, j):
    pairs = []
    reps = sorted(
        {r["rep"] for r in runs.values() if r["sky"] == sky and r["j"] == j},
        key=lambda x: (x[0] == "x", int(x.lstrip("x"))),
    )
    for rep in reps:
        off = runs.get(f"{sky}-j{j}-off-r{rep}")
        on = runs.get(f"{sky}-j{j}-on-r{rep}")
        if off and on:
            pairs.append(
                {
                    "rep": rep,
                    "off": off["wall"],
                    "on": on["wall"],
                    "saving": (off["wall"] - on["wall"]) / off["wall"],
                    "spoiled": bool(off["spoiled"] or on["spoiled"]),
                    "resync_off": off["resync_s"],
                    "resync_on": on["resync_s"],
                    "major_off": off["major_s"],
                    "major_on": on["major_s"],
                    "cycles": [off["cycles"], on["cycles"]],
                    "resyncs": [off["resyncs"], on["resyncs"]],
                    "load1_before": [off["load1_before"], on["load1_before"]],
                    "load1_after": [off["load1_after"], on["load1_after"]],
                }
            )
    clean = [p for p in pairs if not p["spoiled"]]
    used = clean if len(clean) >= MIN_CLEAN_PAIRS else pairs

    def stats(ps):
        return {
            "pairs": len(ps),
            "off_wall": summary([p["off"] for p in ps]),
            "on_wall": summary([p["on"] for p in ps]),
            "saving": summary([p["saving"] for p in ps]),
            "pairs_saving": sum(p["saving"] > 0 for p in ps),
            "off_resync": summary([p["resync_off"] for p in ps]),
            "on_resync": summary([p["resync_on"] for p in ps]),
            "off_major": summary([p["major_off"] for p in ps]),
            "on_major": summary([p["major_on"] for p in ps]),
        }

    return {
        "sky": sky,
        "j": j,
        "decision_pairs": "clean" if used is clean else "all (too few clean)",
        "clean": stats(used),
        "all": stats(pairs),
        "spoiled_pairs": len(pairs) - len(clean),
        "pairs": pairs,
    }


def inner(a):
    n = a.shape[-1]
    lo, hi = n // 6, n - n // 6
    return a[..., lo:hi, lo:hi]


def recovery(job):
    return job["recovery_all"]["flux_weighted"]


def image_row(out, sky, j):
    scores = json.loads((out / "scores" / f"{sky}.json").read_text(encoding="utf-8"))
    off = scores["jobs"][f"{sky}-j{j}-off-r1"]
    on = scores["jobs"][f"{sky}-j{j}-on-r1"]
    sigma = scores["briggs_noise"]
    row = {"sky": sky, "j": j, "sigma_jy": sigma}
    for kind in ("image", "residual", "model"):
        a, _ = read_fits(out / "images" / f"{sky}-j{j}-off-r1-{kind}.fits")
        b, _ = read_fits(out / "images" / f"{sky}-j{j}-on-r1-{kind}.fits")
        d = inner(np.asarray(b, dtype=float) - np.asarray(a, dtype=float))
        row[f"{kind}_rms_jy"] = float(np.sqrt(np.mean(d**2)))
        row[f"{kind}_linf_jy"] = float(np.abs(d).max())
    row["deltas"] = {
        "image_rms_over_sigma": row["image_rms_jy"] / sigma,
        "image_linf_jy": row["image_linf_jy"],
        "q_over_q_truth": abs(on["q_over_q_truth"] - off["q_over_q_truth"]),
        "false_flux_abs_jy": abs(on["false_flux_abs"] - off["false_flux_abs"]),
        "recovery_flux_weighted": abs(recovery(on) - recovery(off)),
        "exact_residual_inner_peak_jy": abs(
            on["exact_residual_inner_peak_abs"] - off["exact_residual_inner_peak_abs"]
        ),
    }
    row["off"] = {
        "q_over_q_truth": off["q_over_q_truth"],
        "false_flux_abs": off["false_flux_abs"],
        "exact_residual_inner_peak_abs": off["exact_residual_inner_peak_abs"],
    }
    row["passes"] = all(row["deltas"][k] <= v for k, v in BOUNDS.items())
    return row


def determinism(out):
    groups = {}
    for line in (out / "sha256.txt").read_text(encoding="utf-8").splitlines():
        sha, name = line.split()
        m = re.fullmatch(r"(\w+)-j(\d+)-(on|off)-r(\w+)-(\w+)\.fits", name)
        if m and m.group(4) != "gate":
            sky, j, flag, _rep, kind = m.groups()
            groups.setdefault((sky, flag, kind), {}).setdefault(j, set()).add(sha)
    across_repeats, across_threads = [], []
    for (sky, flag, kind), byj in groups.items():
        for j, shas in byj.items():
            if len(shas) != 1:
                across_repeats.append(f"{sky} {flag} {kind} -j {j}")
        if len(byj) == 2 and len(set.union(*byj.values())) != 1:
            across_threads.append(f"{sky} {flag} {kind}")
    return {
        "differs_across_repeats": sorted(across_repeats),
        "differs_between_j1_and_j16": sorted(across_threads),
    }


def main():
    out, archive = Path(sys.argv[1]), Path(sys.argv[2])
    runs = load_runs(out)
    cells = [cell(runs, s, j) for s in TIMED for j in (16, 1)]
    rows = [image_row(out, s, 16) for s in ALL]
    rows += [image_row(out, s, 1) for s in TIMED]

    print("| Sky | -j | off median (range) | on median (range) | saving median (range) | pairs saving | spoiled |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for c in cells:
        d = c["clean"]
        print(
            f"| {c['sky'].upper()} | {c['j']} | {d['off_wall']['median']:.2f} ({d['off_wall']['min']:.2f}-{d['off_wall']['max']:.2f})"
            f" | {d['on_wall']['median']:.2f} ({d['on_wall']['min']:.2f}-{d['on_wall']['max']:.2f})"
            f" | {100 * d['saving']['median']:.1f} % ({100 * d['saving']['min']:.1f} to {100 * d['saving']['max']:.1f})"
            f" | {d['pairs_saving']} of {d['pairs']} | {c['spoiled_pairs']} |"
        )
    print()
    print("| Sky | -j | resync off / on | major off / on | cycles off, on | resyncs off, on | all pairs saving |")
    print("| --- | ---: | ---: | ---: | --- | --- | ---: |")
    for c in cells:
        d = c["clean"]
        print(
            f"| {c['sky'].upper()} | {c['j']} | {d['off_resync']['median']:.2f} / {d['on_resync']['median']:.2f}"
            f" | {d['off_major']['median']:.2f} / {d['on_major']['median']:.2f}"
            f" | {c['pairs'][0]['cycles']} | {c['pairs'][0]['resyncs']}"
            f" | {100 * c['all']['saving']['median']:.1f} % ({c['all']['pairs']}) |"
        )
    print()
    print("| Sky | -j | image rms/sigma | image Linf uJy | dQ/Qtruth | dfalse mJy | drecovery | dpeak uJy | pass |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for r in rows:
        d = r["deltas"]
        print(
            f"| {r['sky'].upper()} | {r['j']} | {d['image_rms_over_sigma']:.3g} | {1e6 * d['image_linf_jy']:.3g}"
            f" | {d['q_over_q_truth']:.2e} | {1e3 * d['false_flux_abs_jy']:.3g}"
            f" | {d['recovery_flux_weighted']:.2e} | {1e6 * d['exact_residual_inner_peak_jy']:.3g} | {r['passes']} |"
        )

    speed = {}
    for j in (16, 1):
        passing = [
            c["sky"]
            for c in cells
            if c["j"] == j
            and c["clean"]["saving"]["median"] >= SAVING_BAR
            and c["clean"]["pairs_saving"] >= c["clean"]["pairs"] - MIN_POSITIVE_ALLOWANCE
        ]
        speed[j] = passing
    saving_ok = any(len(v) >= 2 for v in speed.values())
    no_regression = all(c["clean"]["saving"]["median"] > SLOWER_LIMIT for c in cells)
    images_ok = all(r["passes"] for r in rows)
    keep = saving_ok and no_regression and images_ok
    verdict = {
        "skies_clearing_the_bar": {str(k): v for k, v in speed.items()},
        "saving_condition": saving_ok,
        "no_regression_condition": no_regression,
        "image_condition": images_ok,
        "keep": keep,
    }
    det = determinism(out)
    print()
    print(json.dumps(verdict, indent=1))
    print(json.dumps(det, indent=1))
    archive.write_text(
        json.dumps(
            {
                "provenance": (out / "provenance.txt").read_text(encoding="utf-8").splitlines(),
                "rule": {
                    "saving_bar": SAVING_BAR,
                    "pairs_that_may_fail": MIN_POSITIVE_ALLOWANCE,
                    "slower_limit": SLOWER_LIMIT,
                    "min_clean_pairs": MIN_CLEAN_PAIRS,
                    "image_bounds": BOUNDS,
                },
                "settings": "-size N N -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -abs-threshold 0.0001 -data-column DATA -field 0 -single -wgridder-accuracy 1e-4 [-beam-band]",
                "cells": cells,
                "images": rows,
                "determinism": det,
                "verdict": verdict,
                "runs": list(runs.values()),
            },
            indent=0,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
