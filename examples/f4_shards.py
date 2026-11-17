"""F4 Stage 3: labels, the label audit and the training/validation shards
(research/f4-flagger.md, sections 4 and 5).

Usage: python examples/f4_shards.py RUN --class calibrator|target --role train|validation
       [--flags-from DIR ...]

Writes $RUN_DIR/<class>/<role>/<name>.npz (x float16 (nsel, nt, nc, 23), y
int8; kind real|sim) and audit.json with the frozen stop verdict. T and A
run on the uninjected DATA of every real scan and are cached under
$RUN_DIR/<class>/flags/; `--flags-from` names earlier runs (F3's `-13`,
`-14`, `-08`) whose `<class>/flags/<name>-T.npy` and `-A.npy` are reused.
"""

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from rang import f2flag_sim as fs
from rang import f3flag as f3
from rang import f4flag as f4

NSEL = 256
SEEDS = {  # first seed per (class, role, kind); realisation k adds k
    ("calibrator", "train", "real"): 20264201,
    ("calibrator", "train", "sim"): 20264251,
    ("calibrator", "validation", "real"): 20264301,
    ("calibrator", "validation", "sim"): 20264311,
    ("target", "train", "real"): 20264601,
    ("target", "train", "sim"): 20264651,
    ("target", "validation", "real"): 20264701,
    ("target", "validation", "sim"): 20264711,
}
REALISATIONS = {"train": 6, "validation": 2}


def sim_scans(klass, role):
    obs = (
        [f3.F2_TRAIN / n for n in ("f2sim-1", "f2sim-2", "f2sim-3")]
        if role == "train"
        else [f3.F2_VAL]
    )
    out = []
    for o in obs:
        out += fs.scans_of(o, klass)
    return out


def select(rng, scan, eligible):
    ix = f3.index(scan)
    live = np.unique(ix["bl"][eligible.any(1)])
    if len(live) <= NSEL:
        return np.sort(live)
    return np.sort(rng.choice(live, NSEL, replace=False))


def to_planes(scan, sel, rowvals, fill):
    ix = f3.index(scan)
    pos = np.full(len(ix["ubl"]), -1)
    pos[sel] = np.arange(len(sel))
    out = np.full((len(sel), ix["nt"], rowvals.shape[1]), fill, rowvals.dtype)
    rows = np.flatnonzero(pos[ix["bl"]] >= 0)
    out[pos[ix["bl"][rows]], ix["t"][rows]] = rowvals[rows]
    return out


def write(path, x, y, kind, meta):
    np.savez(path, x=x.astype(np.float16), y=y, kind=kind, meta=json.dumps(meta))


def cached_flags(name, klass, run, sources, scan, w3):
    """T's and A's flags on the uninjected DATA, from this run's cache, an
    earlier run's (copied here, so Stage 4 finds them), or computed."""
    cache = run / klass / "flags"
    cache.mkdir(parents=True, exist_ok=True)
    for d in [run, *sources]:
        tf = Path(d) / klass / "flags" / f"{name}-T.npy"
        af = Path(d) / klass / "flags" / f"{name}-A.npy"
        if tf.exists() and af.exists():
            t_flag, a_flag = np.load(tf), np.load(af)
            if Path(d) != run:
                np.save(cache / f"{name}-T.npy", t_flag)
                np.save(cache / f"{name}-A.npy", a_flag)
            return t_flag, a_flag, str(d)
    t_flag = f3.t_flags(scan)
    a_flag, _ = f3.a_flags(scan, w3, run / "aoflag" / name)
    np.save(cache / f"{name}-T.npy", t_flag)
    np.save(cache / f"{name}-A.npy", a_flag)
    return t_flag, a_flag, "computed"


def audit_stop(klass, rec):
    """Section 4's frozen stop; returns the reason or None."""
    for r in rec["realisations"]:
        e = max(r["eligible"], 1)
        if klass == "calibrator" and r["positive_consensus"] / e > 0.10:
            return f"strong consensus {r['positive_consensus'] / e:.3f} > 0.10"
        if klass == "target":
            if r["ignored_uninjected"] / e > 0.40:
                return f"ignored {r['ignored_uninjected'] / e:.3f} > 0.40"
            if r["positive_injected"] / e < 0.001:
                return f"injected positives {r['positive_injected'] / e:.5f} < 0.001"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("--class", dest="klass", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--flags-from", type=Path, action="append", default=[])
    args = parser.parse_args()
    run = Path(os.environ["RUN_DIR"]) if args.run == "RUN" else Path(args.run)
    out = run / args.klass / args.role
    out.mkdir(parents=True, exist_ok=True)
    audit = {"real": {}, "sim": {}, "stop": None}
    nreal = REALISATIONS[args.role]
    for i, spec in enumerate(f4.real_sets(args.klass, args.role)):
        t0 = time.perf_counter()
        scan = f4.load(spec)
        name = spec.replace(":", "-")
        w3 = f3.w3_flags(scan)
        eligible = ~w3
        t_flag, a_flag, src = cached_flags(
            name, args.klass, run, args.flags_from, scan, w3
        )
        sigma = f3.baseline_sigma(scan, eligible)
        s = f4.strength_rows(scan, w3)
        rec = {
            "eligible": int(eligible.sum()),
            "T_added": int((t_flag & eligible).sum()),
            "A_added": int((a_flag & eligible).sum()),
            "flags_from": src,
            "strong_consensus_s5": int(
                f4.strong_consensus(t_flag, a_flag, eligible, s).sum()
            ),
            "realisations": [],
        }
        for k in range(nreal):
            seed = SEEDS[(args.klass, args.role, "real")] + nreal * i + k
            data, flags, lab, inj, rng = f4.realise(
                scan, w3, sigma, seed, k % 3 == 2, t_flag, a_flag, s
            )
            elig = ~flags
            sel = select(rng, scan, elig)
            x = f4.rust_features(scan, flags, sel, data)
            y = to_planes(scan, sel, lab, np.int8(-1))
            injected = (inj.amp >= 3) & elig
            native = ~(inj.amp > 0)
            r = {
                "seed": seed,
                "augmented": bool(k % 3 == 2),
                "positive_injected": int(injected.sum()),
                "positive_consensus": int(((lab == 1) & native).sum()),
                "consensus_all": int((t_flag & a_flag & elig & native).sum()),
                "ignored": int(((lab == -1) & elig).sum()),
                "ignored_uninjected": int(((lab == -1) & elig & native).sum()),
                "negative": int((lab == 0).sum()),
                "eligible": int(elig.sum()),
                "t6_cells": int((inj.morph == 1 + f4.CODES.index("T6")).sum()),
                "events": inj.events,
            }
            pos, neg = lab == 1, lab == 0
            r["median_s_positive"] = float(np.median(s[pos])) if pos.any() else None
            r["median_s_negative"] = float(np.median(s[neg])) if neg.any() else None
            if k == 0:
                tt = f3.t_flags(scan, inj.data)
                aa, _ = f3.a_flags(scan, w3, run / "aoflag" / f"{name}-k0", inj.data)
                n = max(int(injected.sum()), 1)
                r["T_recall_injected"] = float((tt & injected).sum() / n)
                r["A_recall_injected"] = float((aa & injected).sum() / n)
            rec["realisations"].append(r)
            write(
                out / f"{name}-{k}.npz",
                x,
                y,
                "real",
                {"set": spec, "seed": seed, "sel": sel.tolist()},
            )
            print(
                json.dumps({k_: v for k_, v in r.items() if k_ != "events"}), flush=True
            )
        rec["seconds"] = time.perf_counter() - t0
        audit["real"][spec] = rec
        reason = audit_stop(args.klass, rec)
        if reason and not audit["stop"]:
            audit["stop"] = {"set": spec, "reason": reason}
        (out / "audit.json").write_text(json.dumps(audit, indent=1), encoding="utf-8")
    for j, sc in enumerate(sim_scans(args.klass, args.role)):
        scan = f3.load_fsim(sc)
        w3 = f3.w3_flags(scan)
        sigma = f3.baseline_sigma(scan, ~w3)
        seed = SEEDS[(args.klass, args.role, "sim")] + j
        data, flags, lab, inj, rng = f4.realise(scan, w3, sigma, seed, j % 3 == 2)
        elig = ~flags
        sel = select(rng, scan, elig)
        x = f4.rust_features(scan, flags, sel, data)
        y = to_planes(scan, sel, lab, np.int8(-1))
        name = f"{Path(sc.path).parent.name}-{Path(sc.path).name}"
        write(
            out / f"sim-{name}.npz",
            x,
            y,
            "sim",
            {"scan": str(sc.path), "seed": seed, "sel": sel.tolist()},
        )
        r = {
            "scan": name,
            "seed": seed,
            "positive": int((lab == 1).sum()),
            "negative": int((lab == 0).sum()),
            "ignored": int(((lab == -1) & elig).sum()),
        }
        audit["sim"][name] = r
        print(json.dumps(r), flush=True)
        (out / "audit.json").write_text(json.dumps(audit, indent=1), encoding="utf-8")
    print(json.dumps({"stop": audit["stop"]}))


if __name__ == "__main__":
    main()
