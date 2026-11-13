"""The pilot floor's pre-registered injection and correction tests (research/imaging-floor.md).

Stages, each resumable (a stage whose output exists is skipped):

    prep     set A's rows on 32 channels: Stokes I, natural and Briggs 0.5 weights, noise constant
    predict  the three skies (truth = set B's model, its truncation, the pilot's model) as facets
             and alternative predictions; the H7 population
    cheap    E1-E4 on the existing full-data exact residuals (no imaging)
    pilot    every test on the real data, and the cumulative chain
    arms     every simulated arm with every test (a2 amplitudes from the a1 runs and the pilot)
    summary  the decision table of section 5

Everything stays in the output directory; `cleanup` deletes the visibility scratch.
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_ms, core_weights, core_wgridder
from rang.core_imaging import read_fits

ARC = math.pi / (180.0 * 3600.0)
SIZE = 4096
SCALE = 3.0
EPS = 1e-5
CHANNELS = np.arange(4, 256, 8)
HELD = Path("D:/rang/outputs/20261103-gemclean-heldout/real")
MS_A = HELD / "cal2.ms"
TRUTH = HELD / "run/cal3-003-gem-model.fits"
PILOT = HELD / "run/cal2-003-gem-model.fits"
MASK = HELD / "images/source-mask.fits"
F_HELDOUT = 1.0568e-3
LAT = math.radians(-30.7110)
LON = math.radians(21.4430)
KW = {
    "pixsize_x": SCALE * ARC,
    "pixsize_y": SCALE * ARC,
    "flip_v": True,
    "flip_w": True,
}
ROWS = 50_000
CENTRAL4 = {(1, 1), (1, 2), (2, 1), (2, 2)}
NOISE_SEED = 1301
SHORT_M = 400.0


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def wjson(path, value):
    path = Path(path)
    path.write_text(json.dumps(value, indent=1, default=float) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- prep


def prep(out, rows_limit=None):
    p = out / "prep"
    if (p / "meta.json").exists():
        return
    p.mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    with core_ms.open_table(str(MS_A)) as t:
        nrow = int(t.nrows) if rows_limit is None else rows_limit
        uvw = np.ascontiguousarray(t.getcol("UVW", 0, nrow), np.float64)
        rows_ok = ~np.asarray(t.getcol("FLAG_ROW", 0, nrow), bool)
        a1 = np.asarray(t.getcol("ANTENNA1", 0, nrow), np.int32)
        a2 = np.asarray(t.getcol("ANTENNA2", 0, nrow), np.int32)
        tm = np.asarray(t.getcol("TIME", 0, nrow), np.float64)
    with core_ms.open_table(str(MS_A / "SPECTRAL_WINDOW")) as s:
        freq_all = np.asarray(s.getcol("CHAN_FREQ", 0, 1)[0], np.float64)
        width = float(np.asarray(s.getcol("CHAN_WIDTH", 0, 1)[0])[0])
    with core_ms.open_table(str(MS_A / "FIELD")) as f:
        phase_dir = np.asarray(f.getcol("PHASE_DIR", 0, 1), np.float64).reshape(-1)[:2]
    nc = CHANNELS.size
    vis = np.empty((nrow, nc), np.complex64)
    wnat = np.empty((nrow, nc), np.float32)
    ratios = []
    rng = np.random.default_rng(7)
    with core_ms.open_table(str(MS_A)) as t:
        for r0 in range(0, nrow, ROWS):
            n = min(ROWS, nrow - r0)
            d = t.getcol("DATA", r0, n)
            w = t.getcol("WEIGHT_SPECTRUM", r0, n)
            f = t.getcol("FLAG", r0, n)
            sel = np.sort(np.concatenate([CHANNELS, CHANNELS + 1]))
            d, w, f = d[:, sel], w[:, sel], f[:, sel]
            if d.shape[-1] == 2:
                full = lambda x: np.stack(
                    [x[..., 0], x[..., 0], x[..., 1], x[..., 1]], axis=-1
                )
                d, w, f = full(d), full(w), full(f)
            v, g = core_weights.stokes_i(d, w, f)
            g = g * rows_ok[r0 : r0 + n, None]
            vis[r0 : r0 + n] = v[:, 0::2]
            wnat[r0 : r0 + n] = g[:, 0::2]
            # adjacent-channel differences: |d|^2 / (1/w_k + 1/w_k+1), chi^2_2 median 2 ln 2
            both = (g[:, 0::2] > 0) & (g[:, 1::2] > 0)
            dd = v[:, 0::2] - v[:, 1::2]
            inv = np.where(
                both,
                1.0 / np.maximum(g[:, 0::2], 1e-30)
                + 1.0 / np.maximum(g[:, 1::2], 1e-30),
                0,
            )
            x = (np.abs(dd) ** 2)[both] / inv[both]
            if x.size:
                ratios.append(rng.choice(x, min(x.size, 40_000), replace=False))
    c = float(np.median(np.concatenate(ratios)) / (2 * math.log(2)))
    freq = freq_all[CHANNELS]
    pad = core_weights.padded_size(SIZE)
    imaging = core_weights.imaging_weights(
        uvw,
        core_weights.wsclean_wavelengths(freq),
        wnat,
        rows_ok,
        mode="briggs",
        robust=0.5,
        width=pad,
        height=pad,
        pixel_scale=core_weights.pixel_scale_radians(SCALE),
        return_grid=False,
    )
    gw = (wnat * imaging["weights"].astype(np.float32)).astype(np.float32)
    gw[~rows_ok] = 0.0
    utime, ti = np.unique(tm, return_inverse=True)
    np.save(p / "uvw.npy", uvw)
    np.save(p / "vis.npy", vis)
    np.save(p / "wnat.npy", wnat)
    np.save(p / "gw.npy", gw)
    np.savez(
        p / "rows.npz", a1=a1, a2=a2, ti=ti.astype(np.int32), utime=utime, freq=freq
    )
    meta = {
        "ms": str(MS_A),
        "nrow": nrow,
        "channels": CHANNELS.tolist(),
        "chan_width_hz": width,
        "noise_c": c,
        "sigma_part_at_median_weight": math.sqrt(c / float(np.median(wnat[wnat > 0]))),
        "phase_dir_rad": phase_dir.tolist(),
        "gridding_weight_sum": float(gw.sum(dtype=np.float64)),
        "active": int(np.count_nonzero(gw)),
        "ntime": int(utime.size),
        "seconds": time.perf_counter() - s0,
    }
    wjson(p / "meta.json", meta)
    log("prep", meta)


class Data:
    def __init__(self, out):
        p = out / "prep"
        self.meta = json.loads((p / "meta.json").read_text())
        self.uvw = np.load(p / "uvw.npy")
        self.vis = np.load(p / "vis.npy")
        self.wnat = np.load(p / "wnat.npy")
        self.gw = np.load(p / "gw.npy")
        r = np.load(p / "rows.npz")
        self.a1, self.a2, self.ti, self.utime, self.freq = (
            r["a1"],
            r["a2"],
            r["ti"],
            r["utime"],
            r["freq"],
        )
        self.n = self.vis.shape[0]
        self.nant = int(max(self.a1.max(), self.a2.max())) + 1
        t = self.utime[self.ti] - self.utime[0]
        self.bin5 = (t // 300).astype(np.int32)
        self.bin2 = (t // 120).astype(np.int32)
        self.L = np.hypot(self.uvw[:, 0], self.uvw[:, 1])
        self.short = self.L < SHORT_M
        self.bl = (self.a1.astype(np.int64) * 1000 + self.a2).astype(np.int64)
        self.ubl, self.bli = np.unique(self.bl, return_inverse=True)
        self.sigma = np.where(
            self.wnat > 0,
            np.sqrt(self.meta["noise_c"] / np.maximum(self.wnat, 1e-30)),
            0,
        ).astype(np.float32)
        mask, _ = read_fits(MASK)
        k = SIZE // 6
        inner = np.zeros((SIZE, SIZE), bool)
        inner[k : SIZE - k, k : SIZE - k] = True
        self.sel = inner & ~(mask > 0.5)
        pm, _ = read_fits(PILOT)
        self.peak = np.unravel_index(np.argmax(pm), pm.shape)
        yy, xx = np.indices((SIZE, SIZE))
        self.rad_arcmin = np.hypot(yy - self.peak[0], xx - self.peak[1]) * SCALE / 60.0
        lam = 299792458.0 / self.freq
        uvl = self.L[:, None] / lam[None, :]
        self.w_short_share = float(
            self.gw[uvl < 1390.0].sum(dtype=np.float64) / self.gw.sum(dtype=np.float64)
        )

    def noise(self, seed):
        rng = np.random.default_rng(seed)
        z = rng.standard_normal(
            (self.n, self.freq.size), np.float32
        ) + 1j * rng.standard_normal((self.n, self.freq.size), np.float32)
        return (z * self.sigma).astype(np.complex64)


# ---------------------------------------------------------------- gridder


def predict(d, img_yx, freq=None, **kw):
    a = dict(KW)
    a.update(kw)
    eps = a.pop("epsilon", EPS)
    m = np.ascontiguousarray(np.asarray(img_yx).T, np.float64)
    # one call over all rows: each call pays the FFTs and w-planes once
    return core_wgridder.dirty2vis(
        uvw=d.uvw, freq=d.freq if freq is None else freq, dirty=m, epsilon=eps, **a
    ).astype(np.complex64)


def predict_facet(d, img_yx, iy, ix, nf, sign):
    """One facet of an nf x nf cut, predicted from its own sub-image with a centre shift."""
    f = SIZE // nf
    sub = img_yx[iy * f : (iy + 1) * f, ix * f : (ix + 1) * f]
    if not np.any(sub):
        return None
    cx = sign[0] * ((ix * f + f // 2) - SIZE // 2) * SCALE * ARC
    cy = sign[1] * ((iy * f + f // 2) - SIZE // 2) * SCALE * ARC
    return predict(d, sub, center_x=cx, center_y=cy)


def grid(d, e, gw=None):
    gw = d.gw if gw is None else gw
    tot = float(gw.sum(dtype=np.float64))
    img = core_wgridder.vis2dirty(
        uvw=d.uvw,
        freq=d.freq,
        vis=np.asarray(e, np.complex128),
        wgt=gw.astype(np.float64) / tot,
        npix_x=SIZE,
        npix_y=SIZE,
        epsilon=EPS,
        **KW,
    )
    return np.asarray(img).T


def floor(d, img):
    return float(np.sqrt(np.mean(img[d.sel] ** 2)))


def shape_stats(d, img):
    """E1-E4 of section 6."""
    x = img[d.sel]
    rms = float(np.sqrt(np.mean(x**2)))
    prof = {}
    for lo, hi in ((0, 10), (10, 20), (20, 40), (40, 68)):
        s = d.sel & (d.rad_arcmin >= lo) & (d.rad_arcmin < hi)
        prof[f"{lo}-{hi}"] = float(np.sqrt(np.mean(img[s] ** 2))) if s.any() else None
    z = np.where(d.sel, img, 0.0)
    pw = np.abs(np.fft.fftshift(np.fft.fft2(z))) ** 2
    du = 1.0 / (SIZE * SCALE * ARC)
    k = (np.arange(SIZE) - SIZE // 2) * du
    uu = np.hypot(k[None, :], k[:, None])
    short = float(pw[uu < 1390.0].sum() / pw.sum())
    m = x.mean()
    skew = float(np.mean((x - m) ** 3) / np.std(x) ** 3)
    return {
        "rms": rms,
        "profile": prof,
        "short_power_fraction": short,
        "skew": skew,
        "below_-3rms": float(np.mean(x < -3 * rms)),
        "above_+3rms": float(np.mean(x > 3 * rms)),
    }


# ---------------------------------------------------------------- skies


def sign_check(d, img, out):
    """Pick the centre-shift sign by matching facets to the full prediction on 3,000 rows."""
    p = out / "skies/sign.json"
    if p.exists():
        return json.loads(p.read_text())["sign"]
    sub = Data.__new__(Data)
    idx = np.linspace(0, d.n - 1, 3000).astype(int)
    sub.uvw, sub.freq, sub.n = d.uvw[idx], d.freq, idx.size
    full = predict(sub, img)
    best = None
    for sign in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        acc = np.zeros_like(full)
        for iy in range(4):
            for ix in range(4):
                v = predict_facet(sub, img, iy, ix, 4, sign)
                if v is not None:
                    acc += v
        err = float(np.abs(acc - full).max() / np.abs(full).max())
        log("sign", sign, err)
        if best is None or err < best[1]:
            best = (sign, err)
    if best[1] > 1e-4:
        raise SystemExit(f"facet predictions do not match the full prediction: {best}")
    (out / "skies").mkdir(parents=True, exist_ok=True)
    wjson(p, {"sign": list(best[0]), "rel_err": best[1]})
    return list(best[0])


def sky_set(d, out, name, img, nf=4, alts=True):
    """Facets (nf x nf, summed to 4 x 4 for nf=8), alternative predictions and the smeared one."""
    q = out / "skies" / name
    q.mkdir(parents=True, exist_ok=True)
    sign = sign_check(d, img, out)
    s0 = time.perf_counter()
    for iy in range(nf):
        for ix in range(nf):
            fn = q / f"facet{nf}_{iy}_{ix}.npy"
            if fn.exists():
                continue
            v = predict_facet(d, img, iy, ix, nf, sign)
            np.save(fn, np.zeros((0,), np.complex64) if v is None else v)
    if nf == 8:
        for jy in range(4):
            for jx in range(4):
                fn = q / f"facet4_{jy}_{jx}.npy"
                if fn.exists():
                    continue
                acc = None
                for iy in (2 * jy, 2 * jy + 1):
                    for ix in (2 * jx, 2 * jx + 1):
                        v = np.load(q / f"facet8_{iy}_{ix}.npy")
                        if v.size:
                            acc = v.copy() if acc is None else acc + v
                np.save(fn, np.zeros((0,), np.complex64) if acc is None else acc)
    if not (q / "full.npy").exists():
        acc = np.zeros((d.n, d.freq.size), np.complex64)
        for jy in range(4):
            for jx in range(4):
                v = np.load(q / f"facet4_{jy}_{jx}.npy")
                if v.size:
                    acc += v
        np.save(q / "full.npy", acc)
    if alts:
        dnu = d.meta["chan_width_hz"]
        jobs = {
            "flipw": {"flip_w": False},
            "now": {"do_wgridding": False},
            "eps7": {"epsilon": 1e-7},
        }
        for k, kw in jobs.items():
            if not (q / f"{k}.npy").exists():
                np.save(q / f"{k}.npy", predict(d, img, **kw))
        if not (q / "smear.npy").exists():
            a = predict(d, img, freq=d.freq - dnu / 4)
            a += predict(d, img, freq=d.freq + dnu / 4)
            np.save(q / "smear.npy", (a / 2).astype(np.complex64))
    if not (q / "check.json").exists():
        ref = predict(d, img)
        full = np.load(q / "full.npy")
        wjson(
            q / "check.json",
            {
                "facet_sum_vs_full_rel_linf": float(
                    np.abs(full - ref).max() / np.abs(ref).max()
                ),
                "seconds": time.perf_counter() - s0,
            },
        )
    log("sky", name, json.loads((q / "check.json").read_text()))


def load_set(out, name):
    q = out / "skies" / name
    facets = {}
    for jy in range(4):
        for jx in range(4):
            v = np.load(q / f"facet4_{jy}_{jx}.npy")
            if v.size:
                facets[(jy, jx)] = v
    return {"facets": facets, "full": np.load(q / "full.npy"), "dir": q}


def alpha_bins(d, out, truth):
    """H8c: pixels assigned to 8 equal-probability alpha bins of N(-0.7, 0.3), seed 1319."""
    q = out / "skies/alpha"
    q.mkdir(parents=True, exist_ok=True)
    if (q / "bins.json").exists():
        return
    from scipy.stats import norm

    rng = np.random.default_rng(1319)
    b = rng.integers(0, 8, truth.shape)
    z = norm.ppf((np.arange(8) + 0.5) / 8)
    for k in range(8):
        np.save(q / f"bin{k}.npy", predict(d, np.where(b == k, truth, 0.0)))
    wjson(q / "bins.json", {"z": z.tolist()})


def population(d, out):
    """H7: unmodelled sources to 4 deg, katbeam's azimuthal mean, counts frozen in section 4."""
    q = out / "skies/pop.npy"
    if q.exists():
        return
    from katbeam import JimBeam

    rng = np.random.default_rng(1318)
    K, smin, smax = 10.0, 1e-5, 10.0
    area = 2 * math.pi * (1 - math.cos(math.radians(4.0)))
    n = int(rng.poisson(K / 1.5 * (smin**-1.5 - smax**-1.5) * area))
    u = rng.random(n)
    s = (smin**-1.5 - u * (smin**-1.5 - smax**-1.5)) ** (-1 / 1.5) * (
        1.043 / 1.4
    ) ** -0.7
    r = 4.0 * np.sqrt(rng.random(n))
    phi = 2 * math.pi * rng.random(n)
    beam = JimBeam("MKAT-AA-L-JIM-2020")
    rr = np.linspace(0, 4.0, 401)
    az = np.linspace(0, 2 * math.pi, 16, endpoint=False)
    tab = np.array(
        [np.mean(beam.I(x * np.cos(az), x * np.sin(az), 1043.0)) for x in rr]
    )
    tab = np.where(np.isfinite(tab), np.maximum(tab, 1e-3), 1e-3)
    app = s * np.interp(r, rr, tab)
    l, m = r * np.cos(phi), r * np.sin(phi)
    half = SIZE * SCALE / 3600.0 / 2
    infield = (np.abs(l) < half) & (np.abs(m) < half)
    keep = ~(infield & (app > 3e-3))
    N, px = 5120, 6.0
    ix = np.round(-l[keep] * 3600 / px).astype(int) + N // 2
    iy = np.round(m[keep] * 3600 / px).astype(int) + N // 2
    ok = (ix >= 0) & (ix < N) & (iy >= 0) & (iy < N)
    img = np.zeros((N, N))
    np.add.at(img, (iy[ok], ix[ok]), app[keep][ok])
    np.save(q, predict(d, img, pixsize_x=px * ARC, pixsize_y=px * ARC))
    theta = math.sqrt(16.9 * 9.6)
    sig_c = 1.2e-6 * (1.043 / 3.0) ** -0.7 * (theta / 8.0) ** (10 / 3)
    wjson(
        out / "skies/pop.json",
        {
            "n_drawn": n,
            "n_kept": int(keep.sum()),
            "n_on_grid": int(ok.sum()),
            "flux_kept_apparent_jy": float(app[keep].sum()),
            "beam_table_min": float(tab.min()),
            "analytic_sigma_c_jy": sig_c,
        },
    )


def skies(out):
    d = Data(out)
    truth, _ = read_fits(TRUTH)
    pilot, _ = read_fits(PILOT)
    sky_set(d, out, "pilot", pilot, nf=4)
    sky_set(d, out, "truth", truth, nf=8)
    sky_set(d, out, "trunc", np.where(np.abs(truth) >= 0.01, truth, 0.0), nf=4)
    alpha_bins(d, out, truth)
    population(d, out)


# ---------------------------------------------------------------- tests


def stefcal(d, V, Y, sb, nsb, iters=30, g0=None, w=None):
    """Per-antenna, frequency-independent complex gains per solution bin: V ~ g_p conj(g_q) Y."""
    w = d.wnat if w is None else w
    A = np.einsum("rc,rc->r", w * V, np.conj(Y)).astype(np.complex128)
    B = np.einsum("rc,rc->r", w, np.abs(Y) ** 2).astype(np.float64)
    na = d.nant
    g = np.ones((nsb, na), np.complex128) if g0 is None else g0.copy()
    i1 = sb * na + d.a1
    i2 = sb * na + d.a2
    for it in range(iters):
        gq2 = g.reshape(-1)[i2]
        gq1 = g.reshape(-1)[i1]
        num = np.bincount(i1, (A * gq2).real, nsb * na) + 1j * np.bincount(
            i1, (A * gq2).imag, nsb * na
        )
        num += np.bincount(i2, (np.conj(A) * gq1).real, nsb * na) + 1j * np.bincount(
            i2, (np.conj(A) * gq1).imag, nsb * na
        )
        den = np.bincount(i1, np.abs(gq2) ** 2 * B, nsb * na) + np.bincount(
            i2, np.abs(gq1) ** 2 * B, nsb * na
        )
        gn = np.where(den > 0, num / np.maximum(den, 1e-300), g.reshape(-1)).reshape(
            nsb, na
        )
        g = 0.5 * (g + gn) if it % 2 else gn
    f = g.reshape(-1)[i1] * np.conj(g.reshape(-1)[i2])
    return f.astype(np.complex64), g


def total(Y):
    it = iter(Y.values())
    acc = next(it).copy()
    for v in it:
        acc += v
    return acc


def t1(d, V, Y, per8=False):
    sb, nsb = (d.ti, int(d.ti.max()) + 1) if per8 else (d.bin5, int(d.bin5.max()) + 1)
    f, _ = stefcal(d, V, total(Y), sb, nsb)
    return {k: v * f[:, None] for k, v in Y.items()}


def t2(d, V, Y):
    M = total(Y)
    num = np.bincount(
        d.bli, np.einsum("rc,rc->r", d.wnat * V, np.conj(M)).real, d.ubl.size
    ) + 1j * np.bincount(
        d.bli, np.einsum("rc,rc->r", d.wnat * V, np.conj(M)).imag, d.ubl.size
    )
    den = np.bincount(d.bli, np.einsum("rc,rc->r", d.wnat, np.abs(M) ** 2), d.ubl.size)
    s = np.where(den > 0, num / np.maximum(den, 1e-300), 1.0)
    return {k: v * s[d.bli][:, None].astype(np.complex64) for k, v in Y.items()}, s


def t3(d, V, Y):
    Y = {k: v.copy() for k, v in Y.items()}
    tot = total(Y)
    zero = np.zeros(d.n, np.int32)
    gains = {k: None for k in Y if k not in CENTRAL4}
    base = {k: v.copy() for k, v in Y.items() if k not in CENTRAL4}
    for sweep in range(2):
        for k in list(gains):  # noqa: PLC0206
            tot -= Y[k]
            f, gains[k] = stefcal(d, V - tot, base[k], zero, 1, iters=8, g0=gains[k])
            Y[k] = base[k] * f[:, None]
            tot += Y[k]
    return Y


def linear_scales(d, V, Y, groups):
    """Per group of rows/channels, complex scale per facet: V ~ sum_k s_k Y_k (normal equations)."""
    keys = list(Y)
    out = {k: v.copy() for k, v in Y.items()}
    for idx in groups:
        X = np.stack([Y[k][idx].reshape(-1) for k in keys]).astype(np.complex128)
        w = d.wnat[idx].reshape(-1)
        v = V[idx].reshape(-1)
        Xw = np.conj(X) * w
        N = Xw @ X.T
        b = Xw @ v
        s = np.linalg.lstsq(N, b, rcond=None)[0]
        for j, k in enumerate(keys):
            out[k][idx] = Y[k][idx] * s[j]
    return out


def t4(d, V, Y):
    groups = [
        (np.nonzero(d.bin5 == b)[0], slice(None)) for b in range(int(d.bin5.max()) + 1)
    ]
    return linear_scales(d, V, Y, [g for g in groups])


def t8(d, V, Y):
    return linear_scales(
        d, V, Y, [(slice(None), slice(c, c + 1)) for c in range(d.freq.size)]
    )


def t6_flags(d, e, worst, seed=1316):
    cells = d.bin2[:, None] * 1000 + np.arange(d.freq.size)[None, :]
    s = d.short[:, None] & (d.wnat > 0)
    key = cells[s]
    p = (d.wnat * np.abs(e) ** 2)[s]
    w = d.wnat[s]
    uk, inv = np.unique(key, return_inverse=True)
    power = np.bincount(inv, p) / np.maximum(np.bincount(inv, w), 1e-300)
    nflag = round(0.1 * uk.size)
    if worst:
        bad = uk[np.argsort(-power)[:nflag]]
    else:
        bad = np.random.default_rng(seed).choice(uk, nflag, replace=False)
    gw = d.gw.copy()
    hit = np.isin(cells, bad) & d.short[:, None]
    gw[hit] = 0.0
    return gw, int(nflag), int(uk.size)


def run_tests(d, V, sky, alt_dir, cumulative=False):
    """Every test on data V against a sky set; returns floors and shape stats."""
    Y0 = sky["facets"]
    res = {}
    t0 = time.perf_counter()

    def rec(name, e, gw=None):
        img = grid(d, e, gw)
        res[name] = {"F": floor(d, img)}
        if name == "none":
            res[name]["shape"] = shape_stats(d, img)
        return img

    M0 = total(Y0)
    rec("none", V - M0)
    Y1 = t1(d, V, Y0)
    e1 = V - total(Y1)
    rec("T1", e1)
    rec("T1f", V - total(t1(d, V, Y0, per8=True)))
    Y2, s = t2(d, V, Y1)
    rec("T2", V - total(Y2))
    res["T2"]["worst_baselines"] = [
        [int(d.ubl[i] // 1000), int(d.ubl[i] % 1000), float(abs(s[i] - 1))]
        for i in np.argsort(-np.abs(s - 1))[:145]
    ]
    rec("T3", V - total(t3(d, V, Y1)))
    rec("T4", V - total(t4(d, V, Y0)))
    rec("T8", V - total(t8(d, V, Y0)))
    for worst, name in ((True, "T6w"), (False, "T6r")):
        gw, nflag, ncell = t6_flags(d, e1, worst)
        rec(name, e1, gw)
        res[name]["cells"] = [nflag, ncell]
    for k in ("flipw", "now", "eps7", "smear"):
        if (alt_dir / f"{k}.npy").exists():
            rec("T5" + k if k != "smear" else "T10", V - np.load(alt_dir / f"{k}.npy"))
    if cumulative:
        Y = t1(d, V, Y0)
        rec("cum1_T1", V - total(Y))
        Y, _ = t2(d, V, Y)
        rec("cum2_T2", V - total(Y))
        Y = t8(d, V, Y)
        rec("cum3_T8", V - total(Y))
        Y = t3(d, V, Y)
        rec("cum4_T3", V - total(Y))
        Y = t4(d, V, Y)
        e = V - total(Y)
        rec("cum5_T4", e)
        gw, _, _ = t6_flags(d, e, True)
        rec("cum6_T6", e, gw)
    res["seconds"] = time.perf_counter() - t0
    return res


# ---------------------------------------------------------------- arms


def parallactic(d):
    ra, dec = d.meta["phase_dir_rad"]
    out = []
    for t in d.utime:
        mjd = t / 86400.0
        jd = mjd + 2400000.5
        gmst = math.radians((280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360.0)
        h = gmst + LON - ra
        out.append(
            math.atan2(
                math.sin(h), math.tan(LAT) * math.cos(dec) - math.sin(dec) * math.cos(h)
            )
        )
    return np.array(out)


def facet_centroids(img, nf):
    f = SIZE // nf
    yy, xx = np.indices((f, f))
    cen = {}
    for iy in range(nf):
        for ix in range(nf):
            sub = np.abs(img[iy * f : (iy + 1) * f, ix * f : (ix + 1) * f])
            if sub.sum() > 0:
                y = (sub * yy).sum() / sub.sum() + iy * f
                x = (sub * xx).sum() / sub.sum() + ix * f
                cen[(iy, ix)] = (
                    -(x - SIZE // 2) * SCALE / 3600.0,
                    (y - SIZE // 2) * SCALE / 3600.0,
                )
    return cen


def facet8(out, iy, ix):
    v = np.load(out / "skies/truth" / f"facet8_{iy}_{ix}.npy")
    return v if v.size else None


def gains(rng, shape, amp, phase_deg):
    return (1 + amp * rng.standard_normal(shape)) * np.exp(
        1j * math.radians(phase_deg) * rng.standard_normal(shape)
    )


def flat_norm(d, alpha):
    """c so that the band-weighted flat fit of c (nu/nu0)^alpha is 1."""
    nu0 = d.freq.mean()
    W = d.wnat.sum(axis=0, dtype=np.float64)
    x = (d.freq / nu0) ** alpha
    return x / (np.sum(W * x) / np.sum(W))


def make_arm(d, out, name, k):
    """Data for arm `name` at amplitude multiple k of a1 (noise seed 1301 unless C2)."""
    T = np.load(out / "skies/truth/full.npy")
    V = d.noise(1302 if name == "C2" else NOISE_SEED)
    rng = np.random.default_rng(
        1311 + int("".join(ch for ch in name[1:3] if ch.isdigit()) or 0)
    )
    if name in ("C", "C2", "M"):
        V += T
    elif name in ("H1a", "H1b"):
        nb = int(d.ti.max()) + 1 if name == "H1a" else 1
        g = gains(rng, (nb, d.nant), 0.01 * k, 1.0 * k)
        sb = d.ti if name == "H1a" else np.zeros(d.n, np.int32)
        f = g[sb, d.a1] * np.conj(g[sb, d.a2])
        V += T * f[:, None].astype(np.complex64)
    elif name == "H2":
        short_bl = np.unique(d.bli[d.short])
        pick = rng.choice(short_bl, 30, replace=False)
        eps = 0.02 * k * np.exp(2j * math.pi * rng.random(30))
        s = np.ones(d.ubl.size, np.complex128)
        s[pick] += eps
        V += T * s[d.bli][:, None].astype(np.complex64)
        wjson(
            out / "arms" / f"{name}-{k:g}-baselines.json",
            [[int(d.ubl[i] // 1000), int(d.ubl[i] % 1000)] for i in pick],
        )
    elif name == "H3":
        nb = int(d.bin5.max()) + 1
        for iy in range(8):
            for ix in range(8):
                v = facet8(out, iy, ix)
                if v is None:
                    continue
                if (iy, ix) in {(3, 3), (3, 4), (4, 3), (4, 4)}:
                    V += v
                    continue
                g = gains(rng, (nb, d.nant), 0.02 * k, 2.0 * k)
                f = g[d.bin5, d.a1] * np.conj(g[d.bin5, d.a2])
                V += v * f[:, None].astype(np.complex64)
    elif name in ("H4a", "H4b"):
        from katbeam import JimBeam

        beam = JimBeam("MKAT-AA-L-JIM-2020")
        truth, _ = read_fits(TRUTH)
        cen = facet_centroids(truth, 8)
        q = parallactic(d)
        fm = d.freq / 1e6
        for (iy, ix), (l, m) in cen.items():
            v = facet8(out, iy, ix)
            if v is None:
                continue
            x = l * np.cos(q) - m * np.sin(q)
            y = l * np.sin(q) + m * np.cos(q)
            B = np.stack(
                [np.asarray(beam.I(x, y, fm[c]), np.float64) for c in range(fm.size)],
                axis=1,
            )
            norm = B.mean(axis=0, keepdims=True) if name == "H4a" else B.mean()
            g = 1 + k * (B / norm - 1)
            V += v * g[d.ti].astype(np.complex64)
    elif name == "H5a":
        V += np.load(out / "skies/truth/flipw.npy")
    elif name == "H5b":
        V += np.load(out / "skies/truth/now.npy")
    elif name == "H6":
        ch = rng.choice(d.freq.size, 3, replace=False)
        V += T
        ph = np.exp(-2j * math.pi * d.uvw[:, 2:3] * d.freq[None, ch] / 299792458.0)
        V[:, ch] += (k * d.sigma[:, ch] * ph * d.short[:, None]).astype(np.complex64)
    elif name == "H7":
        V += T + k * np.load(out / "skies/pop.npy")
    elif name in ("H8a", "H8b"):
        if name == "H8a":
            al = -0.7 * k
            V += T * flat_norm(d, al)[None, :].astype(np.complex64)
        else:
            for iy in range(8):
                for ix in range(8):
                    v = facet8(out, iy, ix)
                    a = -0.7 + k * 0.3 * rng.standard_normal()
                    if v is not None:
                        V += v * flat_norm(d, a)[None, :].astype(np.complex64)
    elif name == "H8c":
        z = json.loads((out / "skies/alpha/bins.json").read_text())["z"]
        for b in range(8):
            V += np.load(out / "skies/alpha" / f"bin{b}.npy") * flat_norm(
                d, -0.7 + k * 0.3 * z[b]
            )[None, :].astype(np.complex64)
    elif name == "H10":
        V += np.load(out / "skies/truth/smear.npy")
    else:
        raise ValueError(name)
    return V


A1_ARMS = ["H1a", "H1b", "H2", "H3", "H4a", "H4b", "H6", "H8a", "H8b", "H8c"]
FIXED_ARMS = ["H5a", "H5b", "H7", "H10"]
A_MAX = {
    "H1a": 5,
    "H1b": 5,
    "H2": 10,
    "H3": 5,
    "H4a": 2,
    "H4b": 2,
    "H6": 3,
    "H7": 3,
    "H8a": 1 / 0.7,
    "H8b": 0.5 / 0.3,
    "H8c": 0.5 / 0.3,
}


def arm(d, out, name, k, sky_name="truth"):
    fn = out / "arms" / f"{name}-{k:g}.json"
    if fn.exists():
        return json.loads(fn.read_text())
    (out / "arms").mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    V = make_arm(d, out, name, k)
    sky = load_set(out, "trunc" if name == "M" else sky_name)
    r = run_tests(d, V, sky, sky["dir"])
    r["k"] = k
    r["wall_s"] = time.perf_counter() - s0
    wjson(fn, r)
    log(
        "arm",
        name,
        k,
        {
            t: round(v["F"] * 1e6, 2)
            for t, v in r.items()
            if isinstance(v, dict) and "F" in v
        },
    )
    return r


def arms(out):
    d = Data(out)
    pilot = json.loads((out / "pilot.json").read_text())
    for nm in ("C", "C2", "M"):
        arm(d, out, nm, 1)
    T = arm(d, out, "C", 1)["none"]["F"]
    Ppil = pilot["none"]["F"] ** 2 - T**2
    for nm in FIXED_ARMS:
        arm(d, out, nm, 1)
    for nm in A1_ARMS:
        r = arm(d, out, nm, 1)
        P1 = max(r["none"]["F"] ** 2 - T**2, 1e-30)
        k2 = min(math.sqrt(Ppil / P1), 50.0)
        arm(d, out, nm, round(k2, 3))
    for nm, kmax in A_MAX.items():
        arm(d, out, nm, kmax)


def pilot(out):
    fn = out / "pilot.json"
    if fn.exists():
        return
    d = Data(out)
    sky = load_set(out, "pilot")
    r = run_tests(d, d.vis.astype(np.complex64), sky, sky["dir"], cumulative=True)
    r["C0_F_over_heldout"] = r["none"]["F"] / F_HELDOUT
    wjson(fn, r)
    log(
        "pilot",
        {
            t: round(v["F"] * 1e6, 2)
            for t, v in r.items()
            if isinstance(v, dict) and "F" in v
        },
    )


def cheap(out):
    fn = out / "cheap.json"
    if fn.exists():
        return
    d = Data(out)
    res = {"w_short_share_subset": d.w_short_share}
    for nm in (
        "cal2-003-gem",
        "cal2-003-plain",
        "cal2-003-fast",
        "cal3-003-gem",
        "cal3-003-plain",
        "cal3-003-fast",
        "cal2-001-gem",
    ):
        img = np.load(HELD / "run" / f"{nm}-exact-residual.npy").astype(np.float64)
        res[nm] = shape_stats(d, img)
    wjson(fn, res)
    log("cheap", json.dumps(res)[:2000])


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument(
        "stage", choices=["prep", "skies", "cheap", "pilot", "arms", "all", "cleanup"]
    )
    p.add_argument("--out", default="D:/rang/outputs/20261113-floor")
    p.add_argument("--rows-limit", type=int)
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    s0 = time.perf_counter()
    if a.stage in ("prep", "all"):
        prep(out, a.rows_limit)
    if a.stage in ("skies", "all"):
        skies(out)
    if a.stage in ("cheap", "all"):
        cheap(out)
    if a.stage in ("pilot", "all"):
        pilot(out)
    if a.stage in ("arms", "all"):
        arms(out)
    if a.stage == "cleanup":
        import shutil

        for sub in ("prep", "skies"):
            shutil.rmtree(out / sub, ignore_errors=True)
    log("stage", a.stage, "wall_s", round(time.perf_counter() - s0, 1))


if __name__ == "__main__":
    sys.exit(main())
