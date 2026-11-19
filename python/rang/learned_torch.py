# SPDX-License-Identifier: MIT
"""PyTorch side of the swap contract (task DL1, research/dl1-contract.md):
training-only, behind the optional extra `learned-train` (torch, onnx). The
pipeline, the check and the wheel never import this module.

`DilatedCNN` is architecture `dilated-cnn/1` (F2-F5's network: dilated 3x3
convolutions with zero padding and ReLU, then a 1x1 head; NCHW), loadable
from the Rust kernels' flat weight order (`rang.f3net.flat_weights`) so
that a trained network moves between JAX history, PyTorch and the Rust
kernel without arithmetic. `export_onnx` writes the weights file with the
`rang.learned` header.
"""

from __future__ import annotations

import json

import numpy as np

from . import learned

ARCHITECTURE = "dilated-cnn/1"


def _torch():
    try:
        import torch
    except ImportError as e:  # pragma: no cover - depends on the extra
        raise ImportError(
            "rang.learned_torch needs PyTorch: pip install 'rang-core[learned-train]'"
        ) from e
    return torch


def dilated_cnn(inputs, hidden=8, dilations=(1, 2, 4, 8, 16)):
    """A `torch.nn.Module` of dilated-cnn/1, float32, zero weights."""
    torch = _torch()
    nn = torch.nn

    class DilatedCNN(nn.Module):
        def __init__(self):
            super().__init__()
            layers = []
            cin = inputs
            for d in dilations:
                layers += [nn.Conv2d(cin, hidden, 3, padding=d, dilation=d), nn.ReLU()]
                cin = hidden
            self.body = nn.Sequential(*layers)
            self.head = nn.Conv2d(hidden, 1, 1)
            self.hyperparameters = {
                "inputs": int(inputs),
                "hidden": int(hidden),
                "dilations": [int(d) for d in dilations],
            }

        def forward(self, x):
            return self.head(self.body(x))

    return DilatedCNN()


def load_flat(net, flat):
    """Copy the Rust kernels' flat weights into `net` (exact float32
    copies: per layer W (ky, kx, cin, cout) then b; the head W (hidden, 1)
    then b)."""
    torch = _torch()
    flat = np.asarray(flat, np.float32)
    hp = net.hyperparameters
    convs = [m for m in net.body if isinstance(m, torch.nn.Conv2d)] + [net.head]
    at = 0
    cin = hp["inputs"]
    for k, conv in enumerate(convs):
        head = k == len(hp["dilations"])
        ks, cout = (1, 1) if head else (3, hp["hidden"])
        n = ks * ks * cin * cout
        w = flat[at : at + n].reshape(ks, ks, cin, cout).transpose(3, 2, 0, 1)
        b = flat[at + n : at + n + cout]
        at += n + cout
        with torch.no_grad():
            conv.weight.copy_(torch.from_numpy(np.ascontiguousarray(w)))
            conv.bias.copy_(torch.from_numpy(b.copy()))
        cin = hp["hidden"]
    if at != flat.size:
        raise ValueError(f"flat weights: {flat.size} values, the network takes {at}")
    return net


def export_onnx(net, path, header, opset=17):
    """Write `net` as an ONNX weights file with dynamic batch, time and
    channel axes, input `planes` (N, C, T, F), output `logits` (N, 1, T, F),
    and `header` (a dict, checked by `rang.learned.Header`) in
    metadata_props under `rang.learned`. The exporter and opset are added
    to header['training']."""
    torch = _torch()
    import onnx

    net = net.eval()
    hp = net.hyperparameters
    x = torch.zeros(1, hp["inputs"], 8, 16, dtype=torch.float32)
    header = json.loads(json.dumps(header))
    header.setdefault("training", {})
    header["training"]["exporter"] = (
        f"torch.onnx {torch.__version__}, onnx {onnx.__version__}"
    )
    header["training"]["opset"] = opset
    header["architecture"] = {"id": ARCHITECTURE, "hyperparameters": hp}
    learned.Header.from_dict(header)  # refuse a bad header before writing
    torch.onnx.export(
        net,
        (x,),
        str(path),
        input_names=["planes"],
        output_names=["logits"],
        dynamic_axes={
            "planes": {0: "N", 2: "T", 3: "F"},
            "logits": {0: "N", 2: "T", 3: "F"},
        },
        opset_version=opset,
        dynamo=False,
        do_constant_folding=False,
    )
    model = onnx.load(str(path))
    del model.metadata_props[:]
    entry = model.metadata_props.add()
    entry.key = learned.HEADER_KEY
    entry.value = json.dumps(header, sort_keys=True)
    model.producer_name = "rang.learned_torch"
    onnx.checker.check_model(model)
    onnx.save(model, str(path))
    return path
