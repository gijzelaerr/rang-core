"""The LUNO 1934-638 campaign on the core (research/core-k-luno-campaign.md).

Task K of research/core-parallel-plan.md: the first real-data science run
with the Rust core. Fetch (`core_fetch`), decode (`core_zarr`), the frozen
holdout split, the core solver and fused pass (`core_workflow.core_solve`),
TV and the frozen policy loop, the Tricolour/CARACAL port (`core_flag`) as
the comparator, and corrected-data dirty images (`core_weights`,
`core_grid`). No Measurement Set, container, QuartiCal, Tricolour or
WSClean. Original FLAG and FLAG_ROW are never modified: every arm's flags
are new arrays built with `flagging.protected_flags`.

The licence precondition was settled by the user on 2026-10-30
(research/big-plan.md); the protocol's other caveats stand.
"""

import json
import platform
import subprocess
import time
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import core, core_fetch, core_flag, core_grid, core_weights, core_zarr, rusage
from .core_policy import (
    assert_preserved,
    fixed_support_tv,
    policy_mask,
    protected_flags,
    residual_features,
    split_holdout,
)
from .core_workflow import core_solve, gain_grid

ROOT = Path(__file__).resolve().parents[2]
BUCKET = (
    "https://ratt-public-data.s3.af-south-1.amazonaws.com/LBAND_LUNO_CALIBRATORS.zarr"
)
GROUP = "MAIN/MAIN_1"
STATIONS = (0, 1, 2, 3)
TILES = range(8, 24)
CHANNELS = (1024, 3072)
EXTRA_OBJECTS = (
    "MAIN/MAIN_1/.zattrs",
    "MAIN/MAIN_1/UVW/.zarray",
    "MAIN/MAIN_1/UVW/0.0",
    "ANTENNA/ANTENNA_0/POSITION/.zarray",
    "ANTENNA/ANTENNA_0/POSITION/0.0",
    "ANTENNA/ANTENNA_0/NAME/.zarray",
    "ANTENNA/ANTENNA_0/NAME/0",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ/.zarray",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ/0.0",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH/.zarray",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH/0.0",
    "FIELD/FIELD_0/PHASE_DIR/.zarray",
    "FIELD/FIELD_0/PHASE_DIR/0.0.0",
    "FIELD/FIELD_0/NAME/.zarray",
    "FIELD/FIELD_0/NAME/0",
    "POLARIZATION/POLARIZATION_0/CORR_TYPE/.zarray",
    "POLARIZATION/POLARIZATION_0/CORR_TYPE/0.0",
)
SPLIT_SEED = 7
GRID = (2, 32)
ITERATIONS = 50
THRESHOLDS = (8.0, 5.0, 3.0)
TV_WEIGHTS = (0.0, 1.0, 3.0)
MAX_FRACTION = 0.02
FLAG_PENALTY = 2.0
VALIDATION_WEIGHT = 0.25
VALIDATION_TOLERANCE = 0.01
STRATEGY_DIR = ROOT / "outputs/caracal-strategy-inputs-8f7bb363"
STRATEGIES = {
    "tricolour-firstpass": "mk_rfi_flagging_calibrator_fields_firstpass.yaml",
    "tricolour-mild": "calibrator_mild_flagging.yaml",
}
OR_ACCUMULATED = {
    "flag_nans_zeros",
    "apply_static_mask",
    "sum_threshold",
    "flag_autos",
    "combine_with_input_flags",
}
IMAGE = {
    "width": 512,
    "height": 512,
    "scale_arcsec": 8.0,
    "w_layers": 64,
    "kernel_size": 7,
    "oversampling": 1023,
    "padding": 1.2,
}
ROBUST = 0.5
PEAK_BOX = 9
OFFSOURCE_BOX = 64
BETTER, WORSE = 0.99, 1.01
ARCHIVED_INPUTS = (
    "outputs/luno-support-20261029-01",
    "outputs/luno-solve-20261029-02",
    "outputs/core-g-20261029-01",
    "outputs/core-section6-20261029-02",
    "outputs/caracal-strategy-inputs-8f7bb363",
)
SUPPORT = ROOT / "outputs/luno-support-20261029-01/slice"
SOLVE_INPUTS = ROOT / "outputs/luno-solve-20261029-02/inputs"
QC_SOLVE = ROOT / "outputs/luno-solve-20261029-02/solve"
SECTION6_ARCHIVE = ROOT / "research/results/core-section6.json"
SECTION6_RUN = ROOT / "outputs/core-section6-20261029-02"
SOLVED_ARCHIVE = ROOT / "research/results/meerkat-luno-solved.json"
CODE_FILES = (
    "python/rang/core.py",
    "python/rang/core_campaign.py",
    "python/rang/core_fetch.py",
    "python/rang/core_flag.py",
    "python/rang/core_grid.py",
    "python/rang/core_weights.py",
    "python/rang/core_workflow.py",
    "python/rang/core_zarr.py",
    "python/rang/core_policy.py",
    "examples/prototype_section6.py",
)


# --- small helpers -----------------------------------------------------------


def file_sha256(path):
    h = sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def array_sha256(array):
    return sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def rss_mb():
    return rusage.peak_rss_mb()


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=_json_default) + "\n")


def _json_default(value):
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def snapshot(root):
    root = Path(root)
    return {
        str(p.relative_to(root)): [p.stat().st_size, p.stat().st_mtime_ns]
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def git_status():
    try:
        return subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def receipt_lines(*paths):
    """`size sha256 key` lines of the archived curl receipts, keyed by object."""
    hashes = {}
    for path in paths:
        for line in Path(path).read_text().splitlines():
            size, digest, key = line.split()
            hashes[key] = (int(size), digest)
    return hashes


# --- fetch and decode --------------------------------------------------------


def fetch_extra(base_url, out, keys=EXTRA_OBJECTS):
    """Whole GETs of the small objects the campaign needs beyond task G's slice."""
    out = Path(out)
    client = core_fetch.Client(base_url)
    records = []
    started = time.perf_counter()
    try:
        for key in keys:
            record, body = client.get(key)
            dest = out / "objects" / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            records.append(record)
    finally:
        client.close()
    seconds = time.perf_counter() - started
    write_json(out / "receipt-extra.json", records)
    return {
        "requests": len(records),
        "attempts": sum(len(r["attempts"]) for r in records),
        "bytes": sum(r["bytes"] for r in records),
        "seconds": seconds,
    }


def decode_object(objects, array_key, chunk):
    """Decode one zarr chunk under `objects/`: numeric arrays, or json2 strings.

    json2 object arrays decode as plain JSON (numcodecs' JSON codec appends
    the dtype string and the shape); nothing else is accepted.
    """
    objects = Path(objects)
    meta = json.loads((objects / array_key / ".zarray").read_text())
    if meta["compressor"]["id"] != "blosc":
        raise ValueError(f"{array_key}: only blosc arrays are supported")
    raw = core.blosc_decode((objects / array_key / chunk).read_bytes())
    if meta["dtype"] == "|O":
        if [f["id"] for f in meta.get("filters") or []] != ["json2"]:
            raise ValueError(f"{array_key}: object array without json2")
        items = json.loads(bytes(raw).decode("utf-8"))
        return np.array(items[:-2], dtype=object).reshape(items[-1])
    if meta.get("filters"):
        raise ValueError(f"{array_key}: filtered arrays are not supported")
    index = [int(i) for i in chunk.split(".")]
    full = np.frombuffer(raw, np.dtype(meta["dtype"])).reshape(meta["chunks"])
    return full[
        tuple(
            slice(0, min(c, s - i * c))
            for c, s, i in zip(meta["chunks"], meta["shape"], index)
        )
    ]


def decode_extra(fetched, rows, channels=CHANNELS):
    """Geometry and metadata for the kept rows from the extra objects."""
    objects = Path(fetched) / "objects"
    attrs = json.loads((objects / GROUP / ".zattrs").read_text())
    field = int(attrs["FIELD_ID"])
    lo, hi = channels
    uvw = decode_object(objects, f"{GROUP}/UVW", "0.0")
    return {
        "field_id": field,
        "scan_number": int(attrs["SCAN_NUMBER"]),
        "uvw": np.ascontiguousarray(uvw[np.asarray(rows)], np.float64),
        "antenna_position": np.ascontiguousarray(
            decode_object(objects, "ANTENNA/ANTENNA_0/POSITION", "0.0"), np.float64
        ),
        "antenna_names": [
            str(n) for n in decode_object(objects, "ANTENNA/ANTENNA_0/NAME", "0")
        ],
        "chan_freq": np.ascontiguousarray(
            decode_object(
                objects, "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ", "0.0"
            )[0, lo:hi],
            np.float64,
        ),
        "chan_width": np.ascontiguousarray(
            decode_object(
                objects, "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH", "0.0"
            )[0, lo:hi],
            np.float64,
        ),
        "phase_dir": np.asarray(
            decode_object(objects, "FIELD/FIELD_0/PHASE_DIR", "0.0.0")[field, 0],
            np.float64,
        ),
        "field_name": str(decode_object(objects, "FIELD/FIELD_0/NAME", "0")[field]),
        "corr_type": np.ascontiguousarray(
            decode_object(objects, "POLARIZATION/POLARIZATION_0/CORR_TYPE", "0.0")[0],
            np.int32,
        ),
    }


# --- state, arms, loop -------------------------------------------------------


def build_state(arrays, extra, seed=SPLIT_SEED, grid=GRID):
    """The frozen `flagging_workflow.prepare` state from in-memory arrays."""
    data = np.ascontiguousarray(arrays["DATA"], np.complex64)
    model = np.ascontiguousarray(arrays["MODEL_DATA"], np.complex64)
    weights = np.ascontiguousarray(arrays["WEIGHT_SPECTRUM"], np.float32)
    flags = np.ascontiguousarray(arrays["FLAG"], bool)
    rows = np.ascontiguousarray(arrays["FLAG_ROW"], bool)
    p = np.ascontiguousarray(arrays["ANTENNA1"], np.int32)
    q = np.ascontiguousarray(arrays["ANTENNA2"], np.int32)
    times = np.ascontiguousarray(arrays["TIME"], np.float64)
    names = list(extra["antenna_names"][: max(STATIONS) + 1])
    protected, _ = protected_flags(flags, rows, np.zeros_like(flags))
    eligible = (
        ~protected.any(axis=-1)
        & (p != q)[:, None]
        & np.isfinite(data).all(axis=-1)
        & np.isfinite(weights).all(axis=-1)
        & (weights > 0).all(axis=-1)
        & np.isfinite(model).all(axis=-1)
    )
    nant = len(names)
    time_bins = np.unique(times, return_inverse=True)[1] // grid[0]
    freq_bins = np.arange(data.shape[1]) // grid[1]
    groups = (
        time_bins[:, None] * (freq_bins.max() + 1) + freq_bins[None]
    ) * nant**2 + (p * nant + q)[:, None]
    train, validation, test = split_holdout(eligible, seed, groups=groups)
    return {
        "original_flags": flags,
        "original_rows": rows,
        "data": data,
        "model": model,
        "weights": weights,
        "times": times,
        "frequencies": extra["chan_freq"],
        "antenna1": p,
        "antenna2": q,
        "names": names,
        "eligible": eligible,
        "train": train,
        "validation": validation,
        "test": test,
        "window": np.ones(data.shape[1], bool),
    }


def solve_arm(state, added, label, scale=None):
    """One core solve with the frozen settings; returns a dict of products."""
    metrics, tv, residuals, guidance, diagnostics = core_solve(
        state, added, *GRID, ITERATIONS, trial=label, scale=scale
    )
    gains = diagnostics["gains"]
    valid = diagnostics["gain_valid"]
    diag = np.abs(gains[valid][:, [0, 1], [0, 1]])
    off = np.abs(gains[valid][:, [0, 1], [1, 0]])
    metrics["median_diagonal_amplitude"] = float(np.median(diag)) if diag.size else None
    metrics["median_offdiagonal_amplitude"] = (
        float(np.median(off)) if off.size else None
    )
    return {
        "label": label,
        "added": np.asarray(added, bool),
        "metrics": metrics,
        "tv": tv,
        "residuals": residuals,
        "guidance": guidance,
        "diagnostics": diagnostics,
    }


def tricolour_checks(result, input_flags, strategies, block=4096):
    """Criterion 5: superset of the input, uniform over correlations, monotone.

    The superset and uniformity tests run in row blocks, so no full-cube
    temporary is made (research/p5-memory.md); the booleans are the same."""
    flags = result["flags"]
    superset = True
    uniform = True
    for start in range(0, len(flags), block):
        part = flags[start : start + block]
        superset &= not np.any(input_flags[start : start + block] & ~part)
        uniform &= bool(np.all(part == part[..., :1]))
    fractions = {k: float(v.mean()) for k, v in result["stages"].items()}
    monotone = True
    previous = None
    for step, (name, fraction) in zip(strategies, fractions.items()):
        if previous is not None and step["task"] in OR_ACCUMULATED:
            monotone &= fraction >= previous - 1e-12
        previous = fraction
    return {
        "superset_of_input": bool(superset),
        "uniform_over_correlations": uniform,
        "monotone_or_steps": bool(monotone),
        "stage_fractions": fractions,
        "flag_fraction": float(flags.mean()),
        "pass": bool(superset and uniform and monotone),
    }


def tricolour_arm(state, extra, strategy_path):
    """The comparator: the ported CARACAL strategy on DATA with the original flags."""
    text = Path(strategy_path).read_text()
    strategies = core_flag.parse_strategy(text)
    started = time.perf_counter()
    result = core_flag.flag_rows(
        state["data"],
        state["original_flags"],
        state["antenna1"],
        state["antenna2"],
        state["times"],
        extra["antenna_position"],
        state["frequencies"],
        extra["chan_width"],
        extra["corr_type"],
        strategies,
    )
    wall = time.perf_counter() - started
    additions = state["train"] & result["flags"].any(axis=-1)
    summary = {
        "strategy": Path(strategy_path).name,
        "strategy_sha256": sha256(text.encode()).hexdigest(),
        "steps": len(strategies),
        "core_seconds": result["seconds"],
        "wall_seconds": wall,
        "window_flag_fraction": float(result["flags"].mean()),
        "newly_flagged_cells": int(
            np.count_nonzero(result["flags"].any(-1) & ~state["original_flags"].any(-1))
        ),
        "additions_on_train": int(np.count_nonzero(additions)),
        "checks": tricolour_checks(result, state["original_flags"], strategies),
    }
    return additions, summary


def tv_loop(state, base, scale, prefix):
    """The frozen `flagging_workflow.train` loop (one round) on the core.

    `base` is the solve the candidates start from; its additions are kept
    under every candidate mask. Returns the trial records and the best.
    """
    base_added = base["added"]
    denominator = max(base["metrics"]["tv"], 1e-30)
    validation0 = base["metrics"]["losses"]["validation"]
    if (
        validation0 is None
        or fixed_support_tv(base["tv"]["edges"], base["tv"]["edges"]) is None
    ):
        raise RuntimeError(f"{prefix}: base solve has no validation loss or TV support")
    validation0 = max(validation0, 1e-30)
    best_objective = base["metrics"]["tv"] / denominator + VALIDATION_WEIGHT
    best = {"solve": base, "policy": None, "objective": best_objective}
    trials = [
        {
            "trial": base["label"],
            "policy": None,
            "objective": best_objective,
            "accepted": True,
            "added_count": int(base_added.sum()),
        }
    ]
    seen = {sha256(base_added.tobytes()).hexdigest()}
    outliers = residual_features(
        base["residuals"] * np.sqrt(state["weights"]),
        state["train"],
        state["antenna1"],
        state["antenna2"],
    )
    unguided = None
    for tv_weight in TV_WEIGHTS:
        for threshold in THRESHOLDS:
            mask = policy_mask(
                outliers,
                base["guidance"],
                state["train"],
                threshold=threshold,
                tv_weight=tv_weight,
                max_fraction=MAX_FRACTION,
            )
            added = base_added | mask
            policy = {"threshold": float(threshold), "tv_weight": float(tv_weight)}
            fingerprint = sha256(added.tobytes()).hexdigest()
            label = f"{prefix}-w{tv_weight:g}-z{threshold:g}"
            if fingerprint in seen:
                trials.append(
                    {
                        "trial": label,
                        "policy": policy,
                        "duplicate_mask": fingerprint,
                        "mask_count": int(mask.sum()),
                    }
                )
                continue
            seen.add(fingerprint)
            solve = solve_arm(state, added, label, scale=scale)
            tv_score = fixed_support_tv(solve["tv"]["edges"], base["tv"]["edges"])
            val = solve["metrics"]["losses"]["validation"]
            admissible = (
                tv_score is not None
                and val is not None
                and val <= (1 + VALIDATION_TOLERANCE) * validation0
            )
            objective = (
                tv_score / denominator
                + FLAG_PENALTY * (mask.sum() / np.count_nonzero(state["train"]))
                + VALIDATION_WEIGHT * val / validation0
                if admissible
                else None
            )
            accepted = bool(admissible and objective < best_objective)
            record = {
                "trial": label,
                "policy": policy,
                "mask_count": int(mask.sum()),
                "added_count": int(added.sum()),
                "fixed_support_tv_vs_base": tv_score,
                "losses": solve["metrics"]["losses"],
                "invalid_predictions": solve["metrics"]["invalid_predictions"],
                "converged_fraction": solve["metrics"]["solver"]["converged_fraction"],
                "objective": objective,
                "accepted": accepted,
                "rejection": None
                if admissible
                else "gain support loss or validation degradation",
                "mask_sha256": fingerprint,
            }
            if (
                tv_weight == 0
                and admissible
                and (unguided is None or objective < unguided["objective"])
            ):
                unguided = {"solve": solve, "policy": policy, "objective": objective}
            if accepted:
                best_objective = objective
                best = {"solve": solve, "policy": policy, "objective": objective}
            trials.append(record)
    return trials, best, unguided


# --- imaging -----------------------------------------------------------------


def apply_gains(data, gains, valid, antenna1, antenna2, time_bin, freq_bin):
    """Corrected visibilities G_p^{-1} V G_q^{-H}; cells with an invalid gain
    are returned as False in the mask and left as zeros."""
    data = np.asarray(data, np.complex64)
    nrow, nchan = data.shape[:2]
    tb = np.asarray(time_bin)[:, None]
    fb = np.asarray(freq_bin)[None, :]
    p = np.asarray(antenna1)[:, None]
    q = np.asarray(antenna2)[:, None]
    gp = gains[tb, fb, p]
    gq = gains[tb, fb, q]
    ok = valid[tb, fb, p] & valid[tb, fb, q]
    inv_p = np.zeros_like(gp)
    inv_q = np.zeros_like(gq)
    inv_p[ok] = np.linalg.inv(gp[ok])
    inv_q[ok] = np.linalg.inv(gq[ok])
    v = data.reshape(nrow, nchan, 2, 2).astype(np.complex128)
    corrected = inv_p @ v @ inv_q.conj().swapaxes(-1, -2)
    corrected[~ok] = 0
    return corrected.reshape(nrow, nchan, 4).astype(np.complex64), ok


def image_metrics(dirty, psf, model_flux=None):
    """Peak near the centre, PSF sidelobe, off-source RMS and the point-source
    residual RMS of `dirty - peak * PSF` (PSF unity at its centre)."""
    dirty = np.asarray(dirty, np.float64)
    psf = np.asarray(psf, np.float64)
    h, w = dirty.shape
    cy, cx = h // 2, w // 2
    r = PEAK_BOX // 2
    box = dirty[cy - r : cy + r + 1, cx - r : cx + r + 1]
    iy, ix = np.unravel_index(np.argmax(box), box.shape)
    py, px = cy - r + iy, cx - r + ix
    peak = float(dirty[py, px])
    centre = psf[cy, cx]
    psfn = psf / centre if centre else psf
    inner = np.zeros_like(dirty, bool)
    inner[cy - r : cy + r + 1, cx - r : cx + r + 1] = True
    sidelobe = float(np.abs(psfn[~inner]).max())
    far = np.ones_like(dirty, bool)
    o = OFFSOURCE_BOX // 2
    far[cy - o : cy + o, cx - o : cx + o] = False
    shifted = np.roll(np.roll(psfn, py - cy, axis=0), px - cx, axis=1)
    residual = dirty - peak * shifted
    out = {
        "peak_jy_per_beam": peak,
        "peak_pixel": [int(py), int(px)],
        "psf_centre": float(centre),
        "psf_max_sidelobe": sidelobe,
        # Reported beside the frozen 9 x 9 figure: the four-station main lobe
        # is wider than 9 pixels at 8 arcsec, so the frozen box sees the lobe.
        "psf_max_outside_offsource_box": float(np.abs(psfn[far]).max()),
        "offsource_rms": float(np.sqrt(np.mean(dirty[far] ** 2))),
        "residual_rms": float(np.sqrt(np.mean(residual**2))),
        "residual_rms_offsource": float(np.sqrt(np.mean(residual[far] ** 2))),
        "residual_max_abs": float(np.abs(residual).max()),
    }
    if model_flux:
        out["model_stokes_i_jy"] = float(model_flux)
        out["flux_recovery"] = peak / float(model_flux)
    return out


def image_arm(state, extra, solve, out_dir, label):
    """Corrected-data Stokes I dirty image of one arm on its final flags."""
    started = time.perf_counter()
    time_map, freq_map, _, _ = gain_grid(state, *GRID)
    corrected, ok = apply_gains(
        state["data"],
        solve["diagnostics"]["gains"],
        solve["diagnostics"]["gain_valid"],
        state["antenna1"],
        state["antenna2"],
        time_map,
        freq_map,
    )
    final, final_rows = protected_flags(
        state["original_flags"],
        state["original_rows"],
        np.broadcast_to(solve["added"][..., None], state["original_flags"].shape),
    )
    imaging_flags = final | ~ok[..., None]
    sample, weight = core_grid.stokes_i_reader(
        corrected, state["weights"], imaging_flags, flag_rows=final_rows
    )
    padded = core_weights.padded_size(IMAGE["width"], IMAGE["padding"])
    padded_h = core_weights.padded_size(IMAGE["height"], IMAGE["padding"])
    imaging = core_weights.imaging_weights(
        extra["uvw"],
        core_weights.wsclean_wavelengths(state["frequencies"]),
        weight,
        np.ones(len(weight), bool),
        mode="briggs",
        robust=ROBUST,
        width=padded,
        height=padded_h,
        pixel_scale=core_weights.pixel_scale_radians(IMAGE["scale_arcsec"]),
        return_grid=False,
    )
    weighted = time.perf_counter()
    products = core_grid.invert(
        extra["uvw"], state["frequencies"], sample, weight, imaging["weights"], **IMAGE
    )
    gridded = time.perf_counter()
    imaged = weight > 0
    model_i = np.real(state["model"][..., 0] + state["model"][..., 3]) * 0.5
    model_flux = float(model_i[imaged].mean()) if imaged.any() else None
    metrics = image_metrics(products["dirty"], products["psf"], model_flux)
    metrics["imaged_cells"] = int(imaged.sum())
    metrics["imaging_weight_sums"] = imaging["sums"]
    metrics["gridder"] = products["stats"]
    header = core_grid.wcs_header(
        extra["phase_dir"],
        IMAGE["width"],
        IMAGE["height"],
        IMAGE["scale_arcsec"],
        state["frequencies"],
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    extra_keys = {
        "WSCVWSUM": products["stats"]["visibility_weight_sum"],
        "WSCIMGWG": products["stats"]["image_weight"],
        "WSCNORMF": products["stats"]["psf_normalization"],
        "WSCNVIS": products["stats"]["gridded_count"],
        "WSCNWLAY": products["stats"]["n_w_layers"],
        "WSCDATAC": "CORRECTED_DATA",
        "WSCWEIGH": f"Briggs'({ROBUST})",
        "RANGARM": label,
    }
    core_grid.write_fits(
        out_dir / f"{label}-dirty.fits", products["dirty"], header, extra_keys
    )
    core_grid.write_fits(
        out_dir / f"{label}-psf.fits", products["psf"], header, extra_keys
    )
    metrics["seconds"] = {
        "correct_and_weights": weighted - started,
        "grid": gridded - weighted,
        "total": time.perf_counter() - started,
    }
    metrics["dirty_sha256"] = array_sha256(products["dirty"])
    metrics["psf_sha256"] = array_sha256(products["psf"])
    return metrics


# --- decision rule -----------------------------------------------------------


def call(candidate, reference):
    """Three-way call of the frozen rule; None values are undecidable."""
    if candidate is None or reference is None or not reference:
        return {"ratio": None, "call": "undecidable"}
    ratio = float(candidate) / float(reference)
    verdict = "better" if ratio <= BETTER else ("worse" if ratio >= WORSE else "null")
    return {"ratio": ratio, "call": verdict}


def hypothesis(arms, candidate, reference):
    c, r = arms[candidate], arms[reference]
    return {
        "candidate": candidate,
        "reference": reference,
        "mse_test": call(
            c["metrics"]["losses"]["test"], r["metrics"]["losses"]["test"]
        ),
        "residual_rms": call(c["image"]["residual_rms"], r["image"]["residual_rms"]),
        "mse_validation": call(
            c["metrics"]["losses"]["validation"], r["metrics"]["losses"]["validation"]
        ),
        "additions": [c["additions"], r["additions"]],
    }


# --- the section 6 reference -------------------------------------------------


def _section6():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "prototype_section6", ROOT / "examples/prototype_section6.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def section6_summary(arrays):
    """The unedited section 6 pass on `arrays`; hashes and counts only."""
    products, seconds = _section6().section6_pass(arrays)
    solution = products["solution"]
    return {
        "gains_sha256": array_sha256(solution.gains),
        "gain_flags_sha256": array_sha256(solution.flags),
        "chi2_train_mean_per_cell": products["chi2"],
        "iterations": solution.iterations,
        "converged_fraction": solution.converged_fraction,
        "flagged_gain_fraction": float(np.mean(solution.flags != 0)),
        "tv_total": products["tv"]["total"],
        "survey": products["survey"],
        "policy_mask_counts": {k: int(v.sum()) for k, v in products["masks"].items()},
        "policy_mask_sha256": {
            k: array_sha256(v) for k, v in products["masks"].items()
        },
        "step_seconds": seconds,
        "_gains": solution.gains,
        "_gain_flags": solution.flags,
    }


def precondition(out_dir):
    """Section 6 on the archived local tiles against the archives (protocol)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    arrays, ingest_stats = _section6().ingest()
    summary = section6_summary(arrays)
    gains, gflags = summary.pop("_gains"), summary.pop("_gain_flags")
    qc_gains = np.load(QC_SOLVE / "gains.npy").astype(np.complex128)
    qc_flagged = np.load(QC_SOLVE / "gain_flags.npy") != 0
    keep = ~qc_flagged
    worst = 0.0
    for p in range(4):
        for q in range(p + 1, 4):
            pair = keep[..., p] & keep[..., q]
            if pair.any():
                a = gains[..., p, :, :] @ gains[..., q, :, :].conj().swapaxes(-1, -2)
                b = qc_gains[..., p, :, :] @ qc_gains[..., q, :, :].conj().swapaxes(
                    -1, -2
                )
                worst = max(worst, float(np.abs(a - b)[pair].max()))
    section6 = json.loads(SECTION6_ARCHIVE.read_text())
    run02 = section6["run_02"]
    solved = json.loads(SOLVED_ARCHIVE.read_text())
    # The committed archive carries chi-squared and the mask counts; the mask
    # hashes live in the run's result.json, which the archive pins by SHA256.
    chi2_archived = run02.get("checks", {}).get("3_chi2", {}).get("core")
    if chi2_archived is None:
        chi2_archived = _find(run02, "chi2_train_mean_per_cell")
    counts_archived = _find(run02, "policy_mask_counts")
    run02_result = SECTION6_RUN / "result.json"
    run02_hash_ok = file_sha256(run02_result) == run02.get("result_sha256")
    masks_archived = (
        json.loads(run02_result.read_text()).get("policy_mask_sha256")
        if run02_hash_ok
        else None
    )
    checks = {
        "gain_flags_identical_to_quartical": bool(
            np.array_equal(gflags != 0, qc_flagged)
        ),
        "max_baseline_product_difference": worst,
        "chi2": summary["chi2_train_mean_per_cell"],
        "chi2_archived": chi2_archived,
        "survey": summary["survey"],
        "section6_run_result_hash_matches_archive": run02_hash_ok,
        "policy_masks_equal_archive": masks_archived == summary["policy_mask_sha256"],
        "policy_counts_equal_archive": counts_archived == summary["policy_mask_counts"],
        "converged_fraction": summary["converged_fraction"],
        "converged_fraction_archived": solved["solve_summary"]["conv_perc"][0][0],
        "flagged_gain_fraction": summary["flagged_gain_fraction"],
        "flagged_gain_fraction_archived": solved["solve_summary"][
            "flagged_gain_fraction"
        ],
        "archive_hashes": {
            "quartical_gains": file_sha256(QC_SOLVE / "gains.npy"),
            "quartical_gain_flags": file_sha256(QC_SOLVE / "gain_flags.npy"),
            "expected": solved["input_sha256"],
        },
    }
    passed = {
        "gain_flags": checks["gain_flags_identical_to_quartical"],
        "gain_products": worst <= 1e-6,
        "chi2": chi2_archived is not None
        and abs(summary["chi2_train_mean_per_cell"] - chi2_archived) <= 1e-9,
        "survey": summary["survey"]
        == {
            "fully_identified": 389,
            "underidentified": 43,
            "no_train": 592,
            "no_solved_gain": 0,
            "over_rank": 0,
            "status": {"fully_identified status0": 389, "underidentified status3": 43},
        },
        "policy_masks": bool(
            checks["policy_masks_equal_archive"]
            and checks["policy_counts_equal_archive"]
        ),
        "converged_fraction": abs(
            summary["converged_fraction"] - checks["converged_fraction_archived"]
        )
        <= 1e-12,
        "flagged_gain_fraction": abs(
            summary["flagged_gain_fraction"] - checks["flagged_gain_fraction_archived"]
        )
        <= 1e-12,
        "quartical_arrays_are_the_archived_ones": all(
            checks["archive_hashes"]["expected"][str(QC_SOLVE.relative_to(ROOT) / n)]
            == checks["archive_hashes"][k]
            for k, n in (
                ("quartical_gains", "gains.npy"),
                ("quartical_gain_flags", "gain_flags.npy"),
            )
        ),
    }
    result = {
        "protocol": "research/core-k-luno-campaign.md",
        "stage": "precondition",
        "passed": passed,
        "all_passed": all(passed.values()),
        "checks": checks,
        "section6": summary,
        "ingest": ingest_stats,
        "seconds": time.perf_counter() - started,
        "max_rss_mb": rss_mb(),
    }
    write_json(out_dir / "result.json", result)
    return result


def _find(tree, key):
    """First value of `key` anywhere in a nested dict."""
    if isinstance(tree, dict):
        if key in tree:
            return tree[key]
        for value in tree.values():
            found = _find(value, key)
            if found is not None:
                return found
    return None


# --- the campaign ------------------------------------------------------------


def run(run_dir, bucket=BUCKET, workers=8, precondition_dir=None):
    """The frozen campaign: fetch, decode, reference, arms, images, receipts."""
    run_dir = Path(run_dir)
    if run_dir.exists():
        raise FileExistsError(f"{run_dir} exists; use a fresh run directory")
    run_dir.mkdir(parents=True)
    core.library()
    before = {name: snapshot(ROOT / name) for name in ARCHIVED_INPUTS}
    status_before = git_status()
    wall = time.perf_counter()
    stages = {}

    def stage(name, started):
        stages[name] = {
            "seconds": time.perf_counter() - started,
            "max_rss_mb": rss_mb(),
        }

    # 1. Fetch.
    t = time.perf_counter()
    fetched = run_dir / "fetch"
    fetch = core_fetch.fetch_slice(
        bucket, GROUP, STATIONS, TILES, fetched, workers=workers
    )
    fetch_extra_result = fetch_extra(bucket, fetched)
    stage("fetch", t)
    # 2. Decode.
    t = time.perf_counter()
    arrays, decode_stats = core_fetch.decode_slice(fetched)
    rows = np.asarray(fetch["rows"])
    extra = decode_extra(fetched, rows)
    stage("decode", t)
    # 3. Reference: the section 6 pass on the fetched bytes (criterion 3).
    t = time.perf_counter()
    reference = section6_summary(arrays)
    reference.pop("_gains")
    reference.pop("_gain_flags")
    stage("section6_reference", t)
    # 4. State and split.
    t = time.perf_counter()
    state = build_state(arrays, extra)
    stage("split", t)
    split_counts = {
        k: int(np.count_nonzero(state[k]))
        for k in ("eligible", "train", "validation", "test")
    }
    arms = {}
    solves = {}
    candidates = {}
    # 5. Arms.
    t = time.perf_counter()
    zero = np.zeros_like(state["train"])
    original = solve_arm(state, zero, "original")
    scale0 = original["metrics"]["scale"]
    stage("solve_original", t)
    solves["original"] = original
    tricolour = {}
    for label, strategy in STRATEGIES.items():
        t = time.perf_counter()
        additions, summary = tricolour_arm(state, extra, STRATEGY_DIR / strategy)
        stage(f"flag_{label}", t)
        t = time.perf_counter()
        solves[label] = solve_arm(state, additions, label, scale=scale0)
        stage(f"solve_{label}", t)
        tricolour[label] = summary
    t = time.perf_counter()
    trials, best, unguided = tv_loop(state, original, scale0, "tv")
    stage("tv_loop", t)
    candidates["tv-policy"] = trials
    solves["tv-policy"] = {
        **best["solve"],
        "label": "tv-policy",
        "policy": best["policy"],
    }
    solves["tv-unguided-best"] = (
        {**unguided["solve"], "label": "tv-unguided-best", "policy": unguided["policy"]}
        if unguided is not None
        else None
    )
    t = time.perf_counter()
    trials2, best2, _ = tv_loop(
        state, solves["tricolour-firstpass"], scale0, "firstpass-tv"
    )
    stage("tv_loop_firstpass", t)
    candidates["tricolour-firstpass+tv"] = trials2
    solves["tricolour-firstpass+tv"] = {
        **best2["solve"],
        "label": "tricolour-firstpass+tv",
        "policy": best2["policy"],
    }
    # 6. Images and per-arm records.
    base_edges = original["tv"]["edges"]
    for label, solve in solves.items():
        if solve is None:
            arms[label] = None
            continue
        t = time.perf_counter()
        image = image_arm(state, extra, solve, run_dir / "images", label)
        stage(f"image_{label}", t)
        added = solve["added"]
        final, final_rows = protected_flags(
            state["original_flags"],
            state["original_rows"],
            np.broadcast_to(added[..., None], state["original_flags"].shape),
        )
        assert_preserved(
            state["original_flags"], state["original_rows"], final, final_rows
        )
        holdout_touched = int(np.count_nonzero(added & ~state["train"]))
        arms[label] = {
            "label": label,
            "source": solve["label"],
            "policy": solve.get("policy"),
            "metrics": solve["metrics"],
            "fixed_support_tv_vs_original": fixed_support_tv(
                solve["tv"]["edges"], base_edges
            ),
            "additions": int(added.sum()),
            "additions_fraction_of_train": float(added.sum() / split_counts["train"]),
            "final_flag_fraction": float(final.mean()),
            "original_flag_fraction": float(state["original_flags"].mean()),
            "flag_row_unchanged": bool(
                np.array_equal(final_rows, state["original_rows"])
            ),
            "superset_of_original": bool(not np.any(state["original_flags"] & ~final)),
            "holdout_cells_added": holdout_touched,
            "additions_sha256": array_sha256(added),
            "gains_sha256": array_sha256(solve["diagnostics"]["gains"]),
            "image": image,
        }
        (run_dir / "flags").mkdir(exist_ok=True)
        (run_dir / "gains").mkdir(exist_ok=True)
        np.savez_compressed(run_dir / "flags" / f"{label}.npz", additions=added)
        np.savez_compressed(
            run_dir / "gains" / f"{label}.npz",
            gains=solve["diagnostics"]["gains"],
            gain_valid=solve["diagnostics"]["gain_valid"],
        )
    # 7. Hypotheses and cost clause.
    hypotheses = [
        hypothesis(arms, "tv-policy", "tricolour-firstpass"),
        hypothesis(arms, "tv-policy", "original"),
        hypothesis(arms, "tricolour-firstpass+tv", "tricolour-firstpass"),
    ]
    tv_chain = stages["solve_original"]["seconds"] + stages["tv_loop"]["seconds"]
    cost = {
        "tv_chain_seconds": tv_chain,
        "tricolour_firstpass_seconds": stages["flag_tricolour-firstpass"]["seconds"],
        "ratio": tv_chain / stages["flag_tricolour-firstpass"]["seconds"],
        "limit_ratio": 3.0,
        "comparable": tv_chain <= 3.0 * stages["flag_tricolour-firstpass"]["seconds"],
    }
    total = time.perf_counter() - wall
    after = {name: snapshot(ROOT / name) for name in ARCHIVED_INPUTS}
    result = {
        "protocol": "research/core-k-luno-campaign.md",
        "provisional": "licence confirmation from SARAO pending; observer permission in chat 2026-10-29 15:36 SAST; WEIGHT_SPECTRUM is a QuartiCal product; 1934-638 model origin unlogged",
        "cells": {
            "group": GROUP,
            "field_id": extra["field_id"],
            "field_name": extra["field_name"],
            "scan_number": extra["scan_number"],
            "stations": list(STATIONS),
            "station_names": state["names"],
            "tiles": [TILES.start, TILES.stop],
            "channels": list(CHANNELS),
            "rows": len(rows),
            "shape": list(state["data"].shape),
            "frequency_range_mhz": [
                float(state["frequencies"][0] / 1e6),
                float(state["frequencies"][-1] / 1e6),
            ],
        },
        "fetch": {k: v for k, v in fetch.items() if k not in ("rows", "plans")},
        "fetch_extra": fetch_extra_result,
        "decode": decode_stats,
        "section6_reference": reference,
        "split": {"seed": SPLIT_SEED, "counts": split_counts},
        "tricolour": tricolour,
        "arms": arms,
        "hypotheses": hypotheses,
        "cost_clause": cost,
        "stages": stages,
        "wall_seconds": total,
        "max_rss_mb": rss_mb(),
        "settings": {
            "grid": GRID,
            "iterations": ITERATIONS,
            "thresholds": THRESHOLDS,
            "tv_weights": TV_WEIGHTS,
            "max_fraction": MAX_FRACTION,
            "flag_penalty": FLAG_PENALTY,
            "validation_weight": VALIDATION_WEIGHT,
            "validation_tolerance": VALIDATION_TOLERANCE,
            "image": IMAGE,
            "robust": ROBUST,
            "decision_band": [BETTER, WORSE],
        },
    }
    write_json(run_dir / "result.json", result)
    write_json(run_dir / "candidates.json", candidates)
    receipt = {
        "fetch_receipt": "fetch/receipt.json",
        "fetch_extra_receipt": "fetch/receipt-extra.json",
        "fetched_object_sha256": {
            r["key"]: r["sha256"]
            for r in json.loads((fetched / "receipt-extra.json").read_text())
        },
        "code_sha256": {name: file_sha256(ROOT / name) for name in CODE_FILES},
        "library": str(core.library_path()),
        "library_sha256": file_sha256(core.library_path()),
        "backend": core.backend_name(),
        "strategies": {
            label: file_sha256(STRATEGY_DIR / name)
            for label, name in STRATEGIES.items()
        },
        "static_masks": {p.name: file_sha256(p) for p in core_flag.static_mask_files()},
        "settings": result["settings"],
        "seed": SPLIT_SEED,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "precondition_dir": str(precondition_dir) if precondition_dir else None,
    }
    write_json(run_dir / "receipt.json", receipt)
    audit = {
        "inputs": list(ARCHIVED_INPUTS),
        "input_files_checked": sum(len(v) for v in before.values()),
        "inputs_unchanged": before == after,
        "changed": [
            f"{name}/{k}"
            for name in ARCHIVED_INPUTS
            for k in set(before[name]) | set(after[name])
            if before[name].get(k) != after[name].get(k)
        ][:20],
        "git_status_unchanged": status_before == git_status(),
        "run_dir_files": sorted(str(p.relative_to(run_dir)) for p in run_dir.iterdir()),
    }
    write_json(run_dir / "side-effects.json", audit)
    return result


# --- the checker -------------------------------------------------------------


def check(run_dir, precondition_dir, check_dir):
    """Criteria 1-7 of the protocol for one campaign run."""
    run_dir, precondition_dir, check_dir = (
        Path(run_dir),
        Path(precondition_dir),
        Path(check_dir),
    )
    check_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    result = json.loads((run_dir / "result.json").read_text())
    pre = json.loads((precondition_dir / "result.json").read_text())
    fetched = run_dir / "fetch"
    fetch_result = json.loads((fetched / "result.json").read_text())
    receipt = json.loads((fetched / "receipt.json").read_text())
    receipt_extra = json.loads((fetched / "receipt-extra.json").read_text())
    criteria = {}

    # 1. Fetch integrity.
    archived = receipt_lines(SUPPORT / "receipt.txt", SOLVE_INPUTS / "receipt.txt")

    def archived_path(key):
        # DATA tiles, UVW and the subtables live in the solve inputs; the
        # support slice holds the other MAIN_1 columns. Whichever exists.
        for root in (SUPPORT, SOLVE_INPUTS):
            if (root / key).exists():
                return root / key
        return SOLVE_INPUTS / key

    bad_status, bad_bytes = [], []
    handles = {}
    with ExitStack() as stack:
        for r in receipt + receipt_extra:
            path = archived_path(r["key"])
            size = path.stat().st_size
            if r["range"] is None:
                if r["status"] != 200 or r["bytes"] != size:
                    bad_status.append(r["key"])
                expected = file_sha256(path)
                line = archived.get(r["key"])
                if r["sha256"] != expected or (line and line[1] != expected):
                    bad_bytes.append(r["key"])
            else:
                start, end = r["range"]
                want = f"bytes {start}-{end - 1}/{size}"
                if r["status"] != 206 or r["headers"].get("Content-Range") != want:
                    bad_status.append([r["key"], r["range"]])
                if r["key"] not in handles:
                    handles[r["key"]] = stack.enter_context(open(path, "rb"))
                handle = handles[r["key"]]
                handle.seek(start)
                if sha256(handle.read(end - start)).hexdigest() != r["sha256"]:
                    bad_bytes.append([r["key"], r["range"]])
    arrays, _ = core_fetch.decode_slice(fetched)
    rows = np.asarray(fetch_result["rows"])
    array_ok = {}
    for name, dtype in fetch_result["row_columns"]:
        payload = (SUPPORT / GROUP / name / "0").read_bytes()
        values = np.frombuffer(core.blosc_decode(payload), dtype)[rows]
        array_ok[name] = bool(np.array_equal(arrays[name], values))
    for name in fetch_result["tile_columns"]:
        root = (SOLVE_INPUTS if name == "DATA" else SUPPORT) / GROUP / name
        meta = core_zarr.array_meta(root)
        nchan, ncorr = meta["chunks"][1], meta["chunks"][2]
        row_bytes = nchan * ncorr * np.dtype(meta["dtype"]).itemsize
        parts = []
        for tile in fetch_result["tiles"]:
            raw, _ = core_zarr.read_rows(root / f"0.{tile}.0", row_bytes, rows)
            parts.append(
                np.frombuffer(raw, meta["dtype"]).reshape(len(rows), nchan, ncorr)
            )
        expected = np.concatenate(parts, axis=1)
        array_ok[name] = bool(
            arrays[name].shape == expected.shape
            and np.array_equal(arrays[name].view(np.uint8), expected.view(np.uint8))
        )
    total_bytes = fetch_result["bytes"] + sum(r["bytes"] for r in receipt_extra)
    total_requests = fetch_result["requests"] + len(receipt_extra)
    criteria["1_fetch_integrity"] = {
        "pass": not bad_status
        and not bad_bytes
        and all(array_ok.values())
        and total_bytes <= 770_000_000
        and total_requests <= 2230,
        "bad_status": bad_status[:10],
        "bad_bytes": bad_bytes[:10],
        "arrays_equal_archive": array_ok,
        "bytes": total_bytes,
        "requests": total_requests,
        "attempts": fetch_result["attempts"]
        + sum(len(r["attempts"]) for r in receipt_extra),
        "seconds": fetch_result["seconds"],
        "task_g_seconds": 74.5,
        "task_g_bytes": 751_848_436,
    }

    # 2. Flags preserved and no side effects.
    audit = json.loads((run_dir / "side-effects.json").read_text())
    arms = {k: v for k, v in result["arms"].items() if v is not None}
    flag_ok = {
        label: arm["superset_of_original"]
        and arm["flag_row_unchanged"]
        and arm["holdout_cells_added"] == 0
        for label, arm in arms.items()
    }
    criteria["2_flags_preserved"] = {
        "pass": all(flag_ok.values()) and audit["inputs_unchanged"],
        "arms": flag_ok,
        "inputs_unchanged": audit["inputs_unchanged"],
        "input_files_checked": audit["input_files_checked"],
        "git_status_unchanged": audit["git_status_unchanged"],
    }

    # 3. Section 6 on the fetched bytes equals the precondition.
    ref, pre6 = result["section6_reference"], pre["section6"]
    same = {
        k: ref[k] == pre6[k]
        for k in (
            "gains_sha256",
            "gain_flags_sha256",
            "chi2_train_mean_per_cell",
            "survey",
            "policy_mask_sha256",
            "policy_mask_counts",
        )
    }
    criteria["3_reference_reproduction"] = {
        "pass": all(same.values()) and pre["all_passed"],
        "equal": same,
        "precondition_passed": pre["all_passed"],
        "chi2": ref["chi2_train_mean_per_cell"],
    }

    # 4. Every arm solves.
    solved = {}
    for label, arm in arms.items():
        m = arm["metrics"]
        solved[label] = (
            m["solver"]["converged_fraction"] >= 0.9
            and m["losses"]["validation"] is not None
            and m["losses"]["test"] is not None
            and all(v == 0 for v in m["invalid_predictions"].values())
        )
    criteria["4_arms_solve"] = {
        "pass": all(solved.values()),
        "arms": solved,
        "converged": {
            k: v["metrics"]["solver"]["converged_fraction"] for k, v in arms.items()
        },
        "unavailable": [k for k, v in result["arms"].items() if v is None],
    }

    # 5. Tricolour arms well formed.
    criteria["5_tricolour_well_formed"] = {
        "pass": all(t["checks"]["pass"] for t in result["tricolour"].values()),
        "checks": {k: t["checks"] for k, t in result["tricolour"].items()},
    }

    # 6. Hypothesis (always decided by the rule; pass means decidable).
    criteria["6_hypotheses"] = {
        "pass": all(
            h["mse_test"]["call"] != "undecidable" for h in result["hypotheses"]
        ),
        "calls": result["hypotheses"],
        "headline": {
            "pair": "tv-policy vs tricolour-firstpass",
            "mse_test": result["hypotheses"][0]["mse_test"],
            "residual_rms": result["hypotheses"][0]["residual_rms"],
            "cost_comparable": result["cost_clause"]["comparable"],
            "cost_ratio": result["cost_clause"]["ratio"],
            "tv_policy_selected": arms["tv-policy"]["policy"],
        },
    }

    # 7. Outputs.
    files = {
        p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*") if p.is_file()
    }
    required = {"result.json", "receipt.json", "side-effects.json", "candidates.json"}
    required |= {f"flags/{k}.npz" for k in arms} | {f"gains/{k}.npz" for k in arms}
    required |= {f"images/{k}-dirty.fits" for k in arms} | {
        f"images/{k}-psf.fits" for k in arms
    }
    missing = sorted(required - files)
    criteria["7_outputs"] = {
        "pass": not missing and (run_dir / "environment.json").exists(),
        "missing": missing,
        "environment_json": (run_dir / "environment.json").exists(),
    }
    summary = {
        "protocol": "research/core-k-luno-campaign.md",
        "run": str(run_dir),
        "precondition": str(precondition_dir),
        "all_pass": all(c["pass"] for c in criteria.values()),
        "criteria": criteria,
        "check_seconds": time.perf_counter() - started,
    }
    write_json(check_dir / "result.json", summary)
    return summary


__all__ = [
    "apply_gains",
    "build_state",
    "call",
    "check",
    "decode_extra",
    "decode_object",
    "fetch_extra",
    "hypothesis",
    "image_arm",
    "image_metrics",
    "precondition",
    "run",
    "solve_arm",
    "tricolour_arm",
    "tricolour_checks",
    "tv_loop",
]
