"""Python interface to the Rang core (Rust, GPL-3.0-or-later).

Phase 1 exposes one fused pass over the visibility cells: prediction, residual,
per-split weighted residual sums, per-baseline robust scores and
antenna-diagonal Gauss--Newton blocks. See research/core-phase1.md. The library
is loaded through ctypes like the existing kernels; set RANG_CORE_LIB to use a
prebuilt library, otherwise it is built from core/ with Cargo, offline.
"""

import ctypes
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

SPLITS = ("train", "validation", "test")
SPLIT_CODES = {"train": 1, "validation": 2, "test": 3}


def _pointer(kind):
    return ctypes.POINTER(kind)


class _Inputs(ctypes.Structure):
    _fields_ = [
        ("nrow", ctypes.c_size_t),
        ("nchan", ctypes.c_size_t),
        ("ntime_bins", ctypes.c_size_t),
        ("nfreq_bins", ctypes.c_size_t),
        ("nant", ctypes.c_size_t),
        ("data", _pointer(ctypes.c_float)),
        ("weights", _pointer(ctypes.c_float)),
        ("model_stored", _pointer(ctypes.c_float)),
        ("model_scalar", _pointer(ctypes.c_double)),
        ("antenna1", _pointer(ctypes.c_uint32)),
        ("antenna2", _pointer(ctypes.c_uint32)),
        ("time_bin", _pointer(ctypes.c_uint32)),
        ("freq_bin", _pointer(ctypes.c_uint32)),
        ("gains", _pointer(ctypes.c_double)),
        ("gain_valid", _pointer(ctypes.c_uint8)),
        ("split", _pointer(ctypes.c_uint8)),
    ]


class _Outputs(ctypes.Structure):
    _fields_ = [
        ("residuals", _pointer(ctypes.c_double)),
        ("scores", _pointer(ctypes.c_double)),
        ("diag_h", _pointer(ctypes.c_double)),
        ("diag_b", _pointer(ctypes.c_double)),
        ("diag_count", _pointer(ctypes.c_uint64)),
        ("split_stats", _pointer(ctypes.c_double)),
    ]


def core_root():
    root = Path(__file__).resolve().parents[2] / "core"
    if not (root / "Cargo.toml").is_file():
        raise RuntimeError("Run from the Rang checkout or set RANG_CORE_LIB")
    return root


def build_core():
    """Build the core library in release mode without downloading crates."""
    root = core_root()
    manifest = str(root / "Cargo.toml")
    subprocess.run(
        ["cargo", "build", "--offline", "--release", "--manifest-path", manifest],
        cwd=root,
        check=True,
    )
    metadata = json.loads(
        subprocess.check_output(
            [
                "cargo",
                "metadata",
                "--offline",
                "--no-deps",
                "--format-version",
                "1",
                "--manifest-path",
                manifest,
            ],
            cwd=root,
            text=True,
        )
    )
    name = (
        "rang_core.dll"
        if os.name == "nt"
        else "librang_core.dylib"
        if sys.platform == "darwin"
        else "librang_core.so"
    )
    return Path(metadata["target_directory"]) / "release" / name


@lru_cache(maxsize=1)
def library():
    configured = os.environ.get("RANG_CORE_LIB")
    path = Path(configured).resolve() if configured else build_core()
    lib = ctypes.CDLL(str(path))
    lib.rang_core_fused.argtypes = [_pointer(_Inputs), _pointer(_Outputs)]
    lib.rang_core_fused.restype = ctypes.c_int
    return lib


def library_path():
    return Path(library()._name).resolve()


def _array(value, dtype, shape, label):
    array = np.require(value, dtype=dtype, requirements=["C", "A"])
    if array.shape != tuple(shape):
        raise ValueError(f"{label} must have shape {tuple(shape)}, not {array.shape}")
    return array


def _ptr(array, kind):
    return array.ctypes.data_as(_pointer(kind))


@dataclass
class FusedResult:
    """Products of one fused pass. Unrequested products are None."""

    residuals: np.ndarray | None
    scores: np.ndarray | None
    diag_h: np.ndarray | None
    diag_b: np.ndarray | None
    diag_count: np.ndarray | None
    split_stats: dict

    def losses(self):
        """Split losses as `flagging_workflow.solve` reports them."""
        return {
            name: (
                stats["sum"] / stats["cells"]
                if stats["cells"] and not stats["invalid"] and not stats["nonfinite"]
                else None
            )
            for name, stats in self.split_stats.items()
        }

    def invalid_predictions(self):
        return {name: stats["invalid"] for name, stats in self.split_stats.items()}


def split_labels(**masks):
    """Combine boolean train/validation/test masks into the core's labels."""
    labels = None
    for name, mask in masks.items():
        mask = np.asarray(mask, bool)
        if labels is None:
            labels = np.zeros(mask.shape, np.uint8)
        if np.any(labels[mask]):
            raise ValueError("splits overlap")
        labels[mask] = SPLIT_CODES[name]
    return labels


def fused_pass(
    data,
    weights,
    antenna1,
    antenna2,
    time_bin,
    freq_bin,
    gains,
    gain_valid,
    split,
    *,
    model=None,
    scalar_model=None,
    residuals=True,
    scores=True,
    normals=True,
):
    """Run the core's fused pass.

    data, model: (row, chan, 4) complex64; weights: (row, chan, 4) float32;
    gains: (time_bin, freq_bin, antenna, 2, 2) complex128 with gain_valid of the
    first three dimensions; split: (row, chan) labels 0 none, 1 train,
    2 validation, 3 test (see split_labels). Exactly one of model and
    scalar_model ((chan,) real fluxes) is given.
    """
    data = np.require(data, np.complex64, ["C", "A"])
    if data.ndim != 3 or data.shape[-1] != 4:
        raise ValueError("data must be (row, chan, 4) complex")
    nrow, nchan = data.shape[:2]
    gains = np.require(gains, np.complex128, ["C", "A"])
    if gains.ndim != 5 or gains.shape[-2:] != (2, 2):
        raise ValueError("gains must be (time_bin, freq_bin, antenna, 2, 2)")
    nt, nf, na = gains.shape[:3]
    weights = _array(weights, np.float32, (nrow, nchan, 4), "weights")
    a1 = _array(antenna1, np.uint32, (nrow,), "antenna1")
    a2 = _array(antenna2, np.uint32, (nrow,), "antenna2")
    tb = _array(time_bin, np.uint32, (nrow,), "time_bin")
    fb = _array(freq_bin, np.uint32, (nchan,), "freq_bin")
    valid = _array(np.asarray(gain_valid, bool), np.uint8, (nt, nf, na), "gain_valid")
    labels = _array(split, np.uint8, (nrow, nchan), "split")
    if (model is None) == (scalar_model is None):
        raise ValueError("give exactly one of model and scalar_model")
    inputs = _Inputs(
        nrow,
        nchan,
        nt,
        nf,
        na,
        _ptr(data, ctypes.c_float),
        _ptr(weights, ctypes.c_float),
        None,
        None,
        _ptr(a1, ctypes.c_uint32),
        _ptr(a2, ctypes.c_uint32),
        _ptr(tb, ctypes.c_uint32),
        _ptr(fb, ctypes.c_uint32),
        _ptr(gains, ctypes.c_double),
        _ptr(valid, ctypes.c_uint8),
        _ptr(labels, ctypes.c_uint8),
    )
    keep = []
    if model is not None:
        stored = _array(model, np.complex64, data.shape, "model")
        keep.append(stored)
        inputs.model_stored = _ptr(stored, ctypes.c_float)
    else:
        flux = _array(scalar_model, np.float64, (nchan,), "scalar_model")
        keep.append(flux)
        inputs.model_scalar = _ptr(flux, ctypes.c_double)
    out_res = np.empty(data.shape, np.complex128) if residuals else None
    out_z = np.empty((nrow, nchan)) if scores else None
    out_h = np.empty((nt, nf, na, 8, 8)) if normals else None
    out_b = np.empty((nt, nf, na, 8)) if normals else None
    out_n = np.empty((nt, nf, na), np.uint64) if normals else None
    stats = np.zeros(12)
    outputs = _Outputs(
        _ptr(out_res, ctypes.c_double) if residuals else None,
        _ptr(out_z, ctypes.c_double) if scores else None,
        _ptr(out_h, ctypes.c_double) if normals else None,
        _ptr(out_b, ctypes.c_double) if normals else None,
        _ptr(out_n, ctypes.c_uint64) if normals else None,
        _ptr(stats, ctypes.c_double),
    )
    status = library().rang_core_fused(ctypes.byref(inputs), ctypes.byref(outputs))
    if status:
        raise RuntimeError(f"rang core fused pass failed with status {status}")
    split_stats = {
        name: {
            "sum": float(stats[4 * k]),
            "cells": int(stats[4 * k + 1]),
            "invalid": int(stats[4 * k + 2]),
            "nonfinite": int(stats[4 * k + 3]),
        }
        for k, name in enumerate(SPLITS)
    }
    return FusedResult(out_res, out_z, out_h, out_b, out_n, split_stats)
