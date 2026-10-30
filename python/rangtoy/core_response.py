"""Frozen signed-source/sky-completeness/full-Jones gain-flexibility controls.

Verbatim extract of the frozen `rangtoy.flagging_response` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_response.py at commit
2da566c (now history/python/flagging_response.py),
sha256 b62a9877af099d9c72875b8439818b033e8fdff22d5b931386f327dbfed5fac8.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import json
import shutil
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from .core_templates import (
    REFERENCE_HZ,  # noqa: F401 (re-export)
    corrected_intensity,
)

SOURCES = (
    {
        "name": "compact",
        "flux_jy": 0.06,
        "l_arcmin": 9.0,
        "m_arcmin": -6.0,
        "fwhm_arcmin": 0.0,
        "spectral_index": -0.5,
    },
    {
        "name": "extended",
        "flux_jy": 0.12,
        "l_arcmin": -12.0,
        "m_arcmin": -14.0,
        "fwhm_arcmin": 8.0,
        "spectral_index": -0.9,
    },
)


GRIDS = ((2, 32), (14, 128))


SKIES = ("omitted", "complete-diagnostic")


ALLOCATION_BYTES = 3 * 1024**3 // 2


RESERVE_BYTES = 8 * 1024**3


CONDITION_LIMIT = 1e8


def _json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def allocated_bytes(path):
    """Actual allocated filesystem blocks, not a compressed-size forecast."""
    path = Path(path)
    if not path.exists():
        return 0
    total = 0
    for item in (path, *path.rglob("*")):
        if item.is_symlink():
            raise ValueError("symlinks are not allowed in a response output tree")
        stat = item.stat()
        total += getattr(stat, "st_blocks", (stat.st_size + 511) // 512) * 512
    return total


def copy_bound(path):
    """Conservative copy storage including filesystem-block/metadata overhead."""
    path = Path(path)
    total = 0
    for item in (path, *path.rglob("*")) if path.is_dir() else (path,):
        if item.is_symlink():
            raise ValueError("source-copy symlinks are not allowed")
        total += ((item.stat().st_size + 4095) // 4096 + 4) * 4096
    return total


class Budget:
    """Checked allocation budget, NOT an OS-enforced filesystem quota.

    Every local write/copy has a conservative reservation. Shared solve() and
    its native QC writes are a single pre-reserved batch, checked afterwards.
    A breach stops further work; existing/failed artifacts are never erased.
    """

    def __init__(self, root):
        self.root = Path(root).resolve()

    def check(self, needed=0):
        used = allocated_bytes(self.root)
        if needed < 0 or used + needed > ALLOCATION_BYTES:
            raise ValueError("response1.5GiB checked allocation budget exceeded")
        ancestor = self.root
        while not ancestor.exists():
            ancestor = ancestor.parent
        if shutil.disk_usage(ancestor).free < RESERVE_BYTES + needed:
            raise ValueError("response operation would violate8GiB disk reserve")
        return used

    @contextmanager
    def operation(self, needed, label):
        before = self.check(needed)
        yield
        after = self.check()
        if after - before > needed:
            raise ValueError(f"{label} exceeded its reserved allocation; stop work")

    def _target(self, path):
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError("response writes must remain in the exclusive run tree")
        return path

    def mkdir(self, path):
        path = self._target(path)
        with self.operation(64 * 1024, "directory creation"):
            path.mkdir(parents=True, exist_ok=False)

    def copy(self, source, target):
        target = self._target(target)
        with self.operation(copy_bound(source), "copy/backup"):
            if Path(source).is_dir():
                shutil.copytree(source, target)
            else:
                if target.exists():
                    raise ValueError("backup/copy target must be exclusive")
                shutil.copy2(source, target)

    def json(self, path, value):
        path = self._target(path)
        payload = (
            json.dumps(value, indent=2, allow_nan=False, default=_json_default) + "\n"
        )
        with (
            self.operation(len(payload.encode()) + 64 * 1024, "JSON checkpoint"),
            path.open("x") as stream,
        ):
            stream.write(payload)

    def npz(self, path, *, replace_backed_up=False, **arrays):
        path = self._target(path)
        # ZIP/header/DEFLATE expansion, plus filesystem metadata, is reserved.
        needed = int(sum(np.asarray(a).nbytes for a in arrays.values()) * 1.01)
        needed += (len(arrays) + 8) * 8192
        with (
            self.operation(needed, "array checkpoint"),
            path.open("wb" if replace_backed_up else "xb") as stream,
        ):
            np.savez_compressed(stream, **arrays)


def linear_response(intensity, templates, weights, mask):
    """Evaluation-only real coefficients for frozen unit-Jy spectral templates.

    No positivity/bounds, sample rejection, slope fitting, confidence intervals
    or truth-dependent ranking. Rank-deficient flux estimates are unavailable.
    """
    intensity, templates = np.asarray(intensity), np.asarray(templates)
    weights, mask = np.asarray(weights, float), np.asarray(mask)
    if (
        mask.dtype != np.bool_
        or mask.shape != intensity.shape
        or weights.shape != intensity.shape
        or templates.ndim != intensity.ndim + 1
        or templates.shape[1:] != intensity.shape
        or not len(templates)
        or mask.sum() < len(templates)
    ):
        raise ValueError(
            "matched templates/intensity/weights and nonempty bool support"
        )
    if (
        not np.isfinite(intensity[mask]).all()
        or not np.isfinite(templates[:, mask]).all()
        or not np.isfinite(weights[mask]).all()
        or (weights[mask] <= 0).any()
    ):
        raise ValueError("invalid evaluation samples must not be silently discarded")
    design = templates[:, mask].T * np.sqrt(weights[mask, None])
    target = intensity[mask] * np.sqrt(weights[mask])
    matrix = np.concatenate((design.real, design.imag), axis=0)
    vector = np.r_[target.real, target.imag]
    flux, _, rank, singular = np.linalg.lstsq(matrix, vector, rcond=1e-10)
    condition = (
        float(singular[0] / singular[-1])
        if singular.size and singular[-1] > 0
        else None
    )
    available = bool(
        rank == len(templates)
        and condition is not None
        and condition <= CONDITION_LIMIT
    )
    residual = vector - matrix @ flux
    norm = float(vector @ vector)
    return {
        "available": available,
        "rank": int(rank),
        "condition": condition,
        "sample_count": int(mask.sum()),
        "flux_jy": flux.tolist() if available else [None] * len(templates),
        "weighted_mse_proxy": float(residual @ residual / mask.sum()),
        "unexplained_weighted_response_energy_fraction": float(
            residual @ residual / norm
        )
        if norm > 0
        else None,
        "spectral_indices": "fixed evaluation family; not fitted",
        "positivity_or_parameter_bounds": False,
        "confidence_intervals": "not claimed; shared noisy DATA and estimated gains",
    }


def _jones_samples(state, diagnostics, grid, row, channel):
    ti, fi = grid
    time = np.unique(state["times"], return_inverse=True)[1][row] // ti
    frequency = channel // fi
    p, q = state["antenna1"][row], state["antenna2"][row]
    gains, valid = diagnostics["gains"], diagnostics["gain_valid"]
    return (
        gains[time, frequency, p],
        gains[time, frequency, q],
        valid[time, frequency, p] & valid[time, frequency, q],
    )


def _correct(data, weights, jones):
    gp, gq, good = jones
    values = corrected_intensity(
        data[:, None], gp[:, None], gq[:, None], good[:, None], weights[:, None]
    )
    return tuple(value[:, 0] for value in values)


def _product_distance(jones, reference, weights, mask):
    gp, gq, _ = jones
    rp, rq, _ = reference
    operator = gp[mask] @ gq[mask].conj().swapaxes(-1, -2)
    target = rp[mask] @ rq[mask].conj().swapaxes(-1, -2)
    error = np.sum(np.abs(operator - target) ** 2, axis=(-1, -2))
    norm = np.sum(np.abs(target) ** 2, axis=(-1, -2))
    denominator = float(np.sum(weights[mask] * norm))
    return (
        float(np.sqrt(np.sum(weights[mask] * error) / denominator))
        if denominator > 0
        else None
    )
