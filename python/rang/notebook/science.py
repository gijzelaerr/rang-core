"""The two research questions as guided notebooks (task D3,
research/d3-science-notebooks.md): archive readers, live demonstrations on
public or simulated data, and plots.

Notebook 06 asks whether gain total variation can guide flagging; its real
results are read from `research/results/flagging-verdict.json` (task L4's
table of the 90 pre-registered calls) and the campaign archives it cites.
Notebook 07 asks whether small pointing and beam corrections can be
constrained; it runs the Rust toy fixture, the JAX reference predictor and
solver and the observability audits live, and reads B1-0 and B1-1 from
`research/results/b1-beam-product.json` and the B1 baseline archive.

Every number a notebook prints comes from an archive or from a cell that
computes it; the frozen rules are quoted from constants, never retyped.
Plots are bare `matplotlib.figure.Figure` objects (`_plot.figure`).
"""

from __future__ import annotations

import importlib.util
import json
import os
import zipfile
from pathlib import Path, PurePosixPath

import numpy as np

from . import _plot
from .data import FIXTURE_SHA256, _safe_members, _search_roots, _sha256

VERDICT_ARCHIVE = "flagging-verdict.json"
B1_PRODUCT_ARCHIVE = "b1-beam-product.json"
B1_BASELINES_ARCHIVE = "b1-baselines.json"
# Where B1-1 (i) left its baseline archive (ignored outputs; not committed).
B1_BASELINES_RUN = "b1-20261030-10-baseline-g1b"
HOLOGRAPHY_RUN = "b1-20261030-05-holography"
B1_PROTOCOL = "research/b1-beam-pointing.md"

# Quoted verbatim from the frozen B1 protocol (research/b1-beam-pointing.md,
# "B1-2" and "Metrics for Q3"); tests/test_d3_notebooks.py checks that each
# is a substring of the protocol, so they cannot drift.
B1_2_DECISION_RULE = (
    "A direction is *constrainable* on a data set if its profiled Fisher "
    "σ ≤ 0.3′ for pointing (half the 0.6′ that holography removes) or "
    "≤ 0.5 % for width and ellipticity, **and** at least 1 % of its "
    "signature lies outside the nuisance span. B1-3 fits only constrainable "
    "directions; if none is constrainable on any set, B1 closes null at B1-2."
)
B1_3_DECISION_RULE = (
    "Rang wins only if it improves 2 or 3 over both baselines with 1 no "
    "worse, at matched cost (the novelty rule); otherwise the result is "
    "recorded as null."
)
B1_3_MATCHED_COST = '"matched" means within a factor 1.5 in wall for the same data.'
B1_3_METRICS = (
    "Recovered offset against truth",
    "Held-out visibility error",
    "Faint-source flux and spectral-index distortion",
    "Cost",
)

# The B1 tasks as research/b1-beam-pointing.md labels them (status as of the
# B1-0/B1-1 merge; "proposed" until a report says "measured").
B1_TASKS = (
    ("B1-0", "the reference beam: SARAO's 2023 holography release", "measured"),
    ("B1-1 (i)", "baseline: the SARAO/SKA Gaussian pointing-offset fit", "measured"),
    ("B1-1 (ii)", "baseline: physical pointing self-calibration", "proposed"),
    ("B1-2", "identifiability survey over beam and pointing directions", "proposed"),
    ("B1-3", "pointing self-calibration and rang's method at matched cost", "proposed"),
)

# The environment switches of the two notebooks. All default off: the
# documentation build runs on public data only.
SWITCHES = {
    "RANG_NOTEBOOK_LUNO": "replay task K on a local four-station LUNO slice",
    "RANG_NOTEBOOK_SLOW": "run the JAX audits with long compiles (katbeam predictor)",
    "RANG_NOTEBOOK_HOLOGRAPHY": "draw maps of the local B1-0 holography product "
    "(CC BY-NC 4.0; never on the public site)",
}


def switch(name):
    """True when the environment variable `name` is set to 1."""
    return os.environ.get(name, "0") == "1"


def skip_line(name, reason=""):
    """The line a gated cell prints when its switch is off."""
    text = f"skipped: set {name}=1 to {SWITCHES[name]}"
    return text + (f" ({reason})" if reason else "")


def checkout_root():
    """The repository checkout (the directory with `research/results`), or None."""
    for root in _search_roots():
        if (root / "research" / "results").is_dir():
            return root
    return None


def results_path(filename):
    root = checkout_root()
    if root is None:
        return None
    path = root / "research" / "results" / filename
    return path if path.is_file() else None


def load_results(filename):
    """A committed archive under `research/results/`."""
    path = results_path(filename)
    if path is None:
        raise FileNotFoundError(f"research/results/{filename} not found")
    return json.loads(path.read_text(encoding="utf-8"))


def as_text(mapping, name="value", digits=4):
    """A dict as a one-column table of text, floats in `digits` significant
    figures (so that 1e-11 does not print as 0.0)."""
    import pandas as pd

    def text(value):
        if isinstance(value, (bool, np.bool_)):
            return str(bool(value))
        if isinstance(value, (int, np.integer)):
            return f"{int(value):,}"
        if isinstance(value, (float, np.floating)):
            return f"{float(value):.{digits}g}"
        return str(value)

    return pd.Series({k: text(v) for k, v in mapping.items()}, name=name).to_frame()


# --- notebook 06: the flagging verdict ---------------------------------------

CAMPAIGN_ORDER = ("K", "L1", "L1-M", "C1", "L2")
CAMPAIGN_NOTES = {
    "K": "PKS 1934−638, four stations",
    "L1": "PKS 1934−638, whole array",
    "L1-M": "L1 under three calibrator models",
    "C1": "L1 with the closure-invariant arm",
    "L2": "PKS 1830−211, whole array, two models",
}
WAVE3_MAP = (
    ("K", "core-k-luno-campaign.json", "first real-data campaign, four stations"),
    ("L1", "luno-array-campaign.json", "the whole array; amendment 1"),
    ("L2", "luno-1830-campaign.json", "the second calibrator, two models"),
    ("L1-M", "l1-model-completeness.json", "was the calibrator model the cause?"),
    ("C1", "c1-closure-arm.json", "a gauge-free closure statistic"),
    ("A1", "a1-rfi-audit.json", "what the emptied station-bins are"),
    ("L5", "l5-solver-science.json", "would a converged solver change it?"),
    ("L4", VERDICT_ARCHIVE, "the verdict: every call in one table"),
    ("L3", None, "native flags and weights: not run, no data"),
)


def flagging_rules():
    """The frozen policy, objective and call band, from `core_campaign`."""
    from .. import core_campaign as cc

    return {
        "split seed": cc.SPLIT_SEED,
        "solution grid (integrations × channels)": cc.GRID,
        "solver iterations": cc.ITERATIONS,
        "thresholds τ": cc.THRESHOLDS,
        "TV weights α": cc.TV_WEIGHTS,
        "largest added fraction": cc.MAX_FRACTION,
        "flag penalty in L": cc.FLAG_PENALTY,
        "validation weight in L": cc.VALIDATION_WEIGHT,
        "validation tolerance": cc.VALIDATION_TOLERANCE,
        "call band (better ≤, worse ≥)": (cc.BETTER, cc.WORSE),
        "image robustness (Briggs)": cc.ROBUST,
    }


def wave3_table():
    """Which wave 3 protocol answers which part of the question, and its archive."""
    import pandas as pd

    rows = []
    for task, archive, role in WAVE3_MAP:
        rows.append(
            {
                "task": task,
                "role": role,
                "archive": f"research/results/{archive}" if archive else "–",
                "archive present": bool(archive and results_path(archive)),
            }
        )
    return pd.DataFrame(rows).set_index("task")


def verdict():
    """`research/results/flagging-verdict.json` (task L4)."""
    return load_results(VERDICT_ARCHIVE)


def calls_table(record=None):
    """Every pre-registered call: campaign, model, pair, rule, metric, ratio,
    call, and the archive path it was read from."""
    import pandas as pd

    record = record or verdict()
    frame = pd.DataFrame(record["calls"])
    frame["pair"] = frame["candidate"] + " vs " + frame["reference"]
    return frame[
        [
            "campaign",
            "model",
            "pair",
            "rule",
            "metric",
            "ratio",
            "call",
            "source",
            "path",
        ]
    ]


def call_counts(record=None):
    """Calls per campaign and outcome, with the archive's own totals checked."""
    record = record or verdict()
    calls = calls_table(record)
    counts = (
        calls.groupby(["campaign", "call"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=["better", "worse", "null", "undecidable"], fill_value=0)
    )
    order = [c for c in CAMPAIGN_ORDER if c in counts.index]
    counts = counts.loc[order + [c for c in counts.index if c not in order]]
    counts.loc["all"] = counts.sum()
    archived = record["summary"]["by_call"]
    if {k: int(counts.loc["all", k]) for k in archived} != archived:
        raise ValueError("the call table disagrees with the archive's summary")
    if int(counts.loc["all"].sum()) != record["summary"]["calls"]:
        raise ValueError("call count disagrees with the archive's summary")
    return counts


def headline_calls(record=None):
    """The headline pairs against the CARACAL first pass, per campaign, model,
    rule and metric (the rows a positive would have had to come from)."""
    calls = calls_table(record)
    mask = calls["pair"].str.endswith("vs tricolour-firstpass")
    return calls[mask].drop(columns=["path"]).reset_index(drop=True)


def calls_figure(record=None, title="every pre-registered call"):
    """All decidable ratios per campaign against the frozen null band;
    undecidable calls are counted beside each row."""
    from ..core_campaign import BETTER, WORSE

    calls = calls_table(record)
    campaigns = [c for c in CAMPAIGN_ORDER if c in set(calls["campaign"])]
    fig, axes = _plot.figure(width=7.5, height=1.2 + 0.5 * len(campaigns))
    ax = axes[0, 0]
    ax.axvspan(BETTER, WORSE, color="0.9", label="null band")
    ax.axvline(1.0, color="0.5", lw=0.8)
    markers = {"mse_test": "o", "residual_rms": "s"}
    for y, campaign in enumerate(campaigns):
        rows = calls[calls["campaign"] == campaign]
        for k, (metric, marker) in enumerate(markers.items()):
            values = rows.loc[rows["metric"] == metric, "ratio"].dropna()
            ax.plot(
                values,
                np.full(len(values), y + 0.12 * (k - 0.5)),
                marker,
                ms=5,
                mfc="none",
                color=f"C{k}",
                label=metric if y == 0 else None,
            )
        undecidable = int((rows["call"] == "undecidable").sum())
        ax.annotate(
            f"{undecidable} undecidable",
            (WORSE, y),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            fontsize="x-small",
        )
    ax.set_yticks(range(len(campaigns)), campaigns)
    ax.invert_yaxis()
    ax.set_xlim(BETTER - 0.004, WORSE + 0.008)
    ax.set_xlabel("candidate / reference")
    ax.legend(fontsize="small", loc="lower left")
    ax.set_title(title)
    return fig


def policy_selections(record=None):
    """What the frozen TV policy selected in each campaign."""
    import pandas as pd

    record = record or verdict()
    frame = pd.DataFrame(record["tv_policy_selections"])
    for column in ("guided_trials", "guided_distinct_solved", "guided_accepted"):
        if column in frame:
            frame[column] = frame[column].astype("Int64")
    keep = [
        "campaign",
        "model",
        "selected_policy",
        "additions",
        "guided_trials",
        "guided_distinct_solved",
        "guided_accepted",
        "guided_best_objective",
        "no_change_objective",
    ]
    return frame[[k for k in keep if k in frame.columns]]


def cost_table(record=None):
    """The cost clause as each campaign archived it."""
    import pandas as pd

    record = record or verdict()
    frame = pd.DataFrame(record["cost_clause"])
    keep = [
        "campaign",
        "model",
        "note",
        "tv_chain_seconds",
        "firstpass_seconds",
        "ratio",
        "comparable",
    ]
    return frame[[k for k in keep if k in frame.columns]]


def cost_limit():
    """The cost clause's limit ratio as task K archived it."""
    return load_results("core-k-luno-campaign.json")["cost_clause"]["limit_ratio"]


def cost_figure(record=None):
    """TV-chain wall over first-pass wall per run, against the frozen limit."""
    table = cost_table(record)
    limit = cost_limit()
    labels = [
        f"{c} ({m})" if isinstance(m, str) and m else c
        for c, m in zip(table["campaign"], table.get("model", [""] * len(table)))
    ]
    fig, axes = _plot.figure(width=6.5, height=1 + 0.35 * len(table))
    ax = axes[0, 0]
    colours = ["C2" if ok else "C3" for ok in table["comparable"]]
    ax.barh(range(len(table)), table["ratio"], color=colours)
    ax.axvline(limit, color="0.3", ls="--", label=f"limit {limit:g}×")
    ax.set_yticks(range(len(table)), labels)
    ax.invert_yaxis()
    ax.set_xlabel("TV chain / CARACAL first pass (wall)")
    ax.legend(fontsize="small")
    ax.set_title("the cost clause (green: comparable)")
    return fig


def context_tables(record=None):
    """The cross-cutting findings the verdict cites, as small tables:
    model completeness (L1-M), closure structure (C1), convergence (L5), the
    GNSS bins (A1) and the CASA crosscal baseline (O-CASA)."""
    import pandas as pd

    record = record or verdict()
    ctx = record["context"]
    out = {
        "L1-M model calls": pd.DataFrame(ctx["l1m_model_calls"])[
            ["question", "pair", "metric", "ratio", "call"]
        ],
        "C1 closure-TV map (Q1)": pd.Series(ctx["c1_q1_trace"], name="value")
        .to_frame()
        .rename_axis("statistic"),
        "L5 whole-array solve": pd.DataFrame(
            {
                label: {
                    "iterations": run["iterations"],
                    "converged fraction": run["converged_fraction"],
                    "test MSE": run["losses"]["test"],
                    "gain TV (polar gauge)": run["polar_tv"],
                }
                for label, run in ctx["l5_array"].items()
            }
        ).T,
        "A1 emptied station-bins": pd.Series(
            ctx["a1_emptied"], name="station-bins"
        ).to_frame(),
        "O-CASA matched crosscal (arm SH)": pd.Series(ctx["o_casa_sh"], name="value")
        .to_frame()
        .rename_axis("held-out MSE"),
    }
    return out


def fixture_era(record=None):
    """The fixture-era numbers the verdict keeps (QuartiCal, 2026-09)."""
    record = record or verdict()
    ctx = record["context"]
    base = ctx["fixture_baseline"]
    injected = ctx["fixture_seed109_injected"]
    return {
        "baseline gauge-fixed TV": base["tv"],
        "baseline validation MSE": base["losses"]["validation"],
        "baseline test MSE": base["losses"]["test"],
        "policy selected": base["selected_policy"],
        "injected case: TV and residual rankings chose the same mask": (
            injected["selected_tv"]["mask_id"]
            == injected["selected_residual"]["mask_id"]
        ),
        "injected case: cells added": injected["selected_tv"]["flags_added"],
        "injected case: test MSE ratio": injected["selected_tv"]["test_MSE"]
        / injected["baseline_test_mse"],
        "injected case: recall of injected cells": injected["selected_tv"][
            "known_injection_recall"
        ],
    }


def verdict_summary_markdown(record=None):
    """The verdict in three sentences, every number read from the archive."""
    record = record or verdict()
    counts = record["summary"]["by_call"]
    total = record["summary"]["calls"]
    selections = policy_selections(record)
    guided = int(selections["guided_accepted"].fillna(0).sum())
    cost = cost_table(record)
    failing = cost[~cost["comparable"]]
    head = headline_calls(record)
    decided = head[head["call"] != "undecidable"]
    spread = {
        metric: float((rows["ratio"] - 1).abs().max())
        for metric, rows in decided.groupby("metric")
    }
    return (
        f"Of the **{total}** pre-registered calls, **{counts['null']} are null** and "
        f"**{counts['undecidable']} undecidable**; {counts['better']} are better and "
        f"{counts['worse']} worse. Over every campaign the frozen policy accepted "
        f"**{guided}** TV-guided (α > 0) masks. In every decidable call against the "
        f"CARACAL first pass, held-out MSE agrees within {spread['mse_test']:.2%} and "
        f"the image residual RMS within {spread['residual_rms']:.2%}. "
        f"The cost clause fails in {len(failing)} of {len(cost)} runs, at "
        f"{failing['ratio'].min():.2f}–{failing['ratio'].max():.2f}× the first "
        f"pass on the parallel kernels."
    )


def verdict_tables_check():
    """Run `examples/verdict_tables.py --check` (stdlib, reads the committed
    archives): is the consolidated table current? Returns (ok, output), or
    None outside a checkout."""
    import subprocess
    import sys

    root = checkout_root()
    script = root / "examples" / "verdict_tables.py" if root else None
    if script is None or not script.is_file():
        return None
    done = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )
    return done.returncode == 0, (done.stdout + done.stderr).strip()


def archived_hypotheses(filename):
    """A campaign archive's frozen calls (K's and L1's `hypotheses`)."""
    import pandas as pd

    from .experiment import _flatten

    return pd.DataFrame([_flatten(h) for h in load_results(filename)["hypotheses"]])


# --- notebook 07: the toy and the JAX reference path -------------------------


def enable_x64():
    """JAX 64-bit mode, as `rang.pointing` requires (before any array)."""
    import jax

    jax.config.update("jax_enable_x64", True)
    return jax.__version__


def toy_fixture(full=False):
    """The Rust toy fixture (`rang-toy --pointing-reference`, or the complete
    `--pointing-full-reference`): eight approximate MeerKAT core antennas, 24
    times over six hours, four channels, four point sources. Returns a dict
    with the raw fixture, the `Components`, the `Observation` and the row
    count."""
    import jax.numpy as jnp

    from .. import toy_output
    from ..pointing import Observation, component_list

    flag = "--pointing-full-reference" if full else "--pointing-reference"
    text = toy_output(flag)
    fixture = json.loads(text)
    rows, sources = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    sky = component_list(sources[:, 0], sources[:, 1], sources[:, 2], sources[:, 3])
    obs = Observation(
        jnp.asarray(rows[:, :3]),
        jnp.asarray(rows[:, 3]),
        *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(rows[:, 7]),
    )
    return {
        "fixture": fixture,
        "sky": sky,
        "obs": obs,
        "rows": len(rows),
        "sha256": _sha256_text(text),
    }


def _sha256_text(text):
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()


def toy_summary(toy):
    """What the toy fixture holds."""
    fx, obs = toy["fixture"], toy["obs"]
    return {
        "complex rows": toy["rows"],
        "antennas": fx["antenna_count"],
        "times": fx["time_count"],
        "channels (Hz)": sorted({float(f) for f in np.asarray(obs.frequency_hz)}),
        "sources (l, m, Jy, index)": np.asarray(fx["sources"]).round(5).tolist(),
        "max |w| (m)": float(np.max(np.abs(np.asarray(obs.uvw_m)[:, 2]))),
        "fixture SHA256": toy["sha256"][:16] + "…",
    }


def jax_against_rust(toy):
    """The JAX DFT and its `jacfwd` Jacobian against the Rust predictor's
    visibilities and analytic Jacobian at the fixture's pointing."""
    import jax
    import jax.numpy as jnp

    from ..pointing import predict, real_stack

    fx, sky, obs = toy["fixture"], toy["sky"], toy["obs"]
    nant, ntime = fx["antenna_count"], fx["time_count"]
    theta = jnp.asarray(fx["pointing_arcmin"])

    def forward(flat):
        offsets = jnp.broadcast_to(flat.reshape(1, nant, 2), (ntime, nant, 2))
        return real_stack(predict(sky, obs, offsets))

    vis = np.asarray(forward(theta))
    jac = np.asarray(jax.jacfwd(forward)(theta))
    rust_vis = np.asarray(fx["vis_re_im"])
    rust_jac = np.asarray(fx["jacobian"])
    return {
        "max |V_jax − V_rust| (Jy)": float(np.max(np.abs(vis - rust_vis))),
        "max |V| (Jy)": float(np.max(np.abs(rust_vis))),
        "max |J_jax − J_rust| (Jy/arcmin)": float(np.max(np.abs(jac - rust_jac))),
        "max |J| (Jy/arcmin)": float(np.max(np.abs(rust_jac))),
        "Jacobian shape": list(jac.shape),
    }


def rust_experiment_table(**kwargs):
    """One run of the Rust baseline experiment (`rang.run_experiment`): the
    calibration models of research/first-results.md on one seed."""
    import pandas as pd

    from .. import run_experiment

    result = run_experiment(**kwargs)
    keep = (
        "flux_jy",
        "pointing_rmse_arcmin",
        "heldout_rms_jy",
        "template_transfer",
        "fitted_beam_width_error",
        "iterations",
    )
    rows = {r["method"]: {k: r.get(k) for k in keep} for r in result["results"]}
    settings = {
        k: result[k]
        for k in (
            "seed",
            "noise_jy",
            "pointing_sigma_arcmin",
            "beam_width_error",
            "true_flux_jy",
            "execution_seconds",
        )
    }
    return pd.DataFrame(rows).T, settings


def beam_width_campaign():
    """research/results/beam-width-campaign.json: 20 paired seeds per case,
    mean recovered flux (mJy) per calibration model."""
    import pandas as pd

    record = load_results("beam-width-campaign.json")
    out = {}
    for name, campaign in record["campaigns"].items():
        out[f"{name}: flux (mJy)"] = {
            method: 1e3 * stats["flux_jy"]["mean"]
            for method, stats in campaign["summary"].items()
        }
        out[f"{name}: held-out RMS (mJy)"] = {
            method: 1e3 * stats["heldout_rms_jy"]["mean"]
            for method, stats in campaign["summary"].items()
        }
    truth = {
        name: 1e3 * c["configuration"]["true_flux_jy"]
        for name, c in record["campaigns"].items()
    }
    return pd.DataFrame(out), truth


def smooth_pointing_demo(toy, seed=7, noise=0.001, knots=6, smoothness=0.01):
    """examples/pointing.py in a function: sinusoidal per-antenna truth plus
    a constant offset, every fourth interior time held out, the JAX spline
    solver on the rest. Returns the inputs, the fit and its scores."""
    import time

    import jax.numpy as jnp

    from ..pointing import Observation, predict, solve_pointing

    fx, sky, obs = toy["fixture"], toy["sky"], toy["obs"]
    times = np.linspace(0, 6 * 3600, fx["time_count"])
    knot_times = np.linspace(times[0], times[-1], knots)
    rng = np.random.default_rng(seed)
    nants = fx["antenna_count"]
    bias = rng.normal(0, 0.3, (nants, 2))
    phase = rng.uniform(0, 2 * np.pi, (nants, 2))
    truth = bias[None] + 0.25 * np.sin(
        2 * np.pi * times[:, None, None] / times[-1] + phase
    )
    noiseless = np.asarray(predict(sky, obs, jnp.asarray(truth)))
    data = noiseless + noise * (
        rng.normal(size=toy["rows"]) + 1j * rng.normal(size=toy["rows"])
    )
    heldout = np.asarray(obs.time_index) % 4 == 2
    train = Observation(*(a[~heldout] for a in obs))
    started = time.perf_counter()
    fit = solve_pointing(
        sky,
        train,
        data[~heldout],
        times,
        knot_times,
        nants,
        noise_jy=noise,
        smoothness=smoothness,
    )
    seconds = time.perf_counter() - started
    predicted = np.asarray(predict(sky, obs, jnp.asarray(fit["offsets_arcmin"])))
    fixed = np.asarray(predict(sky, obs, jnp.zeros_like(jnp.asarray(truth))))

    def rms(residual):
        return float(np.sqrt(np.mean(np.abs(residual) ** 2) / 2))

    return {
        "times": times,
        "knots": knot_times,
        "truth": truth,
        "fit": fit,
        "seconds": seconds,
        "scores": {
            "converged": bool(fit["success"]),
            "pointing RMSE (arcsec)": 60
            * float(np.sqrt(np.mean((fit["offsets_arcmin"] - truth) ** 2))),
            "held-out RMS, no pointing (mJy)": 1e3 * rms((data - fixed)[heldout]),
            "held-out RMS, fitted (mJy)": 1e3 * rms((data - predicted)[heldout]),
            "injected noise (mJy)": 1e3 * noise,
            "data Jacobian rank": fit["data_jacobian_rank"],
            "parameters": fit["parameter_count"],
            "fit seconds (with compile)": seconds,
        },
    }


def smooth_pointing_archive():
    """research/results/smooth-pointing.json: the archived seed-7 run."""
    record = load_results("smooth-pointing.json")
    return {
        "pointing RMSE (arcsec)": 60 * record["pointing_rmse_arcmin"],
        "held-out RMS, no pointing (mJy)": 1e3 * record["fixed_heldout_rms_jy"],
        "held-out RMS, fitted (mJy)": 1e3 * record["fit_heldout_rms_jy"],
        "seed": record["seed"],
        "jax": record["jax_version"],
    }


def trajectory_figure(demo, antennas=(0, 1, 2, 3)):
    """Truth (dashed) and the spline fit (solid) per antenna and axis."""
    times_h = demo["times"] / 3600
    fit = demo["fit"]["offsets_arcmin"]
    fig, axes = _plot.figure(
        2, (len(antennas) + 1) // 2, width=8, height=4.6, sharex=True, sharey=True
    )
    for ax, antenna in zip(axes.flat, antennas):
        for axis, name in enumerate(("axis 1", "axis 2")):
            ax.plot(times_h, demo["truth"][:, antenna, axis], "--", color=f"C{axis}")
            ax.plot(times_h, fit[:, antenna, axis], color=f"C{axis}", label=name)
        for k in demo["knots"] / 3600:
            ax.axvline(k, color="0.85", lw=0.6, zorder=0)
        ax.set_title(f"antenna {antenna}", fontsize="small")
    axes[0, 0].legend(fontsize="x-small")
    for ax in axes[-1]:
        ax.set_xlabel("time (h)")
    for ax in axes[:, 0]:
        ax.set_ylabel("offset (arcmin)")
    fig.suptitle("smooth pointing: truth dashed, JAX spline fit solid (knots grey)")
    return fig


SYMMETRY_CASES = (
    ("circular beam, rotating", 1.0, True, "fixed"),
    ("ellipse 1.1, rotating", 1.1, True, "fixed"),
    ("ellipse 1.1, no rotation", 1.1, False, "fixed"),
    ("ellipse 1.1, rotating, one gain per antenna", 1.1, True, "constant"),
    ("ellipse 1.1, rotating, gain per antenna and time", 1.1, True, "per_time"),
)


def symmetry_audit(toy, cases=SYMMETRY_CASES, noise=0.001):
    """Which array-common pointing modes the visibilities can see once the
    source/channel fluxes (and optionally the gains) are free
    (`observability.sky_locked_information`, research/beam-rotation.md)."""
    import jax.numpy as jnp
    import pandas as pd

    from ..observability import sky_locked_information

    obs, nants = toy["obs"], toy["fixture"]["antenna_count"]
    rows = {}
    for label, ratio, rotate, gains in cases:
        selected = (
            obs
            if rotate
            else obs._replace(beam_angle_rad=jnp.zeros_like(obs.beam_angle_rad))
        )
        result = sky_locked_information(
            toy["sky"],
            selected,
            nants,
            noise_jy=noise,
            beam_axis_ratio=ratio,
            gain_model=gains,
        )
        rows[label] = _audit_row(result)
    return pd.DataFrame(rows).T


def _audit_row(result):
    crlb = result["local_crlb_arcsec"]
    return {
        "observable common modes": result["observable_common_modes"],
        "σ axis 1 (arcsec)": crlb[0] if crlb else None,
        "σ axis 2 (arcsec)": crlb[1] if crlb else None,
        "gain columns": result.get("gain_nuisance_parameters"),
        "differential-pointing columns": result.get("differential_pointing_parameters"),
        "retained derivative fraction": result["retained_derivative_norm_fraction"],
    }


GAIN_AUDIT_CASES = (
    ("per_time_channel", False),
    ("per_time_channel", True),
)


def gain_audit(thinned, complete, cases=GAIN_AUDIT_CASES, noise=0.001):
    """Frequency-dependent gains, with and without differential pointing, on
    the thinned and the complete toy coverage (examples/gain_observability.py)."""
    import pandas as pd

    from ..observability import sky_locked_information

    rows = {}
    for coverage, toy in (("thinned", thinned), ("complete", complete)):
        for gains, differential in cases:
            result = sky_locked_information(
                toy["sky"],
                toy["obs"],
                toy["fixture"]["antenna_count"],
                noise_jy=noise,
                beam_axis_ratio=1.1,
                gain_model=gains,
                differential_pointing=differential,
            )
            label = f"{coverage}, gains {gains}" + (
                " + differential pointing" if differential else ""
            )
            rows[label] = _audit_row(result)
    return pd.DataFrame(rows).T


def gain_audit_archive():
    """research/results/gain-observability.json as a table."""
    import pandas as pd

    rows = {}
    for r in load_results("gain-observability.json"):
        coverage = "complete" if r["complete_baselines"] else "thinned"
        label = f"{coverage}, gains {r['gain_model']}" + (
            " + differential pointing" if r["differential_pointing_parameters"] else ""
        )
        rows[label] = _audit_row(r)
    return pd.DataFrame(rows).T


def katbeam_audit_archive():
    """research/results/katbeam-observability.json: the chromatic-shape
    ablations of the katbeam model (H and V)."""
    import pandas as pd

    record = load_results("katbeam-observability.json")
    rows = []
    for r in record["results"]:
        crlb = r["local_crlb_arcsec"]
        budget = r.get("information_budget") or {}
        rows.append(
            {
                "polarization": r["beam_metadata"]["polarization"],
                "case": r["beam_metadata"].get("ablation"),
                "observable common modes": r["observable_common_modes"],
                "σ axis 1 (arcsec)": crlb[0] if crlb else None,
                "σ axis 2 (arcsec)": crlb[1] if crlb else None,
                "σ with 1 % flux priors (arcsec)": budget.get("local_sigma_arcsec"),
            }
        )
    return pd.DataFrame(rows).set_index(["polarization", "case"])


def katbeam_audit_live(complete, polarization="H", noise=0.001):
    """The native and no-rotation katbeam cases of
    examples/katbeam_observability.py, live (JAX compiles the katbeam
    predictor: tens of seconds)."""
    import jax.numpy as jnp
    import pandas as pd

    from ..beams import load_katbeam, make_beam_predictor
    from ..observability import sky_locked_information

    table, metadata = load_katbeam(polarization)
    rows = {}
    for name, rotate in (("native", True), ("native_without_rotation", False)):
        obs = complete["obs"]
        if not rotate:
            obs = obs._replace(beam_angle_rad=jnp.zeros_like(obs.beam_angle_rad))
        predictor = make_beam_predictor(table, "cosine", dict(metadata, ablation=name))
        result = sky_locked_information(
            complete["sky"],
            obs,
            complete["fixture"]["antenna_count"],
            noise_jy=noise,
            gain_model="per_time_channel",
            differential_pointing=True,
            common_time_variation=True,
            predictor=predictor,
            log_flux_prior_covariance=0.01**2 * np.eye(16) if rotate else None,
        )
        row = _audit_row(result)
        row["σ with 1 % flux priors (arcsec)"] = (
            result.get("information_budget") or {}
        ).get("local_sigma_arcsec")
        rows[f"{polarization} {name}"] = row
    return pd.DataFrame(rows).T


def information_budget_archive():
    """research/results/information-budget.json: where the pointing
    information comes from (data alone against external flux priors)."""
    import pandas as pd

    record = load_results("information-budget.json")
    rows = {}
    for r in record["results"]:
        budget = r.get("information_budget") or {}
        label = (
            f"{'Gaussian' if not r['beam_quartic'] else 'non-Gaussian'}, "
            f"{r['scenario']}"
        )
        fractions = budget.get("data_only_fraction_eigenvalues")
        rows[label] = {
            "σ with priors (arcsec)": budget.get("local_sigma_arcsec"),
            "data-only information fractions": fractions,
            "observable modes without priors": r["observable_common_modes"],
        }
    return pd.DataFrame(rows).T


def katbeam_signal_figure(freq_hz=1.284e9, half_width_deg=1.5, step_deg=0.02):
    """katbeam's Stokes I power beam and the change a 30″ pointing offset
    makes, |∇I_b| · 30″, the unit B1-0 measures beam errors in."""
    from ..beam_holography import KatBeam, gradient_magnitude, grid

    beam = KatBeam()
    x, y = grid(half_width_deg, step_deg)
    power = beam.power_i(0, x, y, freq_hz)
    signal = gradient_magnitude(power, step_deg) * (30 / 3600)
    fig, axes = _plot.figure(1, 2, width=8.4, height=3.6)
    ext = (-half_width_deg, half_width_deg, -half_width_deg, half_width_deg)
    im = axes[0, 0].imshow(power, origin="lower", extent=ext, cmap="viridis")
    axes[0, 0].contour(x, y, power, levels=[0.5], colors="w", linewidths=0.8)
    fig.colorbar(im, ax=axes[0, 0], label="I_b (on-axis = 1)")
    axes[0, 0].set_title(f"katbeam I_b at {freq_hz / 1e6:.0f} MHz", fontsize="small")
    im = axes[0, 1].imshow(100 * signal, origin="lower", extent=ext, cmap="magma")
    axes[0, 1].contour(x, y, power, levels=[0.5], colors="w", linewidths=0.8)
    fig.colorbar(im, ax=axes[0, 1], label="% of on-axis")
    axes[0, 1].set_title("|∇I_b| · 30″: the signal of a 30″ offset", fontsize="small")
    for ax in axes.flat:
        ax.set_xlabel("x, cross-elevation (deg)")
    axes[0, 0].set_ylabel("y, elevation (deg)")
    ring = np.abs(power - 0.5) < 0.02
    return fig, {
        "median 30″ signal on the half-power ring": float(np.median(signal[ring])),
        "max 30″ signal anywhere": float(signal.max()),
    }


# --- notebook 07: B1-0 and B1-1 ---------------------------------------------


def b1_product():
    """research/results/b1-beam-product.json (B1-0, derived statistics only)."""
    return load_results(B1_PRODUCT_ARCHIVE)


def b1_gates(record=None):
    """The three frozen B1-0 gates as measured."""
    import pandas as pd

    record = record or b1_product()
    g0a, g0b, g0c = record["g0a"], record["g0b"], record["g0c"]
    rows = {
        "G0a reader and orientation": {
            "measured": f"median centroid error {g0a['median_centroid_error_arcmin']}′ "
            f"({g0a['median_centroid_error_arcmin_if_flipped']}′ flipped); "
            f"width {g0a['width_definition']}, median relative error "
            f"{g0a['median_width_relative_error']}",
            "fits or channels": g0a["fits"],
            "pass": g0a["pass"],
        },
        "G0b frequency interpolation": {
            "measured": f"median max |ΔI_b| {g0b['median_max_abs_dI_main_lobe']}, "
            f"95th percentile {g0b['p95_max_abs_dI_main_lobe']}",
            "fits or channels": g0b["held_out_channels"],
            "pass": g0b["pass"],
        },
        "G0c spatial interpolation": {
            "measured": f"max |ΔI_b| inside half power {g0c['max_abs_dI_half_power']}",
            "fits or channels": g0c["channels"],
            "pass": g0c["pass"],
        },
    }
    return pd.DataFrame(rows).T


def b1_comparison(record=None):
    """katbeam and EIDOS against the holography beam (medians over the 82
    product channels in 900–1650 MHz; |ΔI| as a fraction of on-axis)."""
    import pandas as pd

    record = record or b1_product()
    s = record["summary"]
    labels = {
        "fwhm_major_ratio_median": "I FWHM major / holography",
        "fwhm_minor_ratio_median": "I FWHM minor / holography",
        "core_max_median": "max |ΔI|, core (r ≤ r_HP)",
        "lobe_max_median": "max |ΔI|, main lobe",
        "lobe_rms_median": "RMS |ΔI|, main lobe",
        "sidelobe_max_median": "max |ΔI|, first-sidelobe annulus",
        "sidelobe_rms_median": "RMS |ΔI|, first-sidelobe annulus",
        "first_sidelobe_level_median": "first-sidelobe level",
        "ring_max_over_30arcsec_signal_median": "max |ΔI| on the HP ring / 30″ signal",
        "pks1934_flux_weighted_mean_abs_dI_median": "PKS 1934−638 field, flux-weighted |ΔI|",
    }
    frame = pd.DataFrame(
        {
            model: {labels[k]: s[model][k] for k in labels}
            for model in ("katbeam", "eidos")
        }
    )
    frame["holography"] = None
    frame.loc["first-sidelobe level", "holography"] = s["holography"][
        "first_sidelobe_level_median"
    ]
    return frame


def b1_per_channel_figure(record=None):
    """Per channel, in units of the 30″ signal on the half-power ring, how far
    katbeam and EIDOS are from the holography beam; and the first-sidelobe
    level of all three."""
    record = record or b1_product()
    channels = record["per_channel"]
    freq = np.array([c["freq_mhz"] for c in channels])
    fig, axes = _plot.figure(1, 2, width=9, height=3.4)
    ax = axes[0, 0]
    for k, model in enumerate(("katbeam", "eidos")):
        ax.plot(
            freq,
            [c[model]["ring_max_over_30arcsec_signal"] for c in channels],
            ".-",
            color=f"C{k}",
            label=model,
        )
    ax.axhline(1, color="0.4", ls="--", lw=0.8, label="= the 30″ signal")
    ax.set_yscale("log")
    from matplotlib.ticker import FormatStrFormatter

    ax.yaxis.set_major_formatter(FormatStrFormatter("%g"))
    ax.yaxis.set_minor_formatter(FormatStrFormatter("%g"))
    ax.set_xlabel("frequency (MHz)")
    ax.set_ylabel("max |ΔI| on HP ring / 30″ signal")
    ax.legend(fontsize="small")
    ax = axes[0, 1]
    for model, colour in (("holography", "k"), ("katbeam", "C0"), ("eidos", "C1")):
        ax.plot(
            freq,
            [100 * c[model]["first_sidelobe_level"] for c in channels],
            ".-",
            color=colour,
            label=model,
        )
    ax.set_xlabel("frequency (MHz)")
    ax.set_ylabel("first-sidelobe level (% of on-axis)")
    ax.legend(fontsize="small")
    fig.suptitle("B1-0: the controls against the measured beam (archive)")
    return fig


def b1_antenna_spread_figure(record=None):
    """RMS over the 64 antennas of I_b(antenna) − I_b(array average) in the
    main lobe, per product channel."""
    record = record or b1_product()
    rows = record["antenna_spread"]["per_channel"]
    freq = np.array([r["freq_mhz"] for r in rows])
    fig, axes = _plot.figure(width=6, height=3.2)
    ax = axes[0, 0]
    ax.plot(
        freq,
        [100 * r["rms_over_antennas_main_lobe"] for r in rows],
        ".-",
        label="main lobe",
    )
    ax.plot(freq, [100 * r["rms_over_antennas_core"] for r in rows], ".-", label="core")
    ax.set_xlabel("frequency (MHz)")
    ax.set_ylabel("RMS over antennas (% of on-axis)")
    ax.legend(fontsize="small")
    ax.set_title("B1-0: antenna-to-antenna beam spread (archive)", fontsize="small")
    return fig


def pointing_fixture(cache_dir):
    """The whole public fixture (`outer_scans/`: five scans and the
    pipeline's reference offsets), extracted once under `cache_dir`, never
    into the checkout. Returns the directory that holds `outer_scans/`."""
    from .data import download_fixture, find_fixture

    cache_dir = Path(cache_dir)
    done = cache_dir / "fixture-outer-scans"
    if (done / "COMPLETE").is_file():
        return done
    archive = find_fixture()
    if archive is None or archive.is_dir():
        archive = download_fixture(cache_dir)
    if _sha256(archive) != FIXTURE_SHA256:
        raise ValueError(f"{archive} is not the pinned public fixture")
    partial = cache_dir / "fixture-outer-scans.partial"
    if partial.exists():
        import shutil

        shutil.rmtree(partial)
    partial.mkdir(parents=True)
    with zipfile.ZipFile(archive) as zipped:
        for info in _safe_members(zipped, "outer_scans/"):
            if PurePosixPath(info.filename).parts[0] == "outer_scans":
                zipped.extract(info, partial)
    (partial / "COMPLETE").write_text(FIXTURE_SHA256 + "\n")
    if done.exists():
        import shutil

        shutil.rmtree(done)
    partial.replace(done)
    return done


def b1_baseline_module():
    """`examples/b1_baselines.py` (the port of the SARAO/SKA fit) from the
    checkout, or None outside one."""
    root = checkout_root()
    path = root / "examples" / "b1_baselines.py" if root else None
    if path is None or not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("rang_b1_baselines", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def b1_baseline_live(cache_dir):
    """B1-1 (i) live: the ported Gaussian fit on the five fixture scans,
    against the pipeline's own `reference_offsets.txt` (gate G1a), and the
    per-antenna estimate in arcmin. None outside a checkout."""
    import time

    import pandas as pd

    port = b1_baseline_module()
    if port is None:
        return None
    root = pointing_fixture(cache_dir)
    started = time.perf_counter()
    scans, reference, _ = port.load_fixture(root, root)
    base = port.run_baseline(scans)
    seconds = time.perf_counter() - started
    ref = reference[:, 1:].astype(float)
    names = [str(n) for n in reference[:, 0]]
    diff = np.abs(base["rows"] - ref)
    arcmin = np.degrees(base["rows"][:, [0, 1, 2, 3]]) * 60
    valid = np.array([[f["valid"] for f in fits] for fits in base["fits"]])
    estimate = pd.DataFrame(
        {
            "xEl (arcmin)": arcmin[:, 0],
            "σ xEl": arcmin[:, 1],
            "El (arcmin)": arcmin[:, 2],
            "σ El": arcmin[:, 3],
            "valid chunks": valid.sum(axis=1),
            "chunks": valid.shape[1],
            "|offset| / σ (max of the axes)": np.max(
                np.abs(arcmin[:, [0, 2]]) / arcmin[:, [1, 3]], axis=1
            ),
        },
        index=pd.Index(names, name="antenna"),
    )
    g1a = {
        "max |port − reference| over all 12 columns": float(diff.max()),
        "criterion (upstream test, decimal=6)": 1.5e-6,
        "pass": bool(np.all(diff < 1.5e-6)),
        "seconds (read + fit)": seconds,
    }
    return {"g1a": g1a, "estimate": estimate, "base": base, "names": names}


def b1_baselines_archive():
    """The B1-1 (i) archive with G1b, from `research/results/` when committed,
    else from the ignored run directory; (record, path) or None."""
    path = results_path(B1_BASELINES_ARCHIVE)
    if path is None:
        for root in _search_roots():
            candidate = root / "outputs" / B1_BASELINES_RUN / B1_BASELINES_ARCHIVE
            if candidate.is_file():
                path = candidate
                break
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8")), path


def g1b_table(record):
    """G1b per injection: noise-free error, mean and RMS error over the
    seeds, and the coverage of the formal 1σ interval (arcmin)."""
    import pandas as pd

    rows = []
    antennas = record.get("antennas", ["m000", "m001", "m002", "m003"])
    for case in record["g1b"]["cases"]:
        inj = tuple(case["injected_arcmin"])
        for a, name in enumerate(antennas):
            rows.append(
                {
                    "injected (xEl, El)": inj,
                    "antenna": name,
                    "noise-free error xEl": case["noiseless_error_arcmin"][a][0],
                    "noise-free error El": case["noiseless_error_arcmin"][a][1],
                    "RMS error xEl": case["rms_error_arcmin"][a][0],
                    "RMS error El": case["rms_error_arcmin"][a][1],
                    "1σ coverage (all antennas)": case["coverage_1sigma"],
                }
            )
    return pd.DataFrame(rows).set_index(["injected (xEl, El)", "antenna"])


def g1b_figure(record):
    """Recovered against injected offset per antenna along each axis (G1b,
    noise-free): a slope above one is over-recovery, an offset at zero bias."""
    antennas = record.get("antennas", ["m000", "m001", "m002", "m003"])
    cases = record["g1b"]["cases"]
    fig, axes = _plot.figure(1, 2, width=8.4, height=3.4, sharey=True)
    for axis, name in enumerate(("xEl", "El")):
        ax = axes[0, axis]
        picked = [c for c in cases if c["injected_arcmin"][1 - axis] == 0]
        picked.sort(key=lambda c: c["injected_arcmin"][axis])
        inj = np.array([c["injected_arcmin"][axis] for c in picked])
        for a, ant in enumerate(antennas):
            err = np.array([c["noiseless_error_arcmin"][a][axis] for c in picked])
            ax.plot(inj, inj + err, ".-", label=ant)
        lim = np.max(np.abs(inj)) * 1.8
        ax.plot([-lim, lim], [-lim, lim], color="0.5", lw=0.8, ls="--", label="truth")
        ax.set_xlabel(f"injected {name} (arcmin)")
        ax.set_title(name, fontsize="small")
    axes[0, 0].set_ylabel("recovered (arcmin)")
    axes[0, 0].legend(fontsize="x-small")
    fig.suptitle("G1b: the Gaussian fit against the measured beam, noise-free")
    return fig


def find_holography():
    """The local B1-0 product directory (CC BY-NC 4.0, never committed):
    `RANG_HOLOGRAPHY_PRODUCT`, else `outputs/b1-20261030-05-holography`."""
    configured = os.environ.get("RANG_HOLOGRAPHY_PRODUCT")
    candidates = [Path(configured)] if configured else []
    candidates += [root / "outputs" / HOLOGRAPHY_RUN for root in _search_roots()]
    for path in candidates:
        if all(
            (path / name).is_file()
            for name in ("small.npz", "manifest.json", "array_average_native.npy")
        ):
            return path
    return None


def holography_figure(
    product_dir, freqs_hz=(0.95e9, 1.284e9, 1.6e9), half_width_deg=3.0
):
    """Array-average Stokes I power beam of the holography product (dB) at a
    few frequencies, and katbeam minus holography at the middle one."""
    from ..beam_holography import HolographyBeam, KatBeam, grid

    beam = HolographyBeam(product_dir, flip=1)
    x, y = grid(half_width_deg, 0.03)
    ext = (-half_width_deg, half_width_deg, -half_width_deg, half_width_deg)
    fig, axes = _plot.figure(
        1, len(freqs_hz) + 1, width=3.3 * (len(freqs_hz) + 1), height=3.2
    )
    for ax, f in zip(axes.flat, freqs_hz):
        power = beam.power_i("array_average", x, y, f)
        im = ax.imshow(
            10 * np.log10(np.maximum(power, 1e-5)),
            origin="lower",
            extent=ext,
            vmin=-40,
            vmax=0,
            cmap="viridis",
        )
        ax.set_title(f"holography I_b, {f / 1e6:.0f} MHz", fontsize="small")
        ax.set_xlabel("x (deg)")
    fig.colorbar(im, ax=axes[0, len(freqs_hz) - 1], label="dB")
    middle = freqs_hz[len(freqs_hz) // 2]
    diff = KatBeam().power_i(0, x, y, middle) - beam.power_i(
        "array_average", x, y, middle
    )
    lim = float(np.max(np.abs(diff)))
    ax = axes[0, -1]
    im = ax.imshow(
        100 * diff,
        origin="lower",
        extent=ext,
        cmap="RdBu_r",
        vmin=-100 * lim,
        vmax=100 * lim,
    )
    fig.colorbar(im, ax=ax, label="% of on-axis")
    ax.set_title(f"katbeam − holography, {middle / 1e6:.0f} MHz", fontsize="small")
    ax.set_xlabel("x (deg)")
    axes[0, 0].set_ylabel("y (deg)")
    return fig
