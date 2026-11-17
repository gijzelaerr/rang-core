# SPDX-License-Identifier: MIT
"""tfcrop probes, host side (research/v8-tfcrop.md, sections 3 and 6; every
output is labelled probe, never a gate case).

Usage:
  tfcrop_probe.py template OUT.ms NANT NTIME NCHAN
  tfcrop_probe.py design NAME TEMPLATE_INFO.json OUT_DIR
  tfcrop_probe.py job OUT_DIR WSL_DIR ARMSET

A template MS holds every (baseline, correlation) plane of NANT antennas,
NTIME integrations of 8 s in one scan and NCHAN channels; rows are time
major, baselines in order, so plane (b, c) is `rows b::nbl`, correlation c.

Designs (`DESIGNS`) write `NAME.npz` (DATA, FLAG) and `NAME.json` (each
plane's band shape, ladder and parameters). The ladder: rows t and
t + NTIME/2 carry the same relative amplitude e_t with opposite signs of the
alternating pattern (-1)^(t + f), so the time mean of every channel is the
band B(f) exactly, and each row's tfcrop threshold is crossed at a channel
only where CASA's fit F departs from B by more than about 2 e_t. One CASA
run then reads |B/F - 1| on a ladder of e for every channel of every plane.
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v8b_cases as vc

LADDER = np.geomspace(1e-4, 0.1, 20)


def template(out, nant, ntime, nchan):
    enu = [(np.cos(k * 2.4) * 40.0 * (k + 1), np.sin(k * 2.4) * 40.0 * (k + 1), 0.0)
           for k in range(nant)]  # fmt: skip
    xyz = vc.itrf_positions(enu)
    pairs = [(a, b) for a in range(nant) for b in range(a + 1, nant)]
    nbl = len(pairs)
    times = vc.T0 + 3 * 3600.0 + vc.DT * np.repeat(np.arange(ntime), nbl)
    a1 = np.tile([p[0] for p in pairs], ntime)
    a2 = np.tile([p[1] for p in pairs], ntime)
    field = ("PROBE", 1.2, -0.5)
    t = vc._ms(out, len(times), nchan)
    with t:
        vc._main_rows(t, times, a1, a2, np.ones(len(times)), np.zeros(len(times)),
                      vc.uvw(times, field[1], field[2], xyz, a1, a2))  # fmt: skip
        t.putcol("DATA", np.ones((len(times), nchan, 4), np.complex64))
        t.putcol("FLAG", np.zeros((len(times), nchan, 4), bool))
        t.putcol("FLAG_ROW", np.zeros(len(times), bool))
    vc._subtables(out, xyz, field, [(1.284e9, 208984.375, nchan)], "V8 tfcrop probe")
    info = {"nant": nant, "ntime": ntime, "nchan": nchan, "nbl": nbl}
    Path(str(out) + ".json").write_text(json.dumps(info), encoding="utf-8")
    return info


def shape_library(nchan):
    """Band shapes (positive), name -> array."""
    x = np.linspace(-1.0, 1.0, nchan)
    ch = np.arange(nchan)
    lib = {}
    for s in (0.0, 0.3, 0.9):
        lib[f"line{s}"] = 1.0 + s * x
    for k in (2, 3, 4, 5, 6):
        lib[f"poly{k}"] = 2.0 + x**k
    for p in (0.5, 1, 1.5, 2, 3, 4, 6):
        lib[f"sine{p}"] = 2.0 + np.sin(np.pi * p * x)
        lib[f"sineA{p}"] = 2.0 + 0.3 * np.sin(np.pi * p * x + 0.7)
    for at in (8, 16, 37, 64, 100, 128, 200, 240):
        lib[f"step{at}"] = np.where(ch < at, 1.0, 1.5)
        lib[f"stepS{at}"] = np.where(ch < at, 1.0, 1.05)
    for at in (8, 40, 128, 250):
        for d in (0.2, 0.9):
            lib[f"vee{at}-{d}"] = 1.0 - d * np.maximum(0, 1 - np.abs(ch - at) / 30)
    for c in (3, 30, 90, 128, 250):
        for w in (0.5, 1, 3, 8, 20):
            for h in (0.05, 0.5):
                lib[f"bump{c}-{w}-{h}"] = 1.0 + h * np.exp(-0.5 * ((ch - c) / w) ** 2)
    for c in (0, 1, 2, 5, 60, 127, 128, 200, 254, 255):
        for h in (0.01, 0.1, 1.0):
            b = np.ones(nchan)
            b[c] += h
            lib[f"spike{c}-{h}"] = b
            lib[f"lspike{c}-{h}"] = (1.0 + 0.5 * x) + np.where(ch == c, h, 0.0)
    return lib


def design_ladder(info, seed=1, mult=None):
    """Every plane a library shape (cycled, shuffled by `seed`) on the
    20-step ladder of e."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    half = ntime // 2
    assert half == len(LADDER)
    lib = shape_library(nchan)
    names = sorted(lib)
    rng = np.random.default_rng(seed)
    order = rng.permutation(nbl * 4)
    e = np.concatenate([LADDER, LADDER])
    sgn = np.where(np.arange(ntime) < half, 1.0, -1.0)[:, None] * (
        (-1.0) ** np.arange(nchan)[None, :]
    )
    pattern = 1.0 + e[:, None] * sgn
    data = np.empty((nbl * ntime, nchan, 4), np.complex64)
    planes = []
    for k in range(nbl * 4):
        b, c = divmod(int(order[k]), 4)
        name = names[k % len(names)]
        band = lib[name] * (1.0 if mult is None else mult[k % len(mult)])
        data[b::nbl, :, c] = (band[None, :] * pattern).astype(np.complex64)
        planes.append([b, c, name])
    return data, np.zeros(data.shape, bool), {"planes": planes, "e": e.tolist(),
                                               "sign": sgn[:, :2].tolist()}  # fmt: skip


def design_rows(info, seed=2, ladder=None):
    """Step-3 probe: every band is a straight line (so any line or
    polynomial fit of the time mean reproduces it), every row t < NTIME/2
    carries u_t(f) = e_t (-1)^f plus k outliers of random sign and graded
    amplitude (1 to 12 e_t), k in {0, 1, 2, 4, 8, 16, 32, 64}, and row
    t + NTIME/2 carries -u_t, so the time mean is the band exactly. The flags
    then read the per-row rule (centre, scale, iterations, cutoff)."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    half = ntime // 2
    lad = LADDER if ladder is None else ladder
    rng = np.random.default_rng(seed)
    data = np.empty((nbl * ntime, nchan, 4), np.complex64)
    planes = []
    x = np.linspace(-1.0, 1.0, nchan)
    for b in range(nbl):
        for c in range(4):
            level, slope = rng.uniform(0.5, 20.0), rng.uniform(-0.9, 0.9)
            band = level * (1.0 + slope * x)
            u = np.empty((half, nchan))
            for t in range(half):
                e = lad[t % len(lad)]
                u[t] = e * (-1.0) ** np.arange(nchan)
                k = int(rng.choice([0, 1, 2, 4, 8, 16, 32, 64]))
                at = rng.choice(nchan, k, replace=False)
                top = min(12.0, 0.8 / e - 1.0)  # keeps 1 + u > 0
                u[t, at] += rng.choice([-1.0, 1.0], k) * rng.uniform(1.0, top, k) * e
            u = np.concatenate([u, -u])
            data[b::nbl, :, c] = (band[None, :] * (1.0 + u)).astype(np.complex64)
            planes.append([b, c, f"line{level:.3f},{slope:.3f}"])
    return data, np.zeros(data.shape, bool), {"planes": planes}


def design_noise_rows(info, seed=3):
    """D1 boundary probe (S2): straight-line bands; row t < NTIME/2 carries
    u_t = sigma_t g (g Gaussian, clipped to +-0.9) with sigma_t stepped
    from 0.08 to 0.12 across rows and planes; one plane in four instead
    has sigma 0.05 plus 4-12 outliers of +-0.9 and a few values graded
    0.12-0.2, so that a row's sd drops by 0.1 or more between passes.
    Row t + NTIME/2 carries -u_t (time mean = band)."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    half = ntime // 2
    rng = np.random.default_rng(seed)
    data = np.empty((nbl * ntime, nchan, 4), np.complex64)
    planes = []
    x = np.linspace(-1.0, 1.0, nchan)
    k = 0
    for b in range(nbl):
        for c in range(4):
            level, slope = rng.uniform(0.5, 20.0), rng.uniform(-0.9, 0.9)
            band = level * (1.0 + slope * x)
            u = np.empty((half, nchan))
            heavy = k % 4 == 3
            for t in range(half):
                if heavy:
                    u[t] = np.clip(0.05 * rng.standard_normal(nchan), -0.9, 0.9)
                    n_out = int(rng.integers(4, 13))
                    at = rng.choice(nchan, n_out + 6, replace=False)
                    u[t, at[:n_out]] = rng.choice([-0.9, 0.9], n_out)
                    u[t, at[n_out:]] = rng.choice([-1.0, 1.0], 6) * rng.uniform(
                        0.12, 0.2, 6
                    )
                else:
                    s = 0.08 + 0.04 * ((t + 0.37 * k) % half) / (half - 1)
                    u[t] = np.clip(s * rng.standard_normal(nchan), -0.9, 0.9)
            u = np.concatenate([u, -u])
            data[b::nbl, :, c] = (band[None, :] * (1.0 + u)).astype(np.complex64)
            planes.append(
                [b, c, f"line{level:.6f},{slope:.6f}" + (",heavy" if heavy else "")]
            )
            k += 1
    return data, np.zeros(data.shape, bool), {"planes": planes}


READ_SHAPES = ("poly2", "poly3", "poly4", "poly6", "sine1", "sine2", "sineA3",
               "step64", "stepS128", "vee128-0.2", "bump90-8-0.05", "line0.9")  # fmt: skip


def design_readout(info, seed=4, amp=0.05):
    """Sparse readout (R1): planes of the READ_SHAPES (92 planes each).
    In row t, the channels f with (f + t) % 9 == 0 are test cells; channel
    f is hit by four rows (k = 0..3) with values +a, -a, +b, -b (a, b from a
    per-plane shifted ladder in [0.4, 1.6] * amp), so the time mean is the
    band exactly and every channel is seen with both signs; every other
    cell is the band itself. A test cell is flagged where
    |(B/F)(1 + delta) - 1| > cutoff * sd_row, so the + and - crossings
    bracket the misfit B/F - 1 at that channel."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    rng = np.random.default_rng(seed)
    lib = shape_library(nchan)
    data = np.empty((nbl * ntime, nchan, 4), np.complex64)
    planes = []
    ch = np.arange(nchan)
    for k in range(nbl * 4):
        b, c = divmod(k, 4)
        name = READ_SHAPES[k % len(READ_SHAPES)]
        band = lib[name]
        u = np.zeros((ntime, nchan))
        shift = rng.uniform(0, 1)
        for f in ch:
            t0 = (-f) % 9
            mags = amp * (
                0.4 + 1.2 * ((np.array([0.0, 0.5]) + shift + f * 0.618) % 1.0)
            )
            vals = (mags[0], -mags[0], mags[1], -mags[1])
            for j in range(4):
                t = t0 + 9 * j
                if t < ntime:
                    u[t, f] = vals[j]
            # A channel with fewer than four rows keeps its time mean zero.
            if t0 + 27 >= ntime:
                u[t0 + 18, f] = 0.0
                u[t0 + 9, f] = -u[t0, f]
        data[b::nbl, :, c] = (band[None, :] * (1.0 + u)).astype(np.complex64)
        planes.append([b, c, name])
    return data, np.zeros(data.shape, bool), {"planes": planes}


def design_noise(info, seed=5, sigma=0.1):
    """N1: `syn-noise`-like planes with a fresh seed (V8b's random smooth
    bandpass per plane times 1 + complex Gaussian noise of `sigma` per
    component), no flags. A stand-in for the development cases that is
    not a gate case."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    rng = np.random.default_rng(seed)
    bp = vc._bandpass(rng, nbl, nchan)  # (nbl, nchan, 4)
    shape = (ntime, nbl, nchan, 4)
    noise = (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)) * sigma
    data = (bp[None] * (1 + noise)).reshape(ntime * nbl, nchan, 4).astype(np.complex64)
    planes = [[b, c, "bandpass"] for b in range(nbl) for c in range(4)]
    return data, np.zeros(data.shape, bool), {"planes": planes}


def design_ladder_time(info, seed=6):
    """L1 transposed (LT): every plane's time series is a library shape
    (over NTIME integrations), on a ladder of e over channels (channels f
    and f + NCHAN/2 mirrored, so the mean over channels of every time is
    the shape exactly): the time-direction analogue of L1."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    half = nchan // 2
    lib = shape_library(ntime)
    names = sorted(lib)
    rng = np.random.default_rng(seed)
    order = rng.permutation(nbl * 4)
    lad = np.geomspace(1e-4, 0.1, half)
    e = np.concatenate([lad, lad])
    sgn = np.where(np.arange(nchan) < half, 1.0, -1.0)[None, :] * (
        (-1.0) ** np.arange(ntime)[:, None]
    )
    pattern = 1.0 + e[None, :] * sgn
    data = np.empty((nbl * ntime, nchan, 4), np.complex64)
    planes = []
    for k in range(nbl * 4):
        b, c = divmod(int(order[k]), 4)
        name = names[k % len(names)]
        data[b::nbl, :, c] = (lib[name][:, None] * pattern).astype(np.complex64)
        planes.append([b, c, name])
    return data, np.zeros(data.shape, bool), {"planes": planes}


DESIGNS = {
    "LT": lambda info: design_ladder_time(info, seed=6),
    "N1": lambda info: design_noise(info, seed=5),
    "L1": lambda info: design_ladder(info, seed=1),
    "S1": lambda info: design_rows(info, seed=2),
    "L1x0.01": lambda info: design_ladder(info, seed=1, mult=[0.01]),
    "L1x100": lambda info: design_ladder(info, seed=1, mult=[100.0]),
    "S2": lambda info: design_noise_rows(info, seed=3),
    "R1": lambda info: design_readout(info, seed=4),
    "NA": lambda info: design_noisy_average(info, seed=7),
    "NS": lambda info: design_scale_ladder(info, seed=10),
    "W1": lambda info: design_windows(info, seed=8),
    "F1": lambda info: design_preflagged(info, seed=9),
    "F2": lambda info: design_piece_counts(info, seed=11),
}


def _mirror_rows(rng, half, nchan, sd=0.03):
    """Rows t < half carry u_t (Gaussian, sd `sd`, clipped), rows t + half
    carry -u_t: the time mean is the plane's average spectrum exactly, and
    every row's sd stays below 0.1 (one D1 pass)."""
    u = np.clip(sd * rng.standard_normal((half, nchan)), -0.5, 0.5)
    return np.concatenate([u, -u])


def design_noisy_average(info, seed=7):
    """NA (the fit on noisy averages): each plane's time mean is a known
    spectrum A = m * B * (1 + eta * g), B a random positive line or cubic,
    g Gaussian per channel, eta in {0, 1e-3, 3e-3, 0.01, 0.03, 0.1}, one
    plane in four with 3-10 positive spikes (+0.2 to +2) in A, and a scale m
    in {0.01, 1, 100}. Rows are A * (1 + u) with mirrored u (D1 one pass),
    so the flags read CASA's fit of A through D1."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    half = ntime // 2
    rng = np.random.default_rng(seed)
    x = np.linspace(-1.0, 1.0, nchan)
    data = np.empty((nbl * ntime, nchan, 4), np.complex64)
    planes = []
    etas = (0.0, 1e-3, 3e-3, 0.01, 0.03, 0.1)
    scales = (0.01, 1.0, 100.0)
    for k in range(nbl * 4):
        b, c = divmod(k, 4)
        cubic = k % 2 == 1
        p = rng.normal(0, 0.3, 4) * (1.0 if cubic else np.array([1, 1, 0, 0]))
        band = 2.0 + p[0] * x + p[1] * x**2 * cubic + p[2] * x**3 * cubic
        if not cubic:
            band = 2.0 + p[0] * x
        eta = etas[(k // 2) % len(etas)]
        m = scales[(k // 12) % len(scales)]
        avg = band * (1.0 + eta * rng.standard_normal(nchan))
        spikes = k % 4 == 3
        if spikes:
            at = rng.choice(nchan, int(rng.integers(3, 11)), replace=False)
            avg[at] += rng.uniform(0.2, 2.0, len(at))
        avg = m * np.maximum(avg, 0.05 * m)
        u = _mirror_rows(rng, half, nchan)
        data[b::nbl, :, c] = (avg[None, :] * (1.0 + u)).astype(np.complex64)
        planes.append(
            [
                b,
                c,
                f"{'cubic' if cubic else 'line'},eta={eta},m={m},spikes={int(spikes)}",
            ]
        )
    return data, np.zeros(data.shape, bool), {"planes": planes}


SCALES = (1e-3, 1e-2, 0.1, 1.0, 10.0, 100.0, 1e4, 1e6)


def design_scale_ladder(info, seed=10):
    """NS (the absolute tolerance): NA-like planes in groups of eight that
    are identical up to an amplitude scale m in SCALES (same band, average
    noise, spikes and rows), so any flag that changes with m within a group
    is caused by an absolute constant in CASA."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    half = ntime // 2
    rng = np.random.default_rng(seed)
    x = np.linspace(-1.0, 1.0, nchan)
    data = np.empty((nbl * ntime, nchan, 4), np.complex64)
    planes = []
    etas = (0.0, 1e-3, 0.01, 0.03, 0.1)
    base = None
    for k in range(nbl * 4):
        b, c = divmod(k, 4)
        g, j = divmod(k, len(SCALES))
        m = SCALES[j]
        if j == 0:
            cubic = g % 2 == 1
            p = rng.normal(0, 0.3, 3)
            band = 2.0 + p[0] * x + ((p[1] * x**2 + p[2] * x**3) if cubic else 0.0)
            eta = etas[(g // 2) % len(etas)]
            avg = band * (1.0 + eta * rng.standard_normal(nchan))
            spikes = g % 4 == 3
            if spikes:
                at = rng.choice(nchan, int(rng.integers(3, 11)), replace=False)
                avg[at] += rng.uniform(0.2, 2.0, len(at))
            avg = np.maximum(avg, 0.05)
            base = (avg, _mirror_rows(rng, half, nchan), cubic, eta, spikes)
        avg, u, cubic, eta, spikes = base
        data[b::nbl, :, c] = ((m * avg)[None, :] * (1.0 + u)).astype(np.complex64)
        kind = "cubic" if cubic else "line"
        planes.append([b, c, f"g={g},{kind},eta={eta},spikes={int(spikes)},m={m}"])
    return data, np.zeros(data.shape, bool), {"planes": planes}


def design_windows(info, seed=8):
    """W1 (window statistics on an exact fit): straight-line bands (any fit
    reproduces them), mirrored rows with sd 0.03 plus structures along
    frequency: runs of 2-12 channels raised by 1-4 sd (sum), stretches of
    5-30 channels with 2-5 times the noise (std), and single spikes."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    half = ntime // 2
    rng = np.random.default_rng(seed)
    x = np.linspace(-1.0, 1.0, nchan)
    data = np.empty((nbl * ntime, nchan, 4), np.complex64)
    planes = []
    for k in range(nbl * 4):
        b, c = divmod(k, 4)
        band = rng.uniform(0.5, 20.0) * (1.0 + rng.uniform(-0.9, 0.9) * x)
        u = np.clip(0.03 * rng.standard_normal((half, nchan)), -0.3, 0.3)
        for t in range(half):
            for _ in range(int(rng.integers(0, 4))):
                w = int(rng.integers(2, 13))
                f0 = int(rng.integers(0, nchan - w))
                u[t, f0 : f0 + w] += rng.choice([-1, 1]) * rng.uniform(1, 4) * 0.03
            for _ in range(int(rng.integers(0, 3))):
                w = int(rng.integers(5, 31))
                f0 = int(rng.integers(0, nchan - w))
                u[t, f0 : f0 + w] *= rng.uniform(2, 5)
            if rng.random() < 0.3:
                u[t, int(rng.integers(0, nchan))] += rng.choice([-1, 1]) * 0.3
        u = np.clip(np.concatenate([u, -u]), -0.9, 0.9)
        data[b::nbl, :, c] = (band[None, :] * (1.0 + u)).astype(np.complex64)
        planes.append([b, c, "line"])
    return data, np.zeros(data.shape, bool), {"planes": planes}


def design_piece_counts(info, seed=11):
    """F2 (pieces with few valid channels): noisy line bands with mirrored
    rows (sd 0.03, NA-like average noise 0.01) and whole channels flagged so
    that one piece of a 7-piece (and of a 3-piece) split keeps exactly n
    valid channels, n = 0..9 cycled over planes; the other pieces keep at
    least 20. Reads the guard on short pieces (D5)."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    half = ntime // 2
    rng = np.random.default_rng(seed)
    x = np.linspace(-1.0, 1.0, nchan)
    data = np.empty((nbl * ntime, nchan, 4), np.complex64)
    flag = np.zeros(data.shape, bool)
    planes = []
    for k in range(nbl * 4):
        b, c = divmod(k, 4)
        band = rng.uniform(0.5, 20.0) * (1.0 + rng.uniform(-0.9, 0.9) * x)
        avg = band * (1.0 + 0.01 * rng.standard_normal(nchan))
        u = _mirror_rows(rng, half, nchan)
        n = k % 10
        split = 7 if (k // 10) % 2 == 0 else 3
        edges = np.linspace(0, nchan, split + 1).round().astype(int)
        piece = int(rng.integers(0, split))
        lo, hi = edges[piece], edges[piece + 1]
        chf = np.zeros(nchan, bool)
        keep = rng.choice(np.arange(lo, hi), n, replace=False) if n else []
        chf[lo:hi] = True
        chf[list(keep)] = False
        data[b::nbl, :, c] = (avg[None, :] * (1.0 + u)).astype(np.complex64)
        flag[b::nbl, :, c] = chf[None, :]
        planes.append([b, c, f"n={n},split={split},piece={piece}"])
    return data, flag, {"planes": planes}


def design_preflagged(info, seed=9):
    """F1 (pre-existing flags): S2-like planes (straight-line bands, mirrored
    rows, sd 0.03, a few outliers) with FLAG set before tfcrop: random cells
    (fraction 0-0.9), whole channels (0-90 %), whole rows (0-90 %), and one
    plane in eight wholly flagged except one row or one channel. Flags are
    set on both mirrored rows so the unflagged time mean stays the band."""
    nbl, ntime, nchan = info["nbl"], info["ntime"], info["nchan"]
    half = ntime // 2
    rng = np.random.default_rng(seed)
    x = np.linspace(-1.0, 1.0, nchan)
    data = np.empty((nbl * ntime, nchan, 4), np.complex64)
    flag = np.zeros(data.shape, bool)
    planes = []
    for k in range(nbl * 4):
        b, c = divmod(k, 4)
        band = rng.uniform(0.5, 20.0) * (1.0 + rng.uniform(-0.9, 0.9) * x)
        u = np.clip(0.03 * rng.standard_normal((half, nchan)), -0.5, 0.5)
        for t in range(half):
            at = rng.choice(nchan, 3, replace=False)
            u[t, at] = rng.choice([-1, 1], 3) * rng.uniform(0.1, 0.4, 3)
        u = np.concatenate([u, -u])
        f = np.zeros((half, nchan), bool)
        kind = k % 8
        frac = (k // 8) % 10 / 10.0
        if kind in (0, 1):
            f = rng.random((half, nchan)) < frac
        elif kind in (2, 3):
            f[:, rng.random(nchan) < frac] = True
        elif kind in (4, 5):
            f[rng.random(half) < frac, :] = True
        elif kind == 6:
            f[:] = True
            f[int(rng.integers(0, half)), :] = False
        else:
            f[:] = True
            f[:, int(rng.integers(0, nchan))] = False
        f = np.concatenate([f, f])
        data[b::nbl, :, c] = (band[None, :] * (1.0 + u)).astype(np.complex64)
        flag[b::nbl, :, c] = f
        planes.append([b, c, f"kind={kind},frac={frac}"])
    return data, flag, {"planes": planes}


def main(argv):
    cmd = argv[0]
    if cmd == "template":
        out, nant, ntime, nchan = argv[1], *map(int, argv[2:5])
        print(template(Path(out), nant, ntime, nchan))
    elif cmd == "design":
        name, tinfo, outdir = argv[1], argv[2], Path(argv[3])
        info = json.loads(Path(tinfo).read_text(encoding="utf-8"))
        data, flag, meta = DESIGNS[name](info)
        outdir.mkdir(parents=True, exist_ok=True)
        np.savez(outdir / f"{name}.npz", data=data, flag=flag)
        meta |= info
        (outdir / f"{name}.json").write_text(json.dumps(meta), encoding="utf-8")
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
