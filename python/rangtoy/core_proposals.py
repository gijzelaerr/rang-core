"""Frozen whole-rectangle TRAIN-only proposals for the MeerKAT TV pilot.

Verbatim extract of the frozen `rangtoy.flagging_structured_proposals` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_structured_proposals.py at commit
2da566c (now history/python/flagging_structured_proposals.py),
sha256 aa1fff8f4c6601ef3d3b9e2526ae771341844d4759f850178561f18b5058d37c.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

from hashlib import sha256

import numpy as np

FREQUENCY_WIDTHS = (16, 32, 64, 128)


TV_CAP = 5.0


def _bool_shape(value, shape, label):
    value = np.asarray(value)
    if value.dtype != np.bool_ or value.shape != shape:
        raise ValueError(f"{label} requires bool shape {shape}")
    return value


def _inputs(state, residual_score, guidance):
    train = np.asarray(state["train"])
    if train.ndim != 2 or train.dtype != np.bool_:
        raise ValueError("TRAIN requires a two-dimensional bool mask")
    scores, tv = np.asarray(residual_score), np.asarray(guidance)
    for label, values in (("residual score", scores), ("TV guidance", tv)):
        if values.shape != train.shape or values.dtype.kind not in "fiu":
            raise ValueError(f"{label} requires a real TRAIN-shaped map")
        # Intentionally inspect only training values. NaN/Inf or arbitrarily
        # large held-out values must not affect candidate geometry or ranking.
        if not np.isfinite(values[train]).all():
            raise ValueError(f"{label} has nonfinite TRAIN values")
    if np.any(tv[train] < 0):
        raise ValueError("TV guidance must be nonnegative on TRAIN")
    times = np.asarray(state["times"])
    p, q = np.asarray(state["antenna1"]), np.asarray(state["antenna2"])
    for label, values in (("times", times), ("antenna1", p), ("antenna2", q)):
        if values.shape != (train.shape[0],):
            raise ValueError(f"{label} row shape differs from TRAIN")
    if not np.isfinite(times).all() or any(
        antenna.dtype.kind not in "iu" or np.any(antenna < 0) for antenna in (p, q)
    ):
        raise ValueError("finite times and nonnegative integer antenna IDs required")
    window = _bool_shape(
        state.get("window", np.ones(train.shape[1], bool)),
        (train.shape[1],),
        "frequency window",
    )
    protected = np.zeros_like(train)
    if "original_flags" in state:
        flags = _bool_shape(
            state["original_flags"], (*train.shape, 4), "original flags"
        )
        protected |= flags.any(axis=-1)
    if "original_rows" in state:
        rows = _bool_shape(state["original_rows"], (train.shape[0],), "original rows")
        protected |= rows[:, None]
    if np.any(train & (protected | (p == q)[:, None] | ~window[None])):
        raise ValueError(
            "TRAIN includes original protected cells/rows, autos or outside-window cells"
        )
    masks = {"train": train}
    for key in ("validation", "test"):
        if key in state:
            masks[key] = _bool_shape(state[key], train.shape, f"{key} split")
    keys = tuple(masks)
    for index, key in enumerate(keys):
        if any(np.any(masks[key] & masks[other]) for other in keys[index + 1 :]):
            raise ValueError("TRAIN/validation/test masks overlap")
    return train, scores, tv, times, p, q, window


def _row_groups(train, p, q):
    eligible_rows = train.any(axis=1) & (p != q)
    antennas = np.unique(np.r_[p[eligible_rows], q[eligible_rows]])
    groups = [(eligible_rows, {"group": "global", "antennas": antennas.tolist()})]
    for antenna in antennas:
        groups.append(
            (
                eligible_rows & ((p == antenna) | (q == antenna)),
                {"group": "antenna-star", "antennas": [int(antenna)]},
            )
        )
    pairs = np.unique(
        np.column_stack((np.minimum(p, q), np.maximum(p, q)))[eligible_rows], axis=0
    )
    for left, right in pairs:
        groups.append(
            (
                eligible_rows
                & (np.minimum(p, q) == left)
                & (np.maximum(p, q) == right),
                {"group": "baseline", "antennas": [int(left), int(right)]},
            )
        )
    return groups


def generate_candidates(
    state,
    residual_score,
    guidance,
    *,
    freq_widths=FREQUENCY_WIDTHS,
    max_fraction=0.02,
    min_samples=8,
    tv_weight=1.0,
    return_stats=False,
):
    """Return deterministic unique masks with geometry, indices and both scores.

    Widths tile native channel indices from zero. Only complete exact-width
    tiles wholly within the experiment window enter the geometry family. Time
    selectors contain one unique integration time or all unique times. Baseline
    groups are physical unordered pairs, including either stored orientation.

    Each candidate contains ``metadata``, sorted ``indices``, ``mask_id``,
    ``sample_count``, ``added_fraction``, ``geometry_alias_count``,
    ``residual_score`` and ``tv_score``. ``return_stats=True`` additionally
    returns fixed-family rejection/alias counts and normalization metadata.
    Neither ranking can change which masks are admissible.
    """
    if (
        not freq_widths
        or any(
            not isinstance(width, (int, np.integer))
            or isinstance(width, (bool, np.bool_))
            or width not in FREQUENCY_WIDTHS
            for width in freq_widths
        )
        or len(set(freq_widths)) != len(freq_widths)
        or not np.isfinite(max_fraction)
        or not 0 <= max_fraction <= 0.02
        or not isinstance(min_samples, (int, np.integer))
        or isinstance(min_samples, (bool, np.bool_))
        or min_samples < 8
        or not np.isfinite(tv_weight)
        or tv_weight < 0
    ):
        raise ValueError(
            "frozen widths, at least eight samples, <=2% budget and nonnegative TV weight required"
        )
    train, scores, tv, times, p, q, window = _inputs(state, residual_score, guidance)
    train_count = int(train.sum())
    budget = int(max_fraction * train_count)
    training_tv = tv[train]
    positive_tv = training_tv[training_tv > 0]
    median_tv = float(np.median(positive_tv)) if len(positive_tv) else 1.0
    median_tv = max(median_tv, 1e-30)
    stats = {
        "train_count": train_count,
        "sample_budget": budget,
        "raw_geometry_count": 0,
        "rejected_under_minimum": 0,
        "rejected_over_budget": 0,
        "excluded_frequency_tiles": 0,
        "admissible_geometry_count": 0,
        "duplicate_geometry_count": 0,
        "distinct_candidate_count": 0,
        "tv_train_positive_median": median_tv,
        "tv_cap": TV_CAP,
        "tv_weight": float(tv_weight),
    }
    tiles = []
    for width in sorted(freq_widths):
        for first in range(0, train.shape[1] - width + 1, width):
            if window[first : first + width].all():
                tiles.append((first, width))
            else:
                stats["excluded_frequency_tiles"] += 1
    unique_times = np.unique(times)
    scopes = [
        (
            times == time,
            {
                "time_mode": "single",
                "time": float(time),
                "time_index": index,
                "time_count": 1,
            },
        )
        for index, time in enumerate(unique_times)
    ]
    scopes.append(
        (
            np.ones(len(times), bool),
            {
                "time_mode": "all",
                "time": None,
                "time_index": None,
                "time_count": len(unique_times),
            },
        )
    )
    candidates, masks = [], {}
    for time_rows, time_metadata in scopes:
        for group_rows, group_metadata in _row_groups(train, p, q):
            rows = np.flatnonzero(time_rows & group_rows)
            stats["raw_geometry_count"] += len(tiles)
            for first, width in tiles:
                local = train[rows, first : first + width]
                count = int(local.sum())
                if count < min_samples:
                    stats["rejected_under_minimum"] += 1
                    continue
                if count > budget:
                    stats["rejected_over_budget"] += 1
                    continue
                stats["admissible_geometry_count"] += 1
                local_row, local_channel = np.nonzero(local)
                indices = (
                    rows[local_row] * train.shape[1] + first + local_channel
                ).astype(np.int64)
                mask_id = sha256(
                    indices.astype("<i8", copy=False).tobytes()
                ).hexdigest()
                if mask_id in masks:
                    candidate = candidates[masks[mask_id]]
                    if not np.array_equal(candidate["indices"], indices):
                        raise RuntimeError("candidate mask hash collision")
                    candidate["geometry_alias_count"] += 1
                    stats["duplicate_geometry_count"] += 1
                    continue
                z_positive = np.maximum(scores.flat[indices], 0).astype(float)
                relative_tv = np.clip(tv.flat[indices] / median_tv, 0, TV_CAP)
                residual_rank = float(np.mean(z_positive))
                tv_rank = float(np.mean(z_positive * (1 + tv_weight * relative_tv)))
                if not np.isfinite([residual_rank, tv_rank]).all():
                    raise ValueError("training ranking scores overflowed")
                masks[mask_id] = len(candidates)
                candidates.append(
                    {
                        "mask_id": mask_id,
                        "indices": indices,
                        "metadata": {
                            **time_metadata,
                            **group_metadata,
                            "frequency_start": int(first),
                            "frequency_stop": int(first + width),
                            "frequency_width": int(width),
                        },
                        "sample_count": count,
                        "added_fraction": count / train_count,
                        "geometry_alias_count": 1,
                        "residual_score": residual_rank,
                        "tv_score": tv_rank,
                    }
                )
    stats["distinct_candidate_count"] = len(candidates)
    return (candidates, stats) if return_stats else candidates


def rank_candidates(candidates, *, mode="residual", limit=None):
    """Rank the same unique family; ties use stable SHA256 mask IDs, not labels."""
    if mode not in ("residual", "tv"):
        raise ValueError("ranking mode must be residual or tv")
    if limit is not None and (
        not isinstance(limit, (int, np.integer))
        or isinstance(limit, (bool, np.bool_))
        or limit < 0
    ):
        raise ValueError("ranking limit must be a nonnegative integer")
    field = f"{mode}_score"
    if len({candidate["mask_id"] for candidate in candidates}) != len(candidates):
        raise ValueError("ranking family must contain unique candidate masks")
    if any(not np.isfinite(candidate[field]) for candidate in candidates):
        raise ValueError("ranking requires finite candidate scores")
    ranked = sorted(candidates, key=lambda item: (-item[field], item["mask_id"]))
    return ranked if limit is None else ranked[:limit]
