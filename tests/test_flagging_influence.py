import numpy as np
import pytest
from rangtoy.flagging_influence import (
    DERIVED_LIMIT_BYTES,
    RESERVE_BYTES,
    _capacity,
    _training_bundle,
    anchored_response,
    jones_jacobian,
    training_normals,
)


def test_polarized_model_refuses_wrong_common_u2_gauge():
    args = list(problem())
    args[1][:, 1, 1] *= 2
    h, b, _ = training_normals(*args)
    r = anchored_response(
        h[0], b[0], np.zeros((32, 32)), np.zeros(32), args[0][0], np.ones(4, bool)
    )
    assert r["native_status"] == 6 and not r["guard_pass"]


def test_inactive_station_is_removed_not_counted_as_global_rank_failure():
    args = problem()
    gains, models, residuals, weights, p, q, bins = args
    keep = (p < 3) & (q < 3)
    h, b, _ = training_normals(
        gains,
        models[keep],
        residuals[keep],
        weights[keep],
        p[keep],
        q[keep],
        bins[keep],
    )
    local = gains[0].copy()
    local[3] = np.nan
    r = anchored_response(
        h[0],
        b[0],
        np.zeros((32, 32)),
        np.zeros(32),
        local,
        np.array([1, 1, 1, 0], bool),
    )
    assert r["guard_pass"] and r["diagnostics"]["full_rank"] == 20
    assert np.all(r["delta"][3] == 0)


def test_resource_ceiling_and_disk_reserve_checked_before_derived_write(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    import rangtoy.flagging_influence as influence

    monkeypatch.setattr(
        influence.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=RESERVE_BYTES - 1),
    )
    with pytest.raises(RuntimeError, match="reserve"):
        _capacity(tmp_path, 1)
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(
        influence.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=RESERVE_BYTES * 2),
    )
    with pytest.raises(RuntimeError, match="256MiB"):
        _capacity(tmp_path, DERIVED_LIMIT_BYTES)
    assert not list(tmp_path.iterdir())


def real_vector(x):
    return np.asarray(x, dtype=np.complex128).ravel().view(float)


def problem(seed=29):
    rng = np.random.default_rng(seed)
    gains = np.tile(np.eye(2, dtype=complex), (1, 4, 1, 1))
    gains += 0.03 * (rng.normal(size=gains.shape) + 1j * rng.normal(size=gains.shape))
    pairs = [(p, q) for p in range(4) for q in range(p + 1, 4)]
    p, q = np.repeat(np.array(pairs), 4, axis=0).T
    model = np.tile((1 + 0.3j) * np.eye(2), (len(p), 1, 1))
    residual = 0.005 * (
        rng.normal(size=model.shape) + 1j * rng.normal(size=model.shape)
    )
    weights = rng.uniform(0.7, 2.0, size=(len(p), 4))
    return gains, model, residual, weights, p, q, np.zeros(len(p), int)


def gauge_projection(gains):
    generators = [
        np.diag([1j, 0]),
        np.diag([0, 1j]),
        np.array([[0, 1], [-1, 0]]),
        np.array([[0, 1j], [1j, 0]]),
    ]
    vertical = np.column_stack([real_vector(gains @ a) for a in generators])
    q = np.linalg.svd(vertical, full_matrices=False)[0]
    return np.eye(32) - q @ q.T


def reference_step(h, b, dh, db, gains):
    p = gauge_projection(gains)
    h, kept = p @ h @ p, p @ (h - dh) @ p
    largest = np.linalg.eigvalsh(h)[-1]

    def solve(a, rhs):
        values, vectors = np.linalg.eigh(a)
        valid = values > 1e-10 * largest
        return vectors[:, valid] @ (
            (vectors[:, valid].T @ (p @ rhs)) / (values[valid] + 1e-6 * largest)
        )

    return solve(kept, b - db) - solve(h, b)


def test_exact_general_model_jacobian_finite_differences():
    rng = np.random.default_rng(11)
    gp, gq, m = [
        rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2)) for _ in range(3)
    ]
    analytic = jones_jacobian(gp, gq, m)
    numerical = np.empty_like(analytic)
    for column in range(16):
        basis = np.zeros((2, 2), complex)
        basis.flat[(column % 8) // 2] = 1 if column % 2 == 0 else 1j
        delta = 1e-7 * basis
        plus = (
            (gp + delta) @ m @ gq.conj().T
            if column < 8
            else gp @ m @ (gq + delta).conj().T
        )
        minus = (
            (gp - delta) @ m @ gq.conj().T
            if column < 8
            else gp @ m @ (gq - delta).conj().T
        )
        numerical[:, column] = real_vector((plus - minus) / 2e-7)
    np.testing.assert_allclose(analytic, numerical, rtol=2e-7, atol=2e-8)
    identity = jones_jacobian(np.eye(2), np.eye(2), np.eye(2))
    assert identity[1, 1] == 1 and identity[1, 9] == -1


def test_native_normals_match_explicit_weighted_real_jacobian():
    args = problem()
    h, b, counts = training_normals(*args)
    gains, models, residuals, weights, p, q, _ = args
    eh, eb = np.zeros((32, 32)), np.zeros(32)
    for model, residual, weight, antenna_p, antenna_q in zip(
        models, residuals, weights, p, q, strict=True
    ):
        local = jones_jacobian(gains[0, antenna_p], gains[0, antenna_q], model)
        j = np.zeros((8, 32))
        j[:, antenna_p * 8 : (antenna_p + 1) * 8] = local[:, :8]
        j[:, antenna_q * 8 : (antenna_q + 1) * 8] = local[:, 8:]
        w = np.repeat(weight, 2)
        eh += j.T @ (w[:, None] * j)
        eb += j.T @ (w * real_vector(residual))
    np.testing.assert_allclose(h[0], eh, rtol=2e-13, atol=2e-13)
    np.testing.assert_allclose(b[0], eb, rtol=2e-13, atol=2e-13)
    assert counts.tolist() == [24]


def test_projected_anchored_response_matches_numpy_eigen_reference():
    args = problem()
    h, b, _ = training_normals(*args)
    gains, *samples = args
    dh, db, _ = training_normals(gains, *[x[:4] for x in samples])
    response = anchored_response(h[0], b[0], dh[0], db[0], gains[0], np.ones(4, bool))
    assert response["guard_pass"]
    assert (
        response["diagnostics"]["full_rank"]
        == response["diagnostics"]["retained_rank"]
        == 28
    )
    expected = reference_step(h[0], b[0], dh[0], db[0], gains[0])
    np.testing.assert_allclose(
        real_vector(response["delta"]), expected, rtol=2e-10, atol=1e-12
    )
    p = gauge_projection(gains[0])
    np.testing.assert_allclose(
        p @ real_vector(response["delta"]), real_vector(response["delta"]), atol=1e-12
    )


def test_no_deletion_has_exact_zero_response_despite_baseline_gradient():
    args = problem()
    h, b, _ = training_normals(*args)
    assert np.linalg.norm(b) > 0
    r = anchored_response(
        h[0], b[0], np.zeros((32, 32)), np.zeros(32), args[0][0], np.ones(4, bool)
    )
    assert r["guard_pass"] and np.all(r["delta"] == 0)


def test_two_station_extra_gl_ambiguity_and_retained_rank_loss_abstain():
    args = problem()
    gains, *samples = args
    h, b, _ = training_normals(gains, *[x[:4] for x in samples])
    r = anchored_response(
        h[0],
        b[0],
        np.zeros((32, 32)),
        np.zeros(32),
        gains[0],
        np.array([1, 1, 0, 0], bool),
    )
    assert not r["guard_pass"] and r["delta"] is None and r["native_status"] == 3
    h, b, _ = training_normals(*args)
    r = anchored_response(h[0], b[0], h[0], b[0], gains[0], np.ones(4, bool))
    assert not r["guard_pass"] and r["native_status"] == 4


def test_large_station_update_abstains_instead_of_clipping():
    args = list(problem())
    args[2] *= 1000
    h, b, _ = training_normals(*args)
    gains, *samples = args
    dh, db, _ = training_normals(gains, *[x[:4] for x in samples])
    r = anchored_response(h[0], b[0], dh[0], db[0], gains[0], np.ones(4, bool))
    assert not r["guard_pass"] and r["delta"] is None
    assert r["diagnostics"]["max_relative_step"] > 0.1


def test_response_is_equivariant_under_left_diagonal_receiver_phase():
    args = problem()
    gains, models, residuals, weights, p, q, bins = args
    d = np.array(
        [np.diag(np.exp(1j * np.array([a * 0.1, -a * 0.2]))) for a in range(4)]
    )
    transformed_gains = (d @ gains[0])[None]
    transformed_residual = d[p] @ residuals @ d[q].conj().swapaxes(-1, -2)
    h, b, _ = training_normals(*args)
    dh, db, _ = training_normals(
        gains, models[:4], residuals[:4], weights[:4], p[:4], q[:4], bins[:4]
    )
    original = anchored_response(h[0], b[0], dh[0], db[0], gains[0], np.ones(4, bool))
    transformed = (transformed_gains, models, transformed_residual, weights, p, q, bins)
    h, b, _ = training_normals(*transformed)
    dh, db, _ = training_normals(
        transformed_gains,
        models[:4],
        transformed_residual[:4],
        weights[:4],
        p[:4],
        q[:4],
        bins[:4],
    )
    response = anchored_response(
        h[0], b[0], dh[0], db[0], transformed_gains[0], np.ones(4, bool)
    )
    assert original["guard_pass"] and response["guard_pass"]
    np.testing.assert_allclose(
        response["delta"], d @ original["delta"], rtol=3e-10, atol=1e-12
    )


@pytest.mark.parametrize("kind", ["zero-weight", "float-indices", "autocorrelation"])
def test_malformed_native_weight_or_sample_domain_rejected(kind):
    args = list(problem())
    if kind == "zero-weight":
        args[3][0, 1] = 0
    elif kind == "float-indices":
        args[4] = args[4].astype(float)
    else:
        args[5][0] = args[4][0]
    with pytest.raises(ValueError):
        training_normals(*args)


def test_training_curvature_ignores_heldout_data_and_rejects_protected_overlap():
    shape = (6, 32)
    gains = np.tile(np.eye(2, dtype=complex), (1, 1, 4, 1, 1))
    train = np.zeros(shape, bool)
    train[:, :16] = True
    state = {
        "times": np.zeros(6),
        "frequencies": np.arange(32),
        "antenna1": np.array([0, 0, 0, 1, 1, 2]),
        "antenna2": np.array([1, 2, 3, 2, 3, 3]),
        "data": np.ones((*shape, 4), complex),
        "model": np.tile(np.eye(2).reshape(4), (*shape, 1)),
        "weights": np.ones((*shape, 4)),
        "train": train,
        "validation": ~train,
        "test": np.zeros(shape, bool),
        "original_flags": np.zeros((*shape, 4), bool),
        "original_rows": np.zeros(6, bool),
        "window": np.ones(32, bool),
    }
    baseline = {"gains": gains, "gain_valid": np.ones((1, 1, 4), bool)}
    before = _training_bundle(state, baseline)
    state["data"][~train] = 1e30 + 1e30j
    after = _training_bundle(state, baseline)
    assert all(np.array_equal(before[k], after[k]) for k in before)
    state["original_rows"][0] = True
    with pytest.raises(ValueError):
        _training_bundle(state, baseline)
