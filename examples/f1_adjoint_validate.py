"""Stage 1a of research/f1-tv-flagger.md: the adjoint against finite differences.

Usage: python examples/f1_adjoint_validate.py OUTPUT_DIR [--slice ARRAYS.npz]

Two problems: a synthetic 12-antenna scan and the LUNO four-station slice. All
pass bounds are those frozen in section 3 of the protocol.
"""

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault(
    "XLA_FLAGS",
    "--xla_force_host_platform_device_count=4 --xla_cpu_multi_thread_eigen=false",
)

import jax
import jax.numpy as jnp
import numpy as np
from rang import core
from rang import tvflag_adjoint as ta
from rang.core_policy import (
    axis_weights,
    fixed_support_tv,
    gain_tv,
    polar_gauge,
)

TOLERANCE = 1e-13
LOOSE = 1e-11
EPSILONS = (0.02, 0.01)
CELLS = 300
PATCHES = 30
BOUNDS = {
    "polish_max": 1e-8,
    "gauge_max": 1e-8,
    "homogeneity_max": 1e-7,
    "cell_median": 0.01,
    "cell_p95": 0.05,
    "cell_correlation": 0.999,
    "patch_median": 0.01,
    "patch_p95": 0.03,
    "unrolled_median": 0.01,
}
ADJOINT_RESIDUAL = 1e-6


def synthetic(seed=20261102, nant=12, ndump=8, nchan=128):
    rng = np.random.default_rng(seed)
    p, q = np.triu_indices(nant, 1)
    nbl = len(p)
    a1 = np.repeat(p[None], ndump, 0).ravel().astype(np.uint32)
    a2 = np.repeat(q[None], ndump, 0).ravel().astype(np.uint32)
    dump = np.repeat(np.arange(ndump), nbl)
    time_bin = (dump // 2).astype(np.uint32)
    freq_bin = (np.arange(nchan) // 32).astype(np.uint32)
    nt, nf = int(time_bin.max()) + 1, int(freq_bin.max()) + 1
    t = (np.arange(nt) + 0.5) / nt
    f = (np.arange(nf) + 0.5) / nf
    drift = rng.normal(0, 0.03, (nant, 2))
    gains = np.zeros((nt, nf, nant, 2, 2), complex)
    amplitude = 1 + rng.normal(0, 0.05, (nant, 2))
    phase = rng.uniform(-1, 1, (nant, 2))
    leak = 0.02 * (rng.normal(size=(nant, 2)) + 1j * rng.normal(size=(nant, 2)))
    for k in range(2):
        gains[..., k, k] = amplitude[:, k] * np.exp(
            1j * (phase[:, k] + drift[:, k] * (t[:, None, None] + f[None, :, None]))
        )
    gains[..., 0, 1], gains[..., 1, 0] = leak[:, 0], leak[:, 1]
    model = np.zeros((len(a1), nchan, 4), np.complex64)
    model[..., 0], model[..., 3] = 15.0, 15.0
    sigma = 0.22
    m = model.reshape(len(a1), nchan, 2, 2)
    fb = freq_bin[None].repeat(len(a1), 0)
    gp = gains[time_bin[:, None], fb, a1[:, None]]
    gq = gains[time_bin[:, None], fb, a2[:, None]]
    vis = gp @ m @ np.conj(np.swapaxes(gq, -1, -2))
    vis = vis + sigma * (rng.normal(size=vis.shape) + 1j * rng.normal(size=vis.shape))
    # A weak narrowband contaminant, so the residuals are not all noise.
    vis[:, 40:44] += 2.0 * np.exp(1j * rng.uniform(0, 6.28, (len(a1), 4, 1, 1)))
    data = vis.reshape(len(a1), nchan, 4).astype(np.complex64)
    weights = np.full(data.shape, 1 / sigma**2, np.float32)
    selected = rng.random(data.shape[:2]) > 0.05
    return {
        "name": "synthetic-12",
        "data": data,
        "model": model,
        "weights": weights,
        "selected": selected,
        "a1": a1,
        "a2": a2,
        "time_bin": time_bin,
        "freq_bin": freq_bin,
        "nant": nant,
        "time_axis": np.arange(nt, dtype=float),
        "freq_axis": np.arange(nf, dtype=float),
    }


def luno_slice(path):
    a = np.load(path)
    data = a["DATA"].astype(np.complex64)
    weights = a["WEIGHT_SPECTRUM"].astype(np.float32)
    flag = a["FLAG"].astype(bool)
    rows = a["FLAG_ROW"].astype(bool)
    unique = np.unique(a["TIME"], return_inverse=True)
    time_bin = (unique[1] // 2).astype(np.uint32)
    freq_bin = (np.arange(data.shape[1]) // 32).astype(np.uint32)
    selected = (
        ~flag.any(-1)
        & ~rows[:, None]
        & (weights > 0).all(-1)
        & (np.abs(data[..., [0, 3]]) > 0).all(-1)
    )
    nt, nf = int(time_bin.max()) + 1, int(freq_bin.max()) + 1
    return {
        "name": "luno-four-station",
        "data": data,
        "model": a["MODEL_DATA"].astype(np.complex64),
        "weights": weights,
        "selected": selected,
        "a1": a["ANTENNA1"].astype(np.uint32),
        "a2": a["ANTENNA2"].astype(np.uint32),
        "time_bin": time_bin,
        "freq_bin": freq_bin,
        "nant": int(max(a["ANTENNA1"].max(), a["ANTENNA2"].max())) + 1,
        "time_axis": np.arange(nt, dtype=float),
        "freq_axis": np.arange(nf, dtype=float),
    }


def solve(problem, weights, rows, channels, tolerance):
    """Solve the given rows and channels; bins are remapped to a dense grid."""
    tb = problem["time_bin"][rows]
    fb = problem["freq_bin"][channels]
    ut, tb = np.unique(tb, return_inverse=True)
    uf, fb = np.unique(fb, return_inverse=True)
    selected = problem["selected"][np.ix_(rows, channels)]
    flag = np.repeat(~selected[..., None], 4, axis=-1)
    solution = core.solve_complex(
        problem["data"][np.ix_(rows, channels)],
        weights[np.ix_(rows, channels)],
        flag,
        flag.all(axis=(1, 2)),
        problem["a1"][rows],
        problem["a2"][rows],
        tb.astype(np.uint32),
        fb.astype(np.uint32),
        ntime_bins=len(ut),
        nfreq_bins=len(uf),
        nant=problem["nant"],
        model=problem["model"][np.ix_(rows, channels)],
        max_iterations=5000,
        stop_criterion=tolerance,
        stop_fraction=1.0,
        options="anderson=3",
    )
    return solution


class Fixture:
    """One problem at its fixed point, with the adjoint and the saliency."""

    def __init__(self, problem):
        self.problem = problem
        p = problem
        nrow, nchan = p["data"].shape[:2]
        self.all_rows, self.all_channels = np.arange(nrow), np.arange(nchan)
        started = time.perf_counter()
        solution = solve(p, p["weights"], self.all_rows, self.all_channels, TOLERANCE)
        self.solve_seconds = time.perf_counter() - started
        self.iterations = solution.iterations
        self.converged = solution.converged_fraction
        self.raw_gains, self.flags = solution.gains, solution.flags
        self.x, self.valid, raw_valid = ta.sanitize(solution.gains, solution.flags)
        scale = float(
            np.median(np.linalg.norm(solution.gains[raw_valid], axis=(-1, -2)))
        )
        tw, fw = axis_weights(p["time_axis"]), axis_weights(p["freq_axis"])
        self.support = ta.make_support(self.valid, tw, fw, scale)
        aligned, tv_valid = polar_gauge(solution.gains, raw_valid)
        rust = gain_tv(aligned, tv_valid, p["time_axis"], p["freq_axis"], scale=scale)
        self.rust_tv = fixed_support_tv(rust["edges"], rust["edges"])
        self.jax_tv = ta.tv(self.x, self.support)
        self.support.norm = self.jax_tv
        grid = (len(p["time_axis"]), len(p["freq_axis"]))
        self.cells = ta.make_cells(
            p["data"],
            p["model"],
            p["weights"],
            p["selected"],
            p["a1"],
            p["a2"],
            p["time_bin"],
            p["freq_bin"],
            grid,
            gain_valid=self.valid,
            chunk=1 << 16,
        )
        self.operator = ta.Operator(self.cells, self.x, self.valid)
        started = time.perf_counter()
        self.gradient = ta.tv_gradient(self.x, self.support) * self.valid[..., None]
        self.lam, self.residual, self.minres_iterations = ta.minres(
            self.operator, self.gradient
        )
        self.adjoint_seconds = time.perf_counter() - started
        self.s, _ = self.operator.cell_saliency(self.lam)
        self.good_interval = self.residual <= ADJOINT_RESIDUAL
        t = p["time_bin"][self.cells.rows]
        f = p["freq_bin"][self.cells.channels]
        self.cell_good = self.good_interval[t, f]

    def loss_with(self, interval, gains, flags):
        """L with one interval replaced; None if a gain's validity changed."""
        t, f = interval
        x = self.x.copy()
        grid_flags = np.array(self.flags)
        grid_flags[t, f] = flags[0, 0]
        replaced = np.array(self.raw_gains)
        replaced[t, f] = gains[0, 0]
        new_x, valid, _ = ta.sanitize(replaced, grid_flags)
        if not np.array_equal(valid, self.valid):
            return None
        x[t, f] = new_x[t, f]
        return ta.tv(x, self.support)

    def difference(self, cells, epsilon, tolerance):
        """Central difference of L for scaling the weights of `cells` together."""
        p = self.problem
        rows, channels = cells
        t = int(p["time_bin"][rows[0]])
        f = int(p["freq_bin"][channels[0]])
        sub_rows = np.flatnonzero(p["time_bin"] == t)
        sub_channels = np.flatnonzero(p["freq_bin"] == f)
        values = []
        for sign in (1, -1):
            weights = p["weights"].copy()
            original = weights[rows, channels].copy()
            changed = (original * (1 + sign * epsilon)).astype(np.float32)
            weights[rows, channels] = changed
            solution = solve(p, weights, sub_rows, sub_channels, tolerance)
            loss = self.loss_with((t, f), solution.gains, solution.flags)
            if loss is None:
                return None
            values.append(loss)
        return (values[0] - values[1]) / (2 * epsilon)

    def richardson(self, cells):
        fine = self.difference(cells, EPSILONS[1], TOLERANCE)
        coarse = self.difference(cells, EPSILONS[0], TOLERANCE)
        loose = self.difference(cells, EPSILONS[1], LOOSE)
        if fine is None or coarse is None or loose is None:
            return None
        if abs(fine - loose) > 0.1 * abs(fine):
            return None
        return (4 * fine - coarse) / 3


def checks_static(fix):
    """Polish, gauge and homogeneity checks."""
    out = {}
    stationarity = fix.operator.stationarity()
    step, relative, _ = ta.minres(fix.operator, -stationarity)
    good = fix.good_interval
    out["stationarity_max"] = float(np.abs(stationarity).max())
    out["polish_relative_residual_median"] = float(np.median(relative[good]))
    g0 = ta.to_complex(fix.x)
    g1 = ta.to_complex(fix.x + step)
    worst = []
    for a in range(fix.problem["nant"]):
        for b in range(a + 1, fix.problem["nant"]):
            both = fix.valid[:, :, a] & fix.valid[:, :, b] & good
            if both.any():
                p0 = g0[:, :, a][both] @ np.conj(np.swapaxes(g0[:, :, b][both], -1, -2))
                p1 = g1[:, :, a][both] @ np.conj(np.swapaxes(g1[:, :, b][both], -1, -2))
                worst.append(
                    np.linalg.norm(p1 - p0, axis=(-1, -2))
                    / np.linalg.norm(p0, axis=(-1, -2))
                )
    worst = np.concatenate(worst)
    out["polish_max"] = float(worst.max())
    out["polish_median"] = float(np.median(worst))
    out["polish_intervals_excluded"] = int((~good).sum())
    # Gauge: right multiplication by exp(i e X) for the four Hermitian X.
    basis = [
        np.eye(2),
        np.array([[0, 1], [1, 0]]),
        np.array([[0, -1j], [1j, 0]]),
        np.array([[1, 0], [0, -1]]),
    ]
    ratios = []
    for t in range(fix.x.shape[0]):
        for f in range(fix.x.shape[1]):
            gradient = fix.gradient[t, f]
            norm = np.linalg.norm(gradient)
            if norm == 0:
                continue
            for x_matrix in basis:
                tangent = (
                    ta.to_real(g0[t, f] @ (1j * x_matrix)) * fix.valid[t, f][..., None]
                )
                ratios.append(
                    abs(np.sum(tangent * gradient)) / (np.linalg.norm(tangent) * norm)
                )
    out["gauge_max"] = float(np.max(ratios))
    # Homogeneity per interval.
    t = fix.problem["time_bin"][fix.cells.rows].astype(np.int64)
    f = fix.problem["freq_bin"][fix.cells.channels].astype(np.int64)
    key = t * fix.x.shape[1] + f
    total = np.bincount(key, fix.s, minlength=fix.x.shape[0] * fix.x.shape[1])
    absolute = np.bincount(key, np.abs(fix.s), minlength=total.size)
    good_flat = fix.good_interval.ravel() & (absolute > 0)
    out["homogeneity_max"] = float(
        np.max(np.abs(total[good_flat]) / absolute[good_flat])
    )
    out["intervals"] = int(fix.x.shape[0] * fix.x.shape[1])
    out["intervals_with_gradient"] = int(
        (np.linalg.norm(fix.gradient, axis=(-1, -2)) > 0).sum()
    )
    out["adjoint_excluded_intervals"] = int(
        (
            (fix.residual > ADJOINT_RESIDUAL)
            & (np.linalg.norm(fix.gradient, axis=(-1, -2)) > 0)
        ).sum()
    )
    out["adjoint_residual_max_kept"] = float(fix.residual[fix.good_interval].max())
    return out


def summarise(reference, adjoint):
    reference, adjoint = np.asarray(reference), np.asarray(adjoint)
    error = np.abs(reference - adjoint) / np.abs(reference)
    return {
        "n": len(reference),
        "median_relative_error": float(np.median(error)),
        "p95_relative_error": float(np.quantile(error, 0.95)),
        "max_relative_error": float(error.max()),
        "correlation": float(np.corrcoef(reference, adjoint)[0, 1]),
    }


def finite_differences(fix, seed=7):
    rng = np.random.default_rng(seed)
    order = rng.permutation(np.flatnonzero(fix.cell_good & (fix.s != 0)))
    reference, adjoint, tried = [], [], 0
    started = time.perf_counter()
    for i in order:
        if len(reference) >= CELLS or tried >= 10 * CELLS:
            break
        tried += 1
        cell = (fix.cells.rows[[i]], fix.cells.channels[[i]])
        value = fix.richardson(cell)
        if value is not None:
            reference.append(value)
            adjoint.append(fix.s[i])
    cells = summarise(reference, adjoint)
    cells.update(tried=tried, seconds=time.perf_counter() - started)
    # Patches: one baseline, 8 contiguous channels, the whole interval in time.
    p = fix.problem
    channel_of = fix.cells.channels
    row_of = fix.cells.rows
    baseline = p["a1"][row_of].astype(np.int64) * p["nant"] + p["a2"][row_of]
    t = p["time_bin"][row_of].astype(np.int64)
    reference, adjoint, tried = [], [], 0
    for i in rng.permutation(np.flatnonzero(fix.cell_good)):
        if len(reference) >= PATCHES or tried >= 10 * PATCHES:
            break
        tried += 1
        first = channel_of[i] - channel_of[i] % 8
        members = (
            (baseline == baseline[i])
            & (t == t[i])
            & (channel_of >= first)
            & (channel_of < first + 8)
        )
        value = fix.richardson((row_of[members], channel_of[members]))
        if value is not None:
            reference.append(value)
            adjoint.append(float(fix.s[members].sum()))
    patches = summarise(reference, adjoint)
    patches["tried"] = tried
    return cells, patches


def unrolled(fix, interval, steps=200):
    """Reverse mode through Gauss-Newton steps of one interval at its fixed point.

    The step matrix is frozen at the solution (labelled: the protocol did not say).
    The derivative of the iteration still comes from automatic differentiation of
    the exact stationarity, independently of MINRES.
    """
    t, f = interval
    p = fix.problem
    row_t = p["time_bin"][fix.cells.rows]
    chan_f = p["freq_bin"][fix.cells.channels]
    members = np.flatnonzero((row_t == t) & (chan_f == f))
    rows, channels = fix.cells.rows[members], fix.cells.channels[members]
    data = jnp.asarray(p["data"][rows, channels].reshape(-1, 2, 2), jnp.complex128)
    model = jnp.asarray(p["model"][rows, channels].reshape(-1, 2, 2), jnp.complex128)
    weight = jnp.asarray(p["weights"][rows, channels].reshape(-1, 2, 2), jnp.float64)
    a1 = jnp.asarray(p["a1"][rows].astype(np.int32))
    a2 = jnp.asarray(p["a2"][rows].astype(np.int32))
    x_star = jnp.asarray(fix.x[t, f])
    full = jnp.asarray(fix.x)
    mask = jnp.asarray(fix.valid[t, f][..., None], jnp.float64)

    def vis(x):
        g = ta.to_complex(x)
        return g[a1] @ model @ jnp.conj(jnp.swapaxes(g[a2], -1, -2))

    def chi2(x, a):
        r = data - vis(x)
        return jnp.sum(a[..., None, None] * weight * (r.real**2 + r.imag**2))

    def whitened(x):
        v = vis(x) * jnp.sqrt(weight)
        return jnp.concatenate([v.real.ravel(), v.imag.ravel()])

    jacobian = jax.jacfwd(whitened)(x_star).reshape(whitened(x_star).size, -1)
    approximate = 2 * jacobian.T @ jacobian
    dimension = approximate.shape[0]
    damping = 1e-6 * jnp.trace(approximate) / dimension
    inverse = jnp.linalg.inv(approximate + damping * jnp.eye(dimension))
    stationarity = jax.grad(chi2)

    @jax.checkpoint
    def step(x, a):
        update = inverse @ (stationarity(x, a) * mask).ravel()
        return x - update.reshape(x.shape) * mask

    def loss(a):
        x = x_star
        for _ in range(steps):
            x = step(x, a)
        return ta.tv_value(full.at[t, f].set(x), fix.support)

    gradient = np.asarray(jax.grad(loss)(jnp.ones(len(rows))))
    return summarise(gradient, fix.s[members])


def run(problem, output, unroll):
    print(problem["name"], "start", flush=True)
    fix = Fixture(problem)
    result = {
        "problem": problem["name"],
        "cells": int(problem["selected"].sum()),
        "solve": {
            "seconds": fix.solve_seconds,
            "iterations": fix.iterations,
            "converged_fraction": fix.converged,
        },
        "adjoint": {
            "seconds": fix.adjoint_seconds,
            "minres_iterations": fix.minres_iterations,
        },
        "tv_rust": fix.rust_tv,
        "tv_jax": fix.jax_tv,
    }
    result["static"] = checks_static(fix)
    print(json.dumps(result), flush=True)
    result["finite_cells"], result["finite_patches"] = finite_differences(fix)
    if unroll:
        nt, nf = fix.x.shape[:2]
        started = time.perf_counter()
        result["unrolled"] = unrolled(fix, (nt // 2, nf // 2))
        result["unrolled"]["seconds"] = time.perf_counter() - started
    print(json.dumps(result), flush=True)
    return result


def verdict(results):
    calls = {}
    for r in results:
        s, c, q = r["static"], r["finite_cells"], r["finite_patches"]
        checks = {
            "polish": s["polish_max"] <= BOUNDS["polish_max"],
            "gauge": s["gauge_max"] <= BOUNDS["gauge_max"],
            "homogeneity": s["homogeneity_max"] <= BOUNDS["homogeneity_max"],
            "cells": c["median_relative_error"] <= BOUNDS["cell_median"]
            and c["p95_relative_error"] <= BOUNDS["cell_p95"]
            and c["correlation"] >= BOUNDS["cell_correlation"]
            and c["n"] >= CELLS,
            "patches": q["median_relative_error"] <= BOUNDS["patch_median"]
            and q["p95_relative_error"] <= BOUNDS["patch_p95"]
            and q["n"] >= PATCHES,
        }
        if "unrolled" in r:
            checks["unrolled"] = (
                r["unrolled"]["median_relative_error"] <= BOUNDS["unrolled_median"]
            )
        calls[r["problem"]] = checks
    return calls


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--slice", default="outputs/core-phase2-inputs-20261029-01/arrays.npz"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    ta.enable_x64()
    started = time.perf_counter()
    results = [
        run(synthetic(), args.output, True),
        run(luno_slice(args.slice), args.output, False),
    ]
    calls = verdict(results)
    report = {
        "bounds": BOUNDS,
        "results": results,
        "calls": calls,
        "passed": all(all(c.values()) for c in calls.values()),
        "wall_seconds": time.perf_counter() - started,
        "jax": jax.__version__,
    }
    (args.output / "result.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({"calls": calls, "passed": report["passed"]}, indent=1))


if __name__ == "__main__":
    main()
