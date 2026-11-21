"""DL4b (#42) step 0, GPU side (research/dl4b-step0.md section 3).

Bias-free dilated context-aggregation network (Conv and Relu only), arms N1
(one pass) and NP (iterated, image-domain operator with the grid PSF G in
training). Normalisation, update and positivity stay outside the network:
m <- max(m + s f(r/s, m/s), 0), s the residual's robust rms.

train PACKS OUT --arm N1|NP --seed K --hours H [--steps-max S] [--yield-at HH:MM ...]
    Resumes from OUT/ckpt.pt. Checkpoints and validates (image-domain, the
    validation fields in the packs) every 15 minutes; keeps OUT/best.pt by
    validation score (mean recovery - false flux). Exit 0: budget or steps
    done; 3: yielded (GPU_CHECK said so, or a yield window); rerun resumes.

resume-test PACKS OUT
    200 steps straight against 100 + resume + 100: weights must be equal.

export CKPT OUT_ONNX
    ONNX opset 17 (Conv, Relu), checked against PyTorch with onnxruntime.

Data order and augmentation are stateless functions of (seed, step), so a
resume needs only the step and the model and optimiser state.
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import torch
import torch.nn.functional as F
from torch import nn

DIL = (1, 1, 2, 4, 8, 16, 32, 64, 128, 1, 1)
HIDDEN = 32
CELL_DEG = 1.6 / 3600
K_TRAIN = 4
P_MAX = 6
BATCH = 16
LR = 1e-3
CKPT_S = 15 * 60
SAST = dt.timezone(dt.timedelta(hours=2))


class CAN(nn.Module):
    def __init__(self, hidden=HIDDEN, dil=DIL):
        super().__init__()
        layers, c = [], 2
        for d in dil:
            layers += [nn.Conv2d(c, hidden, 3, padding=d, dilation=d, bias=False), nn.ReLU()]  # fmt: skip
            c = hidden
        layers.append(nn.Conv2d(c, 1, 1, bias=False))
        self.net = nn.Sequential(*layers)
        # He init (amendment 3): torch's default gave a gain of 5e-6 through 11 layers
        # and a zero output layer, so training starts at the empty model with
        # healthy hidden features (He alone started 300x above it and collapsed)
        for mod in self.net:
            if isinstance(mod, nn.Conv2d):
                if mod.out_channels > 1:
                    nn.init.kaiming_normal_(mod.weight, nonlinearity="relu")
                else:
                    nn.init.zeros_(mod.weight)

    def forward(self, x):
        return self.net(x)


def robust_rms(x):
    flat = x.flatten(1)
    med = _median(flat)[:, None]
    mad = _median((flat - med).abs())
    return (1.4826 * mad).clamp_min(1e-12).view(-1, 1, 1)


def _median(flat):
    """numpy's median (mean of the two middle values), deterministic on CUDA."""
    n = flat.shape[1]
    srt = flat.sort(dim=1).values
    if n % 2:
        return srt[:, n // 2]
    return 0.5 * (srt[:, n // 2 - 1] + srt[:, n // 2])


def step_model(net, r, m, raw=False):
    """m <- max(m + s f(r/s, m/s), 0); with raw=True also the unclipped update
    (the training loss is taken on it, amendment 3)."""
    s = robust_rms(r)
    x = torch.stack([r / s[:, :, :], m / s[:, :, :]], dim=1)
    u = m + s * net(x)[:, 0]
    return (u, torch.relu(u)) if raw else torch.relu(u)


def gconv(m, Gf):
    """G (*) m for m (B,256,256); Gf = rfft2(ifftshift(G)) (B,512,257)."""
    M = F.pad(m, (0, 256, 0, 256))
    return torch.fft.irfft2(torch.fft.rfft2(M) * Gf, s=(512, 512))[:, :256, :256]


def beam_kernels(beam, n=33):
    """Gaussian clean beams (B,n,n), peak 1; beam rows (maj, min, pa) in deg.
    Orientation: y north (+row), x east = -column (CDELT1 < 0); pa from north
    through east."""
    b = torch.as_tensor(beam, dtype=torch.float64)
    sx = b[:, 1] / CELL_DEG / 2.3548
    sy = b[:, 0] / CELL_DEG / 2.3548
    pa = torch.deg2rad(b[:, 2])
    h = n // 2
    yy, xx = torch.meshgrid(torch.arange(-h, h + 1.0, dtype=torch.float64), torch.arange(-h, h + 1.0, dtype=torch.float64), indexing="ij")  # fmt: skip
    east, north = -xx, yy
    c, s_ = torch.cos(pa)[:, None, None], torch.sin(pa)[:, None, None]
    u = east * c - north * s_
    v = east * s_ + north * c
    k = torch.exp(-0.5 * ((u / sx[:, None, None]) ** 2 + (v / sy[:, None, None]) ** 2))
    return k.float()


def bconv(x, k):
    """Per-sample beam convolution (B,256,256) with kernels (B,n,n)."""
    B, n = x.shape[0], k.shape[-1]
    y = F.conv2d(x[None], k[:, None].flip(-1, -2), padding=n // 2, groups=B)
    return y[0]


class Data:
    def __init__(self, packs, device, psfg=None):
        files = sorted(Path(packs).glob("pack-*.npz"))
        cols = {k: [] for k in ("seed", "flux", "split", "dirty", "tidx", "tval", "comps", "beam")}  # fmt: skip
        for f in files:
            z = np.load(f)
            for k, v in cols.items():
                v.append(z[k])
        c = {k: np.concatenate(v) for k, v in cols.items()}
        self.gseed = np.unique(c["seed"])
        gidx = {int(s): i for i, s in enumerate(self.gseed)}
        self.gi = np.array([gidx[int(s)] for s in c["seed"]])
        self.seed, self.flux, self.split = c["seed"], c["flux"], c["split"]
        self.comps, self.beam = c["comps"], c["beam"]
        self.tidx, self.tval = c["tidx"], c["tval"]
        self.train = np.flatnonzero(self.split == 0)
        self.val = np.flatnonzero(self.split == 1)
        self.device = device
        self.dirty = torch.from_numpy(c["dirty"]).to(device)
        self.G = None
        if psfg:
            # G per seed from examples/dl4b_step0.py psfg shards (seeds 10k..10k+9)
            G = np.empty((len(self.gseed), 512, 512), np.float32)
            for k in np.unique(self.gseed // 10):
                g = np.load(Path(psfg) / f"psfg-{k:03d}.npz")["G"]
                for s in self.gseed[self.gseed // 10 == k]:
                    G[gidx[int(s)]] = g[int(s) % 10]
            self.G = torch.from_numpy(G).to(device)
        self.kern = beam_kernels(self.beam).to(device)
        self.s0 = torch.cat([robust_rms(self.dirty[i : i + 256]).view(-1) for i in range(0, len(self.dirty), 256)])  # fmt: skip
        torch.cuda.reset_peak_memory_stats()

    def truth(self, idx):
        t = torch.zeros(len(idx), 256 * 256, device=self.device)
        ti = torch.from_numpy(self.tidx[idx]).to(self.device).long()
        tv = torch.from_numpy(self.tval[idx]).to(self.device)
        ok = ti >= 0
        rows = torch.arange(len(idx), device=self.device)[:, None].expand_as(ti)
        t[rows[ok], ti[ok]] = tv[ok]
        return t.view(-1, 256, 256)

    def batch(self, idx, aug):
        """Fields idx with augmentation codes aug (0-7: transpose bit 4, flip-y 2,
        flip-x 1). G is flipped about offset 0 (flip then roll by 1)."""
        d, t = self.dirty[idx], self.truth(idx)
        k = self.kern[idx]
        G = self.G[self.gi[idx]] if self.G is not None else None
        for j, a in enumerate(aug):
            dims_img, dims = [], []
            if a & 2:
                dims_img.append(0)
            if a & 1:
                dims_img.append(1)
            if dims_img:
                d[j] = d[j].flip(dims_img).clone()
                t[j] = t[j].flip(dims_img).clone()
                k[j] = k[j].flip(dims_img).clone()
                if G is not None:
                    g = G[j].flip(dims_img)
                    G[j] = g.roll([1] * len(dims_img), dims_img)
            if a & 4:
                d[j], t[j], k[j] = d[j].T.clone(), t[j].T.clone(), k[j].T.clone()
                if G is not None:
                    G[j] = G[j].T.clone()
            del dims
        Gf = (
            None if G is None else torch.fft.rfft2(torch.fft.ifftshift(G, dim=(-2, -1)))
        )
        return d, t, Gf, k, self.s0[idx]


def order(seed, n, step):
    """Field index and augmentation code for each sample of this step."""
    per = n // BATCH
    epoch, pos = divmod(step, per)
    perm = np.random.default_rng([seed, epoch]).permutation(n)
    idx = perm[pos * BATCH : (pos + 1) * BATCH]
    aug = np.random.default_rng([seed, epoch, pos, 7]).integers(0, 8, BATCH)
    return idx, aug


def loss_fn(net, arm, d, t, Gf, k, s0):
    m = torch.zeros_like(d)
    r = d
    passes = 1 if arm == "N1" else K_TRAIN
    total = 0.0
    tb = bconv(t, k)
    for p in range(passes):
        u, m = step_model(net, r, m, raw=True)
        # squared error at beam resolution (amendment 3; L1 stayed at the empty model)
        e = (bconv(u, k) - tb) / s0[:, None, None]
        total = total + (e**2).flatten(1).sum(1).mean()
        if p + 1 < passes:
            m = m.detach()
            r = d - gconv(m, Gf)
    return total / passes


def empty_loss(t, k, s0):
    return float(((bconv(t, k) / s0[:, None, None]) ** 2).flatten(1).sum(1).mean())


def metrics(model, comps, beam_px):
    """recovery (within one beam of an in-image source, nearest of all 100) and
    false flux (beyond two beams of all 100), both / in-image true flux."""
    yy, xx = np.nonzero(model)
    vals = model[yy, xx]
    pos = comps[:, :2]
    inside = comps[:, 3] > 0
    tin = comps[inside, 2].sum()
    if tin <= 0:
        return np.nan, np.nan
    if vals.size == 0:
        return 0.0, 0.0
    dd = (xx[:, None] - pos[None, :, 0]) ** 2 + (yy[:, None] - pos[None, :, 1]) ** 2
    near = dd.argmin(1)
    dist = np.sqrt(dd[np.arange(len(near)), near])
    rec = vals[(dist <= beam_px) & inside[near]].sum() / tin
    false = np.abs(vals[dist > 2 * beam_px]).sum() / tin
    return float(rec), float(false)


@torch.no_grad()
def run_passes(net, arm, d, Gf, p_max=P_MAX):
    m = torch.zeros_like(d)
    r = d
    np_ = 1 if arm == "N1" else p_max
    used = torch.zeros(d.shape[0], dtype=torch.int32, device=d.device)
    done = torch.zeros(d.shape[0], dtype=torch.bool, device=d.device)
    for _ in range(np_):
        m_new = step_model(net, r, m)
        change = (m_new - m).abs().flatten(1).sum(1)
        m = torch.where(done[:, None, None], m, m_new)
        used = used + (~done).int()
        done = done | (change < 0.01 * m_new.abs().flatten(1).sum(1))
        if Gf is not None:
            r = d - gconv(m, Gf)
    return m, used


def validate(net, arm, data):
    net.eval()
    recs, fals, npix = [], [], []
    for i in range(0, len(data.val), BATCH):
        idx = data.val[i : i + BATCH]
        d, _, Gf, _, _ = data.batch(idx, np.zeros(len(idx), int))
        m, _ = run_passes(net, arm, d, Gf)
        mm = m.cpu().numpy()
        for j, f in enumerate(idx):
            bpx = data.beam[f, 0] / CELL_DEG
            r_, f_ = metrics(mm[j], data.comps[f], bpx)
            recs.append(r_)
            fals.append(f_)
            npix.append(int((mm[j] > 0).sum()))
    net.train()
    rec, fal = float(np.nanmean(recs)), float(np.nanmean(fals))
    return {
        "recovery": rec,
        "false": fal,
        "score": -abs(rec - 1.0) - fal,  # amendment 4: two-sided
        "npix_median": float(np.median(npix)),
    }


def setup(seed):
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def make(seed, total_steps, device):
    setup(seed)
    net = CAN().to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=LR, weight_decay=0.0)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: 0.5 * (1 + np.cos(np.pi * min(s, total_steps) / total_steps)))  # fmt: skip
    return net, opt, sched


def save(path, net, opt, sched, state):
    tmp = Path(str(path) + ".tmp")
    torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "state": state, "rng_cuda": torch.cuda.get_rng_state_all(), "rng": torch.get_rng_state()}, tmp)  # fmt: skip
    os.replace(tmp, path)


def in_window(now, windows):
    hm = now.strftime("%H:%M")
    return any(a <= hm < b for a, b in windows)


def gpu_check():
    cmd = os.environ.get("GPU_CHECK")
    if not cmd:
        return 0
    return subprocess.run(cmd, shell=True, check=False).returncode


def train(args, data=None):
    device = torch.device("cuda")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "train.log", "a")  # noqa: SIM115

    def say(msg):
        line = f"{dt.datetime.now(SAST):%Y-%m-%dT%H:%M:%S} {msg}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    if data is None:
        t = time.perf_counter()
        data = Data(args.packs, device, args.psfg)
        if args.arm == "NP" and data.G is None:
            sys.exit("NP needs --psfg")
        say(f"data: {len(data.train)} train, {len(data.val)} val fields, {len(data.gseed)} G; load {time.perf_counter() - t:.0f} s; GPU mem {torch.cuda.memory_allocated() / 2**30:.2f} GiB")  # fmt: skip
    total_steps = args.steps_total
    net, opt, sched = make(args.seed, total_steps, device)
    state = {"step": 0, "train_s": 0.0, "best": -1e9, "history": []}
    ck = out / "ckpt.pt"
    if ck.exists():
        c = torch.load(ck, weights_only=False)
        net.load_state_dict(c["net"])
        opt.load_state_dict(c["opt"])
        sched.load_state_dict(c["sched"])
        state = c["state"]
        torch.cuda.set_rng_state_all(c["rng_cuda"])
        torch.set_rng_state(c["rng"])
        say(f"resume at step {state['step']}, train {state['train_s']:.0f} s")
    windows = [w.split("-") for w in (args.yield_window or [])]
    budget = args.hours * 3600
    last = time.perf_counter()
    t_seg = time.perf_counter()
    rc = 0
    while state["step"] < min(total_steps, args.steps_max or total_steps):
        if state["train_s"] + (time.perf_counter() - t_seg) >= budget:
            state["train_s"] += time.perf_counter() - t_seg
            t_seg = time.perf_counter()
            say("budget reached")
            break
        idx, aug = order(args.seed, len(data.train), state["step"])
        d, t, Gf, k, s0 = data.batch(data.train[idx], aug)
        loss = loss_fn(net, args.arm, d, t, Gf, k, s0)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        sched.step()
        state["step"] += 1
        if state["step"] % 50 == 0:
            ratio = float(loss.detach()) / empty_loss(t, k, s0)
            state.setdefault("ratio", []).append([state["step"], ratio])
            if state["step"] == args.abort_step and ratio > 0.9:
                say(
                    f"abort: loss / empty-model loss = {ratio:.3f} at step {state['step']}"
                )
                save(ck, net, opt, sched, state)
                log.close()
                return 4
        now = time.perf_counter()
        stop = in_window(dt.datetime.now(SAST), windows)
        first = state["step"] == args.first_val
        if now - last >= CKPT_S or stop or first or state["step"] >= total_steps:
            state["train_s"] += now - t_seg
            t_seg = now
            v = (
                validate(net, args.arm, data)
                if args.validate
                else {"score": float("nan")}
            )
            state["history"].append({"step": state["step"], "train_s": state["train_s"], "loss": float(loss), **v})  # fmt: skip
            if args.validate and v["score"] > state["best"]:
                state["best"] = v["score"]
                save(out / "best.pt", net, opt, sched, state)
            save(ck, net, opt, sched, state)
            say(
                f"step {state['step']} loss {float(loss):.4f} val {v} train {state['train_s']:.0f} s peak {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB"
            )
            t_seg = time.perf_counter()
            last = t_seg
            if stop:
                say("yield window: exit 3")
                rc = 3
                break
            if gpu_check() == 3:
                say("GPU_CHECK: yield, exit 3")
                rc = 3
                break
    else:
        state["train_s"] += time.perf_counter() - t_seg
        save(ck, net, opt, sched, state)
        say(f"steps done at {state['step']}")
    if rc == 0:
        if args.validate:
            final_validate(net, opt, sched, state, args.arm, data, out, say)
        save(ck, net, opt, sched, state)
        (out / "done.json").write_text(json.dumps(state, indent=1))
    log.close()
    return rc


def final_validate(net, opt, sched, state, arm, data, out, say):
    """Validate the last weights if the last validation was at an earlier step."""
    hist = state["history"]
    if hist and hist[-1]["step"] == state["step"]:
        return
    v = validate(net, arm, data)
    state["history"].append({"step": state["step"], "train_s": state["train_s"], "final": True, **v})  # fmt: skip
    if v["score"] > state["best"]:
        state["best"] = v["score"]
        save(out / "best.pt", net, opt, sched, state)
    say(f"final validation at step {state['step']}: {v}")


def finalval(args):
    """Final validation for a run that ended without one (budget hit before a checkpoint)."""
    device = torch.device("cuda")
    out = Path(args.out)
    data = Data(args.packs, device, args.psfg)
    c = torch.load(out / "ckpt.pt", weights_only=False)
    net = CAN().to(device)
    net.load_state_dict(c["net"])
    opt = torch.optim.AdamW(net.parameters(), lr=LR, weight_decay=0.0)
    opt.load_state_dict(c["opt"])
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: 1.0)
    state = c["state"]
    with open(out / "train.log", "a") as log:

        def say(msg):
            line = f"{dt.datetime.now(SAST):%Y-%m-%dT%H:%M:%S} {msg}"
            print(line, flush=True)
            log.write(line + chr(10))

        final_validate(net, opt, sched, state, args.arm, data, out, say)
    c["state"] = state
    torch.save(c, out / "ckpt.pt")
    (out / "done.json").write_text(json.dumps(state, indent=1))


def resume_test(args):
    device = torch.device("cuda")
    data = Data(args.packs, device, args.packs + "-psfg")
    out = Path(args.out)
    base = {"packs": args.packs, "arm": "NP", "seed": 11, "hours": 10.0, "steps_total": 200, "validate": False, "yield_window": None, "psfg": None, "first_val": -1, "abort_step": -1}  # fmt: skip
    a = argparse.Namespace(out=str(out / "straight"), steps_max=200, **base)
    train(a, data)
    b = argparse.Namespace(out=str(out / "resumed"), steps_max=100, **base)
    train(b, data)
    b.steps_max = 200
    train(b, data)
    wa = torch.load(out / "straight" / "ckpt.pt", weights_only=False)["net"]
    wb = torch.load(out / "resumed" / "ckpt.pt", weights_only=False)["net"]
    eq = all(torch.equal(wa[k], wb[k]) for k in wa)
    maxd = max(float((wa[k] - wb[k]).abs().max()) for k in wa)
    res = {"bit_identical": eq, "max_abs_diff": maxd}
    (out / "resume-test.json").write_text(json.dumps(res))
    print(res)
    return 0 if eq else 1


def export(args):
    import onnxruntime as ort

    c = torch.load(args.ckpt, weights_only=False, map_location="cpu")
    net = CAN()
    net.load_state_dict(c["net"])
    net.eval()
    x = torch.randn(1, 2, 256, 256)
    torch.onnx.export(net, x, args.out_onnx, opset_version=17, input_names=["x"], output_names=["y"], dynamo=False)  # fmt: skip
    import onnx

    ops = sorted({n.op_type for n in onnx.load(args.out_onnx).graph.node})
    y = net(x).detach().numpy()
    yo = ort.InferenceSession(args.out_onnx).run(None, {"x": x.numpy()})[0]
    res = {"ops": ops, "max_abs_diff_vs_torch": float(np.abs(y - yo).max()), "weights": int(sum(p.numel() for p in net.parameters()))}  # fmt: skip
    print(res)
    Path(str(args.out_onnx) + ".json").write_text(json.dumps(res))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("train")
    p.add_argument("packs")
    p.add_argument("out")
    p.add_argument("--arm", choices=("N1", "NP"), required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--hours", type=float, required=True)
    p.add_argument(
        "--steps-total", type=int, required=True, help="cosine schedule length"
    )
    p.add_argument("--steps-max", type=int)
    p.add_argument("--yield-window", action="append", help="HH:MM-HH:MM in SAST")
    p.add_argument("--no-validate", dest="validate", action="store_false")
    p.add_argument("--psfg", help="directory of psfg-KKK.npz (NP)")
    p.add_argument("--batch", type=int, default=16)
    p.add_argument(
        "--first-val", type=int, default=500, help="also validate at this step"
    )
    p.add_argument(
        "--abort-step", type=int, default=1000, help="exit 4 if loss/empty > 0.9 here"
    )
    p.set_defaults(func=train)
    p = sub.add_parser("finalval")
    p.add_argument("packs")
    p.add_argument("out")
    p.add_argument("--arm", choices=("N1", "NP"), required=True)
    p.add_argument("--psfg")
    p.set_defaults(func=finalval)
    p = sub.add_parser("resume-test")
    p.add_argument("packs")
    p.add_argument("out")
    p.set_defaults(func=resume_test)
    p = sub.add_parser("export")
    p.add_argument("ckpt")
    p.add_argument("out_onnx")
    p.set_defaults(func=export)
    a = ap.parse_args()
    global BATCH
    BATCH = getattr(a, "batch", BATCH)
    sys.exit(a.func(a) or 0)


if __name__ == "__main__":
    main()
