"""C1: the closure-invariant comparator arm on L1's frozen campaign (research/c1-closure-arm.md).

L1's `core_campaign_array.run` runs unedited on all stations of LUNO chunk 0.
Two scoped hooks keep references to what the C1 arms need: `build_state`
keeps the state and `extra`, and `tv_loop` keeps the `original` base solve of
the `tv` loop (with its policy features). After the run, in the same process:

- the closure kernel (`rang.core_closure`) scores every training sample
  with closure traces (primary), closure phases and log closure amplitudes,
  each checked against the NumPy reference on a subset;
- the closure-TV map on the gain grid, per baseline and per antenna, and the
  Q1 statistics against the gain-TV map of `original`;
- `closure-tv-policy`: L1's `tv_loop`, unedited, on the captured base with
  the closure-TV map as the guidance;
- `closure-outlier`: the closure-outlier mask (robust z >= 5, 2 % budget),
  solved and imaged by L1's functions;
- the frozen, amendment 1 and A1-drop calls of every pre-registered pair,
  and the Q3 overlaps.

Original FLAG and FLAG_ROW are never modified; nothing is written outside the
run directory.
"""

import json
import platform
import time
import warnings
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from . import core, core_campaign, core_closure
from . import core_campaign_array as array
from .core_campaign import array_sha256, call, file_sha256, rss_mb, write_json
from .core_policy import fixed_support_tv, gain_tv, polar_gauge
from .core_workflow import gain_grid

ROOT = core_campaign.ROOT
L1_RUN = ROOT / "outputs/luno-array-campaign-20261030-01"
FAMILIES = ("trace", "phase", "logamp")
PRIMARY = "trace"
Z_OUTLIER = 5.0
Z_REPORTED = (3.0, 8.0)
MIN_AVAILABLE_GIB = 16
GNSS_MHZ = (1145.8, 1301.0)
GATE_BASELINES = 20
GATE_TOLERANCE = 1e-5
Q1_RELIABLE = 0.5
Q1_DISTINCT_R2 = 0.25
Q1_REDUNDANT = 0.7
NEW_ARMS = ("closure-tv-policy", "closure-outlier")
PAIRS = (
    ("closure-tv-policy", "tricolour-firstpass"),
    ("closure-tv-policy", "original"),
    ("closure-tv-policy", "tv-policy"),
    ("closure-outlier", "tricolour-firstpass"),
    ("closure-outlier", "original"),
    ("closure-outlier", "tv-policy"),
)
CODE_FILES = (
    *array.CODE_FILES,
    "python/rang/core_closure.py",
    "python/rang/core_campaign_closure.py",
    "core/src/closure.rs",
    "core/src/ffi_closure.rs",
)


# --- hooks ---------------------------------------------------------------------


class Hooks:
    """Scoped references to L1's state, `extra` and the `tv` loop's base."""

    def __init__(self):
        self.state = self.extra = self.base = None
        self.nant = None
        self.tv_loop = array.tv_loop

    @contextmanager
    def installed(self):
        build, loop = array.build_state, array.tv_loop
        self.tv_loop = loop

        def build_state(arrays, extra, nant, *args, **kwargs):
            state = build(arrays, extra, nant, *args, **kwargs)
            corr = tuple(int(c) for c in extra["corr_type"])
            if corr != core_closure.CORR_LINEAR:
                raise RuntimeError(f"CORR_TYPE {corr} is not XX, XY, YX, YY")
            self.state, self.extra, self.nant = state, extra, nant
            return state

        def tv_loop(state, base, scale, prefix):
            if prefix == "tv":
                self.base = base
            return loop(state, base, scale, prefix)

        array.build_state, array.tv_loop = build_state, tv_loop
        try:
            yield self
        finally:
            array.build_state, array.tv_loop = build, loop


# --- closure scores and maps ------------------------------------------------------


def time_index(state):
    return np.unique(state["times"], return_inverse=True)[1]


def cross_stations(state):
    p, q = state["antenna1"], state["antenna2"]
    cross = p != q
    return np.unique(np.concatenate([p[cross], q[cross]]))


def family_scores(state, family, nant, stations):
    return core_closure.scores(
        state["data"],
        state["model"],
        state["weights"],
        state["train"],
        state["antenna1"],
        state["antenna2"],
        time_index(state),
        stations,
        family,
        nant=nant,
        min_closures=min(core_closure.MIN_CLOSURES, len(stations) - 2),
        reroute=core_closure.REROUTE,
    )


def kernel_gate(state, out, family, stations, nbaselines=GATE_BASELINES):
    """Gate 4: the kernel against the NumPy reference on 2 integrations x
    2 channels x `nbaselines` baselines of the run's data."""
    started = time.perf_counter()
    ti = time_index(state)
    ntime = int(ti.max()) + 1
    nchan = state["data"].shape[1]
    min_closures = min(core_closure.MIN_CLOSURES, len(stations) - 2)
    ref = core_closure.Reference(
        state["data"],
        state["model"],
        state["weights"],
        state["train"],
        state["antenna1"],
        state["antenna2"],
        ti,
        stations,
    )
    pairs = sorted({(a, b) for (_, a, b) in ref.rows})
    chosen = [pairs[int(k)] for k in np.linspace(0, len(pairs) - 1, nbaselines)]
    chosen = sorted(set(chosen))
    worst, compared, count_equal, nan_equal = 0.0, 0, True, True
    for t in sorted({0, ntime // 2}):
        for c in sorted({nchan // 3, 2 * nchan // 3}):
            for a, b in chosen:
                row = ref.rows.get((t, a, b))
                if row is None:
                    continue
                r, v, n = ref.sample(family, t, a, b, c, nchan, ntime, min_closures)
                if not state["train"][row, c]:
                    r, v, n = np.nan, np.nan, 0
                k = (out["residual"][row, c], out["tv"][row, c])
                count_equal &= int(out["count"][row, c]) == n
                for mine, theirs in zip(k, (r, v)):
                    if np.isnan(theirs) or np.isnan(mine):
                        nan_equal &= bool(np.isnan(theirs) and np.isnan(mine))
                        continue
                    worst = max(
                        worst, abs(float(mine) - theirs) / max(abs(theirs), 1e-30)
                    )
                compared += 1
    return {
        "samples": compared,
        "baselines": len(chosen),
        "max_relative_difference": worst,
        "counts_equal": bool(count_equal),
        "nan_pattern_equal": bool(nan_equal),
        "tolerance": GATE_TOLERANCE,
        "pass": bool(
            compared > 0 and count_equal and nan_equal and worst <= GATE_TOLERANCE
        ),
        "seconds": time.perf_counter() - started,
    }


def gain_tv_map(state, base, scale):
    """The TV policy's guidance map: `gain_tv` of the polar-gauge gains."""
    _, _, gain_times, gain_freqs = gain_grid(state, *core_campaign.GRID)
    gains = base["diagnostics"]["gains"]
    aligned, ok = polar_gauge(gains, base["diagnostics"]["gain_valid"])
    tv = gain_tv(aligned, ok, gain_times, gain_freqs, scale=scale)
    return tv["map"], ok


def _summary(values):
    v = np.asarray(values, np.float64)
    v = v[np.isfinite(v)]
    if not len(v):
        return None
    q = np.quantile(v, [0.01, 0.25, 0.5, 0.75, 0.99])
    return {
        "n": len(v),
        "mean": float(v.mean()),
        "q01": float(q[0]),
        "q25": float(q[1]),
        "median": float(q[2]),
        "q75": float(q[3]),
        "q99": float(q[4]),
        "max": float(v.max()),
    }


def _nan_list(x, digits=6):
    return [None if not np.isfinite(v) else round(float(v), digits) for v in x]


def q1_statistics(cmap, cmap_even, cmap_odd, pairs, nant, gmap, gvalid):
    """The protocol's Q1 numbers and call for one family's baseline map."""
    p, q = pairs[:, 0], pairs[:, 1]
    amap = core_closure.antenna_map(cmap, pairs, nant)
    guidance = np.maximum(gmap[:, :, p], gmap[:, :, q])
    gb_valid = gvalid[:, :, p] & gvalid[:, :, q]
    rho_ant = core_closure.spearman(amap[gvalid], gmap[gvalid])
    rho_bl = core_closure.spearman(cmap[gb_valid], guidance[gb_valid])
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        c_chan = np.nanmedian(np.where(gb_valid, cmap, np.nan), axis=(0, 2))
        g_chan = np.nanmedian(np.where(gb_valid, guidance, np.nan), axis=(0, 2))
        c_ant = np.nanmedian(amap, axis=(0, 1))
        g_ant = np.nanmedian(np.where(gvalid, gmap, np.nan), axis=(0, 1))
    rho_chan = core_closure.spearman(c_chan, g_chan)
    r2_bl = core_closure.r_squared(cmap[gb_valid], guidance[gb_valid])
    r2_add = core_closure.additive_r_squared(cmap, pairs, nant)
    rho_half = core_closure.spearman(cmap_even, cmap_odd)
    amap_even = core_closure.antenna_map(cmap_even, pairs, nant)
    amap_odd = core_closure.antenna_map(cmap_odd, pairs, nant)
    rho_half_ant = core_closure.spearman(amap_even, amap_odd)
    brown = None if rho_half is None else 2 * rho_half / (1 + rho_half)
    if rho_half is None or rho_half < Q1_RELIABLE:
        verdict = "noise-dominated"
    elif rho_bl is not None and rho_bl >= Q1_REDUNDANT:
        verdict = "redundant"
    elif r2_bl is not None and r2_bl <= Q1_DISTINCT_R2:
        verdict = "distinct"
    else:
        verdict = "partly explained by the gain map"
    return {
        "rho_ant": rho_ant,
        "rho_bl": rho_bl,
        "rho_chan": rho_chan,
        "r2_bl": r2_bl,
        "r2_add": r2_add,
        "rho_half": rho_half,
        "rho_half_spearman_brown": brown,
        "rho_half_ant": rho_half_ant,
        "call": verdict,
        "thresholds": {
            "reliable": Q1_RELIABLE,
            "distinct_r2": Q1_DISTINCT_R2,
            "redundant_rho": Q1_REDUNDANT,
        },
        "map_bins_finite": int(np.isfinite(cmap).sum()),
        "map_bins_compared": int((gb_valid & np.isfinite(cmap)).sum()),
        "closure_map": _summary(cmap),
        "gain_guidance": _summary(guidance[gb_valid]),
        "per_frequency_bin_median": {
            "closure": _nan_list(c_chan),
            "gain": _nan_list(g_chan),
        },
        "per_antenna_median": {
            "closure": _nan_list(c_ant),
            "gain": _nan_list(g_ant),
        },
    }


def closure_maps(state, out, labels, shape, time_map, freq_map):
    """The baseline map of closure TV and its even/odd-channel halves."""
    train = state["train"]
    nchan = train.shape[1]
    cmap, counts = core_closure.bin_map(
        out["tv"], train, time_map, freq_map, labels, shape
    )
    halves = []
    for parity in (0, 1):
        keep = (np.arange(nchan) % 2) == parity
        mask = train & keep[None]
        halves.append(
            core_closure.bin_map(out["tv"], mask, time_map, freq_map, labels, shape)[0]
        )
        del mask
    return cmap, counts, halves[0], halves[1]


def calibration(state, out, nstations):
    """Median R^2 (the weight-scale check), the scored fraction and the
    closure survival (count over the N - 2 a baseline can lead)."""
    train = state["train"]
    r = out["residual"][train]
    n = out["count"][train].astype(np.float64)
    finite = np.isfinite(r)
    return {
        "median_residual_squared": float(np.median(r[finite].astype(np.float64) ** 2))
        if finite.any()
        else None,
        "scored_fraction": float(finite.mean()) if len(r) else None,
        "tv_scored_fraction": float(np.isfinite(out["tv"][train]).mean())
        if len(r)
        else None,
        "mean_closures": float(n.mean()) if len(n) else None,
        "survival": float(n.mean() / (nstations - 2)) if len(n) else None,
        "residual": _summary(r),
        "tv": _summary(out["tv"][train]),
    }


# --- arms ------------------------------------------------------------------------


def closure_guidance(
    state, base, cmap, labels, time_map, freq_map, block=array.ROW_BLOCK
):
    """The base's features with the closure-TV map as guidance."""
    features = base["features"]
    nchan = state["train"].shape[1]
    rows, chans = np.divmod(features["cells"], nchan)
    guidance = cmap[time_map[rows], freq_map[chans], labels[rows]]
    parts = []
    for s in array.row_blocks(len(labels), block):
        g = cmap[time_map[s][:, None], freq_map[None], labels[s][:, None]]
        parts.append(g[state["train"][s] & np.isfinite(g) & (g > 0)])
    positive = np.concatenate(parts) if parts else np.zeros(0)
    scale = float(np.median(positive)) if len(positive) else 1.0
    return {**features, "guidance": guidance, "guidance_scale": scale}


def unguided_equal(closure_trials, tv_trials):
    """Gate 3: the closure loop's alpha = 0 trials reproduce the TV loop's."""
    fields = ("mask_sha256", "duplicate_mask", "objective", "mask_count", "accepted")

    def unguided(trials):
        return {
            t["policy"]["threshold"]: {f: t.get(f) for f in fields}
            for t in trials
            if t.get("policy") and t["policy"]["tv_weight"] == 0
        }

    a, b = unguided(closure_trials), unguided(tv_trials)
    return {"equal": bool(a == b and len(a) > 0), "trials": len(a)}


def arm_entry(state, solve, label, base_edges, ntrain, image):
    added = array.additions_dense(state, solve["added"])
    final = array.final_flags_summary(state, added)
    return {
        "label": label,
        "source": solve["label"],
        "policy": solve.get("policy"),
        "metrics": solve["metrics"],
        "fixed_support_tv_vs_original": fixed_support_tv(
            solve["tv"]["edges"], base_edges
        ),
        "additions": int(added.sum()),
        "additions_fraction_of_train": float(added.sum() / ntrain),
        "final_flag_fraction": final["final_flag_fraction"],
        "original_flag_fraction": float(state["original_flags"].mean()),
        "flag_row_unchanged": final["flag_row_unchanged"],
        "superset_of_original": final["superset_of_original"],
        "holdout_cells_added": int(np.count_nonzero(added & ~state["train"])),
        "additions_sha256": array_sha256(added),
        "gains_sha256": array_sha256(solve["diagnostics"]["gains"]),
        "image": image,
    }


def image_or_reuse(state, extra, solve, run_dir, label, result, arms):
    """L1's `image_arm` with the run's boxes, unless an arm with the same
    additions and gains was already imaged (then its metrics are reused)."""
    added = array.additions_dense(state, solve["added"])
    key = (array_sha256(added), array_sha256(solve["diagnostics"]["gains"]))
    for other, arm in arms.items():
        if arm is not None and (arm["additions_sha256"], arm["gains_sha256"]) == key:
            return {**arm["image"], "reused_from": other}, 0.0
    started = time.perf_counter()
    settings = result["settings"]
    metrics, products = array.image_arm(
        state,
        extra,
        solve,
        Path(run_dir) / "images",
        label,
        settings["image"],
        settings["channel_groups"],
        boxes=result["boxes"],
    )
    del products
    return metrics, time.perf_counter() - started


def load_solve(run_dir, label):
    with np.load(Path(run_dir) / "gains" / f"{label}.npz") as g:
        return {
            "label": label,
            "diagnostics": {"gains": g["gains"], "gain_valid": g["gain_valid"]},
        }


def load_additions(run_dir, label):
    with np.load(Path(run_dir) / "flags" / f"{label}.npz") as f:
        return f["additions"]


# --- A1 ----------------------------------------------------------------------------


def station_support(state, mask, time_map, freq_map, nant, nfb, block=array.ROW_BLOCK):
    """Training-cell counts per (time bin, frequency bin, station) of `mask`."""
    ntb = int(time_map.max()) + 1
    counts = np.zeros(ntb * nfb * nant, np.int64)
    p, q = state["antenna1"], state["antenna2"]
    for s in array.row_blocks(len(p), block):
        r, c = np.nonzero(mask[s])
        base = (time_map[s][r] * nfb + freq_map[c]) * nant
        counts += np.bincount(base + p[s][r], minlength=counts.size)
        counts += np.bincount(base + q[s][r], minlength=counts.size)
    return counts.reshape(ntb, nfb, nant)


def emptied_bins(state, additions, time_map, freq_map, nant, nfb):
    """A1: station-bins with training support in `original` and none in
    `train & ~additions`, per arm and their union."""
    support = station_support(state, state["train"], time_map, freq_map, nant, nfb)
    per_arm, union = {}, np.zeros(support.shape, bool)
    for label, added in additions.items():
        after = station_support(
            state, state["train"] & ~added, time_map, freq_map, nant, nfb
        )
        emptied = (support > 0) & (after == 0)
        per_arm[label] = int(emptied.sum())
        union |= emptied
    return union, per_arm


def bin_cells(state, emptied, time_map, freq_map, block=array.ROW_BLOCK):
    """Samples on a row whose either station is emptied at the sample's bin."""
    out = np.empty(state["train"].shape, bool)
    p, q = state["antenna1"], state["antenna2"]
    for s in array.row_blocks(len(p), block):
        t, f = time_map[s][:, None], freq_map[None]
        out[s] = emptied[t, f, p[s][:, None]] | emptied[t, f, q[s][:, None]]
    return out


# --- calls ---------------------------------------------------------------------------


def pair_calls(state, solves, arms, drop, time_map, freq_map):
    """Each pair's frozen, amendment 1 (matched) and A1-drop calls."""
    out = []
    ok_cache = {}

    def ok(label):
        if label not in ok_cache:
            ok_cache[label] = array.valid_prediction(
                state, solves[label]["diagnostics"]["gain_valid"], time_map, freq_map
            )
        return ok_cache[label]

    keep = ~drop
    for cand, ref in PAIRS:
        frozen = array.available_hypothesis(arms, cand, ref)
        entry = {"candidate": cand, "reference": ref, "frozen": frozen}
        if solves.get(cand) is None or solves.get(ref) is None:
            entry["matched"] = entry["a1_drop"] = {"call": "undecidable"}
            out.append(entry)
            continue
        both = ok(cand) & ok(ref)
        masks = {"validation": state["validation"] & both, "test": state["test"] & both}
        lc = array.restricted_losses(state, solves[cand], masks)
        lr = array.restricted_losses(state, solves[ref], masks)
        entry["matched"] = {
            "matched_test_cells": lc["test"]["cells"],
            "dropped_test_cells": int(np.count_nonzero(state["test"] & ~both)),
            "losses": {"candidate": lc, "reference": lr},
            "mse_test": call(lc["test"]["loss"], lr["test"]["loss"]),
            "mse_validation": call(lc["validation"]["loss"], lr["validation"]["loss"]),
        }
        masks = {"validation": state["validation"] & keep, "test": state["test"] & keep}
        lc = array.restricted_losses(state, solves[cand], masks)
        lr = array.restricted_losses(state, solves[ref], masks)
        invalid = any(x[k]["invalid"] for x in (lc, lr) for k in ("validation", "test"))
        if invalid:
            masks = {k: v & both for k, v in masks.items()}
            lc = array.restricted_losses(state, solves[cand], masks)
            lr = array.restricted_losses(state, solves[ref], masks)
        entry["a1_drop"] = {
            "dropped_test_cells": int(np.count_nonzero(state["test"] & drop)),
            "dropped_validation_cells": int(
                np.count_nonzero(state["validation"] & drop)
            ),
            "matched_fallback": bool(invalid),
            "test_cells": lc["test"]["cells"],
            "losses": {"candidate": lc, "reference": lr},
            "mse_test": call(lc["test"]["loss"], lr["test"]["loss"]),
            "mse_validation": call(lc["validation"]["loss"], lr["validation"]["loss"]),
        }
        out.append(entry)
    return out


def overlap_mask(cells, other, ntrain):
    """`core_closure.overlap` against a boolean `(row, chan)` set."""
    flat = other.reshape(-1)
    cells = np.asarray(cells, np.int64)
    both = int(flat[cells].sum()) if len(cells) else 0
    n_other = int(flat.sum())
    of_mask = both / len(cells) if len(cells) else None
    chance = n_other / ntrain if ntrain else None
    lift = of_mask / chance if of_mask is not None and chance else None
    return {
        "mask": len(cells),
        "other": n_other,
        "both": both,
        "fraction_of_mask": of_mask,
        "fraction_of_other": both / n_other if n_other else None,
        "chance": chance,
        "lift": lift,
        "coincides": bool(
            of_mask is not None and lift is not None and of_mask >= 0.10 and lift >= 3.0
        ),
    }


# --- the C1 arms after L1's run ------------------------------------------------------


def closure_arms(run_dir, hooks, result, started=None):
    """Everything C1 adds after L1's unedited run; writes `c1.json`."""
    run_dir = Path(run_dir)
    state, extra, base, nant = hooks.state, hooks.extra, hooks.base, hooks.nant
    if state is None or base is None:
        raise RuntimeError("the hooks did not capture the state and the tv base")
    stages = array.Stages()
    train = state["train"]
    ntrain = int(np.count_nonzero(train))
    time_map, freq_map, gain_times, gain_freqs = gain_grid(state, *core_campaign.GRID)
    shape_bins = (len(gain_times), len(gain_freqs))
    labels, pairs = core_closure.baseline_index(
        state["antenna1"], state["antenna2"], nant
    )
    stations = cross_stations(state)
    scale0 = result["arms"]["original"]["metrics"]["scale"]
    gates = {
        "base_gains_equal_original": array_sha256(base["diagnostics"]["gains"])
        == result["arms"]["original"]["gains_sha256"],
        "corr_type": [int(c) for c in extra["corr_type"]],
    }
    gmap, gvalid = gain_tv_map(state, base, scale0)
    # A1: emptied station-bins, after the split and before any C1 solve.
    mark = stages.start()
    tric = {
        label: load_additions(run_dir, label)
        for label in ("tricolour-firstpass", "tricolour-mild")
    }
    emptied, per_arm = emptied_bins(
        state, tric, time_map, freq_map, nant, len(gain_freqs)
    )
    drop = bin_cells(state, emptied, time_map, freq_map)
    a1 = {
        "emptied_station_bins": per_arm,
        "emptied_union": int(emptied.sum()),
        "dropped_validation": int(np.count_nonzero(state["validation"] & drop)),
        "dropped_test": int(np.count_nonzero(state["test"] & drop)),
        "emptied_sha256": array_sha256(emptied),
    }
    stages.stop("a1_bins", mark)
    families, cmap_trace, trace_cells, phase_cells = {}, None, None, None
    for family in FAMILIES:
        mark = stages.start()
        out = family_scores(state, family, nant, stations)
        stages.stop(f"kernel_{family}", mark)
        mark = stages.start()
        gate = kernel_gate(state, out, family, stations)
        stages.stop(f"gate_{family}", mark)
        mark = stages.start()
        cmap, counts, even, odd = closure_maps(
            state, out, labels, (*shape_bins, len(pairs)), time_map, freq_map
        )
        q1 = q1_statistics(cmap, even, odd, pairs, nant, gmap, gvalid)
        stages.stop(f"maps_{family}", mark)
        mark = stages.start()
        z = core_closure.robust_z(out["residual"], train, labels)
        cells, proposed = core_closure.top_mask(
            z, train, Z_OUTLIER, core_campaign.MAX_FRACTION
        )
        zf = z[train]
        families[family] = {
            "kernel_gate": gate,
            "calibration": calibration(state, out, len(stations)),
            "q1": q1,
            "outlier": {
                "threshold": Z_OUTLIER,
                "proposed": proposed,
                "selected": len(cells),
                "selected_sha256": array_sha256(np.asarray(cells, np.int64)),
                "counts_at": {
                    f"{t:g}": int(np.count_nonzero(zf >= t))
                    for t in (*Z_REPORTED, Z_OUTLIER)
                },
                "z": _summary(zf),
            },
            "map_bins_with_samples": int((counts > 0).sum()),
        }
        del zf
        stages.stop(f"outlier_{family}", mark)
        if family == PRIMARY:
            cmap_trace, trace_cells = cmap, cells
        elif family == "phase":
            phase_cells = cells
        del out, z
    # (i) closure-TV-guided policy on the captured base.
    mark = stages.start()
    features_c = closure_guidance(state, base, cmap_trace, labels, time_map, freq_map)
    base_c = {**base, "features": features_c}
    trials, best, unguided = hooks.tv_loop(state, base_c, scale0, "closure-tv")
    stages.stop("closure_tv_loop", mark)
    del base_c
    tv_trials = json.loads((run_dir / "candidates.json").read_text())["tv-policy"]
    gates["closure_loop_unguided_equal_tv_loop"] = unguided_equal(trials, tv_trials)
    solves = {
        "closure-tv-policy": {
            **array.strip(best["solve"]),
            "label": "closure-tv-policy",
            "policy": best["policy"],
        }
    }
    guided = [t for t in trials if t.get("policy") and t["policy"]["tv_weight"] > 0]
    selection = {
        "policy": best["policy"],
        "objective": best["objective"],
        "additions": len(best["solve"]["added"]),
        "guided_trials": len(guided),
        "guided_solved": sum("objective" in t for t in guided),
        "guided_admissible": sum(t.get("objective") is not None for t in guided),
        "guided_accepted": sum(bool(t.get("accepted")) for t in guided),
        "guided_selected": bool(best["policy"] and best["policy"]["tv_weight"] > 0),
        "unguided_best": None if unguided is None else unguided["policy"],
        "guidance_scale": features_c["guidance_scale"],
        "guidance_finite_candidates": int(np.isfinite(features_c["guidance"]).sum()),
        "candidates": len(features_c["cells"]),
    }
    # (ii) the closure-outlier mask.
    mark = stages.start()
    if len(trace_cells):
        added = np.zeros(train.shape, bool)
        added.reshape(-1)[trace_cells] = True
        solves["closure-outlier"] = array.solve_arm(
            state, added, "closure-outlier", scale=scale0
        )
        solves["closure-outlier"].pop("features", None)
        del added
        outlier_solved = True
    else:
        solves["closure-outlier"] = {**array.strip(base), "label": "closure-outlier"}
        outlier_solved = False
    stages.stop("solve_closure_outlier", mark)
    # Images and arm entries.
    base_edges = None
    with np.load(run_dir / "gains" / "original.npz") as g:
        aligned, ok = polar_gauge(g["gains"], g["gain_valid"])
        base_edges = gain_tv(aligned, ok, gain_times, gain_freqs, scale=scale0)["edges"]
    arms = dict(result["arms"])
    new_arms = {}
    for label in NEW_ARMS:
        mark = stages.start()
        image, seconds = image_or_reuse(
            state, extra, solves[label], run_dir, label, result, arms
        )
        entry = arm_entry(state, solves[label], label, base_edges, ntrain, image)
        entry["image_seconds"] = seconds
        new_arms[label] = arms[label] = entry
        np.savez_compressed(
            run_dir / "flags" / f"{label}.npz",
            additions=array.additions_dense(state, solves[label]["added"]),
        )
        np.savez_compressed(
            run_dir / "gains" / f"{label}.npz",
            gains=solves[label]["diagnostics"]["gains"],
            gain_valid=solves[label]["diagnostics"]["gain_valid"],
        )
        stages.stop(f"image_{label}", mark)
    new_arms["closure-outlier"]["solved"] = outlier_solved
    # Calls.
    mark = stages.start()
    for label in ("original", "tricolour-firstpass", "tv-policy"):
        if result["arms"].get(label) is not None:
            solves[label] = load_solve(run_dir, label)
    calls = pair_calls(state, solves, arms, drop, time_map, freq_map)
    stages.stop("calls", mark)
    # Q3 overlaps.
    mark = stages.start()
    freqs_mhz = np.asarray(state["frequencies"]) / 1e6
    gnss = (freqs_mhz >= GNSS_MHZ[0]) & (freqs_mhz <= GNSS_MHZ[1])
    residual_candidates = np.zeros(train.shape, bool)
    residual_candidates.reshape(-1)[base["features"]["cells"]] = True
    sets = {
        "tricolour-firstpass": tric["tricolour-firstpass"],
        "tricolour-mild": tric["tricolour-mild"],
        "a1-emptied-bins": train & drop,
        "gnss-range": train & gnss[None],
        "l1-residual-candidates": residual_candidates,
        "tv-policy": load_additions(run_dir, "tv-policy")
        if result["arms"].get("tv-policy") is not None
        else np.zeros(train.shape, bool),
    }
    q3 = {
        name: {k: overlap_mask(cells, x, ntrain) for k, x in sets.items()}
        for name, cells in (("trace", trace_cells), ("phase", phase_cells))
    }
    q3["trace_vs_phase"] = core_closure.overlap(trace_cells, phase_cells, ntrain)
    del sets, residual_candidates
    stages.stop("q3", mark)
    rec = stages.records
    rstages = result["stages"]
    closure_chain = (
        rec["kernel_trace"]["seconds"]
        + rec["maps_trace"]["seconds"]
        + rec["closure_tv_loop"]["seconds"]
    )
    tv_chain = rstages["solve_original"]["seconds"] + rstages["tv_loop"]["seconds"]
    port = rstages["flag_tricolour-firstpass"]["seconds"]
    cost = {
        "closure_chain_seconds": closure_chain,
        "tv_chain_seconds": tv_chain,
        "tricolour_firstpass_seconds": port,
        "closure_chain_over_tv_chain": closure_chain / tv_chain,
        "closure_chain_over_firstpass": closure_chain / port,
        "kernel_seconds": {f: rec[f"kernel_{f}"]["seconds"] for f in FAMILIES},
        "outlier_arm_seconds": rec["solve_closure_outlier"]["seconds"],
    }
    record = {
        "protocol": "research/c1-closure-arm.md",
        "label": result["label"],
        "stations": [int(s) for s in stations],
        "firstpass_additions": (result["arms"].get("tricolour-firstpass") or {}).get(
            "additions"
        ),
        "nant": nant,
        "baselines": len(pairs),
        "gain_grid": list(shape_bins),
        "gates": gates,
        "families": families,
        "closure_tv_policy": {"selection": selection, "trials": trials},
        "arms": new_arms,
        "a1": a1,
        "calls": calls,
        "q3": q3,
        "cost": cost,
        "stages": rec,
        "max_rss_mb": rss_mb(),
        "process_seconds": None if started is None else time.perf_counter() - started,
        "library": str(core_closure.library_path()),
        "library_sha256": file_sha256(core_closure.library_path()),
        "core_library_sha256": file_sha256(core.library_path()),
        "code_sha256": {name: file_sha256(ROOT / name) for name in CODE_FILES},
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    write_json(run_dir / "c1.json", record)
    return record


def run(run_dir, stations=None, precondition_dir=None, label="frozen"):
    """L1's campaign unedited with the C1 hooks, then `c1.json`."""
    started = time.perf_counter()
    core_closure.library()  # build or load the kernel before any timing
    hooks = Hooks()
    with hooks.installed():
        result = array.run(
            run_dir,
            stations=stations,
            precondition_dir=precondition_dir,
            label=f"{label}; C1 closure arms",
        )
    record = closure_arms(run_dir, hooks, result, started)
    hooks.state = hooks.base = None
    return result, record


# --- the checker and the archive ----------------------------------------------------


def _load(path):
    return json.loads(Path(path).read_text())


def check(run_dir, precondition_dir, check_dir, l1_run=L1_RUN):
    """The protocol's criteria 1-6 and the Q1-Q3 summary."""
    from . import core_campaign_1830, core_campaign_fieldmodel

    run_dir, check_dir = Path(run_dir), Path(check_dir)
    check_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    criteria = {}
    pre = _load(Path(precondition_dir) / "result.json")
    replay_dir = Path(precondition_dir) / "replay"
    replay = _load(replay_dir / "result.json")
    replay["_candidates"] = _load(replay_dir / "candidates.json")
    tolerant = core_campaign_1830.compare_replay_tolerant(
        replay,
        _load(array.K_RUN / "result.json"),
        _load(array.K_RUN / "candidates.json"),
    )
    criteria["1_precondition"] = {
        "pass": bool(
            pre["passed"]["k_precondition"]
            and pre["passed"]["groups"]
            and tolerant["all_equal"]
        ),
        "passed_as_l1": pre["passed"],
        "replay_tolerant_all_equal": tolerant["all_equal"],
    }
    result = _load(run_dir / "result.json")
    candidates = _load(run_dir / "candidates.json")
    c1 = _load(run_dir / "c1.json")
    gate = core_campaign_fieldmodel.compare_with_l1(
        result,
        candidates,
        _load(Path(l1_run) / "result.json"),
        _load(Path(l1_run) / "candidates.json"),
    )
    criteria["2_l1_reproduced"] = {"pass": gate["equal"], **gate}
    kernel = {f: v["kernel_gate"]["pass"] for f, v in c1["families"].items()}
    criteria["3_gates"] = {
        "pass": bool(
            c1["gates"]["base_gains_equal_original"]
            and c1["gates"]["closure_loop_unguided_equal_tv_loop"]["equal"]
            and all(kernel.values())
        ),
        "base_gains_equal_original": c1["gates"]["base_gains_equal_original"],
        "unguided_equal": c1["gates"]["closure_loop_unguided_equal_tv_loop"],
        "kernel": kernel,
    }
    summary = array.check(run_dir, precondition_dir, check_dir / "l1-check")
    criteria["4_l1_criteria_evaluated"] = {
        "pass": True,
        "l1_criteria": {k: v["pass"] for k, v in summary["criteria"].items()},
    }
    q = questions(c1)
    criteria["5_questions"] = {
        "pass": q["q1"]["call"] is not None
        and all(
            "call" in c["matched"] or "mse_test" in c["matched"] for c in c1["calls"]
        ),
    }
    criteria["6_outputs"] = {
        "pass": all(
            (run_dir / n).exists()
            for n in ("result.json", "candidates.json", "c1.json", "receipt.json")
        )
    }
    out = {
        "protocol": "research/c1-closure-arm.md",
        "run": str(run_dir),
        "precondition": str(precondition_dir),
        "criteria": criteria,
        "all_pass": all(c["pass"] for c in criteria.values()),
        "questions": q,
        "result_sha256": file_sha256(run_dir / "result.json"),
        "candidates_sha256": file_sha256(run_dir / "candidates.json"),
        "c1_sha256": file_sha256(run_dir / "c1.json"),
        "check_seconds": time.perf_counter() - started,
    }
    write_json(check_dir / "result.json", out)
    return out


def _call(x, key="mse_test"):
    v = (x or {}).get(key) or {}
    return {"ratio": v.get("ratio"), "call": v.get("call", "undecidable")}


def questions(c1):
    """Q1-Q3 in the protocol's terms, from `c1.json`."""
    fam = c1["families"]
    q1 = {
        "call": fam[PRIMARY]["q1"]["call"],
        "by_family": {
            f: {
                k: v["q1"][k]
                for k in (
                    "rho_ant",
                    "rho_bl",
                    "rho_chan",
                    "r2_bl",
                    "r2_add",
                    "rho_half",
                    "rho_half_spearman_brown",
                    "rho_half_ant",
                    "call",
                )
            }
            for f, v in fam.items()
        },
    }
    sel = c1["closure_tv_policy"]["selection"]
    q2 = {
        "selection": sel,
        "outlier": fam[PRIMARY]["outlier"],
        "calls": [
            {
                "pair": f"{c['candidate']} vs {c['reference']}",
                "frozen_mse_test": _call(c["frozen"]),
                "frozen_residual_rms": _call(c["frozen"], "residual_rms"),
                "matched_mse_test": _call(c["matched"]),
                "a1_drop_mse_test": _call(c["a1_drop"]),
                "a1_matched_fallback": c["a1_drop"].get("matched_fallback"),
            }
            for c in c1["calls"]
        ],
    }
    by_pair = {c["pair"]: c for c in q2["calls"]}

    def has(pair, verdict):
        c = by_pair.get(pair)
        if c is None:
            return False
        keys = ("frozen_mse_test", "matched_mse_test", "a1_drop_mse_test")
        return any(c[k]["call"] == verdict for k in keys)

    def rms_not_worse(pair):
        c = by_pair.get(pair)
        return c is not None and c["frozen_residual_rms"]["call"] != "worse"

    policy_fp = "closure-tv-policy vs tricolour-firstpass"
    outlier_fp = "closure-outlier vs tricolour-firstpass"
    outlier_or = "closure-outlier vs original"
    firstpass_additions = c1.get("firstpass_additions")
    outlier_additions = (
        (c1.get("arms") or {}).get("closure-outlier", {}).get("additions")
    )
    q2["positive_policy"] = bool(
        sel["guided_selected"] and has(policy_fp, "better") and rms_not_worse(policy_fp)
    )
    q2["positive_outlier"] = bool(
        has(outlier_or, "better")
        and not has(outlier_fp, "worse")
        and firstpass_additions is not None
        and outlier_additions is not None
        and 0 < outlier_additions < firstpass_additions
    )
    q2["positive"] = q2["positive_policy"] or q2["positive_outlier"]
    q3 = {
        name: {
            k: {
                f: v.get(f)
                for f in (
                    "mask",
                    "other",
                    "both",
                    "fraction_of_mask",
                    "lift",
                    "coincides",
                )
            }
            for k, v in sets.items()
        }
        for name, sets in c1["q3"].items()
        if name != "trace_vs_phase"
    }
    q3["trace_vs_phase"] = c1["q3"]["trace_vs_phase"]
    return {"q1": q1, "q2": q2, "q3": q3}


ARCHIVE_ARM_KEYS = (
    "additions",
    "additions_fraction_of_train",
    "final_flag_fraction",
    "fixed_support_tv_vs_original",
    "additions_sha256",
    "gains_sha256",
)


def archive(check_dir, out_path):
    """The compact archive: arms, Q1-Q3, criteria, cost, hashes; no visibilities."""
    checked = _load(Path(check_dir) / "result.json")
    run_dir = Path(checked["run"])
    r = _load(run_dir / "result.json")
    c1 = _load(run_dir / "c1.json")
    arms = {}
    for label, arm in {**r["arms"], **c1["arms"]}.items():
        if arm is None:
            arms[label] = None
            continue
        m = arm["metrics"]
        image = arm["image"] or {}
        arms[label] = {
            **{k: arm.get(k) for k in ARCHIVE_ARM_KEYS},
            "policy": arm.get("policy"),
            "losses": m["losses"],
            "invalid_predictions": m["invalid_predictions"],
            "tv": m["tv"],
            "converged_fraction": m["solver"]["converged_fraction"],
            "valid_gain_fraction": m["valid_gain_fraction"],
            "residual_rms": image.get("residual_rms"),
            "peak": image.get("peak"),
            "image_reused_from": image.get("reused_from"),
        }
    trials = [
        {
            k: t.get(k)
            for k in (
                "trial",
                "policy",
                "mask_count",
                "mask_sha256",
                "duplicate_mask",
                "fixed_support_tv_vs_base",
                "losses",
                "objective",
                "accepted",
                "rejection",
                "converged_fraction",
            )
        }
        for t in c1["closure_tv_policy"]["trials"]
    ]
    families = {
        f: {
            "kernel_gate": v["kernel_gate"],
            "calibration": v["calibration"],
            "q1": v["q1"],
            "outlier": v["outlier"],
        }
        for f, v in c1["families"].items()
    }
    payload = {
        "schema_version": 1,
        "task": "C1",
        "protocol": "research/c1-closure-arm.md",
        "visibilities_redistributed": False,
        "run_dir": str(run_dir),
        "criteria": checked["criteria"],
        "all_pass": checked["all_pass"],
        "questions": checked["questions"],
        "split": r["split"],
        "arms": arms,
        "l1_hypotheses": r["hypotheses"],
        "l1_amendment_1_pairs": [
            {
                k: p.get(k)
                for k in ("candidate", "reference", "mse_test", "mse_validation")
            }
            for p in r["amendment_1"]["pairs"]
        ],
        "closure_tv_trials": trials,
        "families": families,
        "a1": c1["a1"],
        "calls": c1["calls"],
        "q3": c1["q3"],
        "cost": c1["cost"],
        "c1_stages": {k: v.get("seconds") for k, v in c1["stages"].items()},
        "l1_stages": {k: v.get("seconds") for k, v in r["stages"].items()},
        "wall_seconds": r["wall_seconds"],
        "process_seconds": c1["process_seconds"],
        "max_rss_mb": max(r["max_rss_mb"], c1["max_rss_mb"]),
        "gates": c1["gates"],
        "result_sha256": checked["result_sha256"],
        "candidates_sha256": checked["candidates_sha256"],
        "c1_sha256": checked["c1_sha256"],
        "check_result_sha256": file_sha256(Path(check_dir) / "result.json"),
        "library_sha256": c1["library_sha256"],
        "code_sha256": c1["code_sha256"],
    }
    write_json(out_path, payload)
    return payload


__all__ = [
    "FAMILIES",
    "PAIRS",
    "Hooks",
    "archive",
    "bin_cells",
    "check",
    "closure_arms",
    "closure_guidance",
    "emptied_bins",
    "kernel_gate",
    "overlap_mask",
    "pair_calls",
    "q1_statistics",
    "questions",
    "run",
    "station_support",
    "unguided_equal",
]
