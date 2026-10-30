"""Oracles of big-plan task DF1, the exact gridder (research/df1-wgridder.md).

    python examples/oracle_ducc0.py export MS OUT_DIR
    python examples/oracle_ducc0.py dft-slice DIR [--batch N]
    python examples/oracle_ducc0.py synthetic OUT_DIR
    python examples/oracle_ducc0.py ducc DIR... [--threads 1] [--tag NAME]

`export` writes the LUNO four-station slice of the DDFacet/killMS
feasibility study (field 1, cross-correlations, every 16th channel, Stokes I
`(XX + YY) / 2` as complex64, weight `4 min(w_XX, w_YY)` as float32, zero
where flagged) as `inputs.npz`, read through the core's own Measurement Set
reader (python-casacore is not in the rang venv). `dft-slice` computes the
float64 direct Fourier transform of the slice's dirty image and PSF on the
study's 512 x 512 grid at 8 arcsec. `synthetic` writes the seeded
wide-field cases: point sources, random uvw with large w of both signs,
complex128 visibilities, and the DFT of both directions. `ducc` runs the
ducc0 wheel (`nthreads=1` unless told otherwise) on every case and epsilon,
captures ducc0's `verbosity=1` report, hashes every output and measures it
against the DFT.

Conventions (rang's, the DFT's): pixel `(i, j)` of an `(nx, ny)` image is at
`l = (i - nx/2) dx`, `m = (j - ny/2) dy` (ducc0's layout, first axis l);
`dirty(l, m) = sum_k wgt_k Re[V_k exp(+2 pi i (u l + v m + w (n - 1)))]`
and `V_k = wgt_k sum_lm I(l, m) exp(-2 pi i (u l + v m + w (n - 1)))`, with
uvw in wavelengths (metres times f / c) and no division by n. ducc0 meets
these with `flip_w=True, divide_by_n=False` (measured here, `convention`).
"""

import argparse
import contextlib
import hashlib
import json
import os
import re
import resource
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

C_LIGHT = 299792458.0
ARCSEC = np.pi / (180.0 * 3600.0)
SLICE_NPIX = 512
SLICE_CELL = 8.0 * ARCSEC
# Gated epsilons (f32 1e-4, f64 1e-7) and reported ones (f32 1e-5, f64 1e-9).
EPSILONS = (("f32", 1e-4), ("f32", 1e-5), ("f64", 1e-7), ("f64", 1e-9))


def sha256(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def maxrss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def metrics(test, ref):
    """L-infinity, RMS (both over max |ref|) and relative L2 of test - ref."""
    test = np.asarray(test)
    ref = np.asarray(ref)
    err = test - ref
    peak = float(np.abs(ref).max())
    return {
        "linf_rel_peak": float(np.abs(err).max() / peak),
        "rms_rel_peak": float(np.sqrt(np.mean(np.abs(err) ** 2)) / peak),
        "l2_rel": float(np.linalg.norm(err.ravel()) / np.linalg.norm(ref.ravel())),
        "peak_ref": peak,
    }


def lm_grid(nx, ny, dx, dy, cx=0.0, cy=0.0):
    l1 = cx + (np.arange(nx) - nx // 2) * dx
    m1 = cy + (np.arange(ny) - ny // 2) * dy
    return np.meshgrid(l1, m1, indexing="ij")


def nm1_of(L, M):
    r2 = L * L + M * M
    return np.where(r2 < 1.0, -r2 / (np.sqrt(np.maximum(1.0 - r2, 0.0)) + 1.0), 0.0)


def dft_dirty(u, v, w, values, L, M, batch=64, extra=None):
    """sum_k Re[values_k exp(+2 pi i (u l + v m + w (n-1)))] over the image;
    `extra` (optional real weights) gives a second image in the same pass."""
    nm1 = nm1_of(L, M)
    out = np.zeros(L.shape)
    out2 = None if extra is None else np.zeros(L.shape)
    for s in range(0, u.size, batch):
        ph = np.exp(
            2j
            * np.pi
            * (
                u[s : s + batch, None, None] * L
                + v[s : s + batch, None, None] * M
                + w[s : s + batch, None, None] * nm1
            )
        )
        out += np.real(np.tensordot(values[s : s + batch], ph, axes=(0, 0)))
        if extra is not None:
            out2 += np.real(np.tensordot(extra[s : s + batch], ph, axes=(0, 0)))
    return out if extra is None else (out, out2)


def dft_vis(u, v, w, image, L, M):
    """V_k = sum_lm I exp(-2 pi i (u l + v m + w (n-1))) over nonzero pixels."""
    nz = np.nonzero(image)
    lv, mv, iv = L[nz], M[nz], image[nz]
    nv = nm1_of(lv, mv)
    out = np.zeros(u.size, np.complex128)
    for s in range(0, lv.size, 64):
        ph = np.exp(
            -2j
            * np.pi
            * (
                u[:, None] * lv[None, s : s + 64]
                + v[:, None] * mv[None, s : s + 64]
                + w[:, None] * nv[None, s : s + 64]
            )
        )
        out += ph @ iv[s : s + 64]
    return out


# ----------------------------------------------------------------- export


def cmd_export(args):
    from rangtoy import core_ms

    t0 = time.time()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    with core_ms.open_table(args.ms) as t:
        field = t.getcol("FIELD_ID")
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        sel = np.nonzero((field == 1) & (a1 != a2))[0]
        uvw = t.getcol("UVW")[sel]
        data = t.getcol("DATA")[sel]
        flag = t.getcol("FLAG")[sel]
        wsp = t.getcol("WEIGHT_SPECTRUM")[sel]
        frow = t.getcol("FLAG_ROW")[sel]
        with t.subtable("SPECTRAL_WINDOW") as spw:
            freq = spw.getcol("CHAN_FREQ")[0]
    ch = np.arange(0, freq.size, 16)
    freq = freq[ch]
    data, flag, wsp = data[:, ch], flag[:, ch], wsp[:, ch]
    stokes = 0.5 * (data[..., 0] + data[..., 3])
    bad = flag.any(-1) | frow[:, None] | ~np.isfinite(stokes)
    wgt = 4 * np.minimum(wsp[..., 0], wsp[..., 3]).astype(np.float32)
    wgt[bad] = 0
    stokes[bad] = 0
    vis = stokes.astype(np.complex64)
    np.savez(out / "inputs.npz", uvw=uvw, freq=freq, vis=vis, w=wgt)
    keep = wgt > 0
    r, k = np.nonzero(keep)
    w_lambda = uvw[r, 2] * freq[k] / C_LIGHT
    rec = {
        "ms": str(args.ms),
        "rows": int(uvw.shape[0]),
        "channels": int(freq.size),
        "nvis": int(keep.sum()),
        "wsum": float(wgt[keep].sum()),
        "w_max_lambda": float(np.abs(w_lambda).max()),
        "inputs_sha256": hashlib.sha256((out / "inputs.npz").read_bytes()).hexdigest(),
        "wall_s": time.time() - t0,
        "maxrss_mb": maxrss_mb(),
    }
    (out / "export.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


def slice_arrays(d):
    z = np.load(Path(d) / "inputs.npz")
    return z["uvw"], z["freq"], z["vis"], z["w"]


def cmd_dft_slice(args):
    t0 = time.time()
    d = Path(args.dir)
    uvw, freq, vis, wgt = slice_arrays(d)
    keep = wgt > 0
    r, k = np.nonzero(keep)
    lam = freq[k] / C_LIGHT
    u, v, w = (uvw[r, i] * lam for i in range(3))
    wk = wgt[r, k].astype(np.float64)
    vk = vis[r, k].astype(np.complex128) * wk
    L, M = lm_grid(SLICE_NPIX, SLICE_NPIX, SLICE_CELL, SLICE_CELL)
    dirty, psf = dft_dirty(
        u, v, w, vk, L, M, batch=args.batch, extra=wk.astype(np.complex128)
    )
    np.save(d / "dft_dirty.npy", dirty)
    np.save(d / "dft_psf.npy", psf)
    rec = {
        "nvis": int(u.size),
        "wsum": float(wk.sum()),
        "w_max_lambda": float(np.abs(w).max()),
        "peak_dirty_over_wsum": float(np.abs(dirty).max() / wk.sum()),
        "psf_centre_over_wsum": float(psf[SLICE_NPIX // 2, SLICE_NPIX // 2] / wk.sum()),
        "psf_edge_level": float(np.abs(psf[:16]).max() / wk.sum()),
        "dirty_sha256": sha256(dirty),
        "psf_sha256": sha256(psf),
        "wall_s": time.time() - t0,
        "maxrss_mb": maxrss_mb(),
    }
    (d / "dft.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


# -------------------------------------------------------------- synthetic

# name, npix, field (rad), w scale (lambda), rows, channels, seed
CASES = (
    ("small-8arcmin", 64, 8.0 / 60.0 * np.pi / 180.0, 1.0e3, 400, 4, 101),
    ("mid-2deg", 128, 2.0 * np.pi / 180.0, 3.0e3, 400, 4, 102),
    ("wide-0p3rad", 128, 0.3, 1.0e4, 400, 4, 103),
    ("wide-0p3rad-rect", 128, 0.3, 1.0e4, 300, 3, 104),
)


def make_case(name, npix, field, wscale, nrow, nchan, seed):
    rng = np.random.default_rng(seed)
    nx = npix
    ny = npix if not name.endswith("rect") else npix // 2
    dx = field / nx
    dy = field / nx
    freq = np.linspace(0.9e9, 1.6e9, nchan)
    lam_max = freq.max() / C_LIGHT
    # uv up to 0.45 of the Nyquist extent 1/dx at the highest frequency, w of
    # both signs up to wscale (wavelengths at the highest frequency).
    umax = 0.45 / dx / lam_max
    vmax = 0.45 / dy / lam_max
    uvw = np.stack(
        [
            rng.uniform(-umax, umax, nrow),
            rng.uniform(-vmax, vmax, nrow),
            rng.uniform(-wscale, wscale, nrow) / lam_max,
        ],
        axis=1,
    )
    # A few point sources on pixel centres (so the image DFT is exact), one
    # near a corner, fluxes 0.2-1.
    nsrc = 4
    ix = rng.integers(2, nx - 2, nsrc)
    iy = rng.integers(2, ny - 2, nsrc)
    ix[0], iy[0] = 3, ny - 4
    flux = rng.uniform(0.2, 1.0, nsrc)
    L, M = lm_grid(nx, ny, dx, dy)
    image = np.zeros((nx, ny))
    for a, b, f in zip(ix, iy, flux, strict=True):
        image[a, b] += f
    lam = freq / C_LIGHT
    u = (uvw[:, 0:1] * lam).ravel()
    v = (uvw[:, 1:2] * lam).ravel()
    w = (uvw[:, 2:3] * lam).ravel()
    model = dft_vis(u, v, w, image, L, M).reshape(nrow, nchan)
    noise = 0.05 * (
        rng.standard_normal((nrow, nchan)) + 1j * rng.standard_normal((nrow, nchan))
    )
    vis = model + noise
    wgt = rng.uniform(0.5, 1.5, (nrow, nchan))
    dirty = dft_dirty(u, v, w, (vis * wgt).ravel(), L, M)
    # Degridding reference: a sparse image of 16 random pixels (some negative).
    img2 = np.zeros((nx, ny))
    pix = rng.integers(0, nx * ny, 16)
    img2.ravel()[pix] = rng.uniform(-1.0, 1.0, 16)
    img2.ravel()[pix[0]] = 2.0
    vis2 = (dft_vis(u, v, w, img2, L, M).reshape(nrow, nchan)) * wgt
    return {
        "uvw": uvw,
        "freq": freq,
        "vis": vis,
        "wgt": wgt,
        "nx": nx,
        "ny": ny,
        "dx": dx,
        "dy": dy,
        "dft_dirty": dirty,
        "image": img2,
        "dft_vis": vis2,
        "sources": np.stack([ix, iy, flux], axis=1),
    }


def cmd_synthetic(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    summary = {}
    for name, npix, field, wscale, nrow, nchan, seed in CASES:
        t0 = time.time()
        case = make_case(name, npix, field, wscale, nrow, nchan, seed)
        np.savez(out / f"{name}.npz", **case)
        lam = case["freq"].max() / C_LIGHT
        summary[name] = {
            "npix": [case["nx"], case["ny"]],
            "field_rad": field,
            "pixsize_rad": case["dx"],
            "w_max_lambda": float(np.abs(case["uvw"][:, 2]).max() * lam),
            "rows": nrow,
            "channels": nchan,
            "seed": seed,
            "sha256": hashlib.sha256((out / f"{name}.npz").read_bytes()).hexdigest(),
            "wall_s": time.time() - t0,
        }
        print(name, json.dumps(summary[name]), flush=True)
    summary["maxrss_mb"] = maxrss_mb()
    (out / "synthetic.json").write_text(json.dumps(summary, indent=1))


# ------------------------------------------------------------------- ducc


@contextlib.contextmanager
def capture_fd1(path):
    """Redirect the C++ side's stdout (fd 1) into `path`."""
    sys.stdout.flush()
    saved = os.dup(1)
    with open(path, "ab") as fh:
        os.dup2(fh.fileno(), 1)
        try:
            yield
        finally:
            sys.stdout.flush()
            os.dup2(saved, 1)
            os.close(saved)


REPORT = re.compile(r"grid=\((\d+)x(\d+)(?:x(\d+))?\), supp=(\d+), eps=([0-9.e+-]+)")
WLINE = re.compile(r"w=\[([^;]+); ([^\]]+)\], min\(n-1\)=([^,]+), dw=([^,]+),")


def parse_report(text):
    found = []
    for m in REPORT.finditer(text):
        found.append(
            {
                "nu": int(m.group(1)),
                "nv": int(m.group(2)),
                "nplanes": int(m.group(3)) if m.group(3) else 0,
                "supp": int(m.group(4)),
            }
        )
    wl = [
        {"wmin": float(a), "wmax": float(b), "nm1min": float(c), "dw": float(d)}
        for a, b, c, d in WLINE.findall(text)
    ]
    for rec, extra in zip(found, wl, strict=False):
        rec.update(extra)
    return found


def load_case(path):
    path = Path(path)
    if path.is_dir():
        uvw, freq, vis, wgt = slice_arrays(path)
        dirty = np.load(path / "dft_dirty.npy")
        psf = np.load(path / "dft_psf.npy")
        return {
            "name": "luno-slice",
            "uvw": uvw,
            "freq": freq,
            "vis": vis.astype(np.complex128),
            "vis_c64": vis,
            "wgt": wgt.astype(np.float64),
            "nx": SLICE_NPIX,
            "ny": SLICE_NPIX,
            "dx": SLICE_CELL,
            "dy": SLICE_CELL,
            "dft_dirty": dirty,
            "dft_psf": psf,
        }
    z = dict(np.load(path))
    for key in ("nx", "ny"):
        z[key] = int(z[key])
    for key in ("dx", "dy"):
        z[key] = float(z[key])
    z["name"] = path.stem
    return z


def ducc_vis2dirty(case, prec, eps, nthreads, log, vis=None, wgt=None):
    import ducc0

    dt, ct = (
        (np.float32, np.complex64) if prec == "f32" else (np.float64, np.complex128)
    )
    vis = case["vis"] if vis is None else vis
    wgt = case["wgt"] if wgt is None else wgt
    with capture_fd1(log):
        t0 = time.perf_counter()
        img = ducc0.wgridder.vis2dirty(
            uvw=case["uvw"],
            freq=case["freq"],
            vis=np.ascontiguousarray(vis, ct),
            wgt=np.ascontiguousarray(wgt, dt),
            npix_x=case["nx"],
            npix_y=case["ny"],
            pixsize_x=case["dx"],
            pixsize_y=case["dy"],
            epsilon=eps,
            do_wgridding=True,
            nthreads=nthreads,
            verbosity=1,
            flip_w=True,
            divide_by_n=False,
        )
        wall = time.perf_counter() - t0
    return img, wall


def ducc_dirty2vis(case, prec, eps, nthreads, log):
    import ducc0

    dt = np.float32 if prec == "f32" else np.float64
    with capture_fd1(log):
        t0 = time.perf_counter()
        vis = ducc0.wgridder.dirty2vis(
            uvw=case["uvw"],
            freq=case["freq"],
            dirty=np.ascontiguousarray(case["image"], dt),
            wgt=np.ascontiguousarray(case["wgt"], dt),
            pixsize_x=case["dx"],
            pixsize_y=case["dy"],
            epsilon=eps,
            do_wgridding=True,
            nthreads=nthreads,
            verbosity=1,
            flip_w=True,
            divide_by_n=False,
        )
        wall = time.perf_counter() - t0
    return vis, wall


def cmd_ducc(args):
    import ducc0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    res = {"ducc0": ducc0.__version__, "nthreads": args.threads, "cases": {}}
    for path in args.cases:
        case = load_case(path)
        name = case["name"]
        rec = {}
        for prec, eps in EPSILONS:
            key = f"{prec}_eps{eps:g}"
            log = out / f"{name}_{key}.log"
            vis = case.get("vis_c64") if prec == "f32" and "vis_c64" in case else None
            img, wall = ducc_vis2dirty(case, prec, eps, args.threads, log, vis=vis)
            entry = {
                "vis2dirty": {
                    "wall_s": wall,
                    "sha256": sha256(img),
                    **metrics(img, case["dft_dirty"]),
                }
            }
            np.save(out / f"{name}_{key}_dirty.npy", img)
            if "dft_psf" in case:
                psf, wall = ducc_vis2dirty(
                    case, prec, eps, args.threads, log, vis=np.ones_like(case["vis"])
                )
                entry["psf"] = {
                    "wall_s": wall,
                    "sha256": sha256(psf),
                    **metrics(psf, case["dft_psf"]),
                }
                np.save(out / f"{name}_{key}_psf.npy", psf)
            if "image" in case:
                vis2, wall = ducc_dirty2vis(case, prec, eps, args.threads, log)
                entry["dirty2vis"] = {
                    "wall_s": wall,
                    "sha256": sha256(vis2),
                    **metrics(vis2, case["dft_vis"]),
                }
                np.save(out / f"{name}_{key}_vis.npy", vis2)
            entry["report"] = parse_report(log.read_text())
            rec[key] = entry
            print(
                name,
                key,
                json.dumps({k: v for k, v in entry.items() if k != "report"}),
                entry["report"],
                flush=True,
            )
        res["cases"][name] = rec
    res["maxrss_mb"] = maxrss_mb()
    (out / "ducc.json").write_text(json.dumps(res, indent=1))


def cmd_convention(args):
    """Pin ducc0's w sign and n division on one wide-field case against the
    DFT: the four (flip_w, divide_by_n) combinations at epsilon 1e-10."""
    import ducc0

    case = load_case(args.case)
    res = {}
    with tempfile.TemporaryDirectory() as tmp:
        for flip_w in (False, True):
            for dbn in (False, True):
                with capture_fd1(Path(tmp) / "log"):
                    img = ducc0.wgridder.vis2dirty(
                        uvw=case["uvw"],
                        freq=case["freq"],
                        vis=case["vis"],
                        wgt=case["wgt"],
                        npix_x=case["nx"],
                        npix_y=case["ny"],
                        pixsize_x=case["dx"],
                        pixsize_y=case["dy"],
                        epsilon=1e-10,
                        do_wgridding=True,
                        nthreads=1,
                        flip_w=flip_w,
                        divide_by_n=dbn,
                    )
                res[f"flip_w={flip_w},divide_by_n={dbn}"] = metrics(
                    img, case["dft_dirty"]
                )["linf_rel_peak"]
    print(json.dumps(res, indent=1))
    Path(args.out).write_text(json.dumps(res, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("ms")
    e.add_argument("out")
    e.set_defaults(func=cmd_export)
    d = sub.add_parser("dft-slice")
    d.add_argument("dir")
    d.add_argument("--batch", type=int, default=32)
    d.set_defaults(func=cmd_dft_slice)
    s = sub.add_parser("synthetic")
    s.add_argument("out")
    s.set_defaults(func=cmd_synthetic)
    u = sub.add_parser("ducc")
    u.add_argument("out")
    u.add_argument("cases", nargs="+")
    u.add_argument("--threads", type=int, default=1)
    u.set_defaults(func=cmd_ducc)
    c = sub.add_parser("convention")
    c.add_argument("case")
    c.add_argument("out")
    c.set_defaults(func=cmd_convention)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
