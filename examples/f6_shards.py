"""F6 Stage 3: labels, the pooled label audit and the shards (research/f6-flagger.md),
on nash.

Usage: python examples/f6_shards.py RUN --class calibrator|target --role train|validation
       --level 20 --degree D --flags-from DIR --data-root R --sarao-root C_ROOT
       [--ao-sif S] [--sources luno,eso,sarao,sim]

Per real scan, REALISATIONS[role] realisations, each with antenna dropout (0-8 live
antennas removed, seeded) and Landman's labels plus hybrid positives (T and A both
flag, s >= 3 on the uninjected DATA). SARAO scans come from session C's stage-1
manifest by section 1's cut-off list (training blocks, or validation block
1573212012), T and A from C's labels; long scans keep their central MAX_DUMPS dumps.
The audit is pooled over a scan's realisations (fix 3): stop the class if a scan's
pooled ignored-uninjected share exceeds 40 % or its pooled injected-positive share is
below 0.1 %. Every shard has a `.sha256`; a rerun skips finished shards.
"""

import argparse
import importlib.util
import json
import os
import time
from pathlib import Path

import numpy as np
from rang import f3flag as f3
from rang import f5flag as f5

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("f5_shards", HERE / "f5_shards.py")
f5s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f5s)

SEEDS = {  # first seed per (class, role, source); realisation k adds k
    ("calibrator", "train", "real"): 20266101,
    ("calibrator", "train", "sim"): 20266301,
    ("calibrator", "validation", "real"): 20266401,
    ("calibrator", "validation", "sim"): 20266451,
    ("target", "train", "real"): 20266501,
    ("target", "train", "sim"): 20266701,
    ("target", "validation", "real"): 20266801,
    ("target", "validation", "sim"): 20266851,
}
DROPOUT_SEED = 20266901
DROPOUT_MAX = 8
REALISATIONS = {"train": 4, "validation": 2}
MAX_DUMPS = 32
TRAIN_BLOCKS = ("1571938260", "1611426666", "1629213076", "1749428161")
VALIDATION_BLOCK = "1573212012"


def sarao_scans(root, klass, role):
    m = json.loads((Path(root) / "manifests" / "stage1.json").read_text())
    blocks = TRAIN_BLOCKS if role == "train" else (VALIDATION_BLOCK,)
    out = [
        e
        for e in m["entries"]
        if e["cbid"] in blocks
        and e["class"] == klass
        and e["split"] == ("train" if role == "train" else "validation")
    ]
    return sorted(out, key=lambda e: (e["cbid"], int(e["scan"])))


def central_dumps(scan, n=MAX_DUMPS):
    t = np.unique(scan["times"])
    if len(t) <= n:
        return scan, None
    lo = (len(t) - n) // 2
    keep_t = t[lo : lo + n]
    rows = np.flatnonzero(np.isin(scan["times"], keep_t))
    out = {k: v for k, v in scan.items() if k not in ("_index", "teachers")}
    for k in ("data", "input_flags", "antenna1", "antenna2", "times"):
        out[k] = np.ascontiguousarray(scan[k][rows])
    if "teachers" in scan:
        out["teachers"] = {k: v[rows] for k, v in scan["teachers"].items()}
    return out, rows


def dropout(scan, t_flag, a_flag, seed):
    """Remove 0..DROPOUT_MAX live antennas (seeded); returns the sub-scan, its T, A."""
    rng = np.random.default_rng(seed)
    k = int(rng.integers(0, DROPOUT_MAX + 1))
    if k == 0:
        return scan, t_flag, a_flag, []
    live = f5.live_antennas(scan)
    gone = rng.choice(live, min(k, len(live) - 4), replace=False)
    sub, rows = f5.subarray(scan, np.setdiff1d(live, gone))
    return sub, t_flag[rows], a_flag[rows], [int(g) for g in gone]


def audit_pooled(recs):
    """Fix 3: the bars on a scan's realisations pooled."""
    e = sum(r["eligible"] for r in recs) or 1
    pos = sum(r["positive_injected"] for r in recs) / e
    ign = sum(r["ignored_uninjected"] for r in recs) / e
    if ign > 0.40:
        return f"pooled ignored uninjected {ign:.3f} > 0.40"
    if pos < 0.001:
        return f"pooled injected positives {pos:.5f} < 0.001"
    return None


def realisations(name, scan, t_flag, a_flag, a, out, recs_dir, seed0, nreal, spec_):
    recs = []
    for k in range(nreal):
        path = out / f"{name}-{k}.npz"
        rec_path = recs_dir / f"{path.stem}.json"
        if f5s.done(path):
            recs.append(json.loads(rec_path.read_text()))
            continue
        seed = seed0 + k
        sc, tf, af, gone = dropout(scan, t_flag, a_flag, DROPOUT_SEED + seed - 20266000)
        w3 = f3.w3_flags(sc)
        sigma = f3.baseline_sigma(sc, ~w3)
        strong = f5.hybrid_strong(sc, w3, tf, af)
        data, flags, lab, inj, rng = f5.realise(
            sc, w3, sigma, seed, k % 3 == 2, tf, af, strong
        )
        elig = ~flags
        sel = f5s.select(rng, sc, elig)
        x = f5.rust_features(sc, flags, sel, a.level, a.degree, data)
        y = f5s.to_planes(sc, sel, lab, np.int8(-1))
        native = (inj.amp == 0) & (inj.beta == 0)
        r = {
            "seed": seed,
            "dropped": gone,
            "augmented": bool(k % 3 == 2),
            "positive_injected": int(((lab == 1) & ~native).sum()),
            "positive_hybrid": int(((lab == 1) & native).sum()),
            "ignored_uninjected": int(((lab == -1) & elig & native).sum()),
            "negative": int((lab == 0).sum()),
            "eligible": int(elig.sum()),
        }
        f5s.write(path, x, y, "real", {"set": spec_, "seed": seed, "sel": sel.tolist()})
        rec_path.write_text(json.dumps(r))
        recs.append(r)
        print(json.dumps({"shard": path.name, **r}), flush=True)
    return recs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("--class", dest="klass", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--level", type=int, default=20)
    p.add_argument("--degree", type=int, required=True)
    p.add_argument("--flags-from", type=Path, required=True)
    p.add_argument("--data-root", required=True)
    p.add_argument("--sarao-root", required=True)
    p.add_argument("--ao-sif")
    p.add_argument("--sources", default="luno,eso,sarao,sim")
    a = p.parse_args()
    f5.use_data_root(a.data_root)
    if a.ao_sif:
        f5.AO_SIF = a.ao_sif
    run = Path(os.environ["RUN_DIR"]) if a.run == "RUN" else Path(a.run)
    out = run / a.klass / a.role
    recs_dir = out / "records"
    recs_dir.mkdir(parents=True, exist_ok=True)
    sources = set(a.sources.split(","))
    nreal = REALISATIONS[a.role]
    seed = SEEDS[(a.klass, a.role, "real")]
    audit = {"scans": {}, "stop": None, "level": a.level, "degree": a.degree}
    t0 = time.perf_counter()
    jobs = []
    if ("luno" in sources and a.klass == "calibrator") or (
        "eso" in sources and a.klass == "target"
    ):
        for spec_ in f5.real_sets(a.klass, a.role):
            jobs.append(("f4", spec_))
    if "sarao" in sources:
        for e in sarao_scans(a.sarao_root, a.klass, a.role):
            jobs.append(("sarao", e))
    for i, (kind, item) in enumerate(jobs):
        s0 = seed + 1000 * i
        if kind == "f4":
            spec_ = item
            name = spec_.replace(":", "-")
            if all(f5s.done(out / f"{name}-{k}.npz") for k in range(nreal)):
                recs = [
                    json.loads((recs_dir / f"{name}-{k}.json").read_text())
                    for k in range(nreal)
                ]
            else:
                scan = f5.load(spec_)
                tf, af, _ = f5s.cached_flags(name, a.klass, [a.flags_from])
                recs = realisations(
                    name, scan, tf, af, a, out, recs_dir, s0, nreal, spec_
                )
        else:
            e = item
            name = f"sarao-{e['cbid']}-scan{int(e['scan']):03d}"
            if all(f5s.done(out / f"{name}-{k}.npz") for k in range(nreal)):
                recs = [
                    json.loads((recs_dir / f"{name}-{k}.json").read_text())
                    for k in range(nreal)
                ]
            else:
                scan = f5.load_sarao(
                    Path(a.sarao_root) / e["ms"],
                    a.klass,
                    Path(a.sarao_root) / "labels",
                    e["cbid"],
                    e["scan"],
                )
                scan, _ = central_dumps(scan)
                tf, af = scan["teachers"]["T"], scan["teachers"]["A"]
                recs = realisations(
                    name, scan, tf, af, a, out, recs_dir, s0, nreal, name
                )
        reason = audit_pooled(recs)
        audit["scans"][name] = {"pooled_stop": reason, "realisations": len(recs)}
        if reason and not audit["stop"]:
            audit["stop"] = {"scan": name, "reason": reason}
        (out / "audit.json").write_text(json.dumps(audit, indent=1))
    if "sim" in sources:
        sseed = SEEDS[(a.klass, a.role, "sim")]
        for j, sc in enumerate(f5s.sim_scans(a.klass, a.role)):
            name = f"sim-{Path(sc.path).parent.name}-{Path(sc.path).name}"
            path = out / f"{name}.npz"
            if f5s.done(path):
                continue
            scan = f3.load_fsim(sc)
            w3 = f3.w3_flags(scan)
            sigma = f3.baseline_sigma(scan, ~w3)
            data, flags, lab, _, rng = f5.realise(
                scan, w3, sigma, sseed + j, j % 3 == 2
            )
            elig = ~flags
            sel = f5s.select(rng, scan, elig)
            x = f5.rust_features(scan, flags, sel, a.level, a.degree, data)
            y = f5s.to_planes(scan, sel, lab, np.int8(-1))
            f5s.write(
                path,
                x,
                y,
                "sim",
                {"scan": str(sc.path), "seed": sseed + j, "sel": sel.tolist()},
            )
            print(
                json.dumps({"shard": path.name, "positive": int((lab == 1).sum())}),
                flush=True,
            )
    audit["seconds"] = time.perf_counter() - t0
    (out / "audit.json").write_text(json.dumps(audit, indent=1))
    print(json.dumps({"stop": audit["stop"], "scans": len(audit["scans"])}))


if __name__ == "__main__":
    main()
