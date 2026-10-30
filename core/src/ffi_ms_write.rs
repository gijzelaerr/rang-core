//! C ABI of the casacore table writer (research/e3-table-writer.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Additive to `ffi_ms.rs`: a writable table is an opaque handle holding
//! casacore's write lock until `rang_core_ms_write_close`. Every function
//! returns 0 on success, 1 on an error (message through
//! `rang_core_ms_write_last_error`) and 2 on a panic.

use std::cell::RefCell;
use std::ffi::{CStr, c_char};
use std::time::Duration;

use crate::aipsio::KeywordValue;
use crate::ms_write::{NewColumn, NewManager, TableWriter};

thread_local! {
    static LAST_ERROR: RefCell<String> = const { RefCell::new(String::new()) };
}

fn set_error(message: impl Into<String>) -> i32 {
    LAST_ERROR.with(|e| *e.borrow_mut() = message.into());
    1
}

fn status(result: crate::ms::Result<()>) -> i32 {
    match result {
        Ok(()) => 0,
        Err(e) => set_error(e.0),
    }
}

/// # Safety
/// `s` is null or a NUL-terminated string.
unsafe fn text(s: *const c_char) -> Option<String> {
    // SAFETY: the caller passes a NUL-terminated string or null.
    (!s.is_null()).then(|| unsafe { CStr::from_ptr(s) }.to_string_lossy().into_owned())
}

/// # Safety
/// `p` points to `n` values or `n` is 0.
unsafe fn slice<'a, T>(p: *const T, n: usize) -> &'a [T] {
    if n == 0 || p.is_null() {
        &[]
    } else {
        // SAFETY: guaranteed by the caller.
        unsafe { std::slice::from_raw_parts(p, n) }
    }
}

/// Strings packed as a little-endian `u32` byte count before each one's
/// UTF-8 bytes (the reader's packing).
fn unpack_strings(bytes: &[u8], n: usize) -> Result<Vec<String>, String> {
    let mut out = Vec::with_capacity(n);
    let mut at = 0;
    for _ in 0..n {
        let len = bytes
            .get(at..at + 4)
            .map(|b| u32::from_le_bytes(b.try_into().unwrap()) as usize)
            .ok_or("truncated string list")?;
        let s = bytes
            .get(at + 4..at + 4 + len)
            .ok_or("truncated string list")?;
        out.push(String::from_utf8(s.to_vec()).map_err(|_| "string is not UTF-8")?);
        at += 4 + len;
    }
    Ok(out)
}

/// Copy the last error message into `buf`; returns its full length.
///
/// # Safety
/// `buf` must point to `len` writable bytes or be null.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_last_error(buf: *mut u8, len: usize) -> usize {
    std::panic::catch_unwind(|| {
        LAST_ERROR.with(|e| {
            let message = e.borrow();
            if !buf.is_null() && len > 0 {
                let n = message.len().min(len);
                // SAFETY: the caller guarantees `len` writable bytes.
                unsafe { std::ptr::copy_nonoverlapping(message.as_ptr(), buf, n) };
            }
            message.len()
        })
    })
    .unwrap_or(0)
}

/// Open a table for writing, trying the write lock `attempts` times
/// `wait_ms` apart.
///
/// # Safety
/// `path` is a NUL-terminated string; `out` receives the handle.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_open(
    path: *const c_char,
    attempts: u32,
    wait_ms: u64,
    out: *mut *mut TableWriter,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: as documented.
        let Some(path) = (unsafe { text(path) }) else {
            return set_error("null argument");
        };
        if out.is_null() {
            return set_error("null argument");
        }
        match TableWriter::open(&path, attempts, Duration::from_millis(wait_ms)) {
            Ok(w) => {
                // SAFETY: `out` is a valid pointer.
                unsafe { *out = Box::into_raw(Box::new(w)) };
                0
            }
            Err(e) => set_error(format!("{path}: {e}")),
        }
    })
    .unwrap_or(2)
}

/// Flush, release the lock and free the handle (gone even on an error).
///
/// # Safety
/// `writer` came from `rang_core_ms_write_open` and is not used afterwards.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_close(writer: *mut TableWriter) -> i32 {
    if writer.is_null() {
        return 0;
    }
    let writer = std::panic::AssertUnwindSafe(writer);
    std::panic::catch_unwind(move || {
        // SAFETY: the handle was created by Box::into_raw.
        let w = unsafe { Box::from_raw(*writer) };
        status(w.close())
    })
    .unwrap_or(2)
}

/// Flush without closing.
///
/// # Safety
/// `writer` is an open handle.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_flush(writer: *mut TableWriter) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: an open handle.
        let Some(w) = (unsafe { writer.as_mut() }) else {
            return set_error("null argument");
        };
        status(w.flush())
    })
    .unwrap_or(2)
}

/// The row count of the table.
///
/// # Safety
/// `writer` is an open handle.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_nrows(writer: *const TableWriter) -> u64 {
    std::panic::catch_unwind(|| {
        // SAFETY: an open handle.
        unsafe { writer.as_ref() }.map_or(0, |w| w.nrows)
    })
    .unwrap_or(0)
}

/// Write `count` rows (0: to the end) from `start` of a numeric or Bool
/// column: `nbytes` native bytes, cells of `shape` (`ndim` values, casacore
/// order; 0 for scalars) in Fortran order, booleans one byte each.
///
/// # Safety
/// `writer` is an open handle, `name` NUL-terminated, `shape` and `data`
/// point to `ndim` and `nbytes` values.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_core_ms_write_put(
    writer: *mut TableWriter,
    name: *const c_char,
    start: u64,
    count: u64,
    ndim: usize,
    shape: *const i64,
    data: *const u8,
    nbytes: usize,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: as documented.
        let (Some(w), Some(name)) = (unsafe { writer.as_mut() }, unsafe { text(name) }) else {
            return set_error("null argument");
        };
        // SAFETY: as documented.
        let (shape, data) = unsafe { (slice(shape, ndim), slice(data, nbytes)) };
        status(w.put_column(&name, start, count, shape, data))
    })
    .unwrap_or(2)
}

/// Write `n` strings from row `start` of a scalar string column, packed as
/// the reader packs them (`u32` length, UTF-8 bytes).
///
/// # Safety
/// `writer` is an open handle, `name` NUL-terminated, `packed` points to
/// `nbytes` bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_put_strings(
    writer: *mut TableWriter,
    name: *const c_char,
    start: u64,
    n: usize,
    packed: *const u8,
    nbytes: usize,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: as documented.
        let (Some(w), Some(name)) = (unsafe { writer.as_mut() }, unsafe { text(name) }) else {
            return set_error("null argument");
        };
        // SAFETY: as documented.
        match unpack_strings(unsafe { slice(packed, nbytes) }, n) {
            Ok(values) => status(w.put_strings(&name, start, &values)),
            Err(e) => set_error(e),
        }
    })
    .unwrap_or(2)
}

/// Keyword value kinds of `rang_core_ms_write_put_keyword`.
pub const KEYWORD_SCALAR: i32 = 0;
pub const KEYWORD_STRING: i32 = 1;
pub const KEYWORD_ARRAY: i32 = 2;
pub const KEYWORD_STRING_ARRAY: i32 = 3;
pub const KEYWORD_RECORD: i32 = 4;
/// A table keyword: `data` the stored name (`././NAME` or absolute; E4).
pub const KEYWORD_TABLE: i32 = 5;

/// Build a keyword value from the C arguments.
pub fn keyword_value(
    kind: i32,
    code: i32,
    shape: &[i64],
    data: &[u8],
    nstrings: usize,
) -> Result<KeywordValue, String> {
    Ok(match kind {
        KEYWORD_SCALAR => KeywordValue::Scalar(code, data.to_vec()),
        KEYWORD_STRING => KeywordValue::String(
            String::from_utf8(data.to_vec()).map_err(|_| "keyword string is not UTF-8")?,
        ),
        KEYWORD_ARRAY => KeywordValue::Array(code, shape.to_vec(), data.to_vec()),
        KEYWORD_STRING_ARRAY => {
            KeywordValue::StringArray(shape.to_vec(), unpack_strings(data, nstrings)?)
        }
        KEYWORD_RECORD => KeywordValue::Record,
        KEYWORD_TABLE => KeywordValue::Table(
            String::from_utf8(data.to_vec()).map_err(|_| "table name is not UTF-8")?,
        ),
        other => return Err(format!("unknown keyword kind {other}")),
    })
}

/// Define a keyword of the table (`column` null) or a column. `path` is the
/// keyword name, nested sub-record names separated by `.`. `kind` is one of
/// the `KEYWORD_*` values; `code` the casacore type code of a scalar or of
/// an array's elements; `data` native bytes (a string's UTF-8 bytes; packed
/// strings for a string array).
///
/// # Safety
/// `writer` is an open handle, strings NUL-terminated (`column` may be
/// null), `shape` and `data` point to `ndim` and `nbytes` values.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_core_ms_write_put_keyword(
    writer: *mut TableWriter,
    column: *const c_char,
    path: *const c_char,
    kind: i32,
    code: i32,
    ndim: usize,
    shape: *const i64,
    data: *const u8,
    nbytes: usize,
    nstrings: usize,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: as documented.
        let (Some(w), Some(path)) = (unsafe { writer.as_mut() }, unsafe { text(path) }) else {
            return set_error("null argument");
        };
        // SAFETY: as documented.
        let (column, shape, data) =
            unsafe { (text(column), slice(shape, ndim), slice(data, nbytes)) };
        let value = match keyword_value(kind, code, shape, data, nstrings) {
            Ok(v) => v,
            Err(e) => return set_error(e),
        };
        let parts: Vec<&str> = path.split('.').collect();
        status(w.put_keyword(column.as_deref(), &parts, value))
    })
    .unwrap_or(2)
}

/// Remove a keyword (path as in `rang_core_ms_write_put_keyword`).
///
/// # Safety
/// As `rang_core_ms_write_put_keyword`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_remove_keyword(
    writer: *mut TableWriter,
    column: *const c_char,
    path: *const c_char,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: as documented.
        let (Some(w), Some(path)) = (unsafe { writer.as_mut() }, unsafe { text(path) }) else {
            return set_error("null argument");
        };
        // SAFETY: as documented.
        let column = unsafe { text(column) };
        let parts: Vec<&str> = path.split('.').collect();
        status(w.remove_keyword(column.as_deref(), &parts))
    })
    .unwrap_or(2)
}

/// A column to add; strings NUL-terminated (null: empty).
#[repr(C)]
pub struct NewColumnC {
    pub name: *const c_char,
    pub dtype: i32,
    pub array: i32,
    pub ndim: i32,
    pub nshape: usize,
    pub shape: *const i64,
    pub option: i32,
    pub max_length: u32,
    pub comment: *const c_char,
    pub dm_type: *const c_char,
    pub dm_group: *const c_char,
    /// Canonical (big-endian) default value of a scalar column.
    pub default_value: *const u8,
    pub ndefault: usize,
    /// 0: the default binding; a new data manager named `manager_name`: 1
    /// TiledColumnStMan, 2 TiledShapeStMan (`tile`: the tile shape in
    /// casacore order, rows last), 3 StandardStMan (`tile`: BUCKETROWS,
    /// BUCKETSIZE, PERSCACHESIZE, 0 when not given).
    pub manager: i32,
    pub manager_name: *const c_char,
    pub ntile: usize,
    pub tile: *const i64,
}

/// Build the Rust spec of a new column.
#[allow(clippy::too_many_arguments)]
pub fn new_column(
    name: String,
    dtype: i32,
    array: bool,
    ndim: i32,
    shape: Vec<i64>,
    option: i32,
    max_length: u32,
    texts: [String; 3],
    default: Vec<u8>,
    manager: i32,
    manager_name: String,
    tile: Vec<i64>,
) -> Result<NewColumn, String> {
    let [comment, dm_type, dm_group] = texts;
    let manager = match manager {
        0 => NewManager::Default,
        1 => NewManager::TiledColumn {
            name: manager_name,
            tile,
        },
        2 => NewManager::TiledShape {
            name: manager_name,
            tile,
        },
        3 => {
            let spec = |i: usize| tile.get(i).map_or(0, |&v| v.max(0) as u32);
            NewManager::Standard {
                name: manager_name,
                bucket_rows: spec(0),
                bucket_size: spec(1),
                cache: spec(2),
            }
        }
        other => return Err(format!("unknown data manager choice {other}")),
    };
    Ok(NewColumn {
        name,
        dtype,
        array,
        ndim,
        shape,
        option,
        max_length,
        comment,
        dm_type,
        dm_group,
        default,
        manager,
    })
}

/// `addcols` of one column.
///
/// # Safety
/// `writer` is an open handle and `spec` a valid struct whose pointers
/// follow its counts.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_add_column(
    writer: *mut TableWriter,
    spec: *const NewColumnC,
) -> i32 {
    std::panic::catch_unwind(|| {
        // SAFETY: as documented.
        let (Some(w), Some(s)) = (unsafe { writer.as_mut() }, unsafe { spec.as_ref() }) else {
            return set_error("null argument");
        };
        // SAFETY: as documented.
        let (Some(name), comment, dm_type, dm_group, manager_name) = (unsafe {
            (
                text(s.name),
                text(s.comment).unwrap_or_default(),
                text(s.dm_type).unwrap_or_default(),
                text(s.dm_group).unwrap_or_default(),
                text(s.manager_name).unwrap_or_default(),
            )
        }) else {
            return set_error("null column name");
        };
        // SAFETY: as documented.
        let (shape, default, tile) = unsafe {
            (
                slice(s.shape, s.nshape).to_vec(),
                slice(s.default_value, s.ndefault).to_vec(),
                slice(s.tile, s.ntile).to_vec(),
            )
        };
        match new_column(
            name,
            s.dtype,
            s.array != 0,
            s.ndim,
            shape,
            s.option,
            s.max_length,
            [comment, dm_type, dm_group],
            default,
            s.manager,
            manager_name,
            tile,
        ) {
            Ok(spec) => status(w.add_column(&spec)),
            Err(e) => set_error(e),
        }
    })
    .unwrap_or(2)
}

// ---------------------------------------------------------------------------
// E4: new tables, rows and table info (research/e4-table-create.md). The
// creation calls are made through the extension (`core/py/src/lib.rs`)
// with the argument tuples below; the row and info calls are also C ABI.

/// A column across the binding: name, type code, array, ndim, shape
/// (casacore order), option, maximum string length, comment, data-manager
/// type and group.
pub type ColumnArgs = (
    String,
    i32,
    bool,
    i32,
    Vec<i64>,
    i32,
    u32,
    String,
    String,
    String,
);

/// A data manager across the binding: type, name, columns, BUCKETSIZE,
/// BUCKETROWS, PERSCACHESIZE, DEFAULTTILESHAPE (casacore order).
pub type ManagerArgs = (String, String, Vec<String>, u32, u32, u32, Vec<i64>);

/// Column descriptions from the binding's tuples.
pub fn column_descs(columns: Vec<ColumnArgs>) -> Result<Vec<crate::ms_desc::ColDesc>, String> {
    columns
        .into_iter()
        .map(
            |(name, dtype, array, ndim, shape, option, max_length, comment, dm_type, dm_group)| {
                crate::ms_create::new_coldesc(&crate::ms_create::NewColumn {
                    name,
                    dtype,
                    array,
                    ndim,
                    shape,
                    option,
                    max_length,
                    comment,
                    dm_type,
                    dm_group,
                    keywords: crate::aipsio::Record::default(),
                })
                .map_err(|e| e.0)
            },
        )
        .collect()
}

/// Data-manager specs from the binding's tuples.
pub fn manager_specs(managers: Vec<ManagerArgs>) -> Vec<crate::ms_create::ManagerSpec> {
    managers
        .into_iter()
        .map(
            |(kind, name, columns, bucket_size, bucket_rows, cache, tile)| {
                crate::ms_create::ManagerSpec {
                    kind,
                    name,
                    columns,
                    bucket_size,
                    bucket_rows,
                    cache,
                    tile,
                    ism_computed: false,
                }
            },
        )
        .collect()
}

/// Add `n` rows.
///
/// # Safety
/// `writer` is an open handle.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_add_rows(writer: *mut TableWriter, n: u64) -> i32 {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        // SAFETY: the caller passes an open handle.
        match unsafe { writer.as_mut() } {
            Some(w) => status(w.add_rows(n)),
            None => set_error("null table handle"),
        }
    }))
    .unwrap_or(2)
}

/// Remove `n` rows given in `rows` (any order).
///
/// # Safety
/// `writer` is an open handle and `rows` points to `n` values.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_remove_rows(
    writer: *mut TableWriter,
    rows: *const u64,
    n: usize,
) -> i32 {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        // SAFETY: guaranteed by the caller.
        let rows = unsafe { slice(rows, n) };
        // SAFETY: the caller passes an open handle.
        match unsafe { writer.as_mut() } {
            Some(w) => status(w.remove_rows(rows)),
            None => set_error("null table handle"),
        }
    }))
    .unwrap_or(2)
}

/// Set `table.info` (type, subtype, readme).
///
/// # Safety
/// `writer` is an open handle; strings are NUL-terminated or null.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_ms_write_put_info(
    writer: *mut TableWriter,
    kind: *const c_char,
    sub_kind: *const c_char,
    readme: *const c_char,
) -> i32 {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        // SAFETY: NUL-terminated or null strings.
        let (k, s, r) = unsafe { (text(kind), text(sub_kind), text(readme)) };
        // SAFETY: the caller passes an open handle.
        match unsafe { writer.as_mut() } {
            Some(w) => status(w.put_info(
                &k.unwrap_or_default(),
                &s.unwrap_or_default(),
                &r.unwrap_or_default(),
            )),
            None => set_error("null table handle"),
        }
    }))
    .unwrap_or(2)
}
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strings_unpack_and_errors_are_reported() {
        let mut packed = Vec::new();
        for s in ["a", "bcd"] {
            packed.extend((s.len() as u32).to_le_bytes());
            packed.extend(s.as_bytes());
        }
        assert_eq!(unpack_strings(&packed, 2).unwrap(), vec!["a", "bcd"]);
        assert!(unpack_strings(&packed, 3).is_err());
        let mut out = std::ptr::null_mut();
        let path = c"/nonexistent/table";
        // SAFETY: valid arguments.
        let code = unsafe { rang_core_ms_write_open(path.as_ptr(), 1, 0, &mut out) };
        assert_eq!(code, 1);
        let mut buf = [0u8; 256];
        // SAFETY: a writable buffer.
        let n = unsafe { rang_core_ms_write_last_error(buf.as_mut_ptr(), buf.len()) };
        assert!(
            n > 0
                && std::str::from_utf8(&buf[..n.min(256)])
                    .unwrap()
                    .contains("table.lock")
        );
        assert!(keyword_value(9, 0, &[], &[], 0).is_err());
        assert!(matches!(
            keyword_value(KEYWORD_STRING, 0, &[], b"Jy", 0).unwrap(),
            KeywordValue::String(s) if s == "Jy"
        ));
    }
}
