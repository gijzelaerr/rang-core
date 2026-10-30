//! `rangtoy._core`: the PyO3 extension module over the Rang core.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Task J of `research/core-parallel-plan.md` (`research/core-j-packaging.md`)
//! made this a second entry door into the C ABI of `rang_core::ffi*`; task P7
//! (`research/p7-architecture.md`) made it the only one. Every function calls
//! the same C function a C consumer would: NumPy arrays are borrowed in place
//! as read-only or read-write slices (never copied; non-contiguous arrays and
//! read-only outputs are refused), their pointers fill the `#[repr(C)]`
//! structs, and the status code of the C function is returned for the Python
//! wrapper to interpret. P7 adds the root crate's kernels (`rang_toy`, reached
//! as `rang_core::toy`: gain TV, phase trend, anchored response, projector)
//! and the pointing toy's command line, and releases the GIL around every
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
    Element, IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArrayDyn, PyReadwriteArrayDyn,
};
use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use rang_core::ffi;
use rang_core::ffi_correct::CorrectInputsC;
use rang_core::ffi_flag::{FlagInputs, FlagOutputs};
use rang_core::ffi_grid::{GridInputs, GridOutputs};
use rang_core::ffi_ms_write::{keyword_value, new_column};
use rang_core::ffi_weights::{
    ImagingWeightInputs, ImagingWeightOutputs, StokesIInputs, StokesIOutputs,
};
use rang_core::ms::{DataType, Table};
use rang_core::ms_write::TableWriter;
use rang_core::toy;

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

/// Borrowed pointer of a required input array.
fn ptr<T: Element>(a: &Ro<'_, T>) -> PyResult<*const T> {
    Ok(a.as_slice()?.as_ptr())
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
    Ok(a.as_slice_mut()?.as_mut_ptr())
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
    let s = a.as_slice()?;
    Ok((s.len() == len).then_some(s.as_ptr()))
}

/// Pointer of an output that must hold exactly `len` elements.
fn sized_mut<T: Element>(a: &mut Rw<'_, T>, len: usize) -> PyResult<Option<*mut T>> {
    let s = a.as_slice_mut()?;
    Ok((s.len() == len).then_some(s.as_mut_ptr()))
}

/// The address the extension reads an array at, through the same
/// `as_slice` path every function uses (criterion 4 of the protocol).
#[pyfunction]
fn data_address(array: &Bound<'_, PyAny>) -> PyResult<usize> {
    fn address<T: Element>(a: Ro<'_, T>) -> PyResult<usize> {
        Ok(a.as_slice()?.as_ptr() as usize)
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
    let inputs = ffi::FusedInputs {
        nrow,
        nchan,
        ntime_bins,
        nfreq_bins,
        nant,
        data: ptr(&data)?,
        weights: ptr(&weights)?,
        model_stored: opt_ptr(&model_stored)?,
        model_scalar: opt_ptr(&model_scalar)?,
        antenna1: ptr(&antenna1)?,
        antenna2: ptr(&antenna2)?,
        time_bin: ptr(&time_bin)?,
        freq_bin: ptr(&freq_bin)?,
        gains: ptr(&gains)?,
        gain_valid: ptr(&gain_valid)?,
        split: ptr(&split)?,
    };
    let mut outputs = ffi::FusedOutputs {
        residuals: opt_ptr_mut(&mut residuals)?,
        scores: opt_ptr_mut(&mut scores)?,
        diag_h: opt_ptr_mut(&mut diag_h)?,
        diag_b: opt_ptr_mut(&mut diag_b)?,
        diag_count: opt_ptr_mut(&mut diag_count)?,
        split_stats: ptr_mut(&mut split_stats)?,
    };
    // SAFETY: every pointer borrows a live, contiguous NumPy buffer held by
    // the arguments for the duration of the call; the Python wrapper sizes
    // them as the C ABI documents.
    Ok(detach(py, || unsafe {
        ffi::rang_core_fused(&inputs, &mut outputs)
    }))
}

/// `rang_core_solve_complex`; returns (status, iterations, converged fraction).
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
) -> PyResult<(i32, usize, f64)> {
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
    let inputs = ffi::PredictInputs {
        nrow,
        nchan,
        nsrc,
        ncoeff,
        uvw: ptr(&uvw)?,
        frequency: ptr(&frequency)?,
        lm: ptr(&lm)?,
        kind: ptr(&kind)?,
        flux: ptr(&flux)?,
        coeffs: ptr(&coeffs)?,
        log_poly: ptr(&log_poly)?,
        ref_freq: ptr(&ref_freq)?,
        gauss_shape: ptr(&gauss_shape)?,
    };
    let mut outputs = ffi::PredictOutputs {
        vis: ptr_mut(&mut vis)?,
        spectra: opt_ptr_mut(&mut spectra)?,
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
    let rows = rows.as_slice()?;
    let mut status = 0;
    let mut blocks = 0usize;
    let out = PyBytes::new_with(py, rows.len() * row_bytes, |buf| {
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
    let out = out.as_slice_mut()?;
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
    let rows = rows.as_slice()?;
    let out = out.as_slice_mut()?;
    if out.len() != rows.len() * row_bytes {
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
    let gains = ntime_bins * nfreq_bins * nant;
    let (data, weights, flags, flag_row) = (
        data.as_slice()?,
        weights.as_slice()?,
        flags.as_slice()?,
        flag_row.as_slice()?,
    );
    let added = match &added {
        Some(a) => Some(a.as_slice()?),
        None => None,
    };
    let (antenna1, antenna2, time_bin, freq_bin) = (
        antenna1.as_slice()?,
        antenna2.as_slice()?,
        time_bin.as_slice()?,
        freq_bin.as_slice()?,
    );
    let (inverse, valid) = (inverse.as_slice()?, valid.as_slice()?);
    let (sample, weight) = (sample.as_slice_mut()?, weight.as_slice_mut()?);
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
    let (span, rows) = (span.as_slice()?, rows.as_slice()?);
    let out = out.as_slice_mut()?;
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
    let inputs = StokesIInputs {
        ncell,
        data: ptr(&data)?,
        weights: ptr(&weights)?,
        flags: ptr(&flags)?,
    };
    let mut outputs = StokesIOutputs {
        vis: ptr_mut(&mut vis)?,
        weight: ptr_mut(&mut weight)?,
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
    let inputs = ImagingWeightInputs {
        nrow,
        nchan,
        uvw: ptr(&uvw)?,
        wavelength: ptr(&wavelength)?,
        weights: ptr(&weights)?,
        row_selected: ptr(&row_selected)?,
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
        weights: ptr_mut(&mut out_weights)?,
        grid: opt_ptr_mut(&mut grid)?,
        sums: opt_ptr_mut(&mut sums)?,
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
        uvw: ptr(&uvw)?,
        frequencies: ptr(&frequencies)?,
        data: ptr(&data)?,
        weights: ptr(&weights)?,
        imaging_weights: ptr(&imaging_weights)?,
    };
    let mut outputs = GridOutputs {
        dirty: ptr_mut(&mut dirty)?,
        psf: ptr_mut(&mut psf)?,
        stats: ptr_mut(&mut stats)?,
    };
    // SAFETY: as in `fused`.
    Ok(detach(py, || unsafe {
        rang_core::ffi_grid::rang_core_grid_invert(&inputs, &mut outputs)
    }))
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
    let out = kernel.as_slice_mut()?;
    if Some(out.len()) != kernel_size.checked_mul(oversampling) {
        return Ok(1);
    }
    // SAFETY: `out` has the documented length.
    Ok(detach(py, || unsafe {
        rang_core::ffi_grid::rang_core_grid_kernel(kernel_size, oversampling, out.as_mut_ptr())
    }))
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
    let inputs = FlagInputs {
        nrow,
        nchan,
        ncorr,
        nant,
        nbl,
        ntime,
        nmasks,
        nsteps,
        data: ptr(&data)?,
        flags: ptr(&flags)?,
        baseline_index: ptr(&baseline_index)?,
        time_index: ptr(&time_index)?,
        baselines: ptr(&baselines)?,
        antenna_position: ptr(&antenna_position)?,
        chan_freq: ptr(&chan_freq)?,
        chan_width: ptr(&chan_width)?,
        corr_type: ptr(&corr_type)?,
        mask_freqs: ptr(&mask_freqs)?,
        mask_offsets: ptr(&mask_offsets)?,
        steps: ptr(&steps)?,
    };
    let mut outputs = FlagOutputs {
        flags: ptr_mut(&mut out_flags)?,
        intensity: opt_ptr_mut(&mut intensity)?,
        stages: opt_ptr_mut(&mut stages)?,
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
        toy::tv::rang_gain_tv(nt, nf, na, g, v, tw, fw, out)
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
        toy::trend::rang_trend_slopes(nt, nf, na, g, v, t, f, out, c)
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
        toy::response::rang_response_jacobian(p, q, m, out)
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
        toy::response::rang_response_normals(samples, gain_bins, g, m, r, w, pp, qq, bb, hh, rhs, c)
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
        toy::response::rang_response_step(fh, fb, dh, db, g, a, d, info)
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
        toy::projector::rang_project_out(
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

/// The `rang-toy` command line (`rang_toy::cli`): (true, stdout text) or
/// (false, error message). The text lacks the final newline the binary adds.
#[pyfunction]
fn toy_cli(py: Python<'_>, args: Vec<String>) -> (bool, String) {
    let result = py.detach(|| std::panic::catch_unwind(|| toy::cli(&args)));
    match result {
        Ok(Ok(text)) => (true, text),
        Ok(Err(error)) => (false, error),
        Err(_) => (false, "panic in the pointing toy".to_string()),
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
}

/// The extension module `rangtoy._core`.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add(
        "__doc__",
        "PyO3 extension over the Rang core (research/core-j-packaging.md, research/p7-architecture.md)",
    )?;
    m.add_function(wrap_pyfunction!(data_address, m)?)?;
    m.add_function(wrap_pyfunction!(fused, m)?)?;
    m.add_function(wrap_pyfunction!(solve_complex, m)?)?;
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
    m.add_function(wrap_pyfunction!(flag_rows, m)?)?;
    m.add_function(wrap_pyfunction!(gain_tv, m)?)?;
    m.add_function(wrap_pyfunction!(trend_slopes, m)?)?;
    m.add_function(wrap_pyfunction!(response_jacobian, m)?)?;
    m.add_function(wrap_pyfunction!(response_normals, m)?)?;
    m.add_function(wrap_pyfunction!(response_step, m)?)?;
    m.add_function(wrap_pyfunction!(project_out, m)?)?;
    m.add_function(wrap_pyfunction!(toy_cli, m)?)?;
    m.add_class::<MsTable>()?;
    m.add_class::<MsWriter>()?;
    m.add_function(wrap_pyfunction!(ms_serialisation_check, m)?)?;
    Ok(())
}
