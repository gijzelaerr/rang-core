"""Certified CLEAN on the Rang core (research/clean-certified-imaging.md).

A Cotton-Schwab CLEAN whose major cycles go through the core's exact
gridder and degridder (`rang_core::wgridder`) and whose minor cycles use
Clark's stop rule, the provable rule of Theorem 6 (research/clean-theory.md)
or WSClean's `-mgain` rule, instrumented with the formalism's diagnostics:
the Gram-consistency gap per major cycle, the misfit floor `Q_inf` by
conjugate gradients, the exact recovery coefficient of the component list
and an audit of minor steps that raise the true misfit. The kernel is
`rang_core::clean_certified`, reached through the extension `rang._core`.

Images are `(side, side)` in the gridder's layout: `[i, j]` with `i` along
`l`. With `flip_v` and `flip_w` (the defaults) the transpose is WSClean's FITS
pixel order (research/df1-wgridder.md, item 0).
"""

import numpy as np

from . import core

ARCSEC = np.pi / (180.0 * 3600.0)
RULES = {"clark": 0, "provable": 1, "mgain": 2}
BEAMS = {"exact": 0, "image": 1}
STOPS = ("threshold", "floor", "components", "major_cycles", "diverged")
MINOR_STOPS = ("threshold", "rule", "max_minor", "budget", "diverged")
CYCLE_FIELDS = (
    "index",
    "components",
    "peak_start",
    "peak_working_end",
    "q_before",
    "q_after",
    "dq_exact",
    "dq_predicted",
    "gap",
    "gap_relative",
    "dq_audit",
    "ascending_steps",
    "abs_flux",
    "kappa",
    "reducible",
    "stop",
    "seconds",
)
SUMMARY_FIELDS = (
    "q0",
    "q_final",
    "components",
    "major_cycles",
    "stop",
    "f",
    "seconds",
    "ascending_steps",
    "erc_k",
    "erc_eta",
    "erc_min_pivot",
    "q_floor",
    "floor_iterations",
    "floor_relative_residual",
    "weight_sum",
    "erc_seconds",
)
INTEGER_FIELDS = {"index", "components", "ascending_steps", "major_cycles", "erc_k"}


def _nan_to_none(value):
    return None if isinstance(value, float) and np.isnan(value) else value


def certified_clean(
    uvw,
    freq,
    vis,
    weights,
    *,
    side=512,
    scale_arcsec=8.0,
    epsilon=1e-9,
    wgridding=True,
    flip_v=True,
    flip_w=True,
    gain=0.1,
    threshold=0.0,
    max_components=10_000,
    max_major=100,
    max_minor=None,
    rule="mgain",
    mgain=0.8,
    patch=None,
    beam="exact",
    floor_iterations=0,
    floor_tolerance=None,
    divergence_limit=4.0,
    audit=False,
    erc_max_k=4000,
):
    """Certified CLEAN of `vis` (`(nrow, nchan)` complex) with gridding
    weights `weights` (same shape; reader weight times imaging weight, zero
    for visibilities to ignore); `uvw` is `(nrow, 3)` metres and `freq`
    `(nchan,)` Hz.

    `rule` is "clark", "provable" or "mgain" (with `mgain`); `beam` is
    "exact" (a PSF on a grid twice the image, exact subtraction anywhere) or
    "image" (the image-size PSF WSClean subtracts); `patch` limits the
    subtraction to `±patch` pixels. `floor_iterations > 0` computes `Q_inf`
    first (needed for `floor_tolerance`, the greedy ratio and the reducible
    fraction). Returns a dict with `model`, `residual` (the exact residual
    image of the final model), `summary` and `cycles` (one dict per major
    cycle; `gap_relative` is the Gram-consistency gap in units of `Q`).
    """
    uvw = np.ascontiguousarray(uvw, np.float64)
    freq = np.ascontiguousarray(freq, np.float64).ravel()
    vis = np.ascontiguousarray(vis, np.complex128)
    weights = np.ascontiguousarray(weights, np.float64)
    nrow, nchan = vis.shape
    if uvw.shape != (nrow, 3) or freq.shape != (nchan,) or weights.shape != vis.shape:
        raise ValueError("uvw (nrow, 3), freq (nchan,), vis and weights (nrow, nchan)")
    if rule not in RULES or beam not in BEAMS:
        raise ValueError(f"rule in {sorted(RULES)}, beam in {sorted(BEAMS)}")
    model = np.zeros((side, side), np.float64)
    residual = np.zeros((side, side), np.float64)
    cycles = np.zeros((max_major, len(CYCLE_FIELDS)), np.float64)
    summary = np.zeros(len(SUMMARY_FIELDS), np.float64)
    status = core.extension().clean_certified(
        nrow,
        nchan,
        uvw,
        freq,
        vis.view(np.float64),
        weights,
        int(side),
        float(scale_arcsec) * ARCSEC,
        float(epsilon),
        bool(wgridding),
        bool(flip_v),
        bool(flip_w),
        float(gain),
        float(threshold),
        int(max_components),
        int(max_major),
        0 if max_minor is None else int(max_minor),
        RULES[rule],
        float(mgain),
        -1 if patch is None else int(patch),
        BEAMS[beam],
        int(floor_iterations),
        0.0 if floor_tolerance is None else float(floor_tolerance),
        float(divergence_limit),
        bool(audit),
        int(erc_max_k),
        model,
        residual,
        cycles,
        summary,
    )
    if status:
        raise ValueError(f"core certified CLEAN refused its inputs (status {status})")
    info = {}
    for name, value in zip(SUMMARY_FIELDS, summary.tolist(), strict=True):
        info[name] = int(value) if name in INTEGER_FIELDS else _nan_to_none(value)
    info["stop"] = STOPS[int(summary[SUMMARY_FIELDS.index("stop")])]
    rows = []
    for row in cycles[: info["major_cycles"]]:
        entry = {}
        for name, value in zip(CYCLE_FIELDS, row.tolist(), strict=True):
            entry[name] = int(value) if name in INTEGER_FIELDS else _nan_to_none(value)
        entry["stop"] = MINOR_STOPS[int(row[CYCLE_FIELDS.index("stop")])]
        rows.append(entry)
    return {"model": model, "residual": residual, "summary": info, "cycles": rows}
