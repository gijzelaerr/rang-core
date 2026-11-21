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


def npz_memmap(path, name):
    """A member of an uncompressed .npz (np.savez) as a read-only memmap: the
    shards stay in the page cache, shared between processes, not in each
    trainer's heap (F6 on nash, 2026-11-21: 117 GB of shards per trainer)."""
    import zipfile

    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo(f"{name}.npy")
        if info.compress_type != zipfile.ZIP_STORED:
            return np.load(path)[name]
    with open(path, "rb") as f:
        f.seek(info.header_offset)
        head = f.read(30)
        nlen = int.from_bytes(head[26:28], "little")
        xlen = int.from_bytes(head[28:30], "little")
        f.seek(info.header_offset + 30 + nlen + xlen)
        version = np.lib.format.read_magic(f)
        read = (
            np.lib.format.read_array_header_1_0
            if version == (1, 0)
            else np.lib.format.read_array_header_2_0
        )
        shape, order, dtype = read(f)
        offset = f.tell()
    return np.memmap(path, dtype, "r", offset, shape, order="F" if order else "C")


def load(role_dir, mmap=True):
    shards = {"real": [], "sim": []}
    for p in sorted(Path(role_dir).glob("*.npz")):
        z = np.load(p)
        kind = str(z["kind"])
        if mmap:
            x, y = npz_memmap(p, "x"), npz_memmap(p, "y")
        else:
            x, y = z["x"], z["y"]
        shards[kind].append((p.name, x, y))
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


class Run:
    """One seed's model, optimiser, batch generator and checkpoint. Several runs
    can share one process (and one copy of the shards); each run's arithmetic
    is the same as alone, since nothing is shared between runs but the
    read-only shards."""

    def __init__(self, seed, out, nplanes, device):
        self.seed, self.out, self.device = seed, out, device
        out.mkdir(parents=True, exist_ok=True)
        self.net = f5net.build(nplanes, True, seed=seed).to(device)
        self.opt = torch.optim.Adam(
            self.net.parameters(), lr=RATE, betas=(0.9, 0.999), eps=1e-8
        )
        self.rng = np.random.default_rng(1000 + seed)
        self.ck = out / "ckpt.pt"
        self.step, self.curve, self.run, self.resumed = 0, [], 0.0, []
        if self.ck.exists():
            st = load_ckpt(self.ck)
            self.net.load_state_dict(st["net"])
            self.opt.load_state_dict(st["opt"])
            self.rng.bit_generator.state = st["rng"]
            self.step, self.curve, self.run = st["step"], st["curve"], st["run"]
            self.resumed = [*st["resumed"], self.step]
            print(json.dumps({"seed": seed, "resumed_at": self.step}), flush=True)

    def train_step(self, train, t1):
        self.step += 1
        rng = self.rng
        kind = "real" if rng.random() < 0.5 else "sim"
        pool = train[kind] or train["sim" if kind == "real" else "real"]
        shard = pool[rng.integers(0, len(pool))]
        xb, yb = batch(rng, shard)
        x = torch.from_numpy(xb).to(self.device)
        y = torch.from_numpy(yb).to(self.device)
        loss = f5net.bce(self.net(x), y)
        self.opt.zero_grad(set_to_none=True)
        loss.backward()
        self.opt.step()
        if self.step % 50 == 0:
            self.run += float(loss.detach())
        if self.step % EVERY_STEPS == 0:
            self.curve.append(
                {
                    "step": self.step,
                    "loss": self.run / 20,
                    "seconds": time.perf_counter() - t1,
                }
            )
            self.run = 0.0
            print(json.dumps({"seed": self.seed, **self.curve[-1]}), flush=True)

    def checkpoint(self):
        save_ckpt(
            self.ck,
            {
                "net": self.net.state_dict(),
                "opt": self.opt.state_dict(),
                "rng": self.rng.bit_generator.state,
                "step": self.step,
                "curve": self.curve,
                "run": self.run,
                "resumed": self.resumed,
            },
        )

    def finish(self, val, a, nplanes, t_load, t_train, train):
        vl = validation_loss(self.net, val, self.device)
        arrays = f5net.to_arrays(self.net)
        flat = f5net.flat_from_arrays(arrays)
        header = {
            "stage": "flag",
            "architecture": "f5-n5",
            "nplanes": nplanes,
            "seed": self.seed,
            "steps": a.steps,
            "validation_loss": vl,
            "shards": str(a.shards),
        }
        np.savez(
            self.out / "weights.npz",
            flat=flat,
            header=json.dumps(header),
            **{f"w{i}": w for i, (w, _) in enumerate(arrays)},
            **{f"b{i}": b for i, (_, b) in enumerate(arrays)},
        )
        cuda = self.device.startswith("cuda")
        rec = {
            **header,
            "batch": BATCH,
            "width": WIDTH,
            "rate": RATE,
            "weights": int(flat.size),
            "curve": self.curve,
            "resumed_at": self.resumed,
            "load_seconds": t_load,
            "train_seconds_this_run": t_train,
            "seeds_in_process": a.seed,
            "device": self.device,
            "gpu": torch.cuda.get_device_name(0) if cuda else None,
            "peak_vram_allocated_bytes": int(torch.cuda.max_memory_allocated())
            if cuda
            else None,
            "peak_vram_reserved_bytes": int(torch.cuda.max_memory_reserved())
            if cuda
            else None,
            "torch": torch.__version__,
            "deterministic": True,
            "flat_sha256": hashlib.sha256(flat.tobytes()).hexdigest(),
            "train_shards": {k: [s[0] for s in v] for k, v in train.items()},
            "validation_shards": {k: [s[0] for s in v] for k, v in val.items()},
        }
        (self.out / "train.json").write_text(json.dumps(rec, indent=1))
        print(
            json.dumps(
                {
                    "seed": self.seed,
                    "validation_loss": vl,
                    "flat_sha256": rec["flat_sha256"],
                }
            )
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shards", type=Path)
    ap.add_argument(
        "out", type=Path, help="one seed: its directory; several: OUT/seed-K each"
    )
    ap.add_argument(
        "--seed", required=True, help="a seed, or several comma-separated (one process)"
    )
    ap.add_argument("--steps", type=int, default=30000)
    ap.add_argument(
        "--stop-at", type=int, help="save and stop after this step (resume test)"
    )
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args()
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    seeds = [int(x) for x in str(a.seed).split(",")]
    t0 = time.perf_counter()
    train = load(a.shards / "train")
    val = load(a.shards / "validation")
    t_load = time.perf_counter() - t0
    first = (train["real"] or train["sim"])[0][1]
    nplanes = int(first.shape[-1])
    outs = [a.out] if len(seeds) == 1 else [a.out / f"seed-{s}" for s in seeds]
    runs = [
        Run(s, o, nplanes, a.device)
        for s, o in zip(seeds, outs, strict=True)
        if not (o / "weights.npz").exists()
    ]
    t1 = time.perf_counter()
    last = time.perf_counter()
    while any(r.step < a.steps for r in runs):
        for r in runs:
            if r.step < a.steps:
                r.train_step(train, t1)
        steps = {r.step for r in runs}
        due = (
            any(s % EVERY_STEPS == 0 for s in steps)
            or time.perf_counter() - last >= EVERY_SECONDS
        )
        stop = a.stop_at is not None and a.stop_at in steps
        if due or stop or all(r.step >= a.steps for r in runs):
            for r in runs:
                r.checkpoint()
            last = time.perf_counter()
            if stop:
                print(json.dumps({"stopped_at": a.stop_at}), flush=True)
                return
            if any(r.step < a.steps for r in runs) and gpu_yield():
                print(json.dumps({"yield_at": sorted(steps)}), flush=True)
                raise SystemExit(3)
    t_train = time.perf_counter() - t1
    for r in runs:
        r.finish(val, a, nplanes, t_load, t_train, train)


if __name__ == "__main__":
    main()
