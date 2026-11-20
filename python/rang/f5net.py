# SPDX-License-Identifier: MIT
"""F5's network for training (research/f5-flagger.md, sections 2e and 9): PyTorch,
float32, with no rang imports so that it runs in a NumPy-and-PyTorch-only
environment (the CUDA training venv in WSL). Inference is Rust
(`rang._core.f5flag_logits`; `f3flag_logits` and `f4flag_logits` for the
stack without a stem).

Two forms of one module:

- `stem=False`: F3's and F4's stack (`rang.f3net`, frozen JAX): five 3×3
  convolutions from `nplanes` inputs, dilations 1, 2, 4, 8, 16, 8 hidden
  channels, ReLU, "same" zero padding, 1×1 head. The flat weight order is
  `rang.f3net.flat_weights`'s, so F3/F4 weights load unchanged.
- `stem=True` (N5): a 1×1 linear stem `nplanes` → 8 without activation, then
  five 3×3 convolutions 8 → 8 with the same dilations, ReLU, head.

Flat weight order (the Rust kernels'): per layer W (ky, kx, cin, cout)
row-major then b; the stem W (cin, cout) then b; the head W (8, 1) then b.

Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
see `LICENSES/MIT.txt`.
"""

import math

import numpy as np

HIDDEN = 8
DILATIONS = (1, 2, 4, 8, 16)
N5_PLANES = 33


def weight_count(nplanes, stem):
    n = 0
    cin = nplanes
    if stem:
        n += nplanes * HIDDEN + HIDDEN
        cin = HIDDEN
    for _ in DILATIONS:
        n += 9 * cin * HIDDEN + HIDDEN
        cin = HIDDEN
    return n + HIDDEN + 1


def init_arrays(seed, nplanes, stem):
    """He-normal weights, zero biases, as NumPy arrays in the flat order's
    shapes: [stem (cin, 8), b]?, [(W (3, 3, cin, 8), b)] * 5, (head (8, 1), b).
    Drawn from `numpy.random.default_rng(seed)` in that order (F3's order when
    `stem` is False, so `init_arrays(0, 15, False)` is F3's U3)."""
    rng = np.random.default_rng(seed)
    out = []
    cin = nplanes
    if stem:
        w = rng.normal(0, math.sqrt(1.0 / cin), (cin, HIDDEN))
        out.append((w.astype(np.float32), np.zeros(HIDDEN, np.float32)))
        cin = HIDDEN
    for _ in DILATIONS:
        w = rng.normal(0, math.sqrt(2.0 / (9 * cin)), (3, 3, cin, HIDDEN))
        out.append((w.astype(np.float32), np.zeros(HIDDEN, np.float32)))
        cin = HIDDEN
    head = rng.normal(0, math.sqrt(2.0 / cin), (cin, 1)).astype(np.float32)
    out.append((head, np.zeros(1, np.float32)))
    return out


def flat_from_arrays(arrays):
    return np.concatenate(
        [np.concatenate([np.ravel(w), np.ravel(b)]) for w, b in arrays]
    ).astype(np.float32)


def arrays_from_flat(flat, nplanes, stem):
    flat = np.asarray(flat, np.float32)
    if flat.size != weight_count(nplanes, stem):
        raise ValueError(f"{flat.size} weights, expected {weight_count(nplanes, stem)}")
    out, at, cin = [], 0, nplanes

    def take(shape):
        nonlocal at
        n = int(np.prod(shape))
        a = flat[at : at + n].reshape(shape)
        at += n
        return a

    if stem:
        out.append((take((cin, HIDDEN)), take((HIDDEN,))))
        cin = HIDDEN
    for _ in DILATIONS:
        out.append((take((3, 3, cin, HIDDEN)), take((HIDDEN,))))
        cin = HIDDEN
    out.append((take((cin, 1)), take((1,))))
    return out


def build(nplanes, stem, arrays=None, seed=0):
    """The torch module, with weights from `arrays` (flat order shapes) or
    `init_arrays(seed, ...)`."""
    import torch
    from torch import nn

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.nplanes, self.has_stem = nplanes, stem
            self.stem = nn.Conv2d(nplanes, HIDDEN, 1) if stem else None
            cin = HIDDEN if stem else nplanes
            self.convs = nn.ModuleList()
            for d in DILATIONS:
                self.convs.append(nn.Conv2d(cin, HIDDEN, 3, padding=d, dilation=d))
                cin = HIDDEN
            self.head = nn.Conv2d(HIDDEN, 1, 1)

        def forward(self, x):
            """Logits (N, nt, nc) of inputs (N, nt, nc, nplanes)."""
            h = x.permute(0, 3, 1, 2)
            if self.stem is not None:
                h = self.stem(h)
            for c in self.convs:
                h = torch.relu(c(h))
            return self.head(h)[:, 0]

    net = Net()
    load_arrays(net, arrays if arrays is not None else init_arrays(seed, nplanes, stem))
    return net


def load_arrays(net, arrays):
    """Copy flat-order arrays into the module (HWIO → OIHW)."""
    import torch

    k = 0
    with torch.no_grad():
        if net.stem is not None:
            w, b = arrays[k]
            net.stem.weight.copy_(
                torch.from_numpy(np.ascontiguousarray(w.T[:, :, None, None]))
            )
            net.stem.bias.copy_(torch.from_numpy(b))
            k += 1
        for conv in net.convs:
            w, b = arrays[k]
            conv.weight.copy_(
                torch.from_numpy(np.ascontiguousarray(w.transpose(3, 2, 0, 1)))
            )
            conv.bias.copy_(torch.from_numpy(b))
            k += 1
        w, b = arrays[k]
        net.head.weight.copy_(
            torch.from_numpy(np.ascontiguousarray(w.T[:, :, None, None]))
        )
        net.head.bias.copy_(torch.from_numpy(b))


def to_arrays(net):
    """The module's weights in flat-order shapes (OIHW → HWIO)."""
    out = []
    if net.stem is not None:
        w = net.stem.weight.detach().cpu().numpy()[:, :, 0, 0].T
        out.append((np.ascontiguousarray(w), net.stem.bias.detach().cpu().numpy()))
    for conv in net.convs:
        w = conv.weight.detach().cpu().numpy().transpose(2, 3, 1, 0)
        out.append((np.ascontiguousarray(w), conv.bias.detach().cpu().numpy()))
    w = net.head.weight.detach().cpu().numpy()[:, :, 0, 0].T
    out.append((np.ascontiguousarray(w), net.head.bias.detach().cpu().numpy()))
    return [(a.astype(np.float32), b.astype(np.float32)) for a, b in out]


def bce(z, label):
    """Unweighted binary cross-entropy over cells with label 0 or 1 (−1
    ignored), F3's form."""
    import torch

    keep = label >= 0
    y = torch.where(keep, label, torch.zeros_like(label)).to(z.dtype)
    ce = torch.clamp(z, min=0) - z * y + torch.log1p(torch.exp(-torch.abs(z)))
    n = torch.clamp(keep.sum(), min=1)
    return torch.where(keep, ce, torch.zeros_like(ce)).sum() / n


def export_onnx(net, path, header, nt=16, nc=256):
    """ONNX (opset 17) of the module, inputs (N, nt, nc, nplanes) with dynamic
    N, nt and nc; `header` (a JSON-serialisable dict) goes in
    `metadata_props` under "rang.learned"."""
    import json

    import onnx
    import torch

    x = torch.zeros(1, nt, nc, net.nplanes)
    torch.onnx.export(
        net,
        x,
        str(path),
        opset_version=17,
        input_names=["planes"],
        output_names=["logits"],
        dynamic_axes={
            "planes": {0: "n", 1: "nt", 2: "nc"},
            "logits": {0: "n", 1: "nt", 2: "nc"},
        },
        dynamo=False,
    )
    model = onnx.load(str(path))
    p = model.metadata_props.add()
    p.key = "rang.learned"
    p.value = json.dumps(header, sort_keys=True)
    onnx.save(model, str(path))
