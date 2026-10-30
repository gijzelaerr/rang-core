"""Task P6: ported trend candidates equal the frozen ones exactly.

research/p6-python-hotspots.md criterion 4. The archived-mirror test skips
when the ignored `outputs/` mirror is absent.
"""

import itertools
from pathlib import Path

import numpy as np
import pytest
from rangtoy import core_trend, flagging_trend
from rangtoy.flagging_structured_proposals import generate_candidates as frozen

ROOT = Path(__file__).resolve().parents[1]
MIRROR = ROOT / "outputs/core-trend-mirror-20261029-01/experiments"


def _equal(left, right):
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        return (
            isinstance(left, np.ndarray)
            and isinstance(right, np.ndarray)
            and left.dtype == right.dtype
            and np.array_equal(left, right, equal_nan=True)
        )
    if isinstance(left, dict):
        return (
            isinstance(right, dict)
            and list(left) == list(right)
            and all(_equal(left[k], right[k]) for k in left)
        )
    if isinstance(left, (list, tuple)):
        return (
            type(left) is type(right)
            and len(left) == len(right)
            and all(_equal(a, b) for a, b in zip(left, right))
        )
    return type(left) is type(right) and (
        left == right
        or (isinstance(left, float) and np.isnan(left) and np.isnan(right))
    )


def _both(*args, **kwargs):
    expected = frozen(*args, return_stats=True, **kwargs)
    actual = core_trend.generate_candidates(*args, return_stats=True, **kwargs)
    assert _equal(actual, expected)
    return expected


def _state(rng, antennas, times, channels, density, window=None):
    pairs = [(a, b) for a in range(antennas) for b in range(a, antennas)]
    p = np.asarray([a for _ in range(times) for a, _ in pairs], np.int64)
    q = np.asarray([b for _ in range(times) for _, b in pairs], np.int64)
    swap = rng.random(len(p)) < 0.3
    p, q = np.where(swap, q, p), np.where(swap, p, q)
    t = np.repeat(np.arange(times) * 8.0, len(pairs))
    train = (rng.random((len(p), channels)) < density) & (p != q)[:, None]
    state = {"train": train, "times": t, "antenna1": p, "antenna2": q}
    if window is not None:
        state["window"] = window
        state["train"] &= window[None]
    return state


@pytest.mark.parametrize("seed", range(6))
def test_random_states(seed):
    rng = np.random.default_rng(seed)
    state = _state(
        rng,
        antennas=int(rng.integers(2, 6)),
        times=int(rng.integers(1, 5)),
        channels=int(rng.choice([128, 160, 256])),
        density=float(rng.choice([0.02, 0.1, 0.4, 0.9])),
    )
    z = rng.normal(size=state["train"].shape)
    guidance = rng.exponential(size=state["train"].shape)
    _both(state, z, guidance)
    _both(state, z, guidance, freq_widths=(64, 16), max_fraction=0.01)
    _both(state, z, guidance, min_samples=40, tv_weight=0.0)


def test_admissible_aliases_and_ties():
    # Two antennas: global, star and baseline groups coincide, so every
    # admissible tile reappears as an alias; constant scores tie everywhere.
    rng = np.random.default_rng(11)
    state = _state(rng, antennas=2, times=40, channels=128, density=0.5)
    ones = np.ones(state["train"].shape)
    candidates, stats = _both(state, ones, ones)
    assert stats["admissible_geometry_count"] > 0
    assert stats["duplicate_geometry_count"] > 0
    assert len({c["residual_score"] for c in candidates}) == 1


def test_window_empty_train_and_all_over_budget():
    rng = np.random.default_rng(3)
    window = np.ones(256, bool)
    window[40:50] = False
    state = _state(rng, antennas=4, times=3, channels=256, density=0.3, window=window)
    z, g = rng.normal(size=state["train"].shape), np.zeros(state["train"].shape)
    _, stats = _both(state, z, g)
    assert stats["excluded_frequency_tiles"] > 0
    empty = dict(state, train=np.zeros_like(state["train"]))
    _, stats = _both(empty, z, g)
    assert stats["train_count"] == 0 and stats["admissible_geometry_count"] == 0
    dense = dict(
        state,
        train=state["train"]
        | (state["antenna1"] != state["antenna2"])[:, None] & window,
    )
    _, stats = _both(dense, z, g, max_fraction=0.0)
    assert stats["admissible_geometry_count"] == 0 and stats["rejected_over_budget"] > 0


def test_frozen_validation_errors_kept():
    rng = np.random.default_rng(5)
    state = _state(rng, antennas=3, times=2, channels=128, density=0.2)
    z = np.zeros(state["train"].shape)
    for kwargs in ({"freq_widths": (8,)}, {"min_samples": 4}, {"max_fraction": 0.5}):
        with pytest.raises(ValueError, match="frozen widths"):
            core_trend.generate_candidates(state, z, z, **kwargs)
    with pytest.raises(ValueError, match="nonnegative on TRAIN"):
        core_trend.generate_candidates(state, z, z - 1)


def test_switch_restores_frozen_function():
    original = flagging_trend.generate_candidates
    with core_trend.ported_candidates():
        assert flagging_trend.generate_candidates is core_trend.generate_candidates
    assert flagging_trend.generate_candidates is original is frozen


@pytest.mark.skipif(not MIRROR.is_dir(), reason="archived trend mirror absent")
def test_archived_mirror_case():
    from rangtoy.flagging import residual_features
    from rangtoy.flagging_influence import _npz, _predict
    from rangtoy.flagging_workflow import load_state

    directory = min(MIRROR.iterdir())
    state = load_state(directory)
    baseline = _npz(directory / "trials/baseline/diagnostics.npz")
    _, _, prediction = _predict(state, baseline["gains"], state["train"])
    residual = np.zeros_like(state["data"], dtype=complex)
    residual[state["train"]] = state["data"][state["train"]] - prediction
    z = residual_features(
        residual * np.sqrt(state["weights"]),
        state["train"],
        state["antenna1"],
        state["antenna2"],
    )
    guidance = np.abs(np.random.default_rng(0).normal(size=state["train"].shape))
    candidates, stats = _both(state, z, guidance)
    assert stats["admissible_geometry_count"] > 0 and candidates


def test_geometry_cache_reused_and_invalidated():
    rng = np.random.default_rng(21)
    state = _state(rng, antennas=4, times=3, channels=256, density=0.3)
    z = rng.normal(size=state["train"].shape)
    for _ in range(3):
        _both(state, z, rng.exponential(size=state["train"].shape))
    (key,) = core_trend._GEOMETRY
    changed = dict(state, train=state["train"].copy())
    changed["train"][np.argwhere(changed["train"])[0][0]] = False
    _both(changed, z, np.ones(state["train"].shape))
    assert list(core_trend._GEOMETRY) != [key]
    # Returned arrays are copies: mutating them does not touch the cache.
    first = core_trend.generate_candidates(changed, z, np.ones(state["train"].shape))
    first[0]["indices"][:] = -1
    _both(changed, z, np.ones(state["train"].shape))


def test_segment_means_bitwise():
    assert core_trend._short_sums_are_exact()  # fast path active on this build
    rng = np.random.default_rng(8)
    lengths = rng.integers(1, 1600, size=300)
    lengths[:40] = np.arange(1, 41)
    offsets = np.concatenate(([0], np.cumsum(lengths)))
    values = rng.lognormal(0, 4, size=offsets[-1]) * (rng.random(offsets[-1]) < 0.6)
    expected = [np.mean(values[a:b]) for a, b in itertools.pairwise(offsets)]
    assert (
        core_trend.segment_means(values, offsets).tobytes()
        == np.asarray(expected).tobytes()
    )
