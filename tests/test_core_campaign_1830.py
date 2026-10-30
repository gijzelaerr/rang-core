"""Offline tests of the L2 PKS 1830-211 campaign pieces (research/luno-1830-campaign.md).

Synthetic data only: the scalar model's flux rule and prediction, the
derived row-flag clause, the group-parameterised keys, the tolerant replay
comparison, the four-station survey under scalar and cross-hand models, and
the pre-registered verdict.
"""

import copy

import numpy as np
import pytest
from rangtoy import core_campaign_1830 as l2


def _short_rows(nrow=40, nchan=256, i0=3.0, alpha=0.4, seed=5):
    rng = np.random.default_rng(seed)
    freqs = 1.07e9 + (1.4978e9 - 1.07e9) * np.arange(nchan) / (nchan - 1)
    spectrum = i0 * (freqs / l2.NU0) ** alpha
    data = np.zeros((nrow, nchan, 4), np.complex64)
    data[..., 0] = data[..., 3] = spectrum
    data[..., 1] = data[..., 2] = 0.05
    data += (0.001 * rng.normal(size=data.shape)).astype(np.complex64)
    uvw = np.zeros((nrow, 3))
    uvw[:, 0] = np.linspace(10, 900, nrow)  # half the rows are long baselines
    eligible = np.ones((nrow, nchan), bool)
    return data, eligible, uvw, freqs


def test_power_law_fit_ignores_long_baselines(monkeypatch):
    monkeypatch.setattr(l2, "MIN_TILE_SAMPLES", 10)
    data, eligible, uvw, freqs = _short_rows()
    long = np.hypot(uvw[:, 0], uvw[:, 1]) >= l2.SHORT_BASELINE_M
    assert 0 < long.sum() < len(long)
    data[long] *= 7.0  # only short baselines may enter the fit
    fit = l2.fit_power_law(data, eligible, uvw, freqs, tile_width=32)
    assert fit["short_rows"] == int((~long).sum())
    assert fit["i0_jy"] == pytest.approx(3.0, rel=2e-3)


def test_power_law_fit_default_threshold_excludes_sparse_tiles():
    data, eligible, uvw, freqs = _short_rows()
    # 32-channel tiles of the short rows hold fewer than 1,000 samples.
    with pytest.raises(RuntimeError):
        l2.fit_power_law(data, eligible, uvw, freqs, tile_width=32)


def test_power_law_fit_values(monkeypatch):
    monkeypatch.setattr(l2, "MIN_TILE_SAMPLES", 10)
    data, eligible, uvw, freqs = _short_rows()
    eligible[:, 32:64] = False  # an empty tile is excluded, not fitted
    fit = l2.fit_power_law(data, eligible, uvw, freqs, tile_width=32)
    assert fit["tiles_used"] == 7
    assert not fit["tiles"][1]["used"] and fit["tiles"][1]["samples"] == 0
    assert fit["i0_jy"] == pytest.approx(3.0, rel=2e-3)
    assert fit["alpha"] == pytest.approx(0.4, abs=1e-2)


def test_power_law_fit_needs_two_tiles(monkeypatch):
    monkeypatch.setattr(l2, "MIN_TILE_SAMPLES", 10)
    data, eligible, uvw, freqs = _short_rows()
    eligible[:, 32:] = False
    with pytest.raises(RuntimeError):
        l2.fit_power_law(data, eligible, uvw, freqs, tile_width=32)


def test_scalar_prediction_is_the_power_law_with_zero_cross_hands():
    rng = np.random.default_rng(2)
    uvw = rng.normal(scale=2000.0, size=(12, 3))
    freqs = np.linspace(1.07e9, 1.4978e9, 50)
    model, check = l2.predict_scalar(uvw, freqs, 9.5, 0.25)
    assert check["pass"]
    assert check["max_abs_imaginary"] == 0.0
    expected = (9.5 * (freqs / l2.NU0) ** 0.25).astype(np.complex64)
    assert np.allclose(model[..., 0], expected[None], rtol=1e-6, atol=0)
    assert np.array_equal(model[..., 0], model[..., 3])
    assert not model[..., 1].any() and not model[..., 2].any()
    assert model.dtype == np.complex64


def test_derived_row_flag_clause():
    flags = np.zeros((4, 8, 4), bool)
    flags[1] = True  # fully flagged, FLAG_ROW false (the m031 rows)
    rows = np.array([False, False, True, False])
    added = np.zeros((4, 8), bool)
    added[3, 2] = True
    final, _rows, clause = l2.derived_row_flags(flags, rows, added)
    assert clause["equals_flag_row_or_all_flagged"]
    assert not clause["equals_input_flag_row"]
    assert clause["derived_rows"] == 2 and clause["input_flag_rows"] == 1
    assert final[3, 2].all() and not np.any(flags & ~final)


def test_keys_are_parameterised_by_group():
    keys = l2.input_keys(l2.GROUP)
    assert all("MAIN_1" not in k for k in keys)
    assert "MAIN/MAIN_2/UVW/0.0" in keys and "MAIN/MAIN_2/.zattrs" in keys
    assert "MAIN/MAIN_2/DATA/0.23.0" in keys
    assert "FIELD/FIELD_0/PHASE_DIR/0.0.0" in keys
    assert set(l2.FETCH_KEYS) <= set(keys) | {"MAIN/MAIN_2/DATA/.zarray"}
    assert sum(l2.EXPECTED_SIZES.values()) == 877_200_458
    assert l2.roots_for(l2.K_GROUP) == l2.array.ROOTS
    assert l2.roots_for(l2.GROUP, "outputs/x")[0].as_posix() == "outputs/x/objects"


def _replay_pair():
    arm = {
        "additions_sha256": "a",
        "gains_sha256": "g",
        "fixed_support_tv_vs_original": 0.1,
        "final_flag_fraction": 0.5,
        "additions": 0,
        "metrics": {"losses": {"test": 1.0}, "tv": 0.2},
        "image": {
            "dirty_sha256": "d",
            "psf_sha256": "p",
            "residual_rms": 0.01,
            "peak_jy_per_beam": 14.0,
        },
    }
    k = {
        "cells": {"shape": [1, 2, 4]},
        "split": {"counts": {"train": 3}},
        "arms": {"original": arm},
        "tricolour": {},
        "hypotheses": [],
    }
    replay = copy.deepcopy(k)
    replay["_candidates"] = {}
    return replay, k


def test_tolerant_replay_exempts_image_hashes_only():
    replay, k = _replay_pair()
    image = replay["arms"]["original"]["image"]
    image["dirty_sha256"], image["psf_sha256"] = "other", "other"
    image["residual_rms"] *= 1 + 1e-12
    out = l2.compare_replay_tolerant(replay, k, {})
    assert out["all_equal"]
    assert out["image_hashes_reported"]["original"]["image_dirty_sha256"] is False
    image["residual_rms"] *= 1 + 1e-6
    assert not l2.compare_replay_tolerant(replay, k, {})["all_equal"]
    replay, k = _replay_pair()
    replay["arms"]["original"]["gains_sha256"] = "changed"
    assert not l2.compare_replay_tolerant(replay, k, {})["all_equal"]


def test_tolerant_replay_residual_call_ratio():
    replay, k = _replay_pair()
    null = {"ratio": 1.0, "call": "null"}
    k["hypotheses"] = [{"mse_test": null, "residual_rms": dict(null)}]
    replay["hypotheses"] = [
        {"mse_test": null, "residual_rms": {"ratio": 1.0 + 1e-14, "call": "null"}}
    ]
    assert l2.compare_replay_tolerant(replay, k, {})["all_equal"]
    replay["hypotheses"][0]["mse_test"] = {"ratio": 1.0 + 1e-14, "call": "null"}
    assert not l2.compare_replay_tolerant(replay, k, {})["all_equal"]


def _headline(call, rms="null", cost=True):
    return {
        "matched_mse_test": {"call": call},
        "residual_rms": {"call": rms},
        "cost_comparable": cost,
    }


@pytest.mark.parametrize(
    "calls, expected",
    [
        (("null", "null"), "null"),
        (("better", "better"), "positive"),
        (("better", "null"), "model-dependent (not established)"),
        (("worse", "worse"), "TV worse"),
        (("undecidable", "null"), "null"),
        (("undecidable", "undecidable"), "undecidable"),
    ],
)
def test_verdict_rule(calls, expected):
    out = l2.verdict({"stored": _headline(calls[0]), "scalar": _headline(calls[1])})
    assert out["verdict"] == expected
    if "undecidable" in calls and expected != "undecidable":
        assert out["rests_on_one_model"]


def test_positive_needs_residual_and_cost():
    heads = {"stored": _headline("better"), "scalar": _headline("better", "worse")}
    assert l2.verdict(heads)["verdict"].startswith("not established")
    heads = {"stored": _headline("better", cost=False), "scalar": _headline("better")}
    assert l2.verdict(heads)["verdict"].startswith("not established")


def _survey_arrays(model):
    pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    ntime, nchan = 2, 32
    a1 = np.array([p for _ in range(ntime) for p, _ in pairs])
    a2 = np.array([q for _ in range(ntime) for _, q in pairs])
    nrow = len(a1)
    return {
        "ANTENNA1": a1,
        "ANTENNA2": a2,
        "TIME": np.repeat(np.arange(ntime, dtype=float), len(pairs)),
        "FLAG": np.zeros((nrow, nchan, 4), bool),
        "WEIGHT_SPECTRUM": np.ones((nrow, nchan, 4), np.float32),
        "MODEL_DATA": np.broadcast_to(model, (nrow, nchan, 4)).copy(),
    }


def test_survey_scalar_identifies_and_cross_hands_go_over_rank():
    scalar = _survey_arrays(np.array([5, 0, 0, 5], np.complex64))
    out = l2.survey(scalar)
    assert out["bins"] == 1 and out["bins_with_train"] == 1
    assert out["fully_identified"] == 1
    assert out["status"] == {"fully_identified status0": 1}
    leaky = _survey_arrays(np.array([5, 0.05 + 0.01j, 0.04 - 0.02j, 5], np.complex64))
    out = l2.survey(leaky)
    assert out["over_rank"] == 1
    assert list(out["status"]) == ["over_rank status6"]


def test_survey_solved_gains_report_flagged_stations():
    arrays = _survey_arrays(np.array([5, 0, 0, 5], np.complex64))
    gains = np.broadcast_to(np.eye(2), (1, 1, 6, 2, 2)).astype(np.complex128)
    valid = np.ones((1, 1, 6), bool)
    assert l2.survey(arrays, gains, valid)["fully_identified"] == 1
    valid[0, 0, 2] = False
    out = l2.survey(arrays, gains, valid)
    assert out["no_solved_gain"] == 1 and out["fully_identified"] == 0
