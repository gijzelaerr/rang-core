"""C1 campaign helpers on synthetic inputs (research/c1-closure-arm.md); offline."""

import numpy as np
import pytest
from rangtoy import core_campaign_array as array
from rangtoy import core_campaign_closure as c1


def tiny_state(nant=4, ntime=4, nchan=6, seed=0):
    rng = np.random.default_rng(seed)
    a1, a2, times = [], [], []
    for t in range(ntime):
        for i in range(nant):
            for j in range(i + 1, nant):
                a1.append(i)
                a2.append(j)
                times.append(100.0 + 8 * t)
    nrow = len(a1)
    train = rng.random((nrow, nchan)) < 0.8
    held = ~train
    validation = held & (rng.random((nrow, nchan)) < 0.5)
    test = held & ~validation
    return {
        "antenna1": np.array(a1, np.int32),
        "antenna2": np.array(a2, np.int32),
        "times": np.array(times),
        "train": train,
        "validation": validation,
        "test": test,
    }


def test_hooks_capture_and_restore(monkeypatch):
    calls = []

    def fake_build(arrays, extra, nant, *args, **kwargs):
        return {"built": nant}

    def fake_loop(state, base, scale, prefix):
        calls.append(prefix)
        return [], None, None

    monkeypatch.setattr(array, "build_state", fake_build)
    monkeypatch.setattr(array, "tv_loop", fake_loop)
    hooks = c1.Hooks()
    extra = {"corr_type": np.array([9, 10, 11, 12])}
    with hooks.installed():
        assert array.build_state({}, extra, 7) == {"built": 7}
        array.tv_loop("s", {"label": "original"}, 1.0, "tv")
        array.tv_loop("s", {"label": "firstpass"}, 1.0, "firstpass-tv")
    assert array.build_state is fake_build and array.tv_loop is fake_loop
    assert hooks.state == {"built": 7} and hooks.nant == 7 and hooks.extra is extra
    assert hooks.base == {"label": "original"}
    assert calls == ["tv", "firstpass-tv"]
    assert hooks.tv_loop is fake_loop


def test_hooks_refuse_other_correlations(monkeypatch):
    monkeypatch.setattr(array, "build_state", lambda arrays, extra, nant: {})
    hooks = c1.Hooks()
    with hooks.installed(), pytest.raises(RuntimeError, match="CORR_TYPE"):
        array.build_state({}, {"corr_type": np.array([5, 6, 7, 8])}, 4)
    assert array.build_state is not None


def test_emptied_bins_and_dropped_cells():
    state = tiny_state()
    nant, nchan = 4, state["train"].shape[1]
    time_map = np.unique(state["times"], return_inverse=True)[1] // 2
    freq_map = np.arange(nchan) // 3
    # The "Tricolour" additions remove every training sample of station 3 in
    # time bin 0 and frequency bin 1.
    added = np.zeros(state["train"].shape, bool)
    on3 = (state["antenna1"] == 3) | (state["antenna2"] == 3)
    added[np.ix_(on3 & (time_map == 0), freq_map == 1)] = True
    added &= state["train"]
    emptied, per_arm = c1.emptied_bins(
        state, {"fp": added, "none": np.zeros_like(added)}, time_map, freq_map, nant, 2
    )
    assert per_arm == {"fp": 1, "none": 0}
    assert emptied[0, 1, 3] and emptied.sum() == 1
    drop = c1.bin_cells(state, emptied, time_map, freq_map)
    expect = np.zeros_like(drop)
    expect[np.ix_(on3 & (time_map == 0), freq_map == 1)] = True
    np.testing.assert_array_equal(drop, expect)
    support = c1.station_support(state, state["train"], time_map, freq_map, nant, 2)
    assert support.sum() == 2 * state["train"].sum()


def test_unguided_equal():
    def trial(w, z, sha, objective):
        return {
            "policy": {"threshold": z, "tv_weight": w},
            "mask_sha256": sha,
            "objective": objective,
            "mask_count": 3,
            "accepted": False,
        }

    a = [
        {"trial": "base", "policy": None},
        trial(0.0, 8.0, "x", 1.2),
        trial(1.0, 8.0, "y", 1.3),
    ]
    b = [
        {"trial": "base", "policy": None},
        trial(0.0, 8.0, "x", 1.2),
        trial(1.0, 8.0, "z", 1.4),
    ]
    assert c1.unguided_equal(a, b) == {"equal": True, "trials": 1}
    b[1]["objective"] = 1.21
    assert not c1.unguided_equal(a, b)["equal"]


def test_overlap_mask():
    other = np.zeros((4, 5), bool)
    other[0, :2] = True
    other[3, 4] = True
    o = c1.overlap_mask(np.array([0, 1, 7]), other, 20)
    assert o["both"] == 2 and o["other"] == 3
    assert o["fraction_of_mask"] == pytest.approx(2 / 3)
    assert o["lift"] == pytest.approx((2 / 3) / (3 / 20))
    assert o["coincides"]
    empty = c1.overlap_mask(np.array([], np.int64), other, 20)
    assert empty["fraction_of_mask"] is None and not empty["coincides"]


def test_closure_guidance_replaces_only_guidance():
    state = tiny_state()
    nchan = state["train"].shape[1]
    labels = np.tile(np.arange(6), 4)
    time_map = np.unique(state["times"], return_inverse=True)[1] // 2
    freq_map = np.arange(nchan) // 3
    cmap = np.arange(2 * 2 * 6, dtype=float).reshape(2, 2, 6) + 1
    cmap[0, 0, 0] = np.nan
    cells = np.flatnonzero(state["train"])[:5]
    base = {
        "features": {
            "cells": cells,
            "outliers": np.full(5, 3.0),
            "guidance": np.zeros(5),
            "guidance_scale": 9.0,
            "eligible_count": 10,
        }
    }
    f = c1.closure_guidance(state, base, cmap, labels, time_map, freq_map, block=5)
    rows, chans = np.divmod(cells, nchan)
    np.testing.assert_array_equal(
        f["guidance"], cmap[time_map[rows], freq_map[chans], labels[rows]]
    )
    assert f["outliers"] is base["features"]["outliers"]
    g = cmap[time_map[:, None], freq_map[None], labels[:, None]]
    keep = state["train"] & np.isfinite(g) & (g > 0)
    assert f["guidance_scale"] == np.median(g[keep])
    assert base["features"]["guidance_scale"] == 9.0


def test_q1_statistics_calls():
    rng = np.random.default_rng(2)
    nant = 6
    pairs = np.array([(i, j) for i in range(nant) for j in range(i + 1, nant)])
    gmap = rng.uniform(0.5, 2.0, size=(4, 8, nant))
    gvalid = np.ones(gmap.shape, bool)
    guidance = np.maximum(gmap[:, :, pairs[:, 0]], gmap[:, :, pairs[:, 1]])
    # A closure map that follows the gain map: redundant.
    same = c1.q1_statistics(guidance, guidance, guidance, pairs, nant, gmap, gvalid)
    assert same["call"] == "redundant" and same["rho_bl"] == pytest.approx(1.0)
    # Reproducible structure unrelated to the gains: distinct.
    own = rng.uniform(0.5, 2.0, size=guidance.shape)
    jitter = own * np.exp(0.01 * rng.normal(size=own.shape))
    distinct = c1.q1_statistics(own, own, jitter, pairs, nant, gmap, gvalid)
    assert distinct["call"] == "distinct" and distinct["r2_bl"] < 0.25
    # Pure noise in each half: noise-dominated.
    halves = [rng.uniform(0.5, 2.0, size=guidance.shape) for _ in range(2)]
    noise = c1.q1_statistics(own, *halves, pairs, nant, gmap, gvalid)
    assert noise["call"] == "noise-dominated"


def test_questions_positive_rule():
    def pair(cand, ref, matched, a1, rms="null"):
        return {
            "candidate": cand,
            "reference": ref,
            "frozen": {
                "mse_test": {"ratio": None, "call": "undecidable"},
                "residual_rms": {"ratio": 1.0, "call": rms},
            },
            "matched": {"mse_test": {"ratio": 1.0, "call": matched}},
            "a1_drop": {
                "mse_test": {"ratio": 1.0, "call": a1},
                "matched_fallback": False,
            },
        }

    family = {
        "q1": {
            k: None
            for k in (
                "rho_ant",
                "rho_bl",
                "rho_chan",
                "r2_bl",
                "r2_add",
                "rho_half",
                "rho_half_spearman_brown",
                "rho_half_ant",
            )
        }
        | {"call": "noise-dominated"},
        "outlier": {"selected": 0},
    }
    record = {
        "families": {"trace": family},
        "closure_tv_policy": {"selection": {"guided_selected": False}},
        "calls": [
            pair("closure-tv-policy", "tricolour-firstpass", "better", "null"),
            pair("closure-outlier", "tricolour-firstpass", "null", "null"),
            pair("closure-outlier", "original", "null", "null"),
        ],
        "arms": {"closure-outlier": {"additions": 10}},
        "firstpass_additions": 100,
        "q3": {"trace": {}, "phase": {}, "trace_vs_phase": {}},
    }
    # Better against the first pass, but no guided mask was selected.
    assert not c1.questions(record)["q2"]["positive"]
    record["closure_tv_policy"]["selection"]["guided_selected"] = True
    assert c1.questions(record)["q2"]["positive_policy"]
    record["calls"][0]["frozen"]["residual_rms"]["call"] = "worse"
    assert not c1.questions(record)["q2"]["positive"]
    # The outlier arm: better than original, not worse than the first pass,
    # fewer additions than the first pass.
    record["calls"][2]["a1_drop"]["mse_test"]["call"] = "better"
    assert c1.questions(record)["q2"]["positive_outlier"]
    record["calls"][1]["matched"]["mse_test"]["call"] = "worse"
    assert not c1.questions(record)["q2"]["positive"]
    record["calls"][1]["matched"]["mse_test"]["call"] = "null"
    record["arms"]["closure-outlier"]["additions"] = 200
    assert not c1.questions(record)["q2"]["positive"]
