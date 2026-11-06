//! `rang._core.cal_parang_rotate`, `cal_kcross_solve`, `cal_xf_solve`,
//! `cal_df_solve`: the polarisation terms of `rang_core::cal::parang`,
//! `crosshand` and `leakage` (task C6, `research/c6-polterms.md`), for
//! `rang.cal_pol`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Complex inputs are complex64 arrays viewed as float32 pairs; every array
//! must be C-contiguous with the stated length (a ValueError names it). A
//! kernel error raises ValueError.

use crate::{Ro, Rw, c_slice, c_slice_mut};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rang_core::cal::{crosshand, leakage, parang};

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

fn cells(nrow: usize, nchan: usize) -> PyResult<usize> {
    nrow.checked_mul(nchan)
        .ok_or_else(|| PyValueError::new_err("nrow * nchan overflows"))
}

/// Rotate `data` (complex64 as float32, `(row, chan, 4)`) by the
/// parallactic-angle term: `P_p M P_q^T`, or its inverse with `inverse`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_parang_rotate(
    nrow: usize,
    nchan: usize,
    data: Ro<'_, f32>,
    angle_p: Ro<'_, f64>,
    angle_q: Ro<'_, f64>,
    inverse: bool,
    mut out: Rw<'_, f32>,
) -> PyResult<()> {
    let n = cells(nrow, nchan)?;
    let data = exact(&data, "data", 8 * n)?;
    let ap = exact(&angle_p, "angle_p", nrow)?;
    let aq = exact(&angle_q, "angle_q", nrow)?;
    let out = exact_mut(&mut out, "out", 8 * n)?;
    parang::rotate(data, nrow, nchan, ap, aq, inverse, out).map_err(PyValueError::new_err)
}

struct Inputs<'a> {
    data: &'a [f32],
    model: &'a [f32],
    weight: &'a [f32],
    flag: &'a [u8],
    flag_row: &'a [u8],
    antenna1: &'a [u32],
    antenna2: &'a [u32],
    time_bin: &'a [u32],
}

#[allow(clippy::too_many_arguments)]
fn inputs<'a>(
    nrow: usize,
    nchan: usize,
    data: &'a Ro<'_, f32>,
    model: &'a Ro<'_, f32>,
    weight: &'a Ro<'_, f32>,
    flag: &'a Ro<'_, u8>,
    flag_row: &'a Ro<'_, u8>,
    antenna1: &'a Ro<'_, u32>,
    antenna2: &'a Ro<'_, u32>,
    time_bin: &'a Ro<'_, u32>,
) -> PyResult<Inputs<'a>> {
    let n = cells(nrow, nchan)?;
    Ok(Inputs {
        data: exact(data, "data", 8 * n)?,
        model: exact(model, "model", 8 * n)?,
        weight: exact(weight, "weight", 4 * n)?,
        flag: exact(flag, "flag", 4 * n)?,
        flag_row: exact(flag_row, "flag_row", nrow)?,
        antenna1: exact(antenna1, "antenna1", nrow)?,
        antenna2: exact(antenna2, "antenna2", nrow)?,
        time_bin: exact(time_bin, "time_bin", nrow)?,
    })
}

/// KCROSS per interval: writes `delay` (ns), `ok` (uint8), `err` (ns) per
/// interval and the normalised summed spectrum (complex128 as float64,
/// `(interval, chan)`).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_kcross_solve(
    nrow: usize,
    nchan: usize,
    ntime: usize,
    data: Ro<'_, f32>,
    model: Ro<'_, f32>,
    weight: Ro<'_, f32>,
    flag: Ro<'_, u8>,
    flag_row: Ro<'_, u8>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    time_bin: Ro<'_, u32>,
    freq: Ro<'_, f64>,
    mut delay: Rw<'_, f64>,
    mut ok: Rw<'_, u8>,
    mut err: Rw<'_, f64>,
    mut spectrum: Rw<'_, f64>,
) -> PyResult<()> {
    let i = inputs(
        nrow, nchan, &data, &model, &weight, &flag, &flag_row, &antenna1, &antenna2, &time_bin,
    )?;
    let freq = exact(&freq, "freq", nchan)?;
    let p = crosshand::Problem {
        nrow,
        nchan,
        ntime,
        data: i.data,
        model: i.model,
        weight: i.weight,
        flag: i.flag,
        flag_row: i.flag_row,
        antenna1: i.antenna1,
        antenna2: i.antenna2,
        time_bin: i.time_bin,
        freq,
    };
    let sol = crosshand::kcross(&p).map_err(PyValueError::new_err)?;
    let delay = exact_mut(&mut delay, "delay", ntime)?;
    for (d, s) in delay.iter_mut().zip(&sol) {
        *d = s.delay_ns;
    }
    let ok = exact_mut(&mut ok, "ok", ntime)?;
    for (o, s) in ok.iter_mut().zip(&sol) {
        *o = u8::from(s.ok);
    }
    let err = exact_mut(&mut err, "err", ntime)?;
    for (e, s) in err.iter_mut().zip(&sol) {
        *e = s.err_ns;
    }
    let spectrum = exact_mut(&mut spectrum, "spectrum", 2 * ntime * nchan)?;
    for (t, s) in sol.iter().enumerate() {
        for (c, v) in s.spectrum.iter().enumerate() {
            spectrum[2 * (t * nchan + c)] = v.re;
            spectrum[2 * (t * nchan + c) + 1] = v.im;
        }
    }
    Ok(())
}

/// Xf per interval and channel: writes `x` (complex128 as float64), `ok`
/// (uint8) and `err` (rad), each `(interval, chan)`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_xf_solve(
    nrow: usize,
    nchan: usize,
    ntime: usize,
    data: Ro<'_, f32>,
    model: Ro<'_, f32>,
    weight: Ro<'_, f32>,
    flag: Ro<'_, u8>,
    flag_row: Ro<'_, u8>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    time_bin: Ro<'_, u32>,
    freq: Ro<'_, f64>,
    mut x: Rw<'_, f64>,
    mut ok: Rw<'_, u8>,
    mut err: Rw<'_, f64>,
) -> PyResult<()> {
    let i = inputs(
        nrow, nchan, &data, &model, &weight, &flag, &flag_row, &antenna1, &antenna2, &time_bin,
    )?;
    let freq = exact(&freq, "freq", nchan)?;
    let p = crosshand::Problem {
        nrow,
        nchan,
        ntime,
        data: i.data,
        model: i.model,
        weight: i.weight,
        flag: i.flag,
        flag_row: i.flag_row,
        antenna1: i.antenna1,
        antenna2: i.antenna2,
        time_bin: i.time_bin,
        freq,
    };
    let sol = crosshand::xf(&p).map_err(PyValueError::new_err)?;
    let n = ntime * nchan;
    let x = exact_mut(&mut x, "x", 2 * n)?;
    let ok = exact_mut(&mut ok, "ok", n)?;
    let err = exact_mut(&mut err, "err", n)?;
    for (t, s) in sol.iter().enumerate() {
        for c in 0..nchan {
            let k = t * nchan + c;
            x[2 * k] = s.x[c].re;
            x[2 * k + 1] = s.x[c].im;
            ok[k] = u8::from(s.ok[c]);
            err[k] = s.err[c];
        }
    }
    Ok(())
}

/// Df per interval and channel. Writes `d` (complex128 as float64,
/// `(interval, chan, ant, 2)`), `flags` (uint8, same without the pair),
/// `var_re`, `var_im` (float64, same), and per `(interval, chan)` `chi2`,
/// `neq`, `npar` (float64) and `gauge_antenna` (int64, -1 for none).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn cal_df_solve(
    nrow: usize,
    nchan: usize,
    ntime: usize,
    nant: usize,
    data: Ro<'_, f32>,
    model: Ro<'_, f32>,
    weight: Ro<'_, f32>,
    flag: Ro<'_, u8>,
    flag_row: Ro<'_, u8>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    time_bin: Ro<'_, u32>,
    minblperant: usize,
    gauge: bool,
    refants: Vec<usize>,
    mut d: Rw<'_, f64>,
    mut flags: Rw<'_, u8>,
    mut var_re: Rw<'_, f64>,
    mut var_im: Rw<'_, f64>,
    mut chi2: Rw<'_, f64>,
    mut neq: Rw<'_, f64>,
    mut npar: Rw<'_, f64>,
    mut gauge_antenna: Rw<'_, i64>,
) -> PyResult<()> {
    let i = inputs(
        nrow, nchan, &data, &model, &weight, &flag, &flag_row, &antenna1, &antenna2, &time_bin,
    )?;
    let p = leakage::Problem {
        nrow,
        nchan,
        ntime,
        nant,
        data: i.data,
        model: i.model,
        weight: i.weight,
        flag: i.flag,
        flag_row: i.flag_row,
        antenna1: i.antenna1,
        antenna2: i.antenna2,
        time_bin: i.time_bin,
    };
    let s = leakage::Settings {
        minblperant,
        gauge,
        refants: &refants,
    };
    let sol = leakage::solve(&p, &s).map_err(PyValueError::new_err)?;
    let n = ntime * nchan;
    exact_mut(&mut d, "d", 4 * n * nant)?.copy_from_slice(&sol.d);
    for (o, &f) in exact_mut(&mut flags, "flags", 2 * n * nant)?
        .iter_mut()
        .zip(&sol.flag)
    {
        *o = u8::from(f);
    }
    exact_mut(&mut var_re, "var_re", 2 * n * nant)?.copy_from_slice(&sol.var_re);
    exact_mut(&mut var_im, "var_im", 2 * n * nant)?.copy_from_slice(&sol.var_im);
    exact_mut(&mut chi2, "chi2", n)?.copy_from_slice(&sol.chi2);
    for (o, &v) in exact_mut(&mut neq, "neq", n)?.iter_mut().zip(&sol.neq) {
        *o = v as f64;
    }
    for (o, &v) in exact_mut(&mut npar, "npar", n)?.iter_mut().zip(&sol.npar) {
        *o = v as f64;
    }
    exact_mut(&mut gauge_antenna, "gauge_antenna", n)?.copy_from_slice(&sol.gauge_antenna);
    Ok(())
}
