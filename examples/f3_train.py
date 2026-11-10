"""F3 Stage 4: train the network on the shards (research/f3-flagger.md, section 5).

Runs with NumPy and JAX only (the CUDA venv in WSL); imports `rang/f3net.py`
by path, not the rang package.

Usage: python examples/f3_train.py SHARDS OUT_DIR --seed 1 [--steps 30000]

SHARDS is the Stage 3 directory of one class (with train/ and validation/).
Writes OUT_DIR/weights.npz, OUT_DIR/train.json (loss curve, validation loss,
timing, devices).
"""

import argparse
import importlib.util
import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("f3net", HERE / "python/rang/f3net.py")
f3net = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f3net)

BATCH = 32
WIDTH = 256
RATE = 1e-3


def load(role_dir):
    shards = {"real": [], "sim": []}
    for p in sorted(Path(role_dir).glob("*.npz")):
        z = np.load(p)
        shards[str(z["kind"])].append((p.name, z["x"], z["y"]))
    return shards


def batch(rng, shard):
    _, x, y = shard
    nsel, _, nc, _ = x.shape
    b = rng.integers(0, nsel, BATCH)
    c0 = rng.integers(0, nc - WIDTH + 1, BATCH)
    cols = c0[:, None] + np.arange(WIDTH)[None]
    xb = x[b[:, None], :, cols].transpose(0, 2, 1, 3)  # (B, nt, W, 15)
    yb = y[b[:, None], :, cols].transpose(0, 2, 1)
    return np.asarray(xb, np.float32), np.asarray(yb, np.int8)


def validation_loss(params, shards):
    import jax
    import jax.numpy as jnp

    fwd = jax.jit(f3net.forward)
    tot, n = 0.0, 0
    for kind in ("real", "sim"):
        for _, x, y in shards[kind]:
            for s in range(0, len(x), 16):
                z = np.asarray(fwd(params, jnp.asarray(x[s : s + 16], jnp.float32)))
                yy = y[s : s + 16]
                keep = yy >= 0
                ce = np.maximum(z, 0) - z * (yy == 1) + np.log1p(np.exp(-np.abs(z)))
                tot += float(ce[keep].sum())
                n += int(keep.sum())
    return tot / max(n, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("shards", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--steps", type=int, default=30000)
    args = parser.parse_args()
    import jax
    import jax.numpy as jnp

    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    train = load(args.shards / "train")
    val = load(args.shards / "validation")
    t_load = time.perf_counter() - t0
    rng = np.random.default_rng(1000 + args.seed)
    params = [(jnp.asarray(w), jnp.asarray(b)) for w, b in f3net.init_params(args.seed)]
    m = jax.tree_util.tree_map(jnp.zeros_like, params)
    v = jax.tree_util.tree_map(jnp.zeros_like, params)
    step = f3net.adam_step(RATE)
    curve = []
    t1 = time.perf_counter()
    run = 0.0
    for k in range(1, args.steps + 1):
        kind = "real" if rng.random() < 0.5 else "sim"
        pool = train[kind] or train["sim" if kind == "real" else "real"]
        shard = pool[rng.integers(0, len(pool))]
        xb, yb = batch(rng, shard)
        params, m, v, loss = step(params, m, v, k, jnp.asarray(xb), jnp.asarray(yb))
        run += float(loss) if k % 50 == 0 else 0.0
        if k % 1000 == 0:
            curve.append(
                {"step": k, "loss": run / 20, "seconds": time.perf_counter() - t1}
            )
            print(json.dumps(curve[-1]), flush=True)
            run = 0.0
    t_train = time.perf_counter() - t1
    vl = validation_loss(params, val)
    f3net.save_params(
        args.out / "weights.npz", [(np.asarray(w), np.asarray(b)) for w, b in params]
    )
    rec = {
        "seed": args.seed,
        "steps": args.steps,
        "batch": BATCH,
        "width": WIDTH,
        "rate": RATE,
        "weights": f3net.count_weights(params),
        "validation_loss": vl,
        "curve": curve,
        "load_seconds": t_load,
        "train_seconds": t_train,
        "devices": [str(d) for d in jax.devices()],
        "jax": jax.__version__,
        "train_shards": {k: [s[0] for s in v_] for k, v_ in train.items()},
        "validation_shards": {k: [s[0] for s in v_] for k, v_ in val.items()},
    }
    (args.out / "train.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({"validation_loss": vl, "train_seconds": t_train}))


if __name__ == "__main__":
    main()
