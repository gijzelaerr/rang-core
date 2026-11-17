# SPDX-License-Identifier: GPL-3.0-or-later
"""Implicit gradient of fixed-support gain TV with respect to cell weights.

The JAX reference path of research/f1-tv-flagger.md, section 3. The Rust solver
gives the fixed point `g*`. With `F = grad chi2` the stationarity per interval,
`H = dF/dg` the exact Hessian (matrix-free, a jvp of the grad) and `L` the polar
gauge TV on a fixed edge support:

    lambda = pinv(H) dL/dg           (batched MINRES, one system per interval)
    s_c = dL/da_c = -lambda . dF/da_c

`s_c` is positive where down-weighting the cell lowers TV. Gains are real arrays
`(ntime, nfreq, nant, 8)`: XX, XY, YX, YY, real then imaginary. Set
`XLA_FLAGS=--xla_force_host_platform_device_count=N` before importing JAX to run
the chunks of cells on N threads.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial

import jax
import jax.numpy as jnp
import numpy as np

CHUNK = 1 << 18


def enable_x64():
    jax.config.update("jax_enable_x64", True)


def to_real(gains):
    """`(..., 2, 2)` complex gains as `(..., 8)` reals."""
    gains = np.asarray(gains, np.complex128)
    flat = gains.reshape(*gains.shape[:-2], 4)
    return np.stack([flat.real, flat.imag], axis=-1).reshape(*gains.shape[:-2], 8)


def to_complex(x):
    return (x[..., 0::2] + 1j * x[..., 1::2]).reshape(*x.shape[:-1], 2, 2)


def _hermitian(g):
    return jnp.conj(jnp.swapaxes(g, -1, -2))


def _residual(x, cell):
    interval_t, interval_f, p, q, data, model, _ = cell
    g = to_complex(x)
    return data - g[interval_t, interval_f, p] @ model @ _hermitian(
        g[interval_t, interval_f, q]
    )


def _chi2(x, cell):
    r = _residual(x, cell)
    return jnp.sum(cell[6] * (r.real**2 + r.imag**2))


_grad = jax.jit(jax.grad(_chi2))


@jax.jit
def _hvp(x, v, cell):
    return jax.jvp(lambda y: jax.grad(_chi2)(y, cell), (x,), (v,))[1]


@jax.jit
def _cell_derivative(x, lam, cell):
    """`-lam . grad_x chi2_c` per cell, and the whitened residual norm."""
    r = _residual(x, cell)

    def chi2_cell(y):
        s = _residual(y, cell)
        return jnp.sum(cell[6] * (s.real**2 + s.imag**2), axis=(-1, -2))

    derivative = jax.jvp(chi2_cell, (x,), (lam,))[1]
    return -derivative, jnp.sqrt(jnp.sum(cell[6] * (r.real**2 + r.imag**2), (-1, -2)))


@jax.jit
def _jacobi(x, cell):
    """Scalar diagonal of the Gauss-Newton block of each antenna."""
    interval_t, interval_f, p, q, _, model, weight = cell
    g = to_complex(x)
    gq = g[interval_t, interval_f, q]
    gp = g[interval_t, interval_f, p]
    a = model @ _hermitian(gq)
    b = gp @ model
    wbar = jnp.sum(weight, (-1, -2)) / 4
    out = jnp.zeros(x.shape[:3])
    out = out.at[interval_t, interval_f, p].add(
        2 * wbar * jnp.sum(jnp.abs(a) ** 2, (-1, -2))
    )
    return out.at[interval_t, interval_f, q].add(
        2 * wbar * jnp.sum(jnp.abs(b) ** 2, (-1, -2))
    )


@dataclass
class Cells:
    """Selected cells, sorted by interval, cut into equal padded chunks."""

    chunks: list
    counts: list
    rows: np.ndarray
    channels: np.ndarray
    grid: tuple
    chunk_intervals: list


def make_cells(
    data,
    model,
    weights,
    selected,
    antenna1,
    antenna2,
    time_bin,
    freq_bin,
    grid,
    gain_valid=None,
    scale=None,
    delta=None,
    chunk=CHUNK,
    devices=None,
):
    """Build chunks from `(row, chan, 4)` columns and the `(row, chan)` selection.

    `scale` multiplies the weights of the selected cells (the soft weight `a`).
    `delta` is an optional `(rows, channels, values)` overlay on DATA, where the
    values are `(n, 4)`. Cells with a flagged gain never enter.
    """
    rows, channels = np.nonzero(selected)
    p, q = antenna1[rows].astype(np.int32), antenna2[rows].astype(np.int32)
    t, f = time_bin[rows].astype(np.int32), freq_bin[channels].astype(np.int32)
    if gain_valid is not None:
        keep = gain_valid[t, f, p] & gain_valid[t, f, q]
        rows, channels, p, q, t, f = (v[keep] for v in (rows, channels, p, q, t, f))
    order = np.argsort(t.astype(np.int64) * grid[1] + f, kind="stable")
    rows, channels, p, q, t, f = (v[order] for v in (rows, channels, p, q, t, f))
    devices = devices or jax.devices("cpu")
    pieces, counts, intervals = [], [], []
    for number, start in enumerate(range(0, len(rows), chunk)):
        r, c = rows[start : start + chunk], channels[start : start + chunk]
        n = len(r)
        d = np.zeros((chunk, 4), np.complex128)
        m = np.zeros((chunk, 4), np.complex128)
        w = np.zeros((chunk, 4), np.float64)
        d[:n], m[:n], w[:n] = data[r, c], model[r, c], weights[r, c]
        if delta is not None:
            overlay = _overlay(delta, r, c, data.shape[1])
            d[:n] += overlay
        if scale is not None:
            w[:n] *= scale[r, c, None]
        padded = [
            np.resize(v[start : start + chunk], chunk) * (np.arange(chunk) < n)
            for v in (t, f, p, q)
        ]
        cell = (
            *padded,
            d.reshape(chunk, 2, 2),
            m.reshape(chunk, 2, 2),
            w.reshape(chunk, 2, 2),
        )
        device = devices[number % len(devices)]
        pieces.append(jax.device_put(cell, device))
        counts.append(n)
        intervals.append(
            np.unique(
                t[start : start + chunk].astype(np.int64) * grid[1]
                + f[start : start + chunk]
            )
        )
    return Cells(pieces, counts, rows, channels, tuple(grid), intervals)


def _overlay(delta, rows, channels, nchan):
    keys = delta[0].astype(np.int64) * nchan + delta[1]
    order = np.argsort(keys)
    keys = keys[order]
    want = rows.astype(np.int64) * nchan + channels
    where = np.searchsorted(keys, want)
    where[where == len(keys)] = 0
    out = np.zeros((len(rows), 4), np.complex128)
    if len(keys):
        hit = keys[where] == want
        out[hit] = delta[2][order[where[hit]]]
    return out


class Operator:
    """The chunked stationarity, Hessian and per-cell derivative at one `x`."""

    def __init__(self, cells, x, gain_valid):
        self.cells, self.x, self.gain_valid = cells, x, gain_valid
        self.mask = gain_valid[..., None].astype(np.float64)

    def _pool(self, function):
        devices = [next(iter(c[0].devices())) for c in self.cells.chunks]

        def one(index):
            return function(self.cells.chunks[index], devices[index])

        with ThreadPoolExecutor(max(1, len(set(devices)))) as pool:
            return list(pool.map(one, range(len(self.cells.chunks))))

    def _sum(self, function):
        total = np.zeros_like(self.x)
        for part in self._pool(function):
            total += np.asarray(part)
        return total

    def stationarity(self):
        def run(cell, device):
            return _grad(jax.device_put(self.x, device), cell)

        return self._sum(run) * self.mask

    def hessian(self, v):
        """`H v`; chunks whose intervals all have `v = 0` contribute nothing."""
        moving = np.any(v != 0, axis=(2, 3)).ravel()
        total = np.zeros_like(self.x)
        devices = [next(iter(c[0].devices())) for c in self.cells.chunks]
        wanted = [
            i for i, keys in enumerate(self.cells.chunk_intervals) if moving[keys].any()
        ]

        def one(index):
            device = devices[index]
            return _hvp(
                jax.device_put(self.x, device),
                jax.device_put(v * self.mask, device),
                self.cells.chunks[index],
            )

        with ThreadPoolExecutor(max(1, len(set(devices)))) as pool:
            for part in pool.map(one, wanted):
                total += np.asarray(part)
        return total * self.mask

    def jacobi_step(self):
        """Relative size of one scalar-Jacobi step per gain, `(nt, nf, na)`."""

        def run(cell, device):
            return _jacobi(jax.device_put(self.x, device), cell)

        diagonal = np.zeros(self.x.shape[:3])
        for part in self._pool(run):
            diagonal += np.asarray(part)
        stationarity = np.linalg.norm(self.stationarity(), axis=-1)
        norm = np.linalg.norm(self.x, axis=-1)
        step = stationarity / np.maximum(diagonal, 1e-300) / np.maximum(norm, 1e-300)
        return np.where(self.gain_valid, step, 0.0)

    def cell_saliency(self, lam):
        """`(s_c, whitened residual norm)` in the order of `cells.rows`."""

        def run(cell, device):
            return _cell_derivative(
                jax.device_put(self.x, device),
                jax.device_put(lam * self.mask, device),
                cell,
            )

        n = len(self.cells.rows)
        s, amplitude = np.empty(n), np.empty(n)
        start = 0
        for count, part in zip(self.cells.counts, self._pool(run)):
            s[start : start + count] = np.asarray(part[0])[:count]
            amplitude[start : start + count] = np.asarray(part[1])[:count]
            start += count
        return s, amplitude


def _dot(a, b):
    return np.sum(a * b, axis=(-1, -2))


def minres(operator, b, tolerance=1e-7, iterations=200, check=5):
    """MINRES on the block-diagonal Hessian, one system per interval.

    Returns `lam`, the true relative residual per interval and the iterations.
    Every `check` iterations the true residual is measured and the best iterate
    kept. An interval stops when it reaches `tolerance` or stops improving: with a
    right-hand side outside the range of `H` (underdetermined bins, or a gauge
    the polar TV does not fix) the recurrence would otherwise diverge. The caller
    excludes such intervals on the returned residual.
    """
    shape = b.shape[:2]
    x = np.zeros_like(b)
    r1, r2, y = b.copy(), b.copy(), b.copy()
    beta1 = np.sqrt(_dot(b, b))
    active = beta1 > 0
    beta = np.where(active, beta1, 1.0)
    oldb = np.ones(shape)
    dbar, epsln = np.zeros(shape), np.zeros(shape)
    cs, sn = -np.ones(shape), np.zeros(shape)
    phibar = beta1.copy()
    w, w2 = np.zeros_like(b), np.zeros_like(b)
    best, best_residual = x.copy(), np.where(active, 1.0, 0.0)
    stale = np.zeros(shape, int)
    used = 0

    def true_residual(z):
        residual = operator.hessian(z) - b
        return np.divide(
            np.sqrt(_dot(residual, residual)),
            beta1,
            out=np.zeros(shape),
            where=beta1 > 0,
        )

    for used in range(1, iterations + 1):
        s = np.where(active, 1 / beta, 0.0)[..., None, None]
        v = s * y
        y = operator.hessian(v)
        if used >= 2:
            y = y - np.where(active, beta / oldb, 0.0)[..., None, None] * r1
        alfa = _dot(v, y)
        y = y - (alfa / beta)[..., None, None] * r2
        r1, r2 = r2, y
        oldb, beta_new = beta, np.sqrt(np.maximum(_dot(y, y), 0.0))
        oldeps = epsln
        delta = cs * dbar + sn * alfa
        gbar = sn * dbar - cs * alfa
        epsln = sn * beta_new
        dbar = -cs * beta_new
        gamma = np.maximum(np.hypot(gbar, beta_new), 1e-300)
        cs, sn = gbar / gamma, beta_new / gamma
        phi = cs * phibar
        phibar = sn * phibar
        w1, w2 = w2, w
        w = (v - oldeps[..., None, None] * w1 - delta[..., None, None] * w2) * (
            (1 / gamma)[..., None, None]
        )
        x = x + np.where(active, phi, 0.0)[..., None, None] * w
        estimate = np.divide(phibar, beta1, out=np.zeros(shape), where=beta1 > 0)
        ended = (estimate <= tolerance) | (beta_new <= 1e-14 * beta1)
        if used % check == 0 or (active & ended).any():
            measured = true_residual(x * active[..., None, None])
            improved = active & (measured < best_residual)
            best[improved] = x[improved]
            best_residual[improved] = measured[improved]
            stale = np.where(improved, 0, stale + 1)
            active = active & ~ended & (measured > tolerance) & (stale < 2)
        beta = np.where(active, beta_new, 1.0)
        if not active.any():
            break
    return best, true_residual(best), used


def _cell_chi2(y, data, model, weight):
    g = to_complex(y.reshape(2, 8))
    r = data - g[0] @ model @ jnp.conj(g[1]).T
    return jnp.sum(weight * (r.real**2 + r.imag**2))


@partial(jax.jit, static_argnames="segments")
def _baseline_blocks(x, cell, segment, segments):
    """The exact 16 x 16 Hessian of each (interval, baseline), summed over cells."""
    interval_t, interval_f, p, q, data, model, weight = cell
    y = jnp.concatenate(
        [x[interval_t, interval_f, p], x[interval_t, interval_f, q]], axis=-1
    )
    blocks = jax.vmap(jax.hessian(_cell_chi2))(y, data, model, weight)
    return jax.ops.segment_sum(blocks, segment, segments)


class DenseAdjoint:
    """`H` assembled per interval and its pseudo-inverse.

    The same exact Hessian as the matrix-free `Operator.hessian` (Amendment 4 of
    research/f1-tv-flagger.md). Interval dimension: 8 reals per antenna.
    """

    def __init__(self, cells, x, active=None, rcond=1e-10, threads=4):
        nt, nf = cells.grid
        self.grid, self.rcond = (nt, nf), rcond
        nant = x.shape[2]
        n = nant * 8
        present = np.unique(np.concatenate(cells.chunk_intervals))
        if active is not None:
            present = present[active.ravel()[present]]
        self.keys = present
        where = np.full(nt * nf, -1)
        where[present] = np.arange(len(present))
        self.hessian = np.zeros((len(present), n, n))
        devices = [next(iter(c[0].devices())) for c in cells.chunks]
        offsets = np.arange(8)

        def blocks(index):
            cell = cells.chunks[index]
            count = cells.counts[index]
            t = np.asarray(cell[0])[:count].astype(np.int64)
            f = np.asarray(cell[1])[:count].astype(np.int64)
            p = np.asarray(cell[2])[:count].astype(np.int64)
            q = np.asarray(cell[3])[:count].astype(np.int64)
            key = (t * nf + f) * nant**2 + p * nant + q
            unique, inverse = np.unique(key, return_inverse=True)
            size = len(cell[0])
            segment = np.zeros(size, np.int32)
            segment[:count] = inverse
            # The zero-weight padding adds nothing to segment 0.
            segments = 1 << int(np.ceil(np.log2(max(len(unique), 2))))
            part = _baseline_blocks(
                jax.device_put(x, devices[index]), cell, segment, segments
            )
            return unique, np.asarray(part)[: len(unique)]

        with ThreadPoolExecutor(max(1, len(set(devices)))) as pool:
            for unique, part in pool.map(blocks, range(len(cells.chunks))):
                pair = unique % nant**2
                interval = where[unique // nant**2]
                keep = interval >= 0
                p, q = pair[keep] // nant, pair[keep] % nant
                index = np.concatenate(
                    [p[:, None] * 8 + offsets, q[:, None] * 8 + offsets], axis=1
                )
                np.add.at(
                    self.hessian,
                    (
                        interval[keep][:, None, None],
                        index[:, :, None],
                        index[:, None, :],
                    ),
                    part[keep],
                )
        self.inverse = np.empty_like(self.hessian)

        def invert(i):
            h = self.hessian[i]
            values, vectors = np.linalg.eigh((h + h.T) / 2)
            cut = rcond * np.abs(values).max() if len(values) else 0
            use = np.abs(values) > max(cut, 1e-300)
            self.inverse[i] = (vectors[:, use] / values[use]) @ vectors[:, use].T

        with ThreadPoolExecutor(threads) as pool:
            list(pool.map(invert, range(len(present))))

    def solve(self, b):
        """`(lam, relative residual)`, both on the grid; other intervals are 0."""
        nt, nf = self.grid
        flat = b.reshape(nt * nf, -1)[self.keys]
        solved = (self.inverse @ flat[..., None])[..., 0]
        residual = (self.hessian @ solved[..., None])[..., 0] - flat
        norm = np.linalg.norm(flat, axis=-1)
        relative = np.divide(
            np.linalg.norm(residual, axis=-1),
            norm,
            out=np.zeros(len(norm)),
            where=norm > 0,
        )
        lam = np.zeros((nt * nf, b.shape[2] * 8))
        lam[self.keys] = solved
        grid = np.zeros(nt * nf)
        grid[self.keys] = relative
        return lam.reshape(b.shape), grid.reshape(nt, nf)


def _sqrt2(a):
    """Closed form square root of a Hermitian positive definite 2x2 matrix."""
    det = jnp.real(a[..., 0, 0] * a[..., 1, 1] - a[..., 0, 1] * a[..., 1, 0])
    root = jnp.sqrt(jnp.maximum(det, 1e-300))
    trace = jnp.real(a[..., 0, 0] + a[..., 1, 1])
    identity = jnp.eye(2, dtype=a.dtype)
    return (a + root[..., None, None] * identity) / jnp.sqrt(trace + 2 * root)[
        ..., None, None
    ]


def polar_aligned(x, reference=0):
    """`G U^H` per interval with `U` the unitary factor of the reference gain.

    The closed form stays differentiable where the singular values coincide,
    which the SVD does not (research/f1-tv-flagger.md, section 3).
    """
    g = to_complex(x)
    ref = g[:, :, reference]
    h = _sqrt2(_hermitian(ref) @ ref)
    u = ref @ jnp.linalg.inv(h)
    return g @ _hermitian(u)[:, :, None]


def _edge_norm(difference):
    s = jnp.sum(jnp.abs(difference) ** 2, axis=(-1, -2))
    positive = s > 0
    return jnp.where(positive, jnp.sqrt(jnp.where(positive, s, 1.0)), 0.0)


@dataclass
class Support:
    """Fixed edge support, axis weights and scale of the unit-weight solve."""

    time: np.ndarray
    freq: np.ndarray
    time_weight: np.ndarray
    freq_weight: np.ndarray
    scale: float
    norm: float = 1.0


def tv_value(x, support, power=1):
    """Fixed-support TV of the polar-aligned gains (`power=2`: squared edges)."""
    g = polar_aligned(x) / support.scale
    time = _edge_norm(g[1:] - g[:-1]) * support.time_weight[:, None, None]
    freq = _edge_norm(g[:, 1:] - g[:, :-1]) * support.freq_weight[None, :, None]
    total = jnp.sum(support.time * time**power) / max(1, int(support.time.sum()))
    total += jnp.sum(support.freq * freq**power) / max(1, int(support.freq.sum()))
    return total / support.norm


def _tv_value_static(x, tm, fm, tw, fw, scale, norm, power, nt_count, nf_count):
    g = polar_aligned(x) / scale
    time = _edge_norm(g[1:] - g[:-1]) * tw[:, None, None]
    freq = _edge_norm(g[:, 1:] - g[:, :-1]) * fw[None, :, None]
    total = jnp.sum(tm * time**power) / nt_count
    total += jnp.sum(fm * freq**power) / nf_count
    return total / norm


_tv_jit = jax.jit(_tv_value_static, static_argnames=("power",))
_tv_grad_jit = jax.jit(jax.grad(_tv_value_static), static_argnames=("power",))


def _support_args(support):
    return (
        jnp.asarray(support.time),
        jnp.asarray(support.freq),
        jnp.asarray(support.time_weight),
        jnp.asarray(support.freq_weight),
        support.scale,
        support.norm,
    )


def tv(x, support, power=1):
    return float(
        _tv_jit(
            jnp.asarray(x),
            *_support_args(support),
            power=power,
            nt_count=max(1, int(support.time.sum())),
            nf_count=max(1, int(support.freq.sum())),
        )
    )


def tv_gradient(x, support, power=1):
    return np.asarray(
        _tv_grad_jit(
            jnp.asarray(x),
            *_support_args(support),
            power=power,
            nt_count=max(1, int(support.time.sum())),
            nf_count=max(1, int(support.freq.sum())),
        )
    )


def sanitize(gains, gain_flags, reference=0):
    """`(x, valid)`: flagged or nonfinite gains become identity and are invalid.

    An interval whose reference gain is invalid or singular has no gauge, so
    every gain of it is invalid for TV, as in `core_policy.polar_gauge`.
    """
    gains = np.array(gains, np.complex128)
    valid = (np.asarray(gain_flags) == 0) & np.isfinite(gains).all(axis=(-1, -2))
    gains[~valid] = np.eye(2)
    singular = np.linalg.svd(gains[:, :, reference], compute_uv=False)
    ok = valid[:, :, reference] & (
        singular[..., -1] > 1e-8 * np.maximum(singular[..., 0], 1e-30)
    )
    gains[~ok] = np.eye(2)
    return to_real(gains), valid & ok[..., None], valid


def make_support(valid, time_weight, freq_weight, scale):
    """Edges between valid gains with a non-zero axis weight (`core_policy`)."""
    tw = np.asarray(time_weight, float)
    fw = np.asarray(freq_weight, float)
    time = valid[1:] & valid[:-1] & (tw[:, None, None] > 0)
    freq = valid[:, 1:] & valid[:, :-1] & (fw[None, :, None] > 0)
    return Support(time.astype(float), freq.astype(float), tw, fw, float(scale))
