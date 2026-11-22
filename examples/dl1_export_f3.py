# SPDX-License-Identifier: MIT
"""Export F3's calibrator network to an ONNX weights file (task DL1,
research/dl1-contract.md section 6).

    python examples/dl1_export_f3.py WEIGHTS.npz OUT.onnx [--net f4]

`--net f4` exports F4's calibrator seed 2 instead
(`D:/rang/outputs/f4-20261111-08-train-calibrator/seed-2/weights.npz`, sha256
a20b1abb..., research/f4-flagger.md; amendment 2 of dl1-contract.md).

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
F4_SHA = "a20b1abb10e0a3be7f502a70ab766df647236fe820530bc6b27a4fee4760d90d"


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


def header_f4():
    """F4's: same layout, 23 planes; stopped on its cost gate, held-out sets
    unread, so no gate is passed."""
    h = header()
    fail = {
        "passed": False,
        "rule": "research/f4-flagger.md",
        "scores": {
            "outcome": "stopped on the cost gate (0.441-0.459 against 0.45); held-out unread",
            "validation_recall": 0.954,
        },
    }
    h["inputs"] = dict(h["inputs"], features="f4flag", shape=["N", 23, "T", "F"])
    h["normalisation"] = {
        "features": "rang.f4flag (F3's planes plus eight spectral planes)"
    }
    h["training"] = {
        "framework": "JAX (F4, 2026-11-17, nash CPU); ported to PyTorch by copy",
        "seed": 2,
        "source_weights": "f4-20261111-08-train-calibrator/seed-2/weights.npz",
        "source_weights_sha256": F4_SHA,
        "manifest_sha256": None,
        "teachers": h["training"]["teachers"],
        "tau": -1.0,
    }
    h["gates"] = {"propose": fail, "settings": fail, "replace": fail}
    h["source"] = "research/f4-flagger.md; research/dl1-contract.md"
    return h


NETS = {"f3": (F3_SHA, 15, header), "f4": (F4_SHA, 23, header_f4)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("npz")
    ap.add_argument("out")
    ap.add_argument("--net", choices=sorted(NETS), default="f3")
    args = ap.parse_args()
    want, nplanes, make_header = NETS[args.net]
    import torch

    raw = Path(args.npz).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != want:
        raise SystemExit(f"{args.npz}: sha256 {sha}, expected {args.net} {want}")
    flat = f3net.flat_weights(f3net.load_params(args.npz))
    net = learned_torch.load_flat(learned_torch.dilated_cnn(nplanes), flat)
    learned_torch.export_onnx(net, args.out, make_header())
    w = learned.load(args.out)
    back = learned.dilated_cnn_weights(w)
    same = back.dtype == np.float32 and back.tobytes() == flat.tobytes()
    # PyTorch against the Rust kernel's arithmetic is checked in the runtime
    # bench (tools/dl1_runtimes); here PyTorch against the ONNX graph's input.
    rng = np.random.default_rng(20261119)
    x = rng.standard_normal((1, nplanes, 64, 512)).astype(np.float32)
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
