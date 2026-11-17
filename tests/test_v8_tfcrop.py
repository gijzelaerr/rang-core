# SPDX-License-Identifier: MIT
"""V8 tfcrop (research/v8-tfcrop.md): the conventions identified so far,
checked without CASA. D1 (the per-row rule) against CASA 6.7.6.14's flags
on the first planes of the S1 and S2 probes
(`research/results/v8-tfcrop-probe-casa.json`); the time direction as the
transposed frequency direction; window statistics refused."""

import base64
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from rang import tfcrop

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "research/results/v8-tfcrop-probe-casa.json"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def probe():
    import sys

    sys.path.insert(0, str(ROOT / "tools/oracles/casa"))
    return _load("tfcrop_probe", ROOT / "tools/oracles/casa/tfcrop_probe.py")


def test_d1_matches_casa_on_probe_planes(probe):
    rec = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    info = {"nbl": rec["nbl"], "ntime": rec["ntime"], "nchan": rec["nchan"]}
    designs = {"S1": probe.design_rows(info, seed=2)[0],
               "S2": probe.design_noise_rows(info, seed=3)[0],
               "W1": probe.design_windows(info, seed=8)[0]}  # fmt: skip
    nbl = info["nbl"]
    for arm in rec["arms"]:
        n = nbl * 4 * info["ntime"] * info["nchan"]
        casa = np.unpackbits(np.frombuffer(base64.b64decode(arm["flags"]), np.uint8))[
            :n
        ]
        casa = casa.astype(bool).reshape(nbl * 4, info["ntime"], info["nchan"])
        data = designs[arm["design"]]
        params = {"flagdimension": "freq"} | arm["params"]
        for k in range(nbl * 4):
            b, c = divmod(k, 4)
            a = np.abs(data[b::nbl, :, c]).astype(np.float64)
            got = tfcrop.plane(a, np.zeros(a.shape, bool), params)
            assert np.array_equal(got, casa[k]), (arm["design"], arm["arm"], k)


def test_row_rule_passes():
    # One pass when the first sd is below 0.1 (the previous sd starts at 0).
    u = np.zeros((1, 100))
    u[0, :2] = [0.05, 0.015]
    u[0, 2:] = 0.004 * (-1.0) ** np.arange(98)
    got = tfcrop.row_flags(u, np.ones(u.shape, bool), 3.0)
    sd = np.sqrt(np.mean(u**2))
    # A second pass would flag 0.015 (its sd is 0.0043).
    assert got[0, 0] and not got[0, 1] and 0.015 < 3 * sd < 0.05
    # A second pass when the first sd is at least 0.1.
    v = np.full((1, 100), 0.05) * (-1.0) ** np.arange(100)
    v[0, :3] = 2.0
    v[0, 3] = 0.3
    got = tfcrop.row_flags(v, np.ones(v.shape, bool), 3.0)
    assert got[0, :4].all() and not got[0, 4:].any()


def test_time_is_transposed_freq():
    rng = np.random.default_rng(1)
    a = (2.0 + np.linspace(-1, 1, 64)[:, None]) * (
        1 + 0.1 * rng.standard_normal((64, 48))
    )
    a[10, 5] *= 3
    f = np.zeros(a.shape, bool)
    t = tfcrop.plane(a, f, {"flagdimension": "time", "timecutoff": 3.0})
    q = tfcrop.plane(
        a.T, f.T, {"flagdimension": "freq", "freqcutoff": 3.0, "freqfit": "line"}
    )
    assert np.array_equal(t, q.T) and t[10, 5]


def test_window_statistics_edges():
    # D4: a window that would reach past the band edge flags nothing.
    u = np.zeros((1, 32))
    u[0, 0] = u[0, 1] = 1.0
    sd = np.full((1, 1), 0.1)
    got = tfcrop.window_flags(u, sd, 3.0, "sum", 1)
    assert not got[0, 0] and got[0, 1] and got[0, 2] and not got[0, 3:].any()
    assert np.array_equal(tfcrop.window_flags(u, sd, 3.0, "both", 1),
                          tfcrop.window_flags(u, sd, 3.0, "std", 1))  # fmt: skip
