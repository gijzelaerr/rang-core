"""Checked NumPy/ctypes boundary for the dependency-free Rust QR projector."""

import ctypes
import os
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import build


@lru_cache(maxsize=1)
def _native_library():
    configured = os.environ.get("RANG_TOY_LIB")
    if configured:
        path = Path(configured).resolve()
    else:
        filename = (
            "rang_toy.dll"
            if os.name == "nt"
            else "librang_toy.dylib"
            if sys.platform == "darwin"
            else "librang_toy.so"
        )
        path = build().parent / filename
    return ctypes.CDLL(str(path))


@lru_cache(maxsize=1)
def _native_projector():
    project = _native_library().rang_project_out
    vector = np.ctypeslib.ndpointer(
        dtype=np.float64, ndim=2, flags=("C_CONTIGUOUS", "ALIGNED")
    )
    project.argtypes = [
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
        vector,
        vector,
        vector,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_double,
    ]
    project.restype = ctypes.c_int
    return project


def project_out(nuisance, targets, *, relative_tolerance=1e-12):
    """Return rotated residual coordinates and nuisance rank.

    The returned (rows-rank, target_columns) matrix preserves the Gram matrix
    of targets projected orthogonally off the nuisance column space. It is
    not expressed in the original visibility-row coordinates. No data rows
    are statistically discarded: the removed rows span fitted nuisances.
    """
    if np.iscomplexobj(nuisance) or np.iscomplexobj(targets):
        raise ValueError("projector requires real matrices")
    a, z = (
        np.require(x, dtype=np.float64, requirements=["C", "A"])
        for x in (nuisance, targets)
    )
    if (
        a.ndim != 2
        or z.ndim != 2
        or a.shape[0] != z.shape[0]
        or z.shape[0] == 0
        or z.shape[1] == 0
    ):
        raise ValueError("incompatible nonempty matrix dimensions")
    if (
        not np.isfinite(a).all()
        or not np.isfinite(z).all()
        or not np.isfinite(relative_tolerance)
        or not 0 < relative_tolerance < 1
    ):
        raise ValueError("finite matrices and tolerance in (0,1) required")
    output = np.empty_like(z)
    rank = ctypes.c_size_t()
    status = _native_projector()(
        len(z),
        a.shape[1],
        z.shape[1],
        a,
        z,
        output,
        ctypes.byref(rank),
        relative_tolerance,
    )
    if status:
        raise RuntimeError(f"Rust nuisance projection failed (status {status})")
    return output[rank.value :], rank.value


def project_grouped(gains, shared_nuisance, targets, groups, *, backend="rust"):
    """Eliminate group-local gain columns, then nuisance shared across groups.

    Gains is one unmasked derivative matrix; each group's rows have independent
    gain parameters. Intermediate thin QR preserves all retained inner products.
    No cross-group prior on eliminated gains is permitted.
    Shared rank is measured against its original Frobenius norm, not against
    round-off left after gain elimination. Columns below 1e-12 of that scale
    are numerically redundant (a scale-dependent rank convention).
    """
    if any(np.iscomplexobj(x) for x in (gains, shared_nuisance, targets)):
        raise ValueError("projector requires real matrices")
    gains, shared, targets = (
        np.asarray(x, float) for x in (gains, shared_nuisance, targets)
    )
    groups = np.asarray(groups)
    if backend not in ("rust", "numpy"):
        raise ValueError("backend must be rust or numpy")
    if any(x.ndim != 2 for x in (gains, shared, targets)) or not (
        len(gains) == len(shared) == len(targets)
    ):
        raise ValueError("matrices must have matching row dimensions")
    if groups.shape != (len(targets),) or not len(targets) or targets.shape[1] == 0:
        raise ValueError("groups must label nonempty target rows")
    if not np.issubdtype(groups.dtype, np.integer) or any(
        not np.isfinite(x).all() for x in (gains, shared, targets)
    ):
        raise ValueError("finite matrices and integer group labels required")

    def project(a, z):
        if backend == "rust":
            return project_out(a, z)
        coefficients, _, rank, _ = np.linalg.lstsq(a, z, rcond=1e-12)
        if rank == len(a):
            return np.zeros((0, z.shape[1])), rank
        return z - a @ coefficients, rank

    retained = np.column_stack((shared, targets))
    blocks, total_rank = [], 0
    for group in np.unique(groups):
        mask = groups == group
        projected, rank = project(gains[mask], retained[mask])
        blocks.append(np.linalg.qr(projected, mode="r"))
        total_rank += int(rank)
    combined = np.concatenate(blocks)
    if len(combined) == 0:
        return np.zeros((0, targets.shape[1])), total_rank
    # A shared column can lie entirely in the eliminated gain space. Ranking
    # its tiny residual relative to itself would promote round-off to a new
    # nuisance and spuriously remove information from the targets.
    u, singular, _ = np.linalg.svd(combined[:, : shared.shape[1]], full_matrices=False)
    keep = singular > 1e-12 * np.linalg.norm(shared)
    projected, rank = project(u[:, keep], combined[:, shared.shape[1] :])
    return projected, total_rank + int(rank)
