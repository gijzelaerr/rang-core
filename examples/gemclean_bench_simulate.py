"""Simulated full-MeerKAT Measurement Sets for the gemclean benchmark.

Research note: research/gemclean-benchmark.md. Builds a 64-dish MeerKAT
track (data/meerkat.itrf.txt) at declination -30 deg, predicts a sky of
point sources (and, for S2, a Gaussian disc) exactly by direct Fourier sums
through the core (`rang.core.predict_components`, f64, positive phase as in
the MS), adds Gaussian noise from a fixed seed, and writes the Measurement
Set with rang's own casacore table writer (`rang.core_ms_write`, task E4).

Skies (all flat spectrum, positions continuous, not on pixel centres):

    S1  50 points, fluxes log-uniform 10 mJy - 1 Jy, uniform positions inside
        the inner two-thirds of the 2048 x 1.5 arcsec field, at least
        --min-sep pixels apart
    S2  S1 plus a circular Gaussian of FWHM 40 arcsec and 2 Jy at the point
        of the inner field farthest from every S1 source
    S3  500 points, fluxes log-uniform 0.1 - 100 mJy (three decades), uniform
        positions inside the inner two-thirds, no separation constraint
    none  noise only

Held-out skies for research/gemclean-heldout.md, drawn after the stop rule's
constants were fixed, with their own sky and noise seeds:

    H1  dec -75 (low elevation, south): 60 points, 5 mJy - 1 Jy, min-sep 10 px
    H2  dec +10 (low declination, north): 300 points, 0.2 - 200 mJy, blended
    H3  wider field, 4096 x 1.5 arcsec (1.7 deg), dec -30: 120 points, 5 mJy - 1 Jy
    H4  extended emission, dec -45: 30 points, 5 - 300 mJy, 6 Gaussians of FWHM
        20 - 200 arcsec and 0.1 - 2 Jy, and a curved tail of 25 overlapping
        Gaussians of FWHM 30 - 60 arcsec holding 3 Jy

Held-out sky for research/g5-multiscale.md, its seeds given on the command
line (--sky-seed, --noise-seed) as drawn after the multiscale build was frozen:

    M1  H4's recipe at dec -60

Positions are drawn as pixel offsets (x, y) of WSClean's FITS grid (centre
pixel N/2, 0-based; x grows to the west) and turned into direction cosines
l = -(x - N/2) * scale, m = (y - N/2) * scale (SIN projection: the WSClean
grid is linear in l and m). The noise is complex Gaussian on all four
correlations with sigma per real and per imaginary part (the MS SIGMA,
WEIGHT = 1/SIGMA^2) of sqrt(2) * noise_ujy * sqrt(nvis), so that Stokes I
= (XX + YY)/2 has sigma noise_ujy * sqrt(nvis) per part and the
natural-weight image noise is --noise-ujy; XX = YY = I, XY = YX = noise. The same noise
seed and chunking give the same noise for every sky.

Usage:
    .venv/bin/python examples/gemclean_bench_simulate.py OUT.ms --sky S1 \
        [--nant 64] [--hours 2] [--dt 8] [--catalogue OUT.json] [--noise-out NOISE.c64]
"""

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
from rang import core
from rang import core_ms_write as tables

C = 299_792_458.0
ARCSEC = math.pi / (180.0 * 3600.0)
ROOT = Path(__file__).resolve().parents[1]
ITRF = ROOT / "data" / "meerkat.itrf.txt"
# 2026-03-01T00:00:00 UTC as MJD seconds; the RA is set so that the track
# runs from hour angle -hours/2 to +hours/2.
T_REF_MJD = 61100.0
DEC_DEG = -30.0
SKY_SEEDS = {
    "S1": 20261102,
    "S2": 20261102,
    "S3": 20261103,
    "H1": 20261201,
    "H2": 20261202,
    "H3": 20261203,
    "H4": 20261204,
}
NOISE_SEED = 20261104
NOISE_SEEDS = {"H1": 20261211, "H2": 20261212, "H3": 20261213, "H4": 20261214}
DEC_BY_SKY = {"H1": -75.0, "H2": 10.0, "H4": -45.0, "M1": -60.0}


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def main_table_sha256(ms):
    """SHA-256 of every file directly in the MS directory (the main table)."""
    ms = Path(ms)
    return {p.name: _sha(p) for p in sorted(ms.iterdir()) if p.is_file()}


def antennas(nant):
    rows = [line.split() for line in ITRF.read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if r and not r[0].startswith("#")][:nant]
    xyz = np.array([[float(v) for v in r[:3]] for r in rows])
    diameter = np.array([float(r[3]) for r in rows])
    names = [r[4] for r in rows]
    return xyz, diameter, names


def gmst_rad(mjd):
    """Greenwich mean sidereal time (IAU 1982 linear form, enough here)."""
    jd = mjd + 2400000.5
    deg = 280.46061837 + 360.98564736629 * (jd - 2451545.0)
    return math.radians(deg % 360.0)


def track(xyz, hours, dt, dec_deg=DEC_DEG):
    """Times (MJD s), RA (rad) and per-antenna UVW (ntime, nant, 3)."""
    centre = xyz.mean(axis=0)
    lon = math.atan2(centre[1], centre[0])
    ntime = round(hours * 3600.0 / dt)
    t0 = T_REF_MJD * 86400.0
    times = t0 + dt * (np.arange(ntime) + 0.5)
    mid = (times[0] + times[-1]) / 2.0 / 86400.0
    ra = (gmst_rad(mid) + lon) % (2 * math.pi)
    dec = math.radians(dec_deg)
    # Greenwich hour angle per time; mean solar to sidereal rate.
    gha = np.array([gmst_rad(t / 86400.0) for t in times]) - ra
    rel = xyz - centre
    x, y, z = rel[:, 0], rel[:, 1], rel[:, 2]
    sh, ch = np.sin(gha)[:, None], np.cos(gha)[:, None]
    sd, cd = math.sin(dec), math.cos(dec)
    u = sh * x + ch * y
    v = -sd * ch * x + sd * sh * y + cd * z
    w = cd * ch * x - cd * sh * y + sd * z
    return times, ra, dec, np.stack([u, v, w], axis=-1), lon


def sky(name, size, scale_arcsec, min_sep, seed=None):
    """Component list: dicts with x, y (FITS pixels), l, m, flux, kind, fwhm."""
    if name == "none":
        return []
    rng = np.random.default_rng(SKY_SEEDS[name] if seed is None else seed)
    half = size / 3.0  # inner two-thirds: |offset| < size/3 pixels
    centre = size // 2

    def draw(n, lo, hi, sep):
        out = []
        while len(out) < n:
            x, y = rng.uniform(-half, half, 2)
            if sep and any((x - a) ** 2 + (y - b) ** 2 < sep**2 for a, b in out):
                continue
            out.append((x, y))
        flux = np.exp(rng.uniform(math.log(lo), math.log(hi), n))
        return out, flux

    if name in ("S1", "S2"):
        pos, flux = draw(50, 0.01, 1.0, min_sep)
    elif name == "H1":
        pos, flux = draw(60, 0.005, 1.0, min_sep)
    elif name == "H2":
        pos, flux = draw(300, 2e-4, 0.2, 0.0)
    elif name == "H3":
        pos, flux = draw(120, 0.005, 1.0, min_sep)
    elif name in ("H4", "M1"):
        pos, flux = draw(30, 0.005, 0.3, min_sep)
    else:
        pos, flux = draw(500, 1e-4, 0.1, 0.0)
    comps = [
        {"kind": "point", "dx": float(x), "dy": float(y), "flux": float(f)}
        for (x, y), f in zip(pos, flux, strict=True)
    ]
    if name == "S2":
        # The inner-field grid point farthest from every S1 source, keeping
        # a 3-FWHM margin from the edge of the inner two-thirds.
        fwhm_px = 40.0 / scale_arcsec
        lim = half - 3 * fwhm_px
        g = np.linspace(-lim, lim, 161)
        gx, gy = np.meshgrid(g, g)
        p = np.array(pos)
        d2 = np.min(
            (gx[..., None] - p[:, 0]) ** 2 + (gy[..., None] - p[:, 1]) ** 2, axis=-1
        )
        k = np.unravel_index(np.argmax(d2), d2.shape)
        comps.append(
            {
                "kind": "gaussian",
                "dx": float(gx[k]),
                "dy": float(gy[k]),
                "flux": 2.0,
                "fwhm_arcsec": 40.0,
                "nearest_point_px": float(math.sqrt(d2[k])),
            }
        )
    if name in ("H4", "M1"):
        margin = half - 220.0 / scale_arcsec
        for _ in range(6):
            x, y = rng.uniform(-margin, margin, 2)
            comps.append(
                {
                    "kind": "gaussian",
                    "dx": float(x),
                    "dy": float(y),
                    "flux": float(np.exp(rng.uniform(math.log(0.1), math.log(2.0)))),
                    "fwhm_arcsec": float(
                        np.exp(rng.uniform(math.log(20.0), math.log(200.0)))
                    ),
                }
            )
        # The tail: a quarter circle of radius 500 arcsec, flux falling along it.
        x0, y0 = rng.uniform(-margin / 2, margin / 2, 2)
        radius = 500.0 / scale_arcsec
        angles = np.linspace(0.0, math.pi / 2, 25) + rng.uniform(0, 2 * math.pi)
        along = np.exp(-np.linspace(0.0, 2.0, 25))
        along = 3.0 * along / along.sum()
        for a, f in zip(angles, along, strict=True):
            comps.append(
                {
                    "kind": "gaussian",
                    "dx": float(x0 + radius * math.cos(a)),
                    "dy": float(y0 + radius * math.sin(a)),
                    "flux": float(f),
                    "fwhm_arcsec": float(rng.uniform(30.0, 60.0)),
                }
            )
    scale = scale_arcsec * ARCSEC
    for c in comps:
        c["x"] = centre + c["dx"]
        c["y"] = centre + c["dy"]
        c["l"] = -c["dx"] * scale
        c["m"] = c["dy"] * scale
    return comps


def radec(l, m, ra0, dec0):
    """Inverse SIN projection."""
    n = math.sqrt(1.0 - l * l - m * m)
    dec = math.asin(m * math.cos(dec0) + n * math.sin(dec0))
    ra = ra0 + math.atan2(l, n * math.cos(dec0) - m * math.sin(dec0))
    return ra % (2 * math.pi), dec


def component_arrays(comps):
    n = len(comps)
    lm = np.array([[c["l"], c["m"]] for c in comps]).reshape(n, 2)
    kind = np.array([1 if c["kind"] == "gaussian" else 0 for c in comps])
    flux = np.array([c["flux"] for c in comps])
    shape = np.zeros((n, 3))
    for i, c in enumerate(comps):
        if c["kind"] == "gaussian":
            shape[i] = [c["fwhm_arcsec"] * ARCSEC, c["fwhm_arcsec"] * ARCSEC, 0.0]
    return {
        "lm": lm,
        "kind": kind,
        "flux": flux,
        "coeffs": np.zeros((n, 0)),
        "log_poly": np.zeros(n, bool),
        "ref_freq": np.full(n, 1.4e9),
        "gauss_shape": shape,
    }


def predict(uvw, freq, arrays):
    if len(arrays["flux"]) == 0:
        return np.zeros((len(uvw), len(freq)), np.complex128)
    return core.predict_components(
        uvw,
        freq,
        arrays["lm"],
        arrays["kind"],
        arrays["flux"],
        arrays["coeffs"],
        arrays["log_poly"],
        arrays["ref_freq"],
        arrays["gauss_shape"],
    )


def direct_dft(uvw, freq, arrays):
    """Independent NumPy sum (positive phase, circular Gaussians)."""
    u, v, w = (uvw[:, k][:, None, None] for k in range(3))
    nu = freq[None, :, None]
    l, m = arrays["lm"][:, 0], arrays["lm"][:, 1]
    n1 = np.sqrt(1.0 - l * l - m * m) - 1.0
    phase = 2 * np.pi * nu / C * (u * l + v * m + w * n1)
    fwhm = arrays["gauss_shape"][:, 0]
    q2 = (u**2 + v**2) * (nu / C) ** 2
    env = np.exp(-(np.pi**2) / (4 * math.log(2)) * fwhm**2 * q2)
    return np.sum(arrays["flux"] * env * np.exp(1j * phase), axis=-1)


def create_ms(path, nrow, nchan, ncorr):
    desc = [
        tables.makearrcoldesc(
            "DATA", 0j, shape=[nchan, ncorr], valuetype="complex", comment="data"
        ),
        tables.makearrcoldesc(
            "WEIGHT_SPECTRUM", 0.0, shape=[nchan, ncorr], valuetype="float"
        ),
        tables.makearrcoldesc("FLAG", False, shape=[nchan, ncorr]),
        tables.makearrcoldesc("WEIGHT", 0.0, shape=[ncorr], valuetype="float"),
        tables.makearrcoldesc("SIGMA", 0.0, shape=[ncorr], valuetype="float"),
    ]
    rows_per_tile = max(1, 32768 // (nchan * ncorr))
    dminfo = {
        "*1": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledData",
            "COLUMNS": ["DATA"],
            "SPEC": {"DEFAULTTILESHAPE": [ncorr, nchan, rows_per_tile]},
        },
        "*2": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledWeightSpectrum",
            "COLUMNS": ["WEIGHT_SPECTRUM"],
            "SPEC": {"DEFAULTTILESHAPE": [ncorr, nchan, rows_per_tile]},
        },
        "*3": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledFlag",
            "COLUMNS": ["FLAG"],
            "SPEC": {"DEFAULTTILESHAPE": [ncorr, nchan, rows_per_tile * 8]},
        },
    }
    t = tables.default_ms(str(path), desc, dminfo)
    t.addrows(nrow)
    return t


def fill_subtables(ms, names, xyz, diameter, freq, ra, dec, times, dt):
    nant, nchan = len(names), len(freq)
    width = float(freq[1] - freq[0]) if nchan > 1 else 25e6

    def sub(name, nrow):
        t = tables.table(str(Path(ms) / name), readonly=False)
        if nrow:
            t.addrows(nrow)
        return t

    with sub("ANTENNA", nant) as t:
        t.putcol("NAME", np.array(names))
        t.putcol("STATION", np.array(names))
        t.putcol("TYPE", np.array(["GROUND-BASED"] * nant))
        t.putcol("MOUNT", np.array(["ALT-AZ"] * nant))
        t.putcol("POSITION", xyz)
        t.putcol("OFFSET", np.zeros((nant, 3)))
        t.putcol("DISH_DIAMETER", diameter)
        t.putcol("FLAG_ROW", np.zeros(nant, bool))
    with sub("FEED", nant) as t:
        t.putcol("ANTENNA_ID", np.arange(nant, dtype=np.int32))
        t.putcol("FEED_ID", np.zeros(nant, np.int32))
        t.putcol("SPECTRAL_WINDOW_ID", np.full(nant, -1, np.int32))
        t.putcol("TIME", np.full(nant, (times[0] + times[-1]) / 2))
        t.putcol("INTERVAL", np.full(nant, times[-1] - times[0] + dt))
        t.putcol("NUM_RECEPTORS", np.full(nant, 2, np.int32))
        t.putcol("BEAM_ID", np.full(nant, -1, np.int32))
        for i in range(nant):
            t.putcell("BEAM_OFFSET", i, np.zeros((2, 2)))
            t.putcell("POLARIZATION_TYPE", i, np.array(["X", "Y"]))
            t.putcell("POL_RESPONSE", i, np.eye(2, dtype=np.complex64))
            t.putcell("RECEPTOR_ANGLE", i, np.array([-math.pi / 2, 0.0]))
        t.putcol("POSITION", np.zeros((nant, 3)))
    with sub("SPECTRAL_WINDOW", 1) as t:
        t.putcell("CHAN_FREQ", 0, freq)
        t.putcell("CHAN_WIDTH", 0, np.full(nchan, width))
        t.putcell("EFFECTIVE_BW", 0, np.full(nchan, width))
        t.putcell("RESOLUTION", 0, np.full(nchan, width))
        t.putcol("REF_FREQUENCY", np.array([float(freq.mean())]))
        t.putcol("NUM_CHAN", np.array([nchan], np.int32))
        t.putcol("TOTAL_BANDWIDTH", np.array([width * nchan]))
        t.putcol("MEAS_FREQ_REF", np.array([5], np.int32))
        t.putcol("NAME", np.array(["L-band"]))
        t.putcol("NET_SIDEBAND", np.array([1], np.int32))
        t.putcol("FREQ_GROUP", np.array([0], np.int32))
        t.putcol("FREQ_GROUP_NAME", np.array(["Group 1"]))
        t.putcol("IF_CONV_CHAIN", np.array([0], np.int32))
        t.putcol("FLAG_ROW", np.array([False]))
    with sub("POLARIZATION", 1) as t:
        t.putcol("NUM_CORR", np.array([4], np.int32))
        t.putcell("CORR_TYPE", 0, np.array([9, 10, 11, 12], np.int32))
        t.putcell(
            "CORR_PRODUCT", 0, np.array([[0, 0], [0, 1], [1, 0], [1, 1]], np.int32)
        )
        t.putcol("FLAG_ROW", np.array([False]))
    with sub("DATA_DESCRIPTION", 1) as t:
        t.putcol("SPECTRAL_WINDOW_ID", np.array([0], np.int32))
        t.putcol("POLARIZATION_ID", np.array([0], np.int32))
        t.putcol("FLAG_ROW", np.array([False]))
    with sub("FIELD", 1) as t:
        direction = np.array([[ra, dec]])
        for col in ("DELAY_DIR", "PHASE_DIR", "REFERENCE_DIR"):
            t.putcell(col, 0, direction)
        t.putcol("NAME", np.array(["GEMCLEAN_BENCH"]))
        t.putcol("CODE", np.array(["T"]))
        t.putcol("TIME", np.array([times[0]]))
        t.putcol("NUM_POLY", np.array([0], np.int32))
        t.putcol("SOURCE_ID", np.array([-1], np.int32))
        t.putcol("FLAG_ROW", np.array([False]))
    with sub("OBSERVATION", 1) as t:
        t.putcol("TELESCOPE_NAME", np.array(["MeerKAT"]))
        t.putcell("TIME_RANGE", 0, np.array([times[0] - dt / 2, times[-1] + dt / 2]))
        t.putcol("OBSERVER", np.array(["rang gemclean-bench simulation"]))
        t.putcol("PROJECT", np.array(["gemclean-bench"]))
        t.putcol("RELEASE_DATE", np.array([times[0]]))
        t.putcol("SCHEDULE_TYPE", np.array([""]))
        t.putcell("LOG", 0, np.array([""]))
        t.putcell("SCHEDULE", 0, np.array([""]))
        t.putcol("FLAG_ROW", np.array([False]))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ms")
    p.add_argument(
        "--sky",
        choices=["S1", "S2", "S3", "H1", "H2", "H3", "H4", "M1", "none"],
        required=True,
    )
    p.add_argument("--nant", type=int, default=64)
    p.add_argument("--hours", type=float, default=2.0)
    p.add_argument("--dt", type=float, default=8.0)
    p.add_argument("--nchan", type=int, default=8)
    p.add_argument("--fmin", type=float, default=1.3e9)
    p.add_argument("--fmax", type=float, default=1.5e9)
    p.add_argument("--size", type=int, default=2048)
    p.add_argument("--scale", type=float, default=1.5, help="arcsec per pixel")
    p.add_argument("--min-sep", type=float, default=10.0, help="S1 pixels")
    p.add_argument("--noise-ujy", type=float, default=20.0)
    p.add_argument("--chunk-times", type=int, default=25)
    p.add_argument("--catalogue")
    p.add_argument("--noise-out", help="write the Stokes I noise (row, chan) c64")
    p.add_argument("--sky-override", help="JSON list of components (tests)")
    p.add_argument("--sky-seed", type=int, help="the sky seed (M1 needs it)")
    p.add_argument("--noise-seed", type=int, help="the noise seed (M1 needs it)")
    args = p.parse_args(argv)
    if args.sky == "M1" and (args.sky_seed is None or args.noise_seed is None):
        p.error("M1 needs --sky-seed and --noise-seed")

    t_start = time.perf_counter()
    xyz, diameter, names = antennas(args.nant)
    nant = len(names)
    dec_deg = DEC_BY_SKY.get(args.sky, DEC_DEG)
    times, ra, dec, ant_uvw, lon = track(xyz, args.hours, args.dt, dec_deg)
    a1, a2 = np.triu_indices(nant, 1)
    nbl, ntime = len(a1), len(times)
    nrow = nbl * ntime
    width = (args.fmax - args.fmin) / args.nchan
    freq = args.fmin + width * (np.arange(args.nchan) + 0.5)
    nvis = nrow * args.nchan
    sigma_i = args.noise_ujy * 1e-6 * math.sqrt(nvis)
    sigma_c = sigma_i * math.sqrt(2.0)
    if args.sky_override:
        comps = json.loads(Path(args.sky_override).read_text(encoding="utf-8"))
        scale = args.scale * ARCSEC
        for c in comps:
            c["x"], c["y"] = args.size // 2 + c["dx"], args.size // 2 + c["dy"]
            c["l"], c["m"] = -c["dx"] * scale, c["dy"] * scale
    else:
        comps = sky(args.sky, args.size, args.scale, args.min_sep, args.sky_seed)
    for c in comps:
        c["ra_rad"], c["dec_rad"] = radec(c["l"], c["m"], ra, dec)
    arrays = component_arrays(comps)

    # Check the core DFT against the NumPy sum on a row subset.
    sub_rows = np.unique(np.linspace(0, nrow - 1, 2000).astype(int))
    ti, bi = np.divmod(sub_rows, nbl)
    sub_uvw = ant_uvw[ti, a1[bi]] - ant_uvw[ti, a2[bi]]
    dft_check = None
    if comps:
        ref = direct_dft(sub_uvw, freq, arrays)
        got = predict(sub_uvw, freq, arrays)
        dft_check = {
            "rows": len(sub_rows),
            "max_abs_diff": float(np.abs(got - ref).max()),
            "max_abs_ref": float(np.abs(ref).max()),
            "relative": float(np.abs(got - ref).max() / np.abs(ref).max()),
        }
        if dft_check["relative"] > 1e-7:
            raise SystemExit(f"core DFT disagrees with NumPy: {dft_check}")

    out = Path(args.ms)
    t_tab0 = time.perf_counter()
    t = create_ms(out, nrow, args.nchan, 4)
    t.close()
    fill_subtables(out, names, xyz, diameter, freq, ra, dec, times, args.dt)
    t = tables.table(str(out), readonly=False)
    noise_seed = NOISE_SEEDS.get(args.sky, NOISE_SEED)
    if args.noise_seed is not None:
        noise_seed = args.noise_seed
    rng = np.random.default_rng(noise_seed)
    noise_file = open(args.noise_out, "wb") if args.noise_out else None  # noqa: SIM115
    seconds = {"predict": 0.0, "noise": 0.0, "write": 0.0}
    w_corr = np.float32(1.0 / sigma_c**2)
    try:
        for t0 in range(0, ntime, args.chunk_times):
            t1 = min(ntime, t0 + args.chunk_times)
            nt = t1 - t0
            r0, n = t0 * nbl, nt * nbl
            uvw = (ant_uvw[t0:t1, a1] - ant_uvw[t0:t1, a2]).reshape(n, 3)
            s = time.perf_counter()
            model = predict(uvw, freq, arrays)
            seconds["predict"] += time.perf_counter() - s
            s = time.perf_counter()
            g = rng.standard_normal((n, args.nchan, 4, 2))
            # sigma_c per real and per imaginary part (the MS SIGMA); Stokes
            # I = (XX + YY) / 2 then has sigma_i per part.
            noise = (g[..., 0] + 1j * g[..., 1]) * sigma_c
            data = noise.copy()
            data[..., 0] += model
            data[..., 3] += model
            if noise_file is not None:
                stokes = (0.5 * (noise[..., 0] + noise[..., 3])).astype(np.complex64)
                noise_file.write(stokes.tobytes())
            seconds["noise"] += time.perf_counter() - s
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
        if noise_file is not None:
            noise_file.close()
    t_end = time.perf_counter()
    meta = {
        "ms": str(out.resolve()),
        "sky": args.sky,
        "sky_seed": SKY_SEEDS.get(args.sky) if args.sky_seed is None else args.sky_seed,
        "noise_seed": NOISE_SEED if args.noise_seed is None else args.noise_seed,
        "chunk_times": args.chunk_times,
        "nant": nant,
        "ntime": ntime,
        "nbaseline": nbl,
        "nrow": nrow,
        "nchan": args.nchan,
        "nvis": nvis,
        "freq_hz": freq.tolist(),
        "dt_s": args.dt,
        "hours": args.hours,
        "ra_rad": ra,
        "dec_rad": dec,
        "array_longitude_rad": lon,
        "time_range_mjd_s": [float(times[0]), float(times[-1])],
        "noise": {
            "natural_image_ujy_target": args.noise_ujy,
            "sigma_stokes_i_per_component_jy": sigma_i,
            "sigma_correlation_per_component_jy": sigma_c,
            "weight_per_correlation": float(w_corr),
        },
        "image": {"size": args.size, "scale_arcsec": args.scale},
        "uvw_convention": "per-antenna uvw(ANTENNA1) - uvw(ANTENNA2), as katdal/mvftoms",
        "max_baseline_m": float(np.linalg.norm(xyz[a1] - xyz[a2], axis=1).max()),
        "dft_check": dft_check,
        "components": comps,
        "writer": "rang.core_ms_write (rang's casacore table writer, task E4)",
        "seconds": {
            **seconds,
            "tables_total": t_end - t_tab0,
            "total": t_end - t_start,
        },
        "main_table_sha256": main_table_sha256(out),
    }
    if args.noise_out:
        meta["noise_out"] = str(Path(args.noise_out).resolve())
        meta["noise_out_sha256"] = _sha(args.noise_out)
    if args.catalogue:
        Path(args.catalogue).write_text(
            json.dumps(meta, indent=1) + "\n", encoding="utf-8"
        )
    print(json.dumps({k: meta[k] for k in ("nrow", "nvis", "seconds", "dft_check")}))


if __name__ == "__main__":
    main()
