//! C ABI of the Measurement Set reader for the Python layer (ctypes).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! A table is an opaque handle; a column read returns a buffer the core
//! allocates and the caller frees with `rang_core_ms_free`. Every function
//! returns 0 on success, 1 on an error (message through
//! `rang_core_ms_last_error`) and 2 on a panic.

use std::cell::RefCell;
use std::ffi::{CStr, c_char};

use crate::ms::{DataType, Table};

thread_local! {
    static LAST_ERROR: RefCell<String> = const { RefCell::new(String::new()) };
}

fn set_error(message: impl Into<String>) -> i32 {
    LAST_ERROR.with(|e| *e.borrow_mut() = message.into());
    1
}

/// A column read. `data` holds `nbytes` bytes: for numeric and boolean
/// columns `nrows` cells of `shape` (Fortran order, booleans one byte each);
/// for string columns `nstrings` strings, each a little-endian `u32` byte
/// count followed by UTF-8 bytes.
#[repr(C)]
pub struct MsColumn {
    pub data: *mut u8,
    pub nbytes: usize,
    pub nrows: u64,
    pub ndim: usize,
    pub shape: [i64; 8],
    pub dtype: i32,
    pub nstrings: usize,
}

/// Copy the last error message into `buf`; returns its full length.
///
/// # Safety
/// `buf` must point to `len` writable bytes or be null.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_last_error(buf: *mut u8, len: usize) -> usize {
    LAST_ERROR.with(|e| {
        let message = e.borrow();
        if !buf.is_null() && len > 0 {
            let n = message.len().min(len);
            // SAFETY: the caller guarantees `len` writable bytes.
            unsafe { std::ptr::copy_nonoverlapping(message.as_ptr(), buf, n) };
        }
        message.len()
    })
}

/// Open a table directory read-only.
///
/// # Safety
/// `path` is a NUL-terminated string; `out` receives the handle.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_open(path: *const c_char, out: *mut *mut Table) -> i32 {
    std::panic::catch_unwind(|| {
        if path.is_null() || out.is_null() {
            return set_error("null argument");
        }
        // SAFETY: the caller passes a NUL-terminated string.
        let path = unsafe { CStr::from_ptr(path) }
            .to_string_lossy()
            .into_owned();
        match Table::open(&path) {
            Ok(table) => {
                // SAFETY: `out` is a valid pointer.
                unsafe { *out = Box::into_raw(Box::new(table)) };
                0
            }
            Err(e) => set_error(format!("{path}: {e}")),
        }
    })
    .unwrap_or(2)
}

/// Close a table opened with `rang_core_ms_open`.
///
/// # Safety
/// `table` came from `rang_core_ms_open` and is not used afterwards.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_close(table: *mut Table) {
    if !table.is_null() {
        // SAFETY: the handle was created by Box::into_raw.
        drop(unsafe { Box::from_raw(table) });
    }
}

/// Write the JSON description of the table into `buf`; returns the length
/// needed (the description is complete only if it fits).
///
/// # Safety
/// `table` is an open handle; `buf` points to `len` writable bytes or is null.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_describe(
    table: *const Table,
    buf: *mut u8,
    len: usize,
) -> usize {
    std::panic::catch_unwind(|| {
        // SAFETY: the caller passes an open handle.
        let Some(table) = (unsafe { table.as_ref() }) else {
            return 0;
        };
        let json = table.describe_json();
        if !buf.is_null() && len > 0 {
            let n = json.len().min(len);
            // SAFETY: the caller guarantees `len` writable bytes.
            unsafe { std::ptr::copy_nonoverlapping(json.as_ptr(), buf, n) };
        }
        json.len()
    })
    .unwrap_or(0)
}

/// Read `count` rows (0: to the end) of a column from `start` into `out`.
///
/// # Safety
/// `table` is an open handle, `name` a NUL-terminated string and `out` a
/// valid struct pointer; free the result with `rang_core_ms_free`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_read(
    table: *const Table,
    name: *const c_char,
    start: u64,
    count: u64,
    out: *mut MsColumn,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: the caller passes an open handle and valid pointers.
        let (Some(table), Some(out), false) = (
            unsafe { table.as_ref() },
            unsafe { out.as_mut() },
            name.is_null(),
        ) else {
            return set_error("null argument");
        };
        // SAFETY: the caller passes a NUL-terminated string.
        let name = unsafe { CStr::from_ptr(name) }
            .to_string_lossy()
            .into_owned();
        let data = match table.read_column(&name, start, count) {
            Ok(data) => data,
            Err(e) => return set_error(e.0),
        };
        if data.shape.len() > 8 {
            return set_error("more than 8 cell axes");
        }
        let dtype = data.dtype.unwrap_or(DataType::Str);
        let mut bytes = data.bytes;
        let nstrings = data.strings.len();
        if dtype == DataType::Str {
            bytes = Vec::with_capacity(data.strings.iter().map(|s| 4 + s.len()).sum());
            for s in &data.strings {
                bytes.extend((s.len() as u32).to_le_bytes());
                bytes.extend_from_slice(s.as_bytes());
            }
        }
        let mut shape = [0i64; 8];
        shape[..data.shape.len()].copy_from_slice(&data.shape);
        let mut bytes = bytes.into_boxed_slice();
        *out = MsColumn {
            data: bytes.as_mut_ptr(),
            nbytes: bytes.len(),
            nrows: data.nrows,
            ndim: data.shape.len(),
            shape,
            dtype: dtype.code(),
            nstrings,
        };
        std::mem::forget(bytes);
        0
    })
    .unwrap_or(2)
}

/// Free the buffer of a column read.
///
/// # Safety
/// `out` was filled by a successful `rang_core_ms_read` and is not reused.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_free(out: *mut MsColumn) {
    // SAFETY: the caller passes the struct a read filled.
    if let Some(column) = unsafe { out.as_mut() } {
        if !column.data.is_null() {
            // SAFETY: the buffer was leaked from a boxed slice of this length
            // (possibly empty, whose pointer is still valid to reconstruct).
            drop(unsafe {
                Box::from_raw(std::ptr::slice_from_raw_parts_mut(
                    column.data,
                    column.nbytes,
                ))
            });
        }
        column.data = std::ptr::null_mut();
        column.nbytes = 0;
    }
}
