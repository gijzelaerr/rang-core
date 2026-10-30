"""Prospective TRAIN-only gain-response forecasts and bounded confirmation.

Verbatim extract of the frozen `rangtoy.flagging_prospective` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_prospective.py at commit
2da566c (now history/python/flagging_prospective.py),
sha256 5a36faf8c84d6baefd2d2e6fc9ad1b736d337032b7ed204b27e84e5b73d7e638.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import shutil
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from .core_balanced import balanced_rank
from .core_influence import (
    _predict,
    _training_bundle,
    anchored_response,
    training_normals,
)
from .core_policy import fixed_support_tv, gain_tv, polar_gauge, residual_features
from .core_proposals import generate_candidates
from .core_response import RESERVE_BYTES, Budget, allocated_bytes
from .core_structured import _compact
from .core_trend_run import (
    detrended_tv,
    estimate_trend,
    guidance_from_tv,
    training_gain_support,
)

SEEDS = (107, 109)


MARGIN = 1e-6


class CampaignBudget(Budget):
    def __init__(self, root, limit):
        super().__init__(root)
        self.limit = limit

    def check(self, needed=0):
        used = allocated_bytes(self.root)
        if needed < 0 or used + needed > self.limit:
            raise ValueError("campaign checked allocation budget exceeded")
        ancestor = self.root
        while not ancestor.exists():
            ancestor = ancestor.parent
        if shutil.disk_usage(ancestor).free < RESERVE_BYTES + needed:
            raise ValueError("campaign operation would violate 8GiB disk reserve")
        return used


def make_shortlist(state, baseline, metrics, residuals, guidance):
    """Two whole rectangles per group per ranking; at most 24 distinct masks."""
    z = residual_features(
        residuals * np.sqrt(state["weights"]),
        state["train"],
        state["antenna1"],
        state["antenna2"],
    )
    family, stats = generate_candidates(state, z, guidance, return_stats=True)
    rankings = {
        mode: balanced_rank(family, mode) for mode in ("residual", "tv", "random")
    }
    aligned, valid = polar_gauge(baseline["gains"], baseline["gain_valid"])
    slopes, counts = estimate_trend(
        aligned,
        valid,
        baseline["gain_times"],
        baseline["gain_frequencies"],
        training_gain_support(state, valid.shape),
    )
    if np.isfinite(slopes).all():
        tv = detrended_tv(
            aligned,
            valid,
            baseline["gain_times"],
            baseline["gain_frequencies"],
            slopes,
            scale=metrics["scale"],
        )
        detrended = generate_candidates(state, z, guidance_from_tv(state, tv))
        if {x["mask_id"] for x in detrended} != {x["mask_id"] for x in family}:
            raise RuntimeError("guidance changed the admissible geometry family")
        rankings["detrended"] = balanced_rank(detrended, "tv")
    else:
        rankings["detrended"] = []
    distinct = {}
    for items in rankings.values():
        for item in items:
            distinct.setdefault(item["mask_id"], item)
    stats = {
        "generator": stats,
        "family_mask_ids_sha256": sha256(
            "\n".join(sorted(x["mask_id"] for x in family)).encode()
        ).hexdigest(),
        "trend_slopes": np.where(np.isfinite(slopes), slopes, None).tolist(),
        "trend_edge_counts": counts.tolist(),
        "detrended_guidance_available": bool(np.isfinite(slopes).all()),
        "maximum_distinct": 24,
    }
    return list(distinct.values()), rankings, stats


def forecast_family(state, baseline, metrics, candidates, cache_path=None):
    """TRAIN-only curvature/response/TV; validation deliberately separate."""
    bundle = _training_bundle(state, baseline)
    start = time.perf_counter()
    full_h, full_b, _ = training_normals(
        **{k: v for k, v in bundle.items() if k != "flat_indices"}
    )
    normal_seconds = time.perf_counter() - start
    records, raw = [], []
    for candidate in candidates:
        indices = np.asarray(candidate["indices"])
        if (
            indices.dtype.kind not in "iu"
            or indices.ndim != 1
            or np.any(indices[1:] <= indices[:-1])
            or not 8 <= len(indices) <= int(0.02 * state["train"].sum())
        ):
            raise ValueError("sorted unique bounded whole-TRAIN mask required")
        if (
            sha256(indices.astype("<i8").tobytes()).hexdigest() != candidate["mask_id"]
            or len(indices) != candidate["sample_count"]
            or candidate["added_fraction"] != len(indices) / state["train"].sum()
        ):
            raise ValueError("candidate index/count/fraction/SHA mismatch")
        positions = np.searchsorted(bundle["flat_indices"], indices)
        if np.any(positions >= len(bundle["flat_indices"])) or not np.array_equal(
            bundle["flat_indices"][positions], indices
        ):
            raise ValueError("candidate contains non-TRAIN cells")
        drop = {
            k: v[positions]
            for k, v in bundle.items()
            if k not in ("gains", "flat_indices")
        }
        start = time.perf_counter()
        drop_h, drop_b, _ = training_normals(bundle["gains"], **drop)
        predicted = baseline["gains"].copy().reshape(-1, 4, 2, 2)
        audits = []
        for bin_id in np.unique(drop["bin_ids"]):
            active = np.array(
                [
                    np.trace(full_h[bin_id, 8 * i : 8 * (i + 1), 8 * i : 8 * (i + 1)])
                    > 0
                    for i in range(4)
                ]
            )
            response = anchored_response(
                full_h[bin_id],
                full_b[bin_id],
                drop_h[bin_id],
                drop_b[bin_id],
                bundle["gains"][bin_id],
                active,
            )
            audits.append(
                {
                    "bin_id": int(bin_id),
                    **{k: v for k, v in response.items() if k != "delta"},
                }
            )
            if response["guard_pass"]:
                predicted[bin_id] += response["delta"]
        guard = all(x["guard_pass"] for x in audits)
        predicted = predicted.reshape(baseline["gains"].shape)
        record = {
            "mask_id": candidate["mask_id"],
            "candidate": _compact(candidate),
            "bin_audits": audits,
            "guard_pass": guard,
            "reason": None if guard else "curvature/trust abstention",
            "native_response_seconds": time.perf_counter() - start,
        }
        if guard:
            aligned, valid = polar_gauge(predicted, baseline["gain_valid"])
            tv = gain_tv(
                aligned,
                valid,
                baseline["gain_times"],
                baseline["gain_frequencies"],
                scale=metrics["scale"],
            )
            fixed = fixed_support_tv(tv["edges"], baseline["edges"])
            record["predicted_fixed_tv"] = fixed
            if fixed is None:
                record.update(guard_pass=False, reason="fixed TV support lost")
        records.append(record)
        raw.append(
            predicted
            if record["guard_pass"]
            else np.full_like(predicted, complex(np.nan, np.nan))
        )
    payload = np.stack(raw) if raw else np.empty((0, *baseline["gains"].shape), complex)
    if cache_path is not None:
        budget = CampaignBudget(Path(cache_path).parent, 256 * 1024**2)
        budget.npz(cache_path, raw_predicted_gains=payload)
    return {
        "records": records,
        "raw_predicted_gains": payload,
        "bundle": bundle,
        "full_h": full_h,
        "full_b": full_b,
        "baseline": baseline,
        "metrics": metrics,
        "full_training_normals_seconds": normal_seconds,
    }


def score_forecasts(state, forecast):
    """Only call after complete TRAIN records are serialized by the caller."""
    metrics = forecast["metrics"]
    for i, record in enumerate(forecast["records"]):
        if not record["guard_pass"]:
            continue
        rows, channels, prediction = _predict(
            state, forecast["raw_predicted_gains"][i], state["validation"]
        )
        val = float(
            np.mean(
                np.mean(
                    np.abs(state["data"][rows, channels] - prediction) ** 2
                    * state["weights"][rows, channels],
                    axis=-1,
                )
            )
        )
        if not np.isfinite(val) or val > 1.01 * metrics["losses"]["validation"]:
            record.update(guard_pass=False, reason="validation guard")
            continue
        objective = (
            record["predicted_fixed_tv"] / max(metrics["tv"], 1e-30)
            + 2 * record["candidate"]["added_fraction"]
            + 0.25 * val / max(metrics["losses"]["validation"], 1e-30)
        )
        record.update(
            predicted_validation_MSE=val,
            predicted_objective=objective,
            predicted_benefit=1.25 - objective,
            predicted_cost_removed_benefit=1.25
            - objective
            + 2 * record["candidate"]["added_fraction"],
        )
    return forecast


def _freeze_view(forecast):
    return {
        "records": forecast["records"],
        "full_training_normals_seconds": forecast["full_training_normals_seconds"],
    }
