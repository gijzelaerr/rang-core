"""F5 Stage 5: the held-out sets, once (research/f5-flagger.md, sections 8 and
10), on nash, in shards.

Usage:
  python examples/f5_heldout.py real RUN --set luno:MAIN_0 --method M.json [--data-root R] [--ao-sif S]
  python examples/f5_heldout.py sim RUN --class calibrator --method M.json [--data-root R]
  python examples/f5_heldout.py validate RUN --class calibrator --method M.json  (validation dry run)

M.json (Stage 4's record): {"weights": path to weights.npz, "tau": t, "kappa": k or null,
"level": L, "degree": d, "class": c}. Each case is one shard,
RUN/<set>/<case>.json with a `.sha256`; a rerun skips finished shards. Arms:
T, A (uninjected only), N (W3), N5, W4 (when kappa), the method, N4 (F4's seed 2
at tau -1.0, reported). Cases: uninjected (R3, R4, R5, W3 subset check), R1
(F1's four morphologies, seeds 19-21), R2 (H1-H4n, seeds 31-33), G-perm
(seeds 20265201-03), G-drop (k = 1, 4, 8; seeds 20265301-03), G-sub (core16,
outer32: uninjected and R1), G-chan (4x averaging: uninjected and R1).
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from rang import f2flag as ff
from rang import f2flag_sim as fs
from rang import f3flag as f3
from rang import f3net
from rang import f4flag as f4
from rang import f5flag as f5

N4_WEIGHTS = "outputs/f4-20261111-08-train-calibrator/seed-2/weights.npz"
N4_TAU = -1.0
GPERM_SEEDS = (20265201, 20265202, 20265203)
GDROP_SEEDS = (20265301, 20265302, 20265303)
S3_SEEDS = (61, 62, 63)
S3_MIN = 1000


class Method:
    def __init__(self, path, n4_root=None):
        m = json.loads(Path(path).read_text())
        self.rec = m
        self.w = np.asarray(np.load(m["weights"])["flat"], np.float32)
        self.tau, self.kappa = float(m["tau"]), m.get("kappa")
        self.level, self.degree = int(m["level"]), int(m["degree"])
        self.n4 = None
        if n4_root is not None and m.get("class") == "calibrator":
            p = Path(n4_root) / N4_WEIGHTS
            if p.exists():
                self.n4 = f3net.flat_weights(f3net.load_params(p))

    def arms(self, scan, w3, data=None):
        logit, anom = f5.rust_logits_anomaly(
            scan, w3, self.w, self.level, self.degree, data
        )
        out = {"N": w3, "N5": w3 | (logit > self.tau)}
        if self.kappa is not None:
            with np.errstate(invalid="ignore"):
                out["W4"] = w3 | (anom > self.kappa)
            out["method"] = out["N5"] | out["W4"]
        else:
            out["method"] = out["N5"]
        if self.n4 is not None:
            out["N4"] = f4.n4_flags(scan, w3, self.n4, N4_TAU, data)[0]
        return out, logit


def sha_text(s):
    return hashlib.sha256(s.encode()).hexdigest()


def shard(run, name, fn):
    p = run / f"{name}.json"
    s = p.with_suffix(".sha256")
    if p.exists() and s.exists() and s.read_text().strip() == sha_text(p.read_text()):
        return json.loads(p.read_text())
    t0 = time.perf_counter()
    rec = fn()
    rec["seconds"] = time.perf_counter() - t0
    txt = json.dumps(rec, indent=1)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(txt)
    tmp.replace(p)
    s.write_text(sha_text(txt))
    print(json.dumps({"case": name, "seconds": rec["seconds"]}), flush=True)
    return rec


def hits(flags, rows, chans):
    return int(flags[rows, chans].sum())


def r1_record(scan, w3, method, cases, sets_t=None):
    """Recall per arm of the listed (kind, morphology, seed) cases."""
    eligible = ~w3
    sigma = f3.baseline_sigma(scan, eligible)
    out = []
    for kind, m, s in cases:
        if kind == "r1":
            data, rows, chans = f3.r1_case(scan, eligible, sigma, m, s)
        else:
            data, rows, chans = f5.r2_case(scan, eligible, sigma, m, s)
        arms, _ = method.arms(scan, w3, data)
        arms["T"] = f3.t_flags(scan, data)
        c = {"kind": kind, "morphology": m, "seed": s, "cells": len(rows)}
        for a, fl in arms.items():
            c[a] = hits(fl, rows, chans)
        out.append(c)
    return out


def uninjected(scan, w3, method, a_flag=None, s_rows=None):
    eligible = ~w3
    arms, logit = method.arms(scan, w3)
    arms["T"] = f3.t_flags(scan)
    if a_flag is not None:
        arms["A"] = a_flag
    rec = {"eligible": int(eligible.sum()), "w3_not_in_T": int((w3 & ~arms["T"]).sum())}
    added = {a: fl & eligible for a, fl in arms.items()}
    rec["added"] = {a: int(v.sum()) for a, v in added.items()}
    rec["J_T"] = {a: f3.jaccard(v, added["T"]) for a, v in added.items() if a != "T"}
    if a_flag is not None and s_rows is not None:
        strong = f4.strong_consensus(arms["T"], a_flag, eligible, s_rows)
        rec["strong_cells"] = int(strong.sum())
        rec["R5"] = {
            a: float((fl & strong).sum() / strong.sum()) if strong.any() else None
            for a, fl in arms.items()
        }
    return rec, arms, logit


def real(a):
    run = Path(a.run) / a.set.replace(":", "-")
    run.mkdir(parents=True, exist_ok=True)
    method = Method(a.method, a.data_root)
    if a.set.startswith("reserved:"):
        # Amendment 3: N5-ph's held-out groups, read once.
        f5.RESERVED_FETCH = Path(a.reserved_fetch)
        full = f5.load_reserved(a.set.partition(":")[2], heldout=True)
    else:
        full = f5.load(a.set, heldout=not a.validation)
    w3 = f3.w3_flags(full)
    s_rows = f4.strength_rows(full, w3)
    a_dir = run / "aoflag"

    def un():
        a_flag, rec_a = f5.a_flags(full, w3, a_dir / "clean")
        np.save(run / "A.npy", a_flag)
        rec, _, _ = uninjected(full, w3, method, a_flag, s_rows)
        rec["A_record"] = rec_a
        if rec["w3_not_in_T"]:
            rec["stop"] = "W3 is not a subset of T (section 12, Stage 5)"
        return rec

    base = shard(run, "uninjected", un)
    if base.get("stop"):
        raise SystemExit(base["stop"])
    a_flag = np.load(run / "A.npy")
    for m in f3.R1_MORPHOLOGIES:
        for s in f3.R1_SEEDS:
            shard(
                run,
                f"r1-{m}-{s}",
                lambda m=m, s=s: {"cases": r1_record(full, w3, method, [("r1", m, s)])},
            )
    for m in f5.HELD_OUT:
        for s in f3.R2_SEEDS:
            shard(
                run,
                f"r2-{m}-{s}",
                lambda m=m, s=s: {"cases": r1_record(full, w3, method, [("r2", m, s)])},
            )
    _, arms0, logit0 = uninjected(full, w3, method)
    for s in GPERM_SEEDS:

        def gperm(s=s):
            sc, _ = f5.relabel(full, s)
            arms, logit = method.arms(sc, w3)
            el = ~w3
            return {
                "seed": s,
                "logit_max_abs": float(np.abs(logit - logit0)[el].max()),
                "flag_diff": int((arms["method"] != arms0["method"])[el].sum()),
                "eligible": int(el.sum()),
            }

        shard(run, f"gperm-{s}", gperm)
    for k in (1, 4, 8):
        for s in GDROP_SEEDS:

            def gdrop(k=k, s=s):
                keep = f5.drop_draw(full, k, s)
                sc, rows = f5.subarray(full, keep)
                w = f3.w3_flags(sc)
                arms, _ = method.arms(sc, w)
                el = ~w
                fa = arms0["method"][rows] & el
                sa = arms["method"] & el
                return {
                    "k": k,
                    "seed": s,
                    "kept": [int(v) for v in keep],
                    "change": int((fa ^ sa).sum()),
                    "full_added": int(fa.sum()),
                    "change_frac": int((fa ^ sa).sum()) / max(int(fa.sum()), 1),
                    "w3_diff": int((w != w3[rows]).sum()),
                }

            shard(run, f"gdrop-{k}-{s}", gdrop)
    for name, keep in f5.layouts(full).items():

        def gsub(keep=keep):
            sc, rows = f5.subarray(full, keep)
            w = f3.w3_flags(sc)
            rec, _, _ = uninjected(sc, w, method, a_flag[rows])
            rec["cases"] = r1_record(
                sc,
                w,
                method,
                [("r1", m, s) for m in f3.R1_MORPHOLOGIES for s in f3.R1_SEEDS],
            )
            rec["antennas"] = [int(v) for v in keep]
            return rec

        shard(run, f"gsub-{name}", gsub)

    def gchan():
        sc = f5.average_channels(full)
        w = f3.w3_flags(sc)
        rec, _, _ = uninjected(sc, w, method)
        rec["cases"] = r1_record(
            sc,
            w,
            method,
            [("r1", m, s) for m in f3.R1_MORPHOLOGIES for s in f3.R1_SEEDS],
        )
        return rec

    shard(run, "gchan", gchan)
    print(json.dumps({"set": a.set, "done": True}))


def sim(a):
    run = Path(a.run) / f"sim-{a.klass}"
    run.mkdir(parents=True, exist_ok=True)
    method = Method(a.method, a.data_root)
    obs = f3.F2_VAL if a.validation else f4.F4_TEST
    for sc in fs.scans_of(obs, a.klass):
        name = Path(sc.path).name

        def one(sc=sc):
            scan = f3.load_fsim(sc)
            scan["planes"] = ff.Planes(
                scan["antenna1"], scan["antenna2"], scan["times"]
            )
            w3 = f3.w3_flags(scan)
            arms, _ = method.arms(scan, w3)
            arms["T"] = f3.t_flags(scan)
            rec = {"scan": str(sc.path), "counts": {}}
            for k, fl in arms.items():
                rec["counts"][k] = ff.truth_counts(
                    scan, fl, scan["amp"], w3, scan["morph"]
                )
            rec["drifting_ge10"] = int(
                ((scan["morph"] == 8) & (scan["amp"] >= 10) & ~w3).sum()
            )
            return json.loads(
                json.dumps(
                    rec,
                    default=lambda o: o.tolist() if hasattr(o, "tolist") else int(o),
                )
            )

        shard(run, f"scan-{name}", one)
    recs = [json.loads(q.read_text()) for q in sorted(run.glob("scan-*.json"))]
    if sum(r["drifting_ge10"] for r in recs) < S3_MIN:
        # S3's fallback (section 10): H1 at 10 sigma_b, seeds 61-63, into the scans.
        for sc in fs.scans_of(obs, a.klass):
            name = Path(sc.path).name

            def s3(sc=sc):
                scan = f3.load_fsim(sc)
                w3 = f3.w3_flags(scan)
                sigma = f3.baseline_sigma(scan, ~w3)
                out = []
                for seed in S3_SEEDS:
                    data, rows, chans = f4.r2_case(scan, ~w3, sigma, "H1", seed)
                    arms, _ = method.arms(scan, w3, data)
                    arms["T"] = f3.t_flags(scan, data)
                    c = {"seed": seed, "cells": len(rows)}
                    c.update({k: hits(fl, rows, chans) for k, fl in arms.items()})
                    out.append(c)
                return {"scan": str(sc.path), "cases": out}

            shard(run, f"s3-{name}", s3)
    print(json.dumps({"sim": a.klass, "done": True}))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("real", "sim"))
    p.add_argument("run")
    p.add_argument("--set")
    p.add_argument("--class", dest="klass", default="calibrator")
    p.add_argument("--method", required=True)
    p.add_argument("--data-root")
    p.add_argument("--ao-sif")
    p.add_argument(
        "--reserved-fetch",
        help="objects/ of examples/f5_fetch.py (sets reserved:MAIN_k)",
    )
    p.add_argument(
        "--validation", action="store_true", help="dry run on validation sets"
    )
    a = p.parse_args()
    if a.data_root:
        f5.use_data_root(a.data_root)
    if a.ao_sif:
        f5.AO_SIF = a.ao_sif
    {"real": real, "sim": sim}[a.mode](a)


if __name__ == "__main__":
    main()
