"""Task L5 solver study helpers (research/l5-solver-science.md).

The core solver reads run-time options from `RANG_SOLVE_OPTIONS` and writes a
per-iteration trace to the file named by `RANG_SOLVE_TRACE` (both documented
in `core/src/solve.rs`; unset means the archived QuartiCal 0.2.7 behaviour).
This module sets them around one solve, replays the stop rule of any
criterion on a long run's trace, and computes the study's metrics: held-out
and training losses (the fused pass, K's definition), gain-product distances,
polar-gauge TV and cost. Read-only on every input.
"""

import contextlib
import json
import os
import time
from pathlib import Path

import numpy as np

from . import core, rusage
from .flagging import gain_tv, polar_gauge

OPTIONS_VAR = "RANG_SOLVE_OPTIONS"
TRACE_VAR = "RANG_SOLVE_TRACE"
GRID = (2, 32)


@contextlib.contextmanager
def solver_options(options="", trace=None):
    """Set `RANG_SOLVE_OPTIONS` (and `RANG_SOLVE_TRACE`) for the block only."""
    saved = {k: os.environ.get(k) for k in (OPTIONS_VAR, TRACE_VAR)}
    try:
        os.environ[OPTIONS_VAR] = options
        if trace is None:
            os.environ.pop(TRACE_VAR, None)
        else:
            os.environ[TRACE_VAR] = str(trace)
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def cpu_seconds():
    return rusage.cpu_seconds()


def solve(
    problem,
    options="",
    *,
    max_iterations=50,
    stop_criterion=1e-7,
    stop_fraction=0.99,
    trace=None,
):
    """One core solve of `problem` (see `problem_from_state`) with options.

    Returns gains, flags, validity, iterations, converged fraction, wall and
    CPU seconds (the process's user + system time, so rayon threads count)."""
    wall, cpu = time.perf_counter(), cpu_seconds()
    with solver_options(options, trace):
        solution = core.solve_complex(
            problem["data"],
            problem["weights"],
            problem["flag"],
            problem["flag_row"],
            problem["antenna1"],
            problem["antenna2"],
            problem["time_map"],
            problem["freq_map"],
            ntime_bins=problem["ntime_bins"],
            nfreq_bins=problem["nfreq_bins"],
            nant=problem["nant"],
            model=problem["model"],
            max_iterations=max_iterations,
            stop_criterion=stop_criterion,
            stop_fraction=stop_fraction,
        )
    wall, cpu = time.perf_counter() - wall, cpu_seconds() - cpu
    gains = solution.gains
    return {
        "options": options,
        "max_iterations": max_iterations,
        "stop_criterion": stop_criterion,
        "stop_fraction": stop_fraction,
        "gains": gains,
        "flags": solution.flags,
        "valid": (solution.flags == 0) & np.isfinite(gains).all(axis=(-1, -2)),
        "iterations": solution.iterations,
        "converged_fraction": solution.converged_fraction,
        "wall_seconds": wall,
        "cpu_seconds": cpu,
    }


def problem_from_state(
    state, flags, rows, time_map, freq_map, gain_times, gain_freqs, nant
):
    """The solver inputs and the split masks of a K/L1-style state."""
    return {
        "data": state["data"],
        "weights": state["weights"],
        "model": state["model"],
        "flag": flags,
        "flag_row": rows,
        "antenna1": state["antenna1"],
        "antenna2": state["antenna2"],
        "time_map": np.asarray(time_map),
        "freq_map": np.asarray(freq_map),
        "ntime_bins": len(gain_times),
        "nfreq_bins": len(gain_freqs),
        "nant": nant,
        "gain_times": np.asarray(gain_times),
        "gain_frequencies": np.asarray(gain_freqs),
        "train": state["train"],
        "validation": state["validation"],
        "test": state["test"],
    }


# --- traces ------------------------------------------------------------------


def load_trace(path):
    """A trace written by the core as arrays: per iteration (K) and, for the
    per-interval quantities, (K, intervals); null becomes NaN."""
    raw = json.loads(Path(path).read_text())
    its = raw["iterations"]

    def floats(key):
        return np.array(
            [[np.nan if v is None else v for v in it[key]] for it in its], float
        )

    return {
        "options": raw["options"],
        "settings": raw["settings"],
        "ngains": raw["ngains"],
        "nintervals": raw["nintervals"],
        "anderson_mixes": raw["anderson_mixes"],
        "anderson_resets": raw["anderson_resets"],
        "gain_converged": np.array([it["gain_converged"] for it in its]),
        "gain_flagged": np.array([it["gain_flagged"] for it in its]),
        "product_change": floats("product_change"),
        "chi2": floats("chi2"),
        "unit": np.array([it["unit"] for it in its], bool),
    }


def fraction(passing, excluded, units):
    """`converged_fraction` of the core: passing over non-excluded units."""
    solvable = units - excluded
    return np.where(solvable > 0, passing / np.maximum(solvable, 1), 0.0)


def criterion_curve(trace, criterion, tolerance=None):
    """The per-iteration fraction the stop test of `criterion` sees.

    `gain`: the trace's own gain test (its `stop_criterion`); `product` and
    `loss`: the interval tests of the core (from iteration index 2 on), with
    the loss evaluated at the gains entering each iteration."""
    k = len(trace["gain_converged"])
    if criterion == "gain":
        return fraction(trace["gain_converged"], trace["gain_flagged"], trace["ngains"])
    unit = trace["unit"]
    excluded = (~unit).sum(axis=1)
    if criterion == "product":
        with np.errstate(invalid="ignore"):
            passing = unit & (trace["product_change"] < tolerance)
    elif criterion == "loss":
        chi2 = trace["chi2"]
        previous = np.vstack([np.full((1, chi2.shape[1]), np.nan), chi2[:-1]])
        with np.errstate(invalid="ignore", divide="ignore"):
            change = np.abs(previous - chi2) / chi2
            passing = unit & (chi2 > 0) & (change < tolerance)
    else:
        raise ValueError(criterion)
    passing[: min(2, k)] = False
    return fraction(passing.sum(axis=1), excluded, trace["nintervals"])


def stop_iteration(trace, criterion, tolerance=None, stop_fraction=0.99):
    """1-based iteration at which the criterion stops the solve, or None if it
    does not within the trace."""
    curve = criterion_curve(trace, criterion, tolerance)
    hits = np.flatnonzero(curve >= stop_fraction)
    return int(hits[0]) + 1 if hits.size else None


def settled(trace):
    """How far the last iteration of a long run still moves."""
    change = trace["product_change"][-1]
    chi2 = trace["chi2"]
    rel = np.abs(chi2[-1] - chi2[-2]) / chi2[-1] if len(chi2) > 1 else None
    ok = np.isfinite(change)
    return {
        "iterations": len(trace["gain_converged"]),
        "last_max_product_change": float(change[ok].max()) if ok.any() else None,
        "last_median_product_change": float(np.median(change[ok]))
        if ok.any()
        else None,
        "last_max_relative_chi2_change": float(np.nanmax(rel))
        if rel is not None
        else None,
        "last_gain_fraction": float(criterion_curve(trace, "gain")[-1]),
    }


# --- metrics -----------------------------------------------------------------


def losses(problem, gains, valid, masks):
    """Fused-pass losses (K's definition: mean over cells of the
    correlation-mean w|r|²) of `gains` on the given sample masks."""
    fused = core.fused_pass(
        problem["data"],
        problem["weights"],
        problem["antenna1"],
        problem["antenna2"],
        problem["time_map"],
        problem["freq_map"],
        gains,
        valid,
        core.split_labels(**masks),
        model=problem["model"],
        residuals=False,
        scores=False,
        normals=False,
    )
    values = fused.losses()
    return {
        name: {
            "loss": values[name],
            "cells": fused.split_stats[name]["cells"],
            "invalid": fused.split_stats[name]["invalid"],
        }
        for name in masks
    }


def predicted(problem, valid):
    """Samples whose two station gains are valid."""
    t, f = problem["time_map"][:, None], problem["freq_map"][None]
    p, q = problem["antenna1"], problem["antenna2"]
    return valid[t, f, p[:, None]] & valid[t, f, q[:, None]]


def matched_losses(problem, run, reference):
    """Losses of `run` and `reference` on the split cells both predict."""
    both = predicted(problem, run["valid"]) & predicted(problem, reference["valid"])
    masks = {k: problem[k] & both for k in ("train", "validation", "test")}
    a = losses(problem, run["gains"], run["valid"], masks)
    b = losses(problem, reference["gains"], reference["valid"], masks)
    return {
        "cells": {k: a[k]["cells"] for k in masks},
        "dropped": {k: int(np.count_nonzero(problem[k] & ~both)) for k in masks},
        "run": {k: a[k]["loss"] for k in masks},
        "reference": {k: b[k]["loss"] for k in masks},
        "relative": {
            k: (a[k]["loss"] - b[k]["loss"]) / b[k]["loss"]
            if a[k]["loss"] is not None and b[k]["loss"]
            else None
            for k in masks
        },
    }


def observed_pairs(problem):
    """(time bin, freq bin, antenna, antenna) mask of the station pairs with
    at least one cell the solver uses in the interval (not FLAG or FLAG_ROW,
    nonzero XX/YY data and weight, as `solve::data_flags`). Products of
    unobserved pairs are not constrained by the data (post hoc, L5)."""
    if "observed" in problem:
        return problem["observed"]
    ok = ~(
        np.asarray(problem["flag"], bool).any(-1)
        | np.asarray(problem["flag_row"], bool)[:, None]
    )
    ok &= (problem["weights"][..., [0, 3]] != 0).all(-1)
    ok &= (problem["data"][..., [0, 3]] != 0).all(-1)
    nf, na = problem["nfreq_bins"], problem["nant"]
    per = np.zeros((ok.shape[0], nf), bool)
    for f in range(nf):
        per[:, f] = ok[:, problem["freq_map"] == f].any(axis=1)
    del ok
    rows, fbin = np.nonzero(per)
    t = problem["time_map"][rows]
    p, q = problem["antenna1"][rows], problem["antenna2"][rows]
    out = np.zeros((problem["ntime_bins"], nf, na, na), bool)
    out[t, fbin, p, q] = True
    out[t, fbin, q, p] = True
    problem["observed"] = out
    return out


def product_distance(gains, valid, ref_gains, ref_valid, observed=None):
    """Relative baseline-product distance |P - P_ref|_F / |P_ref|_F over
    pairs p < q of one interval valid in both solutions (and, if given,
    observed in the interval: `observed_pairs`)."""
    nant = gains.shape[2]
    both = valid & ref_valid
    values = []
    for p in range(nant):
        q = np.arange(p + 1, nant)
        if not q.size:
            continue
        pair = both[..., p, None] & both[..., q]
        if observed is not None:
            pair = pair & observed[..., p, p + 1 :]
        if not pair.any():
            continue
        a = gains[..., p, None, :, :] @ gains[..., q, :, :].conj().swapaxes(-1, -2)
        b = ref_gains[..., p, None, :, :] @ ref_gains[..., q, :, :].conj().swapaxes(
            -1, -2
        )
        num = np.linalg.norm((a - b)[pair], axis=(-1, -2))
        den = np.linalg.norm(b[pair], axis=(-1, -2))
        values.append(num / den)
    values = np.concatenate(values) if values else np.zeros(0)
    if not values.size:
        return {"pairs": 0, "max": None, "median": None, "p99": None}
    return {
        "pairs": int(values.size),
        "max": float(values.max()),
        "median": float(np.median(values)),
        "p99": float(np.quantile(values, 0.99)),
    }


def polar_tv(problem, gains, valid, scale):
    aligned, tv_valid = polar_gauge(gains, valid)
    return gain_tv(
        aligned,
        tv_valid,
        problem["gain_times"],
        problem["gain_frequencies"],
        scale=scale,
    )["total"]


def gain_scale(gains, valid):
    """The TV scale K uses: median Frobenius norm of the valid gains."""
    return float(np.median(np.linalg.norm(gains[valid], axis=(-1, -2))))


def summary(problem, run, reference, default, scale):
    """The study's metrics of one run against R (`reference`) and D."""
    split = losses(
        problem,
        run["gains"],
        run["valid"],
        {k: problem[k] for k in ("train", "validation", "test")},
    )
    return {
        "options": run["options"],
        "max_iterations": run["max_iterations"],
        "stop_criterion": run["stop_criterion"],
        "stop_fraction": run["stop_fraction"],
        "iterations": run["iterations"],
        "converged_fraction": run["converged_fraction"],
        "wall_seconds": run["wall_seconds"],
        "cpu_seconds": run["cpu_seconds"],
        "valid_gain_fraction": float(np.mean(run["valid"])),
        "flagged_gains": int(np.count_nonzero(run["flags"] != 0)),
        "losses": {k: v["loss"] for k, v in split.items()},
        "invalid_predictions": {k: v["invalid"] for k, v in split.items()},
        "vs_default": matched_losses(problem, run, default),
        "vs_reference": matched_losses(problem, run, reference),
        "product_distance_to_reference": product_distance(
            run["gains"], run["valid"], reference["gains"], reference["valid"]
        ),
        "product_distance_to_default": product_distance(
            run["gains"], run["valid"], default["gains"], default["valid"]
        ),
        # Post hoc (L5): only the pairs the interval's data constrain.
        "product_distance_to_reference_observed": product_distance(
            run["gains"],
            run["valid"],
            reference["gains"],
            reference["valid"],
            observed_pairs(problem),
        ),
        "product_distance_to_default_observed": product_distance(
            run["gains"],
            run["valid"],
            default["gains"],
            default["valid"],
            observed_pairs(problem),
        ),
        "polar_tv": polar_tv(problem, run["gains"], run["valid"], scale),
        "gains_sha256": core_sha256(run["gains"]),
    }


def core_sha256(array):
    from hashlib import sha256

    return sha256(np.ascontiguousarray(array).tobytes()).hexdigest()
