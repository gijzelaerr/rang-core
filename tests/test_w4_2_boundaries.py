"""Task W4-2 (research/w4-2-boundaries.md): every binding of `rang._core`
checks its arrays' lengths, C order and size products, and refuses a
mismatch with a ValueError naming the argument (review finding W4R-04; the
repro is outputs/w4-review-20261031-02/r01_ffi_bounds.py)."""

import numpy as np
import pytest
from rang import core


@pytest.fixture(scope="module")
def ext():
    return core.extension()


def _fused(ext, split_stats):
    nrow, nchan, nt, nf, na = 1, 1, 1, 1, 2
    gains = np.zeros(8 * na)
    gains[0::8] = gains[6::8] = 1.0
    return ext.fused(
        nrow, nchan, nt, nf, na,
        np.zeros(8, np.float32), np.ones(4, np.float32), None, np.ones(1),
        np.zeros(1, np.uint32), np.ones(1, np.uint32), np.zeros(1, np.uint32),
        np.zeros(1, np.uint32), gains, np.ones(na, np.uint8), np.ones(1, np.uint8),
        None, None, None, None, None, split_stats,
    )  # fmt: skip


def test_short_output_raises_instead_of_writing_past_it(ext):
    """r01 (a): a 1-element `split_stats` got 11 doubles written past it."""
    big = np.full(24, -1.0)
    with pytest.raises(ValueError, match="split_stats must hold 12 elements, not 1"):
        _fused(ext, big[:1])
    assert np.all(big == -1.0)
    assert _fused(ext, np.zeros(12)) == 0


def _predict(ext, uvw):
    nrow = uvw.shape[0]
    vis = np.empty(2 * nrow)
    status = ext.predict_components(
        nrow, 1, 1, 1, uvw, np.array([1.4e9]), np.array([[1e-3, 2e-3]]),
        np.zeros(1, np.uint8), np.ones(1), np.zeros((1, 1)), np.zeros(1, np.uint8),
        np.array([1.4e9]), np.zeros((1, 3)), vis, None,
    )  # fmt: skip
    return status, vis


def test_fortran_ordered_input_raises_instead_of_reading_transposed(ext):
    """r01 (b): a Fortran-ordered `uvw` was read transposed with status 0."""
    uvw = np.array([[100.0, 0.0, 0.0], [0.0, 300.0, 5.0]])
    assert _predict(ext, uvw)[0] == 0
    with pytest.raises(ValueError, match="uvw must be C-contiguous"):
        _predict(ext, np.asfortranarray(uvw))
    with pytest.raises(ValueError, match="array must be C-contiguous"):
        ext.data_address(np.asfortranarray(uvw))
    # One-dimensional views stay accepted when contiguous, refused when not.
    assert isinstance(ext.data_address(uvw[0]), int)
    with pytest.raises(ValueError):
        ext.data_address(uvw[:, 0])


def test_lengths_and_products_name_the_argument(ext):
    data, weights, flags = (np.zeros(8, np.float32), np.ones(4, np.float32),
                            np.zeros(4, np.uint8))  # fmt: skip
    vis, weight = np.zeros(2, np.float32), np.zeros(1, np.float32)
    assert ext.stokes_i(1, data, weights, flags, vis, weight) == 0
    with pytest.raises(ValueError, match="weights must hold 4 elements, not 3"):
        ext.stokes_i(1, data, weights[:3], flags, vis, weight)
    with pytest.raises(ValueError, match="vis must hold 2 elements"):
        ext.stokes_i(1, data, weights, flags, np.zeros(1, np.float32), weight)
    with pytest.raises(ValueError, match="overflows"):
        ext.stokes_i(2**62, data, weights, flags, vis, weight)
    with pytest.raises(ValueError, match="dirty must hold 64 elements"):
        ext.grid_invert(
            1, 1, 8, 8, 7, 63, 1, 1e-4, 1e-4, 1.2,
            np.zeros(3), np.array([1.4e9]), np.zeros(2, np.float32),
            np.ones(1, np.float32), np.ones(1, np.float32),
            np.zeros(63), np.zeros(64), np.zeros(8),
        )  # fmt: skip


def test_root_kernel_bindings_keep_status_one_but_refuse_fortran_order(ext):
    """P7's root-kernel bindings return 1 on a length mismatch (unchanged);
    a Fortran-ordered buffer is now a ValueError there too."""
    out = np.zeros(128)
    assert ext.response_jacobian(np.zeros(8), np.zeros(8), np.zeros(8), out) == 0
    assert ext.response_jacobian(np.zeros(7), np.zeros(8), np.zeros(8), out) == 1
    with pytest.raises(ValueError, match="C-contiguous"):
        ext.response_jacobian(
            np.zeros(8), np.zeros(8), np.zeros(8), np.asfortranarray(np.zeros((16, 8)))
        )
