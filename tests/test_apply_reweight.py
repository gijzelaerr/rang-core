# SPDX-License-Identifier: MIT
"""Issue #55 (research/apply-reweight.md): the empirical re-weighting stage.
The block statistics against numpy and against known noise; off leaves the
apply stage and its hash as they were; on, it writes WEIGHT_SPECTRUM and WEIGHT
of the applied fields' rows only."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from rang import core_config, core_ms, core_ms_write, reweight

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w2_for_rw", ROOT / "tests/test_w2_commands.py"
)
w2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w2)

needs_writer = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


def test_classic_is_statwts_variance():
    rng = np.random.default_rng(55)
    v = (rng.normal(0, 2, (30, 8)) + 1j * rng.normal(0, 3, (30, 8))).astype(
        np.complex64
    )
    ok = rng.uniform(size=v.shape) > 0.1
    group = (np.arange(30) % 3).astype(np.uint32)
    var, count = reweight.block_variances(v, ok, group, 3, 4, "classic", 1)
    for g in range(3):
        for b in range(2):
            x = v[group == g][:, 4 * b : 4 * b + 4][
                ok[group == g][:, 4 * b : 4 * b + 4]
            ]
            x = x.astype(np.complex128)
            want = 0.5 * (np.var(x.real) + np.var(x.imag))
            assert count[g, b] == x.size
            assert abs(var[g, b] / want - 1) < 1e-12


@pytest.mark.parametrize("statistic", ["classic", "mad"])
def test_known_noise_is_recovered(statistic):
    rng = np.random.default_rng(7)
    nrow, nchan, ngroup = 4000, 32, 4
    group = (np.arange(nrow) % ngroup).astype(np.uint32)
    sigma = np.linspace(0.5, 1.5, nchan)[None, :] * (1 + np.arange(ngroup))[:, None]
    s = sigma[group]
    v = (rng.normal(size=(nrow, nchan)) + 1j * rng.normal(size=(nrow, nchan))) * s
    var, _ = reweight.block_variances(v.astype(np.complex64), np.ones(v.shape, bool), group,
                                      ngroup, 1, statistic, 10)  # fmt: skip
    ratio = var / sigma**2
    assert abs(np.median(ratio) - 1) < 0.03, np.median(ratio)


def test_mad_resists_rfi_and_classic_does_not():
    rng = np.random.default_rng(3)
    v = rng.normal(size=(2000, 16)) + 1j * rng.normal(size=(2000, 16))
    v[rng.uniform(size=v.shape) < 0.01] *= 100
    group = np.zeros(2000, np.uint32)
    ok = np.ones(v.shape, bool)
    mad, _ = reweight.block_variances(
        v.astype(np.complex64), ok, group, 1, 16, "mad", 1
    )
    classic, _ = reweight.block_variances(
        v.astype(np.complex64), ok, group, 1, 16, "classic", 1
    )
    assert abs(mad[0, 0] - 1) < 0.1 and classic[0, 0] > 10


def test_regularise_fills_short_blocks():
    var = np.array([[1.0, np.nan, 3.0, np.nan, 5.0], [np.nan] * 5])
    out = reweight.regularise(var, 3)
    assert np.isfinite(out[0]).all() and np.isnan(out[1]).all()
    assert np.array_equal(reweight.regularise(var, 0), var, equal_nan=True)


def test_settings_are_checked():
    reweight.Settings(mode="stokes_v", timebin="120s").check()
    for bad in ({"mode": "x"}, {"statistic": "x"}, {"timebin": "fast"}, {"chanbin": 0}):
        with pytest.raises(ValueError):
            reweight.Settings(**bad).check()


def test_off_leaves_the_apply_hash_unchanged():
    config, errors = core_config.resolve(core_config.loads("version: 1" + chr(10)))
    assert not errors
    assert config["apply"]["reweight"]["mode"] == "off"
    without = {
        **config,
        "apply": {k: v for k, v in config["apply"].items() if k != "reweight"},
    }
    assert core_config.stage_hash(config, "apply") == core_config.stage_hash(
        without, "apply"
    )
    on = {**config, "apply": {**config["apply"], "reweight": {**config["apply"]["reweight"],
                                                              "mode": "stokes_v"}}}  # fmt: skip
    assert core_config.stage_hash(on, "apply") != core_config.stage_hash(
        config, "apply"
    )


def _summary(ms):
    """The apply stage's full summary (the state keeps scalars only)."""
    import json

    path = ms.with_name(ms.name + ".rang-run") / "apply" / "summary.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _weights(ms):
    with core_ms.open_table(ms) as t:
        names = t.colnames()
        ws = t.getcol("WEIGHT_SPECTRUM") if "WEIGHT_SPECTRUM" in names else None
        return ws, t.getcol("WEIGHT"), t.getcol("FIELD_ID")


@needs_writer
def test_off_runs_apply_as_before(tmp_path):
    ms = w2.make_ms(tmp_path / "x.ms")
    config = w2.write_config(tmp_path, "run: {stages: [flag, calibrate, apply]}\n")
    w2.cli("run", config, ms)
    assert "reweight" not in _summary(ms)


@needs_writer
@pytest.mark.parametrize("mode", ["residual", "stokes_v"])
def test_on_writes_the_applied_fields_weights_only(tmp_path, mode):
    ms = w2.make_ms(tmp_path / "x.ms", ncorr=4)
    extra = (
        "run: {stages: [flag, calibrate, apply]}\n"
        f"apply: {{reweight: {{mode: {mode}, chanbin: 4, minsamp: 4, smooth: 0}}}}\n"
    )
    config = w2.write_config(tmp_path, extra)
    if mode == "residual":
        from rang import core_writeback as wb

        with wb.WriteBack(ms, stage="test") as w:
            w.ensure_column("MODEL_DATA")
    _, wt0, fid = _weights(ms)
    w2.cli("run", config, ms)
    summary = _summary(ms)["reweight"]
    assert summary["mode"] == mode and summary["rows"] == int((fid == 0).sum())
    ws, wt, _ = _weights(ms)
    cal, tgt = fid == 0, fid == 1
    assert (ws[cal] > 0).mean() > 0.5
    assert np.array_equal(wt[tgt], wt0[tgt])
    assert not np.array_equal(wt[cal], wt0[cal])
