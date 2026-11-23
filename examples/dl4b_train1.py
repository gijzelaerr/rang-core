"""DL4b (#42) step 1, GPU side (research/dl4b-step1.md section 4).

Step 0's bias-free CAN (examples/dl4b_train.py) at 48 channels, trained on
512^2 crops of the 4096^2 training skies: dirty crop, truth on the beam B * T
crop (rml_gap_score.truth_on_beam, Jy per pixel) and the central 1024^2 of the
sky's PSF, which is the exact operator for a model confined to the crop.
K_TRAIN passes; loss on the unclipped update: squared error of B * u against
B * T, normalised by the crop's dirty robust rms. Crops are sampled statelessly
from (seed, step); validation on fixed crops of V1-V4, score the relative L2 on
the beam (lower is better).

train SKIES OUT --seed K --hours H --steps-total S --batch B [--yield-window HH:MM-HH:MM ...]
resume-test SKIES OUT
export CKPT OUT_ONNX
"""

import argparse
import datetime as dt
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dl4b_train as T0

HIDDEN = 48
CROP, PATCH, SIZE = 512, 1024, 4096
K_TRAIN = 4
K_VAL = 3
LR = 1e-3
WARMUP = 500  # steps (amendment 1)
CLIP = 1.0  # gradient-norm clip (amendment 1)
CKPT_S = 15 * 60
FWHM_TO_SIGMA = 1 / (2 * math.sqrt(2 * math.log(2)))
VAL_CROPS = 16  # per validation sky


class Skies:
    """Training skies in host memory; validation crops fixed."""

    def __init__(self, root, device):
        self.device = device
        dirs = sorted(p for p in Path(root).iterdir() if (p / "bt.npy").exists())
        tr = [d for d in dirs if d.name.startswith("T")]
        va = [d for d in dirs if d.name.startswith("V")]
        self.train = self._load(tr)
        self.val = self._val(self._load(va))

    def _load(self, dirs):
        out = []
        for d in dirs:
            b = json.loads((d / "beam.json").read_text())["beam_px"]
            out.append({"name": d.name, "dirty": np.load(d / "dirty.npy", mmap_mode=None), "bt": np.load(d / "bt.npy"), "psf": np.load(d / "psf1024.npy"), "beam_px": b})  # fmt: skip
        return out

    def _val(self, skies):
        rng = np.random.default_rng(20261121)
        crops = []
        for i, s in enumerate(skies):
            for _ in range(VAL_CROPS):
                y0, x0 = rng.integers(0, SIZE - CROP, 2)
                crops.append((i, int(y0), int(x0)))
        self.val_skies = skies
        return crops

    def batch_from(self, skies, picks, aug):
        d = np.stack(
            [skies[i]["dirty"][y : y + CROP, x : x + CROP] for i, y, x in picks]
        )
        t = np.stack([skies[i]["bt"][y : y + CROP, x : x + CROP] for i, y, x in picks])
        p = np.stack([skies[i]["psf"] for i, _, _ in picks])
        bpx = np.array([skies[i]["beam_px"] for i, _, _ in picks])
        dev = self.device
        d, t, p = (torch.from_numpy(np.ascontiguousarray(a)).to(dev) for a in (d, t, p))
        for j, a in enumerate(aug):
            dims = [k for bit, k in ((2, 0), (1, 1)) if a & bit]
            if dims:
                d[j] = d[j].flip(dims).clone()
                t[j] = t[j].flip(dims).clone()
                p[j] = p[j].flip(dims).roll([1] * len(dims), dims).clone()
            if a & 4:
                d[j], t[j], p[j] = d[j].T.clone(), t[j].T.clone(), p[j].T.clone()
        pf = torch.fft.rfft2(torch.fft.ifftshift(p, dim=(-2, -1)))
        bf = beam_ft(torch.as_tensor(bpx, device=dev), PATCH)
        s0 = T0.robust_rms(d).view(-1)
        return d, t, pf, bf, s0

    def sample(self, seed, step, batch):
        rng = np.random.default_rng([seed, step, 11])
        i = rng.integers(0, len(self.train), batch)
        yx = rng.integers(0, SIZE - CROP, (batch, 2))
        aug = rng.integers(0, 8, batch)
        return [(int(a), int(b), int(c)) for a, (b, c) in zip(i, yx)], aug


def beam_ft(beam_px, n):
    """Area-normalised circular Gaussian B (FWHM beam_px) on an n^2 grid, rfft2 form."""
    ky = torch.fft.fftfreq(n, device=beam_px.device)[:, None]
    kx = torch.fft.rfftfreq(n, device=beam_px.device)[None, :]
    sb = (beam_px * FWHM_TO_SIGMA)[:, None, None]
    return torch.exp(-2 * math.pi**2 * sb**2 * (kx**2 + ky**2)).float()


def conv_pad(x, kf):
    """Linear convolution of crops (B,512,512) with a kernel given as rfft2 of an
    ifftshifted 1024^2 kernel (offsets -512..511), output on the crop."""
    X = torch.fft.rfft2(F.pad(x, (0, PATCH - CROP, 0, PATCH - CROP)))
    return torch.fft.irfft2(X * kf, s=(PATCH, PATCH))[:, :CROP, :CROP]


def beam_conv(x, bf):
    # bf is the transform itself (centred at offset 0), no shift needed
    return conv_pad(x, bf)


def loss_fn(net, d, t, pf, bf, s0, passes=K_TRAIN):
    m = torch.zeros_like(d)
    r = d
    total = 0.0
    for p in range(passes):
        u, m = T0.step_model(net, r, m, raw=True)
        e = (beam_conv(u, bf) - t) / s0[:, None, None]
        total = total + (e**2).flatten(1).sum(1).mean()
        if p + 1 < passes:
            m = m.detach()
            r = d - conv_pad(m, pf)
    return total / passes


def loss_backward(net, d, t, pf, bf, s0, passes=K_TRAIN):
    """loss_fn's gradient with one backward per pass: the passes are detached from
    each other, so the gradients are the same and only one pass's graph is held."""
    m = torch.zeros_like(d)
    r = d
    total = 0.0
    for p in range(passes):
        u, m = T0.step_model(net, r, m, raw=True)
        e = (beam_conv(u, bf) - t) / s0[:, None, None]
        lp = (e**2).flatten(1).sum(1).mean() / passes
        lp.backward()
        total += float(lp.detach())
        if p + 1 < passes:
            m = m.detach()
            with torch.no_grad():
                r = d - conv_pad(m, pf)
    return total


def empty_loss(t, s0):
    return float(((t / s0[:, None, None]) ** 2).flatten(1).sum(1).mean())


@torch.no_grad()
def validate(net, data):
    net.eval()
    num = den = 0.0
    for i in range(0, len(data.val), 16):
        picks = data.val[i : i + 16]
        d, t, pf, bf, _ = data.batch_from(
            data.val_skies, picks, np.zeros(len(picks), int)
        )
        m = torch.zeros_like(d)
        r = d
        for _ in range(K_VAL):
            m = T0.step_model(net, r, m)
            r = d - conv_pad(m, pf)
        num += float(((beam_conv(m, bf) - t) ** 2).sum())
        den += float((t**2).sum())
    net.train()
    rel = math.sqrt(num / den)
    return {"rel_l2": rel, "score": -rel}


def train(args, data=None):
    T0.BATCH = args.batch
    device = torch.device("cuda")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "train.log", "a")  # noqa: SIM115

    def say(msg):
        line = f"{dt.datetime.now(T0.SAST):%Y-%m-%dT%H:%M:%S} {msg}"
        print(line, flush=True)
        log.write(line + chr(10))
        log.flush()

    if data is None:
        t = time.perf_counter()
        data = Skies(args.skies, device)
        say(f"data: {len(data.train)} train skies, {len(data.val)} val crops; load {time.perf_counter() - t:.0f} s")  # fmt: skip
    T0.setup(args.seed)
    net = T0.CAN(hidden=HIDDEN).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=LR, weight_decay=0.0)
    S = args.steps_total
    W = WARMUP

    def lr_at(s):
        # linear warm-up over WARMUP steps, then cosine to 0 (amendment 1)
        if s < W:
            return (s + 1) / W
        return 0.5 * (1 + np.cos(np.pi * min(s - W, S - W) / max(S - W, 1)))

    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_at)
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
    windows = T0.parse_windows(args.yield_window)
    budget = args.hours * 3600
    t_seg = last = time.perf_counter()
    rc = 0
    stop_at = min(S, args.steps_max or S)
    while state["step"] < stop_at:
        if state["train_s"] + (time.perf_counter() - t_seg) >= budget:
            state["train_s"] += time.perf_counter() - t_seg
            t_seg = time.perf_counter()
            say("budget reached")
            break
        picks, aug = data.sample(args.seed, state["step"], args.batch)
        d, t, pf, bf, s0 = data.batch_from(data.train, picks, aug)
        opt.zero_grad(set_to_none=True)
        loss = torch.tensor(loss_backward(net, d, t, pf, bf, s0))
        torch.nn.utils.clip_grad_norm_(net.parameters(), CLIP)
        opt.step()
        sched.step()
        state["step"] += 1
        if state["step"] % 50 == 0:
            ratio = float(loss.detach()) / empty_loss(t, s0)
            state.setdefault("ratio", []).append([state["step"], ratio])
            if state["step"] == args.abort_step and ratio > 0.9:
                say(f"abort: loss / empty-model loss = {ratio:.3f}")
                T0.save(ck, net, opt, sched, state)
                log.close()
                return 4
        now = time.perf_counter()
        stop = T0.in_window(dt.datetime.now(T0.SAST), windows)
        if now - last >= CKPT_S or stop or state["step"] == args.first_val or state["step"] >= stop_at:  # fmt: skip
            state["train_s"] += now - t_seg
            v = validate(net, data) if args.validate else {"score": float("nan")}
            state["history"].append({"step": state["step"], "train_s": state["train_s"], "loss": float(loss.detach()), **v})  # fmt: skip
            if args.validate and v["score"] > state["best"]:
                state["best"] = v["score"]
                T0.save(out / "best.pt", net, opt, sched, state)
            T0.save(ck, net, opt, sched, state)
            say(f"step {state['step']} loss {float(loss.detach()):.4f} val {v} train {state['train_s']:.0f} s peak {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")  # fmt: skip
            t_seg = last = time.perf_counter()
            if stop:
                say("yield window: exit 3")
                rc = 3
                break
            if T0.gpu_check() == 3:
                say("GPU_CHECK: yield, exit 3")
                rc = 3
                break
    if rc == 0:
        if args.validate and (not state["history"] or state["history"][-1]["step"] != state["step"]):  # fmt: skip
            v = validate(net, data)
            state["history"].append({"step": state["step"], "train_s": state["train_s"], "final": True, **v})  # fmt: skip
            if v["score"] > state["best"]:
                state["best"] = v["score"]
                T0.save(out / "best.pt", net, opt, sched, state)
            say(f"final validation at step {state['step']}: {v}")
        T0.save(ck, net, opt, sched, state)
        (out / "done.json").write_text(json.dumps(state, indent=1))
    log.close()
    return rc


def resume_test(args):
    device = torch.device("cuda")
    data = Skies(args.skies, device)
    out = Path(args.out)
    base = {"skies": args.skies, "seed": 11, "hours": 10.0, "steps_total": 100, "validate": False, "yield_window": None, "batch": args.batch, "first_val": -1, "abort_step": -1}  # fmt: skip
    train(argparse.Namespace(out=str(out / "straight"), steps_max=100, **base), data)
    b = argparse.Namespace(out=str(out / "resumed"), steps_max=50, **base)
    train(b, data)
    b.steps_max = 100
    train(b, data)
    wa = torch.load(out / "straight" / "ckpt.pt", weights_only=False)["net"]
    wb = torch.load(out / "resumed" / "ckpt.pt", weights_only=False)["net"]
    res = {"bit_identical": all(torch.equal(wa[k], wb[k]) for k in wa)}
    (out / "resume-test.json").write_text(json.dumps(res))
    print(res)
    return 0 if res["bit_identical"] else 1


def export(args):
    import onnx
    import onnxruntime as ort

    c = torch.load(args.ckpt, weights_only=False, map_location="cpu")
    net = T0.CAN(hidden=HIDDEN)
    net.load_state_dict(c["net"])
    net.eval()
    x = torch.randn(1, 2, 256, 256)
    torch.onnx.export(net, x, args.out_onnx, opset_version=17, input_names=["x"], output_names=["y"], dynamic_axes={"x": {2: "h", 3: "w"}, "y": {2: "h", 3: "w"}}, dynamo=False)  # fmt: skip
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
    p.add_argument("skies")
    p.add_argument("out")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--hours", type=float, required=True)
    p.add_argument("--steps-total", type=int, required=True)
    p.add_argument("--steps-max", type=int)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--yield-window", action="append")
    p.add_argument("--no-validate", dest="validate", action="store_false")
    p.add_argument("--first-val", type=int, default=500)
    p.add_argument("--abort-step", type=int, default=1000)
    p.set_defaults(func=train)
    p = sub.add_parser("resume-test")
    p.add_argument("skies")
    p.add_argument("out")
    p.add_argument("--batch", type=int, default=8)
    p.set_defaults(func=resume_test)
    p = sub.add_parser("export")
    p.add_argument("ckpt")
    p.add_argument("out_onnx")
    p.set_defaults(func=export)
    a = ap.parse_args()
    sys.exit(a.func(a) or 0)


if __name__ == "__main__":
    main()
