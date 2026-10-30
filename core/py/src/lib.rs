//! `rangtoy._core`: the PyO3 extension module over the Rang core.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Task J of `research/core-parallel-plan.md` (`research/core-j-packaging.md`).
//! Every function here is a second entry door into the same C ABI function
//! of `rang_core::ffi*`: NumPy arrays are borrowed in place as read-only or
//! read-write slices (never copied; non-contiguous arrays and read-only
//! outputs are refused), their pointers fill the `#[repr(C)]` structs, and the
//! status code of the C function is returned for the Python wrapper to
//! interpret exactly as it interprets the ctypes call. The Measurement Set
//! reader is a `MsTable` class over `rang_core::ms::Table` whose column bytes
//! move into a NumPy array without a copy. No kernel code lives here.

use numpy::{Element, IntoPyArray, PyArray1, PyReadonlyArrayDyn, PyReadwriteArrayDyn};
use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use rang_core::ffi;
use rang_core::ffi_correct::CorrectInputsC;
use rang_core::ffi_flag::{FlagInputs, FlagOutputs};
use rang_core::ffi_grid::{GridInputs, GridOutputs};
use rang_core::ffi_weights::{
    ImagingWeightInputs, ImagingWeightOutputs, StokesIInputs, StokesIOutputs,
};
use rang_core::ms::{DataType, Table};

type Ro<'py, T> = PyReadonlyArrayDyn<'py, T>;
type Rw<'py, T> = PyReadwriteArrayDyn<'py, T>;
/// A column read: packed bytes, nrows, cell shape, dtype code, nstrings.
type Column<'py> = (Bound<'py, PyArray1<u8>>, u64, Vec<i64>, i32, usize);

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
    Ok(unsafe { ffi::rang_core_fused(&inputs, &mut outputs) })
}

/// `rang_core_solve_complex`; returns (status, iterations, converged fraction).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn solve_complex(
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
    let status = unsafe { ffi::rang_core_solve_complex(&inputs, &mut outputs) };
    Ok((status, iterations, converged))
}

/// `rang_core_predict_components`; returns its status code.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn predict_components(
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
    Ok(unsafe { ffi::rang_core_predict_components(&inputs, &mut outputs) })
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
        // SAFETY: `buf` is the fresh bytes object's buffer of `size` bytes.
        status = unsafe {
            ffi::rang_core_blosc_decode(
                payload.as_ptr(),
                payload.len(),
                buf.as_mut_ptr(),
                buf.len(),
            )
        };
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
        status = unsafe {
            ffi::rang_core_blosc_decode_rows(
                payload.as_ptr(),
                payload.len(),
                row_bytes,
                rows.as_ptr(),
                rows.len(),
                buf.as_mut_ptr(),
                &mut blocks,
            )
        };
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
fn blosc_decode_block(head: &[u8], j: usize, block: &[u8], mut out: Rw<'_, u8>) -> PyResult<i32> {
    let out = out.as_slice_mut()?;
    // SAFETY: every slice is live for the call.
    Ok(unsafe {
        ffi::rang_core_blosc_decode_block(
            head.as_ptr(),
            head.len(),
            j,
            block.as_ptr(),
            block.len(),
            out.as_mut_ptr(),
            out.len(),
        )
    })
}

/// `rang_core_blosc_decode_span_rows` into a caller-owned uint8 array of
/// `len(rows) * row_bytes` bytes.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn blosc_decode_span_rows(
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
    Ok(unsafe {
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
    })
}

/// `rang_core_correct_stokes_i` on borrowed arrays (big plan P5,
/// `research/p5-memory.md`); `added` may be None. Returns the C status.
#[pyfunction]
#[pyo3(signature = (nrow, nchan, ntime_bins, nfreq_bins, nant, data, weights, flags, flag_row, added, antenna1, antenna2, time_bin, freq_bin, inverse, valid, sample, weight))]
#[allow(clippy::too_many_arguments)]
fn correct_stokes_i(
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
    Ok(unsafe {
        rang_core::ffi_correct::rang_core_correct_stokes_i(
            &inputs,
            sample.as_mut_ptr(),
            weight.as_mut_ptr(),
        )
    })
}

/// `rang_core_blosc_decode_span_rows_strided`: rows land at byte
/// `offset + i * stride` of the caller-owned uint8 array `out` (P5).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn blosc_decode_span_rows_strided(
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
    Ok(unsafe {
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
    })
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
    Ok(unsafe { rang_core::ffi_weights::rang_core_stokes_i(&inputs, &mut outputs) })
}

/// `rang_core_imaging_weights`; returns its status code.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn imaging_weights(
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
    Ok(unsafe { rang_core::ffi_weights::rang_core_imaging_weights(&inputs, &mut outputs) })
}

/// `rang_core_grid_invert`; returns its status code.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn grid_invert(
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
    Ok(unsafe { rang_core::ffi_grid::rang_core_grid_invert(&inputs, &mut outputs) })
}

/// `rang_core_grid_kernel` into a caller-owned float64 array.
#[pyfunction]
fn grid_kernel(kernel_size: usize, oversampling: usize, mut kernel: Rw<'_, f64>) -> PyResult<i32> {
    let out = kernel.as_slice_mut()?;
    if out.len() != kernel_size * oversampling {
        return Ok(1);
    }
    // SAFETY: `out` has the documented length.
    Ok(unsafe {
        rang_core::ffi_grid::rang_core_grid_kernel(kernel_size, oversampling, out.as_mut_ptr())
    })
}

/// `rang_core_flag_rows`; returns its status code.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn flag_rows(
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
    Ok(unsafe { rang_core::ffi_flag::rang_core_flag_rows(&inputs, &mut outputs) })
}

/// An open casacore table (read-only), the counterpart of the C ABI handle.
#[pyclass(unsendable)]
struct MsTable {
    table: Table,
}

#[pymethods]
impl MsTable {
    #[new]
    fn new(path: &str) -> PyResult<Self> {
        match Table::open(path) {
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
        let data = self
            .table
            .read_column(name, start, count)
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

/// The extension module `rangtoy._core`.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add(
        "__doc__",
        "PyO3 extension over the Rang core (research/core-j-packaging.md)",
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
    m.add_class::<MsTable>()?;
    Ok(())
}
