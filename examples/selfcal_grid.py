"""selfcal-defaults (research/selfcal-defaults.md): the frozen selfcal grid on the pilot, held out by channel.

Stages (OUT holds one directory per run; RANG_FLOOR_HELD as in floor4_tests):

    f3 ...          floor3_score.py with the nash paths (G1: copy P, g0, score P, summary)
    base            the four-correlation pilot copy, once (floor3_score's rewrite) into OUT/base
    sets            the scoring sets S_B (held out) and S_A (in sample): prep, hands, thermal
    prepare RUN     OUT/RUN/pilot.ms from the base, channels B flagged; OUT/RUN/config.yaml
    score RUN       every cell of RUN on S_B and S_A
    clean RUN       delete OUT/RUN/pilot.ms
    summary         gates and the frozen rule of section 5

Runs: D (the current default), L60 ... L600, N60 ..., M60 ..., and X (the absorption check,
`--cell` and `--minuvw 400`). `rang-core selfcal OUT/RUN/config.yaml OUT/RUN/pilot.ms --run-dir
OUT/RUN/run` runs between prepare and score.
"""

import argparse
import json
import math
import shutil
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import floor3_score as f3
import floor4_tests as f4  # sets the nash paths
import floor_tests as ft
from rang import core_ms
from rang import core_ms_write as tables

REPO = Path(__file__).resolve().parents[1]
P1_YAML = REPO / "research/results/floor-3/p1.yaml"
CH_B = ft.CHANNELS  # 4, 12, ..., 252: imaging-floor's metric channels, held out
CH_A = ft.CHANNELS - 4  # 0, 8, ..., 248: in sample
FLAGGED_B = np.sort(np.concatenate([CH_B - 1, CH_B, CH_B + 1, CH_B + 2]))
SOLINTS = ["60s", "120s", "300s", "600s"]
# clarification 1 (research/selfcal-defaults.md section 9): `data.memory_limit_gb` by the longest
# solint of a run; p1.yaml's 12 GiB refuses one 600 s interval (13.6 GiB) and the scan-long `inf`
MEMORY_GB = {"600s": 16.0, "inf": 96.0}


def sp(s):
    return {"type": "Sp", "solint": s, "freqint": "inf"}


def sa(s):
    return {"type": "Sa", "solint": s, "freqint": "inf"}


def runs():
    r = {"D": {"rounds": 2, "terms": [{"type": "Sp"}, {"type": "Sa"}]}}
    for s in SOLINTS:
        n = s[:-1]
        r[f"L{n}"] = {"rounds": 4, "terms": [sp(s), sp(s), sp(s), sa(s)]}
        r[f"N{n}"] = {"rounds": 3, "terms": [sp(s), sp(s), sa(s)]}
        r[f"M{n}"] = {"rounds": 2, "terms": [sp(s), sa(s)]}
    return r


def cells_of(run, rounds):
    """(cell name, correction round, model image index) of a run; image R + 1 is the final."""
    if run == "D":
        return [("default", 2, 3)]
    s = run[1:]
    if run.startswith("L"):
        return [
            (f"P1@{s}", 1, 2),
            (f"P2@{s}", 2, 3),
            (f"P3@{s}", 3, 4),
            (f"P3A@{s}", 4, 5),
        ]
    if run.startswith("N"):
        return [(f"P2A@{s}", 3, 4)]
    if run.startswith("M"):
        return [(f"P1A@{s}", 2, 3)]
    if run.startswith("X"):
        return [("X", rounds, rounds + 1)]
    raise ValueError(run)


def cell_cost(name):
    kind, s = name.split("@")
    n = int(kind[1])
    amp = kind.endswith("A")
    return (n + amp, amp, -int(s))


# ---------------------------------------------------------------- stages


def cmd_base(out):
    if (out / "base" / "expand.json").exists():
        return
    f3.cmd_copy(out, "base")


def cmd_prepare(out, run, cell=None, minuvw=0.0):
    import yaml

    q = out / run
    q.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(P1_YAML.read_text())
    if run == "X":
        src = json.loads((out / "summary.json").read_text())["chosen"]
        spec = runs()[src["run"]]
        rounds = src["round"]
        cfg["selfcal"]["rounds"] = rounds
        cfg["selfcal"]["terms"] = spec["terms"][:rounds]
        cfg["selfcal"]["minuvw_m"] = float(minuvw)
        (q / "chosen.json").write_text(json.dumps(src))
    else:
        spec = runs()[run]
        cfg["selfcal"]["rounds"] = spec["rounds"]
        cfg["selfcal"]["terms"] = spec["terms"]
    sol = {t.get("solint", "inf") for t in cfg["selfcal"]["terms"]}
    for k, gb in MEMORY_GB.items():
        if k in sol:
            cfg["data"]["memory_limit_gb"] = max(cfg["data"]["memory_limit_gb"], gb)
    (q / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    ms = q / "pilot.ms"
    if (q / "holdout.json").exists():
        return
    shutil.rmtree(ms, ignore_errors=True)
    s0 = time.perf_counter()
    shutil.copytree(out / "base" / "pilot.ms", ms)
    with core_ms.open_table(str(ms)) as t:
        n = int(t.nrows)
    with tables.table(str(ms), readonly=False) as o:
        for r0 in range(0, n, ft.ROWS):
            k = min(ft.ROWS, n - r0)
            f = np.array(o.getcol("FLAG", r0, k), bool)
            f[:, FLAGGED_B, :] = True
            o.putcol("FLAG", f, r0, k)
    ft.wjson(
        q / "holdout.json",
        {"flagged_channels": FLAGGED_B.tolist(), "seconds": time.perf_counter() - s0},
    )


def set_dir(out, name):
    return out / f"set{name}"


def cmd_sets(out):
    for name, ch in (("B", CH_B), ("A", CH_A)):
        q = set_dir(out, name)
        if (q / "thermal.json").exists():
            continue
        ft.CHANNELS = ch
        ft.MS_A = ft.HELD / "cal2.ms"
        ft.prep(q)
        d = ft.Data(q)
        f4.hands_prep(q / "hands", ch)
        T = ft.floor(d, ft.grid(d, d.noise(ft.NOISE_SEED)))
        ft.wjson(
            q / "thermal.json",
            {"T": T, "channels": ch.tolist(), "active": d.meta["active"]},
        )
        ft.log("set", name, T)
    ft.CHANNELS = CH_B


def score_cell(d, h, T, store, name, model_mv, tb):
    g, valid, _gt = f4.store_gains(store, name)
    xx, yy, f, _ok = f4.apply_store(h, g, valid, tb, d.a1, d.a2)
    v, w = f4.stokes_from_hands(xx, yy, h["w"], f, h["rows_ok"])
    gw = np.where(w > 0, d.gw, 0.0).astype(np.float32)
    newly = 1 - np.count_nonzero(gw) / np.count_nonzero(d.gw)
    F = f4.floor_with(d, v, model_mv, gw)
    sig = float(np.median(np.abs(g[valid])))
    Tr = (
        T * math.sqrt(np.count_nonzero(d.gw) / np.count_nonzero(gw))
        if newly > 0.01
        else T
    )
    return {
        "F": F,
        "flux_scale": sig,
        "F_norm": F * sig**2,
        "newly_flagged": newly,
        "T_used": Tr,
    }


def cmd_score(out, run):
    q = out / run
    fn = q / "score.json"
    if fn.exists():
        return
    s = json.loads((q / "run/selfcal/summary.json").read_text())
    fld = s["fields"][0]
    rounds = fld["rounds"]
    R = len(rounds)

    def model_path(k):
        if k == R + 1:
            (p,) = sorted(
                Path(rounds[-1]["store"])
                .parent.parent.joinpath("final")
                .glob("*-model.fits")
            )
        else:
            (p,) = sorted(Path(rounds[k - 1]["store"]).parent.glob("*-model.fits"))
        return p

    res = {
        "run": run,
        "config": (q / "config.yaml").read_text(),
        "gemclean_sha256": s["gemclean_sha256"],
        "rounds": [
            {
                "term": r["term"],
                "solve": {
                    k: r["solve"].get(k)
                    for k in (
                        "iterations",
                        "converged_fraction",
                        "flagged_fraction",
                        "clipped",
                        "time_bins",
                        "wall_seconds",
                    )
                },
                "image_clean": r["image"]["clean"],
                "image_wall_s": r["image"]["wall_seconds"],
                "model_sha256": {
                    k: v
                    for k, v in r["image"]["files"].items()
                    if k.endswith("-model.fits")
                },
                "store": r["store"],
            }
            for r in rounds
        ],
        "final_clean": fld["final_image"]["clean"],
        "cells": {},
    }
    cells = cells_of(run, R)
    for setname in ("B", "A"):
        qs = set_dir(out, setname)
        d = ft.Data(qs)
        h = f4.hands_prep(qs / "hands", None)
        T = json.loads((qs / "thermal.json").read_text())["T"]
        mv1 = f4.model_vis(d, model_path(1))
        F0 = f4.floor_with(d, d.vis, mv1)
        res[f"F0_{setname}"] = F0
        res[f"T_{setname}"] = T
        for cname, kc, km in cells:
            term = rounds[kc - 1]["term"]
            tb = f4.row_bins(h, term.get("solint", "inf"))
            mv = f4.model_vis(d, model_path(km))
            r = score_cell(
                d,
                h,
                T,
                rounds[kc - 1]["store"],
                term.get("name") or term["type"],
                mv,
                tb,
            )
            P0 = F0**2 - T**2
            r["P"] = r["F_norm"] ** 2 - r["T_used"] ** 2
            r["D"] = (P0 - r["P"]) / P0
            res["cells"].setdefault(cname, {"round": kc, "model_image": km})[
                setname
            ] = r
            ft.log(
                "cell", run, cname, setname, round(r["F"] * 1e6, 2), round(r["D"], 4)
            )
            del mv
        del d, h, mv1
    for cname, kc, _km in cells:
        c = res["cells"][cname]
        c["health"] = all(
            (rr["solve"]["converged_fraction"] or 0) >= 0.9
            and (rr["solve"]["flagged_fraction"] or 0) <= 0.05
            for rr in res["rounds"][:kc]
        )
        c["D_ho"] = c["B"]["D"]
        c["D_in"] = c["A"]["D"]
        c["gap"] = c["D_in"] - c["D_ho"]
    ft.wjson(fn, res)


def cmd_summary(out, f4out):
    scores = {
        p.parent.name: json.loads(p.read_text())
        for p in sorted(out.glob("*/score.json"))
    }
    res = {"runs": sorted(scores)}
    x = json.loads((Path(f4out) / "x.json").read_text())
    res["HB1"] = {"rel": x["X2"]["HB1_rel"], "pass": x["X2"]["HB1_pass"]}
    TB = json.loads((set_dir(out, "B") / "thermal.json").read_text())["T"]
    res["HB2"] = {
        "T_B": TB,
        "rel": TB / f4.T_ARCH - 1,
        "pass": abs(TB / f4.T_ARCH - 1) <= 0.005,
    }
    # round-1 models identical across runs (one computation)
    m1 = {
        r: next(iter(sc["rounds"][0]["model_sha256"].values()))
        for r, sc in scores.items()
    }
    res["round1_model_identical"] = len(set(m1.values())) == 1
    # determinism: earlier rounds of N and M against L
    det = {}
    for r, sc in scores.items():
        if r[0] in "NM":
            L = scores.get("L" + r[1:])
            if L is None:
                continue
            same = []
            for k in range(len(sc["rounds"]) - 1):
                ga = f4.store_gains(sc["rounds"][k]["store"], "Sp")[0]
                gb = f4.store_gains(L["rounds"][k]["store"], "Sp")[0]
                same.append(bool(np.array_equal(ga, gb)))
            det[r] = same
    res["determinism"] = det
    cells = {}
    for r, sc in scores.items():
        if r == "X":
            continue
        for cn, c in sc["cells"].items():
            cells[cn] = {
                "run": r,
                "round": c["round"],
                "D_ho": c["D_ho"],
                "D_in": c["D_in"],
                "gap": c["gap"],
                "health": c["health"],
                "F_ho_uJy": c["B"]["F"] * 1e6,
                "F_in_uJy": c["A"]["F"] * 1e6,
                "flux_scale": c["B"]["flux_scale"],
                "newly_flagged": c["B"]["newly_flagged"],
            }
    res["cells"] = cells
    gates = res["HB1"]["pass"] and res["HB2"]["pass"]
    elig = {
        k: v
        for k, v in cells.items()
        if k != "default" and v["health"] and v["gap"] <= 0.05
    }
    res["eligible"] = sorted(elig)
    if not gates or not elig:
        res["outcome"] = "void" if not gates else "no eligible cell: default unchanged"
        ft.wjson(out / "summary.json", res)
        print(json.dumps(res, indent=1, default=float))
        return
    Dstar = max(v["D_ho"] for v in elig.values())
    cand = [k for k, v in elig.items() if v["D_ho"] >= Dstar - 0.02]
    chosen = min(cand, key=cell_cost)
    res["D_star"] = Dstar
    res["candidates"] = sorted(cand, key=cell_cost)
    res["chosen"] = {"cell": chosen, **elig[chosen]}
    dflt = cells.get("default")
    res["baseline"] = dflt
    if dflt is not None:
        d_ok = dflt["health"] and dflt["gap"] <= 0.05
        beats = elig[chosen]["D_ho"] >= dflt["D_ho"] + 0.05
        repl = (not d_ok) and elig[chosen]["D_ho"] >= dflt["D_ho"] - 0.02
        res["beats_baseline"] = beats
        res["baseline_eligible"] = d_ok
        res["change_if_check_passes"] = beats or repl
    res["outcome"] = "pending: the absorption check (run X) has not run"
    if "X" in scores:
        xc = next(iter(scores["X"]["cells"].values()))
        res["absorption_check"] = {
            "D_ho_minuvw400": xc["D_ho"],
            "D_ho_chosen": elig[chosen]["D_ho"],
            "pass": xc["D_ho"] >= elig[chosen]["D_ho"] - 0.05,
            "health": xc["health"],
        }
        if res.get("change_if_check_passes") and res["absorption_check"]["pass"]:
            res["outcome"] = f"change the default to {chosen}"
        elif res.get("change_if_check_passes"):
            res["outcome"] = "absorption suspected: default unchanged"
        else:
            res["outcome"] = (
                "default unchanged: the chosen cell does not beat the baseline by the margin"
            )
    ft.wjson(out / "summary.json", res)
    print(
        json.dumps(
            {k: v for k, v in res.items() if k != "cells"}, indent=1, default=float
        )
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "f3":
        return f3.main(argv[1:])
    p = argparse.ArgumentParser()
    p.add_argument(
        "stage", choices=["base", "sets", "prepare", "score", "clean", "summary"]
    )
    p.add_argument("run", nargs="?")
    p.add_argument("--out", required=True)
    p.add_argument("--minuvw", type=float, default=0.0)
    p.add_argument("--f4out", default=None)
    a = p.parse_args(argv)
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    if a.stage == "base":
        cmd_base(out)
    elif a.stage == "sets":
        cmd_sets(out)
    elif a.stage == "prepare":
        cmd_prepare(out, a.run, minuvw=a.minuvw)
    elif a.stage == "score":
        cmd_score(out, a.run)
    elif a.stage == "clean":
        shutil.rmtree(out / a.run / "pilot.ms", ignore_errors=True)
    elif a.stage == "summary":
        cmd_summary(out, a.f4out)
    ft.log("stage", a.stage, a.run, "wall_s", round(time.perf_counter() - s0, 1))


if __name__ == "__main__":
    sys.exit(main())
