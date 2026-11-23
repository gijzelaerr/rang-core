"""flag.residual (issue #51, research/flag-residual.md): config, hashes, kernels."""

import copy

import numpy as np
import pytest
from rang import core, core_config, flag_residual


def _config():
    raw = {"schema": "rang-config", "version": 1, "flag": {"strategy": "s.yaml"}}
    config, errors = core_config.resolve(raw)
    assert not errors, errors
    return config


def test_default_is_off():
    assert _config()["flag"]["residual"]["mode"] == "off"


def test_off_leaves_every_stage_hash_unchanged():
    config = _config()
    without = copy.deepcopy(config)
    del without["flag"]["residual"]
    for stage in core_config.STAGES:
        assert core_config.stage_hash(config, stage) == core_config.stage_hash(
            without, stage
        )


def test_on_changes_calibrate_hash_only():
    off = _config()
    on = copy.deepcopy(off)
    on["flag"]["residual"]["mode"] = "calibrators"
    assert core_config.stage_hash(on, "calibrate") != core_config.stage_hash(
        off, "calibrate"
    )
    for stage in ("flag", "image", "selfcal"):
        assert core_config.stage_hash(on, stage) == core_config.stage_hash(off, stage)


def _array(nant, ndump):
    a1, a2, dump = [], [], []
    for d in range(ndump):
        for p in range(nant):
            for q in range(p + 1, nant):
                a1.append(p)
                a2.append(q)
                dump.append(d)
    return (np.array(a1, np.uint32), np.array(a2, np.uint32), np.array(dump, np.uint32))


def test_kernels_flag_injected_rfi():
    ext = core.extension()
    nant, ndump, nchan, ncorr = 7, 30, 32, 4
    a1, a2, dump = _array(nant, ndump)
    nrow = len(a1)
    rng = np.random.default_rng(51)
    data = rng.normal(size=(nrow, nchan, ncorr)) + 1j * rng.normal(
        size=(nrow, nchan, ncorr)
    )
    data = (data + 3.0).astype(np.complex64)  # a point source plus noise
    rfi = [(10, 5), (77, 20), (300, 31)]
    for r, c in rfi:
        data[r, c, 0] += 60
    flag = np.zeros((nrow, nchan, ncorr), np.uint8)
    pairs = np.ascontiguousarray(data).view(np.float32)
    model = ext.flag_residual_median_model(pairs, flag, nrow, nchan, ncorr)
    model = model.reshape(nchan, ncorr, 2).view(np.complex64)[..., 0]
    assert np.allclose(model, 3.0, atol=0.5)
    res = np.ascontiguousarray(data - model[None], np.complex64).view(np.float32)
    new, counts = ext.flag_residual_rang(
        res, flag, nrow, nchan, ncorr, a1, a2, dump, nant, 5.0, 3.0, 16, 0.8
    )
    new = new.reshape(nrow, nchan)
    for r, c in rfi:
        assert new[r, c]
    assert new.mean() < 0.01
    assert counts["added"] == int(new.sum())
    q = ext.flag_residual_quartical(
        res, np.zeros((nrow, nchan), np.uint8), nrow, nchan, ncorr, a1, a2, nant,
        [0, 3], 5.0, 10.0, 0.0,
    )  # fmt: skip
    q = q.reshape(nrow, nchan)
    for r, c in rfi:
        assert q[r, c]
    assert q.mean() < 0.01


def test_bad_shapes_raise():
    ext = core.extension()
    with pytest.raises(ValueError):
        ext.flag_residual_median_model(
            np.zeros(6, np.float32), np.zeros(2, np.uint8), 3, 1, 1
        )


def test_tripwire_reads_nothing_without_tables():
    fired, frac = flag_residual.tripwire([{"name": "A", "type": "A"}], 0.05)
    assert not fired and frac == {}


def test_unquoted_off_in_yaml_is_off():
    raw = {
        "schema": "rang-config",
        "version": 1,
        "flag": {"strategy": "s.yaml", "residual": {"mode": False}},
    }
    config, errors = core_config.resolve(raw)
    assert not errors
    assert config["flag"]["residual"]["mode"] == "off"


def test_tripwire_is_relative_to_the_first_pass(monkeypatch):
    monkeypatch.setattr(
        flag_residual, "solution_flag_fractions", lambda steps, types=None: {"B": 0.30}
    )
    assert not flag_residual.tripwire([], 0.05, {"B": 0.297})[0]
    assert flag_residual.tripwire([], 0.05, {"B": 0.20})[0]
    assert flag_residual.tripwire([], 0.05)[0]
