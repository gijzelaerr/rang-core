"""F3 Stage 3: labels, the label audit and the training/validation shards
(research/f3-flagger.md, sections 4 and 5).

Usage: python examples/f3_shards.py RUN --class calibrator|target --role train|validation

Writes $RUN_DIR/<class>/<role>/<name>.npz (x float16 (nsel, nt, nc, 15), y
int8 (nsel, nt, nc): 1 positive, 0 negative, -1 ignored; kind real|sim) and
$RUN_DIR/<class>/<role>/audit.json. T and A run on the uninjected DATA of
every real scan; their flags are cached under $RUN_DIR/<class>/flags/.
"""

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from rang import f2flag_sim as fs
from rang import f3flag as f3

NSEL = 256
SEEDS = {  # first seed per (class, role, kind); realisation k adds k
    ("calibrator", "train", "real"): 20263201,
    ("calibrator", "train", "sim"): 20263251,
    ("calibrator", "validation", "real"): 20263301,
    ("calibrator", "validation", "sim"): 20263311,
    ("target", "train", "real"): 20263601,
    ("target", "train", "sim"): 20263651,
    ("target", "validation", "real"): 20263701,
    ("target", "validation", "sim"): 20263711,
}
REALISATIONS = {"train": 6, "validation": 2}


def real_sets(klass, role):
    if klass == "calibrator":
        return [f"luno:{g}" for g, r in f3.LUNO_ROLE.items() if r == role]
    return [f"eso:{c}" for c, r in sorted(f3.ESO_ROLE.items()) if r == role]


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


def load(spec):
    kind, _, name = spec.partition(":")
    return f3.load_luno(name) if kind == "luno" else f3.load_eso(int(name))


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("--class", dest="klass", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--labels", choices=("frozen", "amend1"), default="amend1")
    parser.add_argument(
        "--flags-from", type=Path, help="reuse T and A flags of an earlier run"
    )
    args = parser.parse_args()
    run = Path(os.environ["RUN_DIR"]) if args.run == "RUN" else Path(args.run)
    out = run / args.klass / args.role
    out.mkdir(parents=True, exist_ok=True)
    cache = (args.flags_from or run) / args.klass / "flags"
    cache.mkdir(parents=True, exist_ok=True)
    audit = {"real": {}, "sim": {}}
    nreal = REALISATIONS[args.role]
    for i, spec in enumerate(real_sets(args.klass, args.role)):
        t0 = time.perf_counter()
        scan = load(spec)
        name = spec.replace(":", "-")
        w3 = f3.w3_flags(scan)
        eligible = ~w3
        tf = cache / f"{name}-T.npy"
        af = cache / f"{name}-A.npy"
        if tf.exists():
            t_flag = np.load(tf)
            a_flag = np.load(af)
        else:
            t_flag = f3.t_flags(scan)
            a_flag, _ = f3.a_flags(scan, w3, run / "aoflag" / name)
            np.save(tf, t_flag)
            np.save(af, a_flag)
        sigma = f3.baseline_sigma(scan, eligible)
        strong = f3.u_rows(scan, w3) >= 3 if args.labels == "amend1" else None
        rec = {
            "eligible": int(eligible.sum()),
            "T_added": int((t_flag & eligible).sum()),
            "A_added": int((a_flag & eligible).sum()),
            "realisations": [],
        }
        for k in range(nreal):
            seed = SEEDS[(args.klass, args.role, "real")] + nreal * i + k
            data, flags, lab, inj, rng = f3.realise(
                scan, w3, sigma, seed, k % 3 == 2, t_flag, a_flag, strong
            )
            elig = ~flags
            sel = select(rng, scan, elig)
            x = f3.rust_features(scan, flags, sel, data)
            y = to_planes(scan, sel, lab, np.int8(-1))
            injected = (inj.amp >= 3) & elig
            cons = (lab == 1) & ~(inj.amp > 0)
            allcons = t_flag & a_flag & elig & ~(inj.amp > 0)
            r = {
                "seed": seed,
                "augmented": bool(k % 3 == 2),
                "positive_injected": int(injected.sum()),
                "positive_consensus": int(cons.sum()),
                "consensus_all": int(allcons.sum()),
                "labels": args.labels,
                "ignored": int(((lab == -1) & elig).sum()),
                "negative": int((lab == 0).sum()),
                "eligible": int(elig.sum()),
                "events": inj.events,
            }
            u = np.sinh(x[..., :8].max(-1))
            yy = y
            un = to_planes(scan, sel, inj.amp, np.float32(0)) == 0
            r["median_u_consensus"] = (
                float(np.median(u[(yy == 1) & un])) if ((yy == 1) & un).any() else None
            )
            r["median_u_negative"] = (
                float(np.median(u[yy == 0])) if (yy == 0).any() else None
            )
            if k == 0:
                tt = f3.t_flags(scan, inj.data)
                aa, _ = f3.a_flags(scan, w3, run / "aoflag" / f"{name}-k0", inj.data)
                r["T_recall_injected"] = float(
                    (tt & injected).sum() / max(injected.sum(), 1)
                )
                r["A_recall_injected"] = float(
                    (aa & injected).sum() / max(injected.sum(), 1)
                )
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
        (out / "audit.json").write_text(json.dumps(audit, indent=1))
    for j, s in enumerate(sim_scans(args.klass, args.role)):
        scan = f3.load_fsim(s)
        w3 = f3.w3_flags(scan)
        eligible = ~w3
        sigma = f3.baseline_sigma(scan, eligible)
        seed = SEEDS[(args.klass, args.role, "sim")] + j
        data, flags, lab, inj, rng = f3.realise(scan, w3, sigma, seed, j % 3 == 2)
        elig = ~flags
        sel = select(rng, scan, elig)
        x = f3.rust_features(scan, flags, sel, data)
        y = to_planes(scan, sel, lab, np.int8(-1))
        name = f"{Path(s.path).parent.name}-{Path(s.path).name}"
        write(
            out / f"sim-{name}.npz",
            x,
            y,
            "sim",
            {"scan": str(s.path), "seed": seed, "sel": sel.tolist()},
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
        (out / "audit.json").write_text(json.dumps(audit, indent=1))


if __name__ == "__main__":
    main()
