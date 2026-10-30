"""L1-M: the PKS 1934-638 field model under L1's frozen campaign
(research/l1-model-completeness.md).

Three calibrator models on LUNO row chunk 0, each through L1's
`core_campaign_array.run` unedited:

- `stored`: the decoded MODEL_DATA (L1's model);
- `point`: CARACal's lsm A0 component alone, predicted by the core;
- `field`: all 196 lsm components, predicted by the core.

The model hook wraps the array module's `decode_inputs` (to keep the row
indices) and `build_state` (to replace `state["model"]` after the seed-7
split is drawn with the stored model), inside a scoped try/finally. After
each run the same process adds `l1m.json`: the model record, split hashes,
gain-grid coordinates, the `original` arm's band losses and the matched
cross-model losses against the earlier runs. The checker compares the runs
(Q1-Q3), applies L1's own checker to each, and the archive keeps numbers and
hashes only. Original FLAG and FLAG_ROW are never modified.

CARACal's lsm is GPL-2.0 and is not committed: `fetch_lsm` downloads it at
the pinned commit and refuses it unless its SHA256 matches.
"""

import json
import math
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from . import core, core_campaign, core_fetch, core_zarr, lsm
from . import core_campaign_array as array
from .core_campaign import array_sha256, call, file_sha256, rss_mb, write_json
from .core_workflow import gain_grid
from .flagging import fixed_support_tv, gain_tv, polar_gauge

ROOT = core_campaign.ROOT
CARACAL_COMMIT = "8f7bb363876f5f0daecbf2167c36bb597c7e5160"
LSM_LAST_CHANGE = "59ad90deffa4d25b76c91d2b0ce6435cfbaed229"
LSM_REPO_PATH = "caracal/data/meerkat_files/pks1934-638.lsm"
LSM_URL = (
    "https://raw.githubusercontent.com/caracal-pipeline/caracal/"
    f"{CARACAL_COMMIT}/{LSM_REPO_PATH}"
)
LSM_NAME = "pks1934-638.lsm"
LSM_SHA256 = "0964b9f4c547bb802bfb16a2e8fdccddff84beeec05b6f3492521a46fa77d101"
LSM_BYTES = 31_241
LSM_COMPONENTS = 196
LSM_GAUSSIANS = 15
LSM_LICENCE = "CARACal GPL-2.0 (pyproject); not committed to Rang"
MODEL_ARMS = ("stored", "point", "field")
CORR_LINEAR = (9, 10, 11, 12)
DFT_TOLERANCE = 1e-9
PA_BOUND = 0.01
DFT_ROWS, DFT_CHANNELS = 200, 64
PREDICT_ROWS = 1024
MIN_AVAILABLE_GIB = 14
LENGTH_BANDS = ((0, 200), (200, 1000), (1000, 3000), (3000, 9000))
QUARTERS = 4
COMPARED_ARMS = ("original", "tricolour-firstpass", "tricolour-mild")
L1_RUN = ROOT / "outputs/luno-array-campaign-20261030-01"
LIGHTSPEED = 299_792_458.0
CODE_FILES = (
    *array.CODE_FILES,
    "python/rangtoy/lsm.py",
    "python/rangtoy/core_campaign_fieldmodel.py",
)


# --- the field model ---------------------------------------------------------


def verify_lsm(path, sha=LSM_SHA256):
    digest = file_sha256(path)
    if digest != sha:
        raise ValueError(f"{path}: SHA256 {digest} is not the pinned {sha}")
    return digest


def fetch_lsm(out_dir, url=LSM_URL, sha=LSM_SHA256):
    """The lsm at the pinned commit in `out_dir`, downloaded if absent."""
    out_dir = Path(out_dir)
    path = out_dir / LSM_NAME
    record = {"url": url, "commit": CARACAL_COMMIT, "last_change": LSM_LAST_CHANGE}
    if not path.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read()
        partial = path.with_suffix(".part")
        partial.write_bytes(payload)
        verify_lsm(partial, sha)
        partial.rename(path)
        record["downloaded_seconds"] = time.perf_counter() - started
    record["sha256"] = verify_lsm(path, sha)
    record["bytes"] = path.stat().st_size
    record["licence"] = LSM_LICENCE
    return path, record


def model_sources(sources, arm):
    """The component list of a model arm: the brightest alone, or all."""
    if arm == "point":
        return [max(sources, key=lambda s: s.i)]
    if arm == "field":
        return list(sources)
    raise ValueError(f"model arm {arm!r} is not predicted")


def predict_stokes_i(uvw, frequency, comps, rows=None):
    """`core.predict_components` for the given rows (all by default)."""
    uvw = uvw if rows is None else uvw[rows]
    return core.predict_components(
        uvw,
        frequency,
        comps["lm"],
        comps["kind"],
        comps["flux"],
        comps["coeffs"],
        comps["log_poly"],
        comps["ref_freq"],
        comps["gauss_shape"],
    )


def direct_dft(uvw, frequency, comps):
    """Independent NumPy prediction of Stokes I (row, chan) from the formulas
    of the protocol: positive phase, FWHM Gaussians with PA east of north."""
    u, v, w = (uvw[:, k][:, None, None] for k in range(3))
    nu = np.asarray(frequency, float)[None, :, None]
    lm = comps["lm"]
    l, m = lm[:, 0], lm[:, 1]
    n1 = np.sqrt(1.0 - l * l - m * m) - 1.0
    log = np.log(nu / comps["ref_freq"])
    exponent = sum(
        comps["coeffs"][:, k] * log ** (k + 1) for k in range(comps["coeffs"].shape[1])
    )
    spectrum = comps["flux"] * np.exp(exponent)
    phase = 2 * np.pi * nu / LIGHTSPEED * (u * l + v * m + w * n1)
    major, minor, pa = comps["gauss_shape"].T
    along = (u * np.sin(pa) + v * np.cos(pa)) * nu / LIGHTSPEED
    across = (u * np.cos(pa) - v * np.sin(pa)) * nu / LIGHTSPEED
    gauss = comps["kind"] == 1
    envelope = np.exp(
        -(np.pi**2)
        / (4 * math.log(2))
        * ((major * along) ** 2 + (minor * across) ** 2)
        * gauss
    )
    return np.sum(spectrum * envelope * np.exp(1j * phase), axis=-1)


def subset(nrow, nchan, rows=DFT_ROWS, channels=DFT_CHANNELS):
    return (
        np.unique(np.linspace(0, nrow - 1, min(rows, nrow)).astype(int)),
        np.unique(np.linspace(0, nchan - 1, min(channels, nchan)).astype(int)),
    )


def prediction_checks(uvw, frequency, sources, phase_centre):
    """The protocol's DFT check (all components) and the PA bound."""
    rows, chans = subset(len(uvw), len(frequency))
    comps = lsm.components(sources, phase_centre)
    sub_uvw, sub_freq = uvw[rows], frequency[chans]
    predicted = predict_stokes_i(sub_uvw, sub_freq, comps)
    reference = direct_dft(sub_uvw, sub_freq, comps)
    peak = float(np.abs(reference).max())
    dft = float(np.abs(predicted - reference).max() / peak)
    point = predict_stokes_i(
        sub_uvw, sub_freq, lsm.components(model_sources(sources, "point"), phase_centre)
    )
    field_rms = float(np.sqrt(np.mean(np.abs(predicted - point) ** 2)))
    gaussians = [s for s in sources if s.gaussian]
    pa_max = 0.0
    if gaussians:
        gcomps = lsm.components(gaussians, phase_centre)
        rotated = {**gcomps, "gauss_shape": gcomps["gauss_shape"].copy()}
        rotated["gauss_shape"][:, 2] += np.pi / 2
        pa_max = float(
            np.abs(
                predict_stokes_i(sub_uvw, sub_freq, gcomps)
                - predict_stokes_i(sub_uvw, sub_freq, rotated)
            ).max()
        )
    out = {
        "rows": len(rows),
        "channels": len(chans),
        "dft_max_abs_over_peak": dft,
        "dft_tolerance": DFT_TOLERANCE,
        "field_term_rms_jy": field_rms,
        "pa90_max_abs_jy": pa_max,
        "pa_bound_fraction_of_field_rms": PA_BOUND,
    }
    out["dft_pass"] = bool(dft <= DFT_TOLERANCE)
    out["pa_pass"] = bool(pa_max <= PA_BOUND * field_rms) if field_rms > 0 else True
    out["pass"] = out["dft_pass"] and out["pa_pass"]
    return out


def write_model(model, uvw, frequency, comps, block=PREDICT_ROWS):
    """Overwrite a (row, chan, 4) complex64 model in place: XX = YY = I."""
    nrow = model.shape[0]
    finite = True
    for start in range(0, nrow, block):
        rows = slice(start, min(start + block, nrow))
        stokes = predict_stokes_i(uvw[rows], frequency, comps)
        finite &= bool(np.isfinite(stokes).all())
        model[rows, :, 0] = stokes
        model[rows, :, 1] = 0
        model[rows, :, 2] = 0
        model[rows, :, 3] = stokes
    return finite


def model_diagnostic(model, uvw, eligible, block=PREDICT_ROWS):
    """Model Stokes I by baseline length on eligible samples (row blocks)."""
    length = np.hypot(uvw[:, 0], uvw[:, 1])
    out = {}
    for lo, hi in LENGTH_BANDS:
        rows = np.flatnonzero((length >= lo) & (length < hi))
        values = []
        for start in range(0, len(rows), block):
            r = rows[start : start + block]
            stokes = 0.5 * (model[r, :, 0] + model[r, :, 3])
            values.append(stokes[eligible[r]])
        values = np.concatenate(values) if values else np.zeros(0, np.complex64)
        if values.size:
            out[f"{lo}-{hi} m"] = {
                "rows": len(rows),
                "samples": int(values.size),
                "median_abs_I": float(np.median(np.abs(values))),
                "mean_re_I": float(np.mean(values.real)),
            }
    return out


# --- the model hook ----------------------------------------------------------


class ModelHook:
    """Replaces `state["model"]` after L1's split; keeps what `post_run` needs."""

    def __init__(self, arm, sources=None):
        if arm not in MODEL_ARMS:
            raise ValueError(f"unknown model arm {arm!r}")
        if arm != "stored" and not sources:
            raise ValueError("a predicted model arm needs the lsm sources")
        self.arm = arm
        self.sources = sources
        self.record = {"arm": arm}
        self.state = self.extra = self.rows = None
        self.stations = None

    @contextmanager
    def installed(self):
        decode, build = array.decode_inputs, array.build_state
        self._decode, self._build = decode, build

        def decode_inputs(stations=None, roots=array.ROOTS):
            arrays, rows, stats = decode(stations, roots)
            self.rows, self.stations = rows, stations
            return arrays, rows, stats

        array.decode_inputs = decode_inputs
        array.build_state = self.build_state
        try:
            yield self
        finally:
            array.decode_inputs, array.build_state = decode, build

    def build_state(self, arrays, extra, nant, *args, **kwargs):
        state = self._build(arrays, extra, nant, *args, **kwargs)
        corr = tuple(int(c) for c in extra["corr_type"])
        if corr != CORR_LINEAR:
            raise RuntimeError(f"CORR_TYPE {corr} is not XX, XY, YX, YY")
        record = self.record
        record["split_sha256"] = {
            k: array_sha256(state[k])
            for k in ("eligible", "train", "validation", "test")
        }
        record["phase_dir_rad"] = [float(x) for x in extra["phase_dir"]]
        record["stored_diagnostic"] = model_diagnostic(
            state["model"], extra["uvw"], state["eligible"]
        )
        if self.arm != "stored":
            if any(s.q or s.u or s.v for s in self.sources):
                raise RuntimeError("polarised components: feed convention not frozen")
            chosen = model_sources(self.sources, self.arm)
            comps = lsm.components(chosen, extra["phase_dir"])
            started = time.perf_counter()
            record["checks"] = prediction_checks(
                extra["uvw"], extra["chan_freq"], self.sources, extra["phase_dir"]
            )
            if not record["checks"]["pass"]:
                raise RuntimeError(f"prediction checks failed: {record['checks']}")
            record["finite"] = write_model(
                state["model"], extra["uvw"], extra["chan_freq"], comps
            )
            record["predict_seconds"] = time.perf_counter() - started
            if not record["finite"]:
                raise RuntimeError("the predicted model is not finite")
            record["components"] = lsm.summary(chosen)
            record["diagnostic"] = model_diagnostic(
                state["model"], extra["uvw"], state["eligible"]
            )
        else:
            record["diagnostic"] = record["stored_diagnostic"]
        self.state, self.extra = state, extra
        return state


# --- after the run -----------------------------------------------------------


def load_gains(run_dir, arm):
    with np.load(Path(run_dir) / "gains" / f"{arm}.npz") as stored:
        return {"gains": stored["gains"], "gain_valid": stored["gain_valid"]}


def band_masks(state, uvw, base):
    """`base` restricted to each baseline band and each channel quarter."""
    length = np.hypot(uvw[:, 0], uvw[:, 1])
    nchan = base.shape[1]
    masks = {}
    for lo, hi in LENGTH_BANDS:
        rows = (length >= lo) & (length < hi)
        masks[f"{lo}-{hi} m"] = base & rows[:, None]
    for k in range(QUARTERS):
        chans = np.zeros(nchan, bool)
        chans[k * nchan // QUARTERS : (k + 1) * nchan // QUARTERS] = True
        masks[f"quarter {k}"] = base & chans[None, :]
    return masks


def band_losses(state, uvw, diagnostics):
    out = {}
    for name, mask in band_masks(state, uvw, state["test"]).items():
        if mask.any():
            result = array.restricted_losses(
                state, {"diagnostics": diagnostics}, {"test": mask}
            )
            out[name] = result["test"]
    return out


def decode_stored_model(hook):
    """Decode the stored MODEL_DATA of the hooked run's rows into its state."""
    out = hook.state["model"]
    lo, _ = array.CHANNELS
    meta = core_zarr.array_meta(array.resolve(f"{array.GROUP}/MODEL_DATA"))
    nchan, ncorr = meta["chunks"][1], meta["chunks"][2]
    dtype = np.dtype(meta["dtype"])
    if dtype != out.dtype:
        raise RuntimeError(f"stored MODEL_DATA dtype {dtype} differs from {out.dtype}")
    row_bytes = nchan * ncorr * dtype.itemsize
    for tile in array.TILES:
        first = tile * nchan - lo
        core_fetch.read_rows_into(
            array.resolve(f"{array.GROUP}/MODEL_DATA/0.{tile}.0"),
            row_bytes,
            hook.rows,
            out,
            first * ncorr * dtype.itemsize,
        )


def set_model(hook, arm):
    """Put model arm `arm` into the hooked state."""
    if arm == "stored":
        decode_stored_model(hook)
        return
    comps = lsm.components(model_sources(hook.sources, arm), hook.extra["phase_dir"])
    write_model(hook.state["model"], hook.extra["uvw"], hook.extra["chan_freq"], comps)


def matched_model_losses(hook, run_dir, others):
    """For each compared arm: the held-out samples that every model's gains
    predict validly, and each model's own-model loss on them.

    `others` maps an earlier model arm to its run directory. The hooked
    state's model is changed in turn and left as the last one set."""
    state = hook.state
    time_map, freq_map, _, _ = gain_grid(state, *core_campaign.GRID)
    runs = {hook.arm: Path(run_dir), **{k: Path(v) for k, v in others.items()}}
    gains = {
        arm: {m: load_gains(d, arm) for m, d in runs.items()} for arm in COMPARED_ARMS
    }
    masks = {}
    for arm in COMPARED_ARMS:
        ok = np.ones_like(state["test"])
        for g in gains[arm].values():
            ok &= array.valid_prediction(state, g["gain_valid"], time_map, freq_map)
        masks[arm] = {
            "validation": state["validation"] & ok,
            "test": state["test"] & ok,
            "dropped_test": int(np.count_nonzero(state["test"] & ~ok)),
            "dropped_validation": int(np.count_nonzero(state["validation"] & ~ok)),
        }
    out = {
        arm: {
            "dropped_test": masks[arm]["dropped_test"],
            "dropped_validation": masks[arm]["dropped_validation"],
            "losses": {},
        }
        for arm in COMPARED_ARMS
    }
    order = [hook.arm] + [m for m in runs if m != hook.arm]
    for model in order:
        if model != hook.arm:
            set_model(hook, model)
        for arm in COMPARED_ARMS:
            result = array.restricted_losses(
                state,
                {"diagnostics": gains[arm][model]},
                {k: masks[arm][k] for k in ("validation", "test")},
            )
            out[arm]["losses"][model] = {k: v["loss"] for k, v in result.items()}
    return out


def post_run(run_dir, hook, others=None, started=None):
    """`l1m.json`: model record, grid, band losses, matched cross-model losses."""
    run_dir = Path(run_dir)
    state, extra = hook.state, hook.extra
    _, _, gain_times, gain_freqs = gain_grid(state, *core_campaign.GRID)
    mark = time.perf_counter()
    original = load_gains(run_dir, "original")
    bands = band_losses(state, extra["uvw"], original)
    band_seconds = time.perf_counter() - mark
    mark = time.perf_counter()
    matched = matched_model_losses(hook, run_dir, others) if others else None
    record = {
        "protocol": "research/l1-model-completeness.md",
        "model": hook.record,
        "stations": "all" if hook.stations is None else list(hook.stations),
        "gain_times": [float(x) for x in gain_times],
        "gain_freqs": [float(x) for x in gain_freqs],
        "original_band_test_losses": bands,
        "matched_model_losses": matched,
        "compared_runs": {k: str(v) for k, v in (others or {}).items()},
        "seconds": {
            "band_losses": band_seconds,
            "matched": time.perf_counter() - mark,
            "total_process": None if started is None else time.perf_counter() - started,
        },
        "max_rss_mb": rss_mb(),
        "code_sha256": {name: file_sha256(ROOT / name) for name in CODE_FILES},
    }
    write_json(run_dir / "l1m.json", record)
    return record


def run(
    run_dir,
    arm,
    lsm_path=None,
    stations=None,
    precondition_dir=None,
    label="frozen",
    others=None,
):
    """L1's campaign under model arm `arm`, then `l1m.json`."""
    started = time.perf_counter()
    sources = None
    if arm != "stored":
        verify_lsm(lsm_path)
        sources = lsm.load(lsm_path)
    hook = ModelHook(arm, sources)
    if lsm_path is not None:
        hook.record["lsm"] = {"path": str(lsm_path), "sha256": file_sha256(lsm_path)}
    with hook.installed():
        result = array.run(
            run_dir,
            stations=stations,
            precondition_dir=precondition_dir,
            label=f"{label}; L1-M model arm {arm}",
        )
    record = post_run(run_dir, hook, others, started)
    hook.state = None
    return result, record


# --- comparisons -------------------------------------------------------------


def _get(value, *path):
    for key in path:
        if value is None:
            return None
        value = value.get(key) if isinstance(value, dict) else value[key]
    return value


TRICOLOUR_FIELDS = (
    "strategy_sha256",
    "window_flag_fraction",
    "newly_flagged_cells",
    "additions_on_train",
    "checks",
)
CANDIDATE_FIELDS = (
    "trial",
    "policy",
    "mask_sha256",
    "mask_count",
    "added_count",
    "fixed_support_tv_vs_base",
    "losses",
    "invalid_predictions",
    "converged_fraction",
    "objective",
    "accepted",
    "rejection",
    "error",
)
ARM_FIELDS = (
    ("additions_sha256",),
    ("gains_sha256",),
    ("final_flag_fraction",),
    ("fixed_support_tv_vs_original",),
    ("metrics", "losses"),
    ("metrics", "tv"),
    ("metrics", "raw_tv"),
    ("metrics", "valid_gain_fraction"),
    ("metrics", "invalid_predictions"),
    ("metrics", "solver", "converged_fraction"),
    ("metrics", "solver", "iterations"),
)


def compare_with_l1(result, candidates, l1_result, l1_candidates):
    """The stored comparator gate: non-image, non-timing fields against L1."""
    diffs = []

    def same(a, b, where):
        if a != b:
            diffs.append(where)

    same(result["split"], l1_result["split"], "split")
    for label, arm in l1_result["arms"].items():
        mine = result["arms"].get(label)
        if (arm is None) != (mine is None):
            diffs.append(f"arms/{label}/availability")
            continue
        if arm is None:
            continue
        for path in ARM_FIELDS:
            same(_get(mine, *path), _get(arm, *path), f"arms/{label}/{'/'.join(path)}")
    for label, t in l1_result["tricolour"].items():
        a = result["tricolour"][label]
        for key in TRICOLOUR_FIELDS:
            same(a.get(key), t.get(key), f"tricolour/{label}/{key}")
    for key, trials in l1_candidates.items():
        mine = candidates.get(key, [])
        if len(mine) != len(trials):
            diffs.append(f"candidates/{key}/count")
            continue
        for k, (a, b) in enumerate(zip(mine, trials)):
            for field in CANDIDATE_FIELDS:
                same(a.get(field), b.get(field), f"candidates/{key}/{k}/{field}")
    same(
        [h["mse_test"] for h in result["hypotheses"]],
        [h["mse_test"] for h in l1_result["hypotheses"]],
        "hypotheses/mse_test",
    )
    a1, b1 = result.get("amendment_1", {}), l1_result.get("amendment_1", {})
    same(_strip_seconds(a1), _strip_seconds(b1), "amendment_1")
    return {"equal": not diffs, "differences": diffs[:50], "count": len(diffs)}


def _strip_seconds(value):
    if isinstance(value, dict):
        return {k: _strip_seconds(v) for k, v in value.items() if "seconds" not in k}
    if isinstance(value, list):
        return [_strip_seconds(v) for v in value]
    return value


def per_antenna_tv(gains, valid, scale, reference=0):
    """Per-antenna amplitude and phase TV of the polar-gauge aligned diagonals."""
    aligned, ok = polar_gauge(gains, valid, reference)
    diag = aligned[..., [0, 1], [0, 1]]  # (t, f, a, 2)
    amp, phase = np.abs(diag), np.angle(diag)
    nant = gains.shape[2]
    sums = {"amplitude": np.zeros(nant), "phase": np.zeros(nant)}
    counts = np.zeros(nant)
    for axis in (0, 1):
        lo = [slice(None)] * 3
        hi = [slice(None)] * 3
        lo[axis], hi[axis] = slice(None, -1), slice(1, None)
        pair = ok[tuple(lo)] & ok[tuple(hi)]  # (t', f', a)
        da = np.abs(amp[tuple(hi)] - amp[tuple(lo)]).sum(-1)
        dp = np.abs(np.angle(np.exp(1j * (phase[tuple(hi)] - phase[tuple(lo)])))).sum(
            -1
        )
        sums["amplitude"] += np.where(pair, da, 0).sum(axis=(0, 1))
        sums["phase"] += np.where(pair, dp, 0).sum(axis=(0, 1))
        counts += 2 * pair.sum(axis=(0, 1))
    with np.errstate(invalid="ignore", divide="ignore"):
        amplitude = sums["amplitude"] / counts / scale
        phase_tv = sums["phase"] / counts
    return {
        "amplitude": [None if not np.isfinite(x) else float(x) for x in amplitude],
        "phase_rad": [None if not np.isfinite(x) else float(x) for x in phase_tv],
        "pairs": [int(c) for c in counts],
    }


def tv_edges(gains, valid, times, freqs, scale):
    aligned, ok = polar_gauge(gains, valid)
    return gain_tv(aligned, ok, np.asarray(times), np.asarray(freqs), scale=scale)


def compare_models(runs):
    """Q1-Q3 from the three runs' `result.json`, `l1m.json` and gains."""
    results = {m: _load(Path(d) / "result.json") for m, d in runs.items()}
    extras = {m: _load(Path(d) / "l1m.json") for m, d in runs.items()}
    stored = results["stored"]
    scale = stored["arms"]["original"]["metrics"]["scale"]
    times, freqs = extras["stored"]["gain_times"], extras["stored"]["gain_freqs"]
    gains = {m: load_gains(d, "original") for m, d in runs.items()}
    edges = {
        m: tv_edges(g["gains"], g["gain_valid"], times, freqs, scale)
        for m, g in gains.items()
    }
    per_antenna = {
        m: per_antenna_tv(g["gains"], g["gain_valid"], scale) for m, g in gains.items()
    }
    out = {"scale": scale, "models": {}, "q1": {}, "q2": {}, "q3": {}}
    for m, r in results.items():
        o = r["arms"]["original"]
        out["models"][m] = {
            "losses": o["metrics"]["losses"],
            "converged_fraction": o["metrics"]["solver"]["converged_fraction"],
            "valid_gain_fraction": o["metrics"]["valid_gain_fraction"],
            "own_scale_tv": o["metrics"]["tv"],
            "tv_at_stored_scale_and_support": fixed_support_tv(
                edges[m]["edges"], edges["stored"]["edges"]
            ),
            "tv_time_frequency_at_stored_scale": [
                edges[m]["time"],
                edges[m]["frequency"],
            ],
            "median_diagonal_amplitude": o["metrics"]["median_diagonal_amplitude"],
            "median_offdiagonal_amplitude": o["metrics"][
                "median_offdiagonal_amplitude"
            ],
            "image": {
                k: o["image"].get(k)
                for k in (
                    "peak_jy_per_beam",
                    "flux_recovery",
                    "offsource_rms",
                    "offsource_robust_sigma",
                    "residual_rms",
                    "residual_robust_sigma_offsource",
                )
                if k in o["image"]
            },
            "band_test_losses": extras[m]["original_band_test_losses"],
            "per_antenna_tv": per_antenna[m],
            "hypotheses": r["hypotheses"],
            "amendment_1_pairs": _get(r, "amendment_1", "pairs"),
            "tv_policy": _policy(r, "tv-policy"),
            "split_sha256": extras[m]["model"]["split_sha256"],
            "tricolour_additions_sha256": {
                a: _get(r, "arms", a, "additions_sha256")
                for a in ("tricolour-firstpass", "tricolour-mild")
            },
        }
    matched = extras["field"].get("matched_model_losses") or {}
    for cand, ref, role in (
        ("field", "stored", "primary"),
        ("field", "point", "secondary"),
    ):
        key = f"{cand} vs {ref}"
        mc, mr = out["models"][cand], out["models"][ref]
        q1 = {
            "role": role,
            "original_mse_test": call(mc["losses"]["test"], mr["losses"]["test"]),
            "original_mse_validation": call(
                mc["losses"]["validation"], mr["losses"]["validation"]
            ),
            "original_chi2_train": call(mc["losses"]["train"], mr["losses"]["train"]),
            "converged_fraction": [mc["converged_fraction"], mr["converged_fraction"]],
            "matched": {},
            "bands": {
                b: call(
                    mc["band_test_losses"][b]["loss"], mr["band_test_losses"][b]["loss"]
                )
                for b in mc["band_test_losses"]
                if b in mr["band_test_losses"]
            },
        }
        for arm, rec in matched.items():
            losses = rec["losses"]
            if cand in losses and ref in losses:
                q1["matched"][arm] = {
                    "mse_test": call(losses[cand]["test"], losses[ref]["test"]),
                    "mse_validation": call(
                        losses[cand]["validation"], losses[ref]["validation"]
                    ),
                    "dropped_test": rec["dropped_test"],
                }
        out["q1"][key] = q1
        ratios = [
            a / b
            for a, b in zip(
                mc["per_antenna_tv"]["amplitude"], mr["per_antenna_tv"]["amplitude"]
            )
            if a is not None and b
        ]
        pratios = [
            a / b
            for a, b in zip(
                mc["per_antenna_tv"]["phase_rad"], mr["per_antenna_tv"]["phase_rad"]
            )
            if a is not None and b
        ]
        out["q2"][key] = {
            "role": role,
            "tv_at_stored_scale_and_support": tv_call(
                mc["tv_at_stored_scale_and_support"],
                mr["tv_at_stored_scale_and_support"],
            ),
            "own_scale_tv": tv_call(mc["own_scale_tv"], mr["own_scale_tv"]),
            "median_per_antenna_amplitude_tv_ratio": float(np.median(ratios))
            if ratios
            else None,
            "median_per_antenna_phase_tv_ratio": float(np.median(pratios))
            if pratios
            else None,
        }
    for m, mo in out["models"].items():
        primary = mo["hypotheses"][0]["mse_test"]["call"]
        out["q3"][m] = {
            "headline_primary": primary,
            "headline_matched": _matched_headline(results[m]),
            "tv_policy": mo["tv_policy"],
            "tv_guided_selected": bool(
                mo["tv_policy"] and (mo["tv_policy"].get("tv_weight") or 0) > 0
            ),
        }
    base = out["q3"]["stored"]
    out["q3"]["decision_changes"] = {
        m: _changed(out["q3"][m], base) for m in out["q3"] if m in ("point", "field")
    }
    return out


TV_CALLS = {"better": "drops", "worse": "rises"}


def tv_call(candidate, reference):
    """The frozen +-1 % rule on TV, named for TV: drops, rises, null."""
    out = call(candidate, reference)
    out["call"] = TV_CALLS.get(out["call"], out["call"])
    return out


def _policy(result, label):
    policy = _get(result, "arms", label, "policy")
    if policy is None:
        return None
    return {k: policy.get(k) for k in ("threshold", "tv_weight") if k in policy} | {
        "additions": _get(result, "arms", label, "additions")
    }


def _matched_headline(result):
    pairs = _get(result, "amendment_1", "pairs") or []
    for pair in pairs:
        if (
            pair.get("candidate") == "tv-policy"
            and pair.get("reference") == "tricolour-firstpass"
        ):
            return _get(pair, "mse_test", "call")
    return None


def _changed(a, b):
    return bool(
        a["headline_primary"] != b["headline_primary"]
        or a["headline_matched"] != b["headline_matched"]
        or (a["tv_policy"] or {}).get("tv_weight")
        != (b["tv_policy"] or {}).get("tv_weight")
    )


def _load(path):
    return json.loads(Path(path).read_text())


# --- the checker -------------------------------------------------------------


def check(runs, precondition_dir, check_dir, lsm_path, l1_run=L1_RUN):
    """Criteria 1-7 of the protocol and Q1-Q3."""
    runs = {m: Path(d) for m, d in runs.items()}
    check_dir = Path(check_dir)
    check_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    criteria = {}
    pre = _load(Path(precondition_dir) / "result.json")
    from . import core_campaign_1830  # L2's tolerant replay comparison

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
    sources = lsm.load(lsm_path)
    summary = lsm.summary(sources)
    extras = {m: _load(d / "l1m.json") for m, d in runs.items()}
    model_checks = {
        m: e["model"].get("checks") for m, e in extras.items() if m != "stored"
    }
    criteria["2_field_model"] = {
        "pass": bool(
            file_sha256(lsm_path) == LSM_SHA256
            and summary["components"] == LSM_COMPONENTS
            and summary["gaussians"] == LSM_GAUSSIANS
            and summary["polarised"] == 0
            and all(c and c["pass"] for c in model_checks.values())
            and all(extras[m]["model"].get("finite") for m in model_checks)
        ),
        "sha256": file_sha256(lsm_path),
        "summary": summary,
        "checks": model_checks,
    }
    results = {m: _load(d / "result.json") for m, d in runs.items()}
    split = {m: e["model"]["split_sha256"] for m, e in extras.items()}
    tric = {
        m: {
            a: _get(r, "arms", a, "additions_sha256")
            for a in ("tricolour-firstpass", "tricolour-mild")
        }
        for m, r in results.items()
    }
    criteria["3_same_split_and_flags"] = {
        "pass": len({json.dumps(v, sort_keys=True) for v in split.values()}) == 1
        and len({json.dumps(v, sort_keys=True) for v in tric.values()}) == 1,
        "split_sha256": split["stored"],
        "tricolour_additions_sha256": tric["stored"],
    }
    gate = compare_with_l1(
        results["stored"],
        _load(runs["stored"] / "candidates.json"),
        _load(Path(l1_run) / "result.json"),
        _load(Path(l1_run) / "candidates.json"),
    )
    criteria["4_stored_equals_l1"] = {"pass": gate["equal"], **gate}
    l1_checks = {}
    for m, d in runs.items():
        summary_m = array.check(d, precondition_dir, check_dir / f"l1-check-{m}")
        l1_checks[m] = {k: v["pass"] for k, v in summary_m["criteria"].items()}
    criteria["5_l1_criteria_evaluated"] = {"pass": True, "by_model": l1_checks}
    comparison = compare_models(runs)
    decidable = {
        k: v["original_mse_test"]["call"] != "undecidable"
        for k, v in comparison["q1"].items()
    }
    criteria["6_questions"] = {"pass": True, "q1_decidable": decidable}
    files_ok = all(
        (d / "l1m.json").exists() and (d / "result.json").exists()
        for d in runs.values()
    )
    criteria["7_outputs"] = {"pass": files_ok}
    out = {
        "protocol": "research/l1-model-completeness.md",
        "runs": {m: str(d) for m, d in runs.items()},
        "precondition": str(precondition_dir),
        "criteria": criteria,
        "all_pass": all(c["pass"] for c in criteria.values()),
        "comparison": comparison,
        "result_sha256": {m: file_sha256(d / "result.json") for m, d in runs.items()},
        "l1m_sha256": {m: file_sha256(d / "l1m.json") for m, d in runs.items()},
        "check_seconds": time.perf_counter() - started,
    }
    write_json(check_dir / "result.json", out)
    return out


ARCHIVE_ARM_KEYS = (
    "additions",
    "additions_fraction_of_train",
    "final_flag_fraction",
    "fixed_support_tv_vs_original",
    "additions_sha256",
    "gains_sha256",
)


def archive(check_dir, out_path):
    """The compact archive: per-model arms, Q1-Q3, criteria, hashes."""
    check_dir = Path(check_dir)
    checked = _load(check_dir / "result.json")
    runs = {m: Path(d) for m, d in checked["runs"].items()}
    models = {}
    for m, d in runs.items():
        r = _load(d / "result.json")
        e = _load(d / "l1m.json")
        arms = {}
        for label, arm in r["arms"].items():
            if arm is None:
                arms[label] = None
                continue
            metrics = arm["metrics"]
            arms[label] = {
                **{k: arm.get(k) for k in ARCHIVE_ARM_KEYS},
                "policy": arm.get("policy"),
                "losses": metrics["losses"],
                "invalid_predictions": metrics["invalid_predictions"],
                "tv": metrics["tv"],
                "raw_tv": metrics["raw_tv"],
                "time_tv": metrics["time_tv"],
                "frequency_tv": metrics["frequency_tv"],
                "scale": metrics["scale"],
                "converged_fraction": metrics["solver"]["converged_fraction"],
                "valid_gain_fraction": metrics["valid_gain_fraction"],
                "median_diagonal_amplitude": metrics["median_diagonal_amplitude"],
                "image": arm["image"],
            }
        models[m] = {
            "run_dir": str(d),
            "label": r["label"],
            "split": r["split"],
            "arms": arms,
            "unavailable": r.get("unavailable"),
            "hypotheses": r["hypotheses"],
            "amendment_1": r.get("amendment_1"),
            "cost_clause": r["cost_clause"],
            "stages": {k: v.get("seconds") for k, v in r["stages"].items()},
            "wall_seconds": r["wall_seconds"],
            "max_rss_mb": r["max_rss_mb"],
            "memory": r["memory"],
            "l1m": {
                k: v for k, v in e.items() if k not in ("gain_times", "gain_freqs")
            },
        }
    payload = {
        "schema_version": 1,
        "task": "L1-M",
        "protocol": "research/l1-model-completeness.md",
        "visibilities_redistributed": False,
        "field_model": {
            "url": LSM_URL,
            "commit": CARACAL_COMMIT,
            "last_change": LSM_LAST_CHANGE,
            "sha256": LSM_SHA256,
            "bytes": LSM_BYTES,
            "licence": LSM_LICENCE,
        },
        "criteria": checked["criteria"],
        "all_pass": checked["all_pass"],
        "comparison": checked["comparison"],
        "models": models,
        "result_sha256": checked["result_sha256"],
        "l1m_sha256": checked["l1m_sha256"],
        "check_result_sha256": file_sha256(check_dir / "result.json"),
    }
    write_json(out_path, payload)
    return payload


__all__ = [
    "MODEL_ARMS",
    "ModelHook",
    "archive",
    "check",
    "compare_models",
    "compare_with_l1",
    "direct_dft",
    "fetch_lsm",
    "matched_model_losses",
    "model_sources",
    "per_antenna_tv",
    "post_run",
    "prediction_checks",
    "run",
    "verify_lsm",
    "write_model",
]
