"""Independent SVD checks of the Rust QR projection and its FFI boundary."""

import numpy as np
import pytest
from rang.projector import project_grouped, project_out


@pytest.mark.parametrize(
    "rows,columns,rank", [(30, 8, 8), (30, 8, 5), (10, 12, 10), (10, 0, 0)]
)
def test_projector_matches_svd(rows, columns, rank):
    rng = np.random.default_rng(19)
    a = rng.normal(size=(rows, rank)) @ rng.normal(size=(rank, columns))
    z = rng.normal(size=(rows, 4))
    actual, found = project_out(a, z)
    expected = z - a @ np.linalg.lstsq(a, z, rcond=1e-12)[0]
    assert found == rank
    assert actual.shape == (rows - rank, 4)
    np.testing.assert_allclose(actual.T @ actual, expected.T @ expected, atol=1e-11)


def test_projector_noncontiguous_inputs_and_invalid_arguments():
    a = np.arange(80.0).reshape(10, 8)[:, ::2]
    z = np.eye(10)[:, ::3]
    p, _ = project_out(a, z)
    expected = z - a @ np.linalg.lstsq(a, z, rcond=1e-12)[0]
    np.testing.assert_allclose(p.T @ p, expected.T @ expected, atol=1e-12)
    with pytest.raises(ValueError, match="real"):
        project_out(a.astype(complex), z)
    with pytest.raises(ValueError, match="dimensions"):
        project_out(a, z[:-1])
    with pytest.raises(ValueError, match="finite"):
        project_out(a, z, relative_tolerance=np.nan)


def test_projector_drops_small_rank_and_preserves_gauge_null():
    a = np.diag([1.0, 0.1, 1e-15])
    p, rank = project_out(a, np.eye(3), relative_tolerance=1e-12)
    assert rank == 2
    np.testing.assert_allclose(p.T @ p, np.diag([0.0, 0.0, 1.0]), atol=1e-14)
    rng = np.random.default_rng(71)
    a = rng.normal(size=(64, 12))
    z = a @ rng.normal(size=(12, 2))
    p, rank = project_out(a, z)
    assert rank == 12
    assert np.linalg.norm(p) < 1e-12


@pytest.mark.parametrize("scale", [1e-150, 1.0, 1e150])
def test_projector_common_rescaling_preserves_information(scale):
    rng = np.random.default_rng(23)
    a, target = rng.normal(size=(37, 9)), rng.normal(size=(37, 3))
    expected = target - a @ np.linalg.lstsq(a, target, rcond=1e-12)[0]
    actual, rank = project_out(a * scale, target)
    assert rank == 9
    np.testing.assert_allclose(actual.T @ actual, expected.T @ expected, atol=1e-12)


@pytest.mark.parametrize("backend", ["rust", "numpy"])
def test_grouped_matches_full_nuisance_projection(backend):
    rng = np.random.default_rng(31)
    groups = np.repeat([0, 1, 2], 20)
    gains, shared, target = (rng.normal(size=(60, n)) for n in (5, 7, 3))
    expanded = np.column_stack(
        [gains * (groups == g)[:, None] for g in range(3)] + [shared]
    )
    expected = target - expanded @ np.linalg.lstsq(expanded, target, rcond=1e-12)[0]
    actual, rank = project_grouped(gains, shared, target, groups, backend=backend)
    assert rank == 22
    np.testing.assert_allclose(actual.T @ actual, expected.T @ expected, atol=1e-11)
    empty, rank = project_grouped(
        np.eye(6),
        np.ones((6, 1)),
        np.ones((6, 2)),
        np.zeros(6, dtype=int),
        backend=backend,
    )
    assert rank == 6
    assert empty.shape == (0, 2)


@pytest.mark.parametrize("backend", ["rust", "numpy"])
def test_grouped_does_not_promote_eliminated_shared_columns(backend):
    rng = np.random.default_rng(1)
    groups = np.repeat([0, 1, 2], 20)
    gains = rng.normal(size=(60, 5))
    shared = gains[:, :2]
    target = rng.normal(size=(60, 3))
    expanded = np.column_stack([gains * (groups == g)[:, None] for g in range(3)])
    expected = target - expanded @ np.linalg.lstsq(expanded, target, rcond=1e-12)[0]
    actual, rank = project_grouped(gains, shared, target, groups, backend=backend)
    assert rank == 15
    np.testing.assert_allclose(actual.T @ actual, expected.T @ expected, atol=1e-11)


@pytest.mark.parametrize("backend", ["rust", "numpy"])
def test_grouped_without_shared_columns(backend):
    rng = np.random.default_rng(29)
    gains, target = rng.normal(size=(25, 3)), rng.normal(size=(25, 2))
    expected = target - gains @ np.linalg.lstsq(gains, target, rcond=1e-12)[0]
    actual, rank = project_grouped(
        gains, np.empty((25, 0)), target, np.zeros(25, int), backend=backend
    )
    assert rank == 3
    np.testing.assert_allclose(actual.T @ actual, expected.T @ expected, atol=1e-12)
