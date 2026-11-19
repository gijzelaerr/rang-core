"""F5 Stage 4: train N5 on the shards (research/f5-flagger.md, section 9).

Runs with NumPy and PyTorch only (the CUDA venv in WSL); imports
`rang/f5net.py` by path, not the rang package. F3's procedure: Adam 1e-3,
30,000 steps, batch 32 windows of one baseline x 256 channels from one shard
per step, real : simulation = 1 : 1, unweighted BCE over non-ignored cells,
batch draws `numpy.random.default_rng(1000 + seed)` in F3's order.

Resumable: a checkpoint every 1,000 steps and at least every 10 minutes
(weights, Adam state, step, the NumPy generator state, torch RNG states,
curve), written atomically with a sha256; a rerun resumes from it. Between
checkpoints `GPU_CHECK` (a command; exit code 3 means yield) is run, if set:
on 3 the trainer saves and exits with 3.

Usage: python examples/f5_train.py SHARDS OUT_DIR --seed 1 [--steps 30000]
       [--stop-at N] [--device cuda]

SHARDS holds train/ and validation/ (`x` float16 (nsel, nt, nc, n), `y` int8,
`kind` real|sim). Writes OUT_DIR/weights.npz (arrays, `flat`, header),
OUT_DIR/train.json and OUT_DIR/ckpt.pt.
"""

import argparse
import hashlib
import importlib.util
import io
import json
import os
import shlex
import subprocess
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("f5net", HERE / "python/rang/f5net.py")
f5net = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f5net)

BATCH = 32
WIDTH = 256
RATE = 1e-3
EVERY_STEPS = 1000
EVERY_SECONDS = 600


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
    xb = x[b[:, None], :, cols].transpose(0, 2, 1, 3)
    yb = y[b[:, None], :, cols].transpose(0, 2, 1)
    return np.asarray(xb, np.float32), np.asarray(yb, np.int8)


def validation_loss(net, shards, device):
    tot, n = 0.0, 0
    net.eval()
    with torch.no_grad():
        for kind in ("real", "sim"):
            for _, x, y in shards[kind]:
                for s in range(0, len(x), 16):
                    xb = torch.from_numpy(np.asarray(x[s : s + 16], np.float32)).to(
                        device
                    )
                    z = net(xb).double().cpu().numpy()
                    yy = y[s : s + 16]
                    keep = yy >= 0
                    ce = np.maximum(z, 0) - z * (yy == 1) + np.log1p(np.exp(-np.abs(z)))
                    tot += float(ce[keep].sum())
                    n += int(keep.sum())
    net.train()
    return tot / max(n, 1)


def save_ckpt(path, state):
    buf = io.BytesIO()
    torch.save(state, buf)
    data = buf.getvalue()
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    path.with_suffix(".sha256").write_text(hashlib.sha256(data).hexdigest())


def load_ckpt(path):
    data = path.read_bytes()
    want = path.with_suffix(".sha256").read_text().strip()
    if hashlib.sha256(data).hexdigest() != want:
        raise SystemExit(f"checkpoint {path} fails its sha256; remove it to restart")
    return torch.load(io.BytesIO(data), weights_only=False)


def gpu_yield():
    cmd = os.environ.get("GPU_CHECK")
    if not cmd:
        return False
    rc = subprocess.call(shlex.split(cmd))
    if rc not in (0, 3):
        raise SystemExit(f"GPU_CHECK failed with exit code {rc}: {cmd}")
    return rc == 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shards", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--steps", type=int, default=30000)
    ap.add_argument(
        "--stop-at", type=int, help="save and stop after this step (resume test)"
    )
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args()
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    a.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    train = load(a.shards / "train")
    val = load(a.shards / "validation")
    t_load = time.perf_counter() - t0
    first = (train["real"] or train["sim"])[0][1]
    nplanes = int(first.shape[-1])
    net = f5net.build(nplanes, True, seed=a.seed).to(a.device)
    opt = torch.optim.Adam(net.parameters(), lr=RATE, betas=(0.9, 0.999), eps=1e-8)
    rng = np.random.default_rng(1000 + a.seed)
    torch.manual_seed(a.seed)
    ck = a.out / "ckpt.pt"
    step, curve, run, resumed = 0, [], 0.0, []
    if ck.exists():
        st = load_ckpt(ck)
        net.load_state_dict(st["net"])
        opt.load_state_dict(st["opt"])
        rng.bit_generator.state = st["rng"]
        torch.set_rng_state(st["torch_rng"])
        if st.get("cuda_rng") is not None and a.device.startswith("cuda"):
            torch.cuda.set_rng_state(st["cuda_rng"])
        step, curve, run, resumed = st["step"], st["curve"], st["run"], st["resumed"]
        resumed = [*resumed, step]
        print(json.dumps({"resumed_at": step}), flush=True)

    def checkpoint():
        save_ckpt(
            ck,
            {
                "net": net.state_dict(),
                "opt": opt.state_dict(),
                "rng": rng.bit_generator.state,
                "torch_rng": torch.get_rng_state(),
                "cuda_rng": torch.cuda.get_rng_state()
                if a.device.startswith("cuda")
                else None,
                "step": step,
                "curve": curve,
                "run": run,
                "resumed": resumed,
            },
        )

    t1 = time.perf_counter()
    last = time.perf_counter()
    while step < a.steps:
        step += 1
        kind = "real" if rng.random() < 0.5 else "sim"
        pool = train[kind] or train["sim" if kind == "real" else "real"]
        shard = pool[rng.integers(0, len(pool))]
        xb, yb = batch(rng, shard)
        x = torch.from_numpy(xb).to(a.device)
        y = torch.from_numpy(yb).to(a.device)
        loss = f5net.bce(net(x), y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        if step % 50 == 0:
            run += float(loss.detach())
        if step % EVERY_STEPS == 0:
            curve.append(
                {"step": step, "loss": run / 20, "seconds": time.perf_counter() - t1}
            )
            run = 0.0
            print(json.dumps(curve[-1]), flush=True)
        due = step % EVERY_STEPS == 0 or time.perf_counter() - last >= EVERY_SECONDS
        if due or step == a.steps or step == a.stop_at:
            checkpoint()
            last = time.perf_counter()
            if step == a.stop_at:
                print(json.dumps({"stopped_at": step}), flush=True)
                return
            if step < a.steps and gpu_yield():
                print(json.dumps({"yield_at": step}), flush=True)
                raise SystemExit(3)
    t_train = time.perf_counter() - t1
    vl = validation_loss(net, val, a.device)
    arrays = f5net.to_arrays(net)
    flat = f5net.flat_from_arrays(arrays)
    header = {
        "stage": "flag",
        "architecture": "f5-n5",
        "nplanes": nplanes,
        "seed": a.seed,
        "steps": a.steps,
        "validation_loss": vl,
        "shards": str(a.shards),
    }
    np.savez(
        a.out / "weights.npz",
        flat=flat,
        header=json.dumps(header),
        **{f"w{i}": w for i, (w, _) in enumerate(arrays)},
        **{f"b{i}": b for i, (_, b) in enumerate(arrays)},
    )
    rec = {
        **header,
        "batch": BATCH,
        "width": WIDTH,
        "rate": RATE,
        "weights": int(flat.size),
        "curve": curve,
        "resumed_at": resumed,
        "load_seconds": t_load,
        "train_seconds_this_run": t_train,
        "device": a.device,
        "gpu": torch.cuda.get_device_name(0) if a.device.startswith("cuda") else None,
        "peak_vram_allocated_bytes": (
            int(torch.cuda.max_memory_allocated())
            if a.device.startswith("cuda")
            else None
        ),
        "peak_vram_reserved_bytes": (
            int(torch.cuda.max_memory_reserved())
            if a.device.startswith("cuda")
            else None
        ),
        "torch": torch.__version__,
        "deterministic": True,
        "flat_sha256": hashlib.sha256(flat.tobytes()).hexdigest(),
        "train_shards": {k: [s[0] for s in v] for k, v in train.items()},
        "validation_shards": {k: [s[0] for s in v] for k, v in val.items()},
    }
    (a.out / "train.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({"validation_loss": vl, "flat_sha256": rec["flat_sha256"]}))


if __name__ == "__main__":
    main()
