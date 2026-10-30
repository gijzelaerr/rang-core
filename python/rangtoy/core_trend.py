"""Trend track hot spot, ported (research/p6-python-hotspots.md).

`generate_candidates` returns exactly what the frozen
`flagging_structured_proposals.generate_candidates` returns: the same
candidates in the same order, the same SHA256 mask ids, alias counts,
metadata, sample counts, bit-identical scores and the same stats. It differs
in how it gets there:

- the geometry (which tiles are admissible, their sorted TRAIN indices, mask
  ids and aliases) depends only on the TRAIN mask, times, antennas, frequency
  window, widths, budget and minimum count, never on the scores or guidance.
  It is built once per distinct geometry input (keyed by a SHA256 of those
  inputs) and reused: `flagging_trend.run` calls the function eight times per
  case with the same state and different guidance;
- tile counts come from one prefix sum per time scope and row group, and the
  indices of every tile of a width from one `np.nonzero` of the group's rows
  (row-major order, then a stable sort by tile, which keeps the row-major
  order the frozen per-tile `np.nonzero` produces);
- the elementwise score terms are computed once over the concatenated indices
  of all candidates, and each score is `np.mean` over the candidate's slice of
  that array (the same values in the same order, so the same pairwise sum).

`run` is the frozen `flagging_trend.run`, unedited, with this function in
place of the frozen one for the duration of the call.
"""

from contextlib import contextmanager
from hashlib import sha256

import numpy as np

from . import core_trend_run as flagging_trend
from .core_proposals import FREQUENCY_WIDTHS, TV_CAP, _inputs, _row_groups

_GEOMETRY = {}  # one entry: the most recent geometry key and its geometry
_SHORT_EXACT = None  # set on first use by `_short_sums_are_exact`
SHORT = 128  # NumPy's PW_BLOCKSIZE: longer vectors are split recursively


def _short_sums(values, starts, lengths):
    """NumPy's float64 `pairwise_sum` of segments of 1-128 values, all at once.

    `np.add.reduce` on a contiguous float64 vector of n <= 128 values
    (numpy/_core/src/umath/loops_utils.h.src): below 8 a plain loop from 0.0;
    otherwise eight accumulators seeded with the first eight values, then
    blocks of eight up to n - n % 8, combined as ((0+1)+(2+3))+((4+5)+(6+7)),
    then the remainder added in order. Segments of different lengths run
    together; a step a segment does not take is masked out, never added as
    zero, so every segment sees exactly its own sequence of additions.
    `_short_sums_are_exact` checks this against `np.mean` before it is used.
    """
    width = int(lengths.max())
    columns = np.arange(-(-width // 8) * 8)  # whole blocks of eight
    inside = columns[None] < lengths[:, None]
    block = np.where(
        inside, values[np.where(inside, starts[:, None] + columns, 0)], 0.0
    )
    rows = np.arange(len(lengths))
    small = lengths < 8
    total = np.zeros(len(lengths))
    for i in range(min(width, 7)):
        take = small & (lengths > i)
        total[take] += block[take, i]
    big = ~small
    if big.any():
        stop = lengths - lengths % 8
        r = np.where(big[:, None], block[:, :8] if width >= 8 else 0.0, 0.0)
        for i in range(8, width, 8):
            take = big & (i < stop)
            r[take] += block[take, i : i + 8]
        combined = ((r[:, 0] + r[:, 1]) + (r[:, 2] + r[:, 3])) + (
            (r[:, 4] + r[:, 5]) + (r[:, 6] + r[:, 7])
        )
        total[big] = combined[big]
        for t in range(7):
            column = stop + t
            take = big & (column < lengths)
            total[take] += block[rows[take], column[take]]
    return total


def _short_sums_are_exact():
    """Bitwise check of `_short_sums` against `np.mean` for every length 1-128."""
    global _SHORT_EXACT
    if _SHORT_EXACT is None:
        rng = np.random.default_rng(20261030)
        lengths = np.repeat(np.arange(1, SHORT + 1), 3)
        starts = np.concatenate(([0], np.cumsum(lengths)[:-1]))
        values = rng.lognormal(0, 3, size=lengths.sum())
        values *= rng.random(len(values)) < 0.7
        expected = np.asarray(
            [np.mean(values[a : a + n]) for a, n in zip(starts, lengths)]
        )
        got = (0.0 + _short_sums(values, starts, lengths)) / lengths
        _SHORT_EXACT = bool(np.array_equal(got, expected))
    return _SHORT_EXACT


def segment_means(values, offsets):
    """`[np.mean(values[a:b]) for a, b in pairwise(offsets)]`, bit for bit.

    Segments of at most 128 values (most candidates) are summed together by
    `_short_sums` when it reproduces NumPy's summation on this build (checked
    once per process); longer segments, or all of them if the check fails,
    call `np.mean`. Segments must be nonempty.
    """
    offsets = np.asarray(offsets, np.int64)
    starts, lengths = offsets[:-1], np.diff(offsets)
    means = np.empty(len(lengths))
    short = (
        lengths <= SHORT if _short_sums_are_exact() else np.zeros(len(lengths), bool)
    )
    if short.any():
        # np.mean: the add reduction starts from the identity 0.0, then / n.
        means[short] = (
            0.0 + _short_sums(values, starts[short], lengths[short])
        ) / lengths[short]
    for index in np.flatnonzero(~short):
        means[index] = np.mean(values[starts[index] : offsets[index + 1]])
    return means


def _geometry_key(train, times, p, q, window, widths, budget, min_samples):
    digest = sha256()
    for array in (train, times, p, q, window):
        array = np.ascontiguousarray(array)
        digest.update(f"{array.dtype.str}{array.shape}".encode())
        digest.update(array.tobytes())
    digest.update(
        repr((tuple(int(w) for w in widths), budget, int(min_samples))).encode()
    )
    return digest.hexdigest()


def _build_geometry(train, scopes, groups, tiles, budget, min_samples):
    """The frozen scope x group x tile walk, without scores."""
    channels = train.shape[1]
    counters = {
        "raw_geometry_count": 0,
        "rejected_under_minimum": 0,
        "rejected_over_budget": 0,
        "admissible_geometry_count": 0,
        "duplicate_geometry_count": 0,
    }
    starts = np.asarray([first for first, _ in tiles], np.int64)
    stops = np.asarray([first + width for first, width in tiles], np.int64)
    widths = sorted({width for _, width in tiles})
    records, masks = [], {}
    for scope, (time_rows, _) in enumerate(scopes):
        for group, (group_rows, _) in enumerate(groups):
            rows = np.flatnonzero(time_rows & group_rows)
            counters["raw_geometry_count"] += len(tiles)
            if not tiles:
                continue
            local = train[rows]
            prefix = np.zeros(channels + 1, np.int64)
            np.cumsum(local.sum(axis=0, dtype=np.int64), out=prefix[1:])
            counts = prefix[stops] - prefix[starts]
            under = counts < min_samples
            over = ~under & (counts > budget)
            counters["rejected_under_minimum"] += int(under.sum())
            counters["rejected_over_budget"] += int(over.sum())
            admissible = np.flatnonzero(~under & ~over)
            if not len(admissible):
                continue
            local_row, channel = np.nonzero(local)
            flat = (rows[local_row] * channels + channel).astype(np.int64)
            by_width = {}
            for width in widths:
                tile_of = channel // width
                order = np.argsort(tile_of, kind="stable")
                by_width[width] = (flat[order], tile_of[order])
            for tile in admissible:
                first, width = tiles[tile]
                ordered, keys = by_width[width]
                lo, hi = np.searchsorted(keys, [first // width, first // width + 1])
                indices = ordered[lo:hi].copy()
                count = int(counts[tile])
                if len(indices) != count:
                    raise RuntimeError("prefix-sum tile count disagrees with indices")
                counters["admissible_geometry_count"] += 1
                mask_id = sha256(
                    indices.astype("<i8", copy=False).tobytes()
                ).hexdigest()
                if mask_id in masks:
                    record = records[masks[mask_id]]
                    if not np.array_equal(record["indices"], indices):
                        raise RuntimeError("candidate mask hash collision")
                    record["geometry_alias_count"] += 1
                    counters["duplicate_geometry_count"] += 1
                    continue
                masks[mask_id] = len(records)
                records.append(
                    {
                        "mask_id": mask_id,
                        "indices": indices,
                        "scope": scope,
                        "group": group,
                        "first": int(first),
                        "width": int(width),
                        "sample_count": count,
                        "geometry_alias_count": 1,
                    }
                )
    if records:
        lengths = np.asarray([len(r["indices"]) for r in records], np.int64)
        offsets = np.concatenate(([0], np.cumsum(lengths)))
        concatenated = np.concatenate([r["indices"] for r in records])
    else:
        offsets, concatenated = np.zeros(1, np.int64), np.zeros(0, np.int64)
    return {
        "records": records,
        "counters": counters,
        "offsets": offsets,
        "indices": concatenated,
    }


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
    """`flagging_structured_proposals.generate_candidates`, same results, faster."""
    # Validation and preamble copied verbatim from the frozen function.
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
    # New from here: cached geometry, then vectorised elementwise score terms.
    groups = _row_groups(train, p, q)
    key = _geometry_key(train, times, p, q, window, freq_widths, budget, min_samples)
    geometry = _GEOMETRY.get(key)
    if geometry is None:
        geometry = _build_geometry(train, scopes, groups, tiles, budget, min_samples)
        _GEOMETRY.clear()
        _GEOMETRY[key] = geometry
    stats.update(geometry["counters"])
    records, offsets = geometry["records"], geometry["offsets"]
    flat = geometry["indices"]
    z_positive = np.maximum(scores.flat[flat], 0).astype(float)
    relative_tv = np.clip(tv.flat[flat] / median_tv, 0, TV_CAP)
    weighted = z_positive * (1 + tv_weight * relative_tv)
    residual_ranks = segment_means(z_positive, offsets)
    tv_ranks = segment_means(weighted, offsets)
    # The frozen loop raises at the first nonfinite score with this message.
    if not (np.isfinite(residual_ranks).all() and np.isfinite(tv_ranks).all()):
        raise ValueError("training ranking scores overflowed")
    bases = {}
    candidates = []
    for index, record in enumerate(records):
        residual_rank = float(residual_ranks[index])
        tv_rank = float(tv_ranks[index])
        first, width = record["first"], record["width"]
        base = (record["scope"], record["group"])
        if base not in bases:
            bases[base] = {**scopes[base[0]][1], **groups[base[1]][1]}
        candidates.append(
            {
                "mask_id": record["mask_id"],
                "indices": record["indices"].copy(),
                "metadata": {
                    **bases[base],
                    "frequency_start": first,
                    "frequency_stop": first + width,
                    "frequency_width": width,
                },
                "sample_count": record["sample_count"],
                "added_fraction": record["sample_count"] / train_count,
                "geometry_alias_count": record["geometry_alias_count"],
                "residual_score": residual_rank,
                "tv_score": tv_rank,
            }
        )
    stats["distinct_candidate_count"] = len(candidates)
    return (candidates, stats) if return_stats else candidates


@contextmanager
def ported_candidates(*modules):
    """Install `generate_candidates` in frozen namespaces (default `flagging_trend`).

    The frozen modules bind the name at import (`from ... import
    generate_candidates`) and look it up at call time, so replacing the module
    attribute for the duration of the call is enough; the files are untouched.
    """
    modules = modules or (flagging_trend,)
    frozen = [module.generate_candidates for module in modules]
    for module in modules:
        module.generate_candidates = generate_candidates
    try:
        yield
    finally:
        for module, function in zip(modules, frozen):
            module.generate_candidates = function


def run(run_dir, source_dir="outputs/tv-concurrent-20260924-01"):
    """The frozen `flagging_trend.run`, unedited, with ported candidates."""
    with ported_candidates():
        return flagging_trend.run(run_dir, source_dir)
