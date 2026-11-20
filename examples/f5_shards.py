"""F5 Stage 3: labels, the label audit and the training/validation shards
(research/f5-flagger.md, sections 3 and 4), on nash.

Usage: python examples/f5_shards.py RUN --class calibrator|target --role train|validation
       --level L --degree D --flags-from DIR [--flags-from DIR ...] [--data-root ROOT]

Writes RUN/<class>/<role>/<name>.npz (x float16 (nsel, nt, nc, n), y int8,
kind real|sim, meta) with a `.sha256` beside each, and audit.json with the
frozen stop verdict. Resumable: a shard whose `.sha256` matches its file is
skipped (its audit record is kept in RUN/<class>/<role>/records/). T's and A's
flags on the uninjected DATA come from F4's caches (`--flags-from`
`<dir>/<class>/flags/<name>-T.npy`, `-A.npy`); a scan without a cache stops
the run (A is not run here). A quarter of the real training realisations use
a random sub-array of 24 to nlive - 1 antennas (seeds 20265801 + index).
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from rang import f2flag_sim as fs
from rang import f3flag as f3
from rang import f5flag as f5

NSEL = 256
SEEDS = {  # first seed per (class, role, kind); realisation k adds k (section 4)
    ("calibrator", "train", "real"): 20265601,
    ("calibrator", "train", "sim"): 20265651,
    ("calibrator", "validation", "real"): 20265701,
    ("calibrator", "validation", "sim"): 20265711,
    ("target", "train", "real"): 20265901,
    ("target", "train", "sim"): 20265951,
    ("target", "validation", "real"): 20265961,
    ("target", "validation", "sim"): 20265971,
}
SUBARRAY_SEED = 20265801
SUBARRAY_SHARE = 0.25
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


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 24), b""):
            h.update(blk)
    return h.hexdigest()


def done(path):
    s = path.with_suffix(".sha256")
    return path.exists() and s.exists() and s.read_text().strip() == sha(path)


def write(path, x, y, kind, meta):
    tmp = path.with_suffix(".part")  # never matched by the trainer's *.npz
    with open(tmp, "wb") as fh:
        np.savez(fh, x=x.astype(np.float16), y=y, kind=kind, meta=json.dumps(meta))
    os.replace(tmp, path)
    path.with_suffix(".sha256").write_text(sha(path))


def cached_flags(name, klass, sources):
    for d in sources:
        tf = Path(d) / klass / "flags" / f"{name}-T.npy"
        af = Path(d) / klass / "flags" / f"{name}-A.npy"
        if tf.exists() and af.exists():
            return np.load(tf), np.load(af), str(d)
    raise SystemExit(f"no cached T/A flags for {name} in {sources}")


def audit_stop(rec):
    """Section 4's frozen stop, both classes; the reason or None."""
    for r in rec["realisations"]:
        e = max(r["eligible"], 1)
        if r["ignored_uninjected"] / e > 0.40:
            return f"ignored uninjected {r['ignored_uninjected'] / e:.3f} > 0.40"
        if r["positive_injected"] / e < 0.001:
            return f"injected positives {r['positive_injected'] / e:.5f} < 0.001"
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("--class", dest="klass", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--level", type=int, required=True)
    p.add_argument("--degree", type=int, required=True)
    p.add_argument("--flags-from", type=Path, action="append", default=[])
    p.add_argument("--data-root")
    p.add_argument("--ao-sif")
    p.add_argument("--only-real", action="store_true")
    a = p.parse_args()
    if a.data_root:
        f5.use_data_root(a.data_root)
    if a.ao_sif:
        f5.AO_SIF = a.ao_sif
    run = Path(os.environ["RUN_DIR"]) if a.run == "RUN" else Path(a.run)
    out = run / a.klass / a.role
    recs = out / "records"
    recs.mkdir(parents=True, exist_ok=True)
    audit = {"real": {}, "sim": {}, "stop": None, "level": a.level, "degree": a.degree}
    nreal = REALISATIONS[a.role]
    for i, spec in enumerate(f5.real_sets(a.klass, a.role)):
        t0 = time.perf_counter()
        name = spec.replace(":", "-")
        paths = [out / f"{name}-{k}.npz" for k in range(nreal)]
        if all(done(q) for q in paths):
            rr = [json.loads((recs / f"{q.stem}.json").read_text()) for q in paths]
            rec = {"realisations": rr, "resumed": True}
            audit["real"][spec] = rec
            reason = audit_stop(rec)
            if reason and not audit["stop"]:
                audit["stop"] = {"set": spec, "reason": reason}
            print(json.dumps({"skip": spec}), flush=True)
            continue
        full = f5.load(spec)
        t_full, a_full, src = cached_flags(name, a.klass, a.flags_from)
        rec = {"flags_from": src, "realisations": []}
        for k in range(nreal):
            seed = SEEDS[(a.klass, a.role, "real")] + nreal * i + k
            path = paths[k]
            if done(path):
                rec["realisations"].append(
                    json.loads((recs / f"{path.stem}.json").read_text())
                )
                continue
            sub_seed = SUBARRAY_SEED + nreal * i + k
            use_sub = (
                a.role == "train"
                and np.random.default_rng(sub_seed).random() < SUBARRAY_SHARE
            )
            if use_sub:
                keep = f5.subarray_draw(full, sub_seed + 1000)
                scan, rows = f5.subarray(full, keep)
                t_flag, a_flag = t_full[rows], a_full[rows]
            else:
                scan, keep = full, None
                t_flag, a_flag = t_full, a_full
            w3 = f3.w3_flags(scan)
            sigma = f3.baseline_sigma(scan, ~w3)
            data, flags, lab, inj, rng = f5.realise(
                scan, w3, sigma, seed, k % 3 == 2, t_flag, a_flag
            )
            elig = ~flags
            sel = select(rng, scan, elig)
            x = f5.rust_features(scan, flags, sel, a.level, a.degree, data)
            y = to_planes(scan, sel, lab, np.int8(-1))
            native = (inj.amp == 0) & (inj.beta == 0)
            r = {
                "seed": seed,
                "augmented": bool(k % 3 == 2),
                "subarray": None if keep is None else [int(v) for v in keep],
                "positive_injected": int((lab == 1).sum()),
                "ignored": int(((lab == -1) & elig).sum()),
                "ignored_uninjected": int(((lab == -1) & elig & native).sum()),
                "negative": int((lab == 0).sum()),
                "eligible": int(elig.sum()),
                "t6_cells": int((inj.morph == 1 + f5.CODES.index("T6")).sum()),
                "t7_cells": int((inj.morph == 1 + f5.CODES.index("T7")).sum()),
                "events": inj.events,
            }
            if k == 0:
                # Section 4's audit: T's and A's recall of the injected positives.
                pos = (lab == 1) & ~native
                n = max(int(pos.sum()), 1)
                tt = f3.t_flags(scan, data)
                aa, _ = f5.a_flags(scan, w3, run / "aoflag" / f"{name}-k0", data)
                r["T_recall_injected"] = float((tt & pos).sum() / n)
                r["A_recall_injected"] = float((aa & pos).sum() / n)
            write(path, x, y, "real", {"set": spec, "seed": seed, "sel": sel.tolist()})
            (recs / f"{path.stem}.json").write_text(json.dumps(r))
            rec["realisations"].append(r)
            print(
                json.dumps(
                    {k_: v for k_, v in r.items() if k_ not in ("events", "subarray")}
                ),
                flush=True,
            )
        rec["seconds"] = time.perf_counter() - t0
        audit["real"][spec] = rec
        reason = audit_stop(rec)
        if reason and not audit["stop"]:
            audit["stop"] = {"set": spec, "reason": reason}
        (out / "audit.json").write_text(json.dumps(audit, indent=1))
    if not a.only_real:
        for j, sc in enumerate(sim_scans(a.klass, a.role)):
            name = f"{Path(sc.path).parent.name}-{Path(sc.path).name}"
            path = out / f"sim-{name}.npz"
            if done(path):
                audit["sim"][name] = json.loads(
                    (recs / f"{path.stem}.json").read_text()
                )
                continue
            scan = f3.load_fsim(sc)
            w3 = f3.w3_flags(scan)
            sigma = f3.baseline_sigma(scan, ~w3)
            seed = SEEDS[(a.klass, a.role, "sim")] + j
            data, flags, lab, inj, rng = f5.realise(scan, w3, sigma, seed, j % 3 == 2)
            elig = ~flags
            sel = select(rng, scan, elig)
            x = f5.rust_features(scan, flags, sel, a.level, a.degree, data)
            y = to_planes(scan, sel, lab, np.int8(-1))
            write(
                path,
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
            (recs / f"{path.stem}.json").write_text(json.dumps(r))
            audit["sim"][name] = r
            print(json.dumps(r), flush=True)
    (out / "audit.json").write_text(json.dumps(audit, indent=1))
    print(json.dumps({"stop": audit["stop"]}))


if __name__ == "__main__":
    main()
