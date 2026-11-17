// SPDX-License-Identifier: MIT
//! Allocation accounting of the `gemclean` binary: the bytes its allocator
//! ([`crate::gemclean::host::HugePageAlloc`]) holds, the largest amount per
//! phase of a run, and the sizes of the main buffers, for the memory report
//! (`-memory-report`, and `memory` in `-report.json`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.
//!
//! The counters are two relaxed atomics touched once per allocation. The
//! binary counts on every platform (Linux through `HugePageAlloc`, elsewhere
//! through [`crate::gemclean::host::CountingAlloc`]); under any other
//! allocator (the Python extension) nothing counts and [`mark`] and [`note`]
//! do nothing. Heap bytes are what was asked for, not
//! resident pages: huge-page rounding, untouched pages and the program's own
//! text are not in them, so the process's peak RSS is reported beside them.

use std::sync::Mutex;
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

static LIVE: AtomicUsize = AtomicUsize::new(0);
/// The largest `LIVE` since the last [`mark`].
static PEAK: AtomicUsize = AtomicUsize::new(0);

/// One phase of a run: its label, the heap held at its end and the most held
/// during it, and the process's resident set (now and peak) and swapped-out
/// bytes at its end. A peak RSS means little if part of the process was in swap.
#[derive(Clone, Debug)]
pub struct Phase {
    pub label: String,
    pub live: usize,
    pub peak: usize,
    pub rss: Option<u64>,
    pub hwm: Option<u64>,
    pub swap: Option<u64>,
}

static PHASES: Mutex<Vec<Phase>> = Mutex::new(Vec::new());
static BUFFERS: Mutex<Vec<(String, usize)>> = Mutex::new(Vec::new());

#[inline(always)]
pub(crate) fn grow(bytes: usize) {
    let live = LIVE.fetch_add(bytes, Relaxed) + bytes;
    PEAK.fetch_max(live, Relaxed);
}

#[inline(always)]
pub(crate) fn shrink(bytes: usize) {
    LIVE.fetch_sub(bytes, Relaxed);
}

#[inline(always)]
pub(crate) fn resize(old: usize, new: usize) {
    if new >= old {
        grow(new - old);
    } else {
        shrink(old - new);
    }
}

/// Whether the counting allocator is in use.
pub fn counting() -> bool {
    PEAK.load(Relaxed) > 0
}

/// Heap bytes held now.
pub fn live() -> usize {
    LIVE.load(Relaxed)
}

#[cfg(target_os = "linux")]
fn status_kb(key: &str) -> Option<u64> {
    let status = std::fs::read_to_string("/proc/self/status").ok()?;
    let line = status.lines().find(|l| l.starts_with(key))?;
    let kb: u64 = line.split_whitespace().nth(1)?.parse().ok()?;
    Some(kb * 1024)
}

/// The process's working set and private bytes, now and at their peaks
/// (`GetProcessMemoryInfo`).
#[cfg(windows)]
#[derive(Clone, Copy, Debug, Default)]
pub struct WindowsMemory {
    pub working_set: u64,
    pub peak_working_set: u64,
    pub private: u64,
    pub peak_private: u64,
}

#[cfg(windows)]
pub fn windows_memory() -> Option<WindowsMemory> {
    use std::ffi::c_void;
    #[repr(C)]
    #[derive(Default)]
    struct Counters {
        cb: u32,
        page_fault_count: u32,
        peak_working_set_size: usize,
        working_set_size: usize,
        quota_peak_paged_pool_usage: usize,
        quota_paged_pool_usage: usize,
        quota_peak_non_paged_pool_usage: usize,
        quota_non_paged_pool_usage: usize,
        pagefile_usage: usize,
        peak_pagefile_usage: usize,
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetCurrentProcess() -> *mut c_void;
        fn K32GetProcessMemoryInfo(process: *mut c_void, counters: *mut Counters, cb: u32) -> i32;
    }
    let mut c = Counters {
        cb: std::mem::size_of::<Counters>() as u32,
        ..Counters::default()
    };
    // SAFETY: a pseudo-handle of this process and a buffer of the size given.
    let ok = unsafe { K32GetProcessMemoryInfo(GetCurrentProcess(), &mut c, c.cb) };
    (ok != 0).then_some(WindowsMemory {
        working_set: c.working_set_size as u64,
        peak_working_set: c.peak_working_set_size as u64,
        private: c.pagefile_usage as u64,
        peak_private: c.peak_pagefile_usage as u64,
    })
}

/// Resident bytes now, their peak so far, and swapped-out bytes (Linux
/// `VmRSS`, `VmHWM`, `VmSwap`; Windows the working set and its peak, no swap).
fn resident() -> (Option<u64>, Option<u64>, Option<u64>) {
    #[cfg(target_os = "linux")]
    {
        (
            status_kb("VmRSS:"),
            status_kb("VmHWM:"),
            status_kb("VmSwap:"),
        )
    }
    #[cfg(windows)]
    {
        match windows_memory() {
            Some(m) => (Some(m.working_set), Some(m.peak_working_set), None),
            None => (None, None, None),
        }
    }
    #[cfg(not(any(target_os = "linux", windows)))]
    {
        (None, None, None)
    }
}

/// End the current phase under `label` and start the next.
pub fn mark(label: &str) {
    if !counting() {
        return;
    }
    let live = LIVE.load(Relaxed);
    let peak = PEAK.swap(live, Relaxed).max(live);
    let (rss, hwm, swap) = resident();
    let phase = Phase {
        label: label.to_string(),
        live,
        peak,
        rss,
        hwm,
        swap,
    };
    PHASES.lock().expect("no panic while recording").push(phase);
}

/// Record the size of a buffer.
pub fn note(label: &str, bytes: usize) {
    if counting() {
        BUFFERS
            .lock()
            .expect("no panic while recording")
            .push((label.to_string(), bytes));
    }
}

/// The phases recorded so far.
pub fn phases() -> Vec<Phase> {
    PHASES.lock().expect("no panic while recording").clone()
}

/// The buffers recorded so far.
pub fn buffers() -> Vec<(String, usize)> {
    BUFFERS.lock().expect("no panic while recording").clone()
}

/// The bytes a vector holds.
pub fn bytes_of<T>(v: &Vec<T>) -> usize {
    v.capacity() * std::mem::size_of::<T>()
}
