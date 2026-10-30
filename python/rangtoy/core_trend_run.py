"""TRAIN-supported scalar phase trends as extra full-Jones TV guidance.

Verbatim extract of the frozen `rangtoy.flagging_trend` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_trend.py at commit
2da566c (now history/python/flagging_trend.py),
sha256 3c578c5e355a4a81d2959db9463f7bbf23025e52e01a61e72ebe9e45c5988e6b.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import ctypes
import json
import os
import platform
import shutil
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

import numpy as np

from .core_balanced import balanced_rank
from .core_cases import CASES, PATTERNS, phase_factors
from .core_influence import _maps, _npz, _predict
from .core_paths import reject_nested_paths
from .core_policy import gain_tv, polar_gauge, residual_features
from .core_proposals import generate_candidates
from .core_response import RESERVE_BYTES, Budget, allocated_bytes
from .core_state import load_state, tree_digest
from .projector import _native_library


@lru_cache(maxsize=1)
def _kernel():
    real = np.ctypeslib.ndpointer(dtype=np.float64, flags=("C_CONTIGUOUS", "ALIGNED"))
    byte = np.ctypeslib.ndpointer(dtype=np.uint8, flags=("C_CONTIGUOUS", "ALIGNED"))
    integer = np.ctypeslib.ndpointer(dtype=np.uintp, flags=("C_CONTIGUOUS", "ALIGNED"))
    fn = _native_library().rang_trend_slopes
    fn.argtypes = [ctypes.c_size_t] * 3 + [real, byte, real, real, real, integer]
    fn.restype = ctypes.c_int
    return fn


def estimate_trend(gains, valid, times, frequencies, training_support):
    """Station × (time rad/s, frequency rad/Hz); missing fits remain NaN.

    Median half-determinant increments assume |scalar phase step| < pi/2.
    Wrapped data alone cannot certify this assumption. Only TRAIN-supported
    valid bins are decoded by the native estimator.
    """
    gains = np.asarray(gains, np.complex128)
    valid, support = np.asarray(valid), np.asarray(training_support)
    if (
        gains.ndim != 5
        or gains.shape[-2:] != (2, 2)
        or min(gains.shape[:3]) == 0
        or valid.dtype != np.bool_
        or support.dtype != np.bool_
        or valid.shape != gains.shape[:3]
        or support.shape != valid.shape
    ):
        raise ValueError("full Jones/bool validity/TRAIN bin support shapes required")
    coordinates = [np.asarray(x, float) for x in (times, frequencies)]
    if any(
        x.shape != (gains.shape[axis],)
        or not np.isfinite(x).all()
        or not np.isfinite(np.diff(x)).all()
        or np.any(np.diff(x) <= 0)
        for axis, x in enumerate(coordinates)
    ):
        raise ValueError("finite strictly increasing native coordinates required")
    used = valid & support
    if not np.isfinite(gains[used]).all():
        raise ValueError("nonfinite TRAIN-supported gain")
    # Poisoned unsupported bins never enter the native kernel's arithmetic.
    packed = np.require(
        np.where(used[..., None, None], gains, 0), requirements=["C", "A"]
    ).view(float)
    slopes = np.full((gains.shape[2], 2), np.nan)
    counts = np.zeros(slopes.shape, dtype=np.uintp)
    status = _kernel()(
        *gains.shape[:3],
        packed,
        np.require(used, dtype=np.uint8, requirements=["C", "A"]),
        *[np.require(x, requirements=["C", "A"]) for x in coordinates],
        slopes,
        counts,
    )
    if status:
        raise ValueError(f"native phase-trend estimator failed: {status}")
    return slopes, counts


def training_gain_support(state, shape):
    """Native grid membership from TRAIN geometry only, never heldout values."""
    train = np.asarray(state["train"])
    times, frequencies = np.asarray(state["times"]), np.asarray(state["frequencies"])
    p, q = np.asarray(state["antenna1"]), np.asarray(state["antenna2"])
    if (
        len(shape) != 3
        or any(type(n) is not int or n < 1 for n in shape)
        or train.dtype != np.bool_
        or train.shape != (len(times), len(frequencies))
        or times.ndim != 1
        or frequencies.ndim != 1
        or not np.isfinite(times).all()
        or not np.isfinite(frequencies).all()
        or np.any(np.diff(frequencies) <= 0)
        or any(
            x.shape != times.shape
            or x.dtype.kind not in "iu"
            or np.any(x < 0)
            or np.any(x >= shape[2])
            for x in (p, q)
        )
        or np.any(train & (p == q)[:, None])
    ):
        raise ValueError("bool TRAIN and bounded native gain geometry required")
    for key in ("validation", "test"):
        if key in state and (
            state[key].dtype != np.bool_
            or state[key].shape != train.shape
            or np.any(train & state[key])
        ):
            raise ValueError("TRAIN overlaps invalid heldout geometry")
    if "original_flags" in state and (
        state["original_flags"].dtype != np.bool_
        or state["original_flags"].shape != (*train.shape, 4)
        or np.any(train & state["original_flags"].any(axis=-1))
    ):
        raise ValueError("TRAIN overlaps original FLAG geometry")
    if "original_rows" in state and (
        state["original_rows"].dtype != np.bool_
        or state["original_rows"].shape != times.shape
        or np.any(train & state["original_rows"][:, None])
    ):
        raise ValueError("TRAIN overlaps original FLAG_ROW geometry")
    support = np.zeros(shape, bool)
    row, channel = np.where(train)
    tm, fm = _maps(state)
    if (len(tm) and tm.max() >= shape[0]) or (len(fm) and fm.max() >= shape[1]):
        raise ValueError("gain grid does not contain TRAIN coordinates")
    support[tm[row], fm[channel], state["antenna1"][row]] = True
    support[tm[row], fm[channel], state["antenna2"][row]] = True
    return support


def detrended_tv(gains, valid, times, frequencies, slopes, *, scale=1.0):
    """Dephase four entries together, then apply the existing Rust TV kernel.

    Unsupported trend stations invalidate guidance, not the primary gain solve.
    Scalar station-constant phases leave these edge norms unchanged.
    """
    gains, valid, slopes = (
        np.asarray(gains, complex),
        np.asarray(valid),
        np.asarray(slopes, float),
    )
    if slopes.shape != (gains.shape[2], 2) or valid.dtype != np.bool_:
        raise ValueError("station/time-frequency slope and bool validity required")
    available = np.isfinite(slopes).all(axis=1)
    safe = np.where(np.isfinite(slopes), slopes, 0)
    phase = (np.asarray(times) - times[0])[:, None, None] * safe[None, None, :, 0] + (
        np.asarray(frequencies) - frequencies[0]
    )[None, :, None] * safe[None, None, :, 1]
    corrected = gains * np.exp(-1j * phase)[..., None, None]
    return gain_tv(
        corrected,
        valid & available[None, None],
        times,
        frequencies,
        scale=scale,
    )


def guidance_from_tv(state, tv):
    tm, fm = _maps(state)
    maps = tv["map"]
    return np.maximum(
        maps[tm[:, None], fm[None], state["antenna1"][:, None]],
        maps[tm[:, None], fm[None], state["antenna2"][:, None]],
    )


class TrendBudget(Budget):
    def check(self, needed=0):
        used = allocated_bytes(self.root)
        if needed < 0 or used + needed > 256 * 1024**2:
            raise ValueError("trend256MiB checked allocation budget exceeded")
        ancestor = self.root
        while not ancestor.exists():
            ancestor = ancestor.parent
        if shutil.disk_usage(ancestor).free < RESERVE_BYTES + needed:
            raise ValueError("trend operation would violate8GiB disk reserve")
        return used


def run(run_dir, source_dir="outputs/tv-concurrent-20260924-01"):
    """Read-only seven baseline × four phase-pattern guidance ablation."""
    from .core_receipts import source_receipts

    output, source = reject_nested_paths(run_dir, source_dir)
    digest = tree_digest(source)
    budget = TrendBudget(output)
    budget.check(256 * 1024**2)
    budget.mkdir(output)
    native = Path(_native_library()._name)
    runtime = source_receipts()
    config = {
        "source": str(source),
        "source_digest": digest,
        "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "native_library_sha256": sha256(native.read_bytes()).hexdigest(),
        "runtime_receipts": runtime,
        "image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
        "environment": {"python": platform.python_version(), "numpy": np.__version__},
        "patterns": PATTERNS,
        "cases": CASES,
        "fit": "median adjacent TRAIN-supported half-determinant gradients",
        "unaliased_scalar_step_assumption_radians": "absolute value < pi/2",
        "minimum_time_frequency_edges": [2, 4],
        "allocation_limit_bytes": 256 * 1024**2,
        "original_flags_or_DATA_written": False,
        "primary_full_Jones_TV_objective_replaced": False,
        "new_QC_solves": 0,
    }
    budget.json(output / "config.json", config)
    records = []
    for case in CASES:
        directory = source / "experiments" / case
        state = load_state(directory)
        baseline = _npz(directory / "trials/baseline/diagnostics.npz")
        metrics = json.loads((directory / "trials/baseline/metrics.json").read_text())
        support = training_gain_support(state, baseline["gain_valid"].shape)
        _, _, prediction = _predict(state, baseline["gains"], state["train"])
        residual = np.zeros_like(state["data"], dtype=complex)
        residual[state["train"]] = state["data"][state["train"]] - prediction
        z = residual_features(
            residual * np.sqrt(state["weights"]),
            state["train"],
            state["antenna1"],
            state["antenna2"],
        )
        for pattern in PATTERNS:
            factors = phase_factors(
                baseline["gain_times"], baseline["gain_frequencies"], pattern
            )
            aligned, valid = polar_gauge(
                baseline["gains"] * factors[..., None, None], baseline["gain_valid"]
            )
            slopes, counts = estimate_trend(
                aligned,
                valid,
                baseline["gain_times"],
                baseline["gain_frequencies"],
                support,
            )
            raw = gain_tv(
                aligned,
                valid,
                baseline["gain_times"],
                baseline["gain_frequencies"],
                scale=metrics["scale"],
            )
            corrected = detrended_tv(
                aligned,
                valid,
                baseline["gain_times"],
                baseline["gain_frequencies"],
                slopes,
                scale=metrics["scale"],
            )
            available = bool(np.isfinite(slopes).all())
            rankings = {}
            for mode, tv in (("rawTV", raw), ("detrendedTV", corrected)):
                if mode == "detrendedTV" and not available:
                    rankings[mode] = None
                    continue
                family = generate_candidates(state, z, guidance_from_tv(state, tv))
                if mode == "rawTV":
                    rankings["residual"] = [
                        c["mask_id"] for c in balanced_rank(family, "residual")
                    ]
                rankings[mode] = [c["mask_id"] for c in balanced_rank(family, "tv")]
            records.append(
                {
                    "case_id": case,
                    "pattern": pattern,
                    "slopes_time_rad_per_second_frequency_rad_per_hz": np.where(
                        np.isfinite(slopes), slopes, None
                    ).tolist(),
                    "edge_counts": counts.tolist(),
                    "available": available,
                    "primary_polar_TV": raw["total"],
                    "detrended_guidance_TV": corrected["total"] if available else None,
                    "rankings": rankings,
                    "finite_primary_edges": int(np.isfinite(raw["edges"]).sum()),
                    "finite_detrended_edges": int(
                        np.isfinite(corrected["edges"]).sum()
                    ),
                }
            )
        budget.json(output / f"checkpoint-{case}.json", records[-4:])
    result = {
        "status": "measured saved-gain guidance ablation, not solver/policy invariance",
        "configuration": config,
        "records": records,
        "audit": {
            "runtime_unchanged": source_receipts() == runtime,
            "source_unchanged": tree_digest(source) == digest,
            "module_unchanged": sha256(Path(__file__).read_bytes()).hexdigest()
            == config["module_sha256"],
            "native_library_unchanged": sha256(native.read_bytes()).hexdigest()
            == config["native_library_sha256"],
        },
        "new_QC_solves": 0,
        "added_flags": 0,
    }
    if not all(result["audit"].values()):
        raise RuntimeError("trend source/runtime preservation failure")
    budget.json(output / "result.json", result)
    return result
