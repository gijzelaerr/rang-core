"""Cross-check of `rang.core_clean.certified_clean` against the Rust example.

Research note: research/clean-certified-imaging.md §9. Runs the Python
binding on the export of `examples/clean_certified_export.py` with the
`exact-mgain` and `image-mgain` settings of `core/examples/clean_certified.rs`
and compares its models and residuals with the example's `.npy` files.

Usage:
    .venv/bin/python examples/clean_certified_binding_check.py INPUTS RUN > OUT.json
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_clean


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    inp, run = Path(argv[0]), Path(argv[1])
    meta = json.loads((inp / "meta.json").read_text())
    nrow, nchan = meta["nrow"], meta["nchan"]
    uvw = np.fromfile(inp / "uvw.f64").reshape(nrow, 3)
    freq = np.fromfile(inp / "freq.f64")
    vis = np.fromfile(inp / "vis.c128", dtype=np.complex128).reshape(nrow, nchan)
    wgt = np.fromfile(inp / "wgt.f64").reshape(nrow, nchan)
    out = {}
    for name, beam in (("exact-mgain", "exact"), ("image-mgain", "image")):
        start = time.perf_counter()
        res = core_clean.certified_clean(
            uvw,
            freq,
            vis,
            wgt,
            threshold=0.05,
            max_components=100_000,
            max_major=1000,
            audit=True,
            rule="mgain",
            beam=beam,
        )
        wall = time.perf_counter() - start
        model = np.load(run / f"{name}-model.npy")
        residual = np.load(run / f"{name}-residual.npy")
        out[name] = {
            "summary": res["summary"],
            "model_linf_vs_example": float(np.abs(res["model"] - model).max()),
            "residual_linf_vs_example": float(np.abs(res["residual"] - residual).max()),
            "wall_s": wall,
        }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
