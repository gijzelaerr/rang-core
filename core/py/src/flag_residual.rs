// SPDX-License-Identifier: MIT
//! `rang._core.flag_residual_rang`, `flag_residual_quartical` and
//! `flag_residual_median_model`: the residual flagging kernels of
//! `rang_core::flag_residual` (issue #51, `research/flag-residual.md`), for
//! `rang.flag_residual`; `flag_residual_diag` and `flag_residual_solver`:
//! the flags at the gain solve (issue #58, `research/solver-flags.md`), for
//! `rang.solver_flags`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License; see
//! `LICENSES/MIT.txt`.
//!
//! The residual and data are C-contiguous float32 arrays of `(row, chan,
//! corr, 2)` (complex64 viewed as float32 pairs); flags are uint8; antennas
//! and dumps uint32. A bad argument raises ValueError.

use crate::{Ro, c_slice, detach};
use numpy::{IntoPyArray, PyArray1};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rang_core::flag_residual::{
    RangSettings, SolverSettings, diag_residual, flags_quartical, flags_rang, median_model,
    solver_flags,
};

/// The rang rule on one block of rows: `(new flags (row*chan,) uint8, counts dict)`.
#[pyfunction]
#[pyo3(signature = (res, flag, nrow, nchan, ncorr, a1, a2, dump, nant, sigma, persist, block, guard))]
#[allow(clippy::too_many_arguments)]
pub fn flag_residual_rang<'py>(
    py: Python<'py>,
    res: Ro<'py, f32>,
    flag: Ro<'py, u8>,
    nrow: usize,
    nchan: usize,
    ncorr: usize,
    a1: Ro<'py, u32>,
    a2: Ro<'py, u32>,
    dump: Ro<'py, u32>,
    nant: usize,
    sigma: f64,
    persist: f64,
    block: usize,
    guard: f64,
) -> PyResult<(Bound<'py, PyArray1<u8>>, Bound<'py, PyDict>)> {
    let (res, flag) = (c_slice(&res, "res")?, c_slice(&flag, "flag")?);
    let (a1, a2, dump) = (
        c_slice(&a1, "a1")?,
        c_slice(&a2, "a2")?,
        c_slice(&dump, "dump")?,
    );
    let s = RangSettings {
        sigma,
        persist,
        block,
        guard,
    };
    let (new, c) = detach(py, || {
        flags_rang(res, flag, nrow, nchan, ncorr, a1, a2, dump, nant, &s)
    })
    .map_err(PyValueError::new_err)?;
    let d = PyDict::new(py);
    d.set_item("cells", c.cells)?;
    d.set_item("cell_rule", c.cell_rule)?;
    d.set_item("persist_chan", c.persist_chan)?;
    d.set_item("persist_dump", c.persist_dump)?;
    d.set_item("guarded_baselines", c.guarded_baselines)?;
    d.set_item("added", c.added)?;
    Ok((new.into_pyarray(py), d))
}

/// QuartiCal 0.2.7's `mad_flags` on one data chunk: new flags `(row*chan,)` uint8.
#[pyfunction]
#[pyo3(signature = (res, flag, nrow, nchan, ncorr, a1, a2, nant, corr_sel, threshold_bl, threshold_global, max_deviation))]
#[allow(clippy::too_many_arguments)]
pub fn flag_residual_quartical<'py>(
    py: Python<'py>,
    res: Ro<'py, f32>,
    flag: Ro<'py, u8>,
    nrow: usize,
    nchan: usize,
    ncorr: usize,
    a1: Ro<'py, u32>,
    a2: Ro<'py, u32>,
    nant: usize,
    corr_sel: Vec<usize>,
    threshold_bl: f64,
    threshold_global: f64,
    max_deviation: f64,
) -> PyResult<Bound<'py, PyArray1<u8>>> {
    let (res, flag) = (c_slice(&res, "res")?, c_slice(&flag, "flag")?);
    let (a1, a2) = (c_slice(&a1, "a1")?, c_slice(&a2, "a2")?);
    let out = detach(py, || {
        flags_quartical(
            res,
            flag,
            nrow,
            nchan,
            ncorr,
            a1,
            a2,
            nant,
            &corr_sel,
            threshold_bl,
            threshold_global,
            max_deviation,
        )
    })
    .map_err(PyValueError::new_err)?;
    Ok(out.into_pyarray(py))
}

/// The per-channel, per-correlation complex median, `(chan*corr*2,)` float32.
#[pyfunction]
pub fn flag_residual_median_model<'py>(
    py: Python<'py>,
    data: Ro<'py, f32>,
    flag: Ro<'py, u8>,
    nrow: usize,
    nchan: usize,
    ncorr: usize,
) -> PyResult<Bound<'py, PyArray1<f32>>> {
    let (data, flag) = (c_slice(&data, "data")?, c_slice(&flag, "flag")?);
    let out = detach(py, || median_model(data, flag, nrow, nchan, ncorr))
        .map_err(PyValueError::new_err)?;
    Ok(out.into_pyarray(py))
}

/// A diagonal term's parallel-hand residual: `(res (row*chan*2*2,) float32,
/// gain-flagged (row*chan,) uint8)`.
#[pyfunction]
#[pyo3(signature = (data, model, nrow, nchan, a1, a2, time_bin, freq_bin, gains, gain_flags, ntime, nfreq, nant))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn flag_residual_diag<'py>(
    py: Python<'py>,
    data: Ro<'py, f32>,
    model: Ro<'py, f32>,
    nrow: usize,
    nchan: usize,
    a1: Ro<'py, u32>,
    a2: Ro<'py, u32>,
    time_bin: Ro<'py, u32>,
    freq_bin: Ro<'py, u32>,
    gains: Ro<'py, f64>,
    gain_flags: Ro<'py, u8>,
    ntime: usize,
    nfreq: usize,
    nant: usize,
) -> PyResult<(Bound<'py, PyArray1<f32>>, Bound<'py, PyArray1<u8>>)> {
    let (data, model) = (c_slice(&data, "data")?, c_slice(&model, "model")?);
    let (a1, a2) = (c_slice(&a1, "a1")?, c_slice(&a2, "a2")?);
    let (tb, fb) = (
        c_slice(&time_bin, "time_bin")?,
        c_slice(&freq_bin, "freq_bin")?,
    );
    let (g, gf) = (
        c_slice(&gains, "gains")?,
        c_slice(&gain_flags, "gain_flags")?,
    );
    let (res, bad) = detach(py, || {
        diag_residual(
            data, model, nrow, nchan, a1, a2, tb, fb, g, gf, ntime, nfreq, nant,
        )
    })
    .map_err(PyValueError::new_err)?;
    Ok((res.into_pyarray(py), bad.into_pyarray(py)))
}

/// The flags of one solution interval's chunk: `(new flags (row*chan,) uint8,
/// counts dict)`.
#[pyfunction]
#[pyo3(signature = (res, flag, nrow, nchan, a1, a2, dump, nant, quartical, sigma, global_sigma, persist, block, guard, min_cells))]
#[allow(clippy::too_many_arguments)]
pub fn flag_residual_solver<'py>(
    py: Python<'py>,
    res: Ro<'py, f32>,
    flag: Ro<'py, u8>,
    nrow: usize,
    nchan: usize,
    a1: Ro<'py, u32>,
    a2: Ro<'py, u32>,
    dump: Ro<'py, u32>,
    nant: usize,
    quartical: bool,
    sigma: f64,
    global_sigma: f64,
    persist: f64,
    block: usize,
    guard: f64,
    min_cells: usize,
) -> PyResult<(Bound<'py, PyArray1<u8>>, Bound<'py, PyDict>)> {
    let (res, flag) = (c_slice(&res, "res")?, c_slice(&flag, "flag")?);
    let (a1, a2, dump) = (
        c_slice(&a1, "a1")?,
        c_slice(&a2, "a2")?,
        c_slice(&dump, "dump")?,
    );
    let s = SolverSettings {
        quartical,
        sigma,
        global_sigma,
        persist,
        block,
        guard,
        min_cells,
    };
    let (new, c) = detach(py, || {
        solver_flags(res, flag, nrow, nchan, a1, a2, dump, nant, &s)
    })
    .map_err(PyValueError::new_err)?;
    let d = PyDict::new(py);
    d.set_item("cells", c.cells)?;
    d.set_item("input_flagged", c.input_flagged)?;
    d.set_item("rule", c.rule)?;
    d.set_item("sparse_baselines", c.sparse_baselines)?;
    d.set_item("guarded_baselines", c.guarded_baselines)?;
    d.set_item("added", c.added)?;
    Ok((new.into_pyarray(py), d))
}
