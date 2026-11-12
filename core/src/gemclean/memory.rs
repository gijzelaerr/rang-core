// SPDX-License-Identifier: GPL-3.0-or-later
//! Allocation accounting of the `gemclean` binary: the bytes its allocator
//! ([`crate::gemclean::host::HugePageAlloc`]) holds, the largest amount per
//! phase of a run, and the sizes of the main buffers, for the memory report
//! (`-memory-report`, and `memory` in `-report.json`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The counters are two relaxed atomics touched once per allocation. Under any
//! other allocator (the Python extension, other platforms) nothing counts and
//! [`mark`] and [`note`] do nothing. Heap bytes are what was asked for, not
//! resident pages: huge-page rounding, untouched pages and the program's own
//! text are not in them, so the process's peak RSS is reported beside them.

// The counters' writers are the allocator's, which exists on 64-bit Linux only.
#![cfg_attr(
    not(all(target_os = "linux", target_pointer_width = "64")),
    allow(dead_code)
)]

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

fn status_kb(key: &str) -> Option<u64> {
    let status = std::fs::read_to_string("/proc/self/status").ok()?;
    let line = status.lines().find(|l| l.starts_with(key))?;
    let kb: u64 = line.split_whitespace().nth(1)?.parse().ok()?;
    Some(kb * 1024)
}

/// End the current phase under `label` and start the next.
pub fn mark(label: &str) {
    if !counting() {
        return;
    }
    let live = LIVE.load(Relaxed);
    let peak = PEAK.swap(live, Relaxed).max(live);
    let phase = Phase {
        label: label.to_string(),
        live,
        peak,
        rss: status_kb("VmRSS:"),
        hwm: status_kb("VmHWM:"),
        swap: status_kb("VmSwap:"),
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
