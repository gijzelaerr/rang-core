import numpy as np
import pytest
from rangtoy import core
from rangtoy.flagging import residual_features
from rangtoy.flagging_influence import training_normals


def _case(seed=3, nchan=6):
    rng = np.random.default_rng(seed)
    pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    times = np.repeat([0.0, 1.0, 2.0, 3.0], len(pairs))
    p = np.tile([a for a, _ in pairs], 4).astype(np.int32)
    q = np.tile([b for _, b in pairs], 4).astype(np.int32)
    shape = (len(times), nchan, 4)
    complex_values = lambda: (
        rng.standard_normal(shape) + 1j * rng.standard_normal(shape)
    ).astype(np.complex64)
    data, model = complex_values(), complex_values()
    weights = rng.uniform(0.5, 2.0, shape).astype(np.float32)
    gains = np.eye(2) + 0.1 * (
        rng.standard_normal((2, 2, 4, 2, 2)) + 1j * rng.standard_normal((2, 2, 4, 2, 2))
    )
    valid = np.ones((2, 2, 4), bool)
    tb = (np.unique(times, return_inverse=True)[1] // 2).astype(np.uint32)
    fb = (np.arange(nchan) // (nchan // 2)).astype(np.uint32)
    split = rng.integers(0, 4, (len(times), nchan)).astype(np.uint8)
    return data, model, weights, p, q, tb, fb, gains, valid, split


def _reference_residuals(data, model, p, q, tb, fb, gains):
    gp = gains[tb[:, None], fb[None], p[:, None]]
    gq = gains[tb[:, None], fb[None], q[:, None]]
    m = model.reshape(*model.shape[:2], 2, 2)
    return data - (gp @ m @ gq.conj().swapaxes(-1, -2)).reshape(data.shape)


def test_residuals_losses_and_scores_match_numpy():
    data, model, weights, p, q, tb, fb, gains, valid, split = _case()
    result = core.fused_pass(
        data, weights, p, q, tb, fb, gains, valid, split, model=model
    )
    reference = _reference_residuals(data, model, p, q, tb, fb, gains)
    np.testing.assert_allclose(result.residuals, reference, rtol=0, atol=1e-12)
    mse = np.mean(np.abs(reference) ** 2 * weights, axis=-1)
    for code, name in enumerate(core.SPLITS, start=1):
        np.testing.assert_allclose(
            result.losses()[name], np.mean(mse[split == code]), rtol=1e-12
        )
    z = residual_features(reference * np.sqrt(weights), split == 1, p, q)
    np.testing.assert_allclose(result.scores, z, rtol=0, atol=1e-12)


def test_scalar_model_equals_stored_scalar_model():
    data, _, weights, p, q, tb, fb, gains, valid, split = _case(nchan=4)
    flux = np.array([1.5, 2.0, 2.5, 3.0])
    stored = np.zeros(data.shape, np.complex64)
    stored[..., 0] = stored[..., 3] = flux
    a = core.fused_pass(
        data, weights, p, q, tb, fb, gains, valid, split, scalar_model=flux
    )
    b = core.fused_pass(data, weights, p, q, tb, fb, gains, valid, split, model=stored)
    np.testing.assert_array_equal(a.residuals, b.residuals)


def test_diagonal_blocks_match_full_training_normals():
    data, model, weights, p, q, tb, fb, gains, valid, split = _case(seed=5)
    result = core.fused_pass(
        data, weights, p, q, tb, fb, gains, valid, split, model=model
    )
    rows, chans = np.nonzero(split == 1)
    nf = gains.shape[1]
    h, b, _ = training_normals(
        gains.reshape(-1, 4, 2, 2),
        model[rows, chans].astype(np.complex128).reshape(-1, 2, 2),
        result.residuals[rows, chans].reshape(-1, 2, 2),
        weights[rows, chans].astype(np.float64),
        p[rows],
        q[rows],
        tb[rows] * nf + fb[chans],
    )
    diag_h = result.diag_h.reshape(-1, 4, 8, 8)
    diag_b = result.diag_b.reshape(-1, 4, 8)
    for a in range(4):
        np.testing.assert_allclose(
            diag_h[:, a], h[:, 8 * a : 8 * a + 8, 8 * a : 8 * a + 8], rtol=0, atol=1e-12
        )
        np.testing.assert_allclose(
            diag_b[:, a], b[:, 8 * a : 8 * a + 8], rtol=0, atol=1e-12
        )


def test_invalid_gain_makes_split_loss_unavailable():
    data, model, weights, p, q, tb, fb, gains, valid, split = _case()
    valid = valid.copy()
    valid[0, 0, 1] = False
    result = core.fused_pass(
        data, weights, p, q, tb, fb, gains, valid, split, model=model
    )
    affected = (tb[:, None] == 0) & (fb[None] == 0) & ((p == 1) | (q == 1))[:, None]
    for code, name in enumerate(core.SPLITS, start=1):
        expected = int(np.count_nonzero(affected & (split == code)))
        assert result.invalid_predictions()[name] == expected
        if expected:
            assert result.losses()[name] is None


def test_rejects_ambiguous_model_and_bad_shapes():
    data, model, weights, p, q, tb, fb, gains, valid, split = _case()
    with pytest.raises(ValueError):
        core.fused_pass(data, weights, p, q, tb, fb, gains, valid, split)
    with pytest.raises(ValueError):
        core.fused_pass(
            data, weights[:, :1], p, q, tb, fb, gains, valid, split, model=model
        )
    with pytest.raises(ValueError):
        core.split_labels(train=split == 1, test=split >= 1)
