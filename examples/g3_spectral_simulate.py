"""Simulated spectral MeerKAT skies for GeMClean's output channels (task G3).

Research note: research/g3-spectral.md (the rule, written before any comparison).
Built on the benchmark's simulator (examples/gemclean_bench_simulate.py): 64
MeerKAT dishes, exact direct Fourier sums through the core
(`rang.core.predict_components`), noise on all four correlations, rang's own
table writer. Here the sources have spectra

    S(nu) = S0 (nu / nu0) ** (alpha + beta ln(nu / nu0)),  nu0 = 1.2 GHz,

(`log_poly` with coefficients alpha, beta), over 16 channels from 900 to
1670 MHz, a 2 h track at 16 s, natural MFS noise 20 uJy.

Skies (positions continuous, inside the inner two-thirds of 2048 x 1.5 arcsec):

    D1   40 points, S0 log-uniform 2-500 mJy, alpha uniform in [-1.2, 0.3],
         every third point curved (beta uniform in [-0.6, 0.6]), at least
         40 pixels apart; dec -30
    D2   20 points as D1 and 5 circular Gaussians of FWHM 15-60 arcsec
         (log-uniform), S0 0.1-1 Jy, alpha in [-1.2, 0], two with beta in
         [-0.6, 0.6], each at least 4 FWHM + 40 pixels from every other
         component; dec -30
    H1s  D1's recipe at dec -60 (held out: seeds given on the command line)
    H2s  D2's recipe at dec -10 (held out)

Usage:
    .venv/bin/python examples/g3_spectral_simulate.py OUT.ms --sky D1 --catalogue OUT.json
    .venv/bin/python examples/g3_spectral_simulate.py OUT.ms --sky H1s \
        --sky-seed 0x... --noise-seed 0x... --catalogue OUT.json
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemclean_bench_simulate as bench
from rang import core
from rang import core_ms_write as tables

C = 299_792_458.0
ARCSEC = math.pi / (180.0 * 3600.0)
NU0 = 1.2e9
SEEDS = {"D1": (20261161, 20261171), "D2": (20261162, 20261172)}
DEC = {"D1": -30.0, "D2": -30.0, "H1s": -60.0, "H2s": -10.0}
RECIPE = {"D1": "points", "D2": "extended", "H1s": "points", "H2s": "extended"}


def spectrum(c, freq):
    x = np.log(np.asarray(freq) / NU0)
    return c["flux"] * np.exp(c["alpha"] * x + c["beta"] * x * x)


def draw_sky(recipe, size, scale_arcsec, seed):
    rng = np.random.default_rng(seed)
    half = size / 3.0
    comps = []

    def far(x, y, need):
        return all(
            (x - c["dx"]) ** 2 + (y - c["dy"]) ** 2 >= need(c) ** 2 for c in comps
        )

    if recipe == "extended":
        for i in range(5):
            fwhm = float(np.exp(rng.uniform(math.log(15.0), math.log(60.0))))
            fwhm_px = fwhm / scale_arcsec
            lim = half - 3 * fwhm_px
            while True:
                x, y = rng.uniform(-lim, lim, 2)
                need = lambda c, f=fwhm_px: 4 * max(f, c.get("fwhm_px", 0.0)) + 40.0
                if far(x, y, need):
                    break
            comps.append(
                {
                    "kind": "gaussian",
                    "dx": float(x),
                    "dy": float(y),
                    "flux": float(np.exp(rng.uniform(math.log(0.1), math.log(1.0)))),
                    "fwhm_arcsec": fwhm,
                    "fwhm_px": fwhm_px,
                    "alpha": float(rng.uniform(-1.2, 0.0)),
                    "beta": float(rng.uniform(-0.6, 0.6)) if i < 2 else 0.0,
                }
            )
    npoints = 40 if recipe == "points" else 20
    for i in range(npoints):
        while True:
            x, y = rng.uniform(-half, half, 2)
            need = lambda c: (
                4 * c.get("fwhm_px", 0.0) + 40.0 if c["kind"] == "gaussian" else 40.0
            )
            if far(x, y, need):
                break
        comps.append(
            {
                "kind": "point",
                "dx": float(x),
                "dy": float(y),
                "flux": float(np.exp(rng.uniform(math.log(2e-3), math.log(0.5)))),
                "alpha": float(rng.uniform(-1.2, 0.3)),
                "beta": float(rng.uniform(-0.6, 0.6)) if i % 3 == 2 else 0.0,
            }
        )
    scale = scale_arcsec * ARCSEC
    centre = size // 2
    for c in comps:
        c["x"], c["y"] = centre + c["dx"], centre + c["dy"]
        c["l"], c["m"] = -c["dx"] * scale, c["dy"] * scale
    return comps


def arrays(comps):
    n = len(comps)
    shape = np.zeros((n, 3))
    for i, c in enumerate(comps):
        if c["kind"] == "gaussian":
            shape[i] = [c["fwhm_arcsec"] * ARCSEC, c["fwhm_arcsec"] * ARCSEC, 0.0]
    return {
        "lm": np.array([[c["l"], c["m"]] for c in comps]).reshape(n, 2),
        "kind": np.array([1 if c["kind"] == "gaussian" else 0 for c in comps]),
        "flux": np.array([c["flux"] for c in comps]),
        "coeffs": np.array([[c["alpha"], c["beta"]] for c in comps]).reshape(n, 2),
        "log_poly": np.ones(n, bool),
        "ref_freq": np.full(n, NU0),
        "gauss_shape": shape,
    }


def predict(uvw, freq, a):
    return core.predict_components(
        uvw,
        freq,
        a["lm"],
        a["kind"],
        a["flux"],
        a["coeffs"],
        a["log_poly"],
        a["ref_freq"],
        a["gauss_shape"],
    )


def direct(uvw, freq, comps, a):
    """Independent NumPy sum with the spectra (positive phase)."""
    u, v, w = (uvw[:, k][:, None, None] for k in range(3))
    nu = freq[None, :, None]
    l, m = a["lm"][:, 0], a["lm"][:, 1]
    n1 = np.sqrt(1.0 - l * l - m * m) - 1.0
    phase = 2 * np.pi * nu / C * (u * l + v * m + w * n1)
    fwhm = a["gauss_shape"][:, 0]
    env = np.exp(
        -(np.pi**2) / (4 * math.log(2)) * fwhm**2 * (u**2 + v**2) * (nu / C) ** 2
    )
    s = np.array([spectrum(c, freq) for c in comps]).T[None]  # (1, nchan, ncomp)
    return np.sum(s * env * np.exp(1j * phase), axis=-1)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ms")
    p.add_argument("--sky", choices=sorted(RECIPE), required=True)
    p.add_argument("--sky-seed", type=lambda s: int(s, 0))
    p.add_argument("--noise-seed", type=lambda s: int(s, 0))
    p.add_argument("--hours", type=float, default=2.0)
    p.add_argument("--dt", type=float, default=16.0)
    p.add_argument("--nchan", type=int, default=16)
    p.add_argument("--fmin", type=float, default=0.9e9)
    p.add_argument("--fmax", type=float, default=1.67e9)
    p.add_argument("--size", type=int, default=2048)
    p.add_argument("--scale", type=float, default=1.5)
    p.add_argument("--noise-ujy", type=float, default=20.0)
    p.add_argument("--chunk-times", type=int, default=25)
    p.add_argument("--catalogue")
    args = p.parse_args(argv)
    if args.sky in SEEDS:
        sky_seed, noise_seed = SEEDS[args.sky]
    else:
        if args.sky_seed is None or args.noise_seed is None:
            raise SystemExit("held-out skies need --sky-seed and --noise-seed")
        sky_seed, noise_seed = args.sky_seed, args.noise_seed

    t_start = time.perf_counter()
    xyz, diameter, names = bench.antennas(64)
    nant = len(names)
    times, ra, dec, ant_uvw, _lon = bench.track(xyz, args.hours, args.dt, DEC[args.sky])
    a1, a2 = np.triu_indices(nant, 1)
    nbl, ntime = len(a1), len(times)
    nrow = nbl * ntime
    width = (args.fmax - args.fmin) / args.nchan
    freq = args.fmin + width * (np.arange(args.nchan) + 0.5)
    nvis = nrow * args.nchan
    sigma_i = args.noise_ujy * 1e-6 * math.sqrt(nvis)
    sigma_c = sigma_i * math.sqrt(2.0)
    comps = draw_sky(RECIPE[args.sky], args.size, args.scale, sky_seed)
    for c in comps:
        c["ra_rad"], c["dec_rad"] = bench.radec(c["l"], c["m"], ra, dec)
        c["flux_per_channel"] = spectrum(c, freq).tolist()
    arr = arrays(comps)

    sub_rows = np.unique(np.linspace(0, nrow - 1, 1500).astype(int))
    ti, bi = np.divmod(sub_rows, nbl)
    sub_uvw = ant_uvw[ti, a1[bi]] - ant_uvw[ti, a2[bi]]
    ref = direct(sub_uvw, freq, comps, arr)
    got = predict(sub_uvw, freq, arr)
    dft_check = {
        "rows": len(sub_rows),
        "max_abs_diff": float(np.abs(got - ref).max()),
        "relative": float(np.abs(got - ref).max() / np.abs(ref).max()),
    }
    if dft_check["relative"] > 1e-7:
        raise SystemExit(f"core DFT disagrees with NumPy: {dft_check}")

    out = Path(args.ms)
    t = bench.create_ms(out, nrow, args.nchan, 4)
    t.close()
    bench.fill_subtables(out, names, xyz, diameter, freq, ra, dec, times, args.dt)
    t = tables.table(str(out), readonly=False)
    rng = np.random.default_rng(noise_seed)
    w_corr = np.float32(1.0 / sigma_c**2)
    seconds = {"predict": 0.0, "write": 0.0}
    try:
        for t0 in range(0, ntime, args.chunk_times):
            t1 = min(ntime, t0 + args.chunk_times)
            nt = t1 - t0
            r0, n = t0 * nbl, nt * nbl
            uvw = (ant_uvw[t0:t1, a1] - ant_uvw[t0:t1, a2]).reshape(n, 3)
            s = time.perf_counter()
            model = predict(uvw, freq, arr)
            seconds["predict"] += time.perf_counter() - s
            g = rng.standard_normal((n, args.nchan, 4, 2))
            data = (g[..., 0] + 1j * g[..., 1]) * sigma_c
            data[..., 0] += model
            data[..., 3] += model
            s = time.perf_counter()
            t.putcol("UVW", uvw, r0, n)
            t.putcol("DATA", data.astype(np.complex64), r0, n)
            t.putcol("WEIGHT_SPECTRUM", np.full((n, args.nchan, 4), w_corr), r0, n)
            t.putcol("FLAG", np.zeros((n, args.nchan, 4), bool), r0, n)
            t.putcol("WEIGHT", np.full((n, 4), w_corr), r0, n)
            t.putcol("SIGMA", np.full((n, 4), np.float32(sigma_c)), r0, n)
            t.putcol("TIME", np.repeat(times[t0:t1], nbl), r0, n)
            t.putcol("TIME_CENTROID", np.repeat(times[t0:t1], nbl), r0, n)
            t.putcol("ANTENNA1", np.tile(a1, nt).astype(np.int32), r0, n)
            t.putcol("ANTENNA2", np.tile(a2, nt).astype(np.int32), r0, n)
            t.putcol("INTERVAL", np.full(n, args.dt), r0, n)
            t.putcol("EXPOSURE", np.full(n, args.dt), r0, n)
            t.putcol("FLAG_ROW", np.zeros(n, bool), r0, n)
            for col, value in (
                ("FIELD_ID", 0),
                ("DATA_DESC_ID", 0),
                ("SCAN_NUMBER", 1),
                ("ARRAY_ID", 0),
                ("OBSERVATION_ID", 0),
                ("FEED1", 0),
                ("FEED2", 0),
                ("PROCESSOR_ID", -1),
                ("STATE_ID", -1),
            ):
                t.putcol(col, np.full(n, value, np.int32), r0, n)
            seconds["write"] += time.perf_counter() - s
    finally:
        t.close()
    meta = {
        "ms": str(out.resolve()),
        "sky": args.sky,
        "recipe": RECIPE[args.sky],
        "sky_seed": sky_seed,
        "noise_seed": noise_seed,
        "nu0_hz": NU0,
        "nant": nant,
        "ntime": ntime,
        "nrow": nrow,
        "nchan": args.nchan,
        "freq_hz": freq.tolist(),
        "channel_width_hz": width,
        "dt_s": args.dt,
        "hours": args.hours,
        "ra_rad": ra,
        "dec_rad": dec,
        "noise": {
            "natural_image_ujy_target": args.noise_ujy,
            "sigma_stokes_i_per_component_jy": sigma_i,
            "sigma_correlation_per_component_jy": sigma_c,
        },
        "image": {"size": args.size, "scale_arcsec": args.scale},
        "dft_check": dft_check,
        "components": comps,
        "seconds": {**seconds, "total": time.perf_counter() - t_start},
        "main_table_sha256": bench.main_table_sha256(out),
    }
    if args.catalogue:
        Path(args.catalogue).write_text(
            json.dumps(meta, indent=1) + "\n", encoding="utf-8"
        )
    print(json.dumps({k: meta[k] for k in ("sky", "nrow", "seconds", "dft_check")}))


if __name__ == "__main__":
    main()
