"""F2 Stage 4: train the network on one class (research/f2-flagger.md, section 7).

Usage: python examples/f2_train.py OUT_DIR --class calibrator|target
           --runs sim:1,sim:2,sim:3,res:1,imi:1 --train OBS [OBS ...] --val OBS
           [--steps 4000] [--workers 4]

OUT_DIR `RUN/x` means $RUN_DIR/x; each run writes OUT_DIR/<class>-<labels>-<seed>/
weights.npz and log.json. Labels: sim (truth, A >= 3 positive, 0 < A < 3
ignored), res (R's added flags), imi (T's added flags). The scans are prepared
once; windows' features are computed by forked NumPy workers; JAX (CPU) only
in the parent, imported after the fork.
"""

import argparse
import json
import multiprocessing
import os
import time
from pathlib import Path

import numpy as np
from rang import f2flag as ff
from rang import f2flag_sim as fs

BATCH = 16
SCANS = {}  # filled before the fork: name -> TrainScan


class TrainScan:
    """One scan's memory-mapped DATA, shared-wrapper planes and the labels."""

    def __init__(self, s, klass):
        m = s.meta
        self.name = f"{m['observation']}/scan{m['scan']}"
        self.path = s.path
        self.nbl, self.nt = m["nbl"], m["ntime"]
        self.nc = len(m["chan_freq"])
        scan = load_full(s)
        shared, _ = ff.run_strategy(scan, ff.shared_strategy(klass))
        amp = np.abs(np.asarray(s.array("rfi"))).max(-1) / m["sigma"]
        r = ff.r_flags(scan, shared) & ~shared
        t, _ = ff.run_strategy(scan, ff.strategy(ff.STRATEGIES[klass]))
        t &= ~shared
        sets = {
            "sim": (amp >= 3, ((amp >= 3) | (amp == 0)) & ~shared),
            "res": (r, ~shared),
            "imi": (t, ~shared),
        }
        self.shared = self.planes(shared)
        self.label = {k: self.planes(v[0]).astype(np.uint8) for k, v in sets.items()}
        self.weight = {k: self.planes(v[1]).astype(np.uint8) for k, v in sets.items()}
        self.label_fraction = {
            k: float(v[0][v[1]].mean()) if v[1].any() else 0.0 for k, v in sets.items()
        }
        del scan

    def planes(self, x):
        return np.ascontiguousarray(
            x.reshape(self.nt, self.nbl, self.nc).transpose(1, 0, 2)
        )

    def vis(self, b):
        data = np.load(self.path / "data.npy", mmap_mode="r")
        return np.asarray(data[b :: self.nbl])


def load_full(s):
    m = s.meta
    data = np.array(s.array("data"))
    a1 = np.array(m["antenna1"], np.int32)
    a2 = np.array(m["antenna2"], np.int32)
    times = np.array(m["times"])
    return {
        "data": data,
        "model": np.array(s.array("model")),
        "weights": np.full(data.shape, 1.0 / m["sigma"] ** 2, np.float32),
        "antenna1": a1,
        "antenna2": a2,
        "times": times,
        "antenna_position": np.array(m["antenna_position"]),
        "chan_freq": np.array(m["chan_freq"]),
        "chan_width": np.array(m["chan_width"]),
        "corr_type": np.array(m["corr_type"], np.int32),
        "nant": m["nant"],
        "planes": ff.Planes(a1, a2, times),
    }


def window(job):
    """Worker: one window's (x, label, weight) from (scan name, labels, seed)."""
    name, labels, seed = job
    scan = SCANS[name]
    rng = np.random.default_rng(seed)
    b = int(rng.integers(0, scan.nbl))
    aug = ff.augment_flags(rng, scan.nt, scan.nc)
    flagged = scan.shared[b] | aug
    x, _ = ff.features(scan.vis(b)[None], flagged[None])
    s, lo, hi = ff.crop_window(rng, scan.nc)
    w = (scan.weight[labels][b] & ~flagged).astype(np.float32)[:, s : s + ff.CROP]
    w[:, :lo] = 0
    w[:, hi:] = 0
    y = scan.label[labels][b][:, s : s + ff.CROP].astype(np.float32)
    return x[0, :, s : s + ff.CROP], y, w


def val_features(job):
    """Worker: full-plane features of a block of validation baselines."""
    name, b0, b1 = job
    scan = SCANS[name]
    vis = np.stack([scan.vis(b) for b in range(b0, b1)])
    x, _ = ff.features(vis, scan.shared[b0:b1])
    return x


def validation_loss(params, val, labels, pool):
    import jax

    loss_fn = jax.jit(ff.loss_fn)
    num = den = 0.0
    for scan in val:
        jobs = [(scan.name, b, min(b + 32, scan.nbl)) for b in range(0, scan.nbl, 32)]
        for (_, b0, b1), x in zip(jobs, pool.imap(val_features, jobs)):
            w = scan.weight[labels][b0:b1].astype(np.float32)
            y = scan.label[labels][b0:b1].astype(np.float32)
            loss = float(loss_fn(params, x, y, w))
            num += loss * float(w.sum())
            den += float(w.sum())
    return num / den


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--class", dest="klass", required=True)
    parser.add_argument("--runs", default="sim:1,sim:2,sim:3,res:1,imi:1")
    parser.add_argument("--train", nargs="+", type=Path, required=True)
    parser.add_argument("--val", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=4000)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    out = args.out
    if out.startswith("RUN/"):
        out = Path(os.environ["RUN_DIR"]) / out[4:]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    train = [
        TrainScan(s, args.klass) for o in args.train for s in fs.scans_of(o, args.klass)
    ]
    val = [TrainScan(s, args.klass) for s in fs.scans_of(args.val, args.klass)]
    for s in train + val:
        SCANS[s.name] = s
    prep = time.perf_counter() - started
    pool = multiprocessing.get_context("fork").Pool(args.workers)
    import jax
    import jax.numpy as jnp

    step = ff.adam_step()
    summaries = []
    for run in args.runs.split(","):
        labels, seed = run.split(":")
        seed = int(seed)
        t_run = time.perf_counter()
        params = [(jnp.asarray(w), jnp.asarray(b)) for w, b in ff.init_params(seed)]
        m = jax.tree_util.tree_map(jnp.zeros_like, params)
        v = jax.tree_util.tree_map(jnp.zeros_like, params)
        rng = np.random.default_rng([seed, 20262200])
        log = []
        t_feat = t_step = 0.0
        for k in range(1, args.steps + 1):
            t = time.perf_counter()
            scan = train[int(rng.integers(0, len(train)))]
            jobs = [(scan.name, labels, int(s)) for s in rng.integers(0, 2**62, BATCH)]
            parts = pool.map(window, jobs)
            x = np.stack([p[0] for p in parts])
            y = np.stack([p[1] for p in parts])
            w = np.stack([p[2] for p in parts])
            t_feat += time.perf_counter() - t
            t = time.perf_counter()
            params, m, v, loss = step(params, m, v, k, x, y, w)
            loss = float(loss)
            t_step += time.perf_counter() - t
            if k % 100 == 0 or k == 1:
                log.append({"step": k, "loss": loss})
        vloss = validation_loss(params, val, labels, pool)
        host = [(np.asarray(w), np.asarray(b)) for w, b in params]
        rdir = out / f"{args.klass}-{labels}-{seed}"
        rdir.mkdir(exist_ok=False)
        ff.save_params(rdir / "weights.npz", host)
        summary = {
            "class": args.klass,
            "labels": labels,
            "seed": seed,
            "steps": args.steps,
            "batch": BATCH,
            "train": [str(o) for o in args.train],
            "val": str(args.val),
            "train_label_fraction": {s.name: s.label_fraction[labels] for s in train},
            "validation_loss": vloss,
            "final_train_loss": log[-1]["loss"],
            "mean_train_loss_last_500": float(
                np.mean([e["loss"] for e in log if e["step"] > args.steps - 500])
            ),
            "weights": ff.count_weights(host),
            "seconds_prepare_shared": prep,
            "seconds_features": t_feat,
            "seconds_steps": t_step,
            "seconds": time.perf_counter() - t_run,
            "jax": jax.__version__,
            "devices": [str(d) for d in jax.devices()],
            "workers": args.workers,
            "log": log,
        }
        (rdir / "log.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        summaries.append(
            {k: summary[k] for k in ("labels", "seed", "validation_loss", "seconds")}
        )
        print(json.dumps(summaries[-1]), flush=True)
    pool.close()
    (out / f"{args.klass}-summary.json").write_text(
        json.dumps({"runs": summaries, "seconds_prepare": prep}, indent=1),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
