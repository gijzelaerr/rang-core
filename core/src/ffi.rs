//! C ABI for the Python layer (ctypes), in the style of the existing kernels.
//!
//! Phase 1 deliberately uses a C ABI rather than PyO3: the existing kernels
//! are loaded through ctypes, the checks build offline, and no new crates are
//! needed. Every pointer is described by an explicit length in the structs.

use crate::blosc;
use crate::fused::{self, Inputs, Model, Outputs, SPLITS};
use crate::predict;
use crate::solve;

/// Borrowed input buffers. A null optional pointer means "absent".
#[repr(C)]
pub struct FusedInputs {
    pub nrow: usize,
    pub nchan: usize,
    pub ntime_bins: usize,
    pub nfreq_bins: usize,
    pub nant: usize,
    pub data: *const f32,
    pub weights: *const f32,
    /// Stored model, `nrow * nchan * 8` floats, or null.
    pub model_stored: *const f32,
    /// Scalar model, `nchan` doubles, or null. Exactly one model is given.
    pub model_scalar: *const f64,
    pub antenna1: *const u32,
    pub antenna2: *const u32,
    pub time_bin: *const u32,
    pub freq_bin: *const u32,
    pub gains: *const f64,
    pub gain_valid: *const u8,
    pub split: *const u8,
}

/// Caller-owned output buffers; null skips that product.
#[repr(C)]
pub struct FusedOutputs {
    pub residuals: *mut f64,
    pub scores: *mut f64,
    pub diag_h: *mut f64,
    pub diag_b: *mut f64,
    pub diag_count: *mut u64,
    /// Four values per split (sum, cells, invalid, nonfinite), train first.
    pub split_stats: *mut f64,
}

unsafe fn slice<'a, T>(ptr: *const T, len: usize) -> Option<&'a [T]> {
    if ptr.is_null() {
        None
    } else {
        // SAFETY: the caller guarantees `len` live, aligned elements.
        Some(unsafe { std::slice::from_raw_parts(ptr, len) })
    }
}

unsafe fn slice_mut<'a, T>(ptr: *mut T, len: usize) -> &'a mut [T] {
    if ptr.is_null() {
        &mut []
    } else {
        // SAFETY: the caller guarantees `len` live, aligned, unaliased elements.
        unsafe { std::slice::from_raw_parts_mut(ptr, len) }
    }
}

/// Run the fused pass. Returns 0 on success, 1 on invalid arguments, 2 on a
/// panic.
///
/// # Safety
/// Every non-null pointer must reference live, aligned, nonoverlapping
/// buffers of the lengths documented on `fused::Inputs` and
/// `fused::Outputs`, and `split_stats` must hold 12 doubles.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_fused(
    inputs: *const FusedInputs,
    outputs: *mut FusedOutputs,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        // SAFETY: the caller passes valid struct pointers.
        let (i, o) = unsafe {
            match (inputs.as_ref(), outputs.as_mut()) {
                (Some(i), Some(o)) => (i, o),
                _ => return 1,
            }
        };
        let cells = i.nrow.saturating_mul(i.nchan);
        let gains = i
            .ntime_bins
            .saturating_mul(i.nfreq_bins)
            .saturating_mul(i.nant);
        // SAFETY: lengths follow the documented contract.
        unsafe {
            let model = match (
                slice(i.model_stored, 8 * cells),
                slice(i.model_scalar, i.nchan),
            ) {
                (Some(m), None) => Model::Stored(m),
                (None, Some(s)) => Model::Scalar(s),
                _ => return 1,
            };
            let required = (
                slice(i.data, 8 * cells),
                slice(i.weights, 4 * cells),
                slice(i.antenna1, i.nrow),
                slice(i.antenna2, i.nrow),
                slice(i.time_bin, i.nrow),
                slice(i.freq_bin, i.nchan),
                slice(i.gains, 8 * gains),
                slice(i.gain_valid, gains),
                slice(i.split, cells),
            );
            let (
                Some(data),
                Some(weights),
                Some(antenna1),
                Some(antenna2),
                Some(time_bin),
                Some(freq_bin),
                Some(gain_values),
                Some(gain_valid),
                Some(split),
            ) = required
            else {
                return 1;
            };
            if o.split_stats.is_null() {
                return 1;
            }
            let view = Inputs {
                nrow: i.nrow,
                nchan: i.nchan,
                ntime_bins: i.ntime_bins,
                nfreq_bins: i.nfreq_bins,
                nant: i.nant,
                data,
                weights,
                model,
                antenna1,
                antenna2,
                time_bin,
                freq_bin,
                gains: gain_values,
                gain_valid,
                split,
            };
            let mut out = Outputs {
                residuals: slice_mut(o.residuals, 8 * cells),
                scores: slice_mut(o.scores, cells),
                diag_h: slice_mut(o.diag_h, 64 * gains),
                diag_b: slice_mut(o.diag_b, 8 * gains),
                diag_count: slice_mut(o.diag_count, gains),
            };
            match fused::run(&view, &mut out) {
                Ok(stats) => {
                    let target = slice_mut(o.split_stats, 4 * SPLITS);
                    for (k, s) in stats.iter().enumerate() {
                        target[4 * k] = s.sum;
                        target[4 * k + 1] = s.cells as f64;
                        target[4 * k + 2] = s.invalid as f64;
                        target[4 * k + 3] = s.nonfinite as f64;
                    }
                    0
                }
                Err(_) => 1,
            }
        }
    });
    result.unwrap_or(2)
}

/// Borrowed inputs of the `complex` solver.
#[repr(C)]
pub struct SolveInputs {
    pub nrow: usize,
    pub nchan: usize,
    pub ntime_bins: usize,
    pub nfreq_bins: usize,
    pub nant: usize,
    pub data: *const f32,
    pub weights: *const f32,
    pub model_stored: *const f32,
    pub model_scalar: *const f64,
    pub flag: *const u8,
    pub flag_row: *const u8,
    pub antenna1: *const u32,
    pub antenna2: *const u32,
    pub time_bin: *const u32,
    pub freq_bin: *const u32,
    pub max_iterations: usize,
    pub stop_criterion: f64,
    pub stop_fraction: f64,
}

/// Caller-owned outputs of the `complex` solver.
#[repr(C)]
pub struct SolveOutputs {
    /// `ntime_bins * nfreq_bins * nant * 8` doubles.
    pub gains: *mut f64,
    /// `ntime_bins * nfreq_bins * nant` flags: 1 flagged, 0 unflagged.
    pub flags: *mut i8,
    pub iterations: *mut usize,
    pub converged_fraction: *mut f64,
}

/// Run the ported QuartiCal `complex` solver. Returns 0 on success, 1 on
/// invalid arguments, 3 on a complex division by zero, 2 on a panic.
///
/// # Safety
/// Every non-null pointer must reference live, aligned, nonoverlapping
/// buffers of the lengths documented on `solve::Problem` and `SolveOutputs`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_solve_complex(
    inputs: *const SolveInputs,
    outputs: *mut SolveOutputs,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        // SAFETY: the caller passes valid struct pointers.
        let (i, o) = unsafe {
            match (inputs.as_ref(), outputs.as_mut()) {
                (Some(i), Some(o)) => (i, o),
                _ => return 1,
            }
        };
        let cells = i.nrow.saturating_mul(i.nchan);
        let ngains = i
            .ntime_bins
            .saturating_mul(i.nfreq_bins)
            .saturating_mul(i.nant);
        if i.max_iterations == 0
            || o.gains.is_null()
            || o.flags.is_null()
            || o.iterations.is_null()
            || o.converged_fraction.is_null()
        {
            return 1;
        }
        // SAFETY: lengths follow the documented contract.
        unsafe {
            let model = match (
                slice(i.model_stored, 8 * cells),
                slice(i.model_scalar, i.nchan),
            ) {
                (Some(m), None) => Model::Stored(m),
                (None, Some(s)) => Model::Scalar(s),
                _ => return 1,
            };
            let (
                Some(data),
                Some(weights),
                Some(flag),
                Some(flag_row),
                Some(antenna1),
                Some(antenna2),
                Some(time_bin),
                Some(freq_bin),
            ) = (
                slice(i.data, 8 * cells),
                slice(i.weights, 4 * cells),
                slice(i.flag, 4 * cells),
                slice(i.flag_row, i.nrow),
                slice(i.antenna1, i.nrow),
                slice(i.antenna2, i.nrow),
                slice(i.time_bin, i.nrow),
                slice(i.freq_bin, i.nchan),
            )
            else {
                return 1;
            };
            let problem = solve::Problem {
                nrow: i.nrow,
                nchan: i.nchan,
                ntime_bins: i.ntime_bins,
                nfreq_bins: i.nfreq_bins,
                nant: i.nant,
                data,
                weights,
                model,
                flag,
                flag_row,
                antenna1,
                antenna2,
                time_bin,
                freq_bin,
            };
            let settings = solve::Settings {
                max_iterations: i.max_iterations,
                stop_criterion: i.stop_criterion,
                stop_fraction: i.stop_fraction,
            };
            match solve::solve(&problem, &settings) {
                Ok(solution) => {
                    let gains = slice_mut(o.gains, 8 * ngains);
                    for (g, jones) in solution.gains.iter().enumerate() {
                        for (k, value) in jones.iter().enumerate() {
                            gains[8 * g + 2 * k] = value.re;
                            gains[8 * g + 2 * k + 1] = value.im;
                        }
                    }
                    slice_mut(o.flags, ngains).copy_from_slice(&solution.flags);
                    *o.iterations = solution.iterations;
                    *o.converged_fraction = solution.converged_fraction;
                    0
                }
                Err(solve::Error::ZeroDivision) => 3,
                Err(_) => 1,
            }
        }
    });
    result.unwrap_or(2)
}

/// Borrowed inputs of the component predictor.
#[repr(C)]
pub struct PredictInputs {
    pub nrow: usize,
    pub nchan: usize,
    pub nsrc: usize,
    pub ncoeff: usize,
    /// `nrow * 3` metres.
    pub uvw: *const f64,
    /// `nchan` hertz.
    pub frequency: *const f64,
    /// `nsrc * 2` direction cosines.
    pub lm: *const f64,
    /// `nsrc` kinds: 0 point, 1 Gaussian.
    pub kind: *const u8,
    pub flux: *const f64,
    /// `nsrc * ncoeff`.
    pub coeffs: *const f64,
    /// `nsrc` flags: nonzero for a logarithmic polynomial.
    pub log_poly: *const u8,
    pub ref_freq: *const f64,
    /// `nsrc * 3`: major FWHM, minor FWHM (radians), position angle.
    pub gauss_shape: *const f64,
}

/// Caller-owned outputs of the component predictor.
#[repr(C)]
pub struct PredictOutputs {
    /// `nrow * nchan * 2` doubles: complex128 visibilities.
    pub vis: *mut f64,
    /// `nsrc * nchan` spectra, or null.
    pub spectra: *mut f64,
}

/// Predict Stokes I visibilities of WSClean-format components. Returns 0 on
/// success, 1 on invalid arguments, 2 on a panic.
///
/// # Safety
/// Every non-null pointer must reference live, aligned, nonoverlapping
/// buffers of the lengths documented on `PredictInputs` and `PredictOutputs`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_predict_components(
    inputs: *const PredictInputs,
    outputs: *mut PredictOutputs,
) -> i32 {
    let result = std::panic::catch_unwind(|| {
        // SAFETY: the caller passes valid struct pointers.
        let (i, o) = unsafe {
            match (inputs.as_ref(), outputs.as_mut()) {
                (Some(i), Some(o)) => (i, o),
                _ => return 1,
            }
        };
        if o.vis.is_null() {
            return 1;
        }
        // SAFETY: lengths follow the documented contract.
        unsafe {
            let (
                Some(uvw),
                Some(frequency),
                Some(lm),
                Some(kind_raw),
                Some(flux),
                Some(coeffs),
                Some(log_raw),
                Some(ref_freq),
                Some(gauss_shape),
            ) = (
                slice(i.uvw, 3 * i.nrow),
                slice(i.frequency, i.nchan),
                slice(i.lm, 2 * i.nsrc),
                slice(i.kind, i.nsrc),
                slice(i.flux, i.nsrc),
                slice(i.coeffs, i.nsrc * i.ncoeff),
                slice(i.log_poly, i.nsrc),
                slice(i.ref_freq, i.nsrc),
                slice(i.gauss_shape, 3 * i.nsrc),
            )
            else {
                return 1;
            };
            let mut kind = Vec::with_capacity(i.nsrc);
            for &k in kind_raw {
                kind.push(match k {
                    0 => predict::Kind::Point,
                    1 => predict::Kind::Gaussian,
                    _ => return 1,
                });
            }
            let log_poly: Vec<bool> = log_raw.iter().map(|&x| x != 0).collect();
            let components = predict::Components {
                lm,
                kind: &kind,
                flux,
                coeffs,
                ncoeff: i.ncoeff,
                log_poly: &log_poly,
                ref_freq,
                gauss_shape,
            };
            let Ok(vis) = predict::predict(uvw, frequency, &components) else {
                return 1;
            };
            let out = slice_mut(o.vis, 2 * i.nrow * i.nchan);
            for (k, value) in vis.iter().enumerate() {
                out[2 * k] = value.re;
                out[2 * k + 1] = value.im;
            }
            if !o.spectra.is_null() {
                let Ok(spec) = predict::spectra(&components, frequency) else {
                    return 1;
                };
                slice_mut(o.spectra, i.nsrc * i.nchan).copy_from_slice(&spec);
            }
            0
        }
    });
    result.unwrap_or(2)
}

/// Decoded length of a blosc chunk. Returns 0 on success, 1 on error.
///
/// # Safety
/// `src` must reference `len` readable bytes and `nbytes` one writable usize.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_blosc_size(
    src: *const u8,
    len: usize,
    nbytes: *mut usize,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: the caller guarantees the buffers.
        unsafe {
            let (Some(src), false) = (slice(src, len), nbytes.is_null()) else {
                return 1;
            };
            match blosc::header(src) {
                Ok(h) => {
                    *nbytes = h.nbytes;
                    0
                }
                Err(_) => 1,
            }
        }
    })
    .unwrap_or(2)
}

/// Decode a whole blosc chunk into `out` (exactly its decoded length).
///
/// # Safety
/// `src` must reference `len` readable bytes and `out` `out_len` writable bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_blosc_decode(
    src: *const u8,
    len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: the caller guarantees the buffers.
        unsafe {
            let Some(src) = slice(src, len) else {
                return 1;
            };
            if out.is_null() {
                return 1;
            }
            match blosc::decode_into(src, slice_mut(out, out_len)) {
                Ok(()) => 0,
                Err(_) => 1,
            }
        }
    })
    .unwrap_or(2)
}

/// Decode selected rows of a row-major blosc chunk, expanding only the blocks
/// that contain them.
///
/// # Safety
/// `src` must reference `len` readable bytes, `rows` `nrows` usize values,
/// `out` `nrows * row_bytes` writable bytes and `blocks` one writable usize.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_blosc_decode_rows(
    src: *const u8,
    len: usize,
    row_bytes: usize,
    rows: *const usize,
    nrows: usize,
    out: *mut u8,
    blocks: *mut usize,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: the caller guarantees the buffers.
        unsafe {
            let (Some(src), Some(rows)) = (slice(src, len), slice(rows, nrows)) else {
                return 1;
            };
            if out.is_null() || blocks.is_null() {
                return 1;
            }
            let out = slice_mut(out, nrows * row_bytes);
            match blosc::decode_rows(src, row_bytes, rows, out) {
                Ok(n) => {
                    *blocks = n;
                    0
                }
                Err(_) => 1,
            }
        }
    })
    .unwrap_or(2)
}

/// Header fields of a blosc chunk from its first bytes: writes nbytes,
/// blocksize, number of blocks and typesize. Returns 0 on success.
///
/// # Safety
/// `head` must reference `len` readable bytes (at least the 16-byte header)
/// and `fields` four writable usize values.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_blosc_header(
    head: *const u8,
    len: usize,
    fields: *mut usize,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: the caller guarantees the buffers.
        unsafe {
            let Some(head) = slice(head, len) else {
                return 1;
            };
            if fields.is_null() {
                return 1;
            }
            match blosc::parse_header(head) {
                Ok(h) => {
                    let out = slice_mut(fields, 4);
                    out.copy_from_slice(&[h.nbytes, h.blocksize, h.nblocks(), h.typesize]);
                    0
                }
                Err(_) => 1,
            }
        }
    })
    .unwrap_or(2)
}

/// Decode block `j` from its compressed bytes. `head` holds the chunk's first
/// bytes (header and, for compressed chunks, the block-start table).
///
/// # Safety
/// `head` must reference `head_len` bytes, `block` `block_len` bytes and
/// `out` `out_len` writable bytes (the block's decoded length).
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_blosc_decode_block(
    head: *const u8,
    head_len: usize,
    j: usize,
    block: *const u8,
    block_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: the caller guarantees the buffers.
        unsafe {
            let (Some(head), Some(block)) = (slice(head, head_len), slice(block, block_len)) else {
                return 1;
            };
            if out.is_null() {
                return 1;
            }
            let Ok(h) = blosc::parse_header(head) else {
                return 1;
            };
            let mut scratch = Vec::new();
            match blosc::decode_block_bytes(&h, j, block, slice_mut(out, out_len), &mut scratch) {
                Ok(()) => 0,
                Err(_) => 1,
            }
        }
    })
    .unwrap_or(2)
}

/// Decode a run of consecutive blocks and copy the requested rows.
///
/// # Safety
/// `head` (`head_len` bytes) holds the header and block-start table, `span`
/// (`span_len` bytes) the compressed bytes from block `first`'s offset,
/// `rows` `nrows` usize values and `out` `nrows * row_bytes` writable bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_blosc_decode_span_rows(
    head: *const u8,
    head_len: usize,
    first: usize,
    count: usize,
    span: *const u8,
    span_len: usize,
    row_bytes: usize,
    rows: *const usize,
    nrows: usize,
    out: *mut u8,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: the caller guarantees the buffers.
        unsafe {
            let (Some(head), Some(span), Some(rows)) = (
                slice(head, head_len),
                slice(span, span_len),
                slice(rows, nrows),
            ) else {
                return 1;
            };
            if out.is_null() {
                return 1;
            }
            let Ok(h) = blosc::parse_header(head) else {
                return 1;
            };
            let Ok((span_start, _)) = blosc::block_span(head, &h, first) else {
                return 1;
            };
            match blosc::decode_span_rows(
                head,
                &h,
                first,
                count,
                span,
                span_start,
                row_bytes,
                rows,
                slice_mut(out, nrows * row_bytes),
            ) {
                Ok(()) => 0,
                Err(_) => 1,
            }
        }
    })
    .unwrap_or(2)
}
