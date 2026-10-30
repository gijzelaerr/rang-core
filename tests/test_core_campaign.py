"""Offline tests of the task K campaign pieces (research/core-k-luno-campaign.md)."""

import json

import numpy as np
import pytest
from rangtoy import core_campaign


def _memcpyed_chunk(payload, blocksize=0):
    blocksize = blocksize or max(len(payload), 1)
    header = bytes([2, 1, 0x02, 4])
    header += len(payload).to_bytes(4, "little")
    header += blocksize.to_bytes(4, "little")
    header += (16 + len(payload)).to_bytes(4, "little")
    return header + payload


def _zarray(shape, chunks, dtype, filters=None):
    return json.dumps(
        {
            "chunks": list(chunks),
            "compressor": {"id": "blosc", "cname": "lz4", "clevel": 5, "shuffle": 1},
            "dtype": dtype,
            "fill_value": None,
            "filters": filters,
            "order": "C",
            "shape": list(shape),
            "zarr_format": 2,
        }
    )


def _write(objects, key, payload):
    path = objects / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload if isinstance(payload, bytes) else payload.encode())


def test_decode_object_numeric_trims_to_shape_and_rejects_pickle(tmp_path):
    objects = tmp_path / "objects"
    values = np.arange(10, dtype="<f8").reshape(5, 2)
    _write(objects, "A/.zarray", _zarray((3, 2), (5, 2), "<f8"))
    _write(objects, "A/0.0", _memcpyed_chunk(values.tobytes()))
    out = core_campaign.decode_object(objects, "A", "0.0")
    assert out.shape == (3, 2) and np.array_equal(out, values[:3])
    names = ["m000", "m001"]
    _write(objects, "N/.zarray", _zarray((2,), (2,), "|O", [{"id": "json2"}]))
    _write(objects, "N/0", _memcpyed_chunk(json.dumps(names + ["|O", [2]]).encode()))
    assert list(core_campaign.decode_object(objects, "N", "0")) == names
    _write(objects, "P/.zarray", _zarray((2,), (2,), "|O", [{"id": "pickle"}]))
    _write(objects, "P/0", _memcpyed_chunk(b"\x80\x04"))
    with pytest.raises(ValueError):
        core_campaign.decode_object(objects, "P", "0")


def _synthetic(seed=3, nrow=12, nchan=64):
    rng = np.random.default_rng(seed)
    a1 = np.repeat([0, 0, 0, 1, 1, 2], 2)
    a2 = np.repeat([1, 2, 3, 2, 3, 3], 2)
    times = np.repeat([1.0, 2.0], 6)
    order = np.argsort(times, kind="stable")
    a1, a2, times = a1[order], a2[order], times[order]
    model = np.zeros((nrow, nchan, 4), np.complex64)
    model[..., 0] = model[..., 3] = 10.0
    data = (
        model
        + (rng.normal(size=model.shape) + 1j * rng.normal(size=model.shape)).astype(
            np.complex64
        )
        * 0.01
    )
    weights = np.full(model.shape, 2.0, np.float32)
    flags = np.zeros(model.shape, bool)
    flags[0, :4] = True
    rows = np.zeros(nrow, bool)
    arrays = {
        "DATA": data,
        "MODEL_DATA": model,
        "WEIGHT_SPECTRUM": weights,
        "FLAG": flags,
        "FLAG_ROW": rows,
        "ANTENNA1": a1.astype(np.int32),
        "ANTENNA2": a2.astype(np.int32),
        "TIME": times,
    }
    extra = {
        "antenna_names": ["m000", "m001", "m002", "m003"],
        "chan_freq": 1.3e9 + 1e6 * np.arange(nchan),
    }
    return arrays, extra


def test_build_state_is_deterministic_and_keeps_flagged_cells_out():
    arrays, extra = _synthetic()
    state = core_campaign.build_state(arrays, extra)
    again = core_campaign.build_state(arrays, extra)
    for key in ("train", "validation", "test"):
        assert np.array_equal(state[key], again[key])
    assert not state["eligible"][0, :4].any()
    assert not (state["train"] & state["validation"]).any()
    assert not (state["train"] & state["test"]).any()
    assert state["train"].sum() > state["validation"].sum() > 0
    assert state["names"] == ["m000", "m001", "m002", "m003"]
    different = core_campaign.build_state(arrays, extra, seed=8)
    assert not np.array_equal(state["train"], different["train"])


def test_apply_gains_inverts_the_corruption():
    rng = np.random.default_rng(5)
    nt, nf, na = 2, 3, 4
    gains = np.eye(2)[None, None, None] + 0.2 * (
        rng.normal(size=(nt, nf, na, 2, 2)) + 1j * rng.normal(size=(nt, nf, na, 2, 2))
    )
    valid = np.ones((nt, nf, na), bool)
    valid[1, 2, 3] = False
    p = np.array([0, 1, 2, 0])
    q = np.array([1, 2, 3, 3])
    tb = np.array([0, 0, 1, 1])
    fb = np.array([0, 1, 2])
    model = np.zeros((4, 3, 2, 2), np.complex128)
    model[..., 0, 0] = model[..., 1, 1] = 3.0
    gp = gains[tb[:, None], fb[None], p[:, None]]
    gq = gains[tb[:, None], fb[None], q[:, None]]
    data = (
        (gp @ model @ gq.conj().swapaxes(-1, -2)).reshape(4, 3, 4).astype(np.complex64)
    )
    corrected, ok = core_campaign.apply_gains(data, gains, valid, p, q, tb, fb)
    assert ok.shape == (4, 3) and not ok[2, 2] and not ok[3, 2] and ok[0, 0]
    expected = model.reshape(4, 3, 4)
    assert np.allclose(corrected[ok], expected[ok], atol=1e-5)
    assert np.all(corrected[~ok] == 0)


def test_image_metrics_recovers_a_scaled_psf():
    n = 128
    y, x = np.mgrid[:n, :n]
    psf = np.exp(-((y - 64) ** 2 + (x - 64) ** 2) / 8.0) + 0.1 * np.cos(x / 3.0)
    psf /= psf[64, 64]
    dirty = 7.5 * psf
    metrics = core_campaign.image_metrics(dirty, psf, model_flux=15.0)
    assert metrics["peak_pixel"] == [64, 64]
    assert abs(metrics["peak_jy_per_beam"] - 7.5) < 1e-12
    assert metrics["residual_rms"] < 1e-12
    assert metrics["psf_max_sidelobe"] > 0
    assert abs(metrics["flux_recovery"] - 0.5) < 1e-12
    shifted = np.roll(np.roll(dirty, 1, axis=0), -2, axis=1)
    moved = core_campaign.image_metrics(shifted, psf)
    assert moved["peak_pixel"] == [65, 62]
    assert moved["residual_rms"] < 1e-9


def test_decision_rule_three_way_and_undecidable():
    assert core_campaign.call(0.98, 1.0)["call"] == "better"
    assert core_campaign.call(1.02, 1.0)["call"] == "worse"
    assert core_campaign.call(1.005, 1.0)["call"] == "null"
    assert core_campaign.call(None, 1.0)["call"] == "undecidable"
    assert core_campaign.call(1.0, 0.0)["call"] == "undecidable"


def test_tricolour_checks_detect_cleared_input_flags():
    flags = np.zeros((3, 4, 4), bool)
    flags[1] = True
    stages = {
        "00-flag_nans_zeros": flags[..., 0][:, None],
        "01-sum_threshold": flags[..., 0][:, None],
    }
    strategies = [{"task": "flag_nans_zeros"}, {"task": "sum_threshold"}]
    result = {"flags": flags, "stages": stages}
    ok = core_campaign.tricolour_checks(result, np.zeros_like(flags), strategies)
    assert ok["pass"] and ok["uniform_over_correlations"]
    cleared = np.zeros_like(flags)
    cleared[0, 0] = True
    bad = core_campaign.tricolour_checks(result, cleared, strategies)
    assert not bad["superset_of_input"] and not bad["pass"]
    mixed = flags.copy()
    mixed[1, 0, 2] = False
    assert not core_campaign.tricolour_checks(
        {"flags": mixed, "stages": stages}, np.zeros_like(flags), strategies
    )["uniform_over_correlations"]


def test_solve_arm_and_tv_loop_on_synthetic_cells():
    arrays, extra = _synthetic()
    state = core_campaign.build_state(arrays, extra)
    zero = np.zeros_like(state["train"])
    base = core_campaign.solve_arm(state, zero, "original")
    assert base["metrics"]["losses"]["validation"] is not None
    assert base["metrics"]["solver"]["converged_fraction"] > 0
    assert base["metrics"]["median_diagonal_amplitude"] is not None
    trials, best, unguided = core_campaign.tv_loop(
        state, base, base["metrics"]["scale"], "tv"
    )
    assert unguided is None or unguided["policy"]["tv_weight"] == 0
    assert trials[0]["accepted"] and trials[0]["objective"] == pytest.approx(1.25)
    assert len(trials) == 1 + len(core_campaign.THRESHOLDS) * len(
        core_campaign.TV_WEIGHTS
    )
    assert best["solve"]["added"].shape == state["train"].shape
    assert not (best["solve"]["added"] & ~state["train"]).any()
    assert all("policy" in t for t in trials)
