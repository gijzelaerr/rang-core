// SPDX-License-Identifier: MIT
//! `rang._core.cal_gain_solve_streamed`: the diagonal gain solve of
//! `rang_core::cal::diag` streamed from a file of cell records
//! (`rang_core::cal::diag_stream`; issue #34, `research/selfcal-memory.md`),
//! for `rang.cal_stream`.

use crate::{Ro, Rw, c_slice, c_slice_mut, detach};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rang_core::cal::diag::{Kind, Settings};
use rang_core::cal::diag_stream;
use std::path::PathBuf;

/// Bytes of one cell record of the stream file.
#[pyfunction]
pub fn cal_stream_record_bytes() -> usize {
    diag_stream::RECORD_BYTES
}

/// Solve one diagonal term (`kind` 0 `diag_complex`, 1 `phase`; `refant <
/// 0` for no referencing) over the `ncells` records of `path`, read in
/// blocks of `block` records each iteration. `live` (uint8, one per gain of
/// `ntime * nfreq * nant`) marks the gains an unflagged cell involves.
/// Writes `gains` (complex128 viewed as float64, `ngain * 4`) and `flags`
/// (int8, `ngain`); returns (iterations, converged fraction). Equal to
/// `cal_gain_solve`'s gains, flags, iterations and fraction on the problem
/// the records list.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_gain_solve_streamed(
    py: Python<'_>,
    path: PathBuf,
    ncells: usize,
    block: usize,
    ntime: usize,
    nfreq: usize,
    nant: usize,
    live: Ro<'_, u8>,
    kind: u32,
    max_iterations: usize,
    stop_criterion: f64,
    stop_fraction: f64,
    refant: i64,
    mut gains: Rw<'_, f64>,
    mut flags: Rw<'_, i8>,
) -> PyResult<(usize, f64)> {
    let ngain = ntime
        .checked_mul(nfreq)
        .and_then(|x| x.checked_mul(nant))
        .ok_or_else(|| PyValueError::new_err("ntime * nfreq * nant overflows"))?;
    let live = c_slice(&live, "live")?;
    let gains = c_slice_mut(&mut gains, "gains")?;
    let flags = c_slice_mut(&mut flags, "flags")?;
    if live.len() != ngain || gains.len() != 4 * ngain || flags.len() != ngain {
        return Err(PyValueError::new_err(format!(
            "live, gains and flags must hold {ngain}, {} and {ngain} elements",
            4 * ngain
        )));
    }
    let kind = match kind {
        0 => Kind::DiagComplex,
        1 => Kind::Phase,
        _ => return Err(PyValueError::new_err("kind must be 0 (ap) or 1 (p)")),
    };
    let settings = Settings {
        kind,
        max_iterations,
        stop_criterion,
        stop_fraction,
        reference_antenna: usize::try_from(refant).ok(),
    };
    let live: Vec<bool> = live.iter().map(|&v| v != 0).collect();
    let solution = detach(py, || {
        diag_stream::solve_file(&path, ncells, block, ntime, nfreq, nant, &live, &settings)
    })
    .map_err(|e| PyValueError::new_err(format!("{e}")))?;
    for (i, g) in solution.gains.iter().enumerate() {
        gains[4 * i..4 * i + 4].copy_from_slice(&[g[0].re, g[0].im, g[1].re, g[1].im]);
    }
    flags.copy_from_slice(&solution.flags);
    Ok((solution.iterations, solution.converged_fraction))
}
