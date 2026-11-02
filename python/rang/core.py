"""Python interface to the Rang core (Rust, GPL-3.0-or-later).

Phase 1 exposes one fused pass over the visibility cells: prediction, residual,
per-split weighted residual sums, per-baseline robust scores and
antenna-diagonal Gauss--Newton blocks (research/core-phase1.md). Phase 2 adds
solve_complex, a port of QuartiCal's full-Jones complex solver
(research/core-phase2.md).

The kernels are reached through the PyO3 extension `rang._core`, built by
maturin from core/py (research/core-j-packaging.md). Task P7
(research/p7-architecture.md) removed the second door, ctypes on a library
built by Cargo at run time: nothing here runs a compiler, and the extension
releases the GIL around every kernel. `RANG_CORE_BACKEND` and `RANG_CORE_LIB`
are no longer read, except that asking for the ctypes backend through either
is refused, so an old command line cannot record a library it did not use.

Task W4-1 (research/w4-1-receipts.md): `ENVIRONMENT` is the one registry of
every `RANG_*` variable the package or the Rust core reads; receipts record
`environment_settings()` and docs/environment.md is generated from it
(`environment_markdown`). `solve_complex` takes `options=` and `trace=`
explicitly; only when they are None does it read `RANG_SOLVE_OPTIONS` and
`RANG_SOLVE_TRACE`, once per call, and the core itself reads neither.
`checkout_root()` is the checkout the package runs from, or None for an
installed wheel.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

SPLITS = ("train", "validation", "test")
SPLIT_CODES = {"train": 1, "validation": 2, "test": 3}


# --- the environment registry (task W4-1, research/w4-1-receipts.md) --------


@dataclass(frozen=True)
class Variable:
    """One environment variable read by the package or the Rust core."""

    name: str
    default: str
    kind: str
    effect: str
    report: str
    reader: str


# What each kind means; receipts record the kinds in RECORDED_KINDS.
KINDS = {
    "result": "changes computed numbers, or which code or binary computes them",
    "input": "selects input data or files",
    "speed": "changes speed or memory only (measured result-neutral)",
    "output": "adds a diagnostic output; the results are unchanged",
    "process": "changes how a command, check or notebook runs",
    "refused": "removed; setting it is an error",
    "viewer": "the notebook's CARTA viewer connection; not recorded",
    "test": "a Rust unit-test fixture; not recorded",
    "retired": "read by no code any more (kept so old receipts stay explained); not recorded",
}
RECORDED_KINDS = ("result", "input", "speed", "output", "process", "refused")


def _v(name, default, kind, effect, report, reader):
    return Variable(name, default, kind, effect, f"research/{report}.md", reader)


ENVIRONMENT = (
    _v(
        "RANG_SOLVE_OPTIONS",
        "unset (the archived solver)",
        "result",
        "solver options `qp_weights`, `stop`, `anderson`, `freeze`; read by "
        "`core.solve_complex` when `options=` is None",
        "l5-solver-science",
        "python/rang/core.py",
    ),
    _v(
        "RANG_SOLVE_TRACE",
        "unset (no trace)",
        "output",
        "file for the per-iteration solver trace; read by "
        "`core.solve_complex` when `trace=` is None",
        "l5-solver-science",
        "python/rang/core.py",
    ),
    _v(
        "RANG_GRIDDER_DEVICE",
        "cpu",
        "result",
        "`gpu` runs the inversion on wgpu (cargo feature `gpu`)",
        "x2-wgpu",
        "python/rang/core_grid.py",
    ),
    _v(
        "RANG_GRIDDER_GPU_PRECISION",
        "f64",
        "result",
        "`f32` selects the GPU path toleranced to 1e-4",
        "x2-wgpu",
        "python/rang/core_grid.py",
    ),
    _v(
        "RANG_GPU_ADAPTER",
        "unset (the best adapter)",
        "result",
        "substring of the name of the GPU adapter to use",
        "x2-wgpu",
        "core/src/gpu/context.rs",
    ),
    _v(
        "RANG_GPU_MEMORY_MB",
        "256",
        "speed",
        "device-memory budget per GPU inversion (batching only)",
        "x2-wgpu",
        "core/src/gpu/invert.rs",
    ),
    _v(
        "RANG_GPU_LAYERS_PER_BATCH",
        "unset (as many as the budget allows)",
        "speed",
        "upper bound on the w-layers per GPU batch",
        "x2-wgpu",
        "core/src/gpu/invert.rs",
    ),
    _v(
        "RANG_DF1_LIB",
        "no longer read",
        "retired",
        "was a prebuilt w-gridder library loaded through ctypes (DF1); W4-3 "
        "removed the fallback",
        "w4-3-kernels",
        "-",
    ),
    _v(
        "RANG_GMCLEAN_SIMD",
        "unset (the best the CPU has)",
        "speed",
        "`scalar`, `avx2` or `avx512` caps gmclean's kernels; the gather sum agrees to rounding only",
        "gmclean",
        "core/src/gmclean/kernels.rs",
    ),
    _v(
        "RANG_WGRIDDER_SIMD",
        "unset (AVX-512 where available)",
        "speed",
        "`avx2` or `baseline` caps the w-gridder's instruction set",
        "df2-wgridder-speed",
        "core/src/wgridder.rs",
    ),
    _v(
        "RANG_WGRIDDER_PLANE_GROUP",
        "4, within 2 GiB of grids",
        "speed",
        "w-planes gridded together; 1 takes the least memory",
        "gmclean",
        "core/src/wgridder.rs",
    ),
    _v(
        "RANG_WGRIDDER_TIMING",
        "unset",
        "output",
        "phase timings of the w-gridder on stderr",
        "df2-wgridder-speed",
        "core/src/wgridder.rs",
    ),
    _v(
        "RANG_C1_LIB",
        "no longer read",
        "retired",
        "was a prebuilt closure-score library loaded through ctypes (C1); "
        "W4-3 moved the kernel into the extension",
        "w4-3-kernels",
        "-",
    ),
    _v(
        "RANG_P6",
        "unset (the frozen calls)",
        "result",
        "`1` runs the signal track's ported guard and influence functions",
        "p6-python-hotspots",
        "python/rang/core_signal.py",
    ),
    _v(
        "RANG_TOY_BIN",
        "unset (the extension)",
        "result",
        "a pointing-toy binary run instead of the extension",
        "p7-architecture",
        "python/rang/__init__.py",
    ),
    _v(
        "RANG_FLAGGING_SUITE_IMAGE",
        "unset",
        "result",
        "the container image the trend run's configuration records",
        "flagging-parallel",
        "python/rang/core_trend_run.py",
    ),
    _v(
        "RANG_STRATEGY_DIR",
        "unset (the CARACAL strategy inputs under outputs/)",
        "input",
        "directory of the Tricolour strategies the notebook flags with",
        "d2-notebook",
        "python/rang/notebook/flags.py",
    ),
    _v(
        "RANG_FIXTURE",
        "unset (outputs/ska-pointing/outer_scans.zip)",
        "input",
        "the notebook's pointing fixture",
        "d2-notebook",
        "python/rang/notebook/data.py",
    ),
    _v(
        "RANG_LUNO_SLICE",
        "unset (task G's fetch)",
        "input",
        "the notebook's LUNO slice directory",
        "d2-notebook",
        "python/rang/notebook/data.py",
    ),
    _v(
        "RANG_LUNO_EXTRA",
        "unset (the solve inputs)",
        "input",
        "the notebook's LUNO extra-columns directory",
        "d2-notebook",
        "python/rang/notebook/data.py",
    ),
    _v(
        "RANG_HOLOGRAPHY_PRODUCT",
        "unset (outputs/b1-20261030-05-holography)",
        "input",
        "the notebook's holography product",
        "d3-science-notebooks",
        "python/rang/notebook/science.py",
    ),
    _v(
        "RANG_NOTEBOOK_CACHE",
        "unset (~/.cache/rang-notebook)",
        "process",
        "the notebook's download cache",
        "d2-notebook",
        "python/rang/notebook/data.py",
    ),
    _v(
        "RANG_NOTEBOOK_LUNO",
        "unset (off)",
        "process",
        "`1` runs the notebook's LUNO section",
        "d2-notebook",
        "python/rang/notebook/science.py",
    ),
    _v(
        "RANG_NOTEBOOK_SLOW",
        "unset (off)",
        "process",
        "`1` runs the notebook's slow JAX audits",
        "d3-science-notebooks",
        "python/rang/notebook/science.py",
    ),
    _v(
        "RANG_NOTEBOOK_HOLOGRAPHY",
        "unset (off)",
        "process",
        "`1` draws the notebook's holography maps",
        "d3-science-notebooks",
        "python/rang/notebook/science.py",
    ),
    _v(
        "RANG_NOTEBOOK_CARTA",
        "0",
        "process",
        "`1` opens the notebook's images in CARTA",
        "nb-carta",
        "python/rang/notebook/carta.py",
    ),
    _v(
        "RANG_PIN_THREADS",
        "unset (caps on)",
        "process",
        "`0` turns off the CLI's BLAS and XLA thread caps (the thread "
        "variables themselves are recorded under `threads`)",
        "p9-cli",
        "python/rang/core_cli.py",
    ),
    _v(
        "RANG_CHECKALL_LOCK",
        "unset (~/.rang-checkall-v2.lock)",
        "process",
        "the check's host lock file",
        "p10-tests",
        "python/rang/check.py",
    ),
    _v(
        "RANG_CHECKALL_LOCKED",
        "unset",
        "process",
        "set by the check while it holds the lock",
        "p10-tests",
        "python/rang/check.py",
    ),
    _v(
        "RANG_CORE_BACKEND",
        "unset",
        "refused",
        "the removed ctypes backend; anything but `extension` is refused",
        "p7-architecture",
        "python/rang/core.py",
    ),
    _v(
        "RANG_CORE_LIB",
        "unset",
        "refused",
        "the removed ctypes library; setting it is refused",
        "p7-architecture",
        "python/rang/core.py",
    ),
    _v(
        "RANG_TOY_LIB",
        "unset",
        "refused",
        "the removed toy ctypes library; recorded by `rang-core environment`",
        "p7-architecture",
        "python/rang/core_cli.py",
    ),
    _v(
        "RANG_CARTA_URL",
        "unset",
        "viewer",
        "the CARTA backend's URL",
        "nb-carta",
        "python/rang/notebook/carta.py",
    ),
    _v(
        "RANG_CARTA_WEBDRIVER",
        "unset",
        "viewer",
        "the CARTA backend's webdriver",
        "nb-carta",
        "python/rang/notebook/carta.py",
    ),
    _v(
        "RANG_CARTA_SESSION_ID",
        "unset",
        "viewer",
        "the CARTA session",
        "nb-carta",
        "python/rang/notebook/carta.py",
    ),
    _v(
        "RANG_CARTA_DIR",
        "unset (`<RANG_NOTEBOOK_CACHE>/carta`)",
        "viewer",
        "where the images for CARTA are written",
        "nb-carta",
        "python/rang/notebook/carta.py",
    ),
    _v(
        "RANG_CARTA_ROOT",
        "unset",
        "viewer",
        "that directory as the CARTA backend sees it",
        "nb-carta",
        "python/rang/notebook/carta.py",
    ),
    _v(
        "RANG_MS_FIXTURE",
        "unset (the tests skip)",
        "test",
        "a real Measurement Set for the reader and writer unit tests",
        "core-e-ms-reader",
        "core/src/ms.rs",
    ),
)
# `RANG_` names in the sources that are not environment variables.
NOT_ENVIRONMENT = {"RANG_E3": "a Measurement Set keyword written by a Rust test"}


def environment_variables(kinds=RECORDED_KINDS):
    """The registry entries of the given kinds, in registry order."""
    return [v for v in ENVIRONMENT if v.kind in kinds]


def environment_settings(environ=None):
    """{name: value, or None when unset} of every recorded registry variable:
    the `rang_environment` record of the receipts (task W4-1)."""
    environ = os.environ if environ is None else environ
    return {v.name: environ.get(v.name) for v in environment_variables()}


def environment_markdown():
    """The registry as a Markdown table (docs/environment.md)."""
    lines = [
        "| Variable | Default | Kind | What it changes | Report | Read by |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for v in ENVIRONMENT:
        lines.append(
            f"| `{v.name}` | {v.default} | {v.kind} | {v.effect} | "
            f"`{v.report}` | `{v.reader}` |"
        )
    return "\n".join(lines) + "\n"


MANIFESTS = ("pyproject.toml", "Cargo.toml", "core/Cargo.toml")


def checkout_root():
    """The source checkout the package runs from, or None.

    `parents[2]` of this file is the checkout only for an editable install;
    for an installed wheel it is `<venv>/lib/python3.X`, which may sit inside
    any git repository. It counts only if it holds the three manifests
    (`check.find_root`'s test), so a receipt names a commit only when there
    is one (task W4-1)."""
    root = Path(__file__).resolve().parents[2]
    return root if all((root / name).is_file() for name in MANIFESTS) else None


def core_root():
    """The core crate of the checkout (its `data/` holds the Tricolour static
    masks). Only a source checkout has it; the wheel does not need it."""
    root = Path(__file__).resolve().parents[2] / "core"
    if not (root / "Cargo.toml").is_file():
        raise RuntimeError("Run from the Rang checkout (core/ is not installed)")
    return root


BACKENDS = ("extension",)


def _refuse_ctypes():
    requested = os.environ.get("RANG_CORE_BACKEND")
    if requested and requested != "extension":
        raise ValueError(
            f"RANG_CORE_BACKEND={requested}: only the extension remains "
            "(research/p7-architecture.md); unset it"
        )
    if os.environ.get("RANG_CORE_LIB"):
        raise ValueError(
            "RANG_CORE_LIB is set, but the ctypes backend was removed by task P7 "
            "(research/p7-architecture.md); unset it"
        )


@lru_cache(maxsize=1)
def extension():
    """The extension module `rang._core`."""
    _refuse_ctypes()
    try:
        from . import _core
    except ImportError as exc:
        raise ImportError(
            "rang._core is not built: install the wheel, or run "
            "`maturin develop --release` (or `pip install -e .`) in the checkout"
        ) from exc
    return _core


def backend_name():
    """Always "extension" (kept for receipts; the ctypes backend is gone)."""
    extension()
    return "extension"


def library():
    """The extension module. Drivers call this to load the core before timing
    (it was the ctypes handle before task P7)."""
    return extension()


def reset_backend():
    """Forget the loaded module (tests only)."""
    extension.cache_clear()


def library_path():
    """The extension's binary, for provenance hashes."""
    return Path(extension().__file__).resolve()


def _array(value, dtype, shape, label):
    array = np.require(value, dtype=dtype, requirements=["C", "A"])
    if array.shape != tuple(shape):
        raise ValueError(f"{label} must have shape {tuple(shape)}, not {array.shape}")
    return array


def _flags(value, shape, label):
    """Bool or uint8 flags as uint8, without a copy when already C-contiguous
    (task P7). Nonzero means flagged, the predicate of `np.asarray(flag, bool)`
    and of the kernel, so the kernel sees the same flags as before."""
    array = np.asarray(value)
    if array.dtype == np.bool_ or array.dtype == np.uint8:
        array = np.require(array, requirements=["C", "A"]).view(np.uint8)
    else:
        array = np.require(array != 0, requirements=["C", "A"]).view(np.uint8)
    if array.shape != tuple(shape):
        raise ValueError(f"{label} must have shape {tuple(shape)}, not {array.shape}")
    return array


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
    if model is not None:
        stored = _array(model, np.complex64, data.shape, "model")
    else:
        stored = _array(scalar_model, np.float64, (nchan,), "scalar_model")
    out_res = np.empty(data.shape, np.complex128) if residuals else None
    out_z = np.empty((nrow, nchan)) if scores else None
    out_h = np.empty((nt, nf, na, 8, 8)) if normals else None
    out_b = np.empty((nt, nf, na, 8)) if normals else None
    out_n = np.empty((nt, nf, na), np.uint64) if normals else None
    stats = np.zeros(12)
    status = extension().fused(
        nrow,
        nchan,
        nt,
        nf,
        na,
        data.view(np.float32),
        weights,
        stored.view(np.float32) if model is not None else None,
        stored if model is None else None,
        a1,
        a2,
        tb,
        fb,
        gains.view(np.float64),
        valid,
        labels,
        out_res.view(np.float64) if residuals else None,
        out_z,
        out_h,
        out_b,
        out_n,
        stats,
    )
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


SOLVE_OPTIONS_VAR = "RANG_SOLVE_OPTIONS"
SOLVE_TRACE_VAR = "RANG_SOLVE_TRACE"
STOP_TESTS = ("gain", "product", "loss")


@dataclass(frozen=True)
class SolveOptions:
    """Parsed run-time solver options (`core/src/solve.rs`, task L5); the
    defaults are the archived solver. `text` is what was parsed."""

    text: str = ""
    transposed_qp_weights: bool = False
    stop: str = "gain"
    tolerance: float = 0.0
    anderson: int = 0
    freeze: bool = False

    def parts(self):
        """The tuple the extension's `solve_complex` takes."""
        return (
            int(self.transposed_qp_weights),
            STOP_TESTS.index(self.stop),
            float(self.tolerance),
            int(self.anderson),
            int(self.freeze),
        )

    def record(self):
        """The options as a receipt entry."""
        return {
            "text": self.text,
            "qp_weights": "transposed" if self.transposed_qp_weights else "archived",
            "stop": self.stop,
            "tolerance": self.tolerance if self.stop != "gain" else None,
            "anderson": self.anderson,
            "freeze": self.freeze,
        }


def solve_options(options=None):
    """`options` parsed by the core's one parser (`Options::parse`): a
    `SolveOptions` as it is, a string in the `RANG_SOLVE_OPTIONS` syntax, or
    None for that variable (unset means the archived solver). Raises
    ValueError when malformed."""
    if isinstance(options, SolveOptions):
        return options
    text = os.environ.get(SOLVE_OPTIONS_VAR, "") if options is None else str(options)
    status, transposed, stop, tolerance, anderson, freeze = (
        extension().solve_options_parse(text)
    )
    if status:
        raise ValueError(
            f"malformed solver options {text!r}: expected qp_weights=archived|"
            "transposed, stop=gain|product:<tol>|loss:<tol>, anderson=<0..10>, "
            "freeze=0|1"
        )
    return SolveOptions(
        text, bool(transposed), STOP_TESTS[stop], tolerance, anderson, bool(freeze)
    )


@dataclass
class ComplexSolution:
    """Gains (time_bin, freq_bin, antenna, 2, 2), flags (1 flagged), counts,
    and the options and trace file the solve used (task W4-1)."""

    gains: np.ndarray
    flags: np.ndarray
    iterations: int
    converged_fraction: float
    options: SolveOptions | None = None
    trace: str | None = None


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
    options=None,
    trace=None,
):
    """Ported QuartiCal 0.2.7 `complex` solve with rang's frozen settings.

    Rows must be sorted by time bin. See research/core-phase2.md for what is
    and is not ported. Defaults match rang's QuartiCal command (50 iterations,
    convergence criterion 1e-7) and QuartiCal's convergence fraction (0.99).
    `options` (see `solve_options`) and `trace` (a file for the L5 trace)
    default to `RANG_SOLVE_OPTIONS` and `RANG_SOLVE_TRACE`, read here once
    per call; the solution records both. Malformed options raise
    RuntimeError with status 1, as the core did before task W4-1.
    """
    try:
        options = solve_options(options)
    except ValueError as exc:
        raise RuntimeError(
            f"rang core complex solve failed with status 1: {exc}"
        ) from exc
    if trace is None:
        trace = os.environ.get(SOLVE_TRACE_VAR) or None
    trace = None if trace is None or str(trace) == "" else str(trace)
    data = np.require(data, np.complex64, ["C", "A"])
    if data.ndim != 3 or data.shape[-1] != 4:
        raise ValueError("data must be (row, chan, 4) complex")
    nrow, nchan = data.shape[:2]
    weights = _array(weights, np.float32, data.shape, "weights")
    flags_in = _flags(flag, data.shape, "flag")
    rows_in = _flags(flag_row, (nrow,), "flag_row")
    a1 = _array(antenna1, np.uint32, (nrow,), "antenna1")
    a2 = _array(antenna2, np.uint32, (nrow,), "antenna2")
    tb = _array(time_bin, np.uint32, (nrow,), "time_bin")
    fb = _array(freq_bin, np.uint32, (nchan,), "freq_bin")
    if (model is None) == (scalar_model is None):
        raise ValueError("give exactly one of model and scalar_model")
    if max_iterations < 1:
        raise ValueError("at least one iteration required")
    if model is not None:
        stored = _array(model, np.complex64, data.shape, "model")
    else:
        stored = _array(scalar_model, np.float64, (nchan,), "scalar_model")
    gains = np.empty((ntime_bins, nfreq_bins, nant, 2, 2), np.complex128)
    flags = np.empty((ntime_bins, nfreq_bins, nant), np.int8)
    status, n_iterations, converged = extension().solve_complex(
        nrow,
        nchan,
        ntime_bins,
        nfreq_bins,
        nant,
        data.view(np.float32),
        weights,
        stored.view(np.float32) if model is not None else None,
        stored if model is None else None,
        flags_in,
        rows_in,
        a1,
        a2,
        tb,
        fb,
        max_iterations,
        stop_criterion,
        stop_fraction,
        gains.view(np.float64),
        flags,
        options.parts(),
        trace,
    )
    if status:
        raise RuntimeError(f"rang core complex solve failed with status {status}")
    return ComplexSolution(
        gains, flags, int(n_iterations), float(converged), options, trace
    )


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
    vis = np.empty((nrow, nchan), np.complex128)
    spec = np.empty((nsrc, nchan)) if spectra else None
    status = extension().predict_components(
        nrow,
        nchan,
        nsrc,
        coeffs.shape[1],
        uvw,
        frequency,
        lm,
        kinds,
        flux,
        coeffs,
        logs,
        refs,
        shapes,
        vis.view(np.float64),
        spec,
    )
    if status:
        raise RuntimeError(
            f"rang core component prediction failed with status {status}"
        )
    return (vis, spec) if spectra else vis


def blosc_decode(payload):
    """Decode a whole blosc-1 chunk (LZ4, byte shuffle) to bytes."""
    payload = bytes(payload)
    ext = extension()
    status, size = ext.blosc_size(payload)
    if status:
        raise ValueError("unsupported or invalid blosc chunk")
    status, out = ext.blosc_decode(payload, size)
    if status:
        raise ValueError("blosc chunk failed to decode")
    return out


def blosc_decode_rows(payload, row_bytes, rows):
    """Decode only `rows` of a row-major blosc chunk; returns (bytes, blocks)."""
    payload = bytes(payload)
    rows = np.require(np.asarray(rows, dtype=np.uintp), np.uintp, ["C", "A"])
    if rows.ndim != 1:
        raise ValueError("rows must be one-dimensional")
    status, blocks, out = extension().blosc_decode_rows(payload, row_bytes, rows)
    if status:
        raise ValueError("blosc row selection failed to decode")
    return out, int(blocks)
