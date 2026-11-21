# SPDX-License-Identifier: MIT
"""DL6 dry run, step R4's export (research/dl6-retrain.md section 2a): an
F5 weights.npz (`examples/f5_train.py`, flat order of `rang/f5net.py`) to
the frozen ONNX form: Conv and Relu only, NCHW `planes` (N, 33, T, F) to
`logits` (N, 1, T, F), opset 17, the header under "rang.learned". Checks:
only Conv/Relu nodes; the initializers read back equal the npz's flat
weights byte for byte; `rang.learned.load` accepts the file; the
interpreter (`rang.learned.run_reference`) against PyTorch on seeded planes
(I2, bar 1e-4). Prints a JSON receipt, and the work-per-cell record of
section 7 (header architecture, op list, initializer shapes).

    python dl6_export.py WEIGHTS.npz F5NET.py OUT.onnx HEADER.json

Needs torch and onnx (rang's `learned-train` extra) and a rang build with
the interpreter (main since 2d9f4c5f).
"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import onnx
import torch
from onnx import numpy_helper
from rang import learned


def main():
    wpath, f5net_py, out, header_json = sys.argv[1:5]
    spec = importlib.util.spec_from_file_location("f5net", f5net_py)
    f5net = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(f5net)
    z = np.load(wpath)
    flat = np.asarray(z["flat"], np.float32)
    nplanes = f5net.N5_PLANES
    net = f5net.build(nplanes, True, f5net.arrays_from_flat(flat, nplanes, True))
    net.eval()

    class NCHW(torch.nn.Module):
        """F5's module without the NHWC permute and the head's [:, 0]."""

        def __init__(self, n):
            super().__init__()
            self.n = n

        def forward(self, x):
            h = self.n.stem(x)
            for c in self.n.convs:
                h = torch.relu(c(h))
            return self.n.head(h)

    m = NCHW(net)
    header = json.loads(Path(header_json).read_text())
    header["architecture"] = {
        "id": "f5-n5",
        "hyperparameters": {
            "inputs": nplanes,
            "hidden": f5net.HIDDEN,
            "dilations": list(f5net.DILATIONS),
            "stem": True,
        },
    }
    header["training"]["exporter"] = f"torch {torch.__version__} onnx {onnx.__version__}"
    header["training"]["opset"] = 17
    header["training"]["flat_sha256"] = hashlib.sha256(flat.tobytes()).hexdigest()
    x0 = torch.zeros(1, nplanes, 16, 256)
    torch.onnx.export(
        m,
        x0,
        out,
        opset_version=17,
        input_names=["planes"],
        output_names=["logits"],
        dynamic_axes={"planes": {0: "N", 2: "T", 3: "F"}, "logits": {0: "N", 2: "T", 3: "F"}},
        dynamo=False,
        do_constant_folding=True,
    )
    model = onnx.load(out)
    # torch's exporter shares equal initializers through Identity nodes (all
    # zero biases at init); give each its own initializer and drop the nodes.
    inits0 = {i.name: i for i in model.graph.initializer}
    keep_nodes = []
    for n in model.graph.node:
        if n.op_type == "Identity" and n.input[0] in inits0:
            t = onnx.TensorProto()
            t.CopyFrom(inits0[n.input[0]])
            t.name = n.output[0]
            model.graph.initializer.append(t)
        else:
            keep_nodes.append(n)
    del model.graph.node[:]
    model.graph.node.extend(keep_nodes)
    onnx.checker.check_model(model)
    p = model.metadata_props.add()
    p.key = learned.HEADER_KEY
    p.value = json.dumps(header, sort_keys=True)
    onnx.save(model, out)
    ops = [n.op_type for n in model.graph.node]
    inits = {i.name: numpy_helper.to_array(i) for i in model.graph.initializer}
    # Read back in the flat order: per conv node, W (OIHW -> HWIO; 1x1 -> (cin, cout)) then b.
    back = []
    for n in model.graph.node:
        if n.op_type != "Conv":
            continue
        w = inits[n.input[1]]
        b = inits[n.input[2]]
        if w.shape[2:] == (1, 1):
            back.append(np.ascontiguousarray(w[:, :, 0, 0].T).ravel())
        else:
            back.append(np.ascontiguousarray(w.transpose(2, 3, 1, 0)).ravel())
        back.append(b.ravel())
    back = np.concatenate(back).astype(np.float32)
    rec = {
        "out": out,
        "ops": ops,
        "conv_only": set(ops) <= {"Conv", "Relu"},
        "initializer_shapes": [list(inits[n.input[k]].shape) for n in model.graph.node if n.op_type == "Conv" for k in (1, 2)],
        "weights": int(flat.size),
        "weights_byte_equal": back.tobytes() == flat.tobytes(),
        "architecture": header["architecture"],
    }
    try:
        w = learned.load(out)
        rec["load"] = "ok"
        rec["onnx_sha256"] = w.sha256
        rng = np.random.default_rng(20261120)
        x = rng.standard_normal((1, nplanes, 64, 512)).astype(np.float32)
        with torch.no_grad():
            yt = m(torch.from_numpy(x)).numpy()
        yi = learned.run_reference(w, x)
        rec["i2_max_abs"] = float(np.abs(yi - yt).max())
        rec["i2_pass"] = rec["i2_max_abs"] <= 1e-4
    except Exception as e:  # recorded: Stop-X
        rec["load"] = f"refused: {e}"
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
