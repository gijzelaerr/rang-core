"""B1-3: pointing self-calibration and the rang method at matched cost.

research/b1-3-pointing-selfcal.md freezes the protocol. This module holds:

- per-antenna holography beams by the frozen rule (the native array average
  plus the antenna's difference from it, linear in frequency between the
  product channels), with analytic spline gradients (`AntennaBeams`), and
  toy beams for tests (`ToyBeams`, `ScaledGaussianBeams`);
- the perturbed-beam terms and their Jacobian per antenna and hand
  (`beam_terms`), and per baseline (`pair_terms`): pointing, squint,
  ellipticity and width as B1-2 parametrised them, composed;
- the per-bin work (`_task`): gains per antenna x hand x channel x 2-dump
  interval re-solved exactly (StefCal form), the profiled normal equations
  of [gains | sky (ln S0, alpha) | beam parameters] with the gains
  Schur-eliminated, the survey accumulation (ratio mode, apparent fluxes as
  B1-2), prediction for simulations, held-out evaluation and faint-source
  fits; run over (scan, 32-channel block) tasks in forked processes;
- `Problem`: the profiled Levenberg-Marquardt solver with three arms (gains
  only, physical pointing self-calibration (ii), and the rang method R with
  distinguishability selection from its own first pass), and the held-out
  split on L1's grid;
- the raster (fixture) fit for B1-1's data type (`fit_raster`).

No dense Jacobian is built; every Gram block is a sum of Re(conj(a) b) over
whitened samples (`beam_identifiability.normals_columns`).
"""

import math
import multiprocessing
import time

import numpy as np
from scipy import optimize

from . import beam_holography, measures
from . import beam_identifiability as bi

LIGHT = bi.LIGHTSPEED
ARCMIN_DEG = 1.0 / 60.0
SIGMA_HAND = (1.0, -1.0)  # squint: H row at u - s/2, V row at u + s/2
HANDS = ((0, 0), (1, 3))  # (hand, correlation): X = XX, Y = YY
TIME_BIN = 2
BLOCK = 32
SUB = 16
NCOM_FIT = 3  # squint x, squint y, ellipticity
NCOM_SURVEY = 4  # + log-width
PRIOR_ARCMIN = 3.0
PRIOR_ELLIPTICITY = 0.05
LM_LAMBDA0 = 1e-3
LM_MAX_PASSES = 10
LM_REL_STOP = 1e-7
LM_LAMBDA_MAX = 1e8
STEFCAL_ITER = 100
STEFCAL_TOL = 1e-8
SPLIT_SEED = 7

# --------------------------------------------------------------------------
# Beams


def _stack8(real, imag):
    """(2, 2, ny, nx) real and imaginary coefficients -> (ny, nx, 8): re of
    (00, 01, 10, 11) then im."""
    ny, nx = real.shape[-2:]
    return np.concatenate((real.reshape(4, ny, nx), imag.reshape(4, ny, nx))).transpose(
        1, 2, 0
    )


def _to_jones(v):
    return (v[..., :4] + 1j * v[..., 4:]).reshape(v.shape[:-1] + (2, 2))


def sample_stack(coeffs, rows, cols):
    """Cubic B-spline value and its column and row derivatives of the
    8-channel coefficient stack `coeffs` ((N, ny, nx, 8), or (ny, nx, 8)
    shared) at per-antenna points rows, cols (N, P). Returns three (N, P, 8)
    arrays. Interior points only (the 4 x 4 taps inside the grid)."""
    rows = np.asarray(rows, float)
    cols = np.asarray(cols, float)
    shared = coeffs.ndim == 3
    ny, nx = coeffs.shape[-3:-1]
    r0 = np.floor(rows).astype(int) - 1
    c0 = np.floor(cols).astype(int) - 1
    if r0.min() < 0 or c0.min() < 0 or r0.max() + 3 >= ny or c0.max() + 3 >= nx:
        raise ValueError("beam coordinates outside the cropped grid")
    wr = [
        (bi._kernel(rows - (r0 + a), 0), bi._kernel(rows - (r0 + a), 1))
        for a in range(4)
    ]
    wc = [
        (bi._kernel(cols - (c0 + b), 0), bi._kernel(cols - (c0 + b), 1))
        for b in range(4)
    ]
    value = np.zeros(rows.shape + (8,))
    dcol = np.zeros_like(value)
    drow = np.zeros_like(value)
    ant = np.arange(rows.shape[0])[:, None]
    for a in range(4):
        ra = r0 + a
        for b in range(4):
            cb = c0 + b
            g = coeffs[ra, cb] if shared else coeffs[ant, ra, cb]
            value += g * (wr[a][0] * wc[b][0])[..., None]
            dcol += g * (wr[a][0] * wc[b][1])[..., None]
            drow += g * (wr[a][1] * wc[b][0])[..., None]
    return value, dcol, drow


class AntennaBeams:
    """Per-antenna holography beams (B1-3 frozen rule).

    E_p(nu) = E_avg(nu) + (1 - t) D_p(nu_k) + t D_p(nu_k+1) with E_avg the
    native array average (linear between native channels), D_p = E_p -
    E_avg at the bracketing product channels nu_k, nu_k+1, everything on the
    spline coefficients (the prefilter is linear). Each antenna is
    normalised so that its own Stokes I power is 1 at the origin.

    `antennas`: holography antenna index (0..63) per data antenna, None for
    the array average. `mode` "antenna" (the rule) or "average" (the array
    average for every antenna). `copolar` zeroes HV and VH. Coefficients
    are cropped to `radius_deg` (plus the spline taps) after prefiltering."""

    name = "holography"

    def __init__(
        self, product, antennas, mode="antenna", copolar=False, radius_deg=1.6
    ):
        self.product = product
        self.antennas = list(antennas)
        self.n = len(self.antennas)
        self.mode = mode
        self.copolar = copolar
        half = math.ceil(radius_deg / beam_holography.PIXEL_DEG) + 4
        self.lo = beam_holography.CENTRE_INDEX - half
        self.hi = beam_holography.CENTRE_INDEX + half + 1
        self.half = half
        self.flip = product.flip
        self.margin0 = float(product.margin_deg[0])
        self.radius_deg = radius_deg
        self._avg = {}
        self._delta = {}

    def _crop(self, maps):
        real = beam_holography._prefilter(maps.real)
        imag = beam_holography._prefilter(maps.imag)
        s = _stack8(real, imag)[self.lo : self.hi, self.lo : self.hi].copy()
        if self.copolar:
            s[..., [1, 2, 5, 6]] = 0.0
        return s

    def _average(self, channel):
        channel = int(channel)
        if channel not in self._avg:
            if len(self._avg) > 16:
                self._avg.pop(next(iter(self._avg)))
            self._avg[channel] = self._crop(
                self.product._maps("array_average", channel)
            )
        return self._avg[channel]

    def _antenna_delta(self, channel):
        channel = int(channel)
        if channel not in self._delta:
            if len(self._delta) > 6:
                self._delta.pop(next(iter(self._delta)))
            avg = self._average(channel)
            out = np.zeros((self.n,) + avg.shape)
            for i, a in enumerate(self.antennas):
                if a is not None:
                    out[i] = self._crop(self.product._maps(int(a), channel)) - avg
            self._delta[channel] = out
        return self._delta[channel]

    def _average_coefficients(self, freq):
        lo, hi, w = self.product.bracket("array_average", float(freq))
        c = (1 - w) * self._average(lo)
        if w > 0:
            c = c + w * self._average(hi)
        return c

    def prepare(self, freq):
        """Coefficients (N, ny, nx, 8) and per-antenna norms at `freq`."""
        c = self._average_coefficients(freq)
        if self.mode == "average":
            coeffs = np.broadcast_to(c, (self.n,) + c.shape)
        else:
            klo, khi, t = self.product.bracket(0, float(freq))
            d = (1 - t) * self._antenna_delta(klo)
            if t > 0:
                d = d + t * self._antenna_delta(khi)
            coeffs = c[None] + d
        zero = np.full((self.n, 1), float(self.half))
        value, _, _ = sample_stack(coeffs, zero, zero)
        e = _to_jones(value[:, 0])
        norm = np.sqrt(0.5 * np.sum(np.abs(e) ** 2, axis=(-2, -1)))
        return {"coeffs": coeffs, "norm": norm, "freq": float(freq)}

    def _pixels(self, x, y):
        step = beam_holography.PIXEL_DEG
        col = (np.asarray(x) - self.margin0) / step - self.lo
        row = (self.flip * np.asarray(y) - self.margin0) / step - self.lo
        return row, col

    def evaluate(self, handle, x, y):
        """Normalised Jones and its gradient per degree at per-antenna
        antenna-frame points x, y (N, P) degrees: three (N, P, 2, 2)."""
        row, col = self._pixels(x, y)
        value, dcol, drow = sample_stack(handle["coeffs"], row, col)
        step = beam_holography.PIXEL_DEG
        norm = handle["norm"][:, None, None, None]
        e = _to_jones(value) / norm
        ex = _to_jones(dcol) / step / norm
        ey = self.flip * _to_jones(drow) / step / norm
        return e, ex, ey

    def average_power(self, freq, x, y):
        """Array-average Stokes I power (normalised) at points x, y (P,)."""
        c = self._average_coefficients(freq)
        zero = np.full((1, 1), float(self.half))
        v0, _, _ = sample_stack(c, zero, zero)
        norm2 = 0.5 * np.sum(np.abs(_to_jones(v0[0, 0])) ** 2)
        row, col = self._pixels(np.atleast_1d(x)[None], np.atleast_1d(y)[None])
        value, _, _ = sample_stack(c, row, col)
        e = _to_jones(value[0])
        return 0.5 * np.sum(np.abs(e) ** 2, axis=(-2, -1)) / norm2


class ToyBeams:
    """Per-antenna `GaussianToyBeam`s behind the `AntennaBeams` interface
    (tests). `average` is the beam used for `average_power`."""

    name = "toy"

    def __init__(self, beams, average=None):
        self.beams = list(beams)
        self.n = len(self.beams)
        self.average = average or self.beams[0]

    def prepare(self, freq):
        norms = []
        for b in self.beams:
            e, _, _ = b(np.zeros(1), np.zeros(1), freq)
            norms.append(math.sqrt(0.5 * np.sum(np.abs(e[0]) ** 2)))
        return {"freq": float(freq), "norm": np.array(norms)}

    def evaluate(self, handle, x, y):
        out = [np.zeros(np.shape(x) + (2, 2), complex) for _ in range(3)]
        for i, b in enumerate(self.beams):
            e, ex, ey = b(x[i], y[i], handle["freq"])
            for k, v in enumerate((e, ex, ey)):
                out[k][i] = v / handle["norm"][i]
        return tuple(out)

    def average_power(self, freq, x, y):
        e, _, _ = self.average(np.atleast_1d(x), np.atleast_1d(y), freq)
        e0, _, _ = self.average(np.zeros(1), np.zeros(1), freq)
        return (
            0.5
            * np.sum(np.abs(e) ** 2, axis=(-2, -1))
            / (0.5 * np.sum(np.abs(e0[0]) ** 2))
        )


class ScaledGaussianBeams:
    """The voltage beam of `pointing.predict`: exp(-2 ln 2 r^2 / fwhm^2)
    with fwhm = 1.02 lambda / D (radians), both hands equal, no squint; for
    the JAX gradient check."""

    name = "scaled-gaussian"

    def __init__(self, nant, dish_m=13.5):
        self.n = nant
        self.dish = dish_m

    def _fwhm_deg(self, freq):
        return math.degrees(1.02 * LIGHT / freq / self.dish)

    def prepare(self, freq):
        return {"freq": float(freq), "norm": np.ones(self.n)}

    def evaluate(self, handle, x, y):
        f = self._fwhm_deg(handle["freq"])
        k = 2 * math.log(2) / f**2
        v = np.exp(-k * (np.asarray(x) ** 2 + np.asarray(y) ** 2))
        e = np.zeros(np.shape(x) + (2, 2), complex)
        ex = np.zeros_like(e)
        ey = np.zeros_like(e)
        for h in range(2):
            e[..., h, h] = v
            ex[..., h, h] = -2 * k * np.asarray(x) * v
            ey[..., h, h] = -2 * k * np.asarray(y) * v
        return e, ex, ey

    def average_power(self, freq, x, y):
        f = self._fwhm_deg(freq)
        k = 2 * math.log(2) / f**2
        return np.exp(-2 * k * (np.asarray(x) ** 2 + np.asarray(y) ** 2))


# --------------------------------------------------------------------------
# Perturbed-beam terms


def beam_terms(beams, handle, u_deg, delta, squint=(0.0, 0.0), ellip=0.0, width=0.0):
    """Per hand h: the h row of every antenna's Jones at the perturbed
    coordinates T_p,h(u) = D (u - delta_p - sigma_h s / 2), D = diag(e^(-w-e),
    e^(-w+e)), and its derivatives. u_deg (K, 2) antenna-frame degrees;
    delta (N, 2) and squint (2,) arcmin. Returns two dicts with "e" (N, K, 2
    m), "d" (N, K, 2 m, 2 axes) = dE/d delta (per arcmin), "de" and "dw"
    (N, K, 2 m) = dE/d e and dE/d w."""
    delta = np.asarray(delta, float)
    squint = np.asarray(squint, float)
    dvec = np.array([math.exp(-width - ellip), math.exp(-width + ellip)])
    out = []
    for h, sig in enumerate(SIGMA_HAND):
        shift = (delta + sig * squint / 2) * ARCMIN_DEG
        t = dvec * (u_deg[None] - shift[:, None])
        e, ex, ey = beams.evaluate(handle, t[..., 0], t[..., 1])
        e, ex, ey = e[..., h, :], ex[..., h, :], ey[..., h, :]
        d = np.stack((-dvec[0] * ARCMIN_DEG * ex, -dvec[1] * ARCMIN_DEG * ey), axis=-1)
        tx, ty = t[..., 0][..., None], t[..., 1][..., None]
        out.append(
            {"e": e, "d": d, "de": -tx * ex + ty * ey, "dw": -(tx * ex + ty * ey)}
        )
    return out


def pair_terms(term, bp, bq, mode, beamed=None, keep=None):
    """Per baseline (bp, bq) and component of one hand: the model factor F
    and its derivatives dFp (pointing of the first antenna, 2 axes), dFq
    (second antenna), dFe (ellipticity), dFw (width).

    mode "fit": F = B_pq = sum_m E_p conj(E_q) for `beamed` components (1
    otherwise, with zero derivatives). mode "ratio" (the survey, apparent
    fluxes): F = 1 and the derivatives divided by B_pq for `keep`
    components (zero otherwise)."""
    ep = term["e"][bp]
    ceq = np.conj(term["e"][bq])
    b = np.sum(ep * ceq, axis=-1)
    dp = np.einsum("bkmj,bkm->bkj", term["d"][bp], ceq)
    dq = np.einsum("bkm,bkmj->bkj", ep, np.conj(term["d"][bq]))
    de = np.sum(term["de"][bp] * ceq, axis=-1) + np.sum(
        ep * np.conj(term["de"][bq]), axis=-1
    )
    dw = np.sum(term["dw"][bp] * ceq, axis=-1) + np.sum(
        ep * np.conj(term["dw"][bq]), axis=-1
    )
    if mode == "fit":
        on = np.ones(b.shape[-1], bool) if beamed is None else np.asarray(beamed)
        f = np.where(on, b, 1.0)
        scale = on.astype(float)
    elif mode == "ratio":
        on = np.ones(b.shape[-1], bool) if keep is None else np.asarray(keep)
        f = np.ones_like(b)
        scale = np.where(on, 1.0 / np.where(b == 0, 1.0, b), 0.0)
    else:
        raise ValueError(mode)
    return {
        "F": f,
        "dp": dp * scale[..., None],
        "dq": dq * scale[..., None],
        "de": de * scale,
        "dw": dw * scale,
    }


def sample_columns(a, pt, bl, sigma, ncom):
    """Per-sample derivative columns of one hand from the component terms a
    (n, K) = flux x phase and the pair terms gathered by baseline index bl:
    y1, y2 (n, 2) and d (n, ncom) = [squint_x, squint_y, ellipticity,
    log-width][:ncom]."""
    y1 = np.einsum("nk,nkj->nj", a, pt["dp"][bl])
    y2 = np.einsum("nk,nkj->nj", a, pt["dq"][bl])
    cols = []
    if ncom >= 2:
        cols += [
            0.5 * sigma * (y1[:, 0] + y2[:, 0]),
            0.5 * sigma * (y1[:, 1] + y2[:, 1]),
        ]
    if ncom >= 3:
        cols.append(np.einsum("nk,nk->n", a, pt["de"][bl]))
    if ncom >= 4:
        cols.append(np.einsum("nk,nk->n", a, pt["dw"][bl]))
    d = np.stack(cols, axis=1) if cols else np.zeros((len(a), 0), complex)
    return y1, y2, d


def stefcal_warm(
    data, model, weight, a1, a2, nant, g0, iterations=STEFCAL_ITER, tol=STEFCAL_TOL
):
    """Diagonal amplitude-and-phase gains of one hand and bin, minimising
    sum w |D - g_p conj(g_q) M|^2 by B1-2's StefCal form (averaging 0.5)
    from the warm start g0. Antennas without samples keep g0."""
    g = np.array(g0, complex)
    w = weight
    it = 0
    for it in range(iterations):
        gq = g[a2]
        gp = g[a1]
        zp = np.conj(gq) * model
        num = np.bincount(a1, (w * data * np.conj(zp)).real, nant) + 1j * np.bincount(
            a1, (w * data * np.conj(zp)).imag, nant
        )
        zq = np.conj(gp) * np.conj(model)
        num = (
            num
            + np.bincount(a2, (w * np.conj(data) * np.conj(zq)).real, nant)
            + 1j * np.bincount(a2, (w * np.conj(data) * np.conj(zq)).imag, nant)
        )
        den = np.bincount(a1, w * np.abs(zp) ** 2, nant) + np.bincount(
            a2, w * np.abs(zq) ** 2, nant
        )
        new = np.where(den > 0, num / np.where(den > 0, den, 1), g)
        new = 0.5 * (new + g)
        change = np.max(np.abs(new - g)) / max(np.max(np.abs(g)), 1e-30)
        g = new
        if change < tol:
            return g, it + 1
    return g, iterations


# --------------------------------------------------------------------------
# Scans and the per-task work


def prepare_scan(d, s2, train=None, test=None):
    """Static per-scan arrays for the tasks. d: the B1-2 loader dict (data,
    flag, weight (rows, chans, 4), a1, a2, time, uvw, freqs, positions,
    phase_dir). s2 (2,): the noise scale per hand. train, test: (rows,
    chans) cell masks of the split (None: every eligible sample trains)."""
    times = np.unique(d["time"])
    integ = np.searchsorted(times, d["time"])
    tbin = integ // TIME_BIN
    bins = np.unique(tbin)
    rows_by_bin = [np.flatnonzero(tbin == t) for t in bins]
    tmean = np.array([d["time"][r].mean() for r in rows_by_bin])
    if "q_bins" in d:  # tests: parallactic angle per bin given directly
        q = np.asarray(d["q_bins"], float)
    else:
        centre = measures.array_centre(d["positions"])
        q = measures.parallactic_angle(tmean, *d["phase_dir"], centre)
    nant = len(d["positions"])
    key = d["a1"] * nant + d["a2"]
    ukey, bl = np.unique(key, return_inverse=True)
    elig = np.zeros(d["data"].shape[:2] + (2,), bool)
    for h, c in HANDS:
        elig[..., h] = (
            ~d["flag"][..., c]
            & (d["weight"][..., c] > 0)
            & np.isfinite(d["data"][..., c])
        )
    out = {
        "a1": np.asarray(d["a1"], int),
        "a2": np.asarray(d["a2"], int),
        "uvw": np.asarray(d["uvw"], float),
        "freqs": np.asarray(d["freqs"], float),
        "data": d["data"],
        "weight": d["weight"],
        "elig": elig,
        "rows_by_bin": rows_by_bin,
        "q": q,
        "bl": bl,
        "bp": ukey // nant,
        "bq": ukey % nant,
        "nant": nant,
        "s2": np.asarray(s2, float),
        "time_span_s": float(np.ptp(d["time"]) + 8.0),
    }
    if train is not None:
        held = ~train
        out["train"] = elig & ~held[..., None]
        out["test"] = test & elig.all(-1)
    else:
        out["train"] = elig
        out["test"] = None
    return out


def _delays(uvw, lm):
    l, m = lm[:, 0], lm[:, 1]
    n1 = np.sqrt(1.0 - l * l - m * m) - 1.0
    return uvw[:, 0:1] * l + uvw[:, 1:2] * m + uvw[:, 2:3] * n1


def _gauss_terms(uvw, sky):
    g = np.flatnonzero(sky["kind"] == 1)
    if not len(g):
        return g, None, None
    major, minor, pa = sky["gauss_shape"][g].T
    u, v = uvw[:, 0:1], uvw[:, 1:2]
    along = u * np.sin(pa) + v * np.cos(pa)
    across = u * np.cos(pa) - v * np.sin(pa)
    quad = (major * along) ** 2 + (minor * across) ** 2
    return g, quad, -(np.pi**2) / (4 * math.log(2)) / LIGHT**2


def _envelope(phase, gauss, nu):
    """Apply the Gaussian components' envelope at frequency nu (copy)."""
    g, quad, const = gauss
    if g is None or not len(g):
        return phase
    out = phase.copy()
    out[:, g] *= np.exp(const * nu * nu * quad)
    return out


_CTX = {}


def _sub_blocks(nch, width):
    return [(s, min(s + width, nch)) for s in range(0, nch, width)]


def _task(args):
    """One (scan, 32-channel block) of a pass. See `Problem.run_pass`."""
    ctx = _CTX
    s, f, params, gains_in, mode = args
    scan = ctx["scans"][s]
    sky = ctx["sky"]
    cfg = ctx["cfg"]
    nant = scan["nant"]
    ncomp = len(sky["lm"])
    freqs = scan["freqs"]
    chans = np.arange(f * BLOCK, min((f + 1) * BLOCK, len(freqs)))
    nu0 = cfg["nu0"]
    started = time.perf_counter()
    if mode == "survey":
        variants = cfg["variants"]  # [(beams, sub width)]
        ncom = NCOM_SURVEY
        acc = bi.ChannelSurvey(nant, ncomp, len(ctx["scans"]), len(variants), ncom)
    else:
        variants = [(ctx["beams"], SUB)]
        ncom = params.get("ncom", 0)
        per_antenna = params.get("per_antenna", False)
    a_sky = params.get("a", np.zeros(ncomp))
    b_sky = params.get("b", np.zeros(ncomp))
    delta = params.get("delta", np.zeros((nant, 2)))
    squint = params.get("squint", np.zeros(2))
    ellip = float(params.get("ellip", 0.0))
    base = ctx["base"][s]  # (K, nchan) S_base
    beamed = ctx["beamed"]
    lm = sky["lm"]
    handles = {}
    nbins = len(scan["rows_by_bin"])
    gains_out = np.ones((nbins, len(chans), 2, nant), complex)
    if gains_in is not None:
        gains_out[:] = gains_in
    n_loc = (
        2 * ncomp
        + (2 * nant if mode != "survey" and per_antenna else 0)
        + (ncom if mode != "survey" else 0)
    )
    h_acc = np.zeros((n_loc, n_loc)) if mode == "fit" else None
    b_acc = np.zeros(n_loc) if mode == "fit" else None
    nraw = n_loc - 2 * ncomp
    raw_acc = np.zeros((nraw, nraw)) if mode == "fit" else None
    chi2 = 0.0
    nsamp = 0
    nsolve = 0
    niter = 0
    pred = None
    if mode == "predict":
        pred = np.zeros((len(scan["a1"]), len(chans), 2), np.complex64)
    eval_idx, eval_val = [], []
    faint = None
    if mode == "faint":
        fsky = ctx["faint_sky"]
        nf = len(fsky["lm"])
        faint = {
            "h": np.zeros((len(chans), nf, nf)),
            "b": np.zeros((len(chans), nf)),
        }
    for ti, rows_t in enumerate(scan["rows_by_bin"]):
        q = scan["q"][ti]
        x, y = measures.sky_to_beam(lm[:, 0], lm[:, 1], q)
        u_deg = np.stack((np.degrees(x), np.degrees(y)), axis=1)
        if mode == "faint":
            fx, fy = measures.sky_to_beam(fsky["lm"][:, 0], fsky["lm"][:, 1], q)
            fu_deg = np.stack((np.degrees(fx), np.degrees(fy)), axis=1)
        uvw = scan["uvw"][rows_t]
        tau = _delays(uvw, lm)
        gauss = _gauss_terms(uvw, sky)
        if mode == "faint":
            ftau = _delays(uvw, fsky["lm"])
        a1 = scan["a1"][rows_t]
        a2 = scan["a2"][rows_t]
        blr = scan["bl"][rows_t]
        pair_cache = {}
        run_start = None
        for ci, c in enumerate(chans):
            nu = freqs[c]
            # phase recurrence, re-anchored at every 16-channel run
            if run_start is None or (c - chans[0]) % SUB == 0:
                run_start = c
                end = min(run_start + SUB, chans[-1] + 1)
                dnu = freqs[c + 1] - nu if end - run_start > 1 else 0.0
                uniform = end - run_start <= 1 or np.allclose(
                    np.diff(freqs[run_start:end]), dnu, rtol=0, atol=1e-3
                )
                cur = np.exp((2j * np.pi / LIGHT) * nu * tau)
                pstep = np.exp((2j * np.pi / LIGHT) * dnu * tau) if uniform else None
                if mode == "faint":
                    fcur = np.exp((2j * np.pi / LIGHT) * nu * ftau)
                    fstep = (
                        np.exp((2j * np.pi / LIGHT) * dnu * ftau) if uniform else None
                    )
            elif uniform:
                cur = cur * pstep
                if mode == "faint":
                    fcur = fcur * fstep
            else:
                cur = np.exp((2j * np.pi / LIGHT) * nu * tau)
                if mode == "faint":
                    fcur = np.exp((2j * np.pi / LIGHT) * nu * ftau)
            phase = _envelope(cur, gauss, nu)
            lf = math.log(nu / nu0)
            spec = base[:, c] * np.exp(a_sky + b_sky * lf)
            amp = phase * spec[None]
            # beam pair terms per variant at the sub-block centre
            vterms = []
            for v, (beams, width) in enumerate(variants):
                sb = (c - chans[0]) // width
                key = (v, sb)
                if key not in pair_cache:
                    lo = chans[0] + sb * width
                    hi = min(lo + width, chans[-1] + 1)
                    feval = float(freqs[lo:hi].mean())
                    hkey = (v, sb)
                    if hkey not in handles:
                        handles[hkey] = beams.prepare(feval)
                    terms = beam_terms(
                        beams, handles[hkey], u_deg, delta, squint, ellip
                    )
                    if mode == "survey":
                        ib = ctx["average"].average_power(
                            feval, u_deg[:, 0], u_deg[:, 1]
                        )
                        keep = ib >= bi.IB_FLOOR
                        pts = [
                            pair_terms(t, scan["bp"], scan["bq"], "ratio", keep=keep)
                            for t in terms
                        ]
                    else:
                        pts = [
                            pair_terms(t, scan["bp"], scan["bq"], "fit", beamed=beamed)
                            for t in terms
                        ]
                    fpts = None
                    if mode == "faint":
                        fterms = beam_terms(
                            beams, handles[hkey], fu_deg, delta, squint, ellip
                        )
                        fpts = [
                            pair_terms(t, scan["bp"], scan["bq"], "fit")["F"]
                            for t in fterms
                        ]
                    pair_cache[key] = (pts, fpts)
                vterms.append(pair_cache[key])
            if mode == "faint":
                fphase = fcur
            for h, corr in HANDS:
                if mode == "survey":
                    sel = scan["elig"][rows_t, c, h]
                elif mode in ("fit", "gains"):
                    sel = scan["train"][rows_t, c, h]
                elif mode == "eval":
                    sel = scan["test"][rows_t, c]
                elif mode == "faint":
                    sel = scan["elig"][rows_t, c, h]
                else:  # predict
                    sel = np.ones(len(rows_t), bool)
                if not sel.any():
                    continue
                loc = np.flatnonzero(sel)
                idx = rows_t[loc]
                bli = blr[loc]
                p, qq = a1[loc], a2[loc]
                am = amp[loc]
                pts0 = vterms[0][0][h]
                z0 = am * pts0["F"][bli]
                m0 = z0.sum(axis=1)
                if mode == "survey":
                    w = scan["weight"][idx, c, corr].astype(float)
                    sw = np.sqrt(w)
                    z = z0 * sw[:, None]
                    cols = []
                    for v in range(len(variants)):
                        y1, y2, dd = sample_columns(
                            am, vterms[v][0][h], bli, SIGMA_HAND[h], NCOM_SURVEY
                        )
                        cols.append(
                            (y1 * sw[:, None], y2 * sw[:, None], dd * sw[:, None])
                        )
                    hm = bi.normals_columns(p, qq, nant, z, cols)
                    acc.add(s, f, h, lf, hm, len(idx))
                    continue
                g = gains_out[ti, ci, h]
                if mode == "predict":
                    gt = ctx["truth_gains"][s][c, h]
                    pred[idx, ci, h] = (gt[p] * np.conj(gt[qq]) * m0).astype(
                        np.complex64
                    )
                    continue
                d = scan["data"][idx, c, corr].astype(complex)
                w = scan["weight"][idx, c, corr].astype(float) / scan["s2"][h]
                if mode in ("fit", "gains"):
                    g, it = stefcal_warm(d, m0, w, p, qq, nant, g)
                    gains_out[ti, ci, h] = g
                    nsolve += 1
                    niter += it
                gg = g[p] * np.conj(g[qq])
                r = d - gg * m0
                if mode == "eval":
                    ok = ctx["predictable"][s][ti, ci, h]
                    good = ok[p] & ok[qq]
                    val = w * np.abs(r) ** 2
                    eval_idx.append(
                        np.stack((idx, np.full(len(idx), c), np.full(len(idx), h)), 1)[
                            good
                        ]
                    )
                    eval_val.append(val[good])
                    continue
                if mode == "faint":
                    fz = fphase[loc] * vterms[0][1][h][bli] * gg[:, None]
                    sw = np.sqrt(w)
                    fz = fz * sw[:, None]
                    rw = r * sw
                    faint["h"][ci] += fz.real.T @ fz.real + fz.imag.T @ fz.imag
                    faint["b"][ci] += fz.real.T @ rw.real + fz.imag.T @ rw.imag
                    continue
                sw = np.sqrt(w)
                rw = r * sw
                chi2 += float(np.sum(np.abs(rw) ** 2))
                nsamp += len(idx)
                if mode == "gains":
                    continue
                gs = gg * sw
                z = z0 * gs[:, None]
                cols = []
                if per_antenna or ncom:
                    y1, y2, dd = sample_columns(am, pts0, bli, SIGMA_HAND[h], ncom)
                    if not per_antenna:
                        y1 = np.zeros_like(y1)
                        y2 = np.zeros_like(y2)
                    cols.append((y1 * gs[:, None], y2 * gs[:, None], dd * gs[:, None]))
                hm, bm = bi.normals_columns(p, qq, nant, z, cols, rw)
                ng = 2 * nant
                if per_antenna or ncom:
                    keep_idx = np.r_[
                        np.arange(ng + ncomp),
                        (ng + ncomp + np.arange(2 * nant)) if per_antenna else [],
                        ng + ncomp + 2 * nant + np.arange(ncom),
                    ].astype(int)
                    hm = hm[np.ix_(keep_idx, keep_idx)]
                    bm = bm[keep_idx]
                hr, br = bi.schur_rhs(hm, bm, ng)
                h_acc += bi.lf_map(hr, ncomp, lf)
                b_acc += bi.lf_map_vector(br, ncomp, lf)
                if nraw:
                    raw_acc += hm[ng + ncomp :, ng + ncomp :]
    out = {"scan": s, "block": f, "seconds": time.perf_counter() - started}
    if mode == "survey":
        out["acc"] = acc
    elif mode == "predict":
        out["pred"] = pred
    elif mode == "eval":
        out["idx"] = np.concatenate(eval_idx) if eval_idx else np.zeros((0, 3), int)
        out["val"] = np.concatenate(eval_val) if eval_val else np.zeros(0)
    elif mode == "faint":
        out["faint"] = faint
    else:
        out.update(
            gains=gains_out,
            chi2=chi2,
            samples=nsamp,
            solves=nsolve,
            stefcal_iterations=niter,
        )
        if mode == "fit":
            out.update(h=h_acc, b=b_acc, raw=raw_acc)
    return out


# --------------------------------------------------------------------------
# The held-out split on L1's grid


def split_cells(scans_elig, group_channels, seed=SPLIT_SEED):
    """Seed-7 80/10/10 split of the cells eligible in both hands, groups =
    (2-dump bin x `group_channels` channels) x baseline, two training cells
    reserved per group (`core_policy.split_holdout`). `scans_elig` is a list
    of (elig (rows, chans) bool, tbin (rows,), baseline (rows,)) in scan
    order; the draw covers their row concatenation. Returns per scan
    (train, validation, test) cell masks."""
    from .core_policy import split_holdout

    elig = np.concatenate([e for e, _, _ in scans_elig], axis=0)
    groups = []
    offset = 0
    for e, tb, blr in scans_elig:
        nch = e.shape[1]
        cb = np.arange(nch) // group_channels
        nbl = int(blr.max()) + 1
        ncb = int(cb.max()) + 1
        ntb = int(tb.max()) + 1
        g = (tb[:, None] * ncb + cb[None, :]) * nbl + blr[:, None] + offset
        groups.append(g)
        offset += ntb * ncb * nbl
    groups = np.concatenate(groups, axis=0)
    train, val, test = split_holdout(elig, seed, groups=groups, minimum_train=2)
    out = []
    at = 0
    for e, _, _ in scans_elig:
        n = e.shape[0]
        out.append((train[at : at + n], val[at : at + n], test[at : at + n]))
        at += n
    return out


def scan_bins(d):
    """2-dump bin and baseline index per row (the split's groups)."""
    times = np.unique(d["time"])
    tbin = np.searchsorted(times, d["time"]) // TIME_BIN
    nant = len(d["positions"])
    _, blr = np.unique(
        np.asarray(d["a1"]) * nant + np.asarray(d["a2"]), return_inverse=True
    )
    return tbin, blr


def eligible_both(d):
    e = np.ones(d["data"].shape[:2], bool)
    for _h, c in HANDS:
        e &= (
            ~d["flag"][..., c]
            & (d["weight"][..., c] > 0)
            & np.isfinite(d["data"][..., c])
        )
    return e


# --------------------------------------------------------------------------
# The solver


class Problem:
    """One set: scans, sky, beams and the forked worker pool.

    sky: dict with lm (K, 2), kind, gauss_shape, and `base` (per scan (K,
    nchan) intrinsic or apparent base spectra), `beamed` (K,) (fit mode:
    components that carry the beam). `average` is the array-average beam
    object for floors. `nproc` single-threaded workers over (scan, block)
    tasks."""

    def __init__(self, scans, sky, beams, nu0, nproc=4, average=None, extra=None):
        self.scans = scans
        self.sky = sky
        self.beams = beams
        self.nu0 = nu0
        self.nproc = nproc
        self.average = average or beams
        self.extra = extra or {}
        self.nant = scans[0]["nant"]
        self.ncomp = len(sky["lm"])
        self.tasks = [
            (s, f)
            for s, sc in enumerate(scans)
            for f in range(math.ceil(len(sc["freqs"]) / BLOCK))
        ]
        self._pool = None
        self.passes = []
        if scans[0].get("test") is not None and "predictable" not in self.extra:
            self.extra["predictable"] = predictable(self)

    def _context(self, variants=None):
        _CTX.clear()
        _CTX.update(
            scans=self.scans,
            sky=self.sky,
            beams=self.beams,
            base=self.sky["base"],
            beamed=self.sky.get("beamed"),
            average=self.average,
            cfg={"nu0": self.nu0, "variants": variants or []},
            **self.extra,
        )

    def map(self, jobs, variants=None):
        """Run tasks (in the pool when nproc > 1)."""
        if self.nproc <= 1:
            self._context(variants)
            return [_task(j) for j in jobs]
        if self._pool is None or variants is not None:
            self.close()
            self._context(variants)
            self._pool = multiprocessing.get_context("fork").Pool(self.nproc)
        return self._pool.map(_task, jobs, chunksize=1)

    def close(self):
        if self._pool is not None:
            self._pool.close()
            self._pool.join()
            self._pool = None

    # ---- survey -----------------------------------------------------------

    def survey(self, variants):
        """The Part 1 rerun: a ChannelSurvey over every task."""
        jobs = [(s, f, {}, None, "survey") for s, f in self.tasks]
        started = time.perf_counter()
        results = self.map(jobs, variants=variants)
        acc = bi.ChannelSurvey(
            self.nant, self.ncomp, len(self.scans), len(variants), NCOM_SURVEY
        )
        for r in results:
            acc.merge(r["acc"])
        self.close()
        return acc, {
            "wall_s": time.perf_counter() - started,
            "task_seconds": float(sum(r["seconds"] for r in results)),
        }

    # ---- passes -------------------------------------------------------------

    def layout(self, per_antenna, ncom):
        k, n2 = self.ncomp, 2 * self.nant
        size = 2 * k + (len(self.scans) * n2 if per_antenna else 0) + ncom
        return size

    def local_index(self, s, per_antenna, ncom):
        k, n2 = self.ncomp, 2 * self.nant
        idx = [np.arange(2 * k)]
        if per_antenna:
            idx.append(2 * k + s * n2 + np.arange(n2))
        if ncom:
            off = 2 * k + (len(self.scans) * n2 if per_antenna else 0)
            idx.append(off + np.arange(ncom))
        return np.concatenate(idx)

    def run_pass(self, state, gains, mode="fit"):
        """One pass at `state` (a, b, delta per scan, squint, ellip,
        per_antenna, ncom). Returns the summed system in the full layout."""
        per_antenna = state["per_antenna"]
        ncom = state["ncom"]
        jobs = []
        for s, f in self.tasks:
            params = {
                "a": state["a"],
                "b": state["b"],
                "delta": state["delta"][s],
                "squint": state["squint"],
                "ellip": state["ellip"],
                "per_antenna": per_antenna,
                "ncom": ncom,
            }
            jobs.append((s, f, params, None if gains is None else gains[(s, f)], mode))
        started = time.perf_counter()
        results = self.map(jobs)
        wall = time.perf_counter() - started
        size = self.layout(per_antenna, ncom)
        h = np.zeros((size, size))
        b = np.zeros(size)
        nraw = size - 2 * self.ncomp
        raw = {}
        out_gains = {}
        chi2 = 0.0
        stats = {"samples": 0, "solves": 0, "stefcal_iterations": 0}
        for r in results:
            out_gains[(r["scan"], r["block"])] = r["gains"]
            chi2 += r["chi2"]
            for k in stats:
                stats[k] += r[k]
            if mode == "fit":
                idx = self.local_index(r["scan"], per_antenna, ncom)
                h[np.ix_(idx, idx)] += r["h"]
                b[idx] += r["b"]
                if nraw:
                    raw.setdefault(r["scan"], np.zeros_like(r["raw"]))
                    raw[r["scan"]] += r["raw"]
        rec = {"wall_s": wall, "chi2": chi2, **stats}
        self.passes.append({"mode": mode, **rec})
        return {
            "h": h,
            "b": b,
            "raw": raw,
            "gains": out_gains,
            "chi2": chi2,
            "stats": rec,
        }

    def evaluate(self, state, gains, mode="eval"):
        jobs = []
        for s, f in self.tasks:
            params = {
                "a": state["a"],
                "b": state["b"],
                "delta": state["delta"][s],
                "squint": state["squint"],
                "ellip": state["ellip"],
            }
            jobs.append((s, f, params, gains[(s, f)], mode))
        return self.map(jobs)


def initial_state(problem, per_antenna, ncom):
    k, nant = problem.ncomp, problem.nant
    return {
        "a": np.zeros(k),
        "b": np.zeros(k),
        "delta": [np.zeros((nant, 2)) for _ in problem.scans],
        "squint": np.zeros(2),
        "ellip": 0.0,
        "per_antenna": per_antenna,
        "ncom": ncom,
    }


def _zero_sum_basis(n):
    """Orthonormal basis (n x (n - 1)) of the zero-sum subspace."""
    if n < 2:
        return np.zeros((n, 0))
    u, _s, _ = np.linalg.svd(np.eye(n) - np.full((n, n), 1.0 / n))
    return u[:, : n - 1]


def sky_profiled(h, ncomp2):
    """theta-theta information with the sky (first ncomp2 rows) profiled."""
    hs = h[:ncomp2, :ncomp2]
    st = h[:ncomp2, ncomp2:]
    return h[ncomp2:, ncomp2:] - st.T @ bi.pinv_psd(hs) @ st


def select_directions(problem, first, active, candidates):
    """R's selection from its first pass (full layout with per-antenna and
    NCOM_FIT common columns). `active[s]` (N,) bool: antennas with training
    data in scan s. `candidates`: set of family names among "antenna",
    "interval_common", "squint", "ellipticity". Returns the design (theta
    -> free) and the records."""
    k2 = 2 * problem.ncomp
    nant, nscan = problem.nant, len(problem.scans)
    n2 = 2 * nant
    nt = nscan * n2 + NCOM_FIT
    f_both = sky_profiled(first["h"], k2)
    raw_diag = np.zeros(nt)
    raw_blocks = {}
    for s, m in first["raw"].items():
        raw_diag[s * n2 : (s + 1) * n2] += np.diag(m)[:n2]
        raw_diag[nscan * n2 :] += np.diag(m)[n2:]
        raw_blocks[s] = m[:n2, :n2]
    records = {"antenna": [], "common": []}
    columns = []
    priors = []
    # per-antenna pointing: family-marginal (zero-mean over active antennas)
    for s in range(nscan):
        act = np.flatnonzero(active[s])
        if len(act) < 2:
            continue
        idx = np.r_[s * n2 + act, s * n2 + nant + act]
        groups = (np.arange(len(act)), np.arange(len(act), 2 * len(act)))
        marg = bi.family_marginal(f_both, idx, groups)
        for j in range(2):
            chosen = []
            for i, p in enumerate(act):
                col = s * n2 + j * nant + p
                fr, fp = raw_diag[col], f_both[col, col]
                rho = math.sqrt(max(fp, 0) / fr) if fr > 0 else 0.0
                sig = float(marg[j * len(act) + i])
                ok = (
                    "antenna" in candidates
                    and sig <= bi.SIGMA_ARCMIN
                    and rho >= bi.RHO_MIN
                )
                records["antenna"].append(
                    {
                        "scan": s,
                        "antenna": int(p),
                        "axis": j,
                        "sigma_family_marginal": sig,
                        "sigma_conditional": float(1 / math.sqrt(fp))
                        if fp > 0
                        else math.inf,
                        "rho": rho,
                        "selected": bool(ok),
                    }
                )
                if ok:
                    chosen.append(p)
            basis = _zero_sum_basis(len(chosen))
            for v in basis.T:
                col = np.zeros(nt)
                col[s * n2 + j * nant + np.asarray(chosen, int)] = v
                columns.append(col)
                priors.append(PRIOR_ARCMIN)
    # common family: interval-common pointing per scan, squint, ellipticity
    vecs, names = [], []
    for s in range(nscan):
        act = np.flatnonzero(active[s])
        for j in range(2):
            u = np.zeros(nt)
            u[s * n2 + j * nant + act] = 1.0
            vecs.append(u)
            names.append(("interval_common", s, j))
    for c, name in enumerate(("squint", "squint", "ellipticity")):
        u = np.zeros(nt)
        u[nscan * n2 + c] = 1.0
        vecs.append(u)
        names.append((name, None, c))
    v = np.array(vecs).T
    fc = v.T @ f_both @ v
    fam = [i for i, nm in enumerate(names) if nm[0] in candidates]
    marg = np.full(len(names), math.inf)
    if fam:
        sub = fc[np.ix_(fam, fam)]
        cov = bi.pinv_psd(sub)
        marg[fam] = np.sqrt(np.clip(np.diag(cov), 0, None))
    for i, (name, s, j) in enumerate(names):
        u = v[:, i]
        if name == "interval_common":
            rawv = (
                float(
                    u[s * n2 : (s + 1) * n2]
                    @ raw_blocks.get(s, np.zeros((n2, n2)))
                    @ u[s * n2 : (s + 1) * n2]
                )
                if s in raw_blocks
                else 0.0
            )
        else:
            rawv = float(raw_diag[nscan * n2 + j])
        fp = float(fc[i, i])
        rho = math.sqrt(max(fp, 0) / rawv) if rawv > 0 else 0.0
        thr = bi.SIGMA_FRACTION if name == "ellipticity" else bi.SIGMA_ARCMIN
        ok = name in candidates and marg[i] <= thr and rho >= bi.RHO_MIN
        records["common"].append(
            {
                "family": name,
                "scan": s,
                "index": j,
                "sigma_family_marginal": float(marg[i]),
                "sigma_conditional": float(1 / math.sqrt(fp)) if fp > 0 else math.inf,
                "rho": rho,
                "selected": bool(ok),
            }
        )
        if ok:
            columns.append(u)
            priors.append(PRIOR_ELLIPTICITY if name == "ellipticity" else PRIOR_ARCMIN)
    design = np.array(columns).T if columns else np.zeros((nt, 0))
    return design, np.array(priors), records


def physical_design(problem, active):
    """(ii): absolute per-antenna offsets of every active antenna."""
    nant, nscan = problem.nant, len(problem.scans)
    n2 = 2 * nant
    nt = nscan * n2
    cols = []
    for s in range(nscan):
        for j in range(2):
            for p in np.flatnonzero(active[s]):
                c = np.zeros(nt)
                c[s * n2 + j * nant + p] = 1.0
                cols.append(c)
    design = np.array(cols).T if cols else np.zeros((nt, 0))
    return design, np.full(design.shape[1], PRIOR_ARCMIN)


def _apply_theta(state, problem, theta):
    nant, nscan = problem.nant, len(problem.scans)
    n2 = 2 * nant
    new = dict(state)
    if state["per_antenna"]:
        new["delta"] = [
            np.stack(
                (theta[s * n2 : s * n2 + nant], theta[s * n2 + nant : (s + 1) * n2]), 1
            )
            for s in range(nscan)
        ]
        rest = theta[nscan * n2 :]
    else:
        rest = theta
    if state["ncom"]:
        new["squint"] = np.array(rest[:2])
        new["ellip"] = float(rest[2])
    return new


def solve(problem, arm, candidates=(), log=print, max_passes=LM_MAX_PASSES):
    """Profiled Levenberg-Marquardt for one arm: "G" (gains and sky), "ii"
    (absolute per-antenna pointing of every antenna) or "R" (selected
    directions). Returns the final state, gains, design and records."""
    k = problem.ncomp
    nant = problem.nant
    per_antenna = arm in ("ii", "R")
    ncom = NCOM_FIT if arm == "R" else 0
    state = initial_state(problem, per_antenna, ncom)
    started = time.perf_counter()
    first = problem.run_pass(state, None, "fit")
    # active antennas per scan: training samples present
    active = []
    for s, sc in enumerate(problem.scans):
        cnt = np.bincount(sc["a1"][sc["train"].any(axis=(1, 2))], minlength=nant)
        cnt += np.bincount(sc["a2"][sc["train"].any(axis=(1, 2))], minlength=nant)
        active.append(cnt > 0)
    records = {}
    if arm == "G":
        design = np.zeros((0, 0))
        priors = np.zeros(0)
    elif arm == "ii":
        design, priors = physical_design(problem, active)
    else:
        design, priors, records = select_directions(
            problem, first, active, set(candidates)
        )
    nt_full = first["h"].shape[0] - 2 * k
    gauge = int(np.argmax(problem.sky.get("gauge_flux", np.ones(k))))
    sky_keep = np.r_[np.delete(np.arange(k), gauge), k + np.delete(np.arange(k), gauge)]
    nsky = len(sky_keep)
    nfree = nsky + design.shape[1]
    lmat = np.zeros((2 * k + nt_full, nfree))
    lmat[sky_keep, np.arange(nsky)] = 1.0
    if design.shape[1]:
        lmat[2 * k :, nsky:] = design
    pdiag = (
        np.r_[np.zeros(nsky), 1.0 / priors**2] if design.shape[1] else np.zeros(nsky)
    )
    phi = np.zeros(design.shape[1])
    sky_a, sky_b = np.zeros(k), np.zeros(k)
    current = first
    obj = current["chi2"]
    lam = LM_LAMBDA0
    passes = 1
    accepted = 0
    rejected = 0
    history = [{"pass": 1, "objective": obj, "accepted": True, "lambda": None}]
    theta_full = np.zeros(nt_full)
    while passes < max_passes:
        h = lmat.T @ current["h"] @ lmat
        bvec = lmat.T @ current["b"]
        hp = h + np.diag(pdiag)
        grad = bvec - pdiag * np.r_[np.zeros(nsky), phi]
        damp = hp + lam * np.diag(np.diag(hp))
        try:
            step = np.linalg.solve(damp, grad)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(damp, grad, rcond=None)[0]
        full = lmat @ step
        t_a = sky_a + full[:k]
        t_b = sky_b + full[k : 2 * k]
        t_phi = phi + step[nsky:]
        t_theta = design @ t_phi if design.shape[1] else np.zeros(nt_full)
        trial = _apply_theta({**state, "a": t_a, "b": t_b}, problem, t_theta)
        res = problem.run_pass(trial, current["gains"], "fit")
        passes += 1
        t_obj = (
            res["chi2"] + float(np.sum((t_phi / priors) ** 2))
            if len(phi)
            else res["chi2"]
        )
        if t_obj < obj:
            rel = (obj - t_obj) / max(abs(obj), 1e-300)
            state, current, obj = trial, res, t_obj
            sky_a, sky_b, phi, theta_full = t_a, t_b, t_phi, t_theta
            accepted += 1
            history.append(
                {
                    "pass": passes,
                    "objective": obj,
                    "accepted": True,
                    "lambda": lam,
                    "relative_decrease": rel,
                }
            )
            log(
                f"{arm} pass {passes}: accepted, objective {obj:.10g}, rel {rel:.3g}, lambda {lam:.1g}"
            )
            lam = lam / 10
            if rel <= LM_REL_STOP:
                break
        else:
            rejected += 1
            history.append(
                {"pass": passes, "objective": t_obj, "accepted": False, "lambda": lam}
            )
            log(
                f"{arm} pass {passes}: rejected, objective {t_obj:.10g}, lambda {lam:.1g}"
            )
            lam = lam * 10
            if lam > LM_LAMBDA_MAX:
                break
    wall = time.perf_counter() - started
    return {
        "arm": arm,
        "state": state,
        "gains": current["gains"],
        "theta_full": theta_full,
        "phi": phi,
        "design": design,
        "active": active,
        "selection": records,
        "objective": obj,
        "chi2": current["chi2"],
        "passes": passes,
        "accepted": accepted,
        "rejected": rejected,
        "history": history,
        "solver_wall_s": wall,
        "free_parameters": int(nfree),
        "free_beam_parameters": int(design.shape[1]),
        "solves": int(sum(p["solves"] for p in problem.passes[-passes:])),
        "stefcal_iterations": int(
            sum(p["stefcal_iterations"] for p in problem.passes[-passes:])
        ),
    }


def predictable(problem):
    """Per scan (bins, chans, 2, N) bool: antenna has training samples in
    that bin, channel and hand (test cells of antennas without are not
    predicted, for every arm alike)."""
    out = []
    for sc in problem.scans:
        nch = len(sc["freqs"])
        arr = np.zeros((len(sc["rows_by_bin"]), nch, 2, sc["nant"]), bool)
        for ti, rows in enumerate(sc["rows_by_bin"]):
            tr = sc["train"][rows]  # (n, chans, 2)
            for h in range(2):
                a1 = np.repeat(sc["a1"][rows][:, None], nch, 1)[tr[..., h]]
                a2 = np.repeat(sc["a2"][rows][:, None], nch, 1)[tr[..., h]]
                ch = np.broadcast_to(np.arange(nch), tr[..., h].shape)[tr[..., h]]
                arr[ti, ch, h, a1] = True
                arr[ti, ch, h, a2] = True
        out.append(arr)
    return out


def heldout(problem, result):
    """Per test cell the hand mean of (w / s^2) |r|^2 with the arm's final
    parameters and gains. Returns (keys, values): keys (M,) int64 cell ids
    (scan, row, channel) sorted, for cells predicted in both hands."""
    results = problem.evaluate(result["state"], result["gains"], "eval")
    maxrow = max(len(sc["a1"]) for sc in problem.scans)
    maxch = max(len(sc["freqs"]) for sc in problem.scans)
    keys, vals = [], []
    for r in results:
        if not len(r["val"]):
            continue
        idx = r["idx"]
        keys.append((r["scan"] * maxrow + idx[:, 0]) * maxch + idx[:, 1])
        vals.append(r["val"])
    keys = np.concatenate(keys)
    vals = np.concatenate(vals)
    order = np.argsort(keys, kind="stable")
    keys, vals = keys[order], vals[order]
    uniq, start, count = np.unique(keys, return_index=True, return_counts=True)
    both = count == 2
    sums = np.add.reduceat(vals, start)
    return uniq[both], 0.5 * sums[both]


def paired(values_r, values_b):
    """Delta = (mean R - mean B) / mean B and its paired SE."""
    d = values_r - values_b
    mb = float(np.mean(values_b))
    delta = float(np.mean(d) / mb)
    se = float(np.std(d, ddof=1) / math.sqrt(len(d)) / mb)
    margin = max(2 * se, 1e-4)
    call = "better" if delta < -margin else ("worse" if delta > margin else "within")
    return {
        "delta": delta,
        "se": se,
        "margin": margin,
        "call": call,
        "cells": len(d),
    }


# --------------------------------------------------------------------------
# The raster (fixture) fit: B1-1's data type


def raster_amplitude(grad, freq, pos_deg):
    """Stokes I amplitude 1/2 (|E_HH| + |E_VV|) and its gradient per degree
    of a `bi.HolographyGradient`-like sampler at positions (n, 2) degrees."""
    e, ex, ey = grad(pos_deg[:, 0], pos_deg[:, 1], freq)
    amp = np.zeros(len(pos_deg))
    g = np.zeros((len(pos_deg), 2))
    for h in range(2):
        v = e[:, h, h]
        a = np.abs(v)
        amp += 0.5 * a
        safe = np.where(a > 0, a, 1.0)
        g[:, 0] += 0.5 * np.real(np.conj(v) * ex[:, h, h]) / safe
        g[:, 1] += 0.5 * np.real(np.conj(v) * ey[:, h, h]) / safe
    return amp, g


def fit_raster(x_scan, y, std, freqs, grad, select, prior_arcmin=PRIOR_ARCMIN):
    """Fit one antenna's gain amplitudes y[chunk, scan] (sigma std) at the
    commanded positions x_scan (scan, 2) degrees as height_chunk x amplitude
    (x - offset). `select`: R's rule (an axis is fitted only if its
    marginal sigma, heights profiled, <= 0.3' and rho >= 0.01 at zero
    offset); else (ii) (both axes). Returns offsets (arcmin), formal sigma,
    the selection record and the number of model evaluations."""
    ok = np.isfinite(y) & np.isfinite(std) & (std > 0)
    chunks = np.flatnonzero(ok.all(axis=1))
    if not len(chunks):
        return {
            "offset": np.full(2, np.nan),
            "sigma": np.full(2, np.nan),
            "selected": [False, False],
            "evaluations": 0,
        }
    yy, ss = y[chunks], std[chunks]
    ff = np.asarray(freqs)[chunks]
    nfev = [0]

    def model(off):
        nfev[0] += 1
        pos = x_scan - np.asarray(off) / 60.0
        amps, grads = [], []
        for f in ff:
            a, g = raster_amplitude(grad, f, pos)
            amps.append(a)
            grads.append(g)
        return np.array(amps), np.array(grads)

    a0, g0 = model(np.zeros(2))
    w = 1.0 / ss**2
    h0 = np.sum(w * yy * a0, axis=1) / np.sum(w * a0 * a0, axis=1)
    # Fisher at zero offset (heights h0)
    jd = -(h0[:, None, None] * g0) / 60.0  # (chunk, scan, 2) per arcmin
    jdw = jd / ss[..., None]
    jhw = a0 / ss  # per chunk column
    f_dd = np.einsum("csi,csj->ij", jdw, jdw)
    f_dh = np.einsum("csi,cs->ic", jdw, jhw)
    f_hh = np.sum(jhw**2, axis=1)
    f_prof = f_dd - (f_dh / f_hh) @ f_dh.T
    cond = np.full(2, math.inf)
    rho = np.zeros(2)
    for j in range(2):
        if f_prof[j, j] > 0:
            cond[j] = 1 / math.sqrt(f_prof[j, j])
            rho[j] = math.sqrt(f_prof[j, j] / f_dd[j, j])
    try:
        marg = np.sqrt(np.clip(np.diag(np.linalg.inv(f_prof)), 0, None))
    except np.linalg.LinAlgError:
        marg = np.full(2, math.inf)
    if select:
        chosen = [
            bool(marg[j] <= bi.SIGMA_ARCMIN and rho[j] >= bi.RHO_MIN) for j in range(2)
        ]
    else:
        chosen = [True, True]
    free = [j for j in range(2) if chosen[j]]
    nch = len(chunks)

    def unpack(p):
        off = np.zeros(2)
        off[free] = p[: len(free)]
        return off, p[len(free) :]

    def residual(p):
        off, hts = unpack(p)
        a, _ = model(off)
        r = ((yy - hts[:, None] * a) / ss).ravel()
        return np.r_[r, off[free] / prior_arcmin]

    def jacobian(p):
        off, hts = unpack(p)
        a, g = model(off)
        jac = np.zeros((nch * yy.shape[1] + len(free), len(p)))
        for i, j in enumerate(free):
            jac[: nch * yy.shape[1], i] = (
                (hts[:, None] * g[..., j] / 60.0) / ss
            ).ravel()
            jac[nch * yy.shape[1] + i, i] = 1.0 / prior_arcmin
        for c in range(nch):
            col = np.zeros_like(yy)
            col[c] = -a[c] / ss[c]
            jac[: nch * yy.shape[1], len(free) + c] = col.ravel()
        return jac

    p0 = np.r_[np.zeros(len(free)), h0]
    fit = optimize.least_squares(
        residual, p0, jac=jacobian, method="lm", xtol=1e-12, ftol=1e-12
    )
    off, _ = unpack(fit.x)
    sig = np.full(2, np.nan)
    try:
        cov = np.linalg.inv(fit.jac.T @ fit.jac)
        for i, j in enumerate(free):
            sig[j] = math.sqrt(cov[i, i])
    except np.linalg.LinAlgError:
        pass
    return {
        "offset": off,
        "sigma": sig,
        "selected": chosen,
        "sigma_marginal_at_zero": marg,
        "sigma_conditional_at_zero": cond,
        "rho_at_zero": rho,
        "chunks": int(nch),
        "evaluations": int(nfev[0]),
        "success": bool(fit.success),
    }


__all__ = [
    "AntennaBeams",
    "Problem",
    "ScaledGaussianBeams",
    "ToyBeams",
    "beam_terms",
    "fit_raster",
    "heldout",
    "pair_terms",
    "paired",
    "predictable",
    "prepare_scan",
    "raster_amplitude",
    "sample_columns",
    "sample_stack",
    "select_directions",
    "solve",
    "split_cells",
    "stefcal_warm",
]
