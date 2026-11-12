# SPDX-License-Identifier: GPL-3.0-or-later
"""G6 criterion 3 (research/g6-predict.md): both imagers' model columns
against the direct Fourier sum of the model image's nonzero pixels.

    python dft.py MS MODEL.fits --field 3 [--columns MODEL_DATA MODEL_WSCLEAN]
        [--rows 400] [--seed 20261180] [--out result.json]

Run in rang's venv (rang.core.predict_components, rang.core_ms). Each
nonzero pixel (x, y) (FITS order, 0-based) is a point at
l = (x - x0) CDELT1, m = (y - y0) CDELT2 (radians, SIN grid, x0 = CRPIX1 - 1).
predict_components' sign convention is checked against WSClean's column:
the rule fixes WSClean as the oracle, so the conjugate is used if it fits
WSClean better, and that is reported."""

import argparse
import json
import sys

import numpy as np

from rang import core, core_ms


def read_fits(path):
    raw = open(path, "rb").read()
    cards, pos = {}, 0
    while True:
        card = raw[pos : pos + 80].decode("ascii", "replace")
        pos += 80
        key = card[:8].strip()
        if key == "END":
            break
        if card[8:10] == "= ":
            value = card[10:].split("/")[0].strip().strip("'").strip()
            cards[key] = value
    start = -(-pos // 2880) * 2880
    nx, ny = int(cards["NAXIS1"]), int(cards["NAXIS2"])
    dtype = {"-32": ">f4", "-64": ">f8"}[cards["BITPIX"]]
    data = np.frombuffer(raw, dtype, nx * ny, start).reshape(ny, nx).astype(np.float64)
    return cards, data


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("ms")
    p.add_argument("model")
    p.add_argument("--field", type=int, required=True)
    p.add_argument("--columns", nargs="+", default=["MODEL_DATA", "MODEL_WSCLEAN"])
    p.add_argument("--rows", type=int, default=400)
    p.add_argument("--seed", type=int, default=20261180)
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)
    cards, img = read_fits(a.model)
    y, x = np.nonzero(img)
    flux = img[y, x]
    cd1 = np.deg2rad(float(cards["CDELT1"]))
    cd2 = np.deg2rad(float(cards["CDELT2"]))
    x0, y0 = float(cards["CRPIX1"]) - 1, float(cards["CRPIX2"]) - 1
    lm = np.stack([(x - x0) * cd1, (y - y0) * cd2], axis=1)
    with core_ms.open_table(a.ms) as t:
        keep = np.flatnonzero(
            (t.getcol("FIELD_ID") == a.field)
            & (t.getcol("ANTENNA1") != t.getcol("ANTENNA2"))
            & (t.getcol("DATA_DESC_ID") == 0)
        )
        rng = np.random.default_rng(a.seed)
        rows = np.sort(rng.choice(keep, size=min(a.rows, len(keep)), replace=False))
        uvw = np.stack([t.getcol("UVW", int(r), 1)[0] for r in rows])
        cols = {
            c: np.stack([t.getcol(c, int(r), 1)[0] for r in rows]) for c in a.columns
        }
    with core_ms.open_table(f"{a.ms}/SPECTRAL_WINDOW") as sw:
        freq = np.asarray(sw.getcol("CHAN_FREQ", 0, 1)[0], np.float64)
    nsrc = len(flux)
    exact = core.predict_components(
        uvw,
        freq,
        lm,
        np.zeros(nsrc, np.uint8),
        flux,
        np.zeros((nsrc, 1)),
        np.zeros(nsrc, bool),
        np.full(nsrc, freq[0]),
        np.zeros((nsrc, 3)),
    )
    out = {
        "model": a.model,
        "components": int(nsrc),
        "rows": int(len(rows)),
        "seed": a.seed,
    }
    w = cols[a.columns[-1]][..., 0].astype(np.complex128)

    def rel(v, ref):
        return float(np.linalg.norm(v - ref) / np.linalg.norm(ref))

    conj = rel(w, np.conj(exact)) < rel(w, exact)
    ref = np.conj(exact) if conj else exact
    out["conjugate_used"] = bool(conj)
    for c, v in cols.items():
        out[c] = {
            "rel_l2_xx": rel(v[..., 0].astype(np.complex128), ref),
            "rel_l2_yy": rel(v[..., -1].astype(np.complex128), ref),
        }
    out["criterion_3"] = bool(
        all(max(out[c]["rel_l2_xx"], out[c]["rel_l2_yy"]) <= 1e-5 for c in cols)
    )
    text = json.dumps(out, indent=1, sort_keys=True)
    if a.out:
        open(a.out, "w").write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
