"""E5 (research/e5-prereview.md): fixes found by the v0.2.0 pre-review."""

import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from rang import core_config as cc

ROOT = Path(__file__).resolve().parents[1]

VALUES = [None, True, 3, -1, 1.5, "x", "1e-3", [], [1], ["x"], [1.5, 2.5], {}, {"a": 1}]
BASE = {
    "version": 1,
    "fields": {"fcal": ["CAL"], "gcal": ["G"], "xcal": ["X"], "target": ["T"]},
    "flag": {"strategy": "s.yaml"},
    "image": {"size": 64, "scale": "2asec"},
}


def _leaves(spec, path=()):
    for k, v in spec.items():
        if isinstance(v, dict):
            yield from _leaves(v, (*path, k))
        else:
            yield (*path, k)


def _put(d, path, v):
    for k in path[:-1]:
        d = d.setdefault(k, {})
    d[path[-1]] = v


def _configs():
    for path in _leaves(cc.SCHEMA):
        for v in VALUES:
            raw = copy.deepcopy(BASE)
            _put(raw, path, v)
            yield f"{'.'.join(path)}={v!r}", raw
    for section, kind in (("primary", "complex"), ("primary", "G"), ("polcal", "Df")):
        for key in cc.TERM_KEYS:
            for v in VALUES:
                raw = copy.deepcopy(BASE)
                term = {"type": v} if key == "type" else {"type": kind, key: v}
                raw["calibrate"] = {"refant": "m000", section: {"terms": [term]}}
                yield f"calibrate.{section}.terms[0]({kind}).{key}={v!r}", raw
    for key in cc.TARGET_KEYS:
        for v in VALUES:
            raw = copy.deepcopy(BASE)
            raw["apply"] = {
                "targets": [{"field": ["T"], "tables": ["complex"], key: v}]
            }
            yield f"apply.targets[0].{key}={v!r}", raw


def test_malformed_values_give_the_error_report_not_a_traceback():
    """Every schema leaf, term key and apply-target key, given values of the
    wrong type, ends in errors or a ConfigError; before E5, 11 forms (such as
    `terms:` with nothing after it, or `selfcal.clean_cutoff: 3`) raised a
    TypeError with exit 1."""
    crashes = {}
    for label, raw in _configs():
        try:
            config, errors = cc.resolve(raw)
            if not errors:
                cc.refusals(config, cc.STAGES)
        except cc.ConfigError:
            pass
        except Exception as exc:  # noqa: BLE001 - the test collects them all
            crashes.setdefault(f"{type(exc).__name__}: {exc}", label)
    assert crashes == {}


@pytest.mark.parametrize(
    "text",
    [
        "version: 1\ncalibrate:\n  secondary:\n    terms:\n",
        "version: 1\nselfcal: {clean_cutoff: 3}\n",
    ],
)
def test_the_reported_forms_are_configuration_errors(text):
    _, errors = cc.resolve(cc.loads(text))
    assert errors


@pytest.mark.parametrize(
    "section, key",
    [
        ("apply", "column"),
        ("selfcal", "model_column"),
        ("selfcal", "output_column"),
    ],
)
def test_no_configuration_writes_data(section, key):
    """WB-01: only FLAG is backed up, so every column rang writes refuses
    DATA. selfcal.input_column DATA is only read; the stage refuses to copy
    apply's output into it."""
    raw = copy.deepcopy(BASE)
    raw[section] = {key: "DATA"}
    _, errors = cc.resolve(raw)
    assert (f"{section}.{key}", "DATA is never written") in errors


def test_the_write_back_session_never_writes_data(tmp_path):
    from rang import core_ms, core_ms_write, core_writeback

    if not core_ms_write.has_creator():
        pytest.skip("extension built without the table writer")
    spec = importlib.util.spec_from_file_location(
        "w1_writeback", ROOT / "examples/w1_writeback.py"
    )
    w1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w1)
    ms = w1.make_ms(tmp_path / "x.ms", 12, 4)
    with core_ms.open_table(ms) as t:
        before = t.getcol("DATA")
    with (
        pytest.raises(ValueError, match="DATA is never written"),
        core_writeback.WriteBack(ms, stage="test") as w,
    ):
        w.write("DATA", 0, np.zeros_like(before[:4]))
    with core_ms.open_table(ms) as t:
        assert np.array_equal(t.getcol("DATA"), before)


def test_selfcal_refuses_to_copy_apply_output_into_data(tmp_path):
    """WB-01: with this run's apply finished, selfcal would copy
    apply.column into its input column; DATA there is refused."""
    from rang import core_ms_write
    from rang import core_pipeline as pipe

    if not core_ms_write.has_creator():
        pytest.skip("extension built without the table writer")
    spec = importlib.util.spec_from_file_location(
        "w1_writeback", ROOT / "examples/w1_writeback.py"
    )
    w1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w1)
    ms = w1.make_ms(tmp_path / "x.ms", 12, 4)
    config, errors = cc.resolve(
        {**copy.deepcopy(BASE), "selfcal": {"input_column": "DATA"}}
    )
    assert errors == []
    run = pipe.RunDir(tmp_path / "run", ms)
    with run.locked():
        run.state["stages"]["apply"] = {"status": "done", "finished": "t"}
        ctx = {"config": config, "ms": ms, "run": run}
        with pytest.raises(pipe.StageFailed, match="DATA is never written"):
            pipe._selfcal_input(ctx)


def test_the_missing_model_column_refusal_names_the_imager_option(tmp_path):
    """CLI-07: the refusal said MODEL_DATA from the imager was a future
    task; `image.write_model: true` writes it."""
    from rang import core_ms_write
    from rang import core_pipeline as pipe

    if not core_ms_write.has_creator():
        pytest.skip("extension built without the table writer")
    spec = importlib.util.spec_from_file_location(
        "w1_writeback", ROOT / "examples/w1_writeback.py"
    )
    w1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w1)
    ms = w1.make_ms(tmp_path / "x.ms", 12, 4)
    raw = {**copy.deepcopy(BASE), "calibrate": {"model": {"source": "column"}}}
    config, errors = cc.resolve(raw)
    assert errors == []
    info = pipe.inspect_ms(ms)
    assert "MODEL_DATA" not in info["columns"]
    with pytest.raises(pipe.Refused) as refused:
        pipe.preflight(config, info, ["calibrate"])
    lines = [
        x for x in str(refused.value).splitlines() if "calibrate.model.column" in x
    ]
    assert lines and "image.write_model: true" in lines[0]
