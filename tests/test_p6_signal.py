"""Task P6: ported signal-track algebra equals the frozen functions bit for bit.

research/p6-python-hotspots.md criterion 4. The stage-level identity (whole
`result.json`) is the labelled trial, not this suite.
"""

import ast
import inspect
import os

import numpy as np
import pytest
from rangtoy import core_signal, core_trend
from rangtoy import flagging_prospective as prospective
from rangtoy import flagging_response as response
from rangtoy.flagging_signal import corrected_intensity as frozen_corrected
from rangtoy.flagging_signal_guard import inverse_tangent as frozen_tangent
from rangtoy.flagging_signal_guard import train_signal_guard as frozen_guard


def _same(left, right):
    assert len(left) == len(right)
    for a, b in zip(left, right):
        a, b = np.asarray(a), np.asarray(b)
        assert a.dtype == b.dtype and a.shape == b.shape
        assert np.array_equal(a, b, equal_nan=True)
        # Bitwise, so signed zeros and NaN payloads also agree.
        assert a.tobytes() == b.tobytes()


def _runs(rng, cells, distinct):
    """Per-cell gains drawn from `distinct` matrices in runs, as the grid does."""
    pool = rng.normal(size=(distinct, 2, 2)) + 1j * rng.normal(size=(distinct, 2, 2))
    lengths = rng.integers(1, 40, size=cells)
    index = np.repeat(np.arange(cells) % distinct, lengths)[:cells]
    return pool, index


def _cases(rng, cells):
    pool, ip = _runs(rng, cells, 7)
    _, iq = _runs(rng, cells, 5)
    pool[1] = [[1, 2], [2, 4]]  # singular
    pool[2] = [[1, 0], [0, 1e-9]]  # condition 1e9 > limit
    pool[3] = [[1, 0], [0, -0.0]]  # singular, signed zero
    pool[4] = [[np.nan, 0], [0, 1]]  # non-finite
    gp, gq = pool[ip], pool[iq]
    data = rng.normal(size=(cells, 4)) + 1j * rng.normal(size=(cells, 4))
    weights = rng.uniform(0.1, 2, size=(cells, 4))
    valid = rng.random(cells) < 0.9
    weights[rng.random(cells) < 0.05, 0] = 0
    return data, gp, gq, valid, weights


@pytest.mark.parametrize("seed", range(4))
def test_corrected_intensity_matches_frozen(seed):
    rng = np.random.default_rng(seed)
    data, gp, gq, valid, weights = _cases(rng, 500)
    # The shapes `response._correct` passes: (cells, 1, ...).
    args = (data[:, None], gp[:, None], gq[:, None], valid[:, None], weights[:, None])
    _same(core_signal.corrected_intensity(*args), frozen_corrected(*args))
    # Two-dimensional (row, channel) shape, as `flagging_signal` passes.
    args = (
        data.reshape(25, 20, 4),
        gp.reshape(25, 20, 2, 2),
        gq.reshape(25, 20, 2, 2),
        valid.reshape(25, 20),
        weights.reshape(25, 20, 4),
    )
    _same(core_signal.corrected_intensity(*args), frozen_corrected(*args))


def test_corrected_intensity_edges():
    rng = np.random.default_rng(9)
    data, gp, gq, valid, weights = _cases(rng, 60)
    for mask in (np.zeros_like(valid), np.ones_like(valid)):
        args = (
            data[:, None],
            gp[:, None],
            gq[:, None],
            mask[:, None],
            weights[:, None],
        )
        _same(core_signal.corrected_intensity(*args), frozen_corrected(*args))
    for n in (0, 1):
        args = (
            data[:n, None],
            gp[:n, None],
            gq[:n, None],
            valid[:n, None],
            weights[:n, None],
        )
        _same(core_signal.corrected_intensity(*args), frozen_corrected(*args))
    with pytest.raises(ValueError, match="four correlations"):
        core_signal.corrected_intensity(data, gp, gq, valid, weights[:, :3])


def test_inverse_tangent_matches_frozen():
    rng = np.random.default_rng(4)
    pool, ip = _runs(rng, 400, 6)
    _, iq = _runs(rng, 400, 3)
    tangent = rng.normal(size=(400, 2, 2)) + 1j * rng.normal(size=(400, 2, 2))
    data = rng.normal(size=(400, 4)) + 1j * rng.normal(size=(400, 4))
    injected = rng.normal(size=(400, 4)) + 1j * rng.normal(size=(400, 4))
    weights = rng.uniform(0.5, 1, size=(400, 4))
    args = (data, injected, pool[ip], pool[iq], tangent, tangent[::-1], weights)
    _same(core_signal.inverse_tangent(*args), frozen_tangent(*args))
    pool[2] = [[1, 0], [0, 1e-9]]
    args = (data, injected, pool[ip], pool[iq], tangent, tangent, weights)
    for function in (core_signal.inverse_tangent, frozen_tangent):
        with pytest.raises(ValueError, match="exceeds1e8"):
            function(*args)


def test_per_run_is_one_call_per_run():
    rng = np.random.default_rng(1)
    pool, index = _runs(rng, 300, 4)
    matrices = pool[index]
    calls = []

    def counted(x):
        calls.append(len(x))
        return np.linalg.inv(x)

    assert np.array_equal(
        core_signal._per_run(counted, matrices), np.linalg.inv(matrices)
    )
    assert calls == [1 + int(np.count_nonzero(index[1:] != index[:-1]))]
    assert (
        np.linalg.cond(np.empty((0, 2, 2))).shape
        == core_signal._cond(np.empty((0, 2, 2))).shape
    )


def _normalised(function, renames):
    """Function source with docstring, name and the allowed substitutions removed."""
    tree = ast.parse(inspect.getsource(function))
    node = tree.body[0]
    node.name = "f"
    if isinstance(node.body[0], ast.Expr) and isinstance(
        node.body[0].value, ast.Constant
    ):
        node.body = node.body[1:]
    text = ast.unparse(tree)
    for old, new in renames:
        text = text.replace(old, new)
    return text


@pytest.mark.parametrize(
    ("ported", "frozen"),
    [
        (core_signal.corrected_intensity, frozen_corrected),
        (core_signal.inverse_tangent, frozen_tangent),
        (core_signal.train_signal_guard_p6, frozen_guard),
    ],
)
def test_ports_are_verbatim_except_cond_and_inv(ported, frozen):
    renames = (("np.linalg.cond(", "_cond("), ("np.linalg.inv(", "_inv("))
    assert _normalised(ported, ()) == _normalised(frozen, renames)
    assert "np.linalg" not in _normalised(ported, ())


def test_switch_is_opt_in_and_restores(monkeypatch):
    monkeypatch.delenv("RANG_P6", raising=False)
    assert not core_signal.enabled()
    monkeypatch.setenv("RANG_P6", "1")
    assert core_signal.enabled()
    frozen_candidates = prospective.generate_candidates
    with core_signal.ported_signal():
        assert response.corrected_intensity is core_signal.corrected_intensity
        assert prospective.generate_candidates is core_trend.generate_candidates
    assert response.corrected_intensity is frozen_corrected
    assert prospective.generate_candidates is frozen_candidates
    assert os.environ["RANG_P6"] == "1"
