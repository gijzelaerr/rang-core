"""Python interface to the Rang core (Rust, GPL-3.0-or-later).

Phase 1 exposes one fused pass over the visibility cells: prediction, residual,
per-split weighted residual sums, per-baseline robust scores and
antenna-diagonal Gauss--Newton blocks (research/core-phase1.md). Phase 2 adds
solve_complex, a port of QuartiCal's full-Jones complex solver
(research/core-phase2.md). The library
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
    lib.rang_core_solve_complex.argtypes = [
        _pointer(_SolveInputs),
        _pointer(_SolveOutputs),
    ]
    lib.rang_core_solve_complex.restype = ctypes.c_int
    lib.rang_core_predict_components.argtypes = [
        _pointer(_PredictInputs),
        _pointer(_PredictOutputs),
    ]
    lib.rang_core_predict_components.restype = ctypes.c_int
    lib.rang_core_blosc_size.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        _pointer(ctypes.c_size_t),
    ]
    lib.rang_core_blosc_size.restype = ctypes.c_int
    lib.rang_core_blosc_decode.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_char_p,
        ctypes.c_size_t,
    ]
    lib.rang_core_blosc_decode.restype = ctypes.c_int
    lib.rang_core_blosc_decode_rows.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_size_t,
        _pointer(ctypes.c_size_t),
        ctypes.c_size_t,
        ctypes.c_char_p,
        _pointer(ctypes.c_size_t),
    ]
    lib.rang_core_blosc_decode_rows.restype = ctypes.c_int
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


class _SolveInputs(ctypes.Structure):
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
        ("flag", _pointer(ctypes.c_uint8)),
        ("flag_row", _pointer(ctypes.c_uint8)),
        ("antenna1", _pointer(ctypes.c_uint32)),
        ("antenna2", _pointer(ctypes.c_uint32)),
        ("time_bin", _pointer(ctypes.c_uint32)),
        ("freq_bin", _pointer(ctypes.c_uint32)),
        ("max_iterations", ctypes.c_size_t),
        ("stop_criterion", ctypes.c_double),
        ("stop_fraction", ctypes.c_double),
    ]


class _SolveOutputs(ctypes.Structure):
    _fields_ = [
        ("gains", _pointer(ctypes.c_double)),
        ("flags", _pointer(ctypes.c_int8)),
        ("iterations", _pointer(ctypes.c_size_t)),
        ("converged_fraction", _pointer(ctypes.c_double)),
    ]


@dataclass
class ComplexSolution:
    """Gains (time_bin, freq_bin, antenna, 2, 2), flags (1 flagged), counts."""

    gains: np.ndarray
    flags: np.ndarray
    iterations: int
    converged_fraction: float


def solve_complex(
    data,
    weights,
    flag,
    flag_row,
    antenna1,
    antenna2,
    time_bin,
    freq_bin,
    *,
    ntime_bins,
    nfreq_bins,
    nant,
    model=None,
    scalar_model=None,
    max_iterations=50,
    stop_criterion=1e-7,
    stop_fraction=0.99,
):
    """Ported QuartiCal 0.2.7 `complex` solve with rang's frozen settings.

    Rows must be sorted by time bin. See research/core-phase2.md for what is
    and is not ported. Defaults match rang's QuartiCal command (50 iterations,
    convergence criterion 1e-7) and QuartiCal's convergence fraction (0.99).
    """
    data = np.require(data, np.complex64, ["C", "A"])
    if data.ndim != 3 or data.shape[-1] != 4:
        raise ValueError("data must be (row, chan, 4) complex")
    nrow, nchan = data.shape[:2]
    weights = _array(weights, np.float32, data.shape, "weights")
    flags_in = _array(np.asarray(flag, bool), np.uint8, data.shape, "flag")
    rows_in = _array(np.asarray(flag_row, bool), np.uint8, (nrow,), "flag_row")
    a1 = _array(antenna1, np.uint32, (nrow,), "antenna1")
    a2 = _array(antenna2, np.uint32, (nrow,), "antenna2")
    tb = _array(time_bin, np.uint32, (nrow,), "time_bin")
    fb = _array(freq_bin, np.uint32, (nchan,), "freq_bin")
    if (model is None) == (scalar_model is None):
        raise ValueError("give exactly one of model and scalar_model")
    if max_iterations < 1:
        raise ValueError("at least one iteration required")
    inputs = _SolveInputs(
        nrow,
        nchan,
        ntime_bins,
        nfreq_bins,
        nant,
        _ptr(data, ctypes.c_float),
        _ptr(weights, ctypes.c_float),
        None,
        None,
        _ptr(flags_in, ctypes.c_uint8),
        _ptr(rows_in, ctypes.c_uint8),
        _ptr(a1, ctypes.c_uint32),
        _ptr(a2, ctypes.c_uint32),
        _ptr(tb, ctypes.c_uint32),
        _ptr(fb, ctypes.c_uint32),
        max_iterations,
        stop_criterion,
        stop_fraction,
    )
    if model is not None:
        stored = _array(model, np.complex64, data.shape, "model")
        inputs.model_stored = _ptr(stored, ctypes.c_float)
    else:
        stored = _array(scalar_model, np.float64, (nchan,), "scalar_model")
        inputs.model_scalar = _ptr(stored, ctypes.c_double)
    gains = np.empty((ntime_bins, nfreq_bins, nant, 2, 2), np.complex128)
    flags = np.empty((ntime_bins, nfreq_bins, nant), np.int8)
    iterations = ctypes.c_size_t()
    fraction = ctypes.c_double()
    outputs = _SolveOutputs(
        _ptr(gains, ctypes.c_double),
        _ptr(flags, ctypes.c_int8),
        ctypes.pointer(iterations),
        ctypes.pointer(fraction),
    )
    status = library().rang_core_solve_complex(
        ctypes.byref(inputs), ctypes.byref(outputs)
    )
    if status:
        raise RuntimeError(f"rang core complex solve failed with status {status}")
    return ComplexSolution(gains, flags, int(iterations.value), float(fraction.value))


class _PredictInputs(ctypes.Structure):
    _fields_ = [
        ("nrow", ctypes.c_size_t),
        ("nchan", ctypes.c_size_t),
        ("nsrc", ctypes.c_size_t),
        ("ncoeff", ctypes.c_size_t),
        ("uvw", _pointer(ctypes.c_double)),
        ("frequency", _pointer(ctypes.c_double)),
        ("lm", _pointer(ctypes.c_double)),
        ("kind", _pointer(ctypes.c_uint8)),
        ("flux", _pointer(ctypes.c_double)),
        ("coeffs", _pointer(ctypes.c_double)),
        ("log_poly", _pointer(ctypes.c_uint8)),
        ("ref_freq", _pointer(ctypes.c_double)),
        ("gauss_shape", _pointer(ctypes.c_double)),
    ]


class _PredictOutputs(ctypes.Structure):
    _fields_ = [
        ("vis", _pointer(ctypes.c_double)),
        ("spectra", _pointer(ctypes.c_double)),
    ]


def predict_components(
    uvw,
    frequency,
    lm,
    kind,
    flux,
    coeffs,
    log_poly,
    ref_freq,
    gauss_shape,
    *,
    spectra=False,
):
    """WSClean-format component prediction (port of africanus wsclean_predict).

    uvw (row, 3) metres; frequency (chan,) Hz; lm (src, 2); kind (src,) with 0
    point and 1 Gaussian; flux (src,); coeffs (src, ncoeff); log_poly (src,)
    bool; ref_freq (src,); gauss_shape (src, 3) as major and minor FWHM in
    radians and position angle. Returns (row, chan) complex128 Stokes I
    visibilities, and (src, chan) spectra when requested.
    """
    uvw = np.require(uvw, np.float64, ["C", "A"])
    if uvw.ndim != 2 or uvw.shape[1] != 3:
        raise ValueError("uvw must be (row, 3)")
    frequency = np.require(frequency, np.float64, ["C", "A"])
    flux = np.require(flux, np.float64, ["C", "A"])
    nsrc = len(flux)
    coeffs = np.require(coeffs, np.float64, ["C", "A"])
    if coeffs.ndim != 2 or coeffs.shape[0] != nsrc:
        raise ValueError("coeffs must be (src, ncoeff)")
    lm = _array(lm, np.float64, (nsrc, 2), "lm")
    kinds = _array(kind, np.uint8, (nsrc,), "kind")
    logs = _array(np.asarray(log_poly, bool), np.uint8, (nsrc,), "log_poly")
    refs = _array(ref_freq, np.float64, (nsrc,), "ref_freq")
    shapes = _array(gauss_shape, np.float64, (nsrc, 3), "gauss_shape")
    nrow, nchan = len(uvw), len(frequency)
    inputs = _PredictInputs(
        nrow,
        nchan,
        nsrc,
        coeffs.shape[1],
        _ptr(uvw, ctypes.c_double),
        _ptr(frequency, ctypes.c_double),
        _ptr(lm, ctypes.c_double),
        _ptr(kinds, ctypes.c_uint8),
        _ptr(flux, ctypes.c_double),
        _ptr(coeffs, ctypes.c_double),
        _ptr(logs, ctypes.c_uint8),
        _ptr(refs, ctypes.c_double),
        _ptr(shapes, ctypes.c_double),
    )
    vis = np.empty((nrow, nchan), np.complex128)
    spec = np.empty((nsrc, nchan)) if spectra else None
    outputs = _PredictOutputs(
        _ptr(vis, ctypes.c_double),
        _ptr(spec, ctypes.c_double) if spectra else None,
    )
    status = library().rang_core_predict_components(
        ctypes.byref(inputs), ctypes.byref(outputs)
    )
    if status:
        raise RuntimeError(
            f"rang core component prediction failed with status {status}"
        )
    return (vis, spec) if spectra else vis


def blosc_decode(payload):
    """Decode a whole blosc-1 chunk (LZ4, byte shuffle) to bytes."""
    payload = bytes(payload)
    size = ctypes.c_size_t()
    lib = library()
    if lib.rang_core_blosc_size(payload, len(payload), ctypes.byref(size)):
        raise ValueError("unsupported or invalid blosc chunk")
    out = ctypes.create_string_buffer(size.value)
    if lib.rang_core_blosc_decode(payload, len(payload), out, size.value):
        raise ValueError("blosc chunk failed to decode")
    return out.raw


def blosc_decode_rows(payload, row_bytes, rows):
    """Decode only `rows` of a row-major blosc chunk; returns (bytes, blocks)."""
    payload = bytes(payload)
    rows = np.require(np.asarray(rows, dtype=np.uintp), np.uintp, ["C", "A"])
    if rows.ndim != 1:
        raise ValueError("rows must be one-dimensional")
    out = ctypes.create_string_buffer(len(rows) * row_bytes)
    blocks = ctypes.c_size_t()
    status = library().rang_core_blosc_decode_rows(
        payload,
        len(payload),
        row_bytes,
        rows.ctypes.data_as(_pointer(ctypes.c_size_t)),
        len(rows),
        out,
        ctypes.byref(blocks),
    )
    if status:
        raise ValueError("blosc row selection failed to decode")
    return out.raw, int(blocks.value)
