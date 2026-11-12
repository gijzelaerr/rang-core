# SPDX-License-Identifier: GPL-3.0-or-later
"""W6 image comparisons (research/w6-imaging-inputs.md).

    python fits_cmp.py same PREFIX_A PREFIX_B          # SHA-256 of the five files
    python fits_cmp.py bounds GEM_PREFIX WSC_PREFIX    # G3's B bounds, dirty and psf
Prints JSON."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

KINDS = ("dirty", "psf", "model", "residual", "image")


def read(path):
    raw = Path(path).read_bytes()
    cards, pos = {}, 0
    while True:
        card = raw[pos : pos + 80].decode("ascii", "replace")
        pos += 80
        if card[:8].strip() == "END":
            break
        if card[8:10] == "= ":
            cards[card[:8].strip()] = card[10:].split("/")[0].strip().strip("'").strip()
    start = -(-pos // 2880) * 2880
    nx, ny = int(cards["NAXIS1"]), int(cards["NAXIS2"])
    dtype = {"-32": ">f4", "-64": ">f8"}[cards["BITPIX"]]
    return cards, np.frombuffer(raw, dtype, nx * ny, start).reshape(ny, nx).astype(
        np.float64
    )


def same(a, b):
    out = {}
    for k in KINDS:
        pa, pb = Path(f"{a}-{k}.fits"), Path(f"{b}-{k}.fits")
        if not pa.exists() or not pb.exists():
            out[k] = None
            continue
        out[k] = (
            hashlib.sha256(pa.read_bytes()).hexdigest()
            == hashlib.sha256(pb.read_bytes()).hexdigest()
        )
    out["identical"] = all(v is True for v in out.values())
    return out


def bounds(g, w):
    cg, dg = read(f"{g}-dirty.fits")
    cw, dw = read(f"{w}-dirty.fits")
    _, pg = read(f"{g}-psf.fits")
    _, pw = read(f"{w}-psf.fits")
    psf = float(np.abs(pg - pw).max() / pw.max())
    dirty = float(np.abs(dg - dw).max() / np.abs(dw).max())
    wg, ww = float(cg["WSCIMGWG"]), float(cw["WSCIMGWG"])
    weight = abs(wg - ww) / ww
    return {
        "psf_rel": psf,
        "dirty_rel": dirty,
        "imgwg_rel": weight,
        "within_b": psf <= 1e-5 and dirty <= 1e-5 and weight <= 1e-6,
    }


def main():
    mode, a, b = sys.argv[1:4]
    print(json.dumps(same(a, b) if mode == "same" else bounds(a, b), sort_keys=True))


if __name__ == "__main__":
    main()
