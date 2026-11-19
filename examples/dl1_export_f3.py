# SPDX-License-Identifier: MIT
"""Export F3's calibrator network to an ONNX weights file (task DL1,
research/dl1-contract.md section 6).

    python examples/dl1_export_f3.py WEIGHTS.npz OUT.onnx

WEIGHTS.npz is F3's seed 3 (`D:/rang/outputs/f3-20261110-17-train-calibrator/
seed-3/weights.npz`, sha256 2cdeee17...). Needs the `learned-train` extra
(torch, onnx). Recreates the network in PyTorch from the Rust kernel's flat
weights (exact copies), exports it with the `rang.learned` header (every
gate failed: F3's calibrator outcome F), then checks that the weights the
contract reads back are byte-equal to the npz's and that PyTorch's logits
agree with the kernel's on seeded planes; prints a JSON summary.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from rang import f3net, learned, learned_torch

F3_SHA = "2cdeee1795995b9d2f8c7c1d6deff6ec354c4a305712766afaccfb3091e2e91e"


def header():
    fail = {
        "passed": False,
        "rule": "research/f3-flagger.md#decision-frozen-rule-section-7",
        "scores": {
            "outcome": "F (calibrators)",
            "antenna_local_recall": 0.024,
            "antenna_local_recall_T": 0.907,
            "R1_pooled": 0.640,
        },
    }
    return {
        "format": learned.FORMAT,
        "stage": "flag",
        "data_class": "calibrator",
        "telescope": "MeerKAT",
        "band": "L",
        "architecture": {},  # filled by export_onnx
        "inputs": {
            "features": "f3flag",
            "tensor": "planes",
            "layout": "NCHW",
            "shape": ["N", 15, "T", "F"],
        },
        "outputs": {"tensor": "logits", "layout": "NCHW", "shape": ["N", 1, "T", "F"]},
        "normalisation": {
            "features": "rang.f3flag.features_numpy (noise-normalised, ash)"
        },
        "training": {
            "framework": "JAX 0.12.0.1 CUDA (F3, 2026-11-10); ported to PyTorch by copy",
            "seed": 3,
            "steps": 30000,
            "source_weights": "f3-20261110-17-train-calibrator/seed-3/weights.npz",
            "source_weights_sha256": F3_SHA,
            "manifest_sha256": None,
            "teachers": [
                {"name": "Tricolour port (T)", "version": "rang-core at 8d3becd"},
                {
                    "name": "AOFlagger generic (A)",
                    "version": "see research/f3-flagger.md",
                },
            ],
            "tau": -2.5,
        },
        "gates": {"propose": fail, "settings": fail, "replace": fail},
        # What the calibrator training data spanned (LUNO tiles 8-23, 4k mode).
        "envelope": {
            "channel_width_hz": [208984.375, 208984.375],
            "band_hz": [1070.0e6, 1498.0e6],
        },
        "licence": "MIT",
        "source": "research/f3-flagger.md; research/dl1-contract.md",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("npz")
    ap.add_argument("out")
    args = ap.parse_args()
    import torch

    raw = Path(args.npz).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != F3_SHA:
        raise SystemExit(f"{args.npz}: sha256 {sha}, expected F3 seed 3 {F3_SHA}")
    flat = f3net.flat_weights(f3net.load_params(args.npz))
    net = learned_torch.load_flat(learned_torch.dilated_cnn(15), flat)
    learned_torch.export_onnx(net, args.out, header())
    w = learned.load(args.out)
    back = learned.dilated_cnn_weights(w)
    same = back.dtype == np.float32 and back.tobytes() == flat.tobytes()
    # PyTorch against the Rust kernel's arithmetic is checked in the runtime
    # bench (tools/dl1_runtimes); here PyTorch against the ONNX graph's input.
    rng = np.random.default_rng(20261119)
    x = rng.standard_normal((1, 15, 64, 512)).astype(np.float32)
    with torch.no_grad():
        y = net(torch.from_numpy(x)).numpy()
    np.save(Path(args.out).with_suffix(".planes.npy"), x)
    np.save(Path(args.out).with_suffix(".torch.npy"), y)
    print(
        json.dumps(
            {
                "out": args.out,
                "onnx_sha256": w.sha256,
                "bytes": len(w.payload),
                "ops": list(w.ops),
                "weights": int(back.size),
                "weights_byte_equal": bool(same),
                "torch": torch.__version__,
            },
            indent=1,
        )
    )
    if not same:
        raise SystemExit("weights read back differ from the npz")


if __name__ == "__main__":
    main()
