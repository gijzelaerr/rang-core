//! C ABI for `closure` (big plan task C1, `research/c1-closure-arm.md`),
//! loaded through ctypes by `python/rang/core_closure.py`. Same
//! conventions as `ffi.rs`: borrowed buffers described by explicit lengths,
//! 0 on success, 1 on invalid arguments (message from
//! `rang_core_closure_last_error`), 2 on a panic.

use crate::closure::{self, ClosureInputs, ClosureOutputs, Family};
use std::cell::RefCell;

thread_local! {
    static LAST_ERROR: RefCell<String> = const { RefCell::new(String::new()) };
}

fn set_error(message: &str) {
    LAST_ERROR.with(|e| *e.borrow_mut() = message.to_string());
}

/// Borrowed inputs for `rang_core_closure_scores`; see
/// `closure::ClosureInputs` for the layouts.
#[repr(C)]
pub struct ClosureInputsC {
    pub nrow: usize,
    pub nchan: usize,
    pub nant: usize,
    pub ntime: usize,
    pub nstation: usize,
    pub data: *const f32,
    pub model: *const f32,
    pub weights: *const f32,
    pub usable: *const u8,
    pub antenna1: *const u32,
    pub antenna2: *const u32,
    pub time_index: *const u32,
    pub stations: *const u32,
    /// `closure::FAMILY_TRACE`, `FAMILY_PHASE` or `FAMILY_LOGAMP`.
    pub family: u32,
    pub min_closures: u32,
    pub reroute: u32,
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

/// Per-sample closure scores of one family into `residual`, `tv` (f32) and
/// `count` (u16), each `nrow * nchan` long.
///
/// # Safety
///
/// `inputs` must point to a valid `ClosureInputsC` whose buffers have the
/// documented lengths; the outputs must be writable and unaliased.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_closure_scores(
    inputs: *const ClosureInputsC,
    residual: *mut f32,
    tv: *mut f32,
    count: *mut u16,
) -> i32 {
    std::panic::catch_unwind(|| {
        if inputs.is_null() {
            set_error("null inputs");
            return 1;
        }
        // SAFETY: the caller guarantees the struct and its buffers.
        unsafe {
            let i = &*inputs;
            let Some(cells) = i.nrow.checked_mul(i.nchan) else {
                set_error("size overflow");
                return 1;
            };
            let Some(family) = Family::from_code(i.family) else {
                set_error("unknown closure family");
                return 1;
            };
            let (
                Some(data),
                Some(model),
                Some(weights),
                Some(usable),
                Some(antenna1),
                Some(antenna2),
                Some(time_index),
                Some(stations),
                Some(residual),
                Some(tv),
                Some(count),
            ) = (
                slice(i.data, 8 * cells),
                slice(i.model, 8 * cells),
                slice(i.weights, 4 * cells),
                slice(i.usable, cells),
                slice(i.antenna1, i.nrow),
                slice(i.antenna2, i.nrow),
                slice(i.time_index, i.nrow),
                slice(i.stations, i.nstation),
                slice_mut(residual, cells),
                slice_mut(tv, cells),
                slice_mut(count, cells),
            )
            else {
                set_error("null buffer");
                return 1;
            };
            let inputs = ClosureInputs {
                nrow: i.nrow,
                nchan: i.nchan,
                nant: i.nant,
                ntime: i.ntime,
                data,
                model,
                weights,
                usable,
                antenna1,
                antenna2,
                time_index,
                stations,
                family,
                min_closures: i.min_closures as usize,
                reroute: i.reroute as usize,
            };
            let mut outputs = ClosureOutputs {
                residual,
                tv,
                count,
            };
            match closure::closure_scores(&inputs, &mut outputs) {
                Ok(()) => 0,
                Err(e) => {
                    set_error(&e.to_string());
                    1
                }
            }
        }
    })
    .unwrap_or(2)
}

/// Copy the last error message of this thread into `buf` (at most `len`
/// bytes); returns its full length.
///
/// # Safety
///
/// `buf` must be null or hold `len` writable bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_closure_last_error(buf: *mut u8, len: usize) -> usize {
    LAST_ERROR.with(|e| {
        let e = e.borrow();
        if !buf.is_null() {
            let n = e.len().min(len);
            // SAFETY: `buf` holds `len` bytes.
            unsafe { std::ptr::copy_nonoverlapping(e.as_ptr(), buf, n) };
        }
        e.len()
    })
}
