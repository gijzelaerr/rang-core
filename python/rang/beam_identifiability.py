"""B1-2: which beam and pointing directions can the data constrain?

research/b1-2-identifiability.md freezes the protocol. This module holds:

- the analytic cubic-spline derivatives of the B1-0 holography beam
  (`spline_sample`, `HolographyGradient`) and a Gaussian toy beam for tests;
- the beam log-derivative factors of every direction per component
  (`direction_factors`): per-antenna pointing, array-common pointing,
  log-width, ellipticity and squint;
- the survey: per gain bin (time bin x channel block x hand), the normal
  blocks of [gains | sky | per-antenna pointing | common directions] are
  accumulated from the whitened per-component phase terms, the gains are
  Schur-eliminated, the reduced blocks are summed, and the sky is profiled
  in two arms (primary: ln S0 and alpha per component; strict: a flux per
  component per channel block) (`Survey`);
- the per-direction measures (conditional sigma, span fraction rho,
  family-marginal sigma, anchored response) and the frozen decision rule
  (`measures_from`, `verdicts`);
- the ESO137 field model (`field_model`): StefCal-form diagonal gains,
  core-gridder images and Hogbom CLEAN, three frozen rounds.

The dense Jacobian is never built. Every Gram block is a sum over samples
of Re(conj(a_i) b_i) in the whitened metric; the generalised Schur
complement with pseudo-inverses is exact for Gram matrices.
"""

import math

import numpy as np
from scipy import sparse

from . import beam_holography, measures

LIGHTSPEED = 299_792_458.0
ARCMIN_DEG = 1.0 / 60.0
COMMON = (
    "pointing_x",
    "pointing_y",
    "log_width",
    "ellipticity",
    "squint_x",
    "squint_y",
)
COMMON_UNIT = ("arcmin", "arcmin", "fraction", "fraction", "arcmin", "arcmin")
# Frozen thresholds (research/b1-2-identifiability.md, decision rule).
SIGMA_ARCMIN = 0.3
SIGMA_FRACTION = 0.005
RHO_MIN = 0.01
IB_FLOOR = 0.01
CUTOFF = 1e-10
DAMPING = 1e-6
CHI2_MEDIAN = 0.454936423119572
GRID = (2, 32)


# --------------------------------------------------------------------------
# Spline derivatives of the B1-0 product


def _kernel(t, order):
    """Cubic B-spline (order 0) or its derivative (order 1) at offsets t."""
    a = np.abs(t)
    if order == 0:
        inner = 2.0 / 3.0 - a * a + 0.5 * a**3
        outer = (2.0 - a) ** 3 / 6.0
        return np.where(a < 1, inner, np.where(a < 2, outer, 0.0))
    if order == 1:
        inner = -2.0 * t + 1.5 * t * a
        outer = -0.5 * np.sign(t) * (2.0 - a) ** 2
        return np.where(a < 1, inner, np.where(a < 2, outer, 0.0))
    raise ValueError("order 0 or 1")


def spline_sample(coeffs, rows, cols, order=(0, 0)):
    """Sum of c[..., i, j] B(rows - i) B(cols - j) over the 4 x 4 taps: the
    value (order (0, 0)) or a derivative of `ndimage.map_coordinates(order=3,
    prefilter=False)` on prefiltered coefficients, at interior points.
    coeffs (..., ny, nx); rows, cols (n,). Returns (..., n)."""
    rows = np.asarray(rows, float)
    cols = np.asarray(cols, float)
    ny, nx = coeffs.shape[-2:]
    r0 = np.floor(rows).astype(int) - 1
    c0 = np.floor(cols).astype(int) - 1
    if r0.min(initial=1) < 0 or c0.min(initial=1) < 0:
        raise ValueError("spline taps outside the grid")
    if (r0.max(initial=0) + 3 >= ny) or (c0.max(initial=0) + 3 >= nx):
        raise ValueError("spline taps outside the grid")
    out = np.zeros(coeffs.shape[:-2] + rows.shape)
    for a in range(4):
        wr = _kernel(rows - (r0 + a), order[0])
        for b in range(4):
            wc = _kernel(cols - (c0 + b), order[1])
            out += coeffs[..., r0 + a, c0 + b] * (wr * wc)
    return out


class HolographyGradient:
    """Normalised Jones and its antenna-frame gradient (per degree) from the
    frozen B1-0 product: cubic spline in space with analytic derivatives,
    linear in frequency, normalised so I_b(0) = 1 (the B1-0 rule)."""

    name = "holography"

    def __init__(self, beam, antenna="array_average"):
        self.beam = beam
        self.antenna = antenna

    def __call__(self, x_deg, y_deg, freq_hz):
        beam = self.beam
        x = np.asarray(x_deg, float).ravel()
        y = np.asarray(y_deg, float).ravel()
        rows, cols = beam.pixel_coordinates(x, y)
        low, high, weight = beam.bracket(self.antenna, float(freq_hz))
        norm = beam.norm(self.antenna, float(freq_hz))
        total = [np.zeros((len(x), 2, 2), complex) for _ in range(3)]
        for channel, w in ((low, 1.0 - weight), (high, weight)):
            if w == 0:
                continue
            real, imag = beam._coefficients(self.antenna, int(channel))
            for k, order in enumerate(((0, 0), (0, 1), (1, 0))):
                value = spline_sample(real, rows, cols, order) + 1j * spline_sample(
                    imag, rows, cols, order
                )
                total[k] += w * np.moveaxis(value, -1, 0)
        e, d_col, d_row = total
        step = beam_holography.PIXEL_DEG
        return e / norm, d_col / step / norm, beam.flip * d_row / step / norm


class GaussianToyBeam:
    """Diagonal Gaussian voltage beam for tests: E_hh = exp(-r_h^2 / (2 s^2))
    with r_h measured from a per-hand squint offset (degrees) and an
    optional x/y width ratio; s = fwhm_v / (2 sqrt(2 ln 2)) of the voltage."""

    name = "gaussian-toy"

    def __init__(self, fwhm_deg=1.0, squint_deg=(0.0, 0.0), ratio=1.0):
        self.s = fwhm_deg / (2 * math.sqrt(2 * math.log(2)))
        self.squint = np.asarray(squint_deg, float)
        self.ratio = ratio

    def __call__(self, x_deg, y_deg, freq_hz):
        x = np.asarray(x_deg, float).ravel()
        y = np.asarray(y_deg, float).ravel()
        e = np.zeros((len(x), 2, 2), complex)
        dx = np.zeros_like(e)
        dy = np.zeros_like(e)
        for h, sign in ((0, 1.0), (1, -1.0)):
            xs = x - sign * self.squint[0] / 2
            ys = y - sign * self.squint[1] / 2
            sx, sy = self.s * self.ratio, self.s
            v = np.exp(-(xs**2) / (2 * sx**2) - ys**2 / (2 * sy**2))
            e[:, h, h] = v
            dx[:, h, h] = -xs / sx**2 * v
            dy[:, h, h] = -ys / sy**2 * v
        return e, dx, dy


# --------------------------------------------------------------------------
# Direction factors


def direction_factors(e, ex, ey, x_deg, y_deg, floor=IB_FLOOR):
    """Beam log-derivative factors per component (frozen parametrisations).

    e, ex, ey: (K, 2, 2) Jones and gradients per degree at the components'
    antenna-frame positions (x_deg, y_deg). Returns
    `gamma` (K, 2 hands, 2 axes) complex: the antenna-1 pointing factor per
    arcmin (antenna 2 takes its conjugate); `beta` (K, 2 hands, 6) real: the
    common directions in COMMON order (pointing per arcmin, log-width and
    ellipticity per unit, squint per arcmin); `ib` (K,) the Stokes I power;
    `kept` (K,) bool (ib >= floor; others get zero factors)."""
    x = np.asarray(x_deg, float)[:, None, None]
    y = np.asarray(y_deg, float)[:, None, None]
    power = np.sum(np.abs(e) ** 2, axis=-1)  # (K, 2): B_h = sum_m |E[h, m]|^2
    ib = 0.5 * power.sum(-1)
    kept = ib >= floor
    safe = np.where(power > 0, power, 1.0)

    def one_sided(d):
        return np.sum(d * np.conj(e), axis=-1) / safe  # (K, 2)

    gx = one_sided(-ex * ARCMIN_DEG)
    gy = one_sided(-ey * ARCMIN_DEG)
    width = one_sided(-(x * ex + y * ey))
    ellip = one_sided(-x * ex + y * ey)
    sq = np.array([-0.5, 0.5])[None, :]
    squint_x = one_sided(ex * ARCMIN_DEG) * sq
    squint_y = one_sided(ey * ARCMIN_DEG) * sq
    gamma = np.stack([gx, gy], axis=-1)
    beta = 2 * np.real(np.stack([gx, gy, width, ellip, squint_x, squint_y], axis=-1))
    gamma[~kept] = 0
    beta[~kept] = 0
    return {"gamma": gamma, "beta": beta, "ib": ib, "kept": kept}


def beam_positions(lm, q):
    """Antenna-frame degrees (x, y) of component direction cosines lm (K, 2)
    at parallactic angle q (rad); small-angle degrees of the SIN offsets."""
    x, y = measures.sky_to_beam(lm[:, 0], lm[:, 1], q)
    return np.degrees(x), np.degrees(y)


def factors_at(beam, lm, q, freq_hz, rotation_rad=0.0):
    x, y = beam_positions(lm, q + rotation_rad)
    e, ex, ey = beam(x, y, freq_hz)
    out = direction_factors(e, ex, ey, x, y)
    out["x_deg"], out["y_deg"] = x, y
    return out


# --------------------------------------------------------------------------
# Sky phase terms


def phase_terms(uvw, freqs, sky, rows=None):
    """K (rows, chans, comps) complex: the core predictor's per-component
    term exp(+2 pi i nu/c (u l + v m + w (n - 1))) times the Gaussian
    envelope (L1-M's direct DFT), without flux."""
    uvw = np.asarray(uvw, float) if rows is None else np.asarray(uvw, float)[rows]
    lm = sky["lm"]
    l, m = lm[:, 0], lm[:, 1]
    n1 = np.sqrt(1.0 - l * l - m * m) - 1.0
    delay = uvw[:, 0:1] * l + uvw[:, 1:2] * m + uvw[:, 2:3] * n1  # (r, K)
    nu = np.asarray(freqs, float)
    phase = (2 * np.pi / LIGHTSPEED) * delay[:, None, :] * nu[None, :, None]
    out = np.exp(1j * phase)
    gauss = sky["kind"] == 1
    if gauss.any():
        major, minor, pa = sky["gauss_shape"][gauss].T
        u, v = uvw[:, 0:1], uvw[:, 1:2]
        along = (u * np.sin(pa) + v * np.cos(pa))[:, None, :] * nu[None, :, None]
        across = (u * np.cos(pa) - v * np.sin(pa))[:, None, :] * nu[None, :, None]
        env = np.exp(
            -(np.pi**2)
            / (4 * math.log(2))
            * ((major * along / LIGHTSPEED) ** 2 + (minor * across / LIGHTSPEED) ** 2)
        )
        out[..., gauss] *= env
    return out


def spectra(sky, freqs):
    """Apparent Stokes I (comps, chans): Tigger's log-polynomial spectrum."""
    nu = np.asarray(freqs, float)[None, :]
    log = np.log(nu / sky["ref_freq"][:, None])
    coeffs = sky["coeffs"]
    exponent = sum(
        coeffs[:, k : k + 1] * log ** (k + 1) for k in range(coeffs.shape[1])
    )
    return sky["flux"][:, None] * np.exp(exponent)


# --------------------------------------------------------------------------
# Per-block normal equations


def _incidence(index, nant):
    n = len(index)
    return sparse.csr_matrix((np.ones(n), (index, np.arange(n))), shape=(nant, n))


def _pair_sum(a, b, values, nant):
    return np.bincount(a * nant + b, weights=values, minlength=nant * nant).reshape(
        nant, nant
    )


def block_normals(a1, a2, nant, z, gamma, beta, sub=None):
    """Gram matrix of one gain bin and hand in the whitened metric.

    a1, a2 (n,) antennas; z (n, K) whitened component terms (flux x phase /
    sigma); gamma (V, nsub, K, 2), beta (V, nsub, K, 6) the factors of V beam
    variants at nsub channel sub-blocks, `sub` (n,) each sample's sub-block.
    Parameter order: [eta (N) | phi (N) | sky (K) | per variant: P_x (N),
    P_y (N), common (6)]. Returns the symmetric matrix."""
    n, ncomp = z.shape
    nvar = gamma.shape[0]
    sub = np.zeros(n, int) if sub is None else np.asarray(sub)
    nsub = gamma.shape[1]
    model = z.sum(axis=1)
    i1, i2 = _incidence(a1, nant), _incidence(a2, nant)
    nb = 2 * nant + 6
    size = 2 * nant + ncomp + nvar * nb
    h = np.zeros((size, size))
    g0, s0 = 0, 2 * nant
    eta, phi, sky = slice(0, nant), slice(nant, 2 * nant), slice(s0, s0 + ncomp)
    # sky-sky
    zs = np.concatenate((z.real, z.imag))
    h[sky, sky] = zs.T @ zs
    # gains-gains
    m2 = np.abs(model) ** 2
    diag = np.bincount(a1, m2, nant) + np.bincount(a2, m2, nant)
    off = _pair_sum(a1, a2, m2, nant)
    off = off + off.T
    h[eta, eta] = np.diag(diag) + off
    h[phi, phi] = np.diag(diag) - off
    # gains-sky
    u = np.conj(model)[:, None] * z
    h[eta, sky] = i1 @ u.real + i2 @ u.real
    h[phi, sky] = i1 @ u.imag - i2 @ u.imag
    for v in range(nvar):
        base = s0 + ncomp + v * nb
        px = slice(base, base + nant)
        py = slice(base + nant, base + 2 * nant)
        pc = slice(base + 2 * nant, base + nb)
        y1 = np.zeros((n, 2), complex)
        y2 = np.zeros((n, 2), complex)
        d = np.zeros((n, 6), complex)
        for s in range(nsub):
            sel = sub == s if nsub > 1 else slice(None)
            zz = z[sel]
            y1[sel] = zz @ gamma[v, s]
            y2[sel] = zz @ np.conj(gamma[v, s])
            d[sel] = zz @ beta[v, s]
        # common blocks
        ds = np.concatenate((d.real, d.imag))
        h[pc, pc] = ds.T @ ds
        h[pc, sky] = ds.T @ zs
        uc = np.conj(model)[:, None] * d
        h[eta, pc] = i1 @ uc.real + i2 @ uc.real
        h[phi, pc] = i1 @ uc.imag - i2 @ uc.imag
        for j, pj in enumerate((px, py)):
            # pointing-sky and pointing-common
            w1 = np.conj(y1[:, j])[:, None]
            w2 = np.conj(y2[:, j])[:, None]
            h[pj, sky] = i1 @ (w1 * z).real + i2 @ (w2 * z).real
            h[pj, pc] = i1 @ (w1 * d).real + i2 @ (w2 * d).real
            # pointing-gains (rows: gain antenna, columns: pointing antenna)
            c1 = np.conj(model) * y1[:, j]
            c2 = np.conj(model) * y2[:, j]
            e_blk = np.diag(
                np.bincount(a1, c1.real, nant) + np.bincount(a2, c2.real, nant)
            )
            e_blk = (
                e_blk
                + _pair_sum(a2, a1, c1.real, nant)
                + _pair_sum(a1, a2, c2.real, nant)
            )
            f_blk = np.diag(
                np.bincount(a1, c1.imag, nant) - np.bincount(a2, c2.imag, nant)
            )
            f_blk = (
                f_blk
                - _pair_sum(a2, a1, c1.imag, nant)
                + _pair_sum(a1, a2, c2.imag, nant)
            )
            h[eta, pj] = e_blk
            h[phi, pj] = f_blk
            for k, pk in enumerate((px, py)):
                if k < j:
                    continue
                r11 = (np.conj(y1[:, j]) * y1[:, k]).real
                r22 = (np.conj(y2[:, j]) * y2[:, k]).real
                r12 = (np.conj(y1[:, j]) * y2[:, k]).real
                r21 = (np.conj(y2[:, j]) * y1[:, k]).real
                blk = np.diag(np.bincount(a1, r11, nant) + np.bincount(a2, r22, nant))
                blk = blk + _pair_sum(a1, a2, r12, nant) + _pair_sum(a2, a1, r21, nant)
                h[pj, pk] = blk
                if k != j:
                    h[pk, pj] = blk.T
        # cross-variant blocks are not needed (conditional measures)
    del g0
    upper = np.triu_indices(size, 1)
    lower = (upper[1], upper[0])
    sym = np.where(h[upper] != 0, h[upper], h[lower])
    h[upper] = sym
    h[lower] = sym
    return h


def pinv_psd(a, cutoff=CUTOFF):
    """Pseudo-inverse of a PSD matrix after diagonal equilibration; the
    eigenvalue cutoff is relative to the largest."""
    d = np.sqrt(np.clip(np.diag(a), 0, None))
    d[d == 0] = 1.0
    s = a / np.outer(d, d)
    w, v = np.linalg.eigh(s)
    keep = w > cutoff * max(w[-1], 0)
    inv = (v[:, keep] / w[keep]) @ v[:, keep].T
    return inv / np.outer(d, d)


def schur(h, eliminate, keep):
    """h[keep, keep] - h[keep, el] pinv(h[el, el]) h[el, keep]."""
    a = h[np.ix_(eliminate, eliminate)]
    x = h[np.ix_(eliminate, keep)]
    return h[np.ix_(keep, keep)] - x.T @ pinv_psd(a) @ x


def anchored_diagonal(a, x, cutoff=CUTOFF, damping=DAMPING, lam_max=None):
    """Horizontal-gauge, minimum-norm, damped gain response A^+ x with the
    native constants (cutoff and damping relative to the largest
    eigenvalue, or to `lam_max` when given)."""
    w, v = np.linalg.eigh(a)
    top = w[-1] if lam_max is None else lam_max
    keep = w > cutoff * w[-1]
    coef = (v[:, keep].T @ x) / (w[keep] + damping * top)[:, None]
    return v[:, keep] @ coef


# --------------------------------------------------------------------------
# The survey


class Survey:
    """Accumulate the gain-reduced and raw blocks over all gain bins.

    `nant` antennas, `ncomp` sky components, `nscan` pointing slots (one
    per scan), `nvar` beam variants. Blocks are kept per (scan, channel
    block, hand) with raw weights; the noise calibration kappa_{scan,hand}
    is applied at combination time (exact: each block scales by kappa)."""

    def __init__(self, nant, ncomp, nscan=1, nvar=1, anchored=True):
        self.nant, self.ncomp, self.nscan, self.nvar = nant, ncomp, nscan, nvar
        self.nb = 2 * nant + 6
        self.reduced = {}
        self.raw = {}
        self.freq = {}
        self.anchored = anchored
        self.anchor = {}
        self.blocks = 0
        self.samples = 0

    def add(self, scan, fblock, hand, freq_centre, h, samples):
        """Add one gain bin's Gram matrix `h` (from `block_normals`, summed
        over the bin's sample chunks)."""
        nant, ncomp = self.nant, self.ncomp
        gains = np.arange(2 * nant)
        rest = np.arange(2 * nant, h.shape[0])
        reduced = schur(h, gains, rest)
        key = (scan, fblock, hand)
        if key not in self.reduced:
            self.reduced[key] = np.zeros_like(reduced)
            self.raw[key] = np.zeros_like(reduced)
        self.reduced[key] += reduced
        self.raw[key] += h[np.ix_(rest, rest)]
        self.freq[fblock] = freq_centre
        self.blocks += 1
        self.samples += int(samples)
        if self.anchored:
            a = h[np.ix_(gains, gains)]
            cols = rest[ncomp:]
            delta = anchored_diagonal(a, h[np.ix_(gains, cols)])
            step = np.sqrt(delta[:nant] ** 2 + delta[nant:] ** 2).max(axis=0)
            self.anchor.setdefault((scan, hand), []).append(step)

    # ---- combination -------------------------------------------------

    def theta_size(self):
        return self.nvar * self.nscan * (2 * self.nant) + self.nvar * 6

    def theta_index(self, scan, variant):
        """Global theta indices of a block's [P (2N), C (6)] for a variant."""
        n2 = 2 * self.nant
        p0 = variant * self.nscan * n2 + scan * n2
        c0 = self.nvar * self.nscan * n2 + variant * 6
        return np.r_[np.arange(p0, p0 + n2), np.arange(c0, c0 + 6)]

    def combined(self, kappa, which="reduced"):
        """Per channel block: (sky-sky, sky-theta, theta-theta) with kappa."""
        source = self.reduced if which == "reduced" else self.raw
        nt, k = self.theta_size(), self.ncomp
        out = {}
        for (scan, fblock, hand), m in source.items():
            m = kappa[(scan, hand)] * m
            ss, st, tt = out.setdefault(
                fblock, [np.zeros((k, k)), np.zeros((k, nt)), np.zeros((nt, nt))]
            )
            ss += m[:k, :k]
            for v in range(self.nvar):
                local = np.arange(k + v * self.nb, k + (v + 1) * self.nb)
                idx = self.theta_index(scan, v)
                st[:, idx] += m[:k][:, local]
                tt[np.ix_(idx, idx)] += m[np.ix_(local, local)]
                for v2 in range(v + 1, self.nvar):
                    local2 = np.arange(k + v2 * self.nb, k + (v2 + 1) * self.nb)
                    idx2 = self.theta_index(scan, v2)
                    tt[np.ix_(idx, idx2)] += m[np.ix_(local, local2)]
                    tt[np.ix_(idx2, idx)] += m[np.ix_(local2, local)]
        return out

    def information(self, kappa, nu0):
        """theta-theta information matrices: raw (no nuisance), gains
        profiled, sky profiled (primary and strict arms), both profiled
        (primary and strict arms)."""
        out = {}
        for which in ("raw", "reduced"):
            per = self.combined(kappa, which)
            k = self.ncomp
            tt_sum = sum(v[2] for v in per.values())
            strict = np.zeros_like(tt_sum)
            nt = tt_sum.shape[0]
            big_ss = np.zeros((2 * k, 2 * k))
            big_st = np.zeros((2 * k, nt))
            for fblock, (ss, st, tt) in per.items():
                strict += tt - st.T @ pinv_psd(ss) @ st
                lf = math.log(self.freq[fblock] / nu0)
                big_ss[:k, :k] += ss
                big_ss[:k, k:] += lf * ss
                big_ss[k:, :k] += lf * ss
                big_ss[k:, k:] += lf * lf * ss
                big_st[:k] += st
                big_st[k:] += lf * st
            primary = tt_sum - big_st.T @ pinv_psd(big_ss) @ big_st
            if which == "raw":
                out["raw"] = tt_sum
                out["sky_primary"] = primary
                out["sky_strict"] = strict
            else:
                out["gains"] = tt_sum
                out["both_primary"] = primary
                out["both_strict"] = strict
        return out


# --------------------------------------------------------------------------
# Measures and verdicts


def direction_labels(nant, nscan, nvar, variants):
    labels = []
    for v in range(nvar):
        for s in range(nscan):
            for axis in ("x", "y"):
                for p in range(nant):
                    labels.append(
                        {
                            "variant": variants[v],
                            "family": "antenna",
                            "scan": s,
                            "antenna": p,
                            "direction": f"pointing_{axis}",
                            "unit": "arcmin",
                        }
                    )
    for v in range(nvar):
        for name, unit in zip(COMMON, COMMON_UNIT, strict=True):
            labels.append(
                {
                    "variant": variants[v],
                    "family": "common",
                    "direction": name,
                    "unit": unit,
                }
            )
    return labels


def threshold(label):
    return SIGMA_ARCMIN if label["unit"] == "arcmin" else SIGMA_FRACTION


def _diag_sigma(f):
    d = np.diag(f).copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(d > 0, 1.0 / np.sqrt(np.where(d > 0, d, 1.0)), np.inf), d


def family_marginal(f, idx, zero_mean_blocks=()):
    """Marginal sigma within a family (theta indices idx) with the others
    fixed; zero_mean_blocks are index groups constrained to sum to zero."""
    sub = f[np.ix_(idx, idx)]
    n = len(idx)
    basis = np.eye(n)
    for group in zero_mean_blocks:
        g = np.zeros(n)
        g[group] = 1.0 / math.sqrt(len(group))
        basis = basis - np.outer(basis @ g, g)
    u, s, _ = np.linalg.svd(basis)
    q = u[:, s > 0.5]
    reduced = q.T @ sub @ q
    cov = q @ pinv_psd(reduced) @ q.T
    with np.errstate(invalid="ignore"):
        return np.sqrt(np.clip(np.diag(cov), 0, None))


def measures_from(info, labels, nant, nscan, nvar, duration_s):
    """Per-direction measures for both sky arms, raw-weight-free."""
    raw_d = np.diag(info["raw"])
    out = {"directions": []}
    sig = {}
    for arm in ("primary", "strict"):
        sig[arm], _ = _diag_sigma(info[f"both_{arm}"])
    sig_gains, _ = _diag_sigma(info["gains"])
    sig_sky = {arm: _diag_sigma(info[f"sky_{arm}"])[0] for arm in ("primary", "strict")}
    # family-marginal (primary arm)
    f = info["both_primary"]
    marginal = np.full(len(labels), np.nan)
    n2 = 2 * nant
    for v in range(nvar):
        for s in range(nscan):
            # antennas with data only: zero-mean over the active antennas
            p0 = v * nscan * n2 + s * n2
            active = np.flatnonzero(raw_d[p0 : p0 + nant] > 0)
            if len(active) < 2:
                continue
            idx = np.r_[p0 + active, p0 + nant + active]
            na = len(active)
            groups = (np.arange(na), np.arange(na, 2 * na))
            marginal[idx] = family_marginal(f, idx, groups)
        c0 = nvar * nscan * n2 + v * 6
        idx = np.arange(c0, c0 + 6)
        marginal[idx] = family_marginal(f, idx)
    for j, label in enumerate(labels):
        rec = dict(label)
        fr = raw_d[j]
        rec["raw_information"] = float(fr)
        for arm in ("primary", "strict"):
            fp = info[f"both_{arm}"][j, j]
            rec[f"sigma_{arm}"] = float(sig[arm][j])
            rec[f"rho_{arm}"] = float(math.sqrt(max(fp, 0) / fr)) if fr > 0 else None
            fs = info[f"sky_{arm}"][j, j]
            rec[f"rho_sky_only_{arm}"] = (
                float(math.sqrt(max(fs, 0) / fr)) if fr > 0 else None
            )
            rec[f"sigma_sky_only_{arm}"] = float(sig_sky[arm][j])
        fg = info["gains"][j, j]
        rec["rho_gains_only"] = float(math.sqrt(max(fg, 0) / fr)) if fr > 0 else None
        rec["sigma_gains_only"] = float(sig_gains[j])
        rec["sigma_raw_no_nuisance"] = float(1 / math.sqrt(fr)) if fr > 0 else None
        rec["sigma_family_marginal"] = float(marginal[j])
        rec["forecast_sigma_1h"] = float(
            sig["primary"][j] * math.sqrt(duration_s / 3600)
        )
        out["directions"].append(rec)
    return out


def verdict(rec):
    t = threshold(rec)
    sigma, rho = rec["sigma_primary"], rec["rho_primary"]
    passed = bool(sigma <= t and rho is not None and rho >= RHO_MIN)
    labels = []
    if passed:
        strict_ok = rec["sigma_strict"] <= t and (rec["rho_strict"] or 0) >= RHO_MIN
        if not strict_ok:
            labels.append("needs a spectral prior")
        if not rec["sigma_family_marginal"] <= t:
            labels.append("constrainable alone only")
    return passed, labels


def summarise(directions, nant):
    """Verdict table rows: common directions one by one, per-antenna pointing
    as a family line per (variant, scan, axis)."""
    rows = []
    families = {}
    for rec in directions:
        passed, labels = verdict(rec)
        rec["constrainable"] = passed
        rec["labels"] = labels
        if rec["family"] == "common":
            rows.append(
                {
                    k: rec[k]
                    for k in (
                        "variant",
                        "direction",
                        "unit",
                        "sigma_primary",
                        "rho_primary",
                        "sigma_strict",
                        "rho_strict",
                        "sigma_family_marginal",
                        "sigma_raw_no_nuisance",
                        "forecast_sigma_1h",
                    )
                }
                | {"constrainable": passed, "labels": labels}
            )
        elif rec["raw_information"] > 0:
            key = (rec["variant"], rec["scan"], rec["direction"])
            families.setdefault(key, []).append(rec)
    for (variant, scan, direction), recs in families.items():
        sig = np.array([r["sigma_primary"] for r in recs])
        rho = np.array([r["rho_primary"] or 0.0 for r in recs])
        npass = sum(r["constrainable"] for r in recs)
        rows.append(
            {
                "variant": variant,
                "scan": scan,
                "direction": f"antenna {direction}",
                "unit": "arcmin",
                "antennas": len(recs),
                "passing": npass,
                "call": "constrainable"
                if npass == len(recs)
                else ("partly" if npass else "not"),
                "constrainable": npass > 0,
                "sigma_primary_median": float(np.median(sig)),
                "sigma_primary_min": float(sig.min()),
                "rho_primary_median": float(np.median(rho)),
                "rho_primary_max": float(rho.max()),
                "sigma_family_marginal_median": float(
                    np.nanmedian([r["sigma_family_marginal"] for r in recs])
                ),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Noise calibration


def noise_scale(data, weight, eligible, block=4096):
    """s^2 = median(z^2)/0.4549 over Re and Im of adjacent-channel-pair
    differences z = (D_{2j+1} - D_{2j}) / sqrt(1/w_{2j} + 1/w_{2j+1}).
    data, weight, eligible: (rows, chans) for one hand."""
    values = []
    nchan = data.shape[1] // 2 * 2
    for start in range(0, data.shape[0], block):
        d = data[start : start + block, :nchan]
        w = weight[start : start + block, :nchan].astype(float)
        e = eligible[start : start + block, :nchan]
        ok = e[:, 0::2] & e[:, 1::2]
        with np.errstate(divide="ignore", invalid="ignore"):
            var = 1.0 / w[:, 0::2] + 1.0 / w[:, 1::2]
            z = (d[:, 1::2] - d[:, 0::2]) / np.sqrt(var)
        z = z[ok]
        values.append(np.concatenate((z.real, z.imag)) ** 2)
    allz = np.concatenate(values)
    return {
        "s2": float(np.median(allz) / CHI2_MEDIAN),
        "pairs": int(allz.size // 2),
    }


# --------------------------------------------------------------------------
# StefCal-form diagonal gains, imaging and Hogbom CLEAN (ESO137 field model)


def stefcal(data, model, weight, a1, a2, nant, phase_only, iterations=100, tol=1e-8):
    """Diagonal gains for one hand and one solution interval: g_p minimising
    sum w |D_pq - g_p conj(g_q) M_pq|^2 by alternating least squares with
    averaging 0.5 (StefCal form). data, model, weight: (n,) samples."""
    g = np.ones(nant, complex)
    w = weight
    for it in range(iterations):
        gq = g[a2]
        gp = g[a1]
        # row (p,q): D = g_p conj(g_q) M  => for antenna p: z = conj(g_q) M
        num = np.bincount(
            a1, (w * data * np.conj(np.conj(gq) * model)).real, nant
        ) + 1j * np.bincount(a1, (w * data * np.conj(np.conj(gq) * model)).imag, nant)
        # for antenna q: conj(D) = g_q conj(g_p) conj(M)
        zq = np.conj(gp) * np.conj(model)
        num = (
            num
            + np.bincount(a2, (w * np.conj(data) * np.conj(zq)).real, nant)
            + 1j * np.bincount(a2, (w * np.conj(data) * np.conj(zq)).imag, nant)
        )
        den = np.bincount(a1, w * np.abs(gq * model) ** 2, nant) + np.bincount(
            a2, w * np.abs(gp * model) ** 2, nant
        )
        new = np.where(den > 0, num / np.where(den > 0, den, 1), g)
        if phase_only:
            new = np.where(np.abs(new) > 0, new / np.abs(np.where(new == 0, 1, new)), 1)
        new = 0.5 * (new + g)
        if phase_only:
            new = new / np.abs(new)
        change = np.max(np.abs(new - g)) / max(np.max(np.abs(g)), 1e-30)
        g = new
        if change < tol:
            return g, it + 1
    return g, iterations


def hogbom(dirty, psf, window, gain=0.1, threshold=0.0, max_iter=10000):
    """Hogbom CLEAN of `dirty` inside the centred square `window` (pixels)
    with the full-size `psf` (peak at the image centre). Returns the
    component image and the residual (window), and the iteration count."""
    h, w = dirty.shape
    cy, cx = h // 2, w // 2
    half = window // 2
    y0, x0 = cy - half, cx - half
    res = dirty[y0 : y0 + window, x0 : x0 + window].copy()
    comp = np.zeros_like(res)
    pc_y, pc_x = np.unravel_index(np.argmax(psf), psf.shape)
    peak_psf = psf[pc_y, pc_x]
    it = 0
    for it in range(max_iter):
        k = int(np.argmax(np.abs(res)))
        py, px = divmod(k, window)
        value = res[py, px]
        if abs(value) <= threshold:
            break
        flux = gain * value / peak_psf
        comp[py, px] += flux
        # psf patch aligned so that psf centre lands on (py, px)
        sy = pc_y - py
        sx = pc_x - px
        res -= flux * psf[sy : sy + window, sx : sx + window]
    return comp, res, it


__all__ = [
    "COMMON",
    "GaussianToyBeam",
    "HolographyGradient",
    "Survey",
    "block_normals",
    "direction_factors",
    "factors_at",
    "family_marginal",
    "hogbom",
    "measures_from",
    "noise_scale",
    "phase_terms",
    "pinv_psd",
    "schur",
    "spectra",
    "spline_sample",
    "stefcal",
    "summarise",
    "verdict",
]
