"""g7_score.py OUT.json LABEL=MODEL.fits [LABEL=MODEL.fits ...] [--check-dirty DIRTY.fits]

The exact scoring of research/g7-defaults.md, section 4, on the pilot (cal.ms, 512 channels):
one operator for every imager's model, rang's core_wgridder at f64 and epsilon 1e-7 with
WSClean's flips, the Stokes I visibilities and the Briggs 0.5 gridding weights of
examples/gemclean_bench_compare.py (`weights`), with the rows read and scored in blocks so the
pilot fits in memory. Per model: Q = 1/2 sum w|V - Am|^2 / sum w, Q0 (the data alone), the exact
residual image (FITS order, written as LABEL-exact-residual.npy beside OUT.json), its inner-field
(central 2N/3) rms, MAD and peak, total and negative model flux.

--check-dirty: the exact dirty image (the data alone, the same blocks) against that file, as the
scorer's block check.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_ms, core_weights, core_wgridder
from rang.core_imaging import read_fits

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "examples"))
import gemclean_bench_compare as gbc  # noqa: E402

MS = "D:/rang/outputs/20261103-gemclean-heldout/real/cal.ms"
SIZE, SCALE, EPS, BLOCK = 4096, 3.0, 1e-7, 60_000


def inner(a):
    lo, hi = SIZE // 2 - SIZE // 3, SIZE // 2 + SIZE // 3
    return a[lo:hi, lo:hi]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("models", nargs="+")
    p.add_argument("--check-dirty")
    a = p.parse_args()
    out = Path(a.out)
    t0 = time.perf_counter()
    with core_ms.open_table(MS) as t:
        nrow = t.nrows
        uvw = np.ascontiguousarray(t.getcol("UVW"), np.float64)
        rows = (
            (t.getcol("FIELD_ID") == 0)
            & (t.getcol("ANTENNA1") != t.getcol("ANTENNA2"))
            & (t.getcol("DATA_DESC_ID") == 0)
            & ~np.asarray(t.getcol("FLAG_ROW"), bool)
        )
        with core_ms.open_table(Path(MS) / "SPECTRAL_WINDOW") as spw:
            freq = np.ascontiguousarray(spw.getcol("CHAN_FREQ")[0], np.float64)
        nchan = freq.size
        vis = np.empty((nrow, nchan), np.complex64)
        weight = np.empty((nrow, nchan), np.float32)
        for s in range(0, nrow, BLOCK):
            k = min(BLOCK, nrow - s)
            v, w = core_weights.stokes_i(
                t.getcol("DATA", s, k), t.getcol("WEIGHT_SPECTRUM", s, k), t.getcol("FLAG", s, k)
            )
            vis[s : s + k], weight[s : s + k] = v, w
    t_read = time.perf_counter() - t0
    gw, padded, sums = gbc.weights(uvw, freq, weight, rows, SIZE, SCALE)
    del weight
    total = float(gw.sum())
    kw = {
        "pixsize_x": SCALE * gbc.ARCSEC,
        "pixsize_y": SCALE * gbc.ARCSEC,
        "epsilon": EPS,
        "flip_v": True,
        "flip_w": True,
    }
    labels, models = [], []
    for spec in a.models:
        label, path = spec.split("=", 1)
        m, _ = read_fits(path)
        labels.append(label)
        models.append(np.ascontiguousarray(np.asarray(m, np.float64).T))
    jobs = [None] + models  # None: the data alone (Q0, the exact dirty image)
    q = [0.0] * len(jobs)
    img = [np.zeros((SIZE, SIZE)) for _ in jobs]
    for s in range(0, nrow, BLOCK):
        k = min(BLOCK, nrow - s)
        u, w = uvw[s : s + k], gw[s : s + k] / total
        v = vis[s : s + k].astype(np.complex128)
        for i, m in enumerate(jobs):
            e = v if m is None else v - core_wgridder.dirty2vis(uvw=u, freq=freq, dirty=m, wgt=w, **kw)
            e = np.where(w > 0, e, 0)
            q[i] += 0.5 * float(np.sum(w * np.abs(e) ** 2))
            img[i] += core_wgridder.vis2dirty(uvw=u, freq=freq, vis=e, wgt=w, npix_x=SIZE, npix_y=SIZE, **kw)
        print(f"rows {s + k}/{nrow} {time.perf_counter() - t0:.0f}s", flush=True)
    res = {
        "ms": MS,
        "size": SIZE,
        "scale_arcsec": SCALE,
        "epsilon": EPS,
        "block_rows": BLOCK,
        "padded_weight_grid": padded,
        "imaging_weight_sums": sums,
        "active_visibilities": int(np.count_nonzero(gw)),
        "q0": q[0],
        "read_s": t_read,
        "models": {},
    }
    dirty = img[0].T
    if a.check_dirty:
        d, _ = read_fits(a.check_dirty)
        d = np.asarray(d, np.float64)
        res["dirty_check"] = {
            "file": a.check_dirty,
            "linf_over_peak": float(np.abs(dirty - d).max() / np.abs(d).max()),
        }
    for i, label in enumerate(labels, start=1):
        r = img[i].T
        np.save(out.parent / f"{label}-exact-residual.npy", r.astype(np.float32))
        ri = inner(r)
        med = float(np.median(ri))
        m = models[i - 1]
        res["models"][label] = {
            "q": q[i],
            "q_over_q0": q[i] / q[0],
            "inner_rms": float(np.sqrt(np.mean(ri**2))),
            "inner_mad_sigma": float(1.4826 * np.median(np.abs(ri - med))),
            "inner_peak": float(np.abs(ri).max()),
            "model_flux": float(m.sum()),
            "model_negative": float(m[m < 0].sum()),
            "components": int(np.count_nonzero(m)),
        }
    res["wall_s"] = time.perf_counter() - t0
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res["models"], indent=1))


if __name__ == "__main__":
    main()
