"""Offline tests of the L1-M field-model driver (research/l1-model-completeness.md)."""

import math

import numpy as np
import pytest
from rangtoy import core_campaign_array as array
from rangtoy import core_campaign_fieldmodel as l1m
from rangtoy import lsm

PHASE = (5.14617966, -1.11198611)


def _sources():
    ra0, dec0 = PHASE
    arcmin = math.radians(1 / 60)
    return [
        lsm.Source("A0", ra0 + 1e-7, dec0 - 1e-5, 15.0, freq0=1.3e9, spi=(-0.1, -0.6)),
        lsm.Source(
            "P1", ra0 + 12 * arcmin, dec0 + 3 * arcmin, 0.03, freq0=1.3e9, spi=(-0.9,)
        ),
        lsm.Source(
            "G1",
            ra0 - 20 * arcmin,
            dec0 + 8 * arcmin,
            0.002,
            freq0=1.3e9,
            spi=(-3.0,),
            emaj=math.radians(6 / 3600),
            emin=math.radians(5 / 3600),
            pa=math.radians(54),
        ),
    ]


def _uvw(nrow=40, seed=2):
    rng = np.random.default_rng(seed)
    return rng.normal(size=(nrow, 3)) * np.array([3000.0, 3000.0, 300.0])


def test_direct_dft_matches_the_core_predictor():
    uvw, nu = _uvw(), np.linspace(1.07e9, 1.5e9, 9)
    comps = lsm.components(_sources(), PHASE)
    core_vis = l1m.predict_stokes_i(uvw, nu, comps)
    dft = l1m.direct_dft(uvw, nu, comps)
    assert np.abs(core_vis - dft).max() <= 1e-10 * np.abs(dft).max()


def test_prediction_checks_pass_and_bound_the_pa():
    uvw, nu = _uvw(80) / 10, np.linspace(1.07e9, 1.5e9, 16)
    checks = l1m.prediction_checks(uvw, nu, _sources(), PHASE)
    assert checks["dft_pass"] and checks["pa_pass"] and checks["pass"]
    assert checks["pa90_max_abs_jy"] > 0
    assert checks["field_term_rms_jy"] > 0


def test_model_sources():
    sources = _sources()
    assert [s.name for s in l1m.model_sources(sources, "point")] == ["A0"]
    assert len(l1m.model_sources(sources, "field")) == 3
    with pytest.raises(ValueError):
        l1m.model_sources(sources, "stored")


def test_write_model_is_stokes_i_on_the_parallel_hands_in_blocks():
    uvw, nu = _uvw(37), np.linspace(1.07e9, 1.5e9, 5)
    comps = lsm.components(_sources(), PHASE)
    model = np.full((37, 5, 4), 7 + 7j, np.complex64)
    assert l1m.write_model(model, uvw, nu, comps, block=8)
    expected = l1m.predict_stokes_i(uvw, nu, comps).astype(np.complex64)
    assert np.array_equal(model[..., 0], expected)
    assert np.array_equal(model[..., 3], expected)
    assert not model[..., 1:3].any()


def _synthetic(seed=3, nchan=32, ntime=4):
    """Four stations, six baselines, a 10 Jy model and small noise."""
    rng = np.random.default_rng(seed)
    pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    a1 = np.array([p for _ in range(ntime) for p, _ in pairs], np.int32)
    a2 = np.array([q for _ in range(ntime) for _, q in pairs], np.int32)
    times = np.repeat(np.arange(ntime, dtype=float), len(pairs))
    nrow = len(times)
    model = np.zeros((nrow, nchan, 4), np.complex64)
    model[..., 0] = model[..., 3] = 10.0
    noise = rng.normal(size=model.shape) + 1j * rng.normal(size=model.shape)
    data = model + (noise * 0.01).astype(np.complex64)
    flags = np.zeros(model.shape, bool)
    flags[0, :4] = True
    arrays = {
        "DATA": data,
        "MODEL_DATA": model,
        "WEIGHT_SPECTRUM": rng.uniform(1.0, 3.0, model.shape).astype(np.float32),
        "FLAG": flags,
        "FLAG_ROW": np.zeros(nrow, bool),
        "ANTENNA1": a1,
        "ANTENNA2": a2,
        "TIME": times,
    }
    extra = {
        "antenna_names": ["m000", "m001", "m002", "m003"],
        "chan_freq": 1.3e9 + 1e6 * np.arange(nchan),
    }
    extra["uvw"] = _uvw(nrow, seed=7)
    extra["phase_dir"] = np.array(PHASE)
    extra["corr_type"] = np.array([9, 10, 11, 12], np.int32)
    return arrays, extra


def test_model_hook_keeps_the_split_and_replaces_the_model():
    arrays, extra = _synthetic()
    reference = array.build_state(
        {k: v.copy() for k, v in arrays.items()}, extra, nant=4
    )
    build = array.build_state
    hook = l1m.ModelHook("field", _sources())
    with hook.installed():
        assert array.build_state is not build
        state = array.build_state(arrays, extra, 4)
    assert array.build_state is build
    for key in ("eligible", "train", "validation", "test"):
        assert np.array_equal(state[key], reference[key])
        assert hook.record["split_sha256"][key] == l1m.array_sha256(reference[key])
    comps = lsm.components(_sources(), PHASE)
    expected = l1m.predict_stokes_i(extra["uvw"], extra["chan_freq"], comps)
    assert np.array_equal(state["model"][..., 0], expected.astype(np.complex64))
    assert not state["model"][..., 1:3].any()
    assert hook.record["checks"]["pass"] and hook.record["finite"]
    assert hook.record["components"]["components"] == 3


def test_model_hook_stored_leaves_the_model_and_restores_on_error():
    arrays, extra = _synthetic()
    before = arrays["MODEL_DATA"].copy()
    hook = l1m.ModelHook("stored")
    build, decode = array.build_state, array.decode_inputs
    with pytest.raises(RuntimeError), hook.installed():
        state = array.build_state(arrays, extra, 4)
        assert np.array_equal(state["model"], before)
        raise RuntimeError("inside")
    assert array.build_state is build and array.decode_inputs is decode


def test_model_hook_refuses_circular_feeds_and_polarised_sources():
    arrays, extra = _synthetic()
    extra["corr_type"] = np.array([5, 6, 7, 8], np.int32)
    with pytest.raises(RuntimeError), l1m.ModelHook("stored").installed():
        array.build_state(arrays, extra, 4)
    arrays, extra = _synthetic()
    sources = _sources()
    sources[1].q = 0.001
    with pytest.raises(RuntimeError), l1m.ModelHook("field", sources).installed():
        array.build_state(arrays, extra, 4)


def test_matched_model_losses_between_predicted_models(tmp_path):
    arrays, extra = _synthetic()
    runs = {}
    for arm in ("point", "field"):
        hook = l1m.ModelHook(arm, _sources())
        with hook.installed():
            state = array.build_state(
                {k: v.copy() for k, v in arrays.items()}, extra, 4
            )
        zero = np.zeros_like(state["train"])
        solve = array.solve_arm(state, zero, "original")
        d = tmp_path / arm / "gains"
        d.mkdir(parents=True)
        for label in l1m.COMPARED_ARMS:
            np.savez(
                d / f"{label}.npz",
                gains=solve["diagnostics"]["gains"],
                gain_valid=solve["diagnostics"]["gain_valid"],
            )
        runs[arm] = (hook, solve)
    hook, solve = runs["field"]
    out = l1m.matched_model_losses(
        hook, tmp_path / "field", {"point": tmp_path / "point"}
    )
    for label in l1m.COMPARED_ARMS:
        rec = out[label]
        assert rec["dropped_test"] == 0
        assert rec["losses"]["field"]["test"] == solve["metrics"]["losses"]["test"]
        assert (
            rec["losses"]["point"]["test"]
            == runs["point"][1]["metrics"]["losses"]["test"]
        )


def test_per_antenna_tv():
    gains = np.zeros((3, 4, 2, 2, 2), complex)
    gains[..., 0, 0] = gains[..., 1, 1] = 1.0
    valid = np.ones((3, 4, 2), bool)
    flat = l1m.per_antenna_tv(gains, valid, scale=1.0)
    assert flat["amplitude"] == [0.0, 0.0] and flat["phase_rad"] == [0.0, 0.0]
    # antenna 1: amplitude step of 0.5 between time 0 and 1 on both hands
    gains[1:, :, 1, 0, 0] = gains[1:, :, 1, 1, 1] = 1.5
    out = l1m.per_antenna_tv(gains, valid, scale=2.0)
    pairs = 2 * (2 * 4 + 3 * 3)  # time pairs + frequency pairs, both hands
    assert out["pairs"] == [pairs, pairs]
    assert out["amplitude"][1] == pytest.approx(0.5 * 2 * 4 / pairs / 2.0)
    assert out["amplitude"][0] == 0.0


def test_compare_with_l1_lists_differences():
    arm = {
        "additions_sha256": "a",
        "gains_sha256": "g",
        "final_flag_fraction": 0.5,
        "fixed_support_tv_vs_original": 0.1,
        "metrics": {
            "losses": {"test": 1.0},
            "tv": 0.1,
            "raw_tv": 0.2,
            "valid_gain_fraction": 0.9,
            "invalid_predictions": {"test": 0},
            "solver": {"converged_fraction": 0.8, "iterations": 50},
        },
    }
    result = {
        "split": {"seed": 7},
        "arms": {"original": arm, "x": None},
        "tricolour": {"t": {"checks": {"pass": True}, "newly_flagged_cells": 3}},
        "hypotheses": [{"mse_test": {"call": "null"}}],
        "amendment_1": {"pairs": [{"mse_test": {"call": "null"}, "seconds": 1.0}]},
    }
    candidates = {"tv-policy": [{"trial": "a", "mask_sha256": "m", "objective": 1.0}]}
    same = l1m.compare_with_l1(result, candidates, result, candidates)
    assert same["equal"] and same["count"] == 0
    import copy

    other = copy.deepcopy(result)
    other["arms"]["original"]["metrics"]["losses"]["test"] = 1.5
    other["amendment_1"]["pairs"][0]["seconds"] = 9.0  # timings are ignored
    diff = l1m.compare_with_l1(other, candidates, result, candidates)
    assert diff["differences"] == ["arms/original/metrics/losses"]


def test_tv_call_names():
    assert l1m.tv_call(0.98, 1.0)["call"] == "drops"
    assert l1m.tv_call(1.02, 1.0)["call"] == "rises"
    assert l1m.tv_call(1.0, 1.0)["call"] == "null"
    assert l1m.tv_call(None, 1.0)["call"] == "undecidable"


def test_lsm_hash_is_enforced(tmp_path):
    path = tmp_path / l1m.LSM_NAME
    path.write_text("#format: name ra_d dec_d i\nX 1 2 3\n")
    with pytest.raises(ValueError):
        l1m.verify_lsm(path)
    sha = l1m.file_sha256(path)
    found, record = l1m.fetch_lsm(tmp_path, url="http://invalid.invalid/", sha=sha)
    assert found == path and record["sha256"] == sha  # present: no download


def test_prediction_checks_fail_for_a_bright_elongated_gaussian():
    sources = _sources()
    sources[2].i = 0.05
    sources[2].emaj = math.radians(30 / 3600)
    uvw, nu = _uvw(80), np.linspace(1.07e9, 1.5e9, 16)
    checks = l1m.prediction_checks(uvw, nu, sources, PHASE)
    assert checks["dft_pass"] and not checks["pa_pass"]
    assert checks["pass"] is (not l1m.PA_GATED)  # amendment 2: reported


def test_compare_with_l1_exempts_image_ratios_in_amendment_1():
    base = {
        "split": {},
        "arms": {},
        "tricolour": {},
        "hypotheses": [],
        "amendment_1": {"pairs": [{"mse_test": 1.0, "residual_rms": {"ratio": 0.99}}]},
    }
    import copy

    other = copy.deepcopy(base)
    other["amendment_1"]["pairs"][0]["residual_rms"]["ratio"] = 0.99 + 1e-15
    assert l1m.compare_with_l1(other, {}, base, {})["equal"]
    other["amendment_1"]["pairs"][0]["mse_test"] = 2.0
    assert not l1m.compare_with_l1(other, {}, base, {})["equal"]
