# SPDX-License-Identifier: MIT
"""DL1 (research/dl1-contract.md): the `learned` key, the ONNX weights file
and its header, refusal, receipts, and F3 through the contract bit-identical
to `rang.f3flag`. Runs without PyTorch; the PyTorch parity test skips
without it."""

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from rang import core_config, learned
from rang import f3flag as f3
from test_f3_flag import synthetic

FIXTURE = Path(__file__).parent / "data" / "learned" / "f3-calibrator-seed3.onnx"
# sha256 of rang.f3net.flat_weights(load_params(F3 seed 3 weights.npz)).tobytes(),
# the npz itself sha256 2cdeee17... (research/f3-flagger.md, stage 4).
F3_FLAT_SHA = "51672bcb024c5f2ddf246d0a0db6ec842fd1240397d85083517f96ffb33c100b"
MINIMAL = {"schema": "rang-config", "version": 1, "flag": {"strategy": "x"}}


def resolved(raw=None):
    config, errors = core_config.resolve(copy.deepcopy(raw or MINIMAL))
    assert not errors
    return config


def on(mode="propose", force=False, weights=FIXTURE):
    return {"mode": mode, "weights": str(weights), "force": force}


def test_every_stage_has_learned_off():
    config = resolved()
    for stage in core_config.STAGES:
        assert config[stage]["learned"] == {
            "mode": "off",
            "weights": None,
            "force": False,
        }
    assert "learned:" in core_config.defaults_yaml()


def test_off_leaves_stage_hash_unchanged():
    config = resolved()
    for stage in core_config.STAGES:
        before = core_config.stage_hash(config, stage)
        stripped = copy.deepcopy(config)
        for s in core_config.STAGES:
            del stripped[s]["learned"]
        # The hash of the configuration without the key, computed the old way.
        old = core_config.stage_hash(stripped, stage)
        assert before == old


def test_non_off_hash_takes_the_file_sha():
    config = resolved()
    h0 = core_config.stage_hash(config, "flag")
    config["flag"]["learned"] = on()
    h1 = core_config.stage_hash(config, "flag")
    assert h1 != h0
    part = learned.hash_part(config["flag"]["learned"])
    assert part["weights_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    # The path is not hashed: the same file elsewhere gives the same hash.
    assert set(part) == {"mode", "force", "weights_sha256"}
    assert core_config.stage_hash(config, "image") == core_config.stage_hash(
        resolved(), "image"
    )


def test_unknown_mode_is_a_schema_error():
    raw = copy.deepcopy(MINIMAL)
    raw["flag"]["learned"] = {"mode": "maybe"}
    _, errors = core_config.resolve(raw)
    assert any(path == "flag.learned.mode" for path, _ in errors)


def test_non_off_without_pipeline_tenant_is_refused():
    raw = copy.deepcopy(MINIMAL)
    raw["flag"]["learned"] = on(force=True)
    with pytest.raises(core_config.ConfigError) as e:
        core_config.validate(raw, ["flag"])
    assert [r.task for r in e.value.refusals] == ["DL"]
    assert "no learned tenant" in str(e.value)
    raw["apply"] = {"learned": {"mode": "propose", "weights": None}}
    with pytest.raises(core_config.ConfigError):
        core_config.validate(raw, ["apply"])
    core_config.validate(MINIMAL, ["flag"])  # off: no refusal


def test_fixture_header():
    w = learned.load(FIXTURE)
    h = w.header
    assert (h.stage, h.data_class, h.telescope, h.band) == (
        "flag",
        "calibrator",
        "MeerKAT",
        "L",
    )
    assert h.architecture["id"] == learned.DILATED_CNN
    assert h.architecture["hyperparameters"] == {
        "inputs": 15,
        "hidden": 8,
        "dilations": [1, 2, 4, 8, 16],
    }
    assert not any(h.passed(m) for m in ("propose", "settings", "replace"))
    assert w.ops == ("Conv", "Relu") * 5 + ("Conv",)
    assert w.inputs == ("planes",) and w.outputs == ("logits",)
    assert len(w.payload) < 32_000


def test_weights_byte_equal_to_f3():
    flat = learned.dilated_cnn_weights(learned.load(FIXTURE))
    assert flat.dtype == np.float32 and flat.size == 3433
    assert hashlib.sha256(flat.tobytes()).hexdigest() == F3_FLAT_SHA


def test_refusal_order_gates_header_envelope():
    with pytest.raises(learned.Refused, match="has not passed the gates"):
        learned.select("flag", on())
    d = learned.select("flag", on(force=True))
    assert d.forced == ["gates"] and not d.fallback
    with pytest.raises(learned.Refused, match="weights file of stage flag"):
        learned.select("calibrate", on(force=True))
    with pytest.raises(learned.Refused, match="has no mode settings"):
        learned.select("flag", on(mode="settings", force=True))
    outside = {"band_hz": (856e6, 1712e6)}
    d = learned.select("flag", on(force=True), outside)
    assert d.fallback and d.envelope_violations
    assert (
        learned.select("flag", on(force=True), {"band_hz": (1.1e9, 1.4e9)}).fallback
        is False
    )
    with pytest.raises(learned.Refused):
        learned.select("flag", on(mode="replace", force=False), outside)
    d = learned.select("flag", on(mode="replace", force=True), outside)
    assert d.forced == ["gates", "envelope"] and not d.fallback
    assert learned.select("flag", {"mode": "off", "weights": None}) is None


def test_receipt():
    d = learned.select("flag", on(force=True), {"band_hz": (1.1e9, 1.2e9)})
    r = d.receipt()
    assert r["weights_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert r["gates_passed"] is False and r["forced"] == ["gates"]
    assert r["envelope"] == {"ok": True, "violations": []}
    assert r["mode"] == "propose" and r["approximate"] is False
    json.dumps(r)


def test_bad_files_are_refused(tmp_path):
    p = tmp_path / "x.onnx"
    p.write_bytes(b"\xff\xff\xff")
    with pytest.raises(learned.Refused, match="ONNX"):
        learned.load(p)
    with pytest.raises(learned.Refused):
        learned.load(tmp_path / "missing.onnx")
    good = learned.load(FIXTURE)
    with pytest.raises(learned.Refused, match="format"):
        learned.Header.from_dict({"format": "other"})
    d = {"format": learned.FORMAT, **good.header.__dict__}
    d["gates"] = {"propose": {"passed": "yes"}}
    with pytest.raises(learned.Refused, match="passed"):
        learned.Header.from_dict(d)


def test_f3_through_the_contract_is_bit_identical():
    """research/dl1-contract.md section 6 (b): the contract's path (ONNX file,
    forced, the kernel) against rang.f3flag with F3's flat weights."""
    scan = synthetic()
    flagged = scan["input_flags"].any(-1)
    d = learned.select("flag", on(force=True))
    z = learned.run_dilated_cnn(d, scan, flagged)
    flat = learned.dilated_cnn_weights(d.weights)
    assert hashlib.sha256(flat.tobytes()).hexdigest() == F3_FLAT_SHA
    ref = f3.rust_logits(scan, flagged, flat.copy())
    assert z.tobytes() == ref.tobytes()


def test_torch_matches_kernel():
    torch = pytest.importorskip("torch")
    from rang import learned_torch

    scan = synthetic()
    flagged = scan["input_flags"].any(-1)
    flat = learned.dilated_cnn_weights(learned.load(FIXTURE))
    net = learned_torch.load_flat(learned_torch.dilated_cnn(15), flat)
    ix = f3.index(scan)
    x = f3.rust_features(scan, flagged, np.arange(len(ix["ubl"])))
    with torch.no_grad():
        y = net(torch.from_numpy(np.ascontiguousarray(x.transpose(0, 3, 1, 2)))).numpy()
    zt = y[:, 0][ix["bl"], ix["t"]]
    zr = f3.rust_logits(scan, flagged, flat)
    assert np.abs(zt - zr)[~flagged].max() <= 1e-4


def test_yaml_off_is_off():
    raw = core_config.loads(
        "schema: rang-config\nversion: 1\nflag:\n  strategy: x\n  learned:\n    mode: off\n"
    )
    config, errors = core_config.resolve(raw)
    assert not errors and config["flag"]["learned"]["mode"] == "off"
