"""Stage 1b of research/f1-tv-flagger.md: the go/no-go on LUNO 1934-638.

Usage: python examples/f1_saliency.py OUTPUT_DIR [--probe]

`--probe` only decodes, solves, and prints the cost and the convergence measure;
it computes no saliency. No training anywhere. Gates are those frozen in section
4 of the protocol, with the details of Amendment 2.
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

import itertools

import numpy as np
from rang import core, core_campaign
from rang import core_campaign_array as array
from rang import tvflag_adjoint as ta
from rang.core_injection_model import make_injection
from rang.core_policy import axis_weights
from rang.core_workflow import gain_grid
from scipy.ndimage import binary_dilation
from scipy.stats import rankdata

SOLVER = {"max_iterations": 100, "options": "anderson=3"}
CONVERGED_STEP = 1e-5
ADJOINT_RESIDUAL = 1e-6
MORPHOLOGIES = (
    "narrowband",
    "time-burst",
    "antenna-local",
    "single-baseline",
    "drifting",
)
STRENGTHS = (3, 10, 30, 100)
SEEDS = (19, 20, 21)
TILE = 8
GATES = {
    "b1_t": 5.0,
    "b2_auc": 0.80,
    "c_t": 3.0,
    "d_fraction": 0.80,
    "morphologies": 3,
    "e_t": 5.0,
    "e_min_cells": 1000,
    "e_min_intervals": 50,
    "e_z": 10.0,
}
Z_BINS = (-np.inf, 3.0, 5.0, 10.0, np.inf)
BOOTSTRAP = 2000


def auc(score, label):
    """Area under the ROC curve with ties at half weight."""
    positive = int(label.sum())
    negative = len(label) - positive
    if not positive or not negative:
        return None
    ranks = rankdata(score)
    return float(
        (ranks[label].sum() - positive * (positive + 1) / 2) / (positive * negative)
    )


def bootstrap_t(groups, seed=20261102):
    """Mean over all values and its t, resampling within each group."""
    groups = [np.asarray(g, float) for g in groups if len(g)]
    if not groups:
        return {"mean": None, "t": None, "n": 0}
    rng = np.random.default_rng(seed)
    values = np.concatenate(groups)
    means = np.zeros(BOOTSTRAP)
    for i in range(BOOTSTRAP):
        means[i] = np.mean(
            np.concatenate([g[rng.integers(0, len(g), len(g))] for g in groups])
        )
    se = float(means.std(ddof=1))
    mean = float(values.mean())
    return {
        "mean": mean,
        "t": mean / se if se > 0 else None,
        "n": len(values),
        "se": se,
    }


def per_baseline_noise(state):
    """Real-component noise per row: scaled MAD of parallel-hand channel differences."""
    data, eligible = state["data"], state["eligible"]
    p, q = state["antenna1"], state["antenna2"]
    key = p.astype(np.int64) * (p.max() + q.max() + 2) + q
    sigma = np.zeros(len(p))
    for b in np.unique(key):
        rows = np.flatnonzero(key == b)
        both = eligible[rows, 1:] & eligible[rows, :-1]
        if not both.any():
            continue
        difference = (data[rows, 1:][..., [0, 3]] - data[rows, :-1][..., [0, 3]])[both]
        values = np.concatenate([difference.real.ravel(), difference.imag.ravel()])
        sigma[rows] = (
            1.4826 * np.median(np.abs(values - np.median(values))) / np.sqrt(2)
        )
    return sigma


def inject_mask(state, morphology, seed):
    """`(rows, channels, unit phasors)`, on training cells only."""
    train = state["train"]
    if morphology in ("narrowband", "time-burst", "antenna-local"):
        mask, delta, _ = make_injection(state, morphology, 1.0, seed)
        rows, channels = np.nonzero(mask)
        phasor = delta[rows, channels, 0] * np.sqrt(state["weights"][rows, channels, 0])
        return rows, channels, np.asarray(phasor, np.complex128)
    rng = np.random.default_rng(seed)
    train.shape[1]
    if morphology == "single-baseline":
        p, q = state["antenna1"], state["antenna2"]
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
    elif morphology == "drifting":
        dump = np.unique(state["times"], return_inverse=True)[1]
        ndump = int(dump.max()) + 1
        span = 2 * (ndump - 1) + 8
        per_channel = train.mean(axis=0)
        width = np.convolve(per_channel, np.ones(span) / span, mode="valid")
        first = int(rng.choice(np.flatnonzero(width >= 0.5 * np.median(per_channel))))
        mask = np.zeros(train.shape, bool)
        for k in range(ndump):
            start = first + 2 * k
            mask[np.ix_(dump == k, np.arange(start, start + 8))] = True
    else:
        raise ValueError(morphology)
    mask &= train
    rows, channels = np.nonzero(mask)
    phase = rng.uniform(-np.pi, np.pi) + rng.normal(0, 0.15, len(rows))
    return rows, channels, np.exp(1j * phase)


class Campaign:
    def __init__(self, state, label, run_dir):
        self.state, self.label, self.run_dir = state, label, run_dir
        self.time_map, self.freq_map, times, freqs = gain_grid(
            state, *core_campaign.GRID
        )
        self.time_map = self.time_map.astype(np.int64)
        self.freq_map = self.freq_map.astype(np.int64)
        self.grid = (len(times), len(freqs))
        self.nant = len(state["names"])
        self.tw, self.fw = axis_weights(times), axis_weights(freqs)
        shape = state["train"].shape
        self.shape = shape
        p, q = state["antenna1"], state["antenna2"]
        key = p.astype(np.int64) * (p.max() + q.max() + 2) + q
        self.baseline = np.unique(key, return_inverse=True)[1].astype(np.int64)
        self.dump = np.unique(state["times"], return_inverse=True)[1].astype(np.int64)
        self.nbl = int(self.baseline.max()) + 1
        self.tiles_t = int(self.dump.max()) // TILE + 1
        self.tiles_f = (shape[1] - 1) // TILE + 1
        self.flags, self.flag_rows = array.solve_flags_lean(
            state, np.zeros(shape, bool)
        )
        self.sigma = per_baseline_noise(state)
        self.ntile = self.nbl * self.tiles_t * self.tiles_f

    # ---- solves
    def solve_box(self, intervals, data=None, flags=None, sub=None):
        """Solve the box around `intervals` (nt, nf bool); returns grid arrays."""
        state = self.state
        t_set = np.flatnonzero(intervals.any(axis=1))
        f_set = np.flatnonzero(intervals.any(axis=0))
        rows = np.flatnonzero(np.isin(self.time_map, t_set))
        channels = np.flatnonzero(np.isin(self.freq_map, f_set))
        tb = np.searchsorted(t_set, self.time_map[rows]).astype(np.uint32)
        fb = np.searchsorted(f_set, self.freq_map[channels]).astype(np.uint32)
        index = np.ix_(rows, channels)
        d = np.array(state["data"][index])
        fl = np.array(self.flags[index])
        if data is not None:
            d[np.searchsorted(rows, data[0]), np.searchsorted(channels, data[1])] += (
                data[2]
            )
        if flags is not None:
            fl[np.searchsorted(rows, flags[0]), np.searchsorted(channels, flags[1])] = (
                True
            )
        solution = core.solve_complex(
            d,
            state["weights"][index],
            fl,
            self.flag_rows[rows] | fl.all(axis=(1, 2)),
            state["antenna1"][rows],
            state["antenna2"][rows],
            tb,
            fb,
            ntime_bins=len(t_set),
            nfreq_bins=len(f_set),
            nant=self.nant,
            model=state["model"][index],
            **SOLVER,
        )
        gains = np.array(self.gains0)
        gflags = np.array(self.gflags0)
        tt, ff = np.nonzero(intervals)
        gains[tt, ff] = solution.gains[
            np.searchsorted(t_set, tt), np.searchsorted(f_set, ff)
        ]
        gflags[tt, ff] = solution.flags[
            np.searchsorted(t_set, tt), np.searchsorted(f_set, ff)
        ]
        return gains, gflags, solution

    def solve_clean(self):
        state = self.state
        started = time.perf_counter()
        solution = core.solve_complex(
            state["data"],
            state["weights"],
            self.flags,
            self.flag_rows,
            state["antenna1"],
            state["antenna2"],
            self.time_map.astype(np.uint32),
            self.freq_map.astype(np.uint32),
            ntime_bins=self.grid[0],
            nfreq_bins=self.grid[1],
            nant=self.nant,
            model=state["model"],
            **SOLVER,
        )
        self.clean_seconds = time.perf_counter() - started
        self.gains0, self.gflags0 = solution.gains, solution.flags
        self.solver0 = {
            "iterations": solution.iterations,
            "converged_fraction": solution.converged_fraction,
            "seconds": self.clean_seconds,
        }
        self.x0, self.valid0, raw = ta.sanitize(solution.gains, solution.flags)
        self.scale = float(
            np.median(np.linalg.norm(solution.gains[raw], axis=(-1, -2)))
        )

    def cell_selection(self, active):
        return self.state["train"] & active[self.time_map[:, None], self.freq_map[None]]

    def cells(self, active, valid, delta=None):
        state = self.state
        return ta.make_cells(
            state["data"],
            state["model"],
            state["weights"],
            self.cell_selection(active),
            state["antenna1"],
            state["antenna2"],
            self.time_map,
            self.freq_map,
            self.grid,
            gain_valid=valid,
            delta=delta,
        )

    def support(self, valid, converged):
        good = valid & converged[..., None]
        support = ta.make_support(good, self.tw, self.fw, self.scale)
        return support

    # ---- saliency
    def adjoint(self, cells, x, valid, support, active, powers):
        """`{power: (s, residual norms, excluded intervals, iterations)}`."""
        operator = ta.Operator(cells, x, valid)
        out = {}
        for power in powers:
            support.norm = self.norms.get(power, 1.0)
            gradient = ta.tv_gradient(x, support, power) * valid[..., None]
            gradient[~active] = 0
            lam, residual, used = ta.minres(operator, gradient)
            bad = (residual > ADJOINT_RESIDUAL) & active
            lam[bad] = 0
            s, amplitude = operator.cell_saliency(lam)
            out[power] = {
                "s": s,
                "amplitude": amplitude,
                "excluded": bad,
                "iterations": used,
                "residual_max": float(residual[active & ~bad].max())
                if (active & ~bad).any()
                else None,
            }
        return out

    def clean(self, powers=(1, 2)):
        started = time.perf_counter()
        everything = np.ones(self.grid, bool)
        self.cells0 = self.cells(everything, self.valid0)
        operator = ta.Operator(self.cells0, self.x0, self.valid0)
        step = operator.jacobi_step()
        self.step0 = step
        self.converged0 = (step <= CONVERGED_STEP).all(axis=-1)
        support = self.support(self.valid0, self.converged0)
        self.norms = {}
        support.norm = 1.0
        self.tv0 = ta.tv(self.x0, support)
        self.norms = {p: ta.tv(self.x0, support, p) for p in powers}
        result = self.adjoint(
            self.cells0, self.x0, self.valid0, support, everything, powers
        )
        self.adjoint_seconds = time.perf_counter() - started
        rows, channels = self.cells0.rows, self.cells0.channels
        self.s0 = {}
        self.excluded0 = {}
        for power in powers:
            dense = np.full(self.shape, np.nan, np.float32)
            dense[rows, channels] = result[power]["s"]
            bad = result[power]["excluded"] | ~self.converged0
            dense[bad[self.time_map[:, None], self.freq_map[None]]] = np.nan
            self.s0[power] = dense
            self.excluded0[power] = bad
        self.amp0 = np.full(self.shape, np.nan, np.float32)
        self.amp0[rows, channels] = result[1]["amplitude"]
        self.minres0 = {p: result[p]["iterations"] for p in powers}
        self.cells0 = None  # release the chunks
        self.base_tiles()

    def tile(self, rows, channels):
        return (
            self.baseline[rows] * (self.tiles_t * self.tiles_f)
            + (self.dump[rows] // TILE) * self.tiles_f
            + channels // TILE
        )

    def base_tiles(self):
        rows, channels = np.nonzero(self.state["train"])
        self.train_rows, self.train_channels = rows, channels
        self.train_tile = self.tile(rows, channels)
        # Robust residual z per baseline, from the clean residuals.
        amp = self.amp0[rows, channels]
        ok = np.isfinite(amp)
        self.base_median = np.zeros(self.nbl)
        self.base_mad = np.ones(self.nbl)
        order = np.argsort(self.baseline[rows[ok]], kind="stable")
        sorted_amp = amp[ok][order]
        edges = np.searchsorted(self.baseline[rows[ok]][order], np.arange(self.nbl + 1))
        for b in range(self.nbl):
            values = sorted_amp[edges[b] : edges[b + 1]]
            if len(values):
                self.base_median[b] = np.median(values)
                self.base_mad[b] = max(
                    1.4826 * np.median(np.abs(values - self.base_median[b])), 1e-12
                )

    def residual_z(self, amp):
        rows = self.train_rows
        b = self.baseline[rows]
        return (amp[rows, self.train_channels] - self.base_median[b]) / self.base_mad[b]

    def patch_auc(self, values, injected_flags):
        """AUC of the tile means of per-train-cell `values`, label: any injected."""
        ok = np.isfinite(values)
        total = np.bincount(self.train_tile[ok], values[ok], minlength=self.ntile)
        count = np.bincount(self.train_tile[ok], minlength=self.ntile)
        label = (
            np.bincount(self.train_tile[ok], injected_flags[ok], minlength=self.ntile)
            > 0
        )
        use = count > 0
        return auc(total[use] / count[use], label[use])

    def interval_contrast(self, dense, rows, channels):
        """Per-interval mean over injected minus mean over clean training cells."""
        inject = np.zeros(self.shape, bool)
        inject[rows, channels] = True
        tt = self.time_map[rows]
        ff = self.freq_map[channels]
        out = []
        for t, f in {(int(a), int(b)) for a, b in zip(tt, ff)}:
            row_set = np.flatnonzero(self.time_map == t)
            chan_set = np.flatnonzero(self.freq_map == f)
            index = np.ix_(row_set, chan_set)
            s = dense[index]
            finite = np.isfinite(s) & self.state["train"][index]
            hot = finite & inject[index]
            cold = finite & ~inject[index]
            if hot.any() and cold.any():
                out.append(float(s[hot].mean() - s[cold].mean()))
        return out

    # ---- one injected case
    def case(self, morphology, seed, strength, mask, powers):
        rows, channels, phasor = mask
        started = time.perf_counter()
        amplitude = strength * self.sigma[rows] * phasor
        values = np.repeat(amplitude[:, None], 4, axis=1)
        contaminated = np.zeros(self.grid, bool)
        contaminated[self.time_map[rows], self.freq_map[channels]] = True
        gains, gflags, solution = self.solve_box(
            contaminated, data=(rows, channels, values)
        )
        x, valid, _ = ta.sanitize(gains, gflags)
        # Intervals whose TV gradient changes: the contaminated ones and neighbours.
        active = contaminated.copy()
        active[1:] |= contaminated[:-1]
        active[:-1] |= contaminated[1:]
        active[:, 1:] |= contaminated[:, :-1]
        active[:, :-1] |= contaminated[:, 1:]
        cells = self.cells(active, valid, delta=(rows, channels, values))
        operator = ta.Operator(cells, x, valid)
        step = operator.jacobi_step()
        converged = self.converged0.copy()
        converged[active] = (step[active] <= CONVERGED_STEP).all(axis=-1)
        support = self.support(valid, converged)
        out = {
            "morphology": morphology,
            "seed": seed,
            "strength": strength,
            "injected": len(rows),
            "contaminated_intervals": int(contaminated.sum()),
            "active_intervals": int(active.sum()),
            "active_cells": len(cells.rows),
            "solver": {
                "iterations": solution.iterations,
                "converged": solution.converged_fraction,
            },
            "unconverged_contaminated": int((~converged & contaminated).sum()),
            "unconverged_active": int((~converged & active).sum()),
        }
        adjoint = self.adjoint(cells, x, valid, support, active, powers)
        injected_train = np.zeros(self.shape, bool)
        injected_train[rows, channels] = True
        flags_train = injected_train[self.train_rows, self.train_channels]
        for power in powers:
            dense = self.s0[power].copy()
            active_cells = self.cell_selection(active)
            dense[active_cells] = np.nan
            dense[cells.rows, cells.channels] = adjoint[power]["s"]
            bad = adjoint[power]["excluded"] | (~converged & active)
            dense[bad[self.time_map[:, None], self.freq_map[None]]] = np.nan
            train_values = dense[self.train_rows, self.train_channels]
            stats = {
                "contrast": self.interval_contrast(dense, rows, channels),
                "patch_auc": self.patch_auc(train_values, flags_train),
                "excluded_intervals": int(adjoint[power]["excluded"].sum()),
                "minres_iterations": adjoint[power]["iterations"],
                "injected_defined": float(np.isfinite(dense[rows, channels]).mean()),
            }
            if power == 1:
                amp = self.amp0.copy()
                amp[active_cells] = np.nan
                amp[cells.rows, cells.channels] = adjoint[1]["amplitude"]
                z = self.residual_z(amp)
                stats["residual_patch_auc"] = self.patch_auc(z, flags_train)
                stats["residual_contrast"] = self.interval_contrast(
                    self._dense(z), rows, channels
                )
                stats["cell_auc"] = self.cell_auc(train_values, flags_train, seed)
                stats["residual_cell_auc"] = self.cell_auc(z, flags_train, seed)
            out[f"power{power}"] = stats
        out["tv_contaminated"] = None
        out["seconds"] = time.perf_counter() - started
        self.last = (x, valid, contaminated, values)
        return out

    def _dense(self, values):
        dense = np.full(self.shape, np.nan, np.float32)
        dense[self.train_rows, self.train_channels] = values
        return dense

    def cell_auc(self, values, label, seed):
        rng = np.random.default_rng(seed)
        ok = np.isfinite(values)
        negative = np.flatnonzero(ok & ~label)
        if len(negative) > 2_000_000:
            negative = rng.choice(negative, 2_000_000, replace=False)
        use = np.concatenate([np.flatnonzero(ok & label), negative])
        return auc(values[use], label[use])

    def removal(self, mask):
        """Gate D's other solve: the injected cells flagged."""
        rows, channels, _ = mask
        contaminated = np.zeros(self.grid, bool)
        contaminated[self.time_map[rows], self.freq_map[channels]] = True
        gains, gflags, _ = self.solve_box(contaminated, flags=(rows, channels))
        x, valid, _ = ta.sanitize(gains, gflags)
        return x, valid

    def gate_d(self, removed, last):
        x_r, valid_r = removed
        x_c, valid_c = last[:2]
        common = valid_r & valid_c
        support = ta.make_support(common, self.tw, self.fw, self.scale)
        lost = int(valid_c.sum() - common.sum())
        return {
            "tv_contaminated": ta.tv(x_c, support),
            "tv_removed": ta.tv(x_r, support),
            "gains_lost": lost,
        }

    # ---- whole-scan reports
    def input_z(self):
        """Section 2's input z-score, the maximum over correlations, per cell."""
        state = self.state
        z = np.full(self.shape, -np.inf, np.float32)
        order = np.argsort(self.baseline, kind="stable")
        edges = np.searchsorted(self.baseline[order], np.arange(self.nbl + 1))
        eligible = state["eligible"]
        for b in range(self.nbl):
            rows = order[edges[b] : edges[b + 1]]
            good = eligible[rows]
            if not good.any():
                continue
            amp = np.log(np.maximum(np.abs(state["data"][rows]), 1e-30))
            amp[~good] = np.nan
            for k in range(4):
                plane = amp[..., k]
                columns = np.where(good.any(axis=0))[0]
                centre = np.zeros(plane.shape[1])
                centre[columns] = np.nanmedian(plane[:, columns], axis=0)
                plane = plane - centre
                mad = np.nanmedian(np.abs(plane - np.nanmedian(plane)))
                value = plane / max(1.4826 * mad, 1e-12)
                z[rows] = np.fmax(z[rows], value)
        return z

    def amplitude_bins(self, dense, z):
        out = []
        train = self.state["train"]
        for low, high in itertools.pairwise(Z_BINS):
            members = train & (z >= low) & (z < high) & np.isfinite(dense)
            rows, channels = np.nonzero(members)
            key = self.time_map[rows] * self.grid[1] + self.freq_map[channels]
            total = np.bincount(key, dense[rows, channels].astype(float))
            count = np.bincount(key)
            means = total[count > 0] / count[count > 0]
            stats = bootstrap_t([means])
            stats.update(
                low=low, high=high, cells=len(rows), intervals=int((count > 0).sum())
            )
            out.append(stats)
        return out

    def edge_structure(self):
        """Dead-zone report: edges, half-set noise and cosine of successive edges."""
        rng = np.random.default_rng(7)
        half = rng.random(self.shape) < 0.5
        saved = self.flags
        grids = []
        everything = np.ones(self.grid, bool)
        for subset in (half, ~half):
            self.flags = saved | subset[..., None]
            gains, gflags, _ = self.solve_box(everything)
            grids.append(ta.sanitize(gains, gflags)[:2])
        self.flags = saved
        out = {}
        aligned = np.asarray(ta.polar_aligned(self.x0))
        one = np.asarray(ta.polar_aligned(grids[0][0]))
        two = np.asarray(ta.polar_aligned(grids[1][0]))
        valid = self.valid0 & grids[0][1] & grids[1][1]
        for name, axis in (("time", 0), ("freq", 1)):
            d = np.diff(aligned, axis=axis)
            noise = np.diff(one, axis=axis) - np.diff(two, axis=axis)
            m = np.take(valid, range(valid.shape[axis] - 1), axis=axis) & np.take(
                valid, range(1, valid.shape[axis]), axis=axis
            )
            e = np.linalg.norm(d, axis=(-1, -2))[m]
            n = np.linalg.norm(noise, axis=(-1, -2))[m] / 2
            prev = np.take(d, range(d.shape[axis] - 1), axis=axis)
            nxt = np.take(d, range(1, d.shape[axis]), axis=axis)
            cos = np.real((np.conj(prev) * nxt).sum((-1, -2))) / (
                np.linalg.norm(prev, axis=(-1, -2)) * np.linalg.norm(nxt, axis=(-1, -2))
                + 1e-30
            )
            mm = np.take(m, range(m.shape[axis] - 1), axis=axis) & np.take(
                m, range(1, m.shape[axis]), axis=axis
            )
            out[name] = {
                "edges": int(m.sum()),
                "median_edge": float(np.median(e)),
                "median_noise": float(np.median(n)),
                "ratio": float(np.median(e) / np.median(n)),
                "fraction_above_twice_noise": float((e > 2 * n).mean()),
                "median_cosine_successive": float(np.median(cos[mm])),
            }
        return out

    def far_stratum(self):
        """Cells with no input flag within 3 dumps and 8 channels on the baseline."""
        state = self.state
        far = np.zeros(self.shape, bool)
        order = np.argsort(self.baseline, kind="stable")
        edges = np.searchsorted(self.baseline[order], np.arange(self.nbl + 1))
        nd = int(self.dump.max()) + 1
        structure = np.ones((7, 17), bool)
        flagged = state["original_flags"].any(-1) | state["original_rows"][:, None]
        for b in range(self.nbl):
            rows = order[edges[b] : edges[b + 1]]
            plane = np.ones((nd, self.shape[1]), bool)
            plane[self.dump[rows]] = flagged[rows]
            far[rows] = ~binary_dilation(plane, structure)[self.dump[rows]]
        return far & state["train"]


def subset_state(state, stations):
    keep = (state["antenna1"] < stations) & (state["antenna2"] < stations)
    out = dict(state)
    for key in (
        "original_flags",
        "original_rows",
        "data",
        "model",
        "weights",
        "times",
        "antenna1",
        "antenna2",
        "eligible",
        "train",
        "validation",
        "test",
    ):
        out[key] = np.ascontiguousarray(state[key][keep])
    out["names"] = state["names"][:stations]
    return out


def write(path, value):
    path.write_text(json.dumps(value, indent=1))


def full_run(campaign, run_dir, extra):
    results = {"cases": [], "removal": []}
    masks = {}
    for morphology in MORPHOLOGIES:
        for seed in SEEDS:
            masks[morphology, seed] = inject_mask(campaign.state, morphology, seed)
    # Gate C: strength 0, the clean saliency on the same masks.
    zero = {}
    for (morphology, seed), mask in masks.items():
        zero.setdefault(morphology, {})[seed] = campaign.interval_contrast(
            campaign.s0[1], mask[0], mask[1]
        )
    results["zero"] = zero
    write(run_dir / "partial.json", results)
    for (morphology, seed), mask in masks.items():
        removed = campaign.removal(mask)
        for strength in STRENGTHS:
            powers = (1, 2) if strength == 10 else (1,)
            record = campaign.case(morphology, seed, strength, mask, powers)
            d = campaign.gate_d(removed, campaign.last)
            record["gate_d"] = d
            results["cases"].append(record)
            print(
                morphology,
                seed,
                strength,
                f"{record['seconds']:.0f}s",
                record["active_cells"],
                "unconv",
                record["unconverged_contaminated"],
                flush=True,
            )
            write(run_dir / "partial.json", results)
    # Gate E and the reports.
    z = campaign.input_z()
    results["amplitude_bins"] = campaign.amplitude_bins(campaign.s0[1], z)
    results["amplitude_bins_tv2"] = campaign.amplitude_bins(campaign.s0[2], z)
    results["edge_structure"] = campaign.edge_structure()
    additions, summary = array.tricolour_arm(
        campaign.state,
        extra,
        core_campaign.STRATEGY_DIR / core_campaign.STRATEGIES["tricolour-firstpass"],
    )
    far = campaign.far_stratum()
    results["first_pass"] = {
        k: summary[k] for k in ("core_seconds", "wall_seconds", "additions_on_train")
    }
    rows, channels = campaign.train_rows, campaign.train_channels
    use = far[rows, channels]
    label = additions[rows, channels]
    s = campaign.s0[1][rows, channels]
    amp = campaign.residual_z(campaign.amp0)
    results["first_pass"].update(
        far_cells=int(use.sum()),
        far_fraction_of_train=float(use.mean()),
        far_additions=int(label[use].sum()),
        saliency_cell_auc_all=campaign.cell_auc(s, label, 7),
        residual_cell_auc_all=campaign.cell_auc(amp, label, 7),
        saliency_cell_auc_far=campaign.cell_auc(s[use], label[use], 7)
        if label[use].any()
        else None,
        residual_cell_auc_far=campaign.cell_auc(amp[use], label[use], 7)
        if label[use].any()
        else None,
    )
    return results


def gates(results):
    calls = {"B1": {}, "B2": {}, "C": {}, "D": {}}
    reports = {"tv2": {}, "residual": {}, "by_strength": {}}
    cases = results["cases"]
    for morphology in MORPHOLOGIES:
        pick = [c for c in cases if c["morphology"] == morphology]
        at10 = [c for c in pick if c["strength"] == 10]
        groups = [c["power1"]["contrast"] for c in at10]
        calls["B1"][morphology] = bootstrap_t(groups)
        aucs = [c["power1"]["patch_auc"] for c in at10]
        calls["B2"][morphology] = {"by_seed": aucs, "mean": float(np.mean(aucs))}
        zero = results["zero"][morphology]
        calls["C"][morphology] = bootstrap_t(list(zero.values()))
        reports["tv2"][morphology] = {
            "b1": bootstrap_t([c["power2"]["contrast"] for c in at10]),
            "b2": float(np.mean([c["power2"]["patch_auc"] for c in at10])),
        }
        reports["residual"][morphology] = {
            "b1": bootstrap_t([c["power1"]["residual_contrast"] for c in at10]),
            "b2": float(np.mean([c["power1"]["residual_patch_auc"] for c in at10])),
            "cell_auc": float(
                np.mean([c["power1"]["residual_cell_auc"] for c in at10])
            ),
            "saliency_cell_auc": float(
                np.mean([c["power1"]["cell_auc"] for c in at10])
            ),
        }
        by = {}
        for strength in STRENGTHS:
            subset = [c for c in pick if c["strength"] == strength]
            by[strength] = {
                "t": bootstrap_t([c["power1"]["contrast"] for c in subset])["t"],
                "patch_auc": float(np.mean([c["power1"]["patch_auc"] for c in subset])),
                "residual_patch_auc": float(
                    np.mean([c["power1"]["residual_patch_auc"] for c in subset])
                ),
            }
        reports["by_strength"][morphology] = by
    strong = [c for c in cases if c["strength"] >= 10]
    lower = [c["gate_d"]["tv_removed"] < c["gate_d"]["tv_contaminated"] for c in strong]
    calls["D"] = {
        "lower": int(sum(lower)),
        "cases": len(lower),
        "fraction": float(np.mean(lower)),
        "gains_lost_max": int(max(c["gate_d"]["gains_lost"] for c in strong)),
    }
    top = results["amplitude_bins"][-1]
    decidable = (
        top["cells"] >= GATES["e_min_cells"]
        and top["intervals"] >= GATES["e_min_intervals"]
    )
    calls["E"] = {"top_bin": top, "decidable": decidable}
    b1_pass = {
        m
        for m, v in calls["B1"].items()
        if v["t"] is not None and v["t"] >= GATES["b1_t"]
    }
    b2_pass = {m for m, v in calls["B2"].items() if v["mean"] >= GATES["b2_auc"]}
    both = sorted(b1_pass & b2_pass)
    passes = {
        "B": len(both) >= GATES["morphologies"],
        "B_morphologies": both,
        "B1_morphologies": sorted(b1_pass),
        "B2_morphologies": sorted(b2_pass),
        "C": all(
            v["t"] is not None and abs(v["t"]) < GATES["c_t"]
            for v in calls["C"].values()
        ),
        "D": calls["D"]["fraction"] >= GATES["d_fraction"],
        "E": (top["t"] is not None and top["mean"] > 0 and top["t"] >= GATES["e_t"])
        if decidable
        else None,
    }
    tv2_pass = sorted(
        m
        for m, v in reports["tv2"].items()
        if v["b1"]["t"] is not None
        and v["b1"]["t"] >= GATES["b1_t"]
        and v["b2"] >= GATES["b2_auc"]
    )
    reports["tv2_morphologies"] = tv2_pass
    go = passes["B"] and passes["C"] and passes["D"] and passes["E"] is not False
    return {"calls": calls, "passes": passes, "go": bool(go), "reports": reports}


def array_curve(state, extra, run_dir):
    """Reported only: narrowband and single-baseline at strength 10 on subarrays."""
    out = {}
    for stations in (8, 16, 32):
        sub = subset_state(state, stations)
        campaign = Campaign(sub, f"stations-{stations}", run_dir)
        campaign.solve_clean()
        campaign.clean(powers=(1,))
        row = {}
        for morphology in ("narrowband", "single-baseline"):
            mask = inject_mask(sub, morphology, SEEDS[0])
            record = campaign.case(morphology, SEEDS[0], 10, mask, (1,))
            row[morphology] = {
                "t": bootstrap_t([record["power1"]["contrast"]])["t"],
                "patch_auc": record["power1"]["patch_auc"],
                "residual_patch_auc": record["power1"]["residual_patch_auc"],
                "injected": record["injected"],
            }
        out[stations] = row
        print("curve", stations, json.dumps(row), flush=True)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    ta.enable_x64()
    started = time.perf_counter()
    arrays, rows, _ = array.decode_inputs(None)
    extra = array.decode_extra(rows)
    nant = len(extra["antenna_names"])
    state = array.build_state(arrays, extra, nant)
    del arrays
    print("decoded", time.perf_counter() - started, flush=True)
    campaign = Campaign(state, "whole-array", args.output)
    campaign.solve_clean()
    print("clean solve", json.dumps(campaign.solver0), flush=True)
    if args.probe:
        mark = time.perf_counter()
        everything = np.ones(campaign.grid, bool)
        cells = campaign.cells(everything, campaign.valid0)
        print("cells", len(cells.rows), time.perf_counter() - mark, flush=True)
        operator = ta.Operator(cells, campaign.x0, campaign.valid0)
        mark = time.perf_counter()
        step = operator.jacobi_step()[campaign.valid0]
        print("jacobi seconds", time.perf_counter() - mark, flush=True)
        print(
            "step quantiles 50 90 99 99.9 max",
            np.quantile(step, [0.5, 0.9, 0.99, 0.999, 1.0]).tolist(),
            flush=True,
        )
        for threshold in (1e-6, 1e-5, 1e-4, 1e-3):
            print(
                threshold, "gains above", float((step > threshold).mean()), flush=True
            )
        mark = time.perf_counter()
        operator.hessian(np.ones_like(campaign.x0))
        print("one hessian product seconds", time.perf_counter() - mark, flush=True)
        for morphology in MORPHOLOGIES:
            mask = inject_mask(state, morphology, SEEDS[0])
            box = np.zeros(campaign.grid, bool)
            box[campaign.time_map[mask[0]], campaign.freq_map[mask[1]]] = True
            print(morphology, len(mask[0]), "intervals", int(box.sum()), flush=True)
        return
    campaign.clean()
    print("clean adjoint", campaign.adjoint_seconds, campaign.minres0, flush=True)
    results = full_run(campaign, args.output, extra)
    results["clean"] = {
        "solver": campaign.solver0,
        "adjoint_seconds": campaign.adjoint_seconds,
        "minres": campaign.minres0,
        "tv": campaign.tv0,
        "tv_norms": campaign.norms,
        "unconverged_intervals": int((~campaign.converged0).sum()),
        "excluded_intervals": {p: int(v.sum()) for p, v in campaign.excluded0.items()},
        "intervals": int(np.prod(campaign.grid)),
        "train_cells": int(state["train"].sum()),
    }
    results["array_curve"] = array_curve(state, extra, args.output)
    results["gates"] = gates(results)
    results["wall_seconds"] = time.perf_counter() - started
    results["settings"] = {
        "solver": SOLVER,
        "converged_step": CONVERGED_STEP,
        "adjoint_residual": ADJOINT_RESIDUAL,
        "morphologies": MORPHOLOGIES,
        "strengths": STRENGTHS,
        "seeds": SEEDS,
        "tile": TILE,
        "gates": GATES,
    }
    write(args.output / "result.json", results)
    print(
        json.dumps(
            {"go": results["gates"]["go"], "passes": results["gates"]["passes"]},
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
