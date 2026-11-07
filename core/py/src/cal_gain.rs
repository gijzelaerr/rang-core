//! `rang._core.cal_gain_*`: the gain term G of `rang_core::cal::diag` and
//! CASA's rules around it in `rang_core::cal::reference` (task C2a,
//! `research/c2a-gain.md`), for `rang.cal_gain`.
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
use rang_core::cal::diag::{self, Kind, Settings};
use rang_core::cal::reference::{self, Mode};
use rang_core::fused::Model;
use rang_core::jones::C64;
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

/// The borrowed problem arrays of one solve.
struct Arrays<'a> {
    data: &'a [f32],
    weights: &'a [f32],
    model: &'a [f32],
    flag: &'a [u8],
    flag_row: &'a [u8],
    antenna1: &'a [u32],
    antenna2: &'a [u32],
    time_bin: &'a [u32],
    freq_bin: &'a [u32],
}

#[allow(clippy::too_many_arguments)]
fn arrays<'a>(
    nrow: usize,
    nchan: usize,
    data: &'a Ro<'_, f32>,
    weights: &'a Ro<'_, f32>,
    model: &'a Ro<'_, f32>,
    flag: &'a Ro<'_, u8>,
    flag_row: &'a Ro<'_, u8>,
    antenna1: &'a Ro<'_, u32>,
    antenna2: &'a Ro<'_, u32>,
    time_bin: &'a Ro<'_, u32>,
    freq_bin: &'a Ro<'_, u32>,
) -> PyResult<Arrays<'a>> {
    let cells = nrow
        .checked_mul(nchan)
        .ok_or_else(|| PyValueError::new_err("nrow * nchan overflows"))?;
    Ok(Arrays {
        data: exact(data, "data", 8 * cells)?,
        weights: exact(weights, "weights", 4 * cells)?,
        model: exact(model, "model", 8 * cells)?,
        flag: exact(flag, "flag", 4 * cells)?,
        flag_row: exact(flag_row, "flag_row", nrow)?,
        antenna1: exact(antenna1, "antenna1", nrow)?,
        antenna2: exact(antenna2, "antenna2", nrow)?,
        time_bin: exact(time_bin, "time_bin", nrow)?,
        freq_bin: exact(freq_bin, "freq_bin", nchan)?,
    })
}

fn problem<'a>(
    a: &Arrays<'a>,
    nrow: usize,
    nchan: usize,
    ntime: usize,
    nfreq: usize,
    nant: usize,
) -> Problem<'a> {
    Problem {
        nrow,
        nchan,
        ntime_bins: ntime,
        nfreq_bins: nfreq,
        nant,
        data: a.data,
        weights: a.weights,
        model: Model::Stored(a.model),
        flag: a.flag,
        flag_row: a.flag_row,
        antenna1: a.antenna1,
        antenna2: a.antenna2,
        time_bin: a.time_bin,
        freq_bin: a.freq_bin,
    }
}

/// Solve one diagonal term: `kind` 0 `diag_complex` (calmode `ap`), 1
/// `phase` (calmode `p`); `refant < 0` for no QuartiCal referencing. Writes
/// `gains` (complex128 viewed as float64, `ngain * 4`), `flags` (int8,
/// `ngain`), `snr` and `err` (float32, `ngain * 2`, CASA's statistics at
/// the solution). Returns (iterations, converged fraction).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_gain_solve(
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
    kind: u32,
    max_iterations: usize,
    stop_criterion: f64,
    stop_fraction: f64,
    refant: i64,
    mut gains: Rw<'_, f64>,
    mut flags: Rw<'_, i8>,
    mut snr: Rw<'_, f32>,
    mut err: Rw<'_, f32>,
) -> PyResult<(usize, f64)> {
    let a = arrays(
        nrow, nchan, &data, &weights, &model, &flag, &flag_row, &antenna1, &antenna2, &time_bin,
        &freq_bin,
    )?;
    let ngain = ntime
        .checked_mul(nfreq)
        .and_then(|x| x.checked_mul(nant))
        .ok_or_else(|| PyValueError::new_err("ntime * nfreq * nant overflows"))?;
    let gains = exact_mut(&mut gains, "gains", 4 * ngain)?;
    let flags = exact_mut(&mut flags, "flags", ngain)?;
    let snr = exact_mut(&mut snr, "snr", 2 * ngain)?;
    let err = exact_mut(&mut err, "err", 2 * ngain)?;
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
    let p = problem(&a, nrow, nchan, ntime, nfreq, nant);
    let result = detach(py, || {
        let solution = diag::solve(&p, &settings)?;
        let stats = diag::solution_statistics(&p, &solution.gains, &solution.flags)?;
        Ok::<_, diag::Error>((solution, stats))
    });
    let (solution, (s, e)) = result.map_err(|e| PyValueError::new_err(format!("{e}")))?;
    for (i, g) in solution.gains.iter().enumerate() {
        gains[4 * i..4 * i + 4].copy_from_slice(&[g[0].re, g[0].im, g[1].re, g[1].im]);
    }
    flags.copy_from_slice(&solution.flags);
    snr.copy_from_slice(&s);
    err.copy_from_slice(&e);
    Ok((solution.iterations, solution.converged_fraction))
}

/// Write a counted solve's `Trace` into `counts` (uint64 pairs) and return
/// (iterations recorded, the error's iteration and message or None); a
/// shape or settings error before the loop raises ValueError (task W3b).
pub(crate) fn write_trace(
    result: Result<(), diag::Error>,
    trace: &diag::Trace,
    counts: &mut [u64],
) -> PyResult<(usize, Option<(usize, String)>)> {
    if trace.counts.len() * 2 > counts.len() {
        return Err(PyValueError::new_err("counts too short"));
    }
    for (i, &(c, x)) in trace.counts.iter().enumerate() {
        counts[2 * i] = c as u64;
        counts[2 * i + 1] = x as u64;
    }
    match (result, trace.error_iteration) {
        (Ok(()), _) => Ok((trace.counts.len(), None)),
        (Err(e), Some(k)) => Ok((trace.counts.len(), Some((k, format!("{e}"))))),
        (Err(e), None) => Err(PyValueError::new_err(format!("{e}"))),
    }
}

/// The counts of `cal_gain_solve`'s global stop test (task W3b,
/// `research/w3b-chainchunks.md`): arguments as `cal_gain_solve` without
/// the outputs; writes per iteration the converged and flagged gains summed
/// over every interval into `counts` (uint64, `2 * max(max_iterations,
/// 1)`). Returns (iterations recorded, the iteration and message of a
/// solver error or None); nothing else is written.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_gain_trace(
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
    kind: u32,
    max_iterations: usize,
    stop_criterion: f64,
    stop_fraction: f64,
    refant: i64,
    mut counts: Rw<'_, u64>,
) -> PyResult<(usize, Option<(usize, String)>)> {
    let a = arrays(
        nrow, nchan, &data, &weights, &model, &flag, &flag_row, &antenna1, &antenna2, &time_bin,
        &freq_bin,
    )?;
    let counts = exact_mut(&mut counts, "counts", 2 * max_iterations.max(1))?;
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
    let p = problem(&a, nrow, nchan, ntime, nfreq, nant);
    let (result, trace) = detach(py, || diag::solve_counted(&p, &settings));
    write_trace(result.map(|_| ()), &trace, counts)
}

/// CASA's `minblperant` test per (time bin, frequency bin, antenna): writes
/// `ok` (uint8, `ntime * nfreq * nant`).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_gain_minblperant(
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
    minblperant: usize,
    mut ok: Rw<'_, u8>,
) -> PyResult<()> {
    let a = arrays(
        nrow, nchan, &data, &weights, &model, &flag, &flag_row, &antenna1, &antenna2, &time_bin,
        &freq_bin,
    )?;
    let out = exact_mut(&mut ok, "ok", ntime * nfreq * nant)?;
    if a.antenna1
        .iter()
        .chain(a.antenna2)
        .any(|&x| x as usize >= nant)
        || a.time_bin.iter().any(|&t| t as usize >= ntime)
        || a.freq_bin.iter().any(|&f| f as usize >= nfreq)
    {
        return Err(PyValueError::new_err("antenna or bin index out of range"));
    }
    let p = problem(&a, nrow, nchan, ntime, nfreq, nant);
    let result = detach(py, || reference::minblperant_ok(&p, minblperant));
    for (o, r) in out.iter_mut().zip(result) {
        *o = u8::from(r);
    }
    Ok(())
}

/// CASA's `applyRefAnt` for one window, in place: `sol` complex128 viewed
/// as float64 (`ntime * nant * npar * nchan * 2`), `flag` uint8 (`ntime *
/// nant * npar * nchan`), `positions` float64 (`nant * 3`), `refants` the
/// user's list; `strict` for `refantmode='strict'`. Writes the refant used
/// per time into `used` (int32, -1 where the interval was flagged) and
/// returns whether an alternate was used.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_gain_apply_refant(
    ntime: usize,
    nant: usize,
    npar: usize,
    nchan: usize,
    mut sol: Rw<'_, f64>,
    mut flag: Rw<'_, u8>,
    positions: Ro<'_, f64>,
    refants: Vec<usize>,
    strict: bool,
    mut used: Rw<'_, i32>,
) -> PyResult<bool> {
    let n = ntime * nant * npar * nchan;
    let sol = exact_mut(&mut sol, "sol", 2 * n)?;
    let flag = exact_mut(&mut flag, "flag", n)?;
    let positions = exact(&positions, "positions", 3 * nant)?;
    let used = exact_mut(&mut used, "used", ntime)?;
    let mut s: Vec<C64> = sol.chunks(2).map(|c| C64::new(c[0], c[1])).collect();
    let mut f: Vec<bool> = flag.iter().map(|&x| x != 0).collect();
    let mode = if strict { Mode::Strict } else { Mode::Flex };
    let out = reference::apply_refant(
        &mut s, &mut f, ntime, nant, npar, nchan, positions, &refants, mode,
    )
    .map_err(|e| PyValueError::new_err(e.0))?;
    for (c, v) in sol.chunks_mut(2).zip(&s) {
        c[0] = v.re;
        c[1] = v.im;
    }
    for (x, v) in flag.iter_mut().zip(&f) {
        *x = u8::from(*v);
    }
    used.copy_from_slice(&out.refant);
    Ok(out.used_alternate)
}
