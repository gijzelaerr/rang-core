# SPDX-License-Identifier: GPL-3.0-or-later
"""F3: the second supervised RFI flagger (research/f3-flagger.md).

The data guards and loaders (LUNO calibrator groups, ESO137 target chunks,
F-SIM scans), the wrapper W3, the NumPy reference of the features
(section 3), the training injections and held-out morphologies (section 4),
the labels, the comparators Z2 and A's input/output, and the measures.
Inference in Rust is `rang._core.f3flag_logits` (`core/src/f3flag.rs`); the
network for training is `rang.f3net` (JAX, no rang imports).
"""

import json
import math
from pathlib import Path

import numpy as np

from . import core
from . import f2flag as ff

LUNO_BUCKET = (
    "https://ratt-public-data.s3.af-south-1.amazonaws.com/LBAND_LUNO_CALIBRATORS.zarr"
)
LUNO_TILES = tuple(range(8, 24))  # channels 1024-3071, 1070.0-1498.0 MHz
ESO_TILES = (5, 6, 7, 8)  # channels 640-1151, 989.7-1096.6 MHz
# Section 4. Exact names; nothing else is ever read.
FETCH_GROUPS = ("MAIN_3", "MAIN_4", "MAIN_5", "MAIN_6", "MAIN_7")
LUNO_ROLE = {
    # MAIN_3 (scan 4) is FLAG_ROW throughout: no rows (deviation 1, research/f3-flagger.md).
    "MAIN_4": "train",
    "MAIN_5": "train",
    "MAIN_6": "train",
    "MAIN_7": "validation",
    "MAIN_1": "test",
    "MAIN_2": "test",
}
LUNO_FORBIDDEN = ("MAIN_16", "MAIN_17", "MAIN_18", "MAIN_19")
ESO_ROLE = {
    2: "train",
    4: "train",
    6: "train",
    8: "train",
    10: "validation",
    0: "test",
    14: "test",
    16: "test",
}
ESO_FORBIDDEN = ("MAIN_4", "MAIN_5", "MAIN_6")

D_OUT = Path("D:/rang/outputs")
INPUTS = D_OUT / "f3-20261110-02-inputs"  # held-out LUNO copies and subtables
FETCH = D_OUT / "f3-20261110-01-fetch" / "objects"
ESO = Path("D:/rang/data/eso137-pilot/ESO137/ms1_target.zarr")
F2_TRAIN = D_OUT / "f2-20261106-02-sim-train"
F2_VAL = D_OUT / "f2-20261106-01-sim-v" / "f2sim-v"
F3_TEST = D_OUT / "f3-20261110-03-sim-test" / "f3sim-t"

NPLANES = 15
HIDDEN = 8
DILATIONS = (1, 2, 4, 8, 16)
RUNMED_HALF = 16
MIN_PAIRS = 16
MIN_AGG = 3
Z2_TAU = 10.0
W3_TASKS = ("flag_nans_zeros", "flag_autos", "combine_with_input_flags")


def check_luno_group(group):
    """Refuse anything but the protocol's LUNO groups (exact names)."""
    if group in LUNO_FORBIDDEN or group not in LUNO_ROLE:
        raise ValueError(f"LUNO {group} is not an F3 group")
    return group


def check_eso_chunk(group, chunk):
    if group != "MAIN_0" or group in ESO_FORBIDDEN or chunk not in ESO_ROLE:
        raise ValueError(f"ESO137 {group} chunk {chunk} is not an F3 set")
    return chunk


# -- the wrapper W3 -----------------------------------------------------------------


def w3_strategy(klass):
    """The class's YAML reduced to T's net static mask (section 2)."""
    steps = []
    for s in ff.strategy(ff.STRATEGIES[klass]):
        if (
            s["task"] in W3_TASKS
            or s["task"] == "apply_static_mask"
            and s["kwargs"].get("uvrange") == "0~550"
        ):
            steps.append(s)
    # flag_nans_zeros appears twice in the YAML; once is enough.
    out, seen = [], set()
    for s in steps:
        key = (s["task"], json.dumps(s.get("kwargs", {}), sort_keys=True))
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


# -- zarr decoding ------------------------------------------------------------------


def _zarr(root, name, key):
    meta = json.loads((root / name / ".zarray").read_text(encoding="utf-8"))
    raw = core.blosc_decode((root / name / key).read_bytes())
    full = np.frombuffer(raw, np.dtype(meta["dtype"])).reshape(meta["chunks"])
    index = [int(i) for i in key.split(".")]
    return full[
        tuple(
            slice(0, min(c, n - i * c))
            for c, n, i in zip(meta["chunks"], meta["shape"], index, strict=True)
        )
    ]


def _first(roots, rel):
    for r in roots:
        if (Path(r) / rel).exists():
            return Path(r)
    raise FileNotFoundError(rel)


def luno_subtables():
    """Antenna positions, channels, correlation types (identical for every group)."""
    root = INPUTS
    freq = _zarr(root, "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ", "0.0")[0]
    width = _zarr(root, "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH", "0.0")[0]
    ch = slice(LUNO_TILES[0] * 128, (LUNO_TILES[-1] + 1) * 128)
    return {
        "antenna_position": _zarr(root, "ANTENNA/ANTENNA_0/POSITION", "0.0").astype(
            np.float64
        ),
        "chan_freq": np.ascontiguousarray(freq[ch], np.float64),
        "chan_width": np.ascontiguousarray(width[ch], np.float64),
        "corr_type": _zarr(root, "POLARIZATION/POLARIZATION_0/CORR_TYPE", "0.0")[
            0
        ].astype(np.int32),
    }


def load_luno(group, weights=False):
    """One LUNO calibrator group, cross rows, channels 1024-3071, as a scan dict."""
    check_luno_group(group)
    roots = (FETCH, INPUTS) if LUNO_ROLE[group] != "test" else (INPUTS,)
    g = f"MAIN/{group}"
    r = _first(roots, f"{g}/TIME/0")
    a1 = _zarr(r, f"{g}/ANTENNA1", "0").astype(np.int32)
    a2 = _zarr(r, f"{g}/ANTENNA2", "0").astype(np.int32)
    frow = _zarr(r, f"{g}/FLAG_ROW", "0").astype(bool)
    keep = (a1 != a2) & ~frow  # F2's rows: FLAG_ROW rows dropped

    def tiles(name):
        rr = _first(roots, f"{g}/{name}/0.{LUNO_TILES[0]}.0")
        return np.concatenate(
            [_zarr(rr, f"{g}/{name}", f"0.{t}.0")[keep] for t in LUNO_TILES], axis=1
        )

    data = np.ascontiguousarray(tiles("DATA"), np.complex64)
    flag = tiles("FLAG").astype(bool)
    scan = dict(luno_subtables())
    scan.update(
        data=data,
        input_flags=np.ascontiguousarray(flag),
        antenna1=np.ascontiguousarray(a1[keep]),
        antenna2=np.ascontiguousarray(a2[keep]),
        times=np.ascontiguousarray(_zarr(r, f"{g}/TIME", "0")[keep], np.float64),
        field=f"LUNO {group}",
        klass="calibrator",
    )
    if weights:
        scan["weights"] = np.ascontiguousarray(tiles("WEIGHT_SPECTRUM"), np.float32)
    scan["nant"] = len(scan["antenna_position"])
    return scan


def load_eso(chunk):
    """ESO137 target MAIN_0, one row chunk, the four channel tiles on disk."""
    check_eso_chunk("MAIN_0", chunk)
    g = "MAIN/MAIN_0"
    a1 = _zarr(ESO, f"{g}/ANTENNA1", f"{chunk}").astype(np.int32)
    a2 = _zarr(ESO, f"{g}/ANTENNA2", f"{chunk}").astype(np.int32)
    keep = a1 != a2

    def tiles(name):
        return np.concatenate(
            [_zarr(ESO, f"{g}/{name}", f"{chunk}.{t}.0")[keep] for t in ESO_TILES],
            axis=1,
        )

    freq = _zarr(ESO, "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ", "0.0")[0]
    width = _zarr(ESO, "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH", "0.0")[0]
    ch = np.concatenate([np.arange(t * 128, (t + 1) * 128) for t in ESO_TILES])
    frow = _zarr(ESO, f"{g}/FLAG_ROW", f"{chunk}").astype(bool)[keep]
    scan = {
        "data": np.ascontiguousarray(tiles("DATA"), np.complex64),
        "input_flags": np.ascontiguousarray(
            tiles("FLAG").astype(bool) | frow[:, None, None]
        ),
        "antenna1": np.ascontiguousarray(a1[keep]),
        "antenna2": np.ascontiguousarray(a2[keep]),
        "times": np.ascontiguousarray(
            _zarr(ESO, f"{g}/TIME", f"{chunk}")[keep], np.float64
        ),
        "antenna_position": _zarr(ESO, "ANTENNA/ANTENNA_0/POSITION", "0.0").astype(
            np.float64
        ),
        "chan_freq": np.ascontiguousarray(freq[ch], np.float64),
        "chan_width": np.ascontiguousarray(width[ch], np.float64),
        "corr_type": _zarr(ESO, "POLARIZATION/POLARIZATION_0/CORR_TYPE", "0.0")[
            0
        ].astype(np.int32),
        "field": f"ESO137 MAIN_0 chunk {chunk}",
        "klass": "target",
    }
    scan["nant"] = len(scan["antenna_position"])
    return scan


def load_fsim(s):
    """One F-SIM scan (`f2flag_sim.Scan`) with its truth amplitude and morphology."""
    m = s.meta
    sigma = m["sigma"]
    rfi = np.array(s.array("rfi"))
    scan = {
        "data": np.array(s.array("data")),
        "input_flags": np.zeros(rfi.shape, bool),
        "antenna1": np.array(m["antenna1"], np.int32),
        "antenna2": np.array(m["antenna2"], np.int32),
        "times": np.array(m["times"]),
        "antenna_position": np.array(m["antenna_position"]),
        "chan_freq": np.array(m["chan_freq"]),
        "chan_width": np.array(m["chan_width"]),
        "corr_type": np.array(m["corr_type"], np.int32),
        "nant": m["nant"],
        "sigma": sigma,
        "amp": (np.abs(rfi).max(-1) / sigma).astype(np.float32),
        "morph": np.array(s.array("morph")),
        "klass": m["class"],
        "field": str(s.path),
    }
    return scan


# -- rows, planes and the Rust kernel -----------------------------------------------


def index(scan):
    """Row -> (baseline, time) indices in `flag_rows`'s baseline order, cached."""
    if "_index" not in scan:
        ubl, bl = ff.baseline_index(scan["antenna1"], scan["antenna2"])
        tgrid, t = np.unique(scan["times"], return_inverse=True)
        scan["_index"] = {
            "ubl": ubl,
            "bl": bl.astype(np.uint32),
            "t": t.astype(np.uint32),
            "nt": len(tgrid),
            "ant1": np.ascontiguousarray(ubl[:, 0], np.uint32),
            "ant2": np.ascontiguousarray(ubl[:, 1], np.uint32),
        }
    return scan["_index"]


def _args(scan, flagged, data=None):
    ix = index(scan)
    data = np.require(scan["data"] if data is None else data, np.complex64, ["C", "A"])
    nant = max(int(scan["nant"]), int(ix["ubl"].max()) + 1)
    return (
        data.shape[1],
        len(ix["ubl"]),
        ix["nt"],
        nant,
        data.view(np.float32),
        np.require(flagged, np.uint8, ["C", "A"]),
        ix["bl"],
        ix["t"],
        ix["ant1"],
        ix["ant2"],
    )


def rust_features(scan, flagged, select, data=None):
    """(nsel, nt, nc, 15) float32 planes of the baselines `select` (indices
    into `index(scan)["ubl"]`)."""
    args = _args(scan, flagged, data)
    select = np.ascontiguousarray(select, np.uint32)
    out = np.empty((len(select), args[2], args[0], NPLANES), np.float32)
    code = core.extension().f3flag_features(*args, select, out)
    if code:
        raise RuntimeError(f"f3flag_features failed with code {code}")
    return out


def rust_logits(scan, flagged, weights, data=None):
    """(row, chan) float32 logits."""
    args = _args(scan, flagged, data)
    out = np.empty((len(scan["times"]), args[0]), np.float32)
    code = core.extension().f3flag_logits(
        *args, np.require(weights, np.float32, ["C", "A"]), out
    )
    if code:
        raise RuntimeError(f"f3flag_logits failed with code {code}")
    return out


# -- the NumPy reference of the features (section 3) --------------------------------


def _nanmedian(x, axis):
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(x, axis=axis)


def features_numpy(scan, flagged, select, data=None):
    """Section 3 in float64 (the u planes rounded to float32 before the
    medians, as the kernel stores them). Slow; for parity on small scans."""
    ix = index(scan)
    data = scan["data"] if data is None else data
    nbl, nt, nc = len(ix["ubl"]), ix["nt"], data.shape[1]
    nant = max(int(scan["nant"]), int(ix["ubl"].max()) + 1)
    vis = np.zeros((nbl, nt, nc, 4), np.complex128)
    fl = np.ones((nbl, nt, nc), bool)
    vis[ix["bl"], ix["t"]] = data
    fl[ix["bl"], ix["t"]] = flagged | ~np.isfinite(data.view(np.float32)).reshape(
        data.shape[:2] + (8,)
    ).all(-1)
    rt = np.full((nbl, nt, nc, 4), np.nan)
    rf = np.full((nbl, nt, nc, 4), np.nan)
    alive = np.zeros(nbl, bool)
    with np.errstate(invalid="ignore", divide="ignore"):
        for b in range(nbl):
            v, f = vis[b], fl[b]
            sig = np.full(4, np.nan)
            both = ~f[:, 1:] & ~f[:, :-1]
            for c in range(4):
                d = (v[:, 1:, c] - v[:, :-1, c])[both]
                if len(d) < MIN_PAIRS:
                    continue
                x = np.concatenate([d.real, d.imag])
                s = 1.4826 * np.median(np.abs(x - np.median(x))) / math.sqrt(2)
                if np.isfinite(s) and s > 0:
                    sig[c] = s
            if not np.isfinite(sig).any():
                continue
            alive[b] = True
            sig[~np.isfinite(sig)] = np.median(sig[np.isfinite(sig)])
            a = np.abs(v) / sig
            a[f] = np.nan
            p = _nanmedian(a, 0)  # (nc, 4)
            pad = np.pad(
                p, ((RUNMED_HALF, RUNMED_HALF), (0, 0)), constant_values=np.nan
            )
            win = np.lib.stride_tricks.sliding_window_view(
                pad, 2 * RUNMED_HALF + 1, axis=0
            )
            s_ = _nanmedian(win, -1)  # (nc, 4)
            ratio = a / np.where(s_ > 0, s_, np.nan)[None]
            g = _nanmedian(ratio, 1)  # (nt, 4)
            rt[b] = a - p[None]
            rf[b] = a - g[:, None, :] * s_[None]
    rt[fl] = np.nan
    rf[fl] = np.nan
    u = np.stack(
        [
            np.where(
                np.isfinite(r).any(-1),
                np.nanmax(np.where(np.isfinite(r), r, -np.inf), -1),
                np.nan,
            )
            for r in (rt, rf)
        ]
    ).astype(np.float32)  # (2, nbl, nt, nc)
    u[:, ~alive] = np.nan
    agg = np.full((2, nant + 1, nt, nc), np.nan)
    for x in range(2):
        for k in range(nant):
            sel = (ix["ant1"] == k) | (ix["ant2"] == k)
            if not sel.any():
                continue
            vals = u[x, sel].astype(np.float64)
            n = np.isfinite(vals).sum(0)
            m = _nanmedian(vals, 0)
            agg[x, k] = np.where(n >= MIN_AGG, m, np.nan)
        vals = u[x].astype(np.float64)
        n = np.isfinite(vals).sum(0)
        agg[x, nant] = np.where(n >= MIN_AGG, _nanmedian(vals, 0), np.nan)
    agg = agg.astype(np.float32).astype(np.float64)

    def ash(z):
        return np.where(np.isfinite(z), np.arcsinh(np.where(np.isfinite(z), z, 0)), 0.0)

    out = np.zeros((len(select), nt, nc, NPLANES), np.float32)
    for i, b in enumerate(select):
        o = np.zeros((nt, nc, NPLANES))
        if alive[b]:
            o[..., 0:4] = ash(rt[b])
            o[..., 4:8] = ash(rf[b])
            p_, q_ = ix["ant1"][b], ix["ant2"][b]
            for x in range(2):
                mp, mq = agg[x, p_], agg[x, q_]
                mx = np.where(
                    np.isfinite(mp) & np.isfinite(mq),
                    np.maximum(mp, mq),
                    np.where(np.isfinite(mp), mp, mq),
                )
                mn = np.where(
                    np.isfinite(mp) & np.isfinite(mq),
                    np.minimum(mp, mq),
                    np.where(np.isfinite(mp), mp, mq),
                )
                o[..., 8 + 3 * x] = ash(mx)
                o[..., 9 + 3 * x] = ash(mn)
                o[..., 10 + 3 * x] = ash(agg[x, nant])
        o[fl[b]] = 0.0
        o[..., NPLANES - 1] = fl[b]
        out[i] = o
    return out


# -- noise, W3 and T ----------------------------------------------------------------


def baseline_sigma(scan, eligible):
    """Per row: the real-part noise of its baseline (F2's `per_baseline_noise`:
    scaled MAD of parallel-hand channel differences over eligible pairs)."""
    ix = index(scan)
    data = scan["data"]
    sigma = np.zeros(len(data))
    order = np.argsort(ix["bl"], kind="stable")
    bounds = np.searchsorted(ix["bl"][order], np.arange(len(ix["ubl"]) + 1))
    for b in range(len(ix["ubl"])):
        rows = order[bounds[b] : bounds[b + 1]]
        both = eligible[rows, 1:] & eligible[rows, :-1]
        if both.sum() < MIN_PAIRS:
            continue
        d = (data[rows, 1:][..., [0, 3]] - data[rows, :-1][..., [0, 3]])[both]
        v = np.concatenate([d.real.ravel(), d.imag.ravel()]).astype(np.float64)
        sigma[rows] = 1.4826 * np.median(np.abs(v - np.median(v))) / math.sqrt(2)
    return sigma


def run_steps(scan, steps, data=None):
    sc = dict(scan, data=scan["data"] if data is None else data)
    return ff.run_strategy(sc, steps, scan["input_flags"])


def w3_flags(scan, data=None):
    """(row, chan) flags of W3 (section 2)."""
    return run_steps(scan, w3_strategy(scan["klass"]), data)[0]


def t_flags(scan, data=None):
    return run_steps(scan, ff.strategy(ff.STRATEGIES[scan["klass"]]), data)[0]


def z2_flags(scan, w3, data=None):
    """Z2: max over the eight residual planes before asinh above 10 (section 2);
    asinh is monotone, so on the stored planes the bar is asinh(10)."""
    ix = index(scan)
    nbl = len(ix["ubl"])
    out = np.zeros(w3.shape, bool)
    bar = np.arcsinh(Z2_TAU)
    for s in range(0, nbl, 128):
        sel = np.arange(s, min(s + 128, nbl))
        x = rust_features(scan, w3, sel, data)
        hit = x[..., :8].max(-1) > bar  # (nsel, nt, nc)
        rows = np.flatnonzero((ix["bl"] >= s) & (ix["bl"] < s + len(sel)))
        out[rows] = hit[ix["bl"][rows] - s, ix["t"][rows]]
    return w3 | out


def n3_flags(scan, w3, weights, tau, data=None):
    logit = rust_logits(scan, w3, weights, data)
    return w3 | (logit > tau), logit


# -- injections (section 4) ---------------------------------------------------------

TRAIN_MORPHOLOGIES = ("T1", "T2", "T3", "T4", "T5")
HELD_OUT = ("H1", "H2")
CODES = TRAIN_MORPHOLOGIES + HELD_OUT


def _coupling(rng):
    w = np.ones(4, np.complex128)
    w[1:] = rng.uniform(0, 1, 3) * np.exp(1j * rng.uniform(-np.pi, np.pi, 3))
    w = rng.permutation(w)
    return w / np.abs(w).max()


def _baseline_length(scan):
    ix = index(scan)
    xyz = np.asarray(scan["antenna_position"])
    return np.linalg.norm(xyz[ix["ant1"]] - xyz[ix["ant2"]], axis=1)


class Injector:
    """Adds events to a copy of DATA on eligible cells; tracks the cell
    strength A = max_c |inj_c| / sigma_b and each cell's morphology code
    (1 + index in CODES)."""

    def __init__(self, scan, eligible, sigma, rng, fixed=None):
        self.scan, self.eligible, self.sigma, self.rng = scan, eligible, sigma, rng
        self.fixed = fixed  # test mode: fixed strength, constant, coherent
        self.ix = index(scan)
        self.nbl = len(self.ix["ubl"])
        self.data = scan["data"].copy()
        self.amp = np.zeros(eligible.shape, np.float32)
        self.morph = np.zeros(eligible.shape, np.int8)
        self.blen = _baseline_length(scan)
        self.nt, self.nc = self.ix["nt"], eligible.shape[1]
        self.events = []

    def add(self, code, bsel, tsel, chans, decay=False):
        """bsel: baseline mask; tsel: (nt,) time mask with channel indices
        `chans`, or an (nt, nc) cell mask."""
        rng, ix = self.rng, self.ix
        rows = np.flatnonzero(bsel[ix["bl"]])
        if not len(rows):
            return
        if tsel.ndim == 1:
            cmask = np.zeros(self.nc, bool)
            cmask[chans] = True
            cells = tsel[ix["t"][rows]][:, None] & cmask[None]
        else:
            cells = tsel[ix["t"][rows]]
        cells &= self.eligible[rows] & (self.sigma[rows] > 0)[:, None]
        r_, c_ = np.nonzero(cells)
        if not len(r_):
            return
        rows = rows[r_]
        b = ix["bl"][rows]
        t = ix["t"][rows].astype(np.float64)
        w = _coupling(rng)
        if self.fixed is not None:
            alpha = np.full(len(rows), float(self.fixed))
            phase = rng.uniform(-np.pi, np.pi) + rng.normal(0, 0.15, len(rows))
            mod = 1.0
        else:
            a0 = math.exp(rng.uniform(math.log(3), math.log(300)))
            alpha = np.full(len(rows), a0)
            if decay and rng.random() < 0.5:
                scale = math.exp(rng.uniform(math.log(100), math.log(5000)))
                alpha = alpha * np.exp(-self.blen[b] / scale)
            if code == "T3":
                alpha = alpha * rng.uniform(0.5, 1.0, self.nbl)[b]
            phi0 = rng.uniform(-np.pi, np.pi, self.nbl)[b]
            nu = rng.uniform(-0.5, 0.5, self.nbl)[b] if rng.random() < 0.5 else 0.0
            phase = phi0 + 2 * np.pi * nu * t + rng.normal(0, 0.15, len(rows))
            if rng.random() < 0.5:
                mod = 1.0
            else:
                period = rng.uniform(4, 32)
                mod = 0.75 + 0.25 * np.sin(2 * np.pi * t / period + rng.uniform(0, 6.3))
        z = (alpha * mod * self.sigma[rows] * np.exp(1j * phase))[:, None] * w[None]
        self.data[rows, c_] += z.astype(np.complex64)
        a = (
            np.abs(self.data[rows, c_] - self.scan["data"][rows, c_]).max(-1)
            / self.sigma[rows]
        ).astype(np.float32)
        new = a > self.amp[rows, c_]
        self.amp[rows, c_] = np.maximum(self.amp[rows, c_], a)
        self.morph[rows[new], c_[new]] = 1 + CODES.index(code)
        self.events.append(
            {"code": code, "cells": len(rows), "alpha": float(np.median(alpha))}
        )

    def _band(self, lo, hi):
        w = int(self.rng.integers(lo, hi + 1))
        c0 = int(self.rng.integers(0, self.nc - w + 1))
        return np.arange(c0, c0 + w)

    def _run(self, lo, hi):
        n = int(min(self.rng.integers(lo, hi + 1), self.nt))
        t0 = int(self.rng.integers(0, self.nt - n + 1))
        m = np.zeros(self.nt, bool)
        m[t0 : t0 + n] = True
        return m

    def _all_times(self):
        return np.ones(self.nt, bool)

    def _live_antennas(self):
        rows = self.eligible.any(1)
        return np.unique(
            np.r_[self.scan["antenna1"][rows], self.scan["antenna2"][rows]]
        )

    def training(self):
        rng = self.rng
        allb = np.ones(self.nbl, bool)
        for _ in range(rng.integers(1, 5)):
            self.add("T1", allb, self._all_times(), self._band(1, 4), decay=True)
        for _ in range(rng.integers(1, 5)):
            self.add("T2", allb, self._run(1, 8), self._band(1, 8), decay=True)
        ants = self._live_antennas()
        for _ in range(rng.integers(1, 4)):
            k = int(rng.choice(ants))
            bsel = (self.ix["ant1"] == k) | (self.ix["ant2"] == k)
            tm = self._all_times() if rng.random() < 0.5 else self._run(2, 16)
            self.add("T3", bsel, tm, self._band(1, 8))
        live = np.unique(self.ix["bl"][self.eligible.any(1)])
        for _ in range(rng.integers(2, 7)):
            bsel = np.zeros(self.nbl, bool)
            bsel[int(rng.choice(live))] = True
            tm = self._all_times() if rng.random() < 0.5 else self._run(1, 16)
            self.add("T4", bsel, tm, self._band(1, 8))
        for _ in range(rng.integers(0, 3)):
            self.add(
                "T5",
                allb,
                self._run(1, 2),
                self._band(64, min(1024, self.nc)),
                decay=True,
            )

    def held_out(self, code):
        rng = self.rng
        allb = np.ones(self.nbl, bool)
        if code == "H1":
            rate = int(rng.integers(1, 4)) * (1 if rng.random() < 0.5 else -1)
            span = abs(rate) * (self.nt - 1) + 4
            c0 = int(rng.integers(0, max(self.nc - span, 1)))
            if rate < 0:
                c0 += span - 4
            cells = np.zeros((self.nt, self.nc), bool)
            for t in range(self.nt):
                lo = c0 + rate * t
                cells[t, max(lo, 0) : max(lo + 4, 0)] = True
            self.add("H1", allb, cells, None)
        elif code == "H2":
            xyz = np.asarray(self.scan["antenna_position"])
            ants = self._live_antennas()
            k = int(rng.choice(ants))
            n = int(rng.integers(3, 7))
            dist = np.linalg.norm(xyz[ants] - xyz[k], axis=1)
            cluster = ants[np.argsort(dist)[:n]]
            bsel = np.isin(self.ix["ant1"], cluster) & np.isin(self.ix["ant2"], cluster)
            self.add("H2", bsel, self._all_times(), self._band(1, 8))
        else:
            raise ValueError(code)


# -- labels (section 4) -------------------------------------------------------------


def labels_real(amp, eligible, t_flag, a_flag, strong=None):
    """int8 (row, chan): 1 positive, 0 negative, -1 ignored. With `strong`
    (Amendment 1: max(u) >= 3 on the uninjected DATA), consensus cells that
    are not strong are ignored rather than positive."""
    lab = np.full(amp.shape, -1, np.int8)
    injected = amp > 0
    lab[eligible & ~injected & ~t_flag & ~a_flag] = 0
    cons = t_flag & a_flag & eligible & ~injected
    if strong is not None:
        cons &= strong
    lab[cons] = 1
    lab[(amp >= 3) & eligible] = 1
    return lab


def u_rows(scan, w3, block=128):
    """(row, chan) float32 max(u^t, u^f) on DATA (section 3, before asinh;
    0 on flagged cells)."""
    ix = index(scan)
    nbl = len(ix["ubl"])
    out = np.zeros(w3.shape, np.float32)
    for s in range(0, nbl, block):
        sel = np.arange(s, min(s + block, nbl))
        x = rust_features(scan, w3, sel)
        u = np.sinh(x[..., :8].max(-1))
        rows = np.flatnonzero((ix["bl"] >= s) & (ix["bl"] < s + len(sel)))
        out[rows] = u[ix["bl"][rows] - s, ix["t"][rows]]
    return out


def labels_sim(truth_amp, inj_amp, eligible):
    a = np.maximum(truth_amp, inj_amp)
    lab = np.full(a.shape, -1, np.int8)
    lab[(a == 0) & eligible] = 0
    lab[(a >= 3) & eligible] = 1
    return lab


def augment_input_flags(rng, flags, scan):
    """F2's synthetic input flags (section 4): bands of 8-256 channels and
    blocks of 1-8 dumps up to an occupancy uniform in 0-0.6."""
    ix = index(scan)
    nt, nc = ix["nt"], flags.shape[1]
    target = rng.uniform(0, 0.6)
    plane = np.zeros((nt, nc), bool)
    while plane.mean() < target:
        if rng.random() < 0.7:
            w = int(rng.integers(8, 257))
            c0 = int(rng.integers(0, max(nc - w, 1)))
            plane[:, c0 : c0 + w] = True
        else:
            n = int(rng.integers(1, 9))
            t0 = int(rng.integers(0, max(nt - n, 1)))
            plane[t0 : t0 + n] = True
    return flags | plane[ix["t"]]


# -- arm A: AOFlagger in WSL Docker (section 2) -------------------------------------

AO_IMAGE = "rang-aflag-aoflagger:3.5.0"


def _wsl(path):
    p = Path(path).resolve()
    drive = p.drive.rstrip(":").lower()
    return f"/mnt/{drive}" + p.as_posix()[2:]


def a_flags(scan, w3, workdir, data=None):
    """(row, chan) flags of A: W3 OR AOFlagger generic-default with W3 as the
    input mask. `workdir` (on D:) receives the planes and the container's
    output; returns (flags, record)."""
    import subprocess

    ix = index(scan)
    data = scan["data"] if data is None else data
    nbl, nt, nc = len(ix["ubl"]), ix["nt"], data.shape[1]
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    vis = np.lib.format.open_memmap(
        work / "vis.npy", "w+", np.complex64, (nbl, nt, nc, 4)
    )
    vis[:] = 0
    vis[ix["bl"], ix["t"]] = data
    vis.flush()
    del vis
    mask = np.ones((nbl, nt, nc), bool)
    mask[ix["bl"], ix["t"]] = w3
    np.save(work / "mask.npy", mask)
    tools = Path(__file__).resolve().parents[2] / "tools/oracles/aoflagger"
    cmd = [
        "wsl.exe",
        "-d",
        "Ubuntu",
        "--",
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "-v",
        f"{_wsl(work)}:/io",
        "-v",
        f"{_wsl(tools)}:/tools:ro",
        AO_IMAGE,
        "python3",
        "/tools/f3_aoflag.py",
        "/io",
    ]
    import time as _time

    t0 = _time.perf_counter()
    subprocess.run(cmd, check=True, capture_output=True)
    wall = _time.perf_counter() - t0
    out = np.load(work / "flags.npy")
    rec = json.loads((work / "aoflag.json").read_text(encoding="utf-8"))
    rec["docker_wall"] = wall
    flags = out[ix["bl"], ix["t"]] | w3
    for name in ("vis.npy", "mask.npy", "flags.npy"):
        (work / name).unlink()
    return flags, rec


# -- held-out measures (section 6) --------------------------------------------------

R1_MORPHOLOGIES = ("narrowband", "time-burst", "antenna-local", "single-baseline")
R1_SEEDS = (19, 20, 21)
R2_SEEDS = (31, 32, 33)
STOPZ2_SEEDS = (41, 42, 43)
STRENGTH = 10.0


def f2_inject(scan, eligible, morphology, seed):
    """F2's R1 injection (`examples/f2_real.py` `inject`, F1's `inject_mask`)
    on eligible cells: (rows, channels, unit phasors). Weights are ones: F2's
    phasor is `delta * sqrt(w)`, independent of the weights."""
    from .core_injection_model import make_injection

    state = {
        "data": scan["data"],
        "train": eligible,
        "validation": np.zeros_like(eligible),
        "test": np.zeros_like(eligible),
        "original_flags": scan["input_flags"],
        "original_rows": scan["input_flags"].all(axis=(1, 2)),
        "antenna1": scan["antenna1"],
        "antenna2": scan["antenna2"],
        "times": scan["times"],
        "weights": np.ones(scan["data"].shape, np.float32),
        "window": np.ones(eligible.shape[1], bool),
    }
    train = eligible
    if morphology in ("narrowband", "time-burst", "antenna-local"):
        mask, delta, _ = make_injection(state, morphology, 1.0, seed)
        rows, channels = np.nonzero(mask)
        return rows, channels, np.asarray(delta[rows, channels, 0], np.complex128)
    rng = np.random.default_rng(seed)
    p, q = scan["antenna1"], scan["antenna2"]
    key = p.astype(np.int64) * (p.max() + q.max() + 2) + q
    baselines, inverse = np.unique(key, return_inverse=True)
    occupancy = np.bincount(inverse, train.mean(axis=1)) / np.bincount(inverse)
    chosen = rng.choice(baselines[occupancy >= np.median(occupancy)])
    support = key == chosen
    per_channel = train[support].mean(axis=0)
    width = np.convolve(per_channel, np.ones(8) / 8, mode="valid")
    first = int(rng.choice(np.flatnonzero(width >= 0.5)))
    mask = np.zeros(train.shape, bool)
    mask[np.ix_(support, np.arange(first, first + 8))] = True
    mask &= train
    rows, channels = np.nonzero(mask)
    phase = rng.uniform(-np.pi, np.pi) + rng.normal(0, 0.15, len(rows))
    return rows, channels, np.exp(1j * phase)


def r1_case(scan, eligible, sigma, morphology, seed):
    """Injected DATA and the injected (rows, channels) of one R1 case."""
    rows, chans, phasor = f2_inject(scan, eligible, morphology, seed)
    data = scan["data"].copy()
    data[rows, chans, :] += (STRENGTH * sigma[rows] * phasor)[:, None].astype(
        np.complex64
    )
    return data, rows, chans


def r2_case(scan, eligible, sigma, code, seed):
    inj = Injector(scan, eligible, sigma, np.random.default_rng(seed), fixed=STRENGTH)
    inj.held_out(code)
    rows, chans = np.nonzero(inj.amp > 0)
    return inj.data, rows, chans


def jaccard(a, b):
    u = int((a | b).sum())
    return int((a & b).sum()) / u if u else None


# -- training and validation realisations (sections 4 and 5) ------------------------


def realise(scan, w3, sigma, seed, augment, t_flag=None, a_flag=None, strong=None):
    """One realisation: (injected DATA, flags before the network, labels,
    Injector, rng). Real scans pass T's and A's flags on the uninjected DATA;
    F-SIM scans carry `amp` (truth)."""
    rng = np.random.default_rng(seed)
    inj = Injector(scan, ~w3, sigma, rng)
    inj.training()
    flags = augment_input_flags(rng, w3, scan) if augment else w3
    elig = ~flags
    if t_flag is not None:
        lab = labels_real(inj.amp, elig, t_flag, a_flag, strong)
    else:
        lab = labels_sim(scan["amp"], inj.amp, elig)
    return inj.data, flags, lab, inj, rng
