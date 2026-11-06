//! `rang._core.cal_delay_solve`: the delay term K of `rang_core::cal::delay`
//! (task C2b, `research/c2b-delay.md`), for `rang.cal_delay`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Complex inputs are complex64 arrays viewed as float32 pairs; every array
//! must be C-contiguous with the stated length (a ValueError names it). A
//! solver error raises ValueError.

use crate::{Ro, Rw, c_slice, c_slice_mut, detach};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rang_core::cal::delay::{self, Settings};
use rang_core::fused::Model;
use rang_core::solve::Problem;

fn exact<'a, T: numpy::Element>(a: &'a Ro<'_, T>, name: &str, len: usize) -> PyResult<&'a [T]> {
    let s = c_slice(a, name)?;
    if s.len() != len {
        return Err(PyValueError::new_err(format!(
            "{name} must hold {len} elements, not {}",
            s.len()
        )));
    }
    Ok(s)
}

fn exact_mut<'a, T: numpy::Element>(
    a: &'a mut Rw<'_, T>,
    name: &str,
    len: usize,
) -> PyResult<&'a mut [T]> {
    let s = c_slice_mut(a, name)?;
    if s.len() != len {
        return Err(PyValueError::new_err(format!(
            "{name} must hold {len} elements, not {}",
            s.len()
        )));
    }
    Ok(s)
}

/// Solve the delay term. `chan_freq` (float64, `nchan`, Hz); `refant < 0`
/// for no QuartiCal referencing; `estimate_antenna < 0` for no FFT initial
/// estimate. Writes `delays` (float64 seconds, `nparam * 2`), `flags` (int8,
/// `nparam`), `err` (float64 seconds, `nparam * 2`, rang's delay error),
/// `gain_flags` (int8, `ntime * nchan * nant`) and, unless it is empty,
/// `gains` (complex128 viewed as float64, `ntime * nchan * nant * 4`).
/// Returns (iterations, converged fraction).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_delay_solve(
    py: Python<'_>,
    nrow: usize,
    nchan: usize,
    ntime: usize,
    nfreq: usize,
    nant: usize,
    data: Ro<'_, f32>,
    weights: Ro<'_, f32>,
    model: Ro<'_, f32>,
    flag: Ro<'_, u8>,
    flag_row: Ro<'_, u8>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    time_bin: Ro<'_, u32>,
    freq_bin: Ro<'_, u32>,
    chan_freq: Ro<'_, f64>,
    max_iterations: usize,
    stop_criterion: f64,
    stop_fraction: f64,
    refant: i64,
    estimate_antenna: i64,
    mut delays: Rw<'_, f64>,
    mut flags: Rw<'_, i8>,
    mut err: Rw<'_, f64>,
    mut gain_flags: Rw<'_, i8>,
    mut gains: Rw<'_, f64>,
) -> PyResult<(usize, f64)> {
    let cells = nrow
        .checked_mul(nchan)
        .ok_or_else(|| PyValueError::new_err("nrow * nchan overflows"))?;
    let nparam = ntime
        .checked_mul(nfreq)
        .and_then(|x| x.checked_mul(nant))
        .ok_or_else(|| PyValueError::new_err("ntime * nfreq * nant overflows"))?;
    let ngain = ntime
        .checked_mul(nchan)
        .and_then(|x| x.checked_mul(nant))
        .ok_or_else(|| PyValueError::new_err("ntime * nchan * nant overflows"))?;
    let p = Problem {
        nrow,
        nchan,
        ntime_bins: ntime,
        nfreq_bins: nfreq,
        nant,
        data: exact(&data, "data", 8 * cells)?,
        weights: exact(&weights, "weights", 4 * cells)?,
        model: Model::Stored(exact(&model, "model", 8 * cells)?),
        flag: exact(&flag, "flag", 4 * cells)?,
        flag_row: exact(&flag_row, "flag_row", nrow)?,
        antenna1: exact(&antenna1, "antenna1", nrow)?,
        antenna2: exact(&antenna2, "antenna2", nrow)?,
        time_bin: exact(&time_bin, "time_bin", nrow)?,
        freq_bin: exact(&freq_bin, "freq_bin", nchan)?,
    };
    let freq = exact(&chan_freq, "chan_freq", nchan)?;
    let delays = exact_mut(&mut delays, "delays", 2 * nparam)?;
    let flags = exact_mut(&mut flags, "flags", nparam)?;
    let err = exact_mut(&mut err, "err", 2 * nparam)?;
    let gain_flags = exact_mut(&mut gain_flags, "gain_flags", ngain)?;
    let gains = c_slice_mut(&mut gains, "gains")?;
    if !gains.is_empty() && gains.len() != 4 * ngain {
        return Err(PyValueError::new_err(format!(
            "gains must be empty or hold {} elements, not {}",
            4 * ngain,
            gains.len()
        )));
    }
    let settings = Settings {
        max_iterations,
        stop_criterion,
        stop_fraction,
        reference_antenna: usize::try_from(refant).ok(),
        estimate_antenna: usize::try_from(estimate_antenna).ok(),
    };
    let result = detach(py, || {
        let solution = delay::solve(&p, freq, &settings)?;
        let e = delay::delay_errors(&p, freq, &solution.delays, &solution.flags)?;
        Ok::<_, rang_core::cal::diag::Error>((solution, e))
    });
    let (solution, e) = result.map_err(|e| PyValueError::new_err(format!("{e}")))?;
    for (i, d) in solution.delays.iter().enumerate() {
        delays[2 * i..2 * i + 2].copy_from_slice(d);
    }
    for (i, d) in e.iter().enumerate() {
        err[2 * i..2 * i + 2].copy_from_slice(d);
    }
    flags.copy_from_slice(&solution.flags);
    gain_flags.copy_from_slice(&solution.gain_flags);
    if !gains.is_empty() {
        for (i, g) in solution.gains.iter().enumerate() {
            gains[4 * i..4 * i + 4].copy_from_slice(&[g[0].re, g[0].im, g[1].re, g[1].im]);
        }
    }
    Ok((solution.iterations, solution.converged_fraction))
}
