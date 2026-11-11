"""E5 (research/e5-prereview.md): fixes found by the v0.2.0 pre-review."""

import copy

import pytest
from rang import core_config as cc

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
