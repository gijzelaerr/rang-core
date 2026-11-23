"""Pre-freeze: one CAN-48 pass at 4096^2 through ONNX Runtime, 16 threads (random He weights)."""

import sys
import time

import numpy as np
import onnxruntime as ort
import torch

sys.path.insert(
    0, "/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e/examples"
)
import dl4b_train as T

net = T.CAN(hidden=48)
for m in net.net:
    if isinstance(m, torch.nn.Conv2d):
        torch.nn.init.kaiming_normal_(m.weight, nonlinearity="relu")
net.eval()
path = "/mnt/d/rang/dl4b-step1/orient/can48.onnx"
torch.onnx.export(
    net,
    torch.randn(1, 2, 256, 256),
    path,
    opset_version=17,
    input_names=["x"],
    output_names=["y"],
    dynamic_axes={"x": {2: "h", 3: "w"}, "y": {2: "h", 3: "w"}},
    dynamo=False,
)
for th in (16,):
    so = ort.SessionOptions()
    so.intra_op_num_threads = th
    s = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
    x = np.random.randn(1, 2, 4096, 4096).astype(np.float32)
    s.run(None, {"x": x})
    t = time.perf_counter()
    for _ in range(2):
        s.run(None, {"x": x})
    print(
        f"CAN-48 4096^2 pass, {th} threads: {(time.perf_counter() - t) / 2:.1f} s; weights {sum(p.numel() for p in net.parameters())}"
    )
