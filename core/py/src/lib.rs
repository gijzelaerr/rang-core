//! `rang._core`: the PyO3 extension module over the Rang core.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Task J of `research/core-parallel-plan.md` (`research/core-j-packaging.md`)
//! made this a second entry door into the C ABI of `rang_core::ffi*`; task P7
//! (`research/p7-architecture.md`) made it the only one. Every function calls
//! the same C function a C consumer would: NumPy arrays are borrowed in place
//! as read-only or read-write slices (never copied; arrays that are not
//! C-contiguous and read-only outputs are refused, task W4-2), their pointers
//! fill the `#[repr(C)]`
//! structs, and the status code of the C function is returned for the Python
//! wrapper to interpret. P7 adds the root crate's kernels (`rang_sim`, reached
//! as `rang_core::sim`: gain TV, phase trend, anchored response, projector)
//! and the pointing simulation's command line, and releases the GIL around every
//! kernel call, so Python threads overlap decode, solves and images. The
//! Measurement Set reader is a `MsTable` class over `rang_core::ms::Table`
//! whose column bytes move into a NumPy array without a copy. No kernel code
//! lives here.
//!
//! With the GIL released, a kernel reads and writes the borrowed buffers
//! while other Python threads run. The NumPy borrow flags stop another
//! extension call from taking a conflicting borrow, but Python code writing
//! into an input array during the call races with the kernel, exactly as it
//! did under ctypes (which also released the GIL): do not do that.

use numpy::{
    Complex32, Complex64, Element, IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArrayDyn,
    PyReadwriteArrayDyn,
};
use numpy::{PyReadonlyArray, PyReadwriteArray, PyUntypedArrayMethods, ndarray::Dimension};
#[cfg(feature = "gpu")]
use pyo3::exceptions::PyRuntimeError;
use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use rang_core::ffi;
use rang_core::ffi_correct::CorrectInputsC;
use rang_core::ffi_flag::{FlagInputs, FlagOutputs};
use rang_core::ffi_grid::{GridInputs, GridOutputs};
use rang_core::ffi_ms_write::{
    ColumnArgs, ManagerArgs, column_descs, keyword_value, manager_specs, new_column,
};
use rang_core::ffi_weights::{
    ImagingWeightInputs, ImagingWeightOutputs, StokesIInputs, StokesIOutputs,
};
use rang_core::ffi_wgridder::{self, WgridderOptions};
use rang_core::ms::{DataType, Table};
use rang_core::ms_write::TableWriter;
use rang_core::sim;
use std::ffi::c_void;

mod cal_gain;
mod clean;

type Ro<'py, T> = PyReadonlyArrayDyn<'py, T>;
type Rw<'py, T> = PyReadwriteArrayDyn<'py, T>;
/// A column read: packed bytes, nrows, cell shape, dtype code, nstrings.
type Column<'py> = (Bound<'py, PyArray1<u8>>, u64, Vec<i64>, i32, usize);

/// A job that runs with the GIL released. It holds raw pointers into NumPy
/// buffers (not `Send`); they stay valid because the borrowed arrays outlive
/// the call, and the job runs on the calling thread.
struct Detached<F>(F);

// SAFETY: `Python::detach` runs the closure on the current thread before it
// returns; nothing crosses to another thread. The bound only asks that the
// closure not touch Python objects, which no job here does.
unsafe impl<F> Send for Detached<F> {}

impl<F: FnOnce() -> R, R> Detached<F> {
    fn run(self) -> R {
        (self.0)()
    }
}

/// Run `f` without the GIL (task P7). The result is wrapped too, because
/// the MS reader's table is not `Send` either; it stays on this thread.
fn detach<R, F: FnOnce() -> R>(py: Python<'_>, f: F) -> R {
    let job = Detached(f);
    py.detach(move || Detached(job.run())).0
}

/// The slice of a C-contiguous input array (task W4-2, W4R-04): rust-numpy's
/// `as_slice` also accepts a Fortran-ordered array, which a kernel would read
/// transposed, so that is a ValueError naming the argument.
fn c_slice<'a, T: Element, D: Dimension>(
    a: &'a PyReadonlyArray<'_, T, D>,
    name: &str,
) -> PyResult<&'a [T]> {
    if !a.is_c_contiguous() {
        return Err(PyValueError::new_err(format!(
            "{name} must be C-contiguous"
        )));
    }
    Ok(a.as_slice()?)
}

/// The slice of a C-contiguous output array (as `c_slice`).
fn c_slice_mut<'a, T: Element, D: Dimension>(
    a: &'a mut PyReadwriteArray<'_, T, D>,
    name: &str,
) -> PyResult<&'a mut [T]> {
    if !a.is_c_contiguous() {
        return Err(PyValueError::new_err(format!(
            "{name} must be C-contiguous"
        )));
    }
    Ok(a.as_slice_mut()?)
}

/// The product of buffer sizes, or a ValueError naming it on overflow (W4-2).
fn size(name: &str, factors: &[usize]) -> PyResult<usize> {
    factors
        .iter()
        .try_fold(1usize, |p, &f| p.checked_mul(f))
        .ok_or_else(|| PyValueError::new_err(format!("{name} overflows")))
}

/// Pointer of a C-contiguous input `name` of exactly `len` elements, else a
/// ValueError naming it (W4-2).
fn arg<T: Element>(a: &Ro<'_, T>, name: &str, len: usize) -> PyResult<*const T> {
    let s = c_slice(a, name)?;
    if s.len() != len {
        return Err(PyValueError::new_err(format!(
            "{name} must hold {len} elements, not {}",
            s.len()
        )));
    }
    Ok(s.as_ptr())
}

/// As `arg` for an optional input; null when absent.
fn opt_arg<T: Element>(a: &Option<Ro<'_, T>>, name: &str, len: usize) -> PyResult<*const T> {
    match a {
        None => Ok(std::ptr::null()),
        Some(a) => arg(a, name, len),
    }
}

/// As `arg` for an output.
fn arg_mut<T: Element>(a: &mut Rw<'_, T>, name: &str, len: usize) -> PyResult<*mut T> {
    let s = c_slice_mut(a, name)?;
    if s.len() != len {
        return Err(PyValueError::new_err(format!(
            "{name} must hold {len} elements, not {}",
            s.len()
        )));
    }
    Ok(s.as_mut_ptr())
}

/// As `arg_mut` for an optional output; null when absent.
fn opt_arg_mut<T: Element>(a: &mut Option<Rw<'_, T>>, name: &str, len: usize) -> PyResult<*mut T> {
    match a {
        None => Ok(std::ptr::null_mut()),
        Some(a) => arg_mut(a, name, len),
    }
}

/// Borrowed pointer of a required input array.
fn ptr<T: Element>(a: &Ro<'_, T>) -> PyResult<*const T> {
    Ok(c_slice(a, "array")?.as_ptr())
}

/// Borrowed pointer of an optional input array; null when absent.
fn opt_ptr<T: Element>(a: &Option<Ro<'_, T>>) -> PyResult<*const T> {
    match a {
        None => Ok(std::ptr::null()),
        Some(a) => ptr(a),
    }
}

/// Borrowed pointer of a required output array.
fn ptr_mut<T: Element>(a: &mut Rw<'_, T>) -> PyResult<*mut T> {
    Ok(c_slice_mut(a, "array")?.as_mut_ptr())
}

/// Borrowed pointer of an optional output array; null when absent.
fn opt_ptr_mut<T: Element>(a: &mut Option<Rw<'_, T>>) -> PyResult<*mut T> {
    match a {
        None => Ok(std::ptr::null_mut()),
        Some(a) => ptr_mut(a),
    }
}

/// Pointer of an input that must hold exactly `len` elements.
fn sized<T: Element>(a: &Ro<'_, T>, len: usize) -> PyResult<Option<*const T>> {
    let s = c_slice(a, "array")?;
    Ok((s.len() == len).then_some(s.as_ptr()))
}

/// Pointer of an output that must hold exactly `len` elements.
fn sized_mut<T: Element>(a: &mut Rw<'_, T>, len: usize) -> PyResult<Option<*mut T>> {
    let s = c_slice_mut(a, "array")?;
    Ok((s.len() == len).then_some(s.as_mut_ptr()))
}

/// The address the extension reads an array at, through the same
/// `as_slice` path every function uses (criterion 4 of the protocol).
#[pyfunction]
fn data_address(array: &Bound<'_, PyAny>) -> PyResult<usize> {
    fn address<T: Element>(a: Ro<'_, T>) -> PyResult<usize> {
        Ok(c_slice(&a, "array")?.as_ptr() as usize)
    }
    if let Ok(a) = array.extract::<Ro<'_, f32>>() {
        return address(a);
    }
    if let Ok(a) = array.extract::<Ro<'_, f64>>() {
        return address(a);
    }
    if let Ok(a) = array.extract::<Ro<'_, u8>>() {
        return address(a);
    }
    if let Ok(a) = array.extract::<Ro<'_, i8>>() {
        return address(a);
    }
    if let Ok(a) = array.extract::<Ro<'_, u32>>() {
        return address(a);
    }
    if let Ok(a) = array.extract::<Ro<'_, i32>>() {
        return address(a);
    }
    if let Ok(a) = array.extract::<Ro<'_, u64>>() {
        return address(a);
    }
    if let Ok(a) = array.extract::<Ro<'_, usize>>() {
        return address(a);
    }
    Err(PyValueError::new_err("unsupported array dtype"))
}

/// `rang_core_fused` on NumPy buffers; returns its status code.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn fused(
    py: Python<'_>,
    nrow: usize,
    nchan: usize,
    ntime_bins: usize,
    nfreq_bins: usize,
    nant: usize,
    data: Ro<'_, f32>,
    weights: Ro<'_, f32>,
    model_stored: Option<Ro<'_, f32>>,
    model_scalar: Option<Ro<'_, f64>>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    time_bin: Ro<'_, u32>,
    freq_bin: Ro<'_, u32>,
    gains: Ro<'_, f64>,
    gain_valid: Ro<'_, u8>,
    split: Ro<'_, u8>,
    mut residuals: Option<Rw<'_, f64>>,
    mut scores: Option<Rw<'_, f64>>,
    mut diag_h: Option<Rw<'_, f64>>,
    mut diag_b: Option<Rw<'_, f64>>,
    mut diag_count: Option<Rw<'_, u64>>,
    mut split_stats: Rw<'_, f64>,
) -> PyResult<i32> {
    let cells = size("nrow * nchan", &[nrow, nchan])?;
    let ngain = size(
        "ntime_bins * nfreq_bins * nant",
        &[ntime_bins, nfreq_bins, nant],
    )?;
    let (c8, g8, g64) = (
        size("8 * nrow * nchan", &[8, cells])?,
        size("8 * gains", &[8, ngain])?,
        size("64 * gains", &[64, ngain])?,
    );
    let inputs = ffi::FusedInputs {
        nrow,
        nchan,
        ntime_bins,
        nfreq_bins,
        nant,
        data: arg(&data, "data", c8)?,
        weights: arg(&weights, "weights", 4 * cells)?,
        model_stored: opt_arg(&model_stored, "model_stored", c8)?,
        model_scalar: opt_arg(&model_scalar, "model_scalar", nchan)?,
        antenna1: arg(&antenna1, "antenna1", nrow)?,
        antenna2: arg(&antenna2, "antenna2", nrow)?,
        time_bin: arg(&time_bin, "time_bin", nrow)?,
        freq_bin: arg(&freq_bin, "freq_bin", nchan)?,
        gains: arg(&gains, "gains", g8)?,
        gain_valid: arg(&gain_valid, "gain_valid", ngain)?,
        split: arg(&split, "split", cells)?,
    };
    let mut outputs = ffi::FusedOutputs {
        residuals: opt_arg_mut(&mut residuals, "residuals", c8)?,
        scores: opt_arg_mut(&mut scores, "scores", cells)?,
        diag_h: opt_arg_mut(&mut diag_h, "diag_h", g64)?,
        diag_b: opt_arg_mut(&mut diag_b, "diag_b", g8)?,
        diag_count: opt_arg_mut(&mut diag_count, "diag_count", ngain)?,
        split_stats: arg_mut(
            &mut split_stats,
            "split_stats",
            4 * rang_core::fused::SPLITS,
        )?,
    };
    // SAFETY: every pointer borrows a live, C-contiguous NumPy buffer held by
    // the arguments for the duration of the call, of the length the C ABI
    // documents (checked above).
    Ok(detach(py, || unsafe {
        ffi::rang_core_fused(&inputs, &mut outputs)
    }))
}

/// `rang_core_solve_options_parse`; returns (status, transposed qp weights,
/// stop code, tolerance, anderson, freeze), the parts `solve_complex` takes.
#[pyfunction]
fn solve_options_parse(text: &str) -> (i32, u8, u8, f64, usize, u8) {
    let mut out = ffi::SolveOptions::default();
    // SAFETY: `text` is a live UTF-8 buffer of its length; `out` is local.
    let status = unsafe { ffi::rang_core_solve_options_parse(text.as_ptr(), text.len(), &mut out) };
    (
        status,
        out.transposed_qp_weights,
        out.stop,
        out.tolerance,
        out.anderson,
        out.freeze,
    )
}

/// `rang_core_solve_complex`; returns (status, iterations, converged fraction).
/// `options` are the parts from `solve_options_parse` and `trace` the trace
/// file or None (task W4-1: the core no longer reads the environment).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn solve_complex(
    py: Python<'_>,
    nrow: usize,
    nchan: usize,
    ntime_bins: usize,
    nfreq_bins: usize,
    nant: usize,
    data: Ro<'_, f32>,
    weights: Ro<'_, f32>,
    model_stored: Option<Ro<'_, f32>>,
    model_scalar: Option<Ro<'_, f64>>,
    flag: Ro<'_, u8>,
    flag_row: Ro<'_, u8>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    time_bin: Ro<'_, u32>,
    freq_bin: Ro<'_, u32>,
    max_iterations: usize,
    stop_criterion: f64,
    stop_fraction: f64,
    mut gains: Rw<'_, f64>,
    mut flags: Rw<'_, i8>,
    options: (u8, u8, f64, usize, u8),
    trace: Option<String>,
) -> PyResult<(i32, usize, f64)> {
    // Every buffer's length and order (task W4-2): a ValueError naming it.
    let cells = size("nrow * nchan", &[nrow, nchan])?;
    let ngain = size(
        "ntime_bins * nfreq_bins * nant",
        &[ntime_bins, nfreq_bins, nant],
    )?;
    let (c8, g8) = (
        size("8 * nrow * nchan", &[8, cells])?,
        size("8 * gains", &[8, ngain])?,
    );
    arg(&data, "data", c8)?;
    arg(&weights, "weights", 4 * cells)?;
    opt_arg(&model_stored, "model_stored", c8)?;
    opt_arg(&model_scalar, "model_scalar", nchan)?;
    arg(&flag, "flag", 4 * cells)?;
    arg(&flag_row, "flag_row", nrow)?;
    arg(&antenna1, "antenna1", nrow)?;
    arg(&antenna2, "antenna2", nrow)?;
    arg(&time_bin, "time_bin", nrow)?;
    arg(&freq_bin, "freq_bin", nchan)?;
    arg_mut(&mut gains, "gains", g8)?;
    arg_mut(&mut flags, "flags", ngain)?;
    let (transposed_qp_weights, stop, tolerance, anderson, freeze) = options;
    let trace = trace.unwrap_or_default();
    let inputs = ffi::SolveInputs {
        nrow,
        nchan,
        ntime_bins,
        nfreq_bins,
        nant,
        data: ptr(&data)?,
        weights: ptr(&weights)?,
        model_stored: opt_ptr(&model_stored)?,
        model_scalar: opt_ptr(&model_scalar)?,
        flag: ptr(&flag)?,
        flag_row: ptr(&flag_row)?,
        antenna1: ptr(&antenna1)?,
        antenna2: ptr(&antenna2)?,
        time_bin: ptr(&time_bin)?,
        freq_bin: ptr(&freq_bin)?,
        max_iterations,
        stop_criterion,
        stop_fraction,
        options: ffi::SolveOptions {
            transposed_qp_weights,
            stop,
            tolerance,
            anderson,
            freeze,
        },
        trace: trace.as_ptr(),
        trace_len: trace.len(),
    };
    let mut iterations = 0usize;
    let mut converged = 0f64;
    let mut outputs = ffi::SolveOutputs {
        gains: ptr_mut(&mut gains)?,
        flags: ptr_mut(&mut flags)?,
        iterations: &mut iterations,
        converged_fraction: &mut converged,
    };
    // SAFETY: as in `fused`.
    let status = detach(py, || unsafe {
        ffi::rang_core_solve_complex(&inputs, &mut outputs)
    });
    Ok((status, iterations, converged))
}

/// `rang_core_predict_components`; returns its status code.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn predict_components(
    py: Python<'_>,
    nrow: usize,
    nchan: usize,
    nsrc: usize,
    ncoeff: usize,
    uvw: Ro<'_, f64>,
    frequency: Ro<'_, f64>,
    lm: Ro<'_, f64>,
    kind: Ro<'_, u8>,
    flux: Ro<'_, f64>,
    coeffs: Ro<'_, f64>,
    log_poly: Ro<'_, u8>,
    ref_freq: Ro<'_, f64>,
    gauss_shape: Ro<'_, f64>,
    mut vis: Rw<'_, f64>,
    mut spectra: Option<Rw<'_, f64>>,
) -> PyResult<i32> {
    let (r3, s2, s3) = (
        size("3 * nrow", &[3, nrow])?,
        size("2 * nsrc", &[2, nsrc])?,
        size("3 * nsrc", &[3, nsrc])?,
    );
    let inputs = ffi::PredictInputs {
        nrow,
        nchan,
        nsrc,
        ncoeff,
        uvw: arg(&uvw, "uvw", r3)?,
        frequency: arg(&frequency, "frequency", nchan)?,
        lm: arg(&lm, "lm", s2)?,
        kind: arg(&kind, "kind", nsrc)?,
        flux: arg(&flux, "flux", nsrc)?,
        coeffs: arg(&coeffs, "coeffs", size("nsrc * ncoeff", &[nsrc, ncoeff])?)?,
        log_poly: arg(&log_poly, "log_poly", nsrc)?,
        ref_freq: arg(&ref_freq, "ref_freq", nsrc)?,
        gauss_shape: arg(&gauss_shape, "gauss_shape", s3)?,
    };
    let mut outputs = ffi::PredictOutputs {
        vis: arg_mut(
            &mut vis,
            "vis",
            size("2 * nrow * nchan", &[2, nrow, nchan])?,
        )?,
        spectra: opt_arg_mut(
            &mut spectra,
            "spectra",
            size("nsrc * nchan", &[nsrc, nchan])?,
        )?,
    };
    // SAFETY: as in `fused`.
    Ok(detach(py, || unsafe {
        ffi::rang_core_predict_components(&inputs, &mut outputs)
    }))
}

/// `rang_core_blosc_size`; returns (status, decoded length).
#[pyfunction]
fn blosc_size(payload: &[u8]) -> (i32, usize) {
    let mut nbytes = 0usize;
    // SAFETY: `payload` is a live byte slice; `nbytes` one writable usize.
    let status = unsafe { ffi::rang_core_blosc_size(payload.as_ptr(), payload.len(), &mut nbytes) };
    (status, nbytes)
}

/// `rang_core_blosc_decode` into a new `bytes` of `size` bytes; returns
/// (status, bytes).
#[pyfunction]
fn blosc_decode<'py>(
    py: Python<'py>,
    payload: &[u8],
    size: usize,
) -> PyResult<(i32, Bound<'py, PyBytes>)> {
    let mut status = 0;
    let out = PyBytes::new_with(py, size, |buf| {
        // SAFETY: `buf` is the fresh bytes object's buffer of `size` bytes;
        // `payload` borrows an immutable bytes object held by the caller.
        status = detach(py, || unsafe {
            ffi::rang_core_blosc_decode(
                payload.as_ptr(),
                payload.len(),
                buf.as_mut_ptr(),
                buf.len(),
            )
        });
        Ok(())
    })?;
    Ok((status, out))
}

/// `rang_core_blosc_decode_rows` into a new `bytes`; returns
/// (status, blocks decoded, bytes).
#[pyfunction]
fn blosc_decode_rows<'py>(
    py: Python<'py>,
    payload: &[u8],
    row_bytes: usize,
    rows: Ro<'_, usize>,
) -> PyResult<(i32, usize, Bound<'py, PyBytes>)> {
    let rows = c_slice(&rows, "rows")?;
    let mut status = 0;
    let mut blocks = 0usize;
    let nbytes = size("len(rows) * row_bytes", &[rows.len(), row_bytes])?;
    let out = PyBytes::new_with(py, nbytes, |buf| {
        // SAFETY: `buf` holds `nrows * row_bytes` bytes; `rows` is live.
        status = detach(py, || unsafe {
            ffi::rang_core_blosc_decode_rows(
                payload.as_ptr(),
                payload.len(),
                row_bytes,
                rows.as_ptr(),
                rows.len(),
                buf.as_mut_ptr(),
                &mut blocks,
            )
        });
        Ok(())
    })?;
    Ok((status, blocks, out))
}

/// `rang_core_blosc_header`; returns (status, (nbytes, blocksize, nblocks,
/// typesize)).
#[pyfunction]
fn blosc_header(head: &[u8]) -> (i32, (usize, usize, usize, usize)) {
    let mut fields = [0usize; 4];
    // SAFETY: `head` is a live byte slice; `fields` four writable values.
    let status =
        unsafe { ffi::rang_core_blosc_header(head.as_ptr(), head.len(), fields.as_mut_ptr()) };
    (status, (fields[0], fields[1], fields[2], fields[3]))
}

/// `rang_core_blosc_decode_block` into a caller-owned uint8 array.
#[pyfunction]
fn blosc_decode_block(
    py: Python<'_>,
    head: &[u8],
    j: usize,
    block: &[u8],
    mut out: Rw<'_, u8>,
) -> PyResult<i32> {
    let out = c_slice_mut(&mut out, "out")?;
    // SAFETY: every slice is live for the call.
    Ok(detach(py, || unsafe {
        ffi::rang_core_blosc_decode_block(
            head.as_ptr(),
            head.len(),
            j,
            block.as_ptr(),
            block.len(),
            out.as_mut_ptr(),
            out.len(),
        )
    }))
}

/// `rang_core_blosc_decode_span_rows` into a caller-owned uint8 array of
/// `len(rows) * row_bytes` bytes.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn blosc_decode_span_rows(
    py: Python<'_>,
    head: &[u8],
    first: usize,
    count: usize,
    span: &[u8],
    row_bytes: usize,
    rows: Ro<'_, usize>,
    mut out: Rw<'_, u8>,
) -> PyResult<i32> {
    let rows = c_slice(&rows, "rows")?;
    let out = c_slice_mut(&mut out, "out")?;
    if Some(out.len()) != rows.len().checked_mul(row_bytes) {
        return Ok(1);
    }
    // SAFETY: every slice is live for the call and `out` has the documented length.
    Ok(detach(py, || unsafe {
        ffi::rang_core_blosc_decode_span_rows(
            head.as_ptr(),
            head.len(),
            first,
            count,
            span.as_ptr(),
            span.len(),
            row_bytes,
            rows.as_ptr(),
            rows.len(),
            out.as_mut_ptr(),
        )
    }))
}

/// `rang_core_correct_stokes_i` on borrowed arrays (big plan P5,
/// `research/p5-memory.md`); `added` may be None. Returns the C status.
#[pyfunction]
#[pyo3(signature = (nrow, nchan, ntime_bins, nfreq_bins, nant, data, weights, flags, flag_row, added, antenna1, antenna2, time_bin, freq_bin, inverse, valid, sample, weight))]
#[allow(clippy::too_many_arguments)]
fn correct_stokes_i(
    py: Python<'_>,
    nrow: usize,
    nchan: usize,
    ntime_bins: usize,
    nfreq_bins: usize,
    nant: usize,
    data: Ro<'_, f32>,
    weights: Ro<'_, f32>,
    flags: Ro<'_, u8>,
    flag_row: Ro<'_, u8>,
    added: Option<Ro<'_, u8>>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    time_bin: Ro<'_, u32>,
    freq_bin: Ro<'_, u32>,
    inverse: Ro<'_, f64>,
    valid: Ro<'_, u8>,
    mut sample: Rw<'_, f32>,
    mut weight: Rw<'_, f32>,
) -> PyResult<i32> {
    let Some(cells) = nrow.checked_mul(nchan) else {
        return Ok(1);
    };
    // `8 * cells` and `8 * gains` below must not wrap either (W4-2).
    let Ok(gains) = size("gains", &[ntime_bins, nfreq_bins, nant]) else {
        return Ok(1);
    };
    if cells.checked_mul(8).is_none() || gains.checked_mul(8).is_none() {
        return Ok(1);
    }
    let (data, weights, flags, flag_row) = (
        c_slice(&data, "data")?,
        c_slice(&weights, "weights")?,
        c_slice(&flags, "flags")?,
        c_slice(&flag_row, "flag_row")?,
    );
    let added = match &added {
        Some(a) => Some(c_slice(a, "added")?),
        None => None,
    };
    let (antenna1, antenna2, time_bin, freq_bin) = (
        c_slice(&antenna1, "antenna1")?,
        c_slice(&antenna2, "antenna2")?,
        c_slice(&time_bin, "time_bin")?,
        c_slice(&freq_bin, "freq_bin")?,
    );
    let (inverse, valid) = (c_slice(&inverse, "inverse")?, c_slice(&valid, "valid")?);
    let (sample, weight) = (
        c_slice_mut(&mut sample, "sample")?,
        c_slice_mut(&mut weight, "weight")?,
    );
    if data.len() != 8 * cells
        || weights.len() != 4 * cells
        || flags.len() != 4 * cells
        || flag_row.len() != nrow
        || added.is_some_and(|a| a.len() != cells)
        || antenna1.len() != nrow
        || antenna2.len() != nrow
        || time_bin.len() != nrow
        || freq_bin.len() != nchan
        || inverse.len() != 8 * gains
        || valid.len() != gains
        || sample.len() != 2 * cells
        || weight.len() != cells
    {
        return Ok(1);
    }
    let inputs = CorrectInputsC {
        nrow,
        nchan,
        ntime_bins,
        nfreq_bins,
        nant,
        data: data.as_ptr(),
        weights: weights.as_ptr(),
        flags: flags.as_ptr(),
        flag_row: flag_row.as_ptr(),
        added: added.map_or(std::ptr::null(), |a| a.as_ptr()),
        antenna1: antenna1.as_ptr(),
        antenna2: antenna2.as_ptr(),
        time_bin: time_bin.as_ptr(),
        freq_bin: freq_bin.as_ptr(),
        inverse: inverse.as_ptr(),
        valid: valid.as_ptr(),
    };
    // SAFETY: every slice is live for the call and has the length checked above.
    Ok(detach(py, || unsafe {
        rang_core::ffi_correct::rang_core_correct_stokes_i(
            &inputs,
            sample.as_mut_ptr(),
            weight.as_mut_ptr(),
        )
    }))
}

/// `rang_core_blosc_decode_span_rows_strided`: rows land at byte
/// `offset + i * stride` of the caller-owned uint8 array `out` (P5).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn blosc_decode_span_rows_strided(
    py: Python<'_>,
    head: &[u8],
    first: usize,
    count: usize,
    span: Ro<'_, u8>,
    row_bytes: usize,
    rows: Ro<'_, usize>,
    mut out: Rw<'_, u8>,
    offset: usize,
    stride: usize,
) -> PyResult<i32> {
    let (span, rows) = (c_slice(&span, "span")?, c_slice(&rows, "rows")?);
    let out = c_slice_mut(&mut out, "out")?;
    if offset > out.len() {
        return Ok(1);
    }
    let out = &mut out[offset..];
    // SAFETY: every slice is live for the call; `out` bounds the writes.
    Ok(detach(py, || unsafe {
        rang_core::ffi_correct::rang_core_blosc_decode_span_rows_strided(
            head.as_ptr(),
            head.len(),
            first,
            count,
            span.as_ptr(),
            span.len(),
            row_bytes,
            rows.as_ptr(),
            rows.len(),
            out.as_mut_ptr(),
            out.len(),
            stride,
        )
    }))
}

/// `rang_core_weight_grid_shape`; returns (status, width, height).
#[pyfunction]
fn weight_grid_shape(width: usize, height: usize, super_weight: f64) -> (i32, usize, usize) {
    let mut shape = [0usize; 2];
    // SAFETY: `shape` holds two writable values.
    let status = unsafe {
        rang_core::ffi_weights::rang_core_weight_grid_shape(
            width,
            height,
            super_weight,
            shape.as_mut_ptr(),
        )
    };
    (status, shape[0], shape[1])
}

/// `rang_core_padded_size`.
#[pyfunction]
fn padded_size(trimmed: usize, padding: f64) -> usize {
    rang_core::ffi_weights::rang_core_padded_size(trimmed, padding)
}

/// `rang_core_stokes_i`; returns its status code.
#[pyfunction]
fn stokes_i(
    py: Python<'_>,
    ncell: usize,
    data: Ro<'_, f32>,
    weights: Ro<'_, f32>,
    flags: Ro<'_, u8>,
    mut vis: Rw<'_, f32>,
    mut weight: Rw<'_, f32>,
) -> PyResult<i32> {
    let c4 = size("4 * ncell", &[4, ncell])?;
    let inputs = StokesIInputs {
        ncell,
        data: arg(&data, "data", size("8 * ncell", &[8, ncell])?)?,
        weights: arg(&weights, "weights", c4)?,
        flags: arg(&flags, "flags", c4)?,
    };
    let mut outputs = StokesIOutputs {
        vis: arg_mut(&mut vis, "vis", 2 * ncell)?,
        weight: arg_mut(&mut weight, "weight", ncell)?,
    };
    // SAFETY: as in `fused`.
    Ok(detach(py, || unsafe {
        rang_core::ffi_weights::rang_core_stokes_i(&inputs, &mut outputs)
    }))
}

/// `rang_core_imaging_weights`; returns its status code.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn imaging_weights(
    py: Python<'_>,
    nrow: usize,
    nchan: usize,
    uvw: Ro<'_, f64>,
    wavelength: Ro<'_, f64>,
    weights: Ro<'_, f32>,
    row_selected: Ro<'_, u8>,
    class: u32,
    robust: f64,
    width: usize,
    height: usize,
    pixel_scale_x: f64,
    pixel_scale_y: f64,
    super_weight: f64,
    rank_filter_level: f64,
    rank_filter_size: usize,
    mut out_weights: Rw<'_, f32>,
    mut grid: Option<Rw<'_, f64>>,
    mut sums: Option<Rw<'_, f64>>,
) -> PyResult<i32> {
    let cells = size("nrow * nchan", &[nrow, nchan])?;
    // The grid's length follows `rang_core_weight_grid_shape`; with an
    // invalid super weight the kernel returns 1 before writing it.
    let grid_len = if super_weight > 0.0 {
        let (w, h) = rang_core::weights::WeightGrid::shape(width, height, super_weight);
        size("grid width * height", &[w, h])? / 2
    } else {
        0
    };
    let inputs = ImagingWeightInputs {
        nrow,
        nchan,
        uvw: arg(&uvw, "uvw", size("3 * nrow", &[3, nrow])?)?,
        wavelength: arg(&wavelength, "wavelength", nchan)?,
        weights: arg(&weights, "weights", cells)?,
        row_selected: arg(&row_selected, "row_selected", nrow)?,
        class,
        robust,
        width,
        height,
        pixel_scale_x,
        pixel_scale_y,
        super_weight,
        rank_filter_level,
        rank_filter_size,
    };
    let mut outputs = ImagingWeightOutputs {
        weights: arg_mut(&mut out_weights, "out_weights", cells)?,
        grid: if super_weight > 0.0 {
            opt_arg_mut(&mut grid, "grid", grid_len)?
        } else {
            opt_ptr_mut(&mut grid)?
        },
        sums: opt_arg_mut(&mut sums, "sums", 4)?,
    };
    // SAFETY: as in `fused`.
    Ok(detach(py, || unsafe {
        rang_core::ffi_weights::rang_core_imaging_weights(&inputs, &mut outputs)
    }))
}

/// `rang_core_grid_invert`; returns its status code.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn grid_invert(
    py: Python<'_>,
    nrow: usize,
    nchan: usize,
    width: usize,
    height: usize,
    kernel_size: usize,
    oversampling: usize,
    n_w_layers: usize,
    pixel_size_x: f64,
    pixel_size_y: f64,
    padding: f64,
    uvw: Ro<'_, f64>,
    frequencies: Ro<'_, f64>,
    data: Ro<'_, f32>,
    weights: Ro<'_, f32>,
    imaging_weights: Ro<'_, f32>,
    mut dirty: Rw<'_, f64>,
    mut psf: Rw<'_, f64>,
    mut stats: Rw<'_, f64>,
) -> PyResult<i32> {
    let cells = size("nrow * nchan", &[nrow, nchan])?;
    let pixels = size("width * height", &[width, height])?;
    let inputs = GridInputs {
        nrow,
        nchan,
        width,
        height,
        kernel_size,
        oversampling,
        n_w_layers,
        pixel_size_x,
        pixel_size_y,
        padding,
        uvw: arg(&uvw, "uvw", size("3 * nrow", &[3, nrow])?)?,
        frequencies: arg(&frequencies, "frequencies", nchan)?,
        data: arg(&data, "data", size("2 * nrow * nchan", &[2, cells])?)?,
        weights: arg(&weights, "weights", cells)?,
        imaging_weights: arg(&imaging_weights, "imaging_weights", cells)?,
    };
    let mut outputs = GridOutputs {
        dirty: arg_mut(&mut dirty, "dirty", pixels)?,
        psf: arg_mut(&mut psf, "psf", pixels)?,
        stats: arg_mut(&mut stats, "stats", rang_core::ffi_grid::N_STATS)?,
    };
    // SAFETY: as in `fused`.
    Ok(detach(py, || unsafe {
        rang_core::ffi_grid::rang_core_grid_invert(&inputs, &mut outputs)
    }))
}

/// `rang_core::gpu::ffi::grid_invert` (task X2, research/x2-wgpu.md):
/// `grid_invert`'s buffers plus the precision (`"f64"` or `"f32"`) and a
/// float64 array of `N_TIMINGS` timings; returns 0, or raises RuntimeError
/// with the reason when the GPU path fails.
#[cfg(feature = "gpu")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn grid_invert_gpu(
    py: Python<'_>,
    nrow: usize,
    nchan: usize,
    width: usize,
    height: usize,
    kernel_size: usize,
    oversampling: usize,
    n_w_layers: usize,
    pixel_size_x: f64,
    pixel_size_y: f64,
    padding: f64,
    uvw: Ro<'_, f64>,
    frequencies: Ro<'_, f64>,
    data: Ro<'_, f32>,
    weights: Ro<'_, f32>,
    imaging_weights: Ro<'_, f32>,
    precision: &str,
    mut dirty: Rw<'_, f64>,
    mut psf: Rw<'_, f64>,
    mut stats: Rw<'_, f64>,
    mut timings: Rw<'_, f64>,
) -> PyResult<i32> {
    let precision = rang_core::gpu::Precision::parse(precision).map_err(PyValueError::new_err)?;
    let cells = size("nrow * nchan", &[nrow, nchan])?;
    let pixels = size("width * height", &[width, height])?;
    let inputs = GridInputs {
        nrow,
        nchan,
        width,
        height,
        kernel_size,
        oversampling,
        n_w_layers,
        pixel_size_x,
        pixel_size_y,
        padding,
        uvw: arg(&uvw, "uvw", size("3 * nrow", &[3, nrow])?)?,
        frequencies: arg(&frequencies, "frequencies", nchan)?,
        data: arg(&data, "data", size("2 * nrow * nchan", &[2, cells])?)?,
        weights: arg(&weights, "weights", cells)?,
        imaging_weights: arg(&imaging_weights, "imaging_weights", cells)?,
    };
    let mut outputs = GridOutputs {
        dirty: arg_mut(&mut dirty, "dirty", pixels)?,
        psf: arg_mut(&mut psf, "psf", pixels)?,
        stats: arg_mut(&mut stats, "stats", rang_core::ffi_grid::N_STATS)?,
    };
    let timings = arg_mut(&mut timings, "timings", rang_core::gpu::ffi::N_TIMINGS)?;
    // SAFETY: as in `fused`; `timings` holds N_TIMINGS doubles.
    detach(py, || unsafe {
        rang_core::gpu::ffi::grid_invert(&inputs, &mut outputs, precision, timings)
    })
    .map(|()| 0)
    .map_err(PyRuntimeError::new_err)
}

/// The adapter the GPU gridder uses (created on first call); RuntimeError
/// when none is usable.
#[cfg(feature = "gpu")]
#[pyfunction]
fn grid_gpu_adapter(py: Python<'_>) -> PyResult<String> {
    detach(py, rang_core::gpu::adapter_description).map_err(PyRuntimeError::new_err)
}

/// `rang_core_grid_kernel` into a caller-owned float64 array; 2 on a panic
/// of the kernel (task P7; before, `(7, 2)` aborted the process).
#[pyfunction]
fn grid_kernel(
    py: Python<'_>,
    kernel_size: usize,
    oversampling: usize,
    mut kernel: Rw<'_, f64>,
) -> PyResult<i32> {
    let out = c_slice_mut(&mut kernel, "kernel")?;
    if Some(out.len()) != kernel_size.checked_mul(oversampling) {
        return Ok(1);
    }
    // SAFETY: `out` has the documented length.
    Ok(detach(py, || unsafe {
        rang_core::ffi_grid::rang_core_grid_kernel(kernel_size, oversampling, out.as_mut_ptr())
    }))
}

// ------------------------------------------- exact gridder (DF2b bindings)

/// `WgridderOptions` from its 18 fields in declaration order (sizes and
/// flags as floats; every value is exact in a double).
fn wgridder_options(o: &[f64]) -> PyResult<WgridderOptions> {
    if o.len() != 18 {
        return Err(PyValueError::new_err("18 gridder options required"));
    }
    Ok(WgridderOptions {
        nx: o[0] as usize,
        ny: o[1] as usize,
        pixsize_x: o[2],
        pixsize_y: o[3],
        epsilon: o[4],
        center_x: o[5],
        center_y: o[6],
        sigma_min: o[7],
        sigma_max: o[8],
        do_wgridding: o[9] as i32,
        divide_by_n: o[10] as i32,
        flip_u: o[11] as i32,
        flip_v: o[12] as i32,
        flip_w: o[13] as i32,
        allow_nshift: o[14] as i32,
        kernel_index: o[15] as i64,
        nu: o[16] as usize,
        nv: o[17] as usize,
    })
}

/// A borrowed visibility array of either complex precision (or none:
/// unit visibilities).
enum VisArg<'py> {
    Unit,
    C64(Ro<'py, Complex32>),
    C128(Ro<'py, Complex64>),
}

impl<'py> VisArg<'py> {
    fn extract(a: Option<&Bound<'py, PyAny>>) -> PyResult<Self> {
        let Some(a) = a else {
            return Ok(VisArg::Unit);
        };
        if let Ok(v) = a.extract::<Ro<'py, Complex32>>() {
            return Ok(VisArg::C64(v));
        }
        if let Ok(v) = a.extract::<Ro<'py, Complex64>>() {
            return Ok(VisArg::C128(v));
        }
        Err(PyValueError::new_err("vis must be complex64 or complex128"))
    }

    fn len(&self) -> Option<usize> {
        match self {
            VisArg::Unit => None,
            VisArg::C64(v) => Some(v.as_array().len()),
            VisArg::C128(v) => Some(v.as_array().len()),
        }
    }

    fn ptr_kind(&self) -> PyResult<(*const c_void, i32)> {
        Ok(match self {
            VisArg::Unit => (std::ptr::null(), ffi_wgridder::WGRIDDER_VIS_UNIT),
            VisArg::C64(v) => (ptr(v)? as *const c_void, ffi_wgridder::WGRIDDER_VIS_C64),
            VisArg::C128(v) => (ptr(v)? as *const c_void, ffi_wgridder::WGRIDDER_VIS_C128),
        })
    }
}

/// A borrowed weight array of either real precision, or none.
enum WgtArg<'py> {
    None,
    F32(Ro<'py, f32>),
    F64(Ro<'py, f64>),
}

impl<'py> WgtArg<'py> {
    fn extract(a: Option<&Bound<'py, PyAny>>) -> PyResult<Self> {
        let Some(a) = a else {
            return Ok(WgtArg::None);
        };
        if let Ok(w) = a.extract::<Ro<'py, f32>>() {
            return Ok(WgtArg::F32(w));
        }
        if let Ok(w) = a.extract::<Ro<'py, f64>>() {
            return Ok(WgtArg::F64(w));
        }
        Err(PyValueError::new_err("weights must be float32 or float64"))
    }

    fn len(&self) -> Option<usize> {
        match self {
            WgtArg::None => None,
            WgtArg::F32(w) => Some(w.as_array().len()),
            WgtArg::F64(w) => Some(w.as_array().len()),
        }
    }

    fn ptr_kind(&self) -> PyResult<(*const c_void, i32)> {
        Ok(match self {
            WgtArg::None => (std::ptr::null(), ffi_wgridder::WGRIDDER_WGT_NONE),
            WgtArg::F32(w) => (ptr(w)? as *const c_void, ffi_wgridder::WGRIDDER_WGT_F32),
            WgtArg::F64(w) => (ptr(w)? as *const c_void, ffi_wgridder::WGRIDDER_WGT_F64),
        })
    }
}

/// The `_ex2` gridding entry point of one precision.
type V2dFn<T> = unsafe extern "C" fn(
    *const WgridderOptions,
    usize,
    usize,
    *const f64,
    *const f64,
    *const c_void,
    i32,
    *const c_void,
    *const c_void,
    i32,
    *const u8,
    *mut T,
    *mut T,
    *mut f64,
) -> i32;

/// The `_ex` degridding entry point of one precision.
type D2vFn<T> = unsafe extern "C" fn(
    *const WgridderOptions,
    usize,
    usize,
    *const f64,
    *const f64,
    *const T,
    *const c_void,
    i32,
    *const u8,
    *mut T,
    *mut f64,
) -> i32;

/// One gridding call of either precision through the `_ex2` entry point.
#[allow(clippy::too_many_arguments)]
fn wgridder_v2d<T: Element>(
    py: Python<'_>,
    opts: Vec<f64>,
    uvw: Ro<'_, f64>,
    freq: Ro<'_, f64>,
    vis: Option<&Bound<'_, PyAny>>,
    wgt: Option<&Bound<'_, PyAny>>,
    wgt2: Option<Ro<'_, f32>>,
    mask: Option<Ro<'_, u8>>,
    mut dirty: Option<Rw<'_, T>>,
    mut psf: Option<Rw<'_, T>>,
    mut info: Rw<'_, f64>,
    run: V2dFn<T>,
) -> PyResult<i32> {
    let opts = wgridder_options(&opts)?;
    let nrow = uvw.as_array().len() / 3;
    let nchan = freq.as_array().len();
    let n = size("nrow * nchan", &[nrow, nchan])?;
    let npix = size("nx * ny", &[opts.nx, opts.ny])?;
    let vis = VisArg::extract(vis)?;
    let wgt = WgtArg::extract(wgt)?;
    let (vis_ptr, vis_kind) = vis.ptr_kind()?;
    let (wgt_ptr, mut wgt_kind) = wgt.ptr_kind()?;
    let wgt2_ptr = match &wgt2 {
        None => std::ptr::null(),
        Some(b) => {
            // Two weights: both float32, multiplied in the core.
            if wgt_kind != ffi_wgridder::WGRIDDER_WGT_F32 {
                return Err(PyValueError::new_err("two weights must both be float32"));
            }
            wgt_kind = ffi_wgridder::WGRIDDER_WGT_F32_PRODUCT;
            ptr(b)? as *const c_void
        }
    };
    let sizes_ok = uvw.as_array().len() == nrow * 3
        && vis.len().is_none_or(|l| l == n)
        && wgt.len().is_none_or(|l| l == n)
        && wgt2.as_ref().is_none_or(|b| b.as_array().len() == n)
        && mask.as_ref().is_none_or(|m| m.as_array().len() == n)
        && dirty.as_ref().is_none_or(|d| d.as_array().len() == npix)
        && psf.as_ref().is_none_or(|d| d.as_array().len() == npix)
        && info.as_array().len() == rang_core::wgridder::N_INFO;
    if !sizes_ok {
        return Err(PyValueError::new_err("gridder array sizes disagree"));
    }
    let uvw_ptr = ptr(&uvw)?;
    let freq_ptr = ptr(&freq)?;
    let mask_ptr = opt_ptr(&mask)?;
    let dirty_ptr = opt_ptr_mut(&mut dirty)?;
    let psf_ptr = opt_ptr_mut(&mut psf)?;
    let info_ptr = ptr_mut(&mut info)?;
    // SAFETY: every pointer borrows a live NumPy buffer of the checked
    // length for the duration of the call.
    Ok(detach(py, || unsafe {
        run(
            &opts, nrow, nchan, uvw_ptr, freq_ptr, vis_ptr, vis_kind, wgt_ptr, wgt2_ptr, wgt_kind,
            mask_ptr, dirty_ptr, psf_ptr, info_ptr,
        )
    }))
}

/// `rang_core_wgridder_vis2dirty_ex2_f64`: data of either complex
/// precision and weights of either real precision read in place (`wgt2`,
/// float32, multiplies a float32 `wgt` in the core); `dirty` and/or `psf`
/// float64 outputs; `info` the plan. Returns the status code.
#[pyfunction]
#[pyo3(signature = (opts, uvw, freq, vis, wgt, wgt2, mask, dirty, psf, info))]
#[allow(clippy::too_many_arguments)]
fn wgridder_vis2dirty_f64(
    py: Python<'_>,
    opts: Vec<f64>,
    uvw: Ro<'_, f64>,
    freq: Ro<'_, f64>,
    vis: Option<&Bound<'_, PyAny>>,
    wgt: Option<&Bound<'_, PyAny>>,
    wgt2: Option<Ro<'_, f32>>,
    mask: Option<Ro<'_, u8>>,
    dirty: Option<Rw<'_, f64>>,
    psf: Option<Rw<'_, f64>>,
    info: Rw<'_, f64>,
) -> PyResult<i32> {
    wgridder_v2d(
        py,
        opts,
        uvw,
        freq,
        vis,
        wgt,
        wgt2,
        mask,
        dirty,
        psf,
        info,
        ffi_wgridder::rang_core_wgridder_vis2dirty_ex2_f64,
    )
}

/// As `wgridder_vis2dirty_f64`, working in single precision (float32
/// outputs).
#[pyfunction]
#[pyo3(signature = (opts, uvw, freq, vis, wgt, wgt2, mask, dirty, psf, info))]
#[allow(clippy::too_many_arguments)]
fn wgridder_vis2dirty_f32(
    py: Python<'_>,
    opts: Vec<f64>,
    uvw: Ro<'_, f64>,
    freq: Ro<'_, f64>,
    vis: Option<&Bound<'_, PyAny>>,
    wgt: Option<&Bound<'_, PyAny>>,
    wgt2: Option<Ro<'_, f32>>,
    mask: Option<Ro<'_, u8>>,
    dirty: Option<Rw<'_, f32>>,
    psf: Option<Rw<'_, f32>>,
    info: Rw<'_, f64>,
) -> PyResult<i32> {
    wgridder_v2d(
        py,
        opts,
        uvw,
        freq,
        vis,
        wgt,
        wgt2,
        mask,
        dirty,
        psf,
        info,
        ffi_wgridder::rang_core_wgridder_vis2dirty_ex2_f32,
    )
}

/// One degridding call of either precision through the `_ex` entry point;
/// `vis` is the real view (`2 * nrow * nchan` values) of the output.
#[allow(clippy::too_many_arguments)]
fn wgridder_d2v<T: Element>(
    py: Python<'_>,
    opts: Vec<f64>,
    uvw: Ro<'_, f64>,
    freq: Ro<'_, f64>,
    dirty: Ro<'_, T>,
    wgt: Option<&Bound<'_, PyAny>>,
    mask: Option<Ro<'_, u8>>,
    mut vis: Rw<'_, T>,
    mut info: Rw<'_, f64>,
    run: D2vFn<T>,
) -> PyResult<i32> {
    let opts = wgridder_options(&opts)?;
    let nrow = uvw.as_array().len() / 3;
    let nchan = freq.as_array().len();
    let n = size("nrow * nchan", &[nrow, nchan])?;
    let wgt = WgtArg::extract(wgt)?;
    let (wgt_ptr, wgt_kind) = wgt.ptr_kind()?;
    let sizes_ok = uvw.as_array().len() == nrow * 3
        && dirty.as_array().len() == size("nx * ny", &[opts.nx, opts.ny])?
        && vis.as_array().len() == size("2 * nrow * nchan", &[2, n])?
        && wgt.len().is_none_or(|l| l == n)
        && mask.as_ref().is_none_or(|m| m.as_array().len() == n)
        && info.as_array().len() == rang_core::wgridder::N_INFO;
    if !sizes_ok {
        return Err(PyValueError::new_err("gridder array sizes disagree"));
    }
    let uvw_ptr = ptr(&uvw)?;
    let freq_ptr = ptr(&freq)?;
    let dirty_ptr = ptr(&dirty)?;
    let mask_ptr = opt_ptr(&mask)?;
    let vis_ptr = ptr_mut(&mut vis)?;
    let info_ptr = ptr_mut(&mut info)?;
    // SAFETY: as in `wgridder_v2d`.
    Ok(detach(py, || unsafe {
        run(
            &opts, nrow, nchan, uvw_ptr, freq_ptr, dirty_ptr, wgt_ptr, wgt_kind, mask_ptr, vis_ptr,
            info_ptr,
        )
    }))
}

/// `rang_core_wgridder_dirty2vis_ex_f64`; returns its status code.
#[pyfunction]
#[pyo3(signature = (opts, uvw, freq, dirty, wgt, mask, vis, info))]
#[allow(clippy::too_many_arguments)]
fn wgridder_dirty2vis_f64(
    py: Python<'_>,
    opts: Vec<f64>,
    uvw: Ro<'_, f64>,
    freq: Ro<'_, f64>,
    dirty: Ro<'_, f64>,
    wgt: Option<&Bound<'_, PyAny>>,
    mask: Option<Ro<'_, u8>>,
    vis: Rw<'_, f64>,
    info: Rw<'_, f64>,
) -> PyResult<i32> {
    wgridder_d2v(
        py,
        opts,
        uvw,
        freq,
        dirty,
        wgt,
        mask,
        vis,
        info,
        ffi_wgridder::rang_core_wgridder_dirty2vis_ex_f64,
    )
}

/// `rang_core_wgridder_dirty2vis_ex_f32`; returns its status code.
#[pyfunction]
#[pyo3(signature = (opts, uvw, freq, dirty, wgt, mask, vis, info))]
#[allow(clippy::too_many_arguments)]
fn wgridder_dirty2vis_f32(
    py: Python<'_>,
    opts: Vec<f64>,
    uvw: Ro<'_, f64>,
    freq: Ro<'_, f64>,
    dirty: Ro<'_, f32>,
    wgt: Option<&Bound<'_, PyAny>>,
    mask: Option<Ro<'_, u8>>,
    vis: Rw<'_, f32>,
    info: Rw<'_, f64>,
) -> PyResult<i32> {
    wgridder_d2v(
        py,
        opts,
        uvw,
        freq,
        dirty,
        wgt,
        mask,
        vis,
        info,
        ffi_wgridder::rang_core_wgridder_dirty2vis_ex_f32,
    )
}

/// `rang_core_wgridder_kernel_row` into seven doubles; 1 past the end.
#[pyfunction]
fn wgridder_kernel_row(index: usize, mut out: Rw<'_, f64>) -> PyResult<i32> {
    let Some(p) = sized_mut(&mut out, 7)? else {
        return Ok(1);
    };
    // SAFETY: `p` holds seven doubles.
    Ok(unsafe { ffi_wgridder::rang_core_wgridder_kernel_row(index, p) })
}

/// The message of this thread's last status-1 gridder failure.
#[pyfunction]
fn wgridder_last_error() -> String {
    // SAFETY: a null buffer asks for the length only; `buf` then holds it.
    let n = unsafe { ffi_wgridder::rang_core_wgridder_last_error(std::ptr::null_mut(), 0) };
    let mut buf = vec![0_u8; n];
    // SAFETY: `buf` holds `n` bytes.
    unsafe { ffi_wgridder::rang_core_wgridder_last_error(buf.as_mut_ptr(), n) };
    String::from_utf8_lossy(&buf).into_owned()
}

/// `rang_core_flag_rows`; returns its status code.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn flag_rows(
    py: Python<'_>,
    nrow: usize,
    nchan: usize,
    ncorr: usize,
    nant: usize,
    nbl: usize,
    ntime: usize,
    nmasks: usize,
    nsteps: usize,
    data: Ro<'_, f32>,
    flags: Ro<'_, u8>,
    baseline_index: Ro<'_, u32>,
    time_index: Ro<'_, u32>,
    baselines: Ro<'_, u32>,
    antenna_position: Ro<'_, f64>,
    chan_freq: Ro<'_, f64>,
    chan_width: Ro<'_, f64>,
    corr_type: Ro<'_, i32>,
    mask_freqs: Ro<'_, f64>,
    mask_offsets: Ro<'_, usize>,
    steps: Ro<'_, f64>,
    mut out_flags: Rw<'_, u8>,
    mut intensity: Option<Rw<'_, f32>>,
    mut stages: Option<Rw<'_, u8>>,
) -> PyResult<i32> {
    let cells = size("nrow * nchan * ncorr", &[nrow, nchan, ncorr])?;
    let window = size("nbl * ntime * nchan", &[nbl, ntime, nchan])?;
    let offsets = c_slice(&mask_offsets, "mask_offsets")?;
    let nmask_freqs = offsets.last().copied().unwrap_or(0);
    let inputs = FlagInputs {
        nrow,
        nchan,
        ncorr,
        nant,
        nbl,
        ntime,
        nmasks,
        nsteps,
        data: arg(&data, "data", size("2 * cells", &[2, cells])?)?,
        flags: arg(&flags, "flags", cells)?,
        baseline_index: arg(&baseline_index, "baseline_index", nrow)?,
        time_index: arg(&time_index, "time_index", nrow)?,
        baselines: arg(&baselines, "baselines", size("2 * nbl", &[2, nbl])?)?,
        antenna_position: arg(
            &antenna_position,
            "antenna_position",
            size("3 * nant", &[3, nant])?,
        )?,
        chan_freq: arg(&chan_freq, "chan_freq", nchan)?,
        chan_width: arg(&chan_width, "chan_width", nchan)?,
        corr_type: arg(&corr_type, "corr_type", ncorr)?,
        mask_freqs: arg(&mask_freqs, "mask_freqs", nmask_freqs)?,
        mask_offsets: arg(&mask_offsets, "mask_offsets", nmasks.saturating_add(1))?,
        steps: arg(
            &steps,
            "steps",
            size(
                "nsteps * STEP_WIDTH",
                &[nsteps, rang_core::ffi_flag::STEP_WIDTH],
            )?,
        )?,
    };
    let mut outputs = FlagOutputs {
        flags: arg_mut(&mut out_flags, "out_flags", cells)?,
        intensity: opt_arg_mut(
            &mut intensity,
            "intensity",
            size("2 * window", &[2, window])?,
        )?,
        stages: opt_arg_mut(
            &mut stages,
            "stages",
            size("nsteps * window", &[nsteps, window])?,
        )?,
    };
    // SAFETY: as in `fused`.
    Ok(detach(py, || unsafe {
        rang_core::ffi_flag::rang_core_flag_rows(&inputs, &mut outputs)
    }))
}

// The root crate's kernels (task P7). Each binding takes the arguments of its
// C function in order, as the frozen modules pass them through
// `projector._native_library()`, checks every buffer length against the
// sizes (1 on a mismatch, as for invalid arguments; ctypes could not check),
// and returns the C status (0 ok, 1 invalid, 2 panic, 3-6 for the step).

/// `rang_gain_tv`: time edges then frequency edges, `2 * nt * nf * na`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn gain_tv(
    py: Python<'_>,
    nt: usize,
    nf: usize,
    na: usize,
    gains: Ro<'_, f64>,
    valid: Ro<'_, u8>,
    time_weights: Ro<'_, f64>,
    freq_weights: Ro<'_, f64>,
    mut output: Rw<'_, f64>,
) -> PyResult<i32> {
    let n = match nt.checked_mul(nf).and_then(|v| v.checked_mul(na)) {
        Some(n) if n > 0 && n <= usize::MAX / 8 => n,
        _ => return Ok(1),
    };
    let (Some(g), Some(v), Some(tw), Some(fw), Some(out)) = (
        sized(&gains, 8 * n)?,
        sized(&valid, n)?,
        sized(&time_weights, nt - 1)?,
        sized(&freq_weights, nf - 1)?,
        sized_mut(&mut output, 2 * n)?,
    ) else {
        return Ok(1);
    };
    // SAFETY: every buffer has the length the C function documents.
    Ok(detach(py, || unsafe {
        sim::tv::rang_gain_tv(nt, nf, na, g, v, tw, fw, out)
    }))
}

/// `rang_trend_slopes`: median phase gradients and sample counts, `2 * na`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn trend_slopes(
    py: Python<'_>,
    nt: usize,
    nf: usize,
    na: usize,
    gains: Ro<'_, f64>,
    valid: Ro<'_, u8>,
    times: Ro<'_, f64>,
    frequencies: Ro<'_, f64>,
    mut output: Rw<'_, f64>,
    mut counts: Rw<'_, usize>,
) -> PyResult<i32> {
    let n = match nt.checked_mul(nf).and_then(|v| v.checked_mul(na)) {
        Some(n) if n > 0 && n <= usize::MAX / 8 => n,
        _ => return Ok(1),
    };
    let (Some(g), Some(v), Some(t), Some(f), Some(out), Some(c)) = (
        sized(&gains, 8 * n)?,
        sized(&valid, n)?,
        sized(&times, nt)?,
        sized(&frequencies, nf)?,
        sized_mut(&mut output, 2 * na)?,
        sized_mut(&mut counts, 2 * na)?,
    ) else {
        return Ok(1);
    };
    // SAFETY: every buffer has the length the C function documents.
    Ok(detach(py, || unsafe {
        sim::trend::rang_trend_slopes(nt, nf, na, g, v, t, f, out, c)
    }))
}

/// `rang_response_jacobian`: eight Re/Im rows by sixteen parameters.
#[pyfunction]
fn response_jacobian(
    py: Python<'_>,
    gp: Ro<'_, f64>,
    gq: Ro<'_, f64>,
    model: Ro<'_, f64>,
    mut output: Rw<'_, f64>,
) -> PyResult<i32> {
    let (Some(p), Some(q), Some(m), Some(out)) = (
        sized(&gp, 8)?,
        sized(&gq, 8)?,
        sized(&model, 8)?,
        sized_mut(&mut output, 128)?,
    ) else {
        return Ok(1);
    };
    // SAFETY: every buffer has the length the C function documents.
    Ok(detach(py, || unsafe {
        sim::response::rang_response_jacobian(p, q, m, out)
    }))
}

/// `rang_response_normals`: per-bin 32x32 normals, right-hand sides, counts.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn response_normals(
    py: Python<'_>,
    samples: usize,
    gain_bins: usize,
    gains: Ro<'_, f64>,
    models: Ro<'_, f64>,
    residuals: Ro<'_, f64>,
    weights: Ro<'_, f64>,
    p: Ro<'_, usize>,
    q: Ro<'_, usize>,
    bins: Ro<'_, usize>,
    mut h: Rw<'_, f64>,
    mut b: Rw<'_, f64>,
    mut counts: Rw<'_, usize>,
) -> PyResult<i32> {
    let (Some(s8), Some(g32), Some(g1024)) = (
        samples.checked_mul(8),
        gain_bins.checked_mul(32),
        gain_bins.checked_mul(1024),
    ) else {
        return Ok(1);
    };
    let (Some(g), Some(m), Some(r), Some(w), Some(pp), Some(qq), Some(bb)) = (
        sized(&gains, g32)?,
        sized(&models, s8)?,
        sized(&residuals, s8)?,
        sized(&weights, 4 * samples)?,
        sized(&p, samples)?,
        sized(&q, samples)?,
        sized(&bins, samples)?,
    ) else {
        return Ok(1);
    };
    let (Some(hh), Some(rhs), Some(c)) = (
        sized_mut(&mut h, g1024)?,
        sized_mut(&mut b, g32)?,
        sized_mut(&mut counts, gain_bins)?,
    ) else {
        return Ok(1);
    };
    // SAFETY: every buffer has the length the C function documents.
    Ok(detach(py, || unsafe {
        sim::response::rang_response_normals(samples, gain_bins, g, m, r, w, pp, qq, bb, hh, rhs, c)
    }))
}

/// `rang_response_step`: the anchored step and ten diagnostics.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn response_step(
    py: Python<'_>,
    full_h: Ro<'_, f64>,
    full_b: Ro<'_, f64>,
    drop_h: Ro<'_, f64>,
    drop_b: Ro<'_, f64>,
    gains: Ro<'_, f64>,
    active: Ro<'_, u8>,
    mut delta: Rw<'_, f64>,
    mut diagnostics: Rw<'_, f64>,
) -> PyResult<i32> {
    let (Some(fh), Some(fb), Some(dh), Some(db), Some(g), Some(a)) = (
        sized(&full_h, 1024)?,
        sized(&full_b, 32)?,
        sized(&drop_h, 1024)?,
        sized(&drop_b, 32)?,
        sized(&gains, 32)?,
        sized(&active, 4)?,
    ) else {
        return Ok(1);
    };
    let (Some(d), Some(info)) = (sized_mut(&mut delta, 32)?, sized_mut(&mut diagnostics, 10)?)
    else {
        return Ok(1);
    };
    // SAFETY: every buffer has the length the C function documents.
    Ok(detach(py, || unsafe {
        sim::response::rang_response_step(fh, fb, dh, db, g, a, d, info)
    }))
}

/// `rang_project_out`; returns (status, nuisance rank).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn project_out(
    py: Python<'_>,
    rows: usize,
    nuisance_cols: usize,
    target_cols: usize,
    nuisance: Ro<'_, f64>,
    targets: Ro<'_, f64>,
    mut output: Rw<'_, f64>,
    relative_tolerance: f64,
) -> PyResult<(i32, usize)> {
    let (Some(na), Some(nz)) = (
        rows.checked_mul(nuisance_cols),
        rows.checked_mul(target_cols),
    ) else {
        return Ok((1, 0));
    };
    let (Some(a), Some(z), Some(out)) = (
        sized(&nuisance, na)?,
        sized(&targets, nz)?,
        sized_mut(&mut output, nz)?,
    ) else {
        return Ok((1, 0));
    };
    let mut rank = 0usize;
    // SAFETY: every buffer has the length the C function documents.
    let status = detach(py, || unsafe {
        sim::projector::rang_project_out(
            rows,
            nuisance_cols,
            target_cols,
            a,
            z,
            out,
            &mut rank,
            relative_tolerance,
        )
    });
    Ok((status, rank))
}

/// The `rang-sim` command line (`rang_sim::cli`): (true, stdout text) or
/// (false, error message). The text lacks the final newline the binary adds.
#[pyfunction]
fn sim_cli(py: Python<'_>, args: Vec<String>) -> (bool, String) {
    let result = py.detach(|| std::panic::catch_unwind(|| sim::cli(&args)));
    match result {
        Ok(Ok(text)) => (true, text),
        Ok(Err(error)) => (false, error),
        Err(_) => (false, "panic in the pointing simulation".to_string()),
    }
}

/// An open casacore table (read-only), the counterpart of the C ABI handle.
#[pyclass(unsendable)]
struct MsTable {
    table: Table,
}

#[pymethods]
impl MsTable {
    #[new]
    fn new(py: Python<'_>, path: &str) -> PyResult<Self> {
        match detach(py, || Table::open(path)) {
            Ok(table) => Ok(MsTable { table }),
            Err(e) => Err(PyOSError::new_err(format!("{path}: {e}"))),
        }
    }

    /// The JSON description of the table.
    fn describe(&self) -> String {
        self.table.describe_json()
    }

    /// Read `count` rows (0: to the end) of a column from `start`. Returns
    /// (bytes as a uint8 array, nrows, cell shape, dtype code, nstrings),
    /// with strings packed as the C ABI packs them: a little-endian u32
    /// length before each string's UTF-8 bytes.
    fn read<'py>(
        &self,
        py: Python<'py>,
        name: &str,
        start: u64,
        count: u64,
    ) -> PyResult<Column<'py>> {
        let table = &self.table;
        let data = detach(py, || table.read_column(name, start, count))
            .map_err(|e| PyOSError::new_err(e.0))?;
        if data.shape.len() > 8 {
            return Err(PyOSError::new_err("more than 8 cell axes"));
        }
        let dtype = data.dtype.unwrap_or(DataType::Str);
        let nstrings = data.strings.len();
        let mut bytes = data.bytes;
        if dtype == DataType::Str {
            bytes = Vec::with_capacity(data.strings.iter().map(|s| 4 + s.len()).sum());
            for s in &data.strings {
                bytes.extend((s.len() as u32).to_le_bytes());
                bytes.extend_from_slice(s.as_bytes());
            }
        }
        Ok((
            bytes.into_pyarray(py),
            data.nrows,
            data.shape,
            dtype.code(),
            nstrings,
        ))
    }
}

/// `serialise(parse(x)) == x` over a table and its subtables (the table
/// writer's criterion 7): (tables, StandardStMan files, tiled headers,
/// failures).
#[pyfunction]
fn ms_serialisation_check(
    py: Python<'_>,
    path: &str,
) -> PyResult<(usize, usize, usize, Vec<String>)> {
    let c = detach(py, || rang_core::ms_write::check_serialisation(path))
        .map_err(|e| PyOSError::new_err(e.0))?;
    Ok((c.tables, c.ssm_files, c.tiled_headers, c.failures))
}

/// `serialise(parse(x)) == x` for the MultiFile header of a table's
/// `table.mf` (research/e5-table-writer-rest.md): the failures (empty when
/// it round-trips).
#[pyfunction]
fn ms_multifile_check(py: Python<'_>, path: &str) -> Vec<String> {
    match detach(py, || rang_core::multifile::check(path)) {
        Ok(true) => Vec::new(),
        Ok(false) => vec![format!("{path}/table.mf header differs")],
        Err(e) => vec![format!("{path}/table.mf: {}", e.0)],
    }
}

/// A table's row count and columns (name, type code, is array), read
/// without writing (research/e5-table-writer-rest.md).
#[pyfunction]
fn ms_describe(py: Python<'_>, path: &str) -> PyResult<(u64, rang_core::ms_write::ColumnList)> {
    detach(py, || rang_core::ms_write::describe(path)).map_err(|e| PyOSError::new_err(e.0))
}

/// `serialise(parse(x)) == x` as `ms_serialisation_check`, with the
/// IncrementalStMan files (research/e5-table-writer-rest.md): (tables,
/// StandardStMan files, tiled headers, IncrementalStMan files, failures).
#[pyfunction]
fn ms_serialisation_check_e5(
    py: Python<'_>,
    path: &str,
) -> PyResult<(usize, usize, usize, usize, Vec<String>)> {
    let c = detach(py, || rang_core::ms_write::check_serialisation(path))
        .map_err(|e| PyOSError::new_err(e.0))?;
    Ok((
        c.tables,
        c.ssm_files,
        c.tiled_headers,
        c.ism_files,
        c.failures,
    ))
}

/// A casacore table open for writing (research/e3-table-writer.md); holds
/// casacore's write lock until `close`.
#[pyclass(unsendable)]
struct MsWriter {
    writer: Option<TableWriter>,
}

impl MsWriter {
    fn get(&mut self) -> PyResult<&mut TableWriter> {
        self.writer
            .as_mut()
            .ok_or_else(|| PyValueError::new_err("table is closed"))
    }
}

#[pymethods]
impl MsWriter {
    #[new]
    fn new(py: Python<'_>, path: &str, attempts: u32, wait_ms: u64) -> PyResult<Self> {
        let wait = std::time::Duration::from_millis(wait_ms);
        match detach(py, || TableWriter::open(path, attempts, wait)) {
            Ok(writer) => Ok(MsWriter {
                writer: Some(writer),
            }),
            Err(e) => Err(PyOSError::new_err(format!("{path}: {e}"))),
        }
    }

    fn nrows(&mut self) -> PyResult<u64> {
        Ok(self.get()?.nrows)
    }

    /// Write `count` rows (0: to the end) from `start`: `data` the cells'
    /// native bytes as a uint8 array (borrowed, not copied), `shape` the
    /// cell shape in casacore order (empty for scalars).
    fn put(
        &mut self,
        py: Python<'_>,
        name: &str,
        start: u64,
        count: u64,
        shape: Vec<i64>,
        data: PyReadonlyArray1<'_, u8>,
    ) -> PyResult<()> {
        let bytes = data.as_slice()?;
        let w = self.get()?;
        detach(py, || w.put_column(name, start, count, &shape, bytes))
            .map_err(|e| PyOSError::new_err(e.0))
    }

    /// Flush, then read `count` rows (0: to the end) from `start`, packed as
    /// `MsTable.read` packs them; the table's lock is kept.
    fn read<'py>(
        &mut self,
        py: Python<'py>,
        name: &str,
        start: u64,
        count: u64,
    ) -> PyResult<Column<'py>> {
        let w = self.get()?;
        let data = detach(py, || w.read_column(name, start, count))
            .map_err(|e| PyOSError::new_err(e.0))?;
        if data.shape.len() > 8 {
            return Err(PyOSError::new_err("more than 8 cell axes"));
        }
        let dtype = data.dtype.unwrap_or(DataType::Str);
        let nstrings = data.strings.len();
        let mut bytes = data.bytes;
        if dtype == DataType::Str {
            bytes = Vec::with_capacity(data.strings.iter().map(|s| 4 + s.len()).sum());
            for s in &data.strings {
                bytes.extend((s.len() as u32).to_le_bytes());
                bytes.extend_from_slice(s.as_bytes());
            }
        }
        Ok((
            bytes.into_pyarray(py),
            data.nrows,
            data.shape,
            dtype.code(),
            nstrings,
        ))
    }

    /// Write one cell as `ArrayColumn::put` does (`putcell`): native bytes,
    /// `shape` in casacore order (research/e5-table-writer-rest.md).
    fn put_cell(
        &mut self,
        py: Python<'_>,
        name: &str,
        row: u64,
        shape: Vec<i64>,
        data: PyReadonlyArray1<'_, u8>,
    ) -> PyResult<()> {
        let bytes = data.as_slice()?;
        let w = self.get()?;
        detach(py, || w.put_cell(name, row, &shape, bytes)).map_err(|e| PyOSError::new_err(e.0))
    }

    fn put_strings(&mut self, name: &str, start: u64, values: Vec<String>) -> PyResult<()> {
        self.get()?
            .put_strings(name, start, &values)
            .map_err(|e| PyOSError::new_err(e.0))
    }

    /// Define a keyword: kind 0 scalar, 1 string, 2 array, 3 string array,
    /// 4 empty record (`rang_core_ms_write_put_keyword`).
    #[pyo3(signature = (column, path, kind, code, shape, data, strings))]
    #[allow(clippy::too_many_arguments)]
    fn put_keyword(
        &mut self,
        column: Option<String>,
        path: Vec<String>,
        kind: i32,
        code: i32,
        shape: Vec<i64>,
        data: Vec<u8>,
        strings: Vec<String>,
    ) -> PyResult<()> {
        let value = if kind == 3 {
            Ok(rang_core::aipsio::KeywordValue::StringArray(shape, strings))
        } else {
            keyword_value(kind, code, &shape, &data, 0)
        }
        .map_err(PyValueError::new_err)?;
        let parts: Vec<&str> = path.iter().map(String::as_str).collect();
        self.get()?
            .put_keyword(column.as_deref(), &parts, value)
            .map_err(|e| PyOSError::new_err(e.0))
    }

    fn remove_keyword(&mut self, column: Option<String>, path: Vec<String>) -> PyResult<()> {
        let parts: Vec<&str> = path.iter().map(String::as_str).collect();
        self.get()?
            .remove_keyword(column.as_deref(), &parts)
            .map_err(|e| PyOSError::new_err(e.0))
    }

    /// `addcols` of one column; `manager` 0 default binding, 1 a new
    /// TiledColumnStMan, 2 a new TiledShapeStMan named `manager_name`.
    #[allow(clippy::too_many_arguments)]
    fn add_column(
        &mut self,
        py: Python<'_>,
        name: String,
        dtype: i32,
        array: bool,
        ndim: i32,
        shape: Vec<i64>,
        option: i32,
        max_length: u32,
        comment: String,
        dm_type: String,
        dm_group: String,
        default: Vec<u8>,
        manager: i32,
        manager_name: String,
        tile: Vec<i64>,
    ) -> PyResult<()> {
        let spec = new_column(
            name,
            dtype,
            array,
            ndim,
            shape,
            option,
            max_length,
            [comment, dm_type, dm_group],
            default,
            manager,
            manager_name,
            tile,
        )
        .map_err(PyValueError::new_err)?;
        let w = self.get()?;
        detach(py, || w.add_column(&spec)).map_err(|e| PyOSError::new_err(e.0))
    }

    fn flush(&mut self, py: Python<'_>) -> PyResult<()> {
        let w = self.get()?;
        detach(py, || w.flush()).map_err(|e| PyOSError::new_err(e.0))
    }

    /// Flush and release the lock; the table is closed even on an error.
    fn close(&mut self, py: Python<'_>) -> PyResult<()> {
        match self.writer.take() {
            Some(w) => detach(py, || w.close()).map_err(|e| PyOSError::new_err(e.0)),
            None => Ok(()),
        }
    }

    /// Write `count` rows of a string-array column from `start`, every
    /// cell of `shape` (casacore order), strings in Fortran order.
    fn put_string_cells(
        &mut self,
        name: &str,
        start: u64,
        count: u64,
        shape: Vec<i64>,
        strings: Vec<String>,
    ) -> PyResult<()> {
        self.get()?
            .put_string_cells(name, start, count, &shape, &strings)
            .map_err(|e| PyOSError::new_err(e.0))
    }

    /// `TiledDataStManAccessor::addHypercube` of the TiledDataStMan `name`:
    /// shapes in casacore order, `values` the id and coordinate values as
    /// (field, keyword kind, type code, shape, native bytes), in order
    /// (research/e6-table-writer-final.md).
    fn add_hypercube(
        &mut self,
        name: &str,
        shape: Vec<i64>,
        tile: Vec<i64>,
        values: Vec<RecordItem>,
    ) -> PyResult<()> {
        let rec = record_of(values)?;
        self.get()?
            .add_hypercube(name, &shape, &tile, rec)
            .map_err(|e| PyOSError::new_err(e.0))
    }

    /// `TiledDataStManAccessor::extendHypercube` of the TiledDataStMan
    /// `name` by `incr` on the last axis (`values` as in `add_hypercube`).
    fn extend_hypercube(&mut self, name: &str, incr: u64, values: Vec<RecordItem>) -> PyResult<()> {
        let rec = record_of(values)?;
        self.get()?
            .extend_hypercube(name, incr, rec)
            .map_err(|e| PyOSError::new_err(e.0))
    }

    /// Write one cell of a string-array column as `ArrayColumn::put` does
    /// (`putcell`; research/e6-table-writer-final.md).
    fn put_string_cell(
        &mut self,
        name: &str,
        row: u64,
        shape: Vec<i64>,
        strings: Vec<String>,
    ) -> PyResult<()> {
        self.get()?
            .put_string_cell(name, row, &shape, &strings)
            .map_err(|e| PyOSError::new_err(e.0))
    }

    /// The columns as (name, type code, is array), in table order.
    fn columns(&mut self) -> PyResult<Vec<(String, i32, bool)>> {
        Ok(self
            .get()?
            .dat
            .columns
            .iter()
            .map(|c| (c.name.clone(), c.dtype, c.is_array()))
            .collect())
    }

    fn add_rows(&mut self, py: Python<'_>, n: u64) -> PyResult<()> {
        let w = self.get()?;
        detach(py, || w.add_rows(n)).map_err(|e| PyOSError::new_err(e.0))
    }

    fn remove_rows(&mut self, py: Python<'_>, rows: Vec<u64>) -> PyResult<()> {
        let w = self.get()?;
        detach(py, || w.remove_rows(&rows)).map_err(|e| PyOSError::new_err(e.0))
    }

    fn is_defined(&mut self, name: &str, row: u64) -> PyResult<bool> {
        self.get()?
            .is_defined(name, row)
            .map_err(|e| PyOSError::new_err(e.0))
    }

    /// Mark the table changed (casacore's `rwKeywordSet`).
    fn mark_changed(&mut self) -> PyResult<()> {
        self.get()?
            .mark_changed()
            .map_err(|e| PyOSError::new_err(e.0))
    }

    fn put_info(&mut self, kind: &str, sub_kind: &str, readme: &str) -> PyResult<()> {
        self.get()?
            .put_info(kind, sub_kind, readme)
            .map_err(|e| PyOSError::new_err(e.0))
    }

    /// Flush, then read cells: (0 undefined / 1 values / 2 strings, shape
    /// in casacore order, native bytes, strings) per row.
    fn read_cells<'py>(
        &mut self,
        py: Python<'py>,
        name: &str,
        start: u64,
        count: u64,
    ) -> PyResult<Vec<CellTuple<'py>>> {
        let w = self.get()?;
        let cells =
            detach(py, || w.read_cells(name, start, count)).map_err(|e| PyOSError::new_err(e.0))?;
        Ok(cells.into_iter().map(|c| cell_tuple(py, c)).collect())
    }
}

type CellTuple<'py> = (i32, Vec<i64>, Bound<'py, PyBytes>, Vec<String>);

/// A record field: name, keyword kind, type code, shape, native bytes.
type RecordItem = (String, i32, i32, Vec<i64>, Vec<u8>);

/// The record of a hypercube's id and coordinate values.
fn record_of(items: Vec<RecordItem>) -> PyResult<rang_core::aipsio::Record> {
    let mut rec = rang_core::aipsio::Record::default();
    for (name, kind, code, shape, data) in items {
        let value = keyword_value(kind, code, &shape, &data, 0).map_err(PyValueError::new_err)?;
        rec.define(&name, value)
            .map_err(|e| PyValueError::new_err(e.0))?;
    }
    Ok(rec)
}

/// A hypercolumn definition: name, ndim, data, coordinate and id columns.
type HypercolumnArgs = (String, u32, Vec<String>, Vec<String>, Vec<String>);

fn cell_tuple(py: Python<'_>, cell: rang_core::ms_write::Cell) -> CellTuple<'_> {
    use rang_core::ms_write::Cell;
    match cell {
        Cell::Undefined => (0, Vec::new(), PyBytes::new(py, &[]), Vec::new()),
        Cell::Values(shape, bytes) => (1, shape, PyBytes::new(py, &bytes), Vec::new()),
        Cell::Strings(shape, strings) => (2, shape, PyBytes::new(py, &[]), strings),
    }
}

fn writer(w: rang_core::ms::Result<TableWriter>) -> PyResult<MsWriter> {
    w.map(|w| MsWriter { writer: Some(w) })
        .map_err(|e| PyOSError::new_err(e.0))
}

/// Create a table (research/e4-table-create.md): description (name,
/// version, comment), columns and data managers as tuples
/// (`ffi_ms_write::ColumnArgs`, `ManagerArgs`), `table.info` (type,
/// subtype, readme), `nrows` rows; returned open for writing.
#[pyfunction]
#[pyo3(signature = (path, desc, columns, managers, info, nrows, big_endian=false, multifile=false, hypercolumns=Vec::new(), block_size=0))]
#[allow(clippy::too_many_arguments)]
fn ms_create_table(
    py: Python<'_>,
    path: &str,
    desc: (String, String, String),
    columns: Vec<ColumnArgs>,
    managers: Vec<ManagerArgs>,
    info: (String, String, String),
    nrows: u64,
    big_endian: bool,
    multifile: bool,
    hypercolumns: Vec<HypercolumnArgs>,
    block_size: i64,
) -> PyResult<MsWriter> {
    let spec = rang_core::ms_create::TableSpec {
        desc_name: desc.0,
        desc_version: desc.1,
        desc_comment: desc.2,
        columns: column_descs(columns).map_err(PyValueError::new_err)?,
        managers: manager_specs(managers),
        info,
        big_endian,
        multifile,
        block_size,
        hypercolumns: hypercolumns
            .into_iter()
            .map(
                |(name, ndim, data, coord, id)| rang_core::ms_create::Hypercolumn {
                    name,
                    ndim,
                    data,
                    coord,
                    id,
                },
            )
            .collect(),
        ..Default::default()
    };
    writer(detach(py, || {
        rang_core::ms_create::create_table(path, &spec, nrows)
    }))
}

/// python-casacore's `default_ms(path, desc, dminfo)`.
#[pyfunction]
fn ms_default_ms(
    py: Python<'_>,
    path: &str,
    columns: Vec<ColumnArgs>,
    managers: Vec<ManagerArgs>,
) -> PyResult<MsWriter> {
    let extra = column_descs(columns).map_err(PyValueError::new_err)?;
    let managers = manager_specs(managers);
    writer(detach(py, || {
        rang_core::ms_create::default_ms(path, &extra, &managers)
    }))
}

/// python-casacore's `default_ms_subtable(name, path, desc, dminfo)`.
#[pyfunction]
fn ms_default_ms_subtable(
    py: Python<'_>,
    name: &str,
    path: &str,
    columns: Vec<ColumnArgs>,
    managers: Vec<ManagerArgs>,
) -> PyResult<MsWriter> {
    let extra = column_descs(columns).map_err(PyValueError::new_err)?;
    let managers = manager_specs(managers);
    writer(detach(py, || {
        rang_core::ms_create::default_ms_subtable(name, path, &extra, &managers)
    }))
}

/// The MAIN table of a CASA calibration table with `nrows` rows.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn ms_caltable_main(
    py: Python<'_>,
    path: &str,
    vis_cal: String,
    float_param: bool,
    ms_name: String,
    pol_basis: String,
    casa_version: String,
    nrows: u64,
) -> PyResult<MsWriter> {
    let cal = rang_core::caltable::CalTable {
        vis_cal,
        float_param,
        ms_name,
        pol_basis,
        casa_version,
    };
    let spec = rang_core::caltable::main_spec(&cal).map_err(|e| PyValueError::new_err(e.0))?;
    writer(detach(py, || {
        rang_core::ms_create::create_table(path, &spec, nrows)
    }))
}

/// A calibration subtable (`OBSERVATION`, `ANTENNA`, `FIELD`,
/// `SPECTRAL_WINDOW`, `HISTORY`) with `nrows` rows.
#[pyfunction]
fn ms_caltable_subtable(py: Python<'_>, path: &str, name: &str, nrows: u64) -> PyResult<MsWriter> {
    let spec = rang_core::caltable::subtable_spec(name).map_err(|e| PyValueError::new_err(e.0))?;
    writer(detach(py, || {
        rang_core::ms_create::create_table(path, &spec, nrows)
    }))
}

/// The array records a table's rows reference: (file, offset, element
/// bits) (`ms_write::array_records`, the alignment-gap mask).
#[pyfunction]
fn ms_array_records(py: Python<'_>, path: &str) -> PyResult<Vec<(String, u64, u32)>> {
    detach(py, || rang_core::ms_write::array_records(path)).map_err(|e| PyOSError::new_err(e.0))
}

/// Read cells of a table without writing (`ms_write::read_cells`).
#[pyfunction]
fn ms_read_cells<'py>(
    py: Python<'py>,
    path: &str,
    name: &str,
    start: u64,
    count: u64,
) -> PyResult<Vec<CellTuple<'py>>> {
    let cells = detach(py, || {
        rang_core::ms_write::read_cells(path, name, start, count, None)
    })
    .map_err(|e| PyOSError::new_err(e.0))?;
    Ok(cells.into_iter().map(|c| cell_tuple(py, c)).collect())
}

// Task W4-3 (research/w4-3-kernels.md): the closure scores (C1) and the
// flux-standard evaluator (FS1), which built a standalone library with Cargo
// before. Each binding takes typed arrays (a wrong dtype is a TypeError),
// refuses one that is not C-contiguous or not of the expected shape
// (ValueError), calls the C function with the GIL released inside
// `catch_unwind`, and raises on its status.

/// Pointer of a C-contiguous input of exactly `shape`.
fn exact_input<T: Element>(a: &Ro<'_, T>, name: &str, shape: &[usize]) -> PyResult<*const T> {
    let view = a.as_array();
    if !view.is_standard_layout() {
        return Err(PyValueError::new_err(format!(
            "{name} must be C-contiguous"
        )));
    }
    if view.shape() != shape {
        return Err(PyValueError::new_err(format!(
            "{name} must have shape {shape:?}, not {:?}",
            view.shape()
        )));
    }
    ptr(a)
}

/// Pointer of a C-contiguous output of exactly `shape`.
fn exact_output<T: Element>(a: &mut Rw<'_, T>, name: &str, shape: &[usize]) -> PyResult<*mut T> {
    let view = a.as_array();
    if !view.is_standard_layout() {
        return Err(PyValueError::new_err(format!(
            "{name} must be C-contiguous"
        )));
    }
    if view.shape() != shape {
        return Err(PyValueError::new_err(format!(
            "{name} must have shape {shape:?}, not {:?}",
            view.shape()
        )));
    }
    ptr_mut(a)
}

/// The apply kernel's last error message on this thread.
fn cal_apply_last_error() -> String {
    // SAFETY: a null buffer asks for the length only; `buf` then holds it.
    let n = unsafe {
        rang_core::cal::ffi_apply::rang_core_cal_apply_last_error(std::ptr::null_mut(), 0)
    };
    let mut buf = vec![0_u8; n];
    // SAFETY: `buf` holds `n` bytes.
    unsafe { rang_core::cal::ffi_apply::rang_core_cal_apply_last_error(buf.as_mut_ptr(), n) };
    String::from_utf8_lossy(&buf).into_owned()
}

/// Length of a 1-D input.
fn len1<T: Element>(a: &Ro<'_, T>) -> usize {
    a.as_array().len()
}

/// `rang_core_cal_apply` (task C4a, research/c4a-apply.md): correct
/// (`direction` 0) or corrupt (1) `data` (complex64 `(nrow, nchan, 4)`)
/// with `flags` (uint8, same shape) by the packed terms (see
/// `rang.cal_apply.pack`) into `out_data` and `out_flags`. Raises
/// ValueError on invalid input (the core's message) and RuntimeError on a
/// panic in the core.
#[pyfunction]
#[pyo3(signature = (
    data, flags, time, antenna1, antenna2, freq, nant,
    kind, time_interp, freq_interp, npar, k_ref_freq, slot_start, slot_offset, slot_time,
    param_offset, params, flag_offset, term_flags, freq_offset, sol_freq,
    direction, threads, out_data, out_flags
))]
#[allow(clippy::too_many_arguments)]
fn cal_apply(
    py: Python<'_>,
    data: Ro<'_, Complex32>,
    flags: Ro<'_, u8>,
    time: Ro<'_, f64>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    freq: Ro<'_, f64>,
    nant: usize,
    kind: Ro<'_, u32>,
    time_interp: Ro<'_, u32>,
    freq_interp: Ro<'_, u32>,
    npar: Ro<'_, u32>,
    k_ref_freq: Ro<'_, f64>,
    slot_start: Ro<'_, u64>,
    slot_offset: Ro<'_, u64>,
    slot_time: Ro<'_, f64>,
    param_offset: Ro<'_, u64>,
    params: Ro<'_, f32>,
    flag_offset: Ro<'_, u64>,
    term_flags: Ro<'_, u8>,
    freq_offset: Ro<'_, u64>,
    sol_freq: Ro<'_, f64>,
    direction: u32,
    threads: usize,
    mut out_data: Rw<'_, Complex32>,
    mut out_flags: Rw<'_, u8>,
) -> PyResult<()> {
    let shape = data.as_array().shape().to_vec();
    if shape.len() != 3 || shape[2] != 4 {
        return Err(PyValueError::new_err(format!(
            "data must be (row, chan, 4), not {shape:?}"
        )));
    }
    let (nrow, nchan) = (shape[0], shape[1]);
    let nterm = len1(&kind);
    let chunk = rang_core::cal::ffi_apply::ApplyChunkC {
        nrow,
        nchan,
        nant,
        data: exact_input(&data, "data", &[nrow, nchan, 4])? as *const f32,
        flags: exact_input(&flags, "flags", &[nrow, nchan, 4])?,
        time: exact_input(&time, "time", &[nrow])?,
        antenna1: exact_input(&antenna1, "antenna1", &[nrow])?,
        antenna2: exact_input(&antenna2, "antenna2", &[nrow])?,
        freq: exact_input(&freq, "freq", &[nchan])?,
    };
    let terms = rang_core::cal::ffi_apply::ApplyTermsC {
        nterm,
        kind: exact_input(&kind, "kind", &[nterm])?,
        time_interp: exact_input(&time_interp, "time_interp", &[nterm])?,
        freq_interp: exact_input(&freq_interp, "freq_interp", &[nterm])?,
        npar: exact_input(&npar, "npar", &[nterm])?,
        k_ref_freq: exact_input(&k_ref_freq, "k_ref_freq", &[nterm])?,
        slot_start: exact_input(&slot_start, "slot_start", &[nterm * (nant + 1)])?,
        slot_offset: exact_input(&slot_offset, "slot_offset", &[nterm + 1])?,
        slot_time: exact_input(&slot_time, "slot_time", &[len1(&slot_time)])?,
        param_offset: exact_input(&param_offset, "param_offset", &[nterm + 1])?,
        params: exact_input(&params, "params", &[len1(&params)])?,
        flag_offset: exact_input(&flag_offset, "flag_offset", &[nterm + 1])?,
        flags: exact_input(&term_flags, "term_flags", &[len1(&term_flags)])?,
        freq_offset: exact_input(&freq_offset, "freq_offset", &[nterm + 1])?,
        sol_freq: exact_input(&sol_freq, "sol_freq", &[len1(&sol_freq)])?,
    };
    // The packed lengths must cover what the offsets name.
    let last = |a: &Ro<'_, u64>| a.as_array().iter().last().copied().unwrap_or(0) as usize;
    for (name, end, have) in [
        ("slot_time", last(&slot_offset), len1(&slot_time)),
        ("params", last(&param_offset), len1(&params)),
        ("term_flags", last(&flag_offset), len1(&term_flags)),
        ("sol_freq", last(&freq_offset), len1(&sol_freq)),
    ] {
        if end > have {
            return Err(PyValueError::new_err(format!(
                "{name} holds {have} values, the offsets name {end}"
            )));
        }
    }
    let od = exact_output(&mut out_data, "out_data", &[nrow, nchan, 4])? as *mut f32;
    let of = exact_output(&mut out_flags, "out_flags", &[nrow, nchan, 4])?;
    // SAFETY: every pointer borrows a live NumPy buffer of the checked shape
    // for the duration of the call; the outputs are distinct writable arrays.
    let status = detach(py, || {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| unsafe {
            rang_core::cal::ffi_apply::rang_core_cal_apply(
                &chunk, &terms, direction, threads, od, of,
            )
        }))
        .unwrap_or(2)
    });
    match status {
        0 => Ok(()),
        1 => Err(PyValueError::new_err(format!(
            "apply kernel failed (1): {}",
            cal_apply_last_error()
        ))),
        s => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
            "apply kernel failed ({s}): a panic in the core"
        ))),
    }
}

/// `rang_core::cal::apply::apply_jones` (task C4b, research/c4b-apply-ms.md):
/// correct (`direction` 0) or corrupt (1) `data` (complex64 `(nrow, nchan,
/// 4)`) with `flags` (uint8, same shape) by binned general 2x2 gains
/// (complex128 `(ntime_bins, nfreq_bins, nant, 2, 2)`, `valid` uint8
/// `(ntime_bins, nfreq_bins, nant)`), a time bin per row and a frequency bin
/// per channel, into `out_data` and `out_flags`. Raises ValueError on invalid
/// input and RuntimeError on a panic in the core.
#[pyfunction]
#[pyo3(signature = (
    data, flags, antenna1, antenna2, nant, gains, valid, time_bin, freq_bin,
    direction, threads, out_data, out_flags
))]
#[allow(clippy::too_many_arguments)]
fn cal_apply_jones(
    py: Python<'_>,
    data: Ro<'_, Complex32>,
    flags: Ro<'_, u8>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    nant: usize,
    gains: Ro<'_, Complex64>,
    valid: Ro<'_, u8>,
    time_bin: Ro<'_, u32>,
    freq_bin: Ro<'_, u32>,
    direction: u32,
    threads: usize,
    mut out_data: Rw<'_, Complex32>,
    mut out_flags: Rw<'_, u8>,
) -> PyResult<()> {
    use rang_core::cal::apply::{self, BinnedJones, Chunk, Direction};
    let shape = data.as_array().shape().to_vec();
    if shape.len() != 3 || shape[2] != 4 {
        return Err(PyValueError::new_err(format!(
            "data must be (row, chan, 4), not {shape:?}"
        )));
    }
    let (nrow, nchan) = (shape[0], shape[1]);
    let gshape = gains.as_array().shape().to_vec();
    if gshape.len() != 5 || gshape[2] != nant || gshape[3] != 2 || gshape[4] != 2 {
        return Err(PyValueError::new_err(format!(
            "gains must be (time_bin, freq_bin, {nant}, 2, 2), not {gshape:?}"
        )));
    }
    let (nt, nf) = (gshape[0], gshape[1]);
    let direction = match direction {
        0 => Direction::Correct,
        1 => Direction::Corrupt,
        d => return Err(PyValueError::new_err(format!("unknown direction {d}"))),
    };
    let cells = nrow * nchan;
    let nsol = nt * nf * nant;
    // Addresses, so they can cross `detach`; each borrows a live NumPy
    // buffer of the checked shape for the whole call.
    let d = exact_input(&data, "data", &[nrow, nchan, 4])? as usize;
    let f = exact_input(&flags, "flags", &[nrow, nchan, 4])? as usize;
    let a1 = exact_input(&antenna1, "antenna1", &[nrow])? as usize;
    let a2 = exact_input(&antenna2, "antenna2", &[nrow])? as usize;
    let g = exact_input(&gains, "gains", &[nt, nf, nant, 2, 2])? as usize;
    let v = exact_input(&valid, "valid", &[nt, nf, nant])? as usize;
    let tb = exact_input(&time_bin, "time_bin", &[nrow])? as usize;
    let fb = exact_input(&freq_bin, "freq_bin", &[nchan])? as usize;
    let od = exact_output(&mut out_data, "out_data", &[nrow, nchan, 4])? as usize;
    let of = exact_output(&mut out_flags, "out_flags", &[nrow, nchan, 4])? as usize;
    let result = detach(py, move || {
        std::panic::catch_unwind(|| {
            // SAFETY: as above; a zero length gives an empty slice, so a
            // dangling pointer of an empty array is never read.
            unsafe fn view<'a, T>(p: usize, n: usize) -> &'a [T] {
                if n == 0 {
                    &[]
                } else {
                    unsafe { std::slice::from_raw_parts(p as *const T, n) }
                }
            }
            unsafe fn view_mut<'a, T>(p: usize, n: usize) -> &'a mut [T] {
                if n == 0 {
                    &mut []
                } else {
                    unsafe { std::slice::from_raw_parts_mut(p as *mut T, n) }
                }
            }
            let (chunk, term, out_d, out_f) = unsafe {
                (
                    Chunk {
                        nrow,
                        nchan,
                        nant,
                        data: view::<f32>(d, 8 * cells),
                        flags: view::<u8>(f, 4 * cells),
                        time: &[],
                        antenna1: view::<u32>(a1, nrow),
                        antenna2: view::<u32>(a2, nrow),
                        freq: &[],
                    },
                    BinnedJones {
                        ntime_bins: nt,
                        nfreq_bins: nf,
                        gains: view::<f64>(g, 8 * nsol),
                        valid: view::<u8>(v, nsol),
                        time_bin: view::<u32>(tb, nrow),
                        freq_bin: view::<u32>(fb, nchan),
                    },
                    view_mut::<f32>(od, 8 * cells),
                    view_mut::<u8>(of, 4 * cells),
                )
            };
            apply::apply_jones(&chunk, &term, direction, threads, out_d, out_f)
        })
    });
    match result {
        Ok(Ok(())) => Ok(()),
        Ok(Err(message)) => Err(PyValueError::new_err(format!(
            "apply kernel failed (1): {message}"
        ))),
        Err(_) => Err(pyo3::exceptions::PyRuntimeError::new_err(
            "apply kernel failed (2): a panic in the core",
        )),
    }
}

/// The closure kernel's last error message on this thread.
fn closure_last_error() -> String {
    // SAFETY: a null buffer asks for the length only; `buf` then holds it.
    let n =
        unsafe { rang_core::ffi_closure::rang_core_closure_last_error(std::ptr::null_mut(), 0) };
    let mut buf = vec![0_u8; n];
    // SAFETY: `buf` holds `n` bytes.
    unsafe { rang_core::ffi_closure::rang_core_closure_last_error(buf.as_mut_ptr(), n) };
    String::from_utf8_lossy(&buf).into_owned()
}

/// `rang_core_closure_scores`: per-sample closure scores of one family.
/// `data`, `model` (complex64) and `weights` (float32) are `(nrow, nchan,
/// 4)`, `usable` (uint8) and the outputs `residual`, `tv` (float32) and
/// `count` (uint16) `(nrow, nchan)`, the row columns (uint32) `(nrow,)`.
/// Raises ValueError on invalid input (the core's message) and
/// RuntimeError on a panic in the core.
#[pyfunction]
#[pyo3(signature = (
    data, model, weights, usable, antenna1, antenna2, time_index, stations,
    nant, ntime, family, min_closures, reroute, residual, tv, count
))]
#[allow(clippy::too_many_arguments)]
fn closure_scores(
    py: Python<'_>,
    data: Ro<'_, Complex32>,
    model: Ro<'_, Complex32>,
    weights: Ro<'_, f32>,
    usable: Ro<'_, u8>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    time_index: Ro<'_, u32>,
    stations: Ro<'_, u32>,
    nant: usize,
    ntime: usize,
    family: u32,
    min_closures: u32,
    reroute: u32,
    mut residual: Rw<'_, f32>,
    mut tv: Rw<'_, f32>,
    mut count: Rw<'_, u16>,
) -> PyResult<()> {
    let shape = data.as_array().shape().to_vec();
    if shape.len() != 3 || shape[2] != 4 {
        return Err(PyValueError::new_err(format!(
            "data must be (row, chan, 4), not {shape:?}"
        )));
    }
    let (nrow, nchan) = (shape[0], shape[1]);
    let nstation = stations.as_array().len();
    let inputs = rang_core::ffi_closure::ClosureInputsC {
        nrow,
        nchan,
        nant,
        ntime,
        nstation,
        data: exact_input(&data, "data", &[nrow, nchan, 4])? as *const f32,
        model: exact_input(&model, "model", &[nrow, nchan, 4])? as *const f32,
        weights: exact_input(&weights, "weights", &[nrow, nchan, 4])?,
        usable: exact_input(&usable, "usable", &[nrow, nchan])?,
        antenna1: exact_input(&antenna1, "antenna1", &[nrow])?,
        antenna2: exact_input(&antenna2, "antenna2", &[nrow])?,
        time_index: exact_input(&time_index, "time_index", &[nrow])?,
        stations: exact_input(&stations, "stations", &[nstation])?,
        family,
        min_closures,
        reroute,
    };
    let residual = exact_output(&mut residual, "residual", &[nrow, nchan])?;
    let tv = exact_output(&mut tv, "tv", &[nrow, nchan])?;
    let count = exact_output(&mut count, "count", &[nrow, nchan])?;
    // SAFETY: every pointer borrows a live NumPy buffer of the checked shape
    // for the duration of the call; the outputs are distinct writable arrays.
    let status = detach(py, || {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| unsafe {
            rang_core::ffi_closure::rang_core_closure_scores(&inputs, residual, tv, count)
        }))
        .unwrap_or(2)
    });
    match status {
        0 => Ok(()),
        1 => Err(PyValueError::new_err(format!(
            "closure kernel failed (1): {}",
            closure_last_error()
        ))),
        s => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
            "closure kernel failed ({s}): a panic in the core"
        ))),
    }
}

/// `rang_core_fluxstd_eval`: `out[k] = 10^(sum_j coeffs[j] *
/// log10(freq[k] / unit_hz)^j)`, all float64, `out` as long as `freq`.
/// Raises ValueError when the core rejects the input (no coefficients, a
/// non-positive frequency or unit) and RuntimeError on a panic.
#[pyfunction]
fn fluxstd_eval(
    py: Python<'_>,
    coeffs: Ro<'_, f64>,
    unit_hz: f64,
    freq: Ro<'_, f64>,
    mut out: Rw<'_, f64>,
) -> PyResult<()> {
    let ncoeff = coeffs.as_array().len();
    let nfreq = freq.as_array().len();
    let coeffs = exact_input(&coeffs, "coeffs", &[ncoeff])?;
    let freq = exact_input(&freq, "freq", &[nfreq])?;
    let out = exact_output(&mut out, "out", &[nfreq])?;
    // SAFETY: the pointers borrow live NumPy buffers of the checked lengths;
    // `out` is a distinct writable array.
    let status = detach(py, || {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| unsafe {
            rang_core::ffi_fluxstd::rang_core_fluxstd_eval(
                ncoeff, coeffs, unit_hz, nfreq, freq, out,
            )
        }))
        .unwrap_or(2)
    });
    match status {
        0 => Ok(()),
        1 => Err(PyValueError::new_err(
            "rang_core_fluxstd_eval rejected its input (no coefficients, or a non-positive frequency or unit)",
        )),
        s => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
            "rang_core_fluxstd_eval failed ({s}): a panic in the core"
        ))),
    }
}

/// The extension module `rang._core`.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add(
        "__doc__",
        "PyO3 extension over the Rang core (research/core-j-packaging.md, research/p7-architecture.md)",
    )?;
    m.add_function(wrap_pyfunction!(data_address, m)?)?;
    m.add_function(wrap_pyfunction!(fused, m)?)?;
    m.add_function(wrap_pyfunction!(solve_complex, m)?)?;
    m.add_function(wrap_pyfunction!(solve_options_parse, m)?)?;
    m.add_function(wrap_pyfunction!(predict_components, m)?)?;
    m.add_function(wrap_pyfunction!(blosc_size, m)?)?;
    m.add_function(wrap_pyfunction!(blosc_decode, m)?)?;
    m.add_function(wrap_pyfunction!(blosc_decode_rows, m)?)?;
    m.add_function(wrap_pyfunction!(blosc_header, m)?)?;
    m.add_function(wrap_pyfunction!(blosc_decode_block, m)?)?;
    m.add_function(wrap_pyfunction!(blosc_decode_span_rows, m)?)?;
    m.add_function(wrap_pyfunction!(blosc_decode_span_rows_strided, m)?)?;
    m.add_function(wrap_pyfunction!(correct_stokes_i, m)?)?;
    m.add_function(wrap_pyfunction!(weight_grid_shape, m)?)?;
    m.add_function(wrap_pyfunction!(padded_size, m)?)?;
    m.add_function(wrap_pyfunction!(stokes_i, m)?)?;
    m.add_function(wrap_pyfunction!(imaging_weights, m)?)?;
    m.add_function(wrap_pyfunction!(grid_invert, m)?)?;
    m.add_function(wrap_pyfunction!(grid_kernel, m)?)?;
    m.add_function(wrap_pyfunction!(wgridder_vis2dirty_f64, m)?)?;
    m.add_function(wrap_pyfunction!(wgridder_vis2dirty_f32, m)?)?;
    m.add_function(wrap_pyfunction!(wgridder_dirty2vis_f64, m)?)?;
    m.add_function(wrap_pyfunction!(wgridder_dirty2vis_f32, m)?)?;
    m.add_function(wrap_pyfunction!(wgridder_kernel_row, m)?)?;
    m.add_function(wrap_pyfunction!(wgridder_last_error, m)?)?;
    m.add_function(wrap_pyfunction!(clean::clean_certified, m)?)?;
    #[cfg(feature = "gpu")]
    m.add_function(wrap_pyfunction!(grid_invert_gpu, m)?)?;
    #[cfg(feature = "gpu")]
    m.add_function(wrap_pyfunction!(grid_gpu_adapter, m)?)?;
    m.add_function(wrap_pyfunction!(flag_rows, m)?)?;
    m.add_function(wrap_pyfunction!(gain_tv, m)?)?;
    m.add_function(wrap_pyfunction!(trend_slopes, m)?)?;
    m.add_function(wrap_pyfunction!(response_jacobian, m)?)?;
    m.add_function(wrap_pyfunction!(response_normals, m)?)?;
    m.add_function(wrap_pyfunction!(response_step, m)?)?;
    m.add_function(wrap_pyfunction!(project_out, m)?)?;
    m.add_function(wrap_pyfunction!(sim_cli, m)?)?;
    m.add_class::<MsTable>()?;
    m.add_class::<MsWriter>()?;
    m.add_function(wrap_pyfunction!(ms_serialisation_check, m)?)?;
    m.add_function(wrap_pyfunction!(ms_serialisation_check_e5, m)?)?;
    m.add_function(wrap_pyfunction!(ms_describe, m)?)?;
    m.add_function(wrap_pyfunction!(ms_multifile_check, m)?)?;
    m.add_function(wrap_pyfunction!(ms_create_table, m)?)?;
    m.add_function(wrap_pyfunction!(ms_default_ms, m)?)?;
    m.add_function(wrap_pyfunction!(ms_default_ms_subtable, m)?)?;
    m.add_function(wrap_pyfunction!(ms_caltable_main, m)?)?;
    m.add_function(wrap_pyfunction!(ms_caltable_subtable, m)?)?;
    m.add_function(wrap_pyfunction!(ms_read_cells, m)?)?;
    m.add_function(wrap_pyfunction!(ms_array_records, m)?)?;
    m.add_function(wrap_pyfunction!(closure_scores, m)?)?;
    m.add_function(wrap_pyfunction!(fluxstd_eval, m)?)?;
    m.add_function(wrap_pyfunction!(cal_apply, m)?)?;
    // Task C2a: the gain term G (research/c2a-gain.md).
    m.add_function(wrap_pyfunction!(cal_gain::cal_gain_solve, m)?)?;
    m.add_function(wrap_pyfunction!(cal_gain::cal_gain_minblperant, m)?)?;
    m.add_function(wrap_pyfunction!(cal_gain::cal_gain_apply_refant, m)?)?;
    m.add_function(wrap_pyfunction!(cal_apply_jones, m)?)?;
    Ok(())
}
