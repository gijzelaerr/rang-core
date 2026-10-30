"""Frozen rectangle geometry, train-only ranks and equal admissible families."""

import numpy as np
import pytest
from rangtoy.flagging_structured_proposals import generate_candidates, rank_candidates


def state():
    pairs = [(p, q) for p in range(5) for q in range(p + 1, 5)] + [(0, 0)]
    p, q = np.tile(np.asarray(pairs).T, 4)
    times = np.repeat(np.arange(4), len(pairs)).astype(float)
    shape = (len(times), 1024)
    flags = np.zeros((*shape, 4), bool)
    flags[0, 1, 2] = True
    rows = np.zeros(shape[0], bool)
    rows[1] = True
    window = np.ones(shape[1], bool)
    eligible = ~flags.any(axis=-1) & ~rows[:, None] & (p != q)[:, None]
    channels = np.arange(shape[1])[None]
    validation = eligible & (channels % 5 == 0)
    test = eligible & ~validation & (channels % 7 == 0)
    train = eligible & ~(validation | test)
    return {
        "train": train,
        "validation": validation,
        "test": test,
        "original_flags": flags,
        "original_rows": rows,
        "window": window,
        "times": times,
        "antenna1": p,
        "antenna2": q,
    }


def expected_indices(source, metadata):
    p, q = source["antenna1"], source["antenna2"]
    rows = p != q
    if metadata["time_mode"] == "single":
        rows &= source["times"] == metadata["time"]
    antennas = metadata["antennas"]
    if metadata["group"] == "antenna-star":
        rows &= (p == antennas[0]) | (q == antennas[0])
    elif metadata["group"] == "baseline":
        rows &= (np.minimum(p, q) == antennas[0]) & (np.maximum(p, q) == antennas[1])
    channels = np.zeros(source["train"].shape[1], bool)
    channels[metadata["frequency_start"] : metadata["frequency_stop"]] = True
    return np.flatnonzero(source["train"] & rows[:, None] & channels[None])


def test_heldout_map_values_do_not_affect_family_scores_or_rankings():
    source = state()
    rng = np.random.default_rng(19)
    scores, tv = rng.random(source["train"].shape), rng.random(source["train"].shape)
    candidates, stats = generate_candidates(source, scores, tv, return_stats=True)
    scores[~source["train"]], tv[~source["train"]] = np.nan, -np.inf
    other, other_stats = generate_candidates(source, scores, tv, return_stats=True)
    assert stats == other_stats
    for first, second in zip(candidates, other):
        np.testing.assert_array_equal(first["indices"], second["indices"])
        assert {k: v for k, v in first.items() if k != "indices"} == {
            k: v for k, v in second.items() if k != "indices"
        }
    for mode in ("residual", "tv"):
        assert [
            x["mask_id"] for x in rank_candidates(candidates, mode=mode, limit=8)
        ] == [x["mask_id"] for x in rank_candidates(other, mode=mode, limit=8)]


def test_every_candidate_is_a_whole_aligned_train_rectangle_with_untouched_holes():
    source = state()
    maps = np.ones(source["train"].shape)
    candidates, stats = generate_candidates(source, maps, maps, return_stats=True)
    assert {c["metadata"]["group"] for c in candidates} == {
        "global",
        "antenna-star",
        "baseline",
    }
    assert {c["metadata"]["time_mode"] for c in candidates} == {"single", "all"}
    assert {c["metadata"]["frequency_width"] for c in candidates} == {16, 32, 64, 128}
    protected = source["original_flags"].any(axis=-1) | source["original_rows"][:, None]
    for candidate in candidates:
        metadata = candidate["metadata"]
        assert metadata["frequency_start"] % metadata["frequency_width"] == 0
        assert (
            metadata["frequency_stop"] - metadata["frequency_start"]
            == metadata["frequency_width"]
        )
        np.testing.assert_array_equal(
            candidate["indices"], expected_indices(source, metadata)
        )
        assert source["train"].flat[candidate["indices"]].all()
        assert not protected.flat[candidate["indices"]].any()
        assert candidate["sample_count"] == len(candidate["indices"]) >= 8
        assert candidate["sample_count"] <= stats["sample_budget"]
        assert candidate["added_fraction"] <= 0.02


def test_oversized_rectangles_rejected_instead_of_trimming_to_budget():
    source = state()
    maps = np.ones(source["train"].shape)
    candidates, stats = generate_candidates(source, maps, maps, return_stats=True)
    assert stats["rejected_over_budget"] > 0
    assert not any(
        c["metadata"]["group"] == "global"
        and c["metadata"]["time_mode"] == "all"
        and c["metadata"]["frequency_width"] == 128
        for c in candidates
    )
    metadata = {
        "group": "global",
        "antennas": [],
        "time_mode": "all",
        "frequency_start": 0,
        "frequency_stop": 128,
    }
    assert len(expected_indices(source, metadata)) > stats["sample_budget"]
    assert (
        stats["raw_geometry_count"]
        == stats["rejected_under_minimum"]
        + stats["rejected_over_budget"]
        + stats["admissible_geometry_count"]
    )


def test_corrupt_training_original_bounds_or_holdout_overlap_are_rejected():
    source = state()
    maps = np.ones(source["train"].shape)
    source["train"][0, 1] = True
    with pytest.raises(ValueError, match="protected"):
        generate_candidates(source, maps, maps)
    source = state()
    source["train"][1, 1] = True
    with pytest.raises(ValueError, match="protected"):
        generate_candidates(source, maps, maps)
    source = state()
    source["train"][0, 5] = True
    with pytest.raises(ValueError, match="overlap"):
        generate_candidates(source, maps, maps)


def test_duplicate_geometry_aliases_and_tie_handling_are_deterministic():
    train = np.ones((1, 1024), bool)
    train[:, ::5] = False
    source = {"train": train, "times": [0.0], "antenna1": [0], "antenna2": [1]}
    maps = np.ones(train.shape)
    candidates, stats = generate_candidates(source, maps, maps, return_stats=True)
    assert candidates and len({c["mask_id"] for c in candidates}) == len(candidates)
    assert all(c["geometry_alias_count"] == 8 for c in candidates)
    assert stats["admissible_geometry_count"] == sum(
        c["geometry_alias_count"] for c in candidates
    )
    assert stats["duplicate_geometry_count"] == stats[
        "admissible_geometry_count"
    ] - len(candidates)
    ranked = rank_candidates(candidates)
    assert [c["mask_id"] for c in ranked] == sorted(c["mask_id"] for c in candidates)
    assert [c["mask_id"] for c in rank_candidates(list(reversed(candidates)))] == [
        c["mask_id"] for c in ranked
    ]


def test_both_rankings_use_identical_families_and_frozen_train_only_scores():
    source = state()
    channels = np.arange(source["train"].shape[1])[None]
    scores = np.broadcast_to(channels / 100, source["train"].shape)
    tv = np.broadcast_to((1024 - channels) / 100, source["train"].shape)
    candidates, stats = generate_candidates(source, scores, tv, return_stats=True)
    residual, guided = (
        rank_candidates(candidates),
        rank_candidates(candidates, mode="tv"),
    )
    assert {c["mask_id"] for c in residual} == {c["mask_id"] for c in guided}
    assert (
        len(rank_candidates(candidates, limit=8))
        == len(rank_candidates(candidates, mode="tv", limit=8))
        == 8
    )
    for candidate in candidates[::37]:
        indices = candidate["indices"]
        positive = np.maximum(scores.flat[indices], 0)
        relative_tv = np.clip(
            tv.flat[indices] / stats["tv_train_positive_median"], 0, 5
        )
        assert candidate["residual_score"] == np.mean(positive)
        assert candidate["tv_score"] == np.mean(positive * (1 + relative_tv))


def test_tiles_must_be_complete_and_wholly_within_the_active_window():
    source = state()
    source["window"][:19] = False
    source["train"][:, :19] = False
    maps = np.ones(source["train"].shape)
    candidates, stats = generate_candidates(source, maps, maps, return_stats=True)
    assert stats["excluded_frequency_tiles"] > 0
    assert all(
        source["window"][
            c["metadata"]["frequency_start"] : c["metadata"]["frequency_stop"]
        ].all()
        for c in candidates
    )


def test_training_shapes_and_frozen_settings_are_validated():
    source = state()
    maps = np.ones(source["train"].shape)
    with pytest.raises(ValueError, match="real TRAIN-shaped"):
        generate_candidates(source, maps[:, :-1], maps)
    with pytest.raises(ValueError, match="<=2% budget"):
        generate_candidates(source, maps, maps, max_fraction=0.03)
    with pytest.raises(ValueError, match="frozen widths"):
        generate_candidates(source, maps, maps, freq_widths=(8,))
    maps[source["train"]] = np.nan
    with pytest.raises(ValueError, match="nonfinite TRAIN"):
        generate_candidates(source, maps, np.ones_like(maps))
