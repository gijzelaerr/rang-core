"""The gain-TV-guided flagging experiment: arms, the decision rule, archives.

A small, local replay of the campaign structure of task K
(research/core-k-luno-campaign.md) on whatever dataset is loaded: the
original arm, a Tricolour-strategy comparator arm, and the frozen TV policy
loop (`core_campaign.tv_loop`), each solved with the frozen settings
(`core_campaign.solve_arm`: 2 x 32 grid, 50 iterations) and imaged; then
the frozen three-way call (`core_campaign.call`, band 0.99-1.01) on the
held-out test MSE and the point-source residual RMS. Separate from the
plotting modules because it drives several stages at once.

The archive readers load the tracked compact results, so the real null
results are shown from their records, never retyped.
"""

from __future__ import annotations

import json

import numpy as np

from . import _plot
from .data import _search_roots

DECISION_RULE = (
    "For each pair (candidate, reference), the ratio candidate / reference of "
    "the held-out test MSE and of the point-source residual RMS of the "
    "corrected dirty image is called 'better' at <= 0.99, 'worse' at >= 1.01 "
    "and 'null' in between; a missing value (an unpredictable held-out cell, "
    "an unavailable arm) is 'undecidable'. The headline pair is the TV policy "
    "against the CARACAL first-pass strategy, and a positive result also "
    "needs comparable cost (TV chain within 3x of the comparator's time)."
)
FROZEN_PAIRS = (
    ("tv-policy", "comparator"),
    ("tv-policy", "original"),
)
ARCHIVES = {
    "fixture": "gain-tv-flagging.json",
    "luno-four-station": "core-k-luno-campaign.json",
    "luno-array": "luno-array-campaign.json",
}
L1_RUN = "luno-array-campaign-20261030-01"


def _frozen_params():
    from ..core_campaign import GRID, ITERATIONS

    return {
        "time_interval": GRID[0],
        "freq_interval": GRID[1],
        "iterations": ITERATIONS,
        "gauge": "polar",
    }


def run_arms(ds, strategy=None, tv=True):
    """Solve the arms with the frozen settings.

    `strategy`: a step list (see `flags.strategy_library`) for the
    comparator arm, or None to skip it. Returns `(arms, trials)`: arms maps
    label -> solve dict (`core_campaign.solve_arm` format plus `params`),
    trials are the TV loop's candidate records.
    """
    from ..core_campaign import solve_arm, tv_loop
    from .flags import run_strategy

    params = _frozen_params()
    state = ds.state
    zero = np.zeros_like(state["train"])
    arms = {"original": solve_arm(state, zero, "original")}
    scale0 = arms["original"]["metrics"]["scale"]
    if strategy is not None:
        run = run_strategy(ds, strategy)
        arms["comparator"] = solve_arm(
            state, run["additions_on_train"], "comparator", scale=scale0
        )
    trials = []
    if tv:
        trials, best, unguided = tv_loop(state, arms["original"], scale0, "tv")
        arms["tv-policy"] = {
            **best["solve"],
            "label": "tv-policy",
            "policy": best["policy"],
        }
        if unguided is not None:
            arms["tv-unguided-best"] = {
                **unguided["solve"],
                "label": "tv-unguided-best",
                "policy": unguided["policy"],
            }
    for arm in arms.values():
        arm["params"] = params
    return arms, trials


def image_arms(ds, arms, **kwargs):
    """Corrected dirty image of every arm on its final flags (frozen robust 0.5)."""
    from .image import image

    return {label: image(ds, arm, **kwargs) for label, arm in arms.items()}


def arms_table(arms, images=None):
    """The decision rule's inputs per arm: additions, held-out MSE, TV,
    convergence, and the image metrics when given."""
    import pandas as pd

    rows = {}
    for label, arm in arms.items():
        m = arm["metrics"]
        row = {
            "additions": int(np.sum(arm["added"])),
            "test MSE": m["losses"]["test"],
            "validation MSE": m["losses"]["validation"],
            "invalid test predictions": m["invalid_predictions"]["test"],
            "TV (gauge)": m["tv"],
            "converged fraction": m["solver"]["converged_fraction"],
        }
        if images is not None and label in images:
            im = images[label]["metrics"]
            row.update(
                {
                    "residual RMS": im["residual_rms"],
                    "peak (Jy/beam)": im["peak_jy_per_beam"],
                    "off-source RMS": im["offsource_rms"],
                }
            )
        rows[label] = row
    return pd.DataFrame(rows).T


def decisions(arms, images, pairs=FROZEN_PAIRS):
    """The frozen calls (`core_campaign.hypothesis`) for each available pair."""
    import pandas as pd

    from ..core_campaign import hypothesis

    records = {
        label: {
            "metrics": arm["metrics"],
            "image": images[label]["metrics"],
            "additions": int(np.sum(arm["added"])),
        }
        for label, arm in arms.items()
        if label in images
    }
    rows = []
    for candidate, reference in pairs:
        if candidate in records and reference in records:
            rows.append(_flatten(hypothesis(records, candidate, reference)))
    return pd.DataFrame(rows)


def _flatten(h):
    out = {"candidate": h["candidate"], "reference": h["reference"]}
    for metric in ("mse_test", "residual_rms", "mse_validation"):
        if metric in h:
            out[f"{metric} ratio"] = h[metric]["ratio"]
            out[f"{metric} call"] = h[metric]["call"]
    if "additions" in h:
        out["additions (cand, ref)"] = h["additions"]
    if "dropped_test_cells" in h:
        out["dropped test cells"] = h["dropped_test_cells"]
    return out


def trials_table(trials):
    """The TV loop's candidates: policy, mask size, objective, verdict."""
    import pandas as pd

    rows = []
    for t in trials:
        policy = t.get("policy") or {}
        rows.append(
            {
                "trial": t["trial"],
                "threshold": policy.get("threshold"),
                "tv weight": policy.get("tv_weight"),
                "mask cells": t.get("mask_count", t.get("added_count")),
                "validation MSE": (t.get("losses") or {}).get("validation"),
                "fixed-support TV": t.get("fixed_support_tv_vs_base"),
                "objective": t.get("objective"),
                "accepted": t.get("accepted"),
                "note": "duplicate mask"
                if "duplicate_mask" in t
                else t.get("rejection"),
            }
        )
    return pd.DataFrame(rows).set_index("trial")


def ratio_figure(table, title="decision inputs"):
    """Each pair's ratios against the frozen 'null' band [0.99, 1.01]."""
    from ..core_campaign import BETTER, WORSE

    metrics = [c[: -len(" ratio")] for c in table.columns if c.endswith(" ratio")]
    fig, axes = _plot.figure(width=7, height=0.9 + 0.55 * max(len(table), 1))
    ax = axes[0, 0]
    ax.axvspan(BETTER, WORSE, color="0.9", label="null band")
    ax.axvline(1.0, color="0.5", lw=0.8)
    labels = [f"{r['candidate']} vs {r['reference']}" for _, r in table.iterrows()]
    for k, metric in enumerate(metrics):
        values = table[f"{metric} ratio"].astype(float).to_numpy()
        y = np.arange(len(table)) + (k - (len(metrics) - 1) / 2) * 0.2
        ok = np.isfinite(values)
        ax.plot(values[ok], y[ok], "o", label=metric)
        for yy in y[~ok]:
            ax.annotate(
                "undecidable",
                (1.0, yy),
                fontsize="x-small",
                ha="center",
                va="center",
                color=f"C{k}",
            )
    ax.set_yticks(np.arange(len(table)), labels)
    lo = min(
        BETTER - 0.005,
        np.nanmin(
            table[[f"{m} ratio" for m in metrics]].astype(float).to_numpy(), initial=1
        ),
    )
    hi = max(
        WORSE + 0.005,
        np.nanmax(
            table[[f"{m} ratio" for m in metrics]].astype(float).to_numpy(), initial=1
        ),
    )
    ax.set_xlim(lo, hi)
    ax.set_xlabel("candidate / reference")
    ax.legend(fontsize="small", loc="lower right")
    ax.set_title(title)
    return fig


# --- archives ----------------------------------------------------------------


def archive_path(name):
    """Path of a tracked archive under `research/results/`, or None."""
    filename = ARCHIVES.get(name, name)
    for root in _search_roots():
        candidate = root / "research" / "results" / filename
        if candidate.is_file():
            return candidate
    return None


def load_archive(name):
    path = archive_path(name)
    if path is None:
        raise FileNotFoundError(
            f"{ARCHIVES.get(name, name)} not found under research/results"
        )
    return json.loads(path.read_text())


def archive_hypotheses(name):
    """The frozen calls as archived (`luno-four-station` or `luno-array`)."""
    import pandas as pd

    return pd.DataFrame([_flatten(h) for h in load_archive(name)["hypotheses"]])


def archive_arms(name):
    """Per-arm additions, held-out losses, convergence and image metrics."""
    import pandas as pd

    rows = {}
    for label, arm in load_archive(name)["arms"].items():
        if arm is None:
            rows[label] = {"note": "unavailable"}
            continue
        m = arm["metrics"]
        image = arm.get("image") or {}
        rows[label] = {
            "additions": arm.get("additions"),
            "test MSE": m["losses"]["test"],
            "validation MSE": m["losses"]["validation"],
            "TV (gauge)": m["tv"],
            "converged fraction": m["solver"]["converged_fraction"],
            "residual RMS": image.get("residual_rms"),
            "peak (Jy/beam)": image.get("peak_jy_per_beam"),
        }
    return pd.DataFrame(rows).T


def archive_status(name):
    """Status line, cost clause and (where recorded) the outcome text."""
    record = load_archive(name)
    out = {"status": record.get("status") or record.get("scientific_outcome")}
    if "cost_clause" in record:
        out["cost clause"] = record["cost_clause"]
    if "scientific_outcome" in record:
        out["outcome"] = record["scientific_outcome"]
    return out


def fixture_pilot():
    """The first fixture campaign (QuartiCal, 2026-09): baseline numbers and
    outcome from results/gain-tv-flagging.json."""
    record = load_archive("fixture")
    final = record["final_whitened_reserved"]
    base = final["baseline"]
    return {
        "baseline TV (gauge)": base["tv"],
        "baseline raw TV": base["raw_tv"],
        "validation MSE": base["losses"]["validation"],
        "test MSE": base["losses"]["test"],
        "selected policy": final.get("selected_policy"),
        "outcome": record["scientific_outcome"],
    }


def amendment_1_calls():
    """L1's matched-sample calls (amendment 1). They are in the run's
    `result.json` under `outputs/`, not in the tracked archive; None when
    the run directory is absent."""
    import pandas as pd

    for root in _search_roots():
        path = root / "outputs" / L1_RUN / "result.json"
        if path.is_file():
            pairs = json.loads(path.read_text())["amendment_1"]["pairs"]
            return pd.DataFrame([_flatten(p) for p in pairs])
    return None
