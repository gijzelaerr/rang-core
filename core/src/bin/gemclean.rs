// SPDX-License-Identifier: GPL-3.0-or-later
//! `gemclean`: a reference CLEAN imager for Measurement Sets with WSClean-like
//! flags (`research/gemclean.md`); the source build's front end of
//! [`rang_core::gemclean::cli`] (task G8, `research/g8-wheel.md`; the wheel's is
//! the console script over `rang._core.gemclean_main`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.

#[cfg(all(target_os = "linux", target_pointer_width = "64"))]
#[global_allocator]
static ALLOCATOR: rang_core::gemclean::host::HugePageAlloc =
    rang_core::gemclean::host::HugePageAlloc;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let code = rang_core::gemclean::cli::main(&args);
    if code != 0 {
        std::process::exit(code);
    }
}
