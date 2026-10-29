//! C ABI for the Python layer (ctypes), in the style of the existing kernels.
//!
//! Phase 1 deliberately uses a C ABI rather than PyO3: the existing kernels
//! are loaded through ctypes, the checks build offline, and no new crates are
//! needed. Every pointer is described by an explicit length in the structs.

use crate::fused::{self, Inputs, Model, Outputs, SPLITS};

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
