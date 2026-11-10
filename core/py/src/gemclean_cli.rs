//! `rang._core.gemclean_main`: GeMClean's command line inside the extension,
//! for the wheel's console script `gemclean` (task G8, `research/g8-wheel.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.

use pyo3::prelude::*;
use std::io::Write;

/// Run gemclean with `args` (without the program name), the GIL released;
/// returns the binary's exit code: 0, 2 on an error (the message on stderr),
/// 101 on a panic (the default hook has printed it). Rust's stdout and
/// stderr are flushed before returning.
#[pyfunction]
pub fn gemclean_main(py: Python<'_>, args: Vec<String>) -> i32 {
    py.detach(|| {
        let code =
            std::panic::catch_unwind(|| rang_core::gemclean::cli::main(&args)).unwrap_or(101);
        let _ = std::io::stdout().flush();
        let _ = std::io::stderr().flush();
        code
    })
}
