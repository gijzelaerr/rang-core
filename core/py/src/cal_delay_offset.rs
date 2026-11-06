//! `rang._core.cal_delay_offset_solve`: the delay term K as QuartiCal's
//! `delay_and_offset` (`rang_core::cal::delay_offset`, task C2c,
//! `research/c2c-bandpass.md`), and `rang._core.cal_bandpass_fill_gaps`,
//! CASA's `fillgaps` for B tables (`rang_core::cal::bandpass`), for
//! `rang.cal_delay` and `rang.cal_bandpass`.
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
use rang_core::cal::bandpass::{self, Complex32};
use rang_core::cal::delay_offset::{self, Settings};
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

/// Solve `delay_and_offset`. Arguments as `cal_delay_solve`, plus
/// `start_offsets` (rang's offset start; false is QuartiCal's zero start)
/// and `offsets` (float64 radians, `nparam * 2`). `err` is the delay error
/// with the offset marginalised. Returns (iterations, converged fraction).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_delay_offset_solve(
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
    start_offsets: bool,
    mut delays: Rw<'_, f64>,
    mut offsets: Rw<'_, f64>,
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
    let offsets = exact_mut(&mut offsets, "offsets", 2 * nparam)?;
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
        let s = delay_offset::solve_with(&p, freq, &settings, start_offsets)?;
        let e = delay_offset::delay_errors(&p, freq, &s.delays, &s.offsets, &s.flags)?;
        Ok::<_, rang_core::cal::diag::Error>((s, e))
    });
    let (solution, e) = result.map_err(|e| PyValueError::new_err(format!("{e}")))?;
    for (i, d) in solution.delays.iter().enumerate() {
        delays[2 * i..2 * i + 2].copy_from_slice(d);
    }
    for (i, d) in solution.offsets.iter().enumerate() {
        offsets[2 * i..2 * i + 2].copy_from_slice(d);
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

/// CASA's `fillgaps` in place on a B table's solutions: `sol` complex64 as
/// float32 pairs and `flag` (uint8, 1 flagged), both `(nrow, nchan, npar)`.
#[pyfunction]
pub fn cal_bandpass_fill_gaps(
    nrow: usize,
    nchan: usize,
    npar: usize,
    maxgap: usize,
    mut sol: Rw<'_, f32>,
    mut flag: Rw<'_, u8>,
) -> PyResult<()> {
    let n = nrow
        .checked_mul(nchan)
        .and_then(|x| x.checked_mul(npar))
        .ok_or_else(|| PyValueError::new_err("nrow * nchan * npar overflows"))?;
    let sol = exact_mut(&mut sol, "sol", 2 * n)?;
    let flag = exact_mut(&mut flag, "flag", n)?;
    let mut s: Vec<Complex32> = sol
        .chunks_exact(2)
        .map(|c| Complex32::new(c[0], c[1]))
        .collect();
    let mut f: Vec<bool> = flag.iter().map(|&x| x != 0).collect();
    bandpass::fill_gaps(&mut s, &mut f, nrow, nchan, npar, maxgap);
    for (o, v) in sol.chunks_exact_mut(2).zip(&s) {
        o[0] = v.re;
        o[1] = v.im;
    }
    for (o, v) in flag.iter_mut().zip(&f) {
        *o = u8::from(*v);
    }
    Ok(())
}
