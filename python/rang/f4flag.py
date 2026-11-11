"""F4: the third supervised RFI flagger (research/f4-flagger.md).

F3's planes plus eight scan-scale spectral planes (section 3), F4's data
roles and guards, the T6 injection and the H3 held-out morphology, the
labels L-A1s (calibrators) and L-INJ (targets), and the comparators Z4 and
ZE. Inference in Rust is `rang._core.f4flag_logits` (`core/src/f4flag.rs`);
training uses `rang.f3net` with `nplanes=23`. F3's code (`rang.f3flag`) is
reused, not changed.
"""

import math

import numpy as np

from . import core
from . import f3flag as f3

NPLANES = 23
SPEC0 = 14
MIN_SPEC = 16
FAMILIES = ((0, 3), (1, 2))  # parallel, cross
ZE_TAU = 5.0

# Section 4. Exact names; nothing else is ever read.
LUNO_ROLE = {
    "MAIN_1": "train",
    "MAIN_2": "train",
    "MAIN_4": "train",
    "MAIN_5": "train",
    "MAIN_6": "train",
    "MAIN_7": "validation",
    "MAIN_0": "test",
    "MAIN_12": "test",
    "MAIN_14": "test",
}
LUNO_FORBIDDEN = tuple(f"MAIN_{k}" for k in (3, 8, 9, 10, 11, 13, 15, 16, 17, 18, 19))
FETCH_GROUPS = ("MAIN_0", "MAIN_12", "MAIN_14")
ESO_ROLE = {
    0: "train",
    2: "train",
    4: "train",
    6: "train",
    8: "train",
    14: "train",
    16: "train",
    10: "validation",
    11: "test",
    12: "test",
    13: "test",
}
ESO_RESERVED = (1, 3, 5, 7, 9, 15, 17)

FETCH = f3.D_OUT / "f4-20261111-01-fetch" / "objects"
F4_TEST = f3.D_OUT / "f4-20261111-02-sim-test" / "f4sim-t"


def check_luno_group(group, heldout=False):
    """Refuse anything but F4's LUNO groups; test groups only with `heldout`
    (Stage 5)."""
    if group in LUNO_FORBIDDEN or group not in LUNO_ROLE:
        raise ValueError(f"LUNO {group} is not an F4 group")
    if LUNO_ROLE[group] == "test" and not heldout:
        raise ValueError(f"LUNO {group} is held out until Stage 5")
    return group


def check_eso_chunk(chunk, heldout=False):
    if chunk in ESO_RESERVED or chunk not in ESO_ROLE:
        raise ValueError(f"ESO137 chunk {chunk} is not an F4 set")
    if ESO_ROLE[chunk] == "test" and not heldout:
        raise ValueError(f"ESO137 chunk {chunk} is held out until Stage 5")
    return chunk


def load_luno(group, heldout=False, weights=False):
    check_luno_group(group, heldout)
    if group in FETCH_GROUPS:
        roots = (FETCH, f3.INPUTS)
    else:
        roots = (f3.FETCH, f3.INPUTS)
    return f3.read_luno(group, roots, weights)


def load_eso(chunk, heldout=False):
    check_eso_chunk(chunk, heldout)
    return f3.read_eso(chunk)


def load(spec, heldout=False):
    """`luno:MAIN_k` or `eso:k`."""
    kind, _, name = spec.partition(":")
    if kind == "luno":
        return load_luno(name, heldout)
    if kind == "eso":
        return load_eso(int(name), heldout)
    raise ValueError(spec)


def real_sets(klass, role):
    if klass == "calibrator":
        return [f"luno:{g}" for g, r in LUNO_ROLE.items() if r == role]
    return [f"eso:{c}" for c, r in sorted(ESO_ROLE.items()) if r == role]


# -- the Rust kernel ----------------------------------------------------------------


def rust_features(scan, flagged, select, data=None):
    """(nsel, nt, nc, 23) float32 planes of the baselines `select`."""
    args = f3._args(scan, flagged, data)
    select = np.ascontiguousarray(select, np.uint32)
    out = np.empty((len(select), args[2], args[0], NPLANES), np.float32)
    code = core.extension().f4flag_features(*args, select, out)
    if code:
        raise RuntimeError(f"f4flag_features failed with code {code}")
    return out


def rust_logits(scan, flagged, weights, data=None):
    args = f3._args(scan, flagged, data)
    out = np.empty((len(scan["times"]), args[0]), np.float32)
    code = core.extension().f4flag_logits(
        *args, np.require(weights, np.float32, ["C", "A"]), out
    )
    if code:
        raise RuntimeError(f"f4flag_logits failed with code {code}")
    return out


# -- the NumPy reference (section 3) ------------------------------------------------


def _percentile(x, q, axis):
    """np.nanpercentile with a minimum of MIN_SPEC finite values."""
    import warnings

    n = np.isfinite(x).sum(axis)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        v = np.nanpercentile(x, q, axis=axis)
    return np.where(n >= MIN_SPEC, v, np.nan)


def _nanmax(x, axis):
    fin = np.isfinite(x)
    m = np.max(np.where(fin, x, -np.inf), axis=axis)
    return np.where(fin.any(axis), m, np.nan)


def spectra_numpy(scan, flagged, data=None):
    """Section 3, steps 1-6, float64: e (nbl, 2, nc), E (2, nant, nc), X (2, nc),
    alive (nbl,)."""
    ix = f3.index(scan)
    data = scan["data"] if data is None else data
    nbl, nt, nc = len(ix["ubl"]), ix["nt"], data.shape[1]
    nant = max(int(scan["nant"]), int(ix["ubl"].max()) + 1)
    vis = np.zeros((nbl, nt, nc, 4), np.complex128)
    fl = np.ones((nbl, nt, nc), bool)
    vis[ix["bl"], ix["t"]] = data
    fl[ix["bl"], ix["t"]] = flagged | ~np.isfinite(data.view(np.float32)).reshape(
        data.shape[:2] + (8,)
    ).all(-1)
    p = np.full((nbl, nc, 4), np.nan)
    alive = np.zeros(nbl, bool)
    with np.errstate(invalid="ignore", divide="ignore"):
        for b in range(nbl):
            v, f = vis[b], fl[b]
            sig = np.full(4, np.nan)
            both = ~f[:, 1:] & ~f[:, :-1]
            for c in range(4):
                d = (v[:, 1:, c] - v[:, :-1, c])[both]
                if len(d) < f3.MIN_PAIRS:
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
            p[b] = f3._nanmedian(a, 0)
        n = np.isfinite(p).sum(0)
        big_b = np.where(n >= f3.MIN_AGG, f3._nanmedian(p, 0), np.nan)  # (nc, 4)
        w = p - big_b[None]
        off = _percentile(w, 50, 1)  # (nbl, 4); Amendment 2: median
        dev = np.abs(w - off[:, None, :])
        e = np.stack([_nanmax(dev[..., list(fam)], -1) for fam in FAMILIES], 1)
        big_e = np.full((2, nant, nc), np.nan)
        for k in range(nant):
            sel = (ix["ant1"] == k) | (ix["ant2"] == k)
            if not sel.any():
                continue
            vals = e[sel]  # (n, 2, nc)
            cnt = np.isfinite(vals).sum(0)
            big_e[:, k] = np.where(cnt >= f3.MIN_AGG, f3._nanmedian(vals, 0), np.nan)
        base = _percentile(big_b, 25, 0)  # (4,)
        exc = big_b - base[None]
        x = np.stack([_nanmax(exc[:, list(fam)], -1) for fam in FAMILIES])
    return e, big_e, x, alive, fl


def features_numpy(scan, flagged, select, data=None):
    """F3's reference planes plus section 3's spectral planes (slow; parity)."""
    ix = f3.index(scan)
    old = f3.features_numpy(scan, flagged, select, data)
    e, big_e, x, alive, fl = spectra_numpy(scan, flagged, data)

    def ash(z):
        return np.where(np.isfinite(z), np.arcsinh(np.where(np.isfinite(z), z, 0)), 0.0)

    nt, nc = old.shape[1], old.shape[2]
    out = np.zeros(old.shape[:3] + (NPLANES,), np.float32)
    out[..., :14] = old[..., :14]
    out[..., NPLANES - 1] = old[..., 14]
    for i, b in enumerate(select):
        if not alive[b]:
            continue
        p_, q_ = ix["ant1"][b], ix["ant2"][b]
        o = np.zeros((nc, 8))
        for phi in range(2):
            mp, mq = big_e[phi, p_], big_e[phi, q_]
            both = np.isfinite(mp) & np.isfinite(mq)
            one = np.where(np.isfinite(mp), mp, mq)
            o[:, 4 * phi] = ash(e[b, phi])
            o[:, 4 * phi + 1] = ash(np.where(both, np.maximum(mp, mq), one))
            o[:, 4 * phi + 2] = ash(np.where(both, np.minimum(mp, mq), one))
            o[:, 4 * phi + 3] = ash(x[phi])
        planes = np.broadcast_to(o[None], (nt, nc, 8)).copy()
        planes[fl[b]] = 0.0
        out[i, ..., SPEC0 : SPEC0 + 8] = planes
    return out


# -- strength, comparators and N4 ---------------------------------------------------


def strength_rows(scan, w3, data=None, block=128):
    """(row, chan) float32 s = max(u^t, u^f, e^par, e^x) before asinh (0 on
    flagged cells; section 4's label strength)."""
    ix = f3.index(scan)
    nbl = len(ix["ubl"])
    out = np.zeros(w3.shape, np.float32)
    for s in range(0, nbl, block):
        sel = np.arange(s, min(s + block, nbl))
        x = rust_features(scan, w3, sel, data)
        v = np.sinh(
            np.maximum(x[..., :8].max(-1), np.maximum(x[..., SPEC0], x[..., SPEC0 + 4]))
        )
        rows = np.flatnonzero((ix["bl"] >= s) & (ix["bl"] < s + len(sel)))
        out[rows] = v[ix["bl"][rows] - s, ix["t"][rows]]
    return out


def _threshold_flags(scan, w3, data, residual_bar, spectral_bar, block=128):
    ix = f3.index(scan)
    nbl = len(ix["ubl"])
    out = np.zeros(w3.shape, bool)
    for s in range(0, nbl, block):
        sel = np.arange(s, min(s + block, nbl))
        x = rust_features(scan, w3, sel, data)
        hit = np.maximum(x[..., SPEC0], x[..., SPEC0 + 4]) > np.arcsinh(spectral_bar)
        if residual_bar is not None:
            hit |= x[..., :8].max(-1) > np.arcsinh(residual_bar)
        rows = np.flatnonzero((ix["bl"] >= s) & (ix["bl"] < s + len(sel)))
        out[rows] = hit[ix["bl"][rows] - s, ix["t"][rows]]
    return w3 | out


def z4_flags(scan, w3, data=None):
    """Z4 (section 2): residual planes above 10 or spectral planes above 5."""
    return _threshold_flags(scan, w3, data, f3.Z2_TAU, ZE_TAU)


def ze_flags(scan, w3, data=None):
    """ZE (section 2): the spectral planes alone above 5 (Stop-E)."""
    return _threshold_flags(scan, w3, data, None, ZE_TAU)


def n4_flags(scan, w3, weights, tau, data=None):
    logit = rust_logits(scan, w3, weights, data)
    return w3 | (logit > tau), logit


# -- injections (section 4) ---------------------------------------------------------

TRAIN_MORPHOLOGIES = f3.TRAIN_MORPHOLOGIES + ("T6",)
HELD_OUT = f3.HELD_OUT + ("H3",)
CODES = TRAIN_MORPHOLOGIES + HELD_OUT
T6_MIN, T6_MAX = 9, 400
T6_FRACTION = 0.45  # Amendment 2 (was 0.6)


def t6_width(rng, nc):
    hi = max(min(T6_MAX, int(T6_FRACTION * nc)), 1)
    lo = min(T6_MIN, hi)
    w = round(math.exp(rng.uniform(math.log(lo), math.log(hi))))
    return min(max(w, lo), hi)


def raised_cosine(nc, chans):
    """Per-channel factor: 1 inside `chans`, raised-cosine edges over 10 % of
    the width at each side."""
    env = np.ones(nc)
    edge = max(1, round(0.1 * len(chans)))
    ramp = 0.5 - 0.5 * np.cos(np.pi * (np.arange(edge) + 0.5) / edge)
    env[chans[:edge]] = ramp[: len(chans[:edge])]
    env[chans[::-1][:edge]] = np.minimum(
        env[chans[::-1][:edge]], ramp[: len(chans[::-1][:edge])]
    )
    return env


class Injector(f3.Injector):
    """F3's injector with T6 (training) and H3 (held out)."""

    codes = CODES
    jitter = ("T3", "T6")

    def t6(self):
        rng = self.rng
        k = int(rng.choice(self._live_antennas()))
        bsel = (self.ix["ant1"] == k) | (self.ix["ant2"] == k)
        w = t6_width(rng, self.nc)
        c0 = int(rng.integers(0, self.nc - w + 1))
        chans = np.arange(c0, c0 + w)
        if rng.random() < 0.75:
            tm = self._all_times()
        else:
            tm = self._run(min(2, self.nt), self.nt)
        env = None if rng.random() < 0.5 else raised_cosine(self.nc, chans)
        self.add("T6", bsel, tm, chans, envelope=env)
        self.events[-1]["width"] = w

    def training(self):
        super().training()
        for _ in range(self.rng.integers(1, 4)):
            self.t6()

    def held_out(self, code):
        if code != "H3":
            return super().held_out(code)
        rng = self.rng
        ants = self._live_antennas()
        pair = rng.choice(ants, 2, replace=False)
        bsel = np.isin(self.ix["ant1"], pair) | np.isin(self.ix["ant2"], pair)
        w = int(
            rng.integers(max(1, int(0.1 * self.nc)), max(2, int(0.4 * self.nc)) + 1)
        )
        w = min(w, self.nc)
        c0 = int(rng.integers(0, self.nc - w + 1))
        self.add("H3", bsel, self._all_times(), np.arange(c0, c0 + w))
        return None


# -- labels (section 4) -------------------------------------------------------------


def labels_calibrator(amp, eligible, t_flag, a_flag, s):
    """L-A1s: F3's Amendment 1 labels with strength s (section 4)."""
    return f3.labels_real(amp, eligible, t_flag, a_flag, strong=s >= 3)


def labels_target(amp, eligible, t_flag, a_flag, s):
    """L-INJ: positive on injections with A >= 3; negative where not
    injected, flagged by neither T nor A and s < 3; ignored otherwise."""
    lab = np.full(amp.shape, -1, np.int8)
    injected = amp > 0
    lab[eligible & ~injected & ~t_flag & ~a_flag & (s < 3)] = 0
    lab[(amp >= 3) & eligible] = 1
    return lab


def strong_consensus(t_flag, a_flag, eligible, s, bar=5.0):
    """R5's cells: uninjected eligible cells flagged by T and A with s >= bar."""
    return t_flag & a_flag & eligible & (s >= bar)


def realise(scan, w3, sigma, seed, augment, t_flag=None, a_flag=None, s=None):
    """One realisation (as F3's `realise`, with T6): (injected DATA, flags
    before the network, labels, Injector, rng). Real scans pass T's and A's
    flags and s on the uninjected DATA; F-SIM scans carry `amp`."""
    rng = np.random.default_rng(seed)
    inj = Injector(scan, ~w3, sigma, rng)
    inj.training()
    flags = f3.augment_input_flags(rng, w3, scan) if augment else w3
    elig = ~flags
    if t_flag is None:
        lab = f3.labels_sim(scan["amp"], inj.amp, elig)
    elif scan["klass"] == "calibrator":
        lab = labels_calibrator(inj.amp, elig, t_flag, a_flag, s)
    else:
        lab = labels_target(inj.amp, elig, t_flag, a_flag, s)
    return inj.data, flags, lab, inj, rng


def r2_case(scan, eligible, sigma, code, seed):
    inj = Injector(
        scan, eligible, sigma, np.random.default_rng(seed), fixed=f3.STRENGTH
    )
    inj.held_out(code)
    rows, chans = np.nonzero(inj.amp > 0)
    return inj.data, rows, chans


R1_SEEDS = f3.R1_SEEDS
R2_SEEDS = f3.R2_SEEDS
STOP_SEEDS = f3.STOPZ2_SEEDS
S3_SEEDS = (61, 62, 63)


# -- arm NA: antenna-domain autocorrelations (Amendment 1) ---------------------------

NA_DELTAS = (0.005, 0.01, 0.02, 0.05, 0.1)
NA_TLOCAL = 5.0


def load_autos(spec, scan, heldout=False):
    """(nant, nt, nc, 2) float64 Re of the XX and YY autocorrelations of the
    set `spec` on `scan`'s time grid (NaN where absent). The autos' FLAG and
    FLAG_ROW are ignored (processing flagged every auto cell)."""
    kind, _, name = spec.partition(":")
    if kind == "luno":
        check_luno_group(name, heldout)
        roots = (FETCH, f3.INPUTS) if name in FETCH_GROUPS else (f3.FETCH, f3.INPUTS)
        g = f"MAIN/{name}"
        r = f3._first(roots, f"{g}/TIME/0")
        a1 = f3._zarr(r, f"{g}/ANTENNA1", "0")
        a2 = f3._zarr(r, f"{g}/ANTENNA2", "0")
        times = f3._zarr(r, f"{g}/TIME", "0")
        keys = [
            (f3._first(roots, f"{g}/DATA/0.{t}.0"), f"0.{t}.0") for t in f3.LUNO_TILES
        ]
    elif kind == "eso":
        chunk = check_eso_chunk(int(name), heldout)
        g = "MAIN/MAIN_0"
        a1 = f3._zarr(f3.ESO, f"{g}/ANTENNA1", f"{chunk}")
        a2 = f3._zarr(f3.ESO, f"{g}/ANTENNA2", f"{chunk}")
        times = f3._zarr(f3.ESO, f"{g}/TIME", f"{chunk}")
        keys = [(f3.ESO, f"{chunk}.{t}.0") for t in f3.ESO_TILES]
    else:
        raise ValueError(spec)
    auto = a1 == a2
    data = np.concatenate(
        [f3._zarr(rt, f"{g}/DATA", k)[auto] for rt, k in keys], axis=1
    )
    tgrid = np.unique(scan["times"])
    ti = np.searchsorted(tgrid, times[auto])
    ok = (ti < len(tgrid)) & (tgrid[np.minimum(ti, len(tgrid) - 1)] == times[auto])
    nant = int(scan["nant"])
    out = np.full((nant, len(tgrid), data.shape[1], 2), np.nan)
    ant = a1[auto].astype(int)
    out[ant[ok], ti[ok]] = data[ok][..., [0, 3]].real
    return out


def _nan_mad(x, axis):
    m = f3._nanmedian(x, axis)
    return 1.4826 * f3._nanmedian(np.abs(x - np.expand_dims(m, axis)), axis)


def na_statistics(autos):
    """D (nant, nc) fractional scan-long excess and T (nant, nt, nc) time-local
    excess in MAD units (Amendment 1)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        m = f3._nanmedian(autos, 1)  # (nant, nc, 2)
        ref = f3._nanmedian(m, 0)  # (nc, 2)
        rho = m / ref[None]
        rho = rho / f3._nanmedian(rho, 1)[:, None, :]
        q = _percentile(rho, 25, 1)  # (nant, 2)
        d = _nanmax(rho - q[:, None, :], -1)
        ratio = autos / m[:, None] - 1
        s = _nan_mad(ratio, 1)
        t = _nanmax(ratio / s[:, None], -1)
    return d, t


def na_antenna_hits(autos, delta):
    """(nant, nt, nc) bool: antenna k flagged at (t, f)."""
    d, t = na_statistics(autos)
    return (d[:, None, :] > delta) | (t > NA_TLOCAL)


def na_flags(scan, autos, w3, delta):
    """W3 OR NA: every cross cell of a baseline whose antenna NA flags."""
    hit = na_antenna_hits(autos, delta)
    ix = f3.index(scan)
    t = ix["t"]
    return w3 | hit[scan["antenna1"], t] | hit[scan["antenna2"], t]


def auto_inject(autos, chans, antenna, strength=10.0):
    """G2's injection: +strength * sigma_auto on one antenna's XX and YY,
    channels `chans`, all dumps; sigma_auto from channel differences. The
    antenna and band are F1's antenna-local choice for the seed (caller)."""
    out = autos.copy()
    a = autos[antenna]
    d = (a[:, 1:] - a[:, :-1]).reshape(-1, 2)
    sigma = _nan_mad(d, 0) / math.sqrt(2)  # (2,)
    out[antenna][:, chans] += strength * sigma[None, None]
    return out
