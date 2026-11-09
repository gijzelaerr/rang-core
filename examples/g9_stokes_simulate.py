"""Simulated polarised MeerKAT skies for GeMClean's Stokes imaging (task G9).

Research note: research/g9-stokes.md (the rule, written before any comparison).
Built on G3's simulator (examples/g3_spectral_simulate.py) and the benchmark's
(examples/gemclean_bench_simulate.py): MeerKAT dishes, exact direct Fourier
sums through the core (`rang.core.predict_components`, one call per channel
and Stokes parameter with that channel's flux), rang's own table writer, noise
on all four correlations. The correlations are the sky-frame coherencies of
WSClean's convention (aocommon/polarization.h; X north-south):

    XX = I + Q,  XY = U + iV,  YX = U - iV,  YY = I - Q,

as calibrated linear-feed data are after the parallactic angle is applied.
Every source has I(nu) = S0 (nu / nu0) ** alpha (nu0 = 1.2 GHz), linear
polarisation p I(nu) at the angle chi(nu) = chi0 + RM (lambda^2 - lambda0^2)
(lambda0 at nu0) and circular polarisation v I(nu):

    Q = p I cos 2 chi,  U = p I sin 2 chi,  V = v I.

Skies (positions continuous, inside the inner two-thirds of size x scale):

    P1     development: 36 points, S0 log-uniform 5-500 mJy, alpha in
           [-1.2, 0.3]; two thirds linearly polarised (p uniform 0.02-0.3,
           chi0 uniform, RM uniform in [-20, 20] rad/m^2 for half of them,
           else 0), every fourth circularly polarised (|v| uniform
           0.005-0.05, random sign), the rest unpolarised; 40 pixels apart;
           dec -30
    H1p    held out: P1's recipe at dec -45 (seeds given on the command line)
    probe  two points for the oracle probe: A (I = 1, Q = -0.8) and
           B (I = 0.6, Q = +0.5), unpolarised otherwise

`--weights varied` gives every correlation its own weight (per-antenna factors
per hand, cross hands lower), noise drawn with those weights, and flags on
single correlations (XY only, YY only) besides whole cells.

Usage:
    .venv/bin/python examples/g9_stokes_simulate.py OUT.ms --sky P1 --catalogue OUT.json
    .venv/bin/python examples/g9_stokes_simulate.py OUT.ms --sky H1p \
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
LAMBDA0_SQ = (C / NU0) ** 2
# Not in rang.simtruth.SEEDS, nor taken by G3 (20261161-62, 20261171-72) or
# E0's tests (20261191-93).
SEEDS = {"P1": (20261181, 20261182), "probe": (20261183, 20261184)}
DEC = {"P1": -30.0, "H1p": -45.0, "probe": -30.0}


def stokes(c, freq):
    """I, Q, U, V of component `c` at `freq` (arrays of len(freq))."""
    nu = np.asarray(freq, float)
    i = c["flux"] * (nu / NU0) ** c["alpha"]
    chi = c["chi0_rad"] + c["rm"] * ((C / nu) ** 2 - LAMBDA0_SQ)
    q = c["p"] * i * np.cos(2 * chi)
    u = c["p"] * i * np.sin(2 * chi)
    v = c["v"] * i
    return i, q, u, v


def draw_sky(name, size, scale_arcsec, seed):
    rng = np.random.default_rng(seed)
    half = size / 3.0
    comps = []
    if name == "probe":
        for dx, dy, flux, q in ((-60.0, 40.0, 1.0, -0.8), (70.0, -50.0, 0.6, 0.5)):
            p = abs(q) / flux
            chi0 = 0.0 if q > 0 else math.pi / 2
            comps.append(
                {"kind": "point", "dx": dx, "dy": dy, "flux": flux, "alpha": 0.0}
                | {"p": p, "chi0_rad": chi0, "rm": 0.0, "v": 0.0}
            )
    else:
        for i in range(36):
            while True:
                x, y = rng.uniform(-half, half, 2)
                if all(
                    (x - c["dx"]) ** 2 + (y - c["dy"]) ** 2 >= 40.0**2 for c in comps
                ):
                    break
            c = {
                "kind": "point",
                "dx": float(x),
                "dy": float(y),
                "flux": float(np.exp(rng.uniform(math.log(5e-3), math.log(0.5)))),
                "alpha": float(rng.uniform(-1.2, 0.3)),
                "p": 0.0,
                "chi0_rad": 0.0,
                "rm": 0.0,
                "v": 0.0,
            }
            linear = i % 3 != 2
            if linear:
                c["p"] = float(rng.uniform(0.02, 0.3))
                c["chi0_rad"] = float(rng.uniform(-math.pi / 2, math.pi / 2))
                if i % 2 == 0:
                    c["rm"] = float(rng.uniform(-20.0, 20.0))
            if i % 4 == 3:
                c["v"] = float(rng.choice([-1.0, 1.0]) * rng.uniform(0.005, 0.05))
            comps.append(c)
    scale = scale_arcsec * ARCSEC
    centre = size // 2
    for c in comps:
        c["x"], c["y"] = centre + c["dx"], centre + c["dy"]
        c["l"], c["m"] = -c["dx"] * scale, c["dy"] * scale
    return comps


def predict_stokes(uvw, freq, comps):
    """(nrow, nchan, 4) visibilities of I, Q, U, V, one channel at a time."""
    n = len(comps)
    lm = np.array([[c["l"], c["m"]] for c in comps]).reshape(n, 2)
    spectra = np.array([np.stack(stokes(c, freq)) for c in comps])  # (n, 4, nchan)
    out = np.zeros((len(uvw), len(freq), 4), np.complex128)
    for ch in range(len(freq)):
        for s in range(4):
            flux = spectra[:, s, ch]
            if not np.any(flux):
                continue
            out[:, ch : ch + 1, s] = core.predict_components(
                uvw,
                np.array([freq[ch]]),
                lm,
                np.zeros(n, np.int64),
                flux.astype(float),
                np.zeros((n, 0)),
                np.zeros(n, bool),
                np.full(n, NU0),
                np.zeros((n, 3)),
            )
    return out


def direct(uvw, freq, comps):
    """Independent NumPy sum of Stokes I and Q (positive phase), for the check."""
    u, v, w = (uvw[:, k][:, None, None] for k in range(3))
    nu = freq[None, :, None]
    l = np.array([c["l"] for c in comps])
    m = np.array([c["m"] for c in comps])
    n1 = np.sqrt(1.0 - l * l - m * m) - 1.0
    phase = np.exp(1j * 2 * np.pi * nu / C * (u * l + v * m + w * n1))
    s = np.array([np.stack(stokes(c, freq)) for c in comps])  # (n, 4, nchan)
    return [np.sum(s[:, k, :].T[None] * phase, axis=-1) for k in range(4)]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ms")
    p.add_argument("--sky", choices=sorted(DEC), required=True)
    p.add_argument("--sky-seed", type=lambda s: int(s, 0))
    p.add_argument("--noise-seed", type=lambda s: int(s, 0))
    p.add_argument("--nant", type=int, default=64)
    p.add_argument("--hours", type=float, default=2.0)
    p.add_argument("--dt", type=float, default=16.0)
    p.add_argument("--nchan", type=int, default=16)
    p.add_argument("--fmin", type=float, default=0.9e9)
    p.add_argument("--fmax", type=float, default=1.67e9)
    p.add_argument("--size", type=int, default=2048)
    p.add_argument("--scale", type=float, default=1.5)
    p.add_argument("--noise-ujy", type=float, default=20.0)
    p.add_argument("--weights", choices=["uniform", "varied"], default="varied")
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
    xyz, diameter, names = bench.antennas(args.nant)
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
    w0 = 1.0 / sigma_c**2
    comps = draw_sky(args.sky, args.size, args.scale, sky_seed)
    for c in comps:
        c["ra_rad"], c["dec_rad"] = bench.radec(c["l"], c["m"], ra, dec)
        i, q, u, v = stokes(c, freq)
        c["stokes_per_channel"] = {
            "I": i.tolist(),
            "Q": q.tolist(),
            "U": u.tolist(),
            "V": v.tolist(),
        }

    sub_rows = np.unique(np.linspace(0, nrow - 1, 800).astype(int))
    ti, bi = np.divmod(sub_rows, nbl)
    sub_uvw = ant_uvw[ti, a1[bi]] - ant_uvw[ti, a2[bi]]
    ref = direct(sub_uvw, freq, comps)
    got = predict_stokes(sub_uvw, freq, comps)
    worst = max(
        float(np.abs(got[..., k] - ref[k]).max() / max(np.abs(ref[0]).max(), 1e-30))
        for k in range(4)
    )
    dft_check = {"rows": len(sub_rows), "relative_to_max_I": worst}
    if worst > 1e-7:
        raise SystemExit(f"core DFT disagrees with NumPy: {dft_check}")

    rng_w = np.random.default_rng(noise_seed + 1)
    # Per-antenna weight factors per hand (X, Y); cross hands 0.8 of the product.
    fx = rng_w.uniform(0.7, 1.3, nant) if args.weights == "varied" else np.ones(nant)
    fy = rng_w.uniform(0.7, 1.3, nant) if args.weights == "varied" else np.ones(nant)
    cross = 0.8 if args.weights == "varied" else 1.0
    wbl = (
        np.stack(
            [
                fx[a1] * fx[a2],
                cross * fx[a1] * fy[a2],
                cross * fy[a1] * fx[a2],
                fy[a1] * fy[a2],
            ],
            axis=-1,
        ).astype(np.float64)
        * w0
    )  # (nbl, 4)

    out = Path(args.ms)
    t = bench.create_ms(out, nrow, args.nchan, 4)
    t.close()
    bench.fill_subtables(out, names, xyz, diameter, freq, ra, dec, times, args.dt)
    t = tables.table(str(out), readonly=False)
    rng = np.random.default_rng(noise_seed)
    seconds = {"predict": 0.0, "write": 0.0}
    flags_total = np.zeros(4, np.int64)
    try:
        for t0 in range(0, ntime, args.chunk_times):
            t1 = min(ntime, t0 + args.chunk_times)
            nt = t1 - t0
            r0, n = t0 * nbl, nt * nbl
            uvw = (ant_uvw[t0:t1, a1] - ant_uvw[t0:t1, a2]).reshape(n, 3)
            s = time.perf_counter()
            sk = predict_stokes(uvw, freq, comps)
            seconds["predict"] += time.perf_counter() - s
            si, sq, su, sv = (sk[..., k] for k in range(4))
            model = np.stack([si + sq, su + 1j * sv, su - 1j * sv, si - sq], axis=-1)
            w = np.broadcast_to(np.tile(wbl, (nt, 1))[:, None, :], (n, args.nchan, 4))
            w = np.ascontiguousarray(w, dtype=np.float32)
            g = rng.standard_normal((n, args.nchan, 4, 2))
            data = model + (g[..., 0] + 1j * g[..., 1]) / np.sqrt(w.astype(float))
            flag = np.zeros((n, args.nchan, 4), bool)
            if args.weights == "varied":
                pick = rng_w.random((n, args.nchan))
                flag[pick < 0.02, 1] = True  # XY only
                flag[(pick >= 0.02) & (pick < 0.03), 3] = True  # YY only
                flag[(pick >= 0.03) & (pick < 0.035), :] = True  # whole cell
            flags_total += flag.sum(axis=(0, 1))
            s = time.perf_counter()
            t.putcol("UVW", uvw, r0, n)
            t.putcol("DATA", data.astype(np.complex64), r0, n)
            t.putcol("WEIGHT_SPECTRUM", w, r0, n)
            t.putcol("FLAG", flag, r0, n)
            t.putcol("WEIGHT", w[:, 0, :].copy(), r0, n)
            t.putcol("SIGMA", (1.0 / np.sqrt(w[:, 0, :])).astype(np.float32), r0, n)
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
        "sky_seed": sky_seed,
        "noise_seed": noise_seed,
        "weights": args.weights,
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
            "sigma_correlation_per_component_jy": sigma_c,
        },
        "flags_per_correlation": flags_total.tolist(),
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
