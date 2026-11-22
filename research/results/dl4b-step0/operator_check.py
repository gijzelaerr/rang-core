"""DL4b step 0, pre-freeze operator check (one seed, flux set 1000).

1. Remake the MS of a seed exactly as examples/astrodeconv_sim.py does.
2. WSClean 256^2 uniform -niter 0 -store-imaging-weights: dirty equals the stored dirty?
3. WEIGHT_SPECTRUM := IMAGING_WEIGHT_SPECTRUM, WSClean 512^2 natural -make-psf-only:
   the centre crop equals the stored 256^2 PSF? (the stored 512^2 PSF does not)
4. Image-domain residual dirty - psf512u (*) model_b against WSClean's residual_b.
5. Exact major cycle: WSClean -predict of model_b, DATA - MODEL_DATA, -niter 0:
   equals residual_b?
Usage: python operator_check.py ADC_WORKTREE SHARD_DIR SEED OUT_JSON
"""

import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from astropy.io import fits

wt, shard_dir, seed, out = (
    Path(sys.argv[1]),
    Path(sys.argv[2]),
    int(sys.argv[3]),
    sys.argv[4],
)
sys.path.insert(0, str(wt / "examples"))
import astrodeconv_sim as A
from rang import core_ms_write as W

F = 1000
k, i = divmod(seed, 10)
z = np.load(shard_dir / f"shard-{k:03d}.npz")
fi = 3 * i + A.FLUX_SETS.index(F)
dirty0, psf0, big0 = z["dirty"][fi], z["psf"][i], z["bigpsf"][i]
model_b, res_b = z["model_b"][fi], z["residual_b"][fi]

p = A.randomize(seed, F)
text = A.skymodel_text(seed, p)
ra0, dec0 = math.radians(A.JOB["ra"]), math.radians(p["dec"])
A.FIELD_DEC[0] = dec0
names = [a[0] for a in A.SPIEL_ANTENNAS]
xyz = np.array([a[1:] for a in A.SPIEL_ANTENNAS])
ndump = math.floor(p["synthesis"] * 3600 / A.JOB["dtime"])
times, uvw, el = A.track(xyz, ra0, dec0, ndump, A.JOB["dtime"])
a1, a2 = np.triu_indices(len(names), 1)
uvw_rows = (uvw[:, a2] - uvw[:, a1]).reshape(-1, 3)
a1r, a2r = np.tile(a1, ndump).astype(np.int32), np.tile(a2, ndump).astype(np.int32)
sigma = A.JOB["sefd"] / math.sqrt(2 * A.JOB["dtime"] * p["dfreq"])
data = A.noisy(A.predict(text, uvw_rows, ra0, dec0), sigma, seed, F)
col = "DATA"  # the contiguous reader (no -reorder) needs DATA
work = Path(tempfile.mkdtemp(prefix=f"opchk-{seed}-", dir="/dev/shm"))
res = {"seed": seed, "flux": F}


def ws(args, name):
    r = subprocess.run(
        ["wsclean", "-j", "1", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=work,
    )
    (work / f"{name}.log").write_text(r.stdout + r.stderr)
    assert r.returncode == 0, (r.stdout + r.stderr)[-1500:]


def img(path):
    return np.asarray(fits.getdata(path), np.float32)[0, 0]


def conv(m, pbig):
    from numpy.fft import irfft2, rfft2

    M = np.zeros((512, 512))
    M[:256, :256] = m
    c = irfft2(rfft2(M) * rfft2(np.fft.ifftshift(pbig.astype(float))), s=(512, 512))
    return c[:256, :256]


try:
    ms = work / "f.ms"
    zero = np.zeros_like(data)
    A.write_ms(ms, xyz, names, times, uvw_rows, a1r, a2r, {col: data, "RESID": zero}, sigma, A.JOB["freq0"], float(p["dfreq"]))  # fmt: skip
    base = [
        "-size",
        "256",
        "256",
        "-scale",
        f"{A.CELL_ASEC}asec",
        "-temp-dir",
        str(work),
        "-reorder",
    ]
    ws(base[:-1] + ["-weight", "uniform", "-niter", "0", "-store-imaging-weights", "-data-column", col, "-name", "d", str(ms)], "d")  # fmt: skip
    d = img(work / "d-image.fits")
    res["dirty_maxabs_diff_rel_peak"] = float(
        np.abs(d - dirty0).max() / np.abs(dirty0).max()
    )
    res["dirty_bit_identical"] = bool(np.array_equal(d, dirty0))
    from rang import core_ms as R

    with R.open_table(str(ms)) as t:
        res["columns_after_store"] = list(t.colnames())
        iw = t.getcol("IMAGING_WEIGHT_SPECTRUM")
        res["iw_stats"] = [
            str(iw.shape),
            str(iw.dtype),
            float(iw.min()),
            float(iw.max()),
            float((iw == 0).mean()),
            float(np.median(iw)),
        ]
        res["iw_xx_vs_yy_maxdiff"] = float(np.abs(iw[..., 0] - iw[..., 3]).max())
    with W.Table(ms) as t:
        w0 = t.getcol("WEIGHT_SPECTRUM")
        t.putcol("WEIGHT_SPECTRUM", iw.astype(np.float32))
        back = t.getcol("WEIGHT_SPECTRUM")
        res["weight_roundtrip_maxdiff"] = float(np.abs(back - iw).max())
        res["w0_stats"] = [str(w0.shape), float(w0.min()), float(w0.max())]
    ws(base + ["-weight", "natural", "-make-psf-only", "-data-column", col, "-name", "p256", str(ms)], "p256")  # fmt: skip
    p256 = img(work / "p256-psf.fits")
    res["psf256_natural_storedw_vs_psf256_rms_rel"] = float(
        (p256 - psf0).std() / psf0.std()
    )
    ws(base[:-1] + ["-weight", "natural", "-make-psf-only", "-data-column", col, "-name", "p256n", str(ms)], "p256n")  # fmt: skip
    res["psf256_natural_storedw_noreorder_rms_rel"] = float(
        (img(work / "p256n-psf.fits") - psf0).std() / psf0.std()
    )
    ws(base + ["-weight", "uniform", "-make-psf-only", "-data-column", col, "-name", "pu256", str(ms)], "pu256")  # fmt: skip
    res["psf256_uniform_fresh_vs_psf256_maxabs"] = float(
        np.abs(img(work / "pu256-psf.fits") - psf0).max()
    )
    # own uniform weights on the 256^2 uv grid (cell 1/(N dtheta)), (u,v) and (-u,-v) counted
    lam = 299792458.0 / A.JOB["freq0"]
    du = 1.0 / (256 * math.radians(A.CELL_ASEC / 3600))
    uu, vv = uvw_rows[:, 0] / lam / du, uvw_rows[:, 1] / lam / du
    best = None
    for mode in ("round", "floor"):
        f = np.round if mode == "round" else np.floor
        xs = np.concatenate([f(uu), f(-uu)]).astype(int)
        ys = np.concatenate([f(vv), f(-vv)]).astype(int)
        key = xs * 100003 + ys
        _, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
        own = (1.0 / cnt[inv[: len(uu)]]).astype(np.float32)
        ratio = iw[:, 0, 0] / own
        res[f"iw_over_own_{mode}"] = [
            float(np.percentile(ratio, q)) for q in (0, 1, 50, 99, 100)
        ]
    with W.Table(ms) as t:
        t.putcol("WEIGHT_SPECTRUM", np.repeat(own[:, None, None], 4, axis=2))
        t.putcol("WEIGHT", np.repeat(own[:, None], 4, axis=1))
    ws(base + ["-weight", "natural", "-make-psf-only", "-data-column", col, "-name", "po", str(ms)], "po")  # fmt: skip
    res["psf256_natural_ownw_vs_psf256_rms_rel"] = float(
        (img(work / "po-psf.fits") - psf0).std() / psf0.std()
    )
    with W.Table(ms) as t:
        t.putcol("WEIGHT_SPECTRUM", iw.astype(np.float32))
        t.putcol("WEIGHT", iw[:, 0, :].astype(np.float32))
    ws(base + ["-weight", "natural", "-make-psf-only", "-data-column", col, "-name", "pw", str(ms)], "pw")  # fmt: skip
    res["psf256_natural_storedw_both_cols_rms_rel"] = float(
        (img(work / "pw-psf.fits") - psf0).std() / psf0.std()
    )
    big = base[:]
    big[1:3] = ["512", "512"]
    ws(big + ["-weight", "natural", "-make-psf-only", "-data-column", col, "-name", "p", str(ms)], "p")  # fmt: skip
    pu = img(work / "p-psf.fits")
    crop = pu[128:384, 128:384]
    res["psf512u_crop_vs_psf256_maxabs"] = float(np.abs(crop - psf0).max())
    res["psf512u_crop_vs_psf256_rms_rel"] = float((crop - psf0).std() / psf0.std())
    cb = big0[128:384, 128:384]
    res["stored_bigpsf_crop_vs_psf256_rms_rel"] = float((cb - psf0).std() / psf0.std())
    for name, pb in (("psf512u", pu), ("stored_bigpsf", big0)):
        e = dirty0 - conv(model_b, pb) - res_b
        res[f"image_domain_{name}_err_rms_rel"] = float(e.std() / res_b.std())
        res[f"image_domain_{name}_err_max_rel_peak"] = float(
            np.abs(e).max() / np.abs(dirty0).max()
        )
    # corner deltas through the operator itself: predict + uniform 256^2 inversion
    hdr = fits.getheader(work / "d-image.fits")
    with W.Table(ms) as t:
        t.putcol("WEIGHT_SPECTRUM", w0)
        t.putcol("WEIGHT", w0[:, 0, :])
    P = np.zeros((512, 512), np.float32)
    for y0, x0 in ((0, 0), (0, 255), (255, 0), (255, 255)):
        m = np.zeros((256, 256), np.float32)
        m[y0, x0] = 1.0
        fits.writeto(
            work / f"c{y0}_{x0}-model.fits", m[None, None], hdr, overwrite=True
        )
        ws(base + ["-weight", "uniform", "-predict", "-data-column", col, "-name", f"c{y0}_{x0}", str(ms)], f"cp{y0}")  # fmt: skip
        ws(base + ["-weight", "uniform", "-niter", "0", "-data-column", "MODEL_DATA", "-name", f"ci{y0}_{x0}", str(ms)], f"ci{y0}")  # fmt: skip
        c = img(work / f"ci{y0}_{x0}-image.fits")
        # c[y, x] = P(y - y0, x - x0); P index offset +256
        P[256 - y0 : 512 - y0, 256 - x0 : 512 - x0] = c
    res["corner_psf_peak"] = float(P[256, 256])
    res["corner_psf_crop_vs_psf256_maxabs"] = float(
        np.abs(P[128:384, 128:384] - psf0).max()
    )
    e = dirty0 - conv(model_b, P) - res_b
    res["image_domain_corner_err_rms_rel"] = float(e.std() / res_b.std())
    res["image_domain_corner_err_max_rel_peak"] = float(
        np.abs(e).max() / np.abs(dirty0).max()
    )
    np.save(work.parent / f"opchk-cornerpsf-{seed}.npy", P)
    # 3x3 deltas at {0,128,255}^2; offset d per axis taken from the delta whose y0+d is nearest 128
    pos = (0, 128, 255)
    imgs = {}
    for y0 in pos:
        for x0 in pos:
            m = np.zeros((256, 256), np.float32)
            m[y0, x0] = 1.0
            nm = f"g{y0}_{x0}"
            fits.writeto(work / f"{nm}-model.fits", m[None, None], hdr, overwrite=True)
            ws(base + ["-weight", "uniform", "-predict", "-data-column", col, "-name", nm, str(ms)], nm + "p")  # fmt: skip
            ws(base + ["-weight", "uniform", "-niter", "0", "-data-column", "MODEL_DATA", "-name", nm + "i", str(ms)], nm + "i")  # fmt: skip
            imgs[(y0, x0)] = img(work / f"{nm}i-image.fits")
    d = np.arange(-256, 256)
    pick = np.array(
        [
            min(pos, key=lambda q: abs(q + dd - 128) if 0 <= q + dd <= 255 else 10**6)
            for dd in d
        ]
    )
    G = np.zeros((512, 512), np.float32)
    for iy, dy in enumerate(d):
        y0 = pick[iy]
        y = y0 + dy
        if not 0 <= y <= 255:
            continue
        for x0 in pos:
            xs = np.where(pick == x0)[0]
            xx = x0 + d[xs]
            ok = (xx >= 0) & (xx <= 255)
            G[iy, xs[ok]] = imgs[(y0, x0)][y, xx[ok]]
    res["grid_psf_peak"] = float(G[256, 256])
    res["grid_psf_crop_vs_psf256_maxabs"] = float(
        np.abs(G[128:384, 128:384] - psf0).max()
    )
    e = dirty0 - conv(model_b, G) - res_b
    res["image_domain_grid_err_rms_rel"] = float(e.std() / res_b.std())
    res["image_domain_grid_err_max_rel_peak"] = float(
        np.abs(e).max() / np.abs(dirty0).max()
    )
    np.save(work.parent / f"opchk-gridpsf-{seed}.npy", G)
    with W.Table(ms) as t:
        t.putcol("WEIGHT_SPECTRUM", w0)
        t.putcol("WEIGHT", w0[:, 0, :])
    hdr = fits.getheader(work / "d-image.fits")
    fits.writeto(
        work / "m-model.fits",
        model_b[None, None].astype(np.float32),
        hdr,
        overwrite=True,
    )
    ws(base + ["-weight", "uniform", "-predict", "-data-column", col, "-name", "m", str(ms)], "pred")  # fmt: skip
    with W.Table(ms) as t:
        md = t.getcol("MODEL_DATA")
        dd = t.getcol(col)
        t.putcol("RESID", (dd - md).astype(dd.dtype))
    ws(base + ["-weight", "uniform", "-niter", "0", "-data-column", "RESID", "-name", "r", str(ms)], "r")  # fmt: skip
    r = img(work / "r-image.fits")
    e = r - res_b
    res["exact_cycle_err_rms_rel"] = float(e.std() / res_b.std())
    res["exact_cycle_err_max_rel_peak"] = float(np.abs(e).max() / np.abs(dirty0).max())
    res["residual_b_rms"] = float(res_b.std())
finally:
    shutil.rmtree(work, ignore_errors=True)
Path(out).write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
