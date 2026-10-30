"""Task L5-C measures and decision (research/l5c-casa-gaincal.md).

Usage (worktree venv, after `examples/oracle_casa_gaincal.py run`):
    python examples/compare_l5c.py compare {fixture,slice} outputs/l5c-<date>-NN
    python examples/compare_l5c.py archive outputs/l5c-<date>-NN [...] \
        [--out research/results/l5c-casa-gaincal.json]

`compare` solves the core arms (D, D49, D_T, R) on L5's problem, loads
QuartiCal's archived gains and CASA's caltables (through
`rang.formats.caltable.read`), and writes `<run>/<set>/compare.json`: the
held-out error on matched cells (total, parallel and cross hands), CASA's
applycal route against the reader route, gauge-invariant parallel-hand
products, the convergence probe (CASA restarts against D vs R and the gain
test at the cap, by identifiability stratum), cost, and the frozen decision.
`archive` gathers the derived numbers of the sets into one JSON (no
visibilities). Read-only on every input; `RAYON_NUM_THREADS` is the caller's.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))

from rang import (
    core,
    core_ms_write,
)
from rang import core_solver_study as study
from rang.formats import caltable

DELTA = 1e-4
THRESHOLDS = (1e-4, 1e-6)
TAU = 1e-7
CHUNK = 32
L5_ARCHIVE = ROOT / "research/results/l5-solver-science.json"
QUARTICAL = {
    "fixture": {
        "QC027": (
            "outputs/tv-response-wsl-20261029-01/clean/trials/clean-t2-f32/diagnostics.npz",
            True,
        ),
        "QC028": ("outputs/rv1-20261030-10/fixture/qc028u", True),
    },
    "slice": {
        "QC027": ("outputs/luno-solve-20261029-02/solve", False),
        "QC028": ("outputs/rv1-20261030-10/luno/qc028u", False),
    },
}
HANDS = {"total": [0, 1, 2, 3], "parallel": [0, 3], "cross": [1, 2]}
SPLITS = ("validation", "test")


def write_json(path, payload):
    def default(v):
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, np.generic):
            return v.item()
        return str(v)

    Path(path).write_text(json.dumps(payload, indent=1, default=default) + "\n")


def rel(a, b):
    return None if a is None or b in (None, 0) else a / b - 1


def stats(values):
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    if not values.size:
        return {"n": 0, "median": None, "p95": None, "max": None}
    return {
        "n": int(values.size),
        "median": float(np.median(values)),
        "p95": float(np.quantile(values, 0.95)),
        "max": float(values.max()),
    }


# --- arms -------------------------------------------------------------------------


def core_arms(problem):
    timings = []
    for _ in range(3):
        d = study.solve(problem)
        timings.append((d["wall_seconds"], d["cpu_seconds"]))
    d49 = study.solve(problem, max_iterations=49)
    dt = study.solve(problem, "qp_weights=transposed")
    r = study.solve(problem, max_iterations=500, stop_fraction=2.0)
    arms = {}
    for name, run in (("D", d), ("D49", d49), ("D_T", dt), ("R", r)):
        arms[name] = {
            "gains": run["gains"],
            "valid": run["valid"],
            "flags": run["flags"],
            "iterations": run["iterations"],
            "converged_fraction": run["converged_fraction"],
            "wall_seconds": run["wall_seconds"],
            "cpu_seconds": run["cpu_seconds"],
            "gains_sha256": study.core_sha256(run["gains"]),
        }
    arms["D"]["timings"] = timings
    return arms


def quartical_arm(path):
    path = ROOT / path
    if path.suffix == ".npz":
        with np.load(path) as z:
            gains, valid = z["gains"], z["gain_valid"]
    else:
        gains = np.load(path / "gains.npy")
        valid = np.load(path / "gain_flags.npy") == 0
    valid = valid & np.isfinite(gains).all(axis=(-1, -2))
    return {"gains": gains, "valid": valid}


def chan_freq(ms):
    return np.asarray(
        core_ms_write.read_cells(Path(ms) / "SPECTRAL_WINDOW", "CHAN_FREQ", 0, 1)[0],
        float,
    )


def casa_arm(setdir, arm, problem, times, freqs):
    """CASA's per-chunk caltables as gains on the core's grid (diagonal 2x2)."""
    nt, nf, na = problem["ntime_bins"], problem["nfreq_bins"], problem["nant"]
    gains = np.zeros((nt, nf, na, 2, 2), complex)
    present = np.zeros((nt, nf, na), bool)
    valid = np.zeros((nt, nf, na), bool)
    tmin = np.array([times[problem["time_map"] == t].min() for t in range(nt)])
    tmax = np.array([times[problem["time_map"] == t].max() for t in range(nt)])
    checks = {
        "tables": 0,
        "chunks_without_table": 0,
        "duplicates": 0,
        "time_outside_bin": 0,
        "chan_freq_mismatch": 0,
        "half_flagged": 0,
        "solutions": 0,
        "flagged_solutions": 0,
    }
    tables = {}
    for k in range(nf):
        path = setdir / "tables" / arm / f"c{k:03d}.tab"
        if not path.is_dir():
            checks["chunks_without_table"] += 1
            continue
        tab = caltable.read(path)
        tables[k] = tab
        checks["tables"] += 1
        centre = freqs[CHUNK * k : CHUNK * (k + 1)].mean()
        if abs(tab.solution_frequencies(0)[0] - centre) > 1e-6 * centre:
            checks["chan_freq_mismatch"] += 1
        par, fl = tab.params[:, 0, :], tab.flags[:, 0, :]
        ants, scans, tt = (tab.column(c) for c in ("ANTENNA1", "SCAN_NUMBER", "TIME"))
        for row in range(tab.nrows):
            t, a = int(scans[row]) - 1, int(ants[row])
            checks["solutions"] += 1
            if not (tmin[t] - 1e-3 <= tt[row] <= tmax[t] + 1e-3):
                checks["time_outside_bin"] += 1
            if present[t, k, a]:
                checks["duplicates"] += 1
            present[t, k, a] = True
            v = par[row]
            x, y = (v[0], v[0]) if tab.kind == "T" else (v[0], v[1])
            gains[t, k, a] = np.diag([x, y])
            bad = fl[row]
            checks["flagged_solutions"] += int(bad.all())
            checks["half_flagged"] += int(bad.any() and not bad.all())
            valid[t, k, a] = not bad.any() and np.isfinite(v).all()
    return {
        "gains": gains,
        "valid": valid,
        "present": present,
        "checks": checks,
    }, tables


def composite(arms, names):
    gains = arms[names[0]]["gains"].copy()
    valid = arms[names[0]]["valid"].copy()
    for n in names[1:]:
        gains = gains @ arms[n]["gains"]
        valid &= arms[n]["valid"]
    return {"gains": gains, "valid": valid}


# --- held-out error ---------------------------------------------------------------


def predict(problem, gains, valid):
    t = problem["time_map"][:, None]
    f = problem["freq_map"][None, :]
    p, q = problem["antenna1"][:, None], problem["antenna2"][:, None]
    gp, gq = gains[t, f, p], gains[t, f, q]
    ok = valid[t, f, p] & valid[t, f, q]
    m = problem["model"].astype(complex).reshape(*problem["model"].shape[:2], 2, 2)
    pred = gp @ m @ np.conj(np.swapaxes(gq, -1, -2))
    return pred.reshape(*pred.shape[:2], 4), ok


def mse(problem, pred, cells, corrs):
    r = problem["data"][..., corrs].astype(complex) - pred[..., corrs]
    per = (problem["weights"][..., corrs] * np.abs(r) ** 2).mean(axis=-1)
    return float(per[cells].mean()) if cells.any() else None


def heldout(problem, predictions):
    """Per arm: own coverage and the MSE on the matched cells."""
    matched = {k: problem[k].copy() for k in SPLITS}
    for _, ok in predictions.values():
        for k in SPLITS:
            matched[k] &= ok
    out = {
        "matched_cells": {k: int(matched[k].sum()) for k in SPLITS},
        "split_cells": {k: int(problem[k].sum()) for k in SPLITS},
        "arms": {},
    }
    for name, (pred, ok) in predictions.items():
        entry = {
            "coverage": {
                k: float((problem[k] & ok).sum() / problem[k].sum()) for k in SPLITS
            }
        }
        for k in SPLITS:
            for hand, corrs in HANDS.items():
                entry[f"{k}_{hand}"] = mse(problem, pred, matched[k], corrs)
        out["arms"][name] = entry
    return out, matched


# --- applycal route ------------------------------------------------------------------


def applycal_route(setdir, arm, problem, tables, freqs, matched):
    ex = np.load(setdir / f"export-{arm}.npz")
    for c, k in (("ANTENNA1", "antenna1"), ("ANTENNA2", "antenna2")):
        if not np.array_equal(ex[c], problem[k]):
            raise SystemExit(f"row gate failed on export-{arm}: {c}")
    data = ex["DATA"].astype(complex)
    corrected = ex["CORRECTED_DATA"].astype(complex)
    flag = ex["FLAG"]
    covered = np.zeros(data.shape[1], bool)
    for k in tables:
        covered[CHUNK * k : CHUNK * (k + 1)] = True
    with np.errstate(divide="ignore", invalid="ignore"):
        product = data / corrected
    ok = (
        (~flag)
        & np.isfinite(product)
        & (np.abs(corrected) > 0)
        & covered[None, :, None]
    )
    ok_cell = ok.all(-1)
    pred = product * problem["model"].astype(complex)
    report = {
        "cells_ok": int(ok_cell.sum()),
        "mse": {
            f"{k}_{hand}": mse(problem, pred, matched[k] & ok_cell, corrs)
            for k in SPLITS
            for hand, corrs in HANDS.items()
        },
        "matched_cells_lost": {k: int((matched[k] & ~ok_cell).sum()) for k in SPLITS},
    }
    # The core's reader semantics with interp='nearest' against CASA's CORRECTED_DATA.
    times = ex["TIME"]
    apply_flag = (
        np.asarray(problem["flag"], bool)
        & ~(problem["validation"] | problem["test"])[..., None]
    )
    eps = np.finfo(np.float32).eps
    worst_rel, worst_eps, above, compared, flag_diff = 0.0, 0.0, 0, 0, 0
    mismatch_rows, mismatch_cells_heldout = 0, 0
    heldout_cells = problem["validation"] | problem["test"]
    tbin = problem["time_map"]
    for k, tab in tables.items():
        sl = slice(CHUNK * k, CHUNK * (k + 1))
        field = int(np.unique(tab.column("FIELD_ID"))[0])
        v, fl = caltable.correct(
            ex["DATA"][:, sl],
            apply_flag[:, sl],
            times,
            problem["antenna1"],
            problem["antenna2"],
            freqs[sl],
            [tab],
            field_id=field,
            spw=0,
            time_interp="nearest",
        )
        both = ~fl & ~flag[:, sl]
        flag_diff += int((fl != flag[:, sl]).sum())
        diff = np.abs(corrected[:, sl] - v)
        ref = np.abs(v)
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(both & (ref > 0), diff / ref, 0.0)
            cellmax = ref.max(axis=-1, keepdims=True)
            e = np.where(both & (cellmax > 0), diff / (eps * cellmax), 0.0)
        compared += int(both.sum())
        above += int((r > 1e-6).sum())
        worst_rel = max(worst_rel, float(r.max()))
        worst_eps = max(worst_eps, float(e.max()))
        # Cells whose nearest-time solution is another bin's (per antenna).
        ants, scans, tt = (tab.column(c) for c in ("ANTENNA1", "SCAN_NUMBER", "TIME"))
        wrong = np.zeros(len(times), bool)
        for a in np.unique(ants):
            sel = ants == a
            order = np.argsort(tt[sel], kind="stable")
            st, ss = tt[sel][order], scans[sel][order]
            ref0 = np.floor(st[0] - 1.0)
            tl = (st - ref0).astype(np.float32)
            ft = (times - ref0).astype(np.float32)
            nearest = np.argmin(np.abs(ft[:, None] - tl[None, :]), axis=1)
            off = (ss[nearest] - 1) != tbin
            rows = (problem["antenna1"] == a) | (problem["antenna2"] == a)
            wrong |= off & rows
        mismatch_rows += int(wrong.sum())
        mismatch_cells_heldout += int((heldout_cells[:, sl] & wrong[:, None]).sum())
    report["reader_vs_casa"] = {
        "compared_values": compared,
        "max_relative": worst_rel,
        "above_1e-6": above,
        "max_float32_eps_of_cell": worst_eps,
        "flag_differences": flag_diff,
        "within_dfio_bound": bool(worst_rel <= 1e-6),
        "within_eps_fallback": bool(worst_eps <= 10.3),
    }
    report["nearest_other_bin"] = {
        "row_chunks": mismatch_rows,
        "heldout_cells": mismatch_cells_heldout,
    }
    return report


# --- products and convergence ---------------------------------------------------


def parallel_products(gains):
    """P[t, f, p, q, a] = (G_p G_q^H)_aa (gauge invariant; for a diagonal G
    it is g_p,a conj(g_q,a))."""
    return np.einsum("tfpaj,tfqaj->tfpqa", gains, np.conj(gains))


def pair_mask(problem, valid_a, valid_b, observed_only=True):
    na = problem["nant"]
    both = valid_a & valid_b
    mask = both[:, :, :, None] & both[:, :, None, :]
    mask &= np.triu(np.ones((na, na), bool), 1)[None, None]
    if observed_only:
        mask &= study.observed_pairs(problem)
    return mask


def product_agreement(problem, a, b, observed_only=True):
    """Relative parallel-hand product differences of arm a against arm b."""
    mask = pair_mask(problem, a["valid"], b["valid"], observed_only)
    pa, pb = parallel_products(a["gains"]), parallel_products(b["gains"])
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.abs(pa - pb) / np.abs(pb)
    d = np.where(mask[..., None], d, np.nan)
    per_interval = interval_max(d, mask) if mask.any() else None
    return stats(d[mask]) | {"pairs": int(mask.sum())}, d, per_interval


def interval_max(values, mask):
    """Max over pairs (and trailing axes) per interval; NaN where none."""
    out = np.full(mask.shape[:2], np.nan)
    v = np.where(
        mask.reshape(mask.shape + (1,) * (values.ndim - mask.ndim)), values, np.nan
    )
    v = v.reshape(*mask.shape[:2], -1)
    has = mask.reshape(*mask.shape[:2], -1).any(-1)
    with np.errstate(all="ignore"):
        out[has] = np.nanmax(v[has], axis=-1)
    return out


def frobenius_interval(problem, a, b):
    """L5's full product distance |P - P_b|_F / |P_b|_F per interval (observed)."""
    mask = pair_mask(problem, a["valid"], b["valid"])
    pa = np.einsum("tfpij,tfqkj->tfpqik", a["gains"], np.conj(a["gains"]))
    pb = np.einsum("tfpij,tfqkj->tfpqik", b["gains"], np.conj(b["gains"]))
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.linalg.norm(pa - pb, axis=(-1, -2)) / np.linalg.norm(pb, axis=(-1, -2))
    return interval_max(d, mask)


def restart_step(problem, g1):
    """|(h_p h_q^H)_aa - 1| per interval (observed pairs valid in g1)."""
    mask = pair_mask(problem, g1["valid"], g1["valid"])
    d = np.abs(parallel_products(g1["gains"]) - 1)
    return interval_max(d, mask)


def strata(problem):
    """'triangle' / 'under-constrained' / 'unobserved' per interval from the
    observed-baseline graph."""
    obs = study.observed_pairs(problem)
    na = problem["nant"]
    nt, nf = obs.shape[:2]
    out = np.empty((nt, nf), object)
    for t in range(nt):
        for f in range(nf):
            o = obs[t, f]
            ants = {a for a in range(na) if o[a].any()}
            if not ants:
                out[t, f] = "unobserved"
                continue
            covered = set()
            for a, b, c in combinations(range(na), 3):
                if o[a, b] and o[b, c] and o[a, c]:
                    covered |= {a, b, c}
            out[t, f] = "triangle" if ants <= covered else "under-constrained"
    return out


def gain_test(d, d49):
    """The archived per-gain test at the cap: |g50 - g49|_F^2 / |g49|_F^2 < tau^2."""
    num = np.linalg.norm(d["gains"] - d49["gains"], axis=(-1, -2)) ** 2
    den = np.linalg.norm(d49["gains"], axis=(-1, -2)) ** 2
    unflagged = d["flags"] == 0
    with np.errstate(divide="ignore", invalid="ignore"):
        passing = unflagged & (num < TAU**2 * den)
    failing = unflagged & ~passing
    replay = passing.sum() / max(int(unflagged.sum()), 1)
    return failing, float(replay)


def spearman(x, y):
    from scipy.stats import spearmanr

    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return None
    return float(spearmanr(x[ok], y[ok]).statistic)


def convergence(problem, arms, casa):
    d_core = frobenius_interval(problem, arms["D"], arms["R"])
    _, _, d_core_diag = product_agreement(problem, arms["D"], arms["R"])
    _, _, d_casa = product_agreement(problem, casa["G"], casa["G-composite"])
    step = restart_step(problem, casa["G-r1"])
    later = {a: restart_step(problem, casa[a]) for a in ("G-r2", "G-r3")}
    failing, replay = gain_test(arms["D"], arms["D49"])
    capped_gain = failing.any(axis=-1)
    kinds = strata(problem)
    both = np.isfinite(d_core) & np.isfinite(d_casa)
    out = {
        "intervals": int(both.size),
        "intervals_compared": int(both.sum()),
        "gain_test_replay": {
            "fraction_passing": replay,
            "core_converged_fraction": arms["D"]["converged_fraction"],
            "equal": bool(abs(replay - arms["D"]["converged_fraction"]) < 1e-12),
            "failing_gains": int(failing.sum()),
            "intervals_with_failing_gain": int(capped_gain.sum()),
        },
        "spearman_core_vs_casa": spearman(d_core[both], d_casa[both]),
        "distributions": {
            "core_D_vs_R_frobenius": stats(d_core[both]),
            "core_D_vs_R_parallel_products": stats(d_core_diag[both]),
            "casa_first_vs_restarted": stats(d_casa[both]),
            "casa_first_restart_step": stats(step[both]),
            "casa_second_restart_step": stats(later["G-r2"][both]),
            "casa_third_restart_step": stats(later["G-r3"][both]),
        },
        "strata_counts": {
            s: int((kinds == s).sum())
            for s in ("triangle", "under-constrained", "unobserved")
        },
        "thresholds": {},
    }
    for thr in THRESHOLDS:
        core_cap = both & (d_core >= thr)
        casa_uns = both & (d_casa >= thr)
        base = casa_uns.sum() / max(both.sum(), 1)
        cond = (casa_uns & core_cap).sum() / max(core_cap.sum(), 1)
        entry = {
            "core_capped": int(core_cap.sum()),
            "casa_unsettled": int(casa_uns.sum()),
            "overlap": int((core_cap & casa_uns).sum()),
            "fraction_of_core_capped_casa_unsettled": float(cond)
            if core_cap.any()
            else None,
            "enrichment": float(cond / base) if core_cap.any() and base > 0 else None,
            "core_capped_with_failing_gain": int((core_cap & capped_gain).sum()),
            "casa_unsettled_with_failing_gain": int((casa_uns & capped_gain).sum()),
            "by_stratum": {},
        }
        for s in ("triangle", "under-constrained"):
            m = both & (kinds == s)
            entry["by_stratum"][s] = {
                "intervals": int(m.sum()),
                "core_capped": int((core_cap & m).sum()),
                "casa_unsettled": int((casa_uns & m).sum()),
                "overlap": int((core_cap & casa_uns & m).sum()),
                "failing_gain": int((capped_gain & m).sum()),
            }
        out["thresholds"][f"{thr:g}"] = entry
    primary = out["thresholds"][f"{THRESHOLDS[0]:g}"]
    if primary["core_capped"] == 0:
        verdict = "undecidable"
    elif (
        primary["fraction_of_core_capped_casa_unsettled"] >= 0.5
        and (primary["enrichment"] or 0) >= 5
    ):
        verdict = "reproduced"
    elif primary["fraction_of_core_capped_casa_unsettled"] < 0.1:
        verdict = "not reproduced"
    else:
        verdict = "partly"
    out["verdict"] = verdict
    per_interval = {
        "core_D_vs_R": d_core,
        "casa_first_vs_restarted": d_casa,
        "casa_restart_step": step,
        "failing_gain": capped_gain,
        "stratum": kinds,
    }
    return out, per_interval


# --- the comparison -------------------------------------------------------------------


def l5_hashes(dataset):
    arms = json.loads(L5_ARCHIVE.read_text())["sweeps"][dataset]["arms"]
    return {k: arms[k]["gains_sha256"] for k in ("D", "D_T")}


def receipt_costs(setdir):
    receipt = json.loads((setdir / "receipt.json").read_text())
    out = {"container_steps": receipt["timing"]}
    for p in sorted((setdir / "casa").glob("*.json")):
        log = json.loads(p.read_text())
        calls = [c for c in log["calls"] if "seconds" in c]
        out[p.stem] = {
            "calls": len(calls),
            "task_seconds": float(sum(c["seconds"] for c in calls)),
            "mean_call_seconds": float(np.mean([c["seconds"] for c in calls]))
            if calls
            else None,
            "loop_seconds": log["seconds"],
        }
    return out


def casa_logs(setdir):
    hits = {}
    for p in sorted((setdir / "logs").glob("*.log")):
        text = p.read_text(errors="replace")
        for s in (
            "Reached convergence",
            "Reached iteration limit",
            "Exceeded maximum iteration",
        ):
            if s in text:
                hits.setdefault(s, []).append(p.name)
    return hits


def solvestats(setdir, arm):
    log = json.loads((setdir / "casa" / f"solve-{arm}.json").read_text())
    total = {}
    for c in log["calls"]:
        for key, value in (c.get("solvestats") or {}).items():
            if isinstance(value, list):
                total[key] = total.get(key, 0) + int(np.sum(value))
    return total


def compare(dataset, run_dir):
    import run_l5_solver_study as l5

    setdir = Path(run_dir).resolve() / dataset
    started = time.perf_counter()
    load_before = os.getloadavg()
    problem, _, _, info = l5.load(dataset)
    with np.load(setdir / "problem.npz") as z:
        times = z["times"]
        for k in ("data", "weights", "model"):
            if not np.array_equal(z[k], problem[k]):
                raise SystemExit(f"problem.npz {k} differs from L5's loader")
    freqs = chan_freq(setdir / "g.ms")
    arms = core_arms(problem)
    expected = l5_hashes(dataset)
    gates = {
        "D_hash_equals_L5": arms["D"]["gains_sha256"] == expected["D"],
        "D_T_hash_equals_L5": arms["D_T"]["gains_sha256"] == expected["D_T"],
    }
    if not gates["D_hash_equals_L5"]:
        raise SystemExit(
            "the core D does not reproduce L5's D; no core number is reported"
        )
    shape = arms["D"]["gains"].shape
    for name, (path, held) in QUARTICAL[dataset].items():
        arms[name] = quartical_arm(path) | {"held_out": held, "source": path}
        gates[f"{name}_grid"] = arms[name]["gains"].shape == shape
    casa, tables = {}, {}
    for arm in ("G", "G-r1", "G-r2", "G-r3", "T"):
        casa[arm], tables[arm] = casa_arm(setdir, arm, problem, times, freqs)
    casa["G-composite"] = composite(casa, ["G", "G-r1", "G-r2", "G-r3"])
    offdiag0 = dict(arms["D"])
    offdiag0["gains"] = arms["D"]["gains"].copy()
    offdiag0["gains"][..., 0, 1] = 0
    offdiag0["gains"][..., 1, 0] = 0

    # Held-out error on matched cells.
    predictions = {
        name: predict(problem, arms[name]["gains"], arms[name]["valid"])
        for name in ("D", "D_T", "R", "QC027", "QC028")
    }
    predictions["D_offdiag0"] = predict(problem, offdiag0["gains"], offdiag0["valid"])
    predictions["CASA_G"] = predict(problem, casa["G"]["gains"], casa["G"]["valid"])
    predictions["CASA_T"] = predict(problem, casa["T"]["gains"], casa["T"]["valid"])
    predictions["CASA_G_restarted"] = predict(
        problem, casa["G-composite"]["gains"], casa["G-composite"]["valid"]
    )
    held, matched = heldout(problem, predictions)
    fused = study.losses(
        problem,
        arms["D"]["gains"],
        arms["D"]["valid"],
        {k: problem[k] for k in SPLITS},
    )
    full = {
        k: mse(
            problem,
            predictions["D"][0],
            problem[k] & predictions["D"][1],
            HANDS["total"],
        )
        for k in SPLITS
    }
    held["numpy_vs_fused_pass_D"] = {k: rel(full[k], fused[k]["loss"]) for k in SPLITS}
    gates["numpy_reproduces_fused_pass"] = all(
        abs(v) <= 1e-6 for v in held["numpy_vs_fused_pass_D"].values()
    )

    # Margin verdicts (parallel hands, test, matched cells).
    a = held["arms"]
    verdicts = {}
    for ref in ("D", "D_T", "QC027", "QC028"):
        r_ = rel(a["CASA_G"]["test_parallel"], a[ref]["test_parallel"])
        in_sample = ref.startswith("QC") and not arms[ref]["held_out"]
        verdicts[ref] = {
            "relative": r_,
            "within_margin": None if in_sample else bool(abs(r_) <= DELTA),
            "not_worse": None if in_sample else bool(r_ <= DELTA),
            "in_sample_reference": in_sample,
        }
    margin = {
        "delta": DELTA,
        "casa_G_vs": verdicts,
        "casa_T_vs_D_test_parallel": rel(
            a["CASA_T"]["test_parallel"], a["D"]["test_parallel"]
        ),
        "casa_G_restarted_vs_D_test_parallel": rel(
            a["CASA_G_restarted"]["test_parallel"], a["D"]["test_parallel"]
        ),
        "casa_G_vs_D_test_total": rel(a["CASA_G"]["test_total"], a["D"]["test_total"]),
        "structural_floor_offdiag0_vs_D_test_parallel": rel(
            a["D_offdiag0"]["test_parallel"], a["D"]["test_parallel"]
        ),
        "casa_G_vs_offdiag0_test_total": rel(
            a["CASA_G"]["test_total"], a["D_offdiag0"]["test_total"]
        ),
    }

    # CASA's applycal route against the reader route.
    routes = {}
    for arm in ("G", "T"):
        routes[arm] = applycal_route(setdir, arm, problem, tables[arm], freqs, matched)
        routes[arm]["bin_exact_vs_applycal_test_parallel"] = rel(
            routes[arm]["mse"]["test_parallel"], a[f"CASA_{arm}"]["test_parallel"]
        )

    # Gain products.
    products = {}
    for x, y in (
        ("CASA_G", "D"),
        ("CASA_G", "R"),
        ("CASA_G", "D_T"),
        ("CASA_G", "QC027"),
        ("CASA_G", "QC028"),
        ("CASA_T", "D"),
        ("CASA_G_restarted", "R"),
        ("D", "R"),
        ("D_T", "D"),
        ("QC027", "D"),
        ("QC028", "D_T"),
    ):
        ax = {
            "CASA_G": casa["G"],
            "CASA_T": casa["T"],
            "CASA_G_restarted": casa["G-composite"],
        }.get(x, arms.get(x))
        ay = arms[y]
        obs, _, per = product_agreement(problem, ax, ay, True)
        allp, _, _ = product_agreement(problem, ax, ay, False)
        products[f"{x}_vs_{y}"] = {
            "observed_pairs": obs,
            "all_pairs": allp,
            "per_interval_max": stats(per) if per is not None else None,
        }

    conv, per_interval = convergence(problem, arms, casa)
    conv["casa_solvestats"] = {arm: solvestats(setdir, arm) for arm in ("G", "T")}
    conv["casa_checks"] = {
        arm: casa[arm]["checks"] for arm in ("G", "G-r1", "G-r2", "G-r3", "T")
    }
    conv["casa_log_iteration_messages"] = casa_logs(setdir)
    conv["casa_valid_gain_fraction"] = {
        arm: float(casa[arm]["valid"].mean()) for arm in ("G", "T")
    }
    conv["core_valid_gain_fraction"] = float(arms["D"]["valid"].mean())
    conv["casa_coverage_of_core_valid_gains"] = float(
        (casa["G"]["valid"] & arms["D"]["valid"]).sum() / arms["D"]["valid"].sum()
    )

    gates.update(
        {
            f"casa_{arm}_{k}": casa[arm]["checks"][k] == 0
            for arm in ("G", "T")
            for k in ("duplicates", "time_outside_bin", "chan_freq_mismatch")
        }
    )
    d_walls = [w for w, _ in arms["D"]["timings"]]
    d_cpus = [c for _, c in arms["D"]["timings"]]
    cost = {
        "core": {
            "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
            "D_wall_seconds_median": float(np.median(d_walls)),
            "D_cpu_seconds_median": float(np.median(d_cpus)),
            "D_walls": d_walls,
            "D_T_wall_seconds": arms["D_T"]["wall_seconds"],
            "R_wall_seconds": arms["R"]["wall_seconds"],
            "R_cpu_seconds": arms["R"]["cpu_seconds"],
            "iterations": {k: arms[k]["iterations"] for k in ("D", "D_T", "R")},
        },
        "casa": receipt_costs(setdir),
        "load_before": load_before,
        "load_after": os.getloadavg(),
    }
    report = {
        "task": "L5-C",
        "dataset": dataset,
        "loader": info,
        "gates": gates,
        "core_hashes": {k: arms[k]["gains_sha256"] for k in ("D", "D49", "D_T", "R")},
        "core_converged_fraction": {
            k: arms[k]["converged_fraction"] for k in ("D", "D_T", "R")
        },
        "heldout": held,
        "margin": margin,
        "routes": routes,
        "products": products,
        "convergence": conv,
        "cost": cost,
        "environment": {
            "git_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "backend": core.backend_name(),
            "library_sha256": study.core_sha256(
                np.frombuffer(core.library_path().read_bytes(), np.uint8)
            ),
        },
        "seconds": time.perf_counter() - started,
    }
    write_json(setdir / "compare.json", report)
    np.savez(
        setdir / "per-interval.npz",
        **{
            k: np.asarray(v, float if k != "stratum" else str)
            for k, v in per_interval.items()
        },
    )
    print(
        json.dumps(
            {
                "dataset": dataset,
                "gates": gates,
                "margin": margin["casa_G_vs"]["D"],
                "tail": conv["verdict"],
            },
            default=str,
        )
    )
    return 0


def archive(run_dirs, out):
    sets = {}
    for run_dir in run_dirs:
        for path in sorted(Path(run_dir).glob("*/compare.json")):
            report = json.loads(path.read_text())
            receipt = json.loads((path.parent / "receipt.json").read_text())
            report["run"] = f"{run_dir}/{path.parent.name}"
            report["receipt"] = {
                k: receipt[k]
                for k in (
                    "image",
                    "source_ms",
                    "code_sha256",
                    "git_head",
                    "settings",
                    "status",
                    "outputs",
                )
            }
            sets[report["dataset"]] = report
    payload = {
        "task": "L5-C",
        "protocol": "research/l5c-casa-gaincal.md",
        "note": "derived numbers and hashes only; no visibilities",
        "sets": sets,
    }
    write_json(out, payload)
    print(f"wrote {out} ({Path(out).stat().st_size} bytes)")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compare")
    c.add_argument("dataset", choices=sorted(QUARTICAL))
    c.add_argument("run_dir")
    a = sub.add_parser("archive")
    a.add_argument("run_dirs", nargs="+")
    a.add_argument(
        "--out", default=str(ROOT / "research/results/l5c-casa-gaincal.json")
    )
    args = parser.parse_args(argv[1:])
    if args.command == "compare":
        return compare(args.dataset, args.run_dir)
    return archive(args.run_dirs, args.out)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
