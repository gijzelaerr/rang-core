//! C ABI for `correct` (big plan task P5, `research/p5-memory.md`), loaded
//! through ctypes by `python/rangtoy/core_fetch.py`. Same conventions as
//! `ffi.rs`: borrowed buffers described by explicit lengths, 0 on success,
//! 1 on invalid arguments, 2 on a panic.

use crate::blosc;
use crate::correct::{self, CorrectInputs};

/// Borrowed inputs for `rang_core_correct_stokes_i`; see
/// `correct::CorrectInputs` for the layouts.
#[repr(C)]
pub struct CorrectInputsC {
    pub nrow: usize,
    pub nchan: usize,
    pub ntime_bins: usize,
    pub nfreq_bins: usize,
    pub nant: usize,
    pub data: *const f32,
    pub weights: *const f32,
    pub flags: *const u8,
    pub flag_row: *const u8,
    /// `(row, chan)` additions, or null for none.
    pub added: *const u8,
    pub antenna1: *const u32,
    pub antenna2: *const u32,
    pub time_bin: *const u32,
    pub freq_bin: *const u32,
    pub inverse: *const f64,
    pub valid: *const u8,
}

unsafe fn slice<'a, T>(ptr: *const T, len: usize) -> Option<&'a [T]> {
    if ptr.is_null() {
        None
    } else {
        // SAFETY: the caller guarantees `len` live, aligned elements.
        Some(unsafe { std::slice::from_raw_parts(ptr, len) })
    }
}

unsafe fn slice_mut<'a, T>(ptr: *mut T, len: usize) -> Option<&'a mut [T]> {
    if ptr.is_null() {
        None
    } else {
        // SAFETY: the caller guarantees `len` live, aligned, unaliased elements.
        Some(unsafe { std::slice::from_raw_parts_mut(ptr, len) })
    }
}

/// Gain-corrected Stokes I sample (`2 * nrow * nchan` floats, interleaved
/// complex64) and reader weight (`nrow * nchan` floats) on the final flags.
///
/// # Safety
///
/// `inputs` must point to a valid `CorrectInputsC` whose buffers have the
/// documented lengths; `sample` and `weight` must be writable and unaliased.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_correct_stokes_i(
    inputs: *const CorrectInputsC,
    sample: *mut f32,
    weight: *mut f32,
) -> i32 {
    std::panic::catch_unwind(|| {
        if inputs.is_null() {
            return 1;
        }
        // SAFETY: the caller guarantees the struct and its buffers.
        unsafe {
            let i = &*inputs;
            let Some(cells) = i.nrow.checked_mul(i.nchan) else {
                return 1;
            };
            let gains = i.ntime_bins * i.nfreq_bins * i.nant;
            let added = if i.added.is_null() {
                Some(&[][..])
            } else {
                slice(i.added, cells)
            };
            let (
                Some(data),
                Some(weights),
                Some(flags),
                Some(flag_row),
                Some(added),
                Some(antenna1),
                Some(antenna2),
                Some(time_bin),
                Some(freq_bin),
                Some(inverse),
                Some(valid),
                Some(sample),
                Some(weight),
            ) = (
                slice(i.data, 8 * cells),
                slice(i.weights, 4 * cells),
                slice(i.flags, 4 * cells),
                slice(i.flag_row, i.nrow),
                added,
                slice(i.antenna1, i.nrow),
                slice(i.antenna2, i.nrow),
                slice(i.time_bin, i.nrow),
                slice(i.freq_bin, i.nchan),
                slice(i.inverse, 8 * gains),
                slice(i.valid, gains),
                slice_mut(sample, 2 * cells),
                slice_mut(weight, cells),
            )
            else {
                return 1;
            };
            let inputs = CorrectInputs {
                nrow: i.nrow,
                nchan: i.nchan,
                ntime_bins: i.ntime_bins,
                nfreq_bins: i.nfreq_bins,
                nant: i.nant,
                data,
                weights,
                flags,
                flag_row,
                added,
                antenna1,
                antenna2,
                time_bin,
                freq_bin,
                inverse,
                valid,
            };
            match correct::correct_stokes_i(&inputs, sample, weight) {
                Ok(()) => 0,
                Err(_) => 1,
            }
        }
    })
    .unwrap_or(2)
}

/// Decode blocks `first..first + count` of a blosc chunk and copy the rows
/// `rows` (`nrows` ascending usize) into `out` with a destination stride of
/// `stride` bytes per row (`out_len` bytes writable). `head` (`head_len`
/// bytes) is the chunk's header and block-start table, `span` (`span_len`
/// bytes) the compressed bytes from block `first`'s offset.
///
/// # Safety
///
/// Every pointer must be valid for its stated length; `out` must not alias
/// the inputs.
#[allow(clippy::too_many_arguments)]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_blosc_decode_span_rows_strided(
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
    out_len: usize,
    stride: usize,
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
            match correct::decode_rows_strided(
                head, &h, first, count, span, span_start, row_bytes, rows, out, out_len, stride,
            ) {
                Ok(()) => 0,
                Err(_) => 1,
            }
        }
    })
    .unwrap_or(2)
}
