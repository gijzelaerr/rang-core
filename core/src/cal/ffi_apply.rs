// SPDX-License-Identifier: GPL-3.0-or-later
//! C ABI for the apply kernel (`cal/apply.rs`, task C4a). Same conventions
//! as `ffi_closure.rs`: borrowed buffers with explicit lengths, 0 on
//! success, 1 on invalid arguments (message from
//! `rang_core_cal_apply_last_error`), 2 on a panic.
//!
//! The terms are packed: per term `t < nterm` its kind, interpolation codes,
//! `npar` and K pivot; its slots are `slot_offset[t]..slot_offset[t + 1]` of
//! `slot_time`, its per-antenna offsets (relative to its first slot) are
//! `slot_start[t * (nant + 1)..(t + 1) * (nant + 1)]`, its parameters
//! `param_offset[t]..` of `params` (floats), its flags `flag_offset[t]..`
//! of `flags` and its solution frequencies `freq_offset[t]..` of
//! `sol_freq`.

use super::apply::{self, Chunk, Direction, Interp, Kind, Term};
use std::cell::RefCell;

thread_local! {
    static LAST_ERROR: RefCell<String> = const { RefCell::new(String::new()) };
}

fn set_error(message: &str) {
    LAST_ERROR.with(|e| *e.borrow_mut() = message.to_string());
}

/// The chunk: `data` interleaved complex64 and `flags` `(nrow, nchan, 4)`,
/// `time`, `antenna1`, `antenna2` `(nrow,)`, `freq` `(nband,)`: the
/// window's frequencies, of which the data hold channels `first_chan..
/// first_chan + nchan` (`nband` = `nchan`, `first_chan` 0 for every channel).
#[repr(C)]
pub struct ApplyChunkC {
    pub nrow: usize,
    pub nchan: usize,
    pub nant: usize,
    pub data: *const f32,
    pub flags: *const u8,
    pub time: *const f64,
    pub antenna1: *const u32,
    pub antenna2: *const u32,
    pub freq: *const f64,
    pub nband: usize,
    pub first_chan: usize,
}

/// The packed terms (see the module documentation).
#[repr(C)]
pub struct ApplyTermsC {
    pub nterm: usize,
    pub kind: *const u32,
    pub time_interp: *const u32,
    pub freq_interp: *const u32,
    pub npar: *const u32,
    pub k_ref_freq: *const f64,
    pub slot_start: *const u64,
    pub slot_offset: *const u64,
    pub slot_time: *const f64,
    pub param_offset: *const u64,
    pub params: *const f32,
    pub flag_offset: *const u64,
    pub flags: *const u8,
    pub freq_offset: *const u64,
    pub sol_freq: *const f64,
}

/// A slice from a pointer that may be null when `len` is 0.
///
/// # Safety
/// A non-null `p` must point to `len` values.
unsafe fn slice<'a, T>(p: *const T, len: usize, name: &str) -> Result<&'a [T], String> {
    if len == 0 {
        return Ok(&[]);
    }
    if p.is_null() {
        return Err(format!("{name} is null"));
    }
    // SAFETY: the caller guarantees `len` values at `p`.
    Ok(unsafe { std::slice::from_raw_parts(p, len) })
}

fn offsets(o: &[u64], name: &str) -> Result<Vec<usize>, String> {
    let o: Vec<usize> = o.iter().map(|&x| x as usize).collect();
    if o.first() != Some(&0) || o.windows(2).any(|w| w[1] < w[0]) {
        return Err(format!("{name} must start at 0 and not decrease"));
    }
    Ok(o)
}

/// # Safety
/// As `rang_core_cal_apply`.
unsafe fn run(
    chunk: &ApplyChunkC,
    terms: &ApplyTermsC,
    direction: u32,
    threads: usize,
    out_data: *mut f32,
    out_flags: *mut u8,
) -> Result<(), String> {
    let cells = chunk
        .nrow
        .checked_mul(chunk.nchan)
        .ok_or("cell count overflows")?;
    let direction = match direction {
        0 => Direction::Correct,
        1 => Direction::Corrupt,
        _ => return Err("direction must be 0 (correct) or 1 (corrupt)".into()),
    };
    let nt = terms.nterm;
    // SAFETY (this block): the caller guarantees the documented lengths.
    let (c, packed) = unsafe {
        let c = Chunk {
            nrow: chunk.nrow,
            nchan: chunk.nchan,
            nant: chunk.nant,
            data: slice(chunk.data, 8 * cells, "data")?,
            flags: slice(chunk.flags, 4 * cells, "flags")?,
            time: slice(chunk.time, chunk.nrow, "time")?,
            antenna1: slice(chunk.antenna1, chunk.nrow, "antenna1")?,
            antenna2: slice(chunk.antenna2, chunk.nrow, "antenna2")?,
            freq: slice(chunk.freq, chunk.nband, "freq")?,
            first_chan: chunk.first_chan,
        };
        let kind = slice(terms.kind, nt, "kind")?;
        let ti = slice(terms.time_interp, nt, "time_interp")?;
        let fi = slice(terms.freq_interp, nt, "freq_interp")?;
        let npar = slice(terms.npar, nt, "npar")?;
        let kref = slice(terms.k_ref_freq, nt, "k_ref_freq")?;
        let starts = slice(terms.slot_start, nt * (chunk.nant + 1), "slot_start")?;
        let so = offsets(
            slice(terms.slot_offset, nt + 1, "slot_offset")?,
            "slot_offset",
        )?;
        let po = offsets(
            slice(terms.param_offset, nt + 1, "param_offset")?,
            "param_offset",
        )?;
        let fo = offsets(
            slice(terms.flag_offset, nt + 1, "flag_offset")?,
            "flag_offset",
        )?;
        let qo = offsets(
            slice(terms.freq_offset, nt + 1, "freq_offset")?,
            "freq_offset",
        )?;
        let times = slice(terms.slot_time, so[nt], "slot_time")?;
        let params = slice(terms.params, po[nt], "params")?;
        let flags = slice(terms.flags, fo[nt], "flags")?;
        let sol_freq = slice(terms.sol_freq, qo[nt], "sol_freq")?;
        (
            c,
            (
                kind, ti, fi, npar, kref, starts, so, po, fo, qo, times, params, flags, sol_freq,
            ),
        )
    };
    let (kind, ti, fi, npar, kref, starts, so, po, fo, qo, times, params, flags, sol_freq) = packed;
    let slot_starts: Vec<Vec<usize>> = (0..nt)
        .map(|t| {
            starts[t * (chunk.nant + 1)..(t + 1) * (chunk.nant + 1)]
                .iter()
                .map(|&x| x as usize)
                .collect()
        })
        .collect();
    let mut list = Vec::with_capacity(nt);
    for t in 0..nt {
        list.push(Term {
            kind: Kind::from_code(kind[t]).ok_or(format!("term {t}: unknown kind {}", kind[t]))?,
            time_interp: Interp::from_code(ti[t])
                .ok_or(format!("term {t}: unknown time interpolation {}", ti[t]))?,
            freq_interp: Interp::from_code(fi[t]).ok_or(format!(
                "term {t}: unknown frequency interpolation {}",
                fi[t]
            ))?,
            slot_start: &slot_starts[t],
            slot_time: &times[so[t]..so[t + 1]],
            nchan_sol: qo[t + 1] - qo[t],
            npar: npar[t] as usize,
            params: &params[po[t]..po[t + 1]],
            flags: &flags[fo[t]..fo[t + 1]],
            sol_freq: &sol_freq[qo[t]..qo[t + 1]],
            k_ref_freq: kref[t],
        });
    }
    if cells > 0 && (out_data.is_null() || out_flags.is_null()) {
        return Err("outputs are null".into());
    }
    // SAFETY: the caller guarantees the output lengths and no aliasing.
    let (od, of) = unsafe {
        if cells == 0 {
            (&mut [][..], &mut [][..])
        } else {
            (
                std::slice::from_raw_parts_mut(out_data, 8 * cells),
                std::slice::from_raw_parts_mut(out_flags, 4 * cells),
            )
        }
    };
    apply::apply(&c, &list, direction, threads, od, of)
}

/// Correct (`direction` 0) or corrupt (1) the chunk by the terms into
/// `out_data` (`8 nrow nchan` floats) and `out_flags` (`4 nrow nchan`).
/// `threads` 0 uses the global rayon pool.
///
/// # Safety
/// Every pointer must hold the lengths the structs document, and the
/// outputs must not alias the inputs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_cal_apply(
    chunk: *const ApplyChunkC,
    terms: *const ApplyTermsC,
    direction: u32,
    threads: usize,
    out_data: *mut f32,
    out_flags: *mut u8,
) -> i32 {
    if chunk.is_null() || terms.is_null() {
        set_error("chunk or terms is null");
        return 1;
    }
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        // SAFETY: forwarded from the caller.
        match unsafe { run(&*chunk, &*terms, direction, threads, out_data, out_flags) } {
            Ok(()) => 0,
            Err(message) => {
                set_error(&message);
                1
            }
        }
    }))
    .unwrap_or(2)
}

/// Copy the last error message of this thread into `buf` (at most `len`
/// bytes); returns its full length.
///
/// # Safety
/// `buf` must be null or hold `len` writable bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_cal_apply_last_error(buf: *mut u8, len: usize) -> usize {
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
